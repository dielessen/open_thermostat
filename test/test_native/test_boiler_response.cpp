#include "control/BoilerResponse.h"
#include "control/FlowPolicy.h"
#include "control/LearnedState.h"
#include "control/RestFloor.h"
#include "control/ShadowComparison.h"
#include "BoilerResponseWidest.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <vector>

// rc.5 (P1): listening to the boiler (control/BoilerResponse.h) and the burner rest floor
// (control/RestFloor.h), plan docs/modern-thermostat/RC5-PLAN.md section 2.1.
namespace {
using heating::control::BoilerResponse;
using heating::control::ControlTuning;
using heating::control::FlowDemand;
using heating::control::FlowLearner;
using heating::control::FlowPolicy;
using heating::control::FlowSettings;
using heating::control::LearnedState;
using heating::control::LearnedStore;
using heating::control::RestFloor;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::ShadowComparison;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;

std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}
const cJSON* at(const cJSON* o, const char* key) { return cJSON_GetObjectItemCaseSensitive(o, key); }

// The E32 drives the boiler at 45 degC for a room 0.2 degC short (it asks heat, no warm-up),
// outdoor 7 degC (band 5..10), lowest flow 30, plan maximum 60, return 5 K below the flow.
struct Bench {
    BoilerResponse r;
    BoilerResponse::Sample s;
    Bench() {
        s.ownRequest = true; s.requestC = 45; s.demand = true; s.shortfallCentiC = 20;
        s.burnerOn = false; s.hotWater = false; s.flowCentiC = 4000; s.returnCentiC = 3500; s.modulationPct = 0;
        s.outdoorCentiC = 700; s.minimumC = 30; s.maximumC = 60; s.roomMeanCentiC = 2080;
    }
    void step() { s.now += 10 * second; r.sample(s); }
    void run(uint64_t ms) { for (uint64_t t = 0; t < ms; t += 10 * second) step(); }
    // The burner heats `ms` up to `flow`, then stops by itself there (the stop is the next step).
    void burn(uint64_t ms, int16_t flow, uint8_t pct = 20, bool withReturn = true) {
        s.burnerOn = true; s.modulationPct = pct;
        const int16_t from = s.flowCentiC.value_or(flow);
        const uint64_t n = ms / (10 * second);
        for (uint64_t k = 1; k <= n; ++k) {
            s.flowCentiC = int16_t(from + (flow - from) * int64_t(k) / int64_t(n));
            if (withReturn) s.returnCentiC = int16_t(*s.flowCentiC - 500);
            step();
        }
        s.burnerOn = false; s.modulationPct = 0;
    }
    // One held target: a burn to the request + 5 K, the stop, then the boiler's own rest.
    void hold(uint64_t restMs = 10 * minute, uint64_t burnMs = 3 * minute) {
        burn(burnMs, int16_t(s.requestC * 100 + 500));
        run(restMs);
    }
};

TEST(BoilerResponse, OutdoorBandsAreFiveKelvinFromMinusTen) {
    EXPECT_EQ(BoilerResponse::band(std::nullopt), 3u) << "unknown outdoor: 5..10";
    const std::pair<int16_t, size_t> cases[] = {{-2500, 0}, {-1001, 0}, {-501, 0}, {-500, 1}, {-1, 1}, {0, 2}, {499, 2}, {500, 3},
                                               {999, 3}, {1000, 4}, {1499, 4}, {1500, 5}, {3500, 5}};
    for (const auto& [outdoor, band] : cases) EXPECT_EQ(BoilerResponse::band(outdoor), band) << outdoor;
}

// A held target: the burner stops by itself with the water at the request (or at most 2 degC
// below it) while the E32 asks heat that a room wants. Two in one request: over-asked, and the
// ceiling for that outdoor band is the request - 2 degC. The rest until the burner fires again
// is the boiler's own; from three of them their median is reported.
TEST(BoilerResponse, TwoHeldTargetsInOneRequestGiveACeilingAndTheRestsTheirMedian) {
    Bench b;
    b.run(minute);
    EXPECT_STREQ(b.r.state(), "collecting");
    b.hold();                                       // within the first 10 min of the request: filling the circuit
    EXPECT_EQ(b.r.heldToday(), 0u);
    EXPECT_FALSE(b.r.ceilingC(700));
    b.hold(11 * minute);                            // held 1; its rest (11 min) ends with the next burn
    EXPECT_EQ(b.r.heldToday(), 1u);
    EXPECT_FALSE(b.r.ceilingC(700)) << "one held target is no verdict";
    b.hold(9 * minute);                             // held 2: over-asked
    EXPECT_EQ(b.r.heldToday(), 2u);
    EXPECT_EQ(b.r.overAsked(), 1u);
    ASSERT_TRUE(b.r.ceilingC(700));
    EXPECT_EQ(*b.r.ceilingC(700), 43) << "the request - 2 degC";
    EXPECT_EQ(b.r.ceilingC(800), b.r.ceilingC(700)) << "the same band";
    EXPECT_FALSE(b.r.ceilingC(1000)) << "another band";
    EXPECT_FALSE(b.r.ceilingC(std::nullopt)) << "unknown outdoor: not applied";
    EXPECT_STREQ(b.r.state(), "collecting") << "learned from one over-asked request, reported from two";
    EXPECT_FALSE(b.r.restS()) << "two rests so far";
    b.hold(10 * minute);                            // held 3 in the same request: one verdict per request
    EXPECT_EQ(b.r.overAsked(), 1u);
    b.burn(3 * minute, 5000);
    ASSERT_TRUE(b.r.restS());
    EXPECT_EQ(*b.r.restS(), 600u) << "11, 9 and 10 min: the median";
    // The request ends, and the next one is over-asked at 43: EMA 43 + 0.3 x (41 - 43) = 42.4.
    b.s.requestC = 0; b.run(5 * minute);
    b.s.requestC = 43; b.run(minute);
    b.hold(); b.hold(); b.hold();
    EXPECT_EQ(b.r.overAsked(), 2u);
    EXPECT_EQ(*b.r.ceilingC(700), 42);
    EXPECT_STREQ(b.r.state(), "learned");
}

TEST(BoilerResponse, WarmUpsHotWaterOtherControllersAndOwnStopsAreNoHeldTargets) {
    const auto held = [](auto change) {
        Bench b;
        b.run(11 * minute);                        // past the settle
        change(b);
        b.hold(); b.hold(); b.hold();
        return b.r.heldToday();
    };
    EXPECT_EQ(held([](Bench&) {}), 3u);
    EXPECT_EQ(held([](Bench& b) { b.s.shortfallCentiC = 100; }), 0u) << "a warm-up: 1 degC short";
    EXPECT_EQ(held([](Bench& b) { b.s.shortfallCentiC = 99; }), 3u);
    EXPECT_EQ(held([](Bench& b) { b.s.demand = false; }), 0u) << "no room asks heat: the E32's own stop";
    EXPECT_EQ(held([](Bench& b) { b.s.ownRequest = false; }), 0u) << "another controller drives the boiler";
    EXPECT_EQ(held([](Bench& b) { b.s.hotWater = true; }), 0u) << "hot water";
    EXPECT_EQ(held([](Bench& b) { b.s.hotWater.reset(); }), 0u) << "hot water unknown";
    // A burner that turns unknown before it reads off: no stop was seen.
    Bench unknown;
    unknown.run(11 * minute);
    unknown.burn(3 * minute, 5000);
    unknown.s.burnerOn.reset(); unknown.step();
    unknown.s.burnerOn = false; unknown.run(10 * minute);
    EXPECT_EQ(unknown.r.heldToday(), 0u);
    // A stop more than 2 degC below the request: the boiler stopped for its own reasons.
    Bench low;
    low.run(11 * minute);
    low.burn(3 * minute, 4250); low.run(10 * minute);
    EXPECT_EQ(low.r.heldToday(), 0u);
    low.burn(3 * minute, 4300); low.run(10 * minute);
    EXPECT_EQ(low.r.heldToday(), 1u) << "request - 2 degC counts";
}

// The owner's recording (30 Oct - 2 Nov 2026): a keep-warm round drops its hot-water bit one report
// before the burner stops, at 72..76 degC, while the boiler holding a request stopped 3..6 degC above
// it. That tail is no heating burn holding the E32's request: no hot water in the minute before the
// stop, a heating burn of at least 1 min, and the water at most 8 degC above the request.
TEST(BoilerResponse, TheTailOfAKeepWarmRoundIsNoHeldTarget) {
    Bench b;
    b.s.requestC = 31;
    b.run(11 * minute);
    const auto round = [&](uint64_t tailMs) {      // 3 min of hot water up to 75 degC, then the tail
        b.s.burnerOn = true; b.s.hotWater = true; b.s.modulationPct = 100;
        for (int k = 0; k < 18; ++k) { b.s.flowCentiC = int16_t(5000 + 140 * k); b.step(); }
        b.s.hotWater = false; b.s.modulationPct = 37;
        for (uint64_t t = 0; t < tailMs; t += 10 * second) b.step();
        b.s.burnerOn = false; b.s.modulationPct = 0; b.run(5 * minute);
    };
    round(10 * second);                             // the recording's tail: one report
    EXPECT_EQ(b.r.heldToday(), 0u);
    round(2 * minute);                              // two minutes on: no longer a tail, but 73 degC is no 31 degC request
    EXPECT_EQ(b.r.heldToday(), 0u);
    b.s.flowCentiC = 3000; b.run(minute);
    b.burn(50 * second, 3400);                      // a heating burn under a minute
    b.run(5 * minute);
    EXPECT_EQ(b.r.heldToday(), 0u);
    b.burn(2 * minute, 3900);                       // 8 degC above: still the boiler holding the request
    b.run(5 * minute);
    EXPECT_EQ(b.r.heldToday(), 1u);
    b.burn(2 * minute, 4000); b.run(5 * minute);
    EXPECT_EQ(b.r.heldToday(), 1u) << "9 degC above";
}

// Hot water, a silence over 60 s, the end of the request or another controller close an open
// rest without counting it; a rest outside 60..1800 s is no observation either.
TEST(BoilerResponse, AnInterruptedRestIsNoObservation) {
    const auto rests = [](auto during) {
        Bench b;
        b.run(11 * minute);
        for (int k = 0; k < 3; ++k) {
            b.burn(3 * minute, 5000);
            b.run(5 * minute); during(b); b.run(5 * minute);
        }
        b.burn(3 * minute, 5000);
        return b.r.restS();
    };
    EXPECT_EQ(rests([](Bench&) {}).value_or(0), 600u);
    EXPECT_FALSE(rests([](Bench& b) { b.s.hotWater = true; b.step(); b.s.hotWater = false; }));
    EXPECT_FALSE(rests([](Bench& b) { b.s.now += 61 * second; }));
    EXPECT_FALSE(rests([](Bench& b) { b.s.requestC = 0; b.step(); b.s.requestC = 45; }));
    EXPECT_FALSE(rests([](Bench& b) { b.s.ownRequest = false; b.step(); b.s.ownRequest = true; }));
    EXPECT_FALSE(rests([](Bench& b) { b.run(21 * minute); })) << "31 min: over 1800 s";
    Bench quick;
    quick.run(11 * minute);
    for (int k = 0; k < 4; ++k) { quick.burn(3 * minute, 5000); quick.run(50 * second); }
    EXPECT_FALSE(quick.r.restS()) << "under 60 s";
    EXPECT_EQ(quick.r.heldToday(), 4u);
}

// The burner at its least power for 3 min while the water rises 2 degC above the request is a
// held target too (once per burn; its stop afterwards starts the rest). The least power: 25 %,
// or the lowest heating power seen this boot when lower.
TEST(BoilerResponse, TheLeastPowerWithTheWaterStillRisingIsHeld) {
    Bench b;
    b.run(11 * minute);
    b.s.burnerOn = true; b.s.modulationPct = 25;
    for (int k = 0; k < 30; ++k) { b.s.flowCentiC = int16_t(4700 + 5 * k); b.step(); } // 47.0 .. 48.45
    EXPECT_EQ(b.r.heldToday(), 1u);
    for (int k = 0; k < 12; ++k) { b.s.flowCentiC = int16_t(4850 + 10 * k); b.step(); }
    b.s.burnerOn = false; b.s.modulationPct = 0; b.step();
    EXPECT_EQ(b.r.heldToday(), 1u) << "the stop of the same burn counts no second time";
    b.run(10 * minute);
    b.s.burnerOn = true; b.s.modulationPct = 30; b.step();
    // A boiler that went down to 12 %: 25 % is no longer its least power.
    Bench low;
    low.run(11 * minute);
    low.s.burnerOn = true; low.s.modulationPct = 12; low.step();
    low.s.modulationPct = 25;
    for (int k = 0; k < 30; ++k) { low.s.flowCentiC = int16_t(4700 + 5 * k); low.step(); }
    EXPECT_EQ(low.r.heldToday(), 0u);
    // Not rising: no held target.
    Bench flat;
    flat.run(11 * minute);
    flat.s.burnerOn = true; flat.s.modulationPct = 20; flat.s.flowCentiC = 4800;
    flat.run(5 * minute);
    EXPECT_EQ(flat.r.heldToday(), 0u);
}

// Within [the lowest flow the E32 asks, the plan's maximum]; raised 1 degC per 6 hours of heat
// asked at or above it without a held target (the season changed), reset by a held target.
TEST(BoilerResponse, TheCeilingStaysWithinItsBoundsAndIsFoundOutAgain) {
    Bench b;
    b.s.requestC = 33; b.s.minimumC = 32;
    b.run(11 * minute);
    b.burn(3 * minute, 3800); b.run(10 * minute);
    b.burn(3 * minute, 3800); b.step();            // held 2: over-asked (and 10 s of heat asked at the ceiling)
    b.s.requestC = 0; b.step();
    ASSERT_TRUE(b.r.ceilingC(700));
    EXPECT_EQ(*b.r.ceilingC(700), 32) << "33 - 2 = 31, under the lowest flow the E32 asks";
    b.s.minimumC = 36; b.step();
    EXPECT_EQ(*b.r.ceilingC(700), 36) << "the boiler's minimum was learned higher since";
    b.s.maximumC = 34; b.step();
    EXPECT_EQ(*b.r.ceilingC(700), 36) << "a minimum above the maximum wins (the guard's order)";
    b.s.minimumC = 30; b.s.maximumC = 60; b.step();
    // Asked at 32 (the ceiling) for 6 h with the burner steady, no held target: 33.
    b.s.requestC = 32; b.s.burnerOn = true; b.s.modulationPct = 40; b.s.flowCentiC = 3200;
    b.run(5 * hour + 50 * minute);
    EXPECT_EQ(*b.r.ceilingC(700), 32);
    b.run(10 * minute);
    EXPECT_EQ(*b.r.ceilingC(700), 33);
    // Below the ceiling: not found out (the curve asks less on its own).
    b.s.requestC = 31; b.run(7 * hour);
    EXPECT_EQ(*b.r.ceilingC(700), 33);
    // A held target resets the time: 5 h, a held target, 5 h: no raise.
    b.s.requestC = 33; b.run(5 * hour);
    b.burn(minute, 3800); b.run(10 * minute);
    b.s.burnerOn = true; b.s.modulationPct = 40; b.s.flowCentiC = 3300;
    b.run(5 * hour);
    EXPECT_EQ(*b.r.ceilingC(700), 33);
    // Never above the plan's maximum.
    b.s.maximumC = 33; b.run(7 * hour);
    EXPECT_EQ(*b.r.ceilingC(700), 33);
}

// The band is the request's mean outdoor; without an outdoor reading it learns into 5..10 degC
// but applies only with an outdoor known.
TEST(BoilerResponse, TheBandIsTheRequestsMeanOutdoor) {
    Bench b;
    b.s.outdoorCentiC = -300;
    b.run(11 * minute);
    b.hold();
    b.s.outdoorCentiC = 300; b.hold();             // the request's mean outdoor stays below 0
    ASSERT_TRUE(b.r.ceilingC(-100));
    EXPECT_FALSE(b.r.ceilingC(300));
    Bench none;
    none.s.outdoorCentiC.reset();
    none.run(11 * minute);
    none.hold(); none.hold();
    EXPECT_FALSE(none.r.ceilingC(std::nullopt));
    EXPECT_EQ(none.r.ceilingC(600).value_or(0), 43);
}

// With the return reported: a steady burn gives the pump's mass flow, from then on the heat the
// emitters take (also without the burner power), and per K of water above the rooms' mean.
TEST(BoilerResponse, AbsorbedHeatFromFlowMinusReturnAndThePumpFlow) {
    Bench b;
    b.s.requestC = 50; b.s.nominalKw = 24;
    b.run(11 * minute);
    // 50 % of 24 kW at a return of 45 degC (efficiency 93.2 %) with 5 K across: 0.5344 kg/s.
    b.s.burnerOn = true; b.s.modulationPct = 50; b.s.flowCentiC = 5000; b.s.returnCentiC = 4500; b.s.roomMeanCentiC = 2000;
    b.run(4 * minute);
    EXPECT_FALSE(b.r.pumpKgPerS()) << "not steady yet";
    EXPECT_FALSE(b.r.absorbedKw());
    b.run(12 * minute);                             // a 10 min window
    const double kw = 0.5 * 24 * FlowLearner::efficiency(45.0f), m = kw / (4.186 * 5);
    ASSERT_TRUE(b.r.pumpKgPerS());
    EXPECT_NEAR(*b.r.pumpKgPerS(), m, 1e-4);
    ASSERT_TRUE(b.r.absorbedKw());
    EXPECT_NEAR(*b.r.absorbedKw(), kw, 1e-3);
    // The burner stops: nothing absorbed from the burner now; the open windows are folded.
    b.s.burnerOn = false; b.step();
    EXPECT_FALSE(b.r.absorbedKw());
    // kW per K of water above the rooms' mean (30 K here), from the steady samples with the pump known.
    ASSERT_TRUE(b.r.kwPerFlowK());
    EXPECT_NEAR(*b.r.kwPerFlowK(), kw / 30, 2e-3);
    EXPECT_STREQ(b.r.state(), "collecting");
    // Without the burner power: still known from the pump flow (flow - return now 8 K).
    b.s.burnerOn = true; b.s.modulationPct.reset(); b.s.returnCentiC = 4200; b.step();
    EXPECT_NEAR(*b.r.absorbedKw(), m * 4.186 * 8, 1e-3);
    // Hot water through the same burn: no heat for the emitters.
    b.s.hotWater = true; b.s.returnCentiC = 4500; b.step();
    EXPECT_FALSE(b.r.absorbedKw());
    // Water that warms during the burn (the boiler's least power running up to its stop): the heat
    // goes into the water, not only through the pump; such a window is not counted.
    Bench rising;
    rising.s.requestC = 50; rising.s.nominalKw = 24;
    rising.run(11 * minute);
    rising.s.burnerOn = true; rising.s.modulationPct = 20;
    for (int k = 0; k < 120; ++k) { rising.s.flowCentiC = int16_t(4500 + 5 * k); rising.s.returnCentiC = int16_t(*rising.s.flowCentiC - 300); rising.step(); }
    rising.s.burnerOn = false; rising.step();
    EXPECT_FALSE(rising.r.pumpKgPerS()) << "0.3 degC a minute: not steady";
}

// Without the return temperature: "no_return", the absorption stays unknown, and the held targets,
// the rest and the ceiling are learned as before.
TEST(BoilerResponse, WithoutTheReturnOnlyTheAbsorptionIsUnknown) {
    Bench b;
    b.s.returnCentiC.reset();
    b.run(11 * minute);
    EXPECT_STREQ(b.r.state(), "no_return");
    for (int k = 0; k < 4; ++k) { b.burn(3 * minute, 5000, 20, false); b.run(10 * minute); }
    b.s.burnerOn = true; b.s.modulationPct = 50; b.s.returnCentiC.reset(); b.run(20 * minute);
    EXPECT_FALSE(b.r.absorbedKw());
    EXPECT_FALSE(b.r.kwPerFlowK());
    EXPECT_FALSE(b.r.pumpKgPerS());
    EXPECT_EQ(b.r.heldToday(), 4u);
    EXPECT_EQ(b.r.restS().value_or(0), 600u);
    EXPECT_EQ(b.r.ceilingC(700).value_or(0), 43);
    EXPECT_STREQ(b.r.state(), "no_return");
    // A second over-asked request: learned, with or without the return.
    b.s.burnerOn = false; b.s.requestC = 0; b.run(minute);
    b.s.requestC = 45; b.run(11 * minute);
    b.burn(3 * minute, 5000, 20, false); b.run(10 * minute); b.burn(3 * minute, 5000, 20, false); b.run(10 * minute);
    EXPECT_STREQ(b.r.state(), "learned");
    // Another controller drives the boiler: "not_driving" (what was learned stays).
    b.s.ownRequest = false; b.step();
    EXPECT_STREQ(b.r.state(), "not_driving");
    EXPECT_EQ(b.r.ceilingC(700).value_or(0), 43);
}

// Another boiler (EMS product id): nothing learned about the old one applies.
TEST(BoilerResponse, AnotherBoilerStartsOver) {
    Bench b;
    b.s.productId = 195;
    b.run(11 * minute);
    b.hold(); b.hold(); b.hold(); b.burn(3 * minute, 5000);
    ASSERT_TRUE(b.r.ceilingC(700)); ASSERT_TRUE(b.r.restS());
    b.s.productId.reset(); b.step();               // not read for a while: no change
    b.s.productId = 0; b.step();
    EXPECT_TRUE(b.r.ceilingC(700));
    b.s.productId = 208; b.step();
    EXPECT_FALSE(b.r.ceilingC(700));
    EXPECT_FALSE(b.r.restS());
    EXPECT_EQ(b.r.heldToday(), 0u);
    EXPECT_EQ(b.r.overAsked(), 0u);
}

TEST(BoilerResponse, HeldTodayFollowsTheLocalDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    Bench b;
    b.s.utc = wednesday23 - 600;                    // Wednesday 22:50 local
    b.run(11 * minute);
    const auto tick = [&](uint64_t ms) { for (uint64_t t = 0; t < ms; t += 10 * second) { *b.s.utc += 10; b.step(); } };
    b.burn(3 * minute, 5000); tick(10 * minute);
    EXPECT_EQ(b.r.heldToday(), 1u);
    b.s.utc = wednesday23 + 3600 + 60;               // Thursday 00:01 local
    b.step();
    EXPECT_EQ(b.r.heldToday(), 0u);
    b.burn(3 * minute, 5000); tick(minute);
    EXPECT_EQ(b.r.heldToday(), 1u);
    // Kept over a restart on the same day, not into the next one.
    BoilerResponse same, next;
    ASSERT_TRUE(same.restore(b.r.stored()));
    BoilerResponse::Sample s = b.s; s.now = 0;
    same.sample(s);
    EXPECT_EQ(same.heldToday(), 1u);
    ASSERT_TRUE(next.restore(b.r.stored()));
    s.utc = *s.utc + 86400; next.sample(s);
    EXPECT_EQ(next.heldToday(), 0u);
}

// What was learned is one LearnedState frame: kind 'B', version 1, at most 48 B, applied whole.
TEST(BoilerResponse, TheFrameKeepsWhatWasLearnedAndADamagedOneIsIgnoredWhole) {
    Bench b;
    EXPECT_EQ(b.r.stored(), "") << "nothing learned: no frame";
    b.s.productId = 195; b.s.nominalKw = 24;
    b.run(11 * minute);
    b.hold(); b.hold(); b.hold(); b.burn(3 * minute, 5000);
    b.s.burnerOn = true; b.s.modulationPct = 50; b.s.flowCentiC = 5000; b.s.returnCentiC = 4500; b.s.roomMeanCentiC = 2000;
    b.run(20 * minute);
    b.s.outdoorCentiC = -800; b.s.requestC = 0; b.run(minute);
    b.s.requestC = 52; b.s.burnerOn = false; b.run(11 * minute);
    b.burn(3 * minute, 5700); b.run(12 * minute); b.burn(3 * minute, 5700); b.run(14 * minute);
    b.s.burnerOn = true; b.s.modulationPct = 40; b.s.flowCentiC = 5200; b.run(hour); // raise time in band 0
    const auto f = b.r.stored();
    ASSERT_EQ(f.size(), BoilerResponse::frameBytes);
    EXPECT_LE(f.size(), BoilerResponse::storedMaxBytes);
    EXPECT_EQ(uint8_t(f[0]), 1); EXPECT_EQ(f[1], 'B');
    BoilerResponse back;
    ASSERT_TRUE(back.restore(f));
    EXPECT_EQ(back.stored(), f) << "a lossless round trip of what the frame holds";
    for (const int16_t o : {-800, 700}) EXPECT_EQ(back.ceilingC(o), b.r.ceilingC(o)) << o;
    EXPECT_EQ(back.restS(), b.r.restS());
    EXPECT_EQ(back.overAsked(), 2u);
    EXPECT_STREQ(back.state(), "learned");
    EXPECT_NEAR(*back.pumpKgPerS(), *b.r.pumpKgPerS(), 0.001);
    EXPECT_NEAR(*back.kwPerFlowK(), *b.r.kwPerFlowK(), 0.001);
    EXPECT_FALSE(back.absorbedKw()) << "now: from the next sample";
    // The same boiler keeps it; another starts over.
    BoilerResponse::Sample s = b.s; s.now = 1;
    back.sample(s);
    EXPECT_TRUE(back.ceilingC(700));
    s.productId = 99; s.now += 10 * second; back.sample(s);
    EXPECT_FALSE(back.ceilingC(700));
    // Damaged, another version, kind or length, implausible values: nothing applied.
    const auto refused = [&](std::string g, const char* why) {
        BoilerResponse r;
        ASSERT_TRUE(r.restore(f));
        EXPECT_FALSE(r.restore(g)) << why;
        EXPECT_EQ(r.stored(), f) << why << ": untouched";
    };
    const auto fix = [](std::string g) { // a valid CRC over a changed payload
        const uint32_t c = LearnedState::crc(g.data(), g.size() - 4);
        for (int i = 0; i < 4; ++i) g[g.size() - 4 + i] = char(c >> (8 * i));
        return g;
    };
    for (size_t i = 0; i < f.size(); ++i) { auto g = f; g[i] = char(g[i] ^ 0x41); refused(g, "a flipped byte"); }
    { auto g = f; g[0] = 2; refused(fix(g), "version 2"); }
    { auto g = f; g[1] = 'R'; refused(fix(g), "another kind"); }
    refused(f.substr(0, f.size() - 1), "short");
    refused(f + '\0', "long");
    { auto g = f; g[4 + 2] = char(242); refused(fix(g), "a ceiling above 80 degC"); }
    { auto g = f; g[4 + 8] = char(181); refused(fix(g), "over 6 h of raise time"); }
    { auto g = f; g[4 + 14] = char(9); refused(fix(g), "nine rests"); }
    { auto g = f; g[4 + 15] = char(5); refused(fix(g), "a rest of 50 s"); }
    { auto g = f; g[4 + 23] = char(0xFF); g[4 + 24] = char(0xFF); refused(fix(g), "a pump of 65 kg/s"); }
    { auto g = f; g[4 + 25] = char(0xFF); g[4 + 26] = char(0xFF); refused(fix(g), "65 kW per K"); }
    EXPECT_FALSE(BoilerResponse().restore(""));
}

// LearnedStore keeps the frame in the global record (after the globals, before the rooms) and
// hands it back at boot. Firmware before rc.5 skips it: it is no room frame.
TEST(BoilerResponse, TheFrameTravelsInTheGlobalRecordAndOlderFirmwareSkipsIt) {
    struct Nvs final : LearnedStore::Backend {
        std::map<size_t, std::string> parts;
        bool read(size_t part, std::string& out) override { const auto i = parts.find(part); if (i == parts.end()) return false; out = i->second; return true; }
        bool write(size_t part, std::string_view bytes) override { parts[part] = std::string(bytes); return true; }
        bool erase(size_t part) override { parts.erase(part); return true; }
    };
    Bench b;
    b.run(11 * minute);
    b.hold(); b.hold(); b.hold(); b.burn(3 * minute, 5000);
    RoomPlan plan; plan.rooms.resize(1); plan.rooms[0].id = "woonkamer"; plan.rooms[0].state = RoomDemand::State::active;
    FlowLearner l; l.setPlan(plan);
    FlowPolicy p; p.setPlan(plan);
    Nvs nvs;
    LearnedStore store;
    ASSERT_TRUE(store.save(nvs, l, p, 0, {b.r.stored()}));
    const auto g = LearnedState::globalFrame(l, p);
    ASSERT_EQ(nvs.parts[0], g + b.r.stored());
    EXPECT_EQ(store.rooms(), 0u) << "the boiler's frame is no room";
    EXPECT_EQ(store.storedRooms(), 0u);
    BoilerResponse back;
    LearnedStore boot;
    EXPECT_EQ(boot.restore(nvs, l, p, 0, [&](std::string_view f) { if (f[1] == BoilerResponse::frameKind) back.restore(f); }), 0u);
    EXPECT_EQ(back.stored(), b.r.stored());
    // Before rc.5 (no `other`): every other frame as before, the boiler's skipped.
    FlowLearner older; older.setPlan(plan);
    FlowPolicy olderPolicy; olderPolicy.setPlan(plan);
    uint32_t done = 0; bool global = false;
    EXPECT_EQ(LearnedState::restoreFrames(nvs.parts[0], older, olderPolicy, done, global), 0u);
    EXPECT_TRUE(global);
    // Nothing learned: no frame, the record as before rc.5.
    LearnedStore none;
    Nvs empty;
    ASSERT_TRUE(none.save(empty, l, p, 0, {BoilerResponse().stored()}));
    EXPECT_EQ(empty.parts[0], g);
}

// "boiler":{"held","rest_s","ceiling_c","absorbed_kw","kw_per_k","state"}, at most 140 B printed.
TEST(BoilerResponse, TheBoilerObjectKeepsItsShapeAndSize) {
    Json fresh(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(BoilerResponse().addJson(fresh.get()));
    EXPECT_EQ(print(fresh.get()), R"({"boiler":{"held":0,"rest_s":null,"ceiling_c":null,"absorbed_kw":null,"kw_per_k":null,"state":"collecting"}})");
    // The widest (BoilerResponseWidest.h): 65535 held targets, a rest of 1800 s, no ceiling for the
    // outdoor now (null is wider), 999.9 kW, 19.999 kW per K and "not_driving".
    ASSERT_TRUE(BoilerResponse().restore(widestBoilerFrame()));
    const BoilerResponse r = widestBoilerResponse();
    Json worst(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(r.addJson(worst.get()));
    const auto text = print(worst.get());
    const std::string part = text.substr(1, text.size() - 2); // "boiler":{..}
    std::printf("[ boiler response ] widest %zu B: %s\n", part.size(), part.c_str());
    EXPECT_LE(part.size(), BoilerResponse::jsonMaxBytes);
    const cJSON* o = at(worst.get(), "boiler");
    EXPECT_EQ(at(o, "held")->valuedouble, 65535);
    EXPECT_EQ(at(o, "rest_s")->valuedouble, 1800);
    EXPECT_EQ(at(o, "absorbed_kw")->valuedouble, 999.9);
    EXPECT_EQ(at(o, "kw_per_k")->valuedouble, 19.999);
    EXPECT_STREQ(at(o, "state")->valuestring, "not_driving");
}

TEST(RestFloor, TheBurnerRestIsAtLeastTheBoilersOwnUnlessARoomIsCold) {
    ControlTuning t;
    EXPECT_FALSE(RestFloor::apply(t, std::nullopt, false));
    EXPECT_EQ(t.minOffS, 300);
    EXPECT_TRUE(RestFloor::apply(t, 600, false));
    EXPECT_EQ(t.minOffS, 600);
    t.minOffS = 300;
    EXPECT_TRUE(RestFloor::apply(t, 1800, false));
    EXPECT_EQ(t.minOffS, 900) << "at most 15 min";
    t.minOffS = 300;
    EXPECT_FALSE(RestFloor::apply(t, 600, true)) << "comfort first";
    EXPECT_EQ(t.minOffS, 300);
    t.minOffS = 1200;
    EXPECT_FALSE(RestFloor::apply(t, 600, false)) << "a longer knob stays";
    EXPECT_EQ(t.minOffS, 1200);
    std::array<RoomDemand::Result, 3> rooms{};
    for (auto& r : rooms) { r.status = RoomDemand::Status::ok; r.usable = true; r.errorCentiC = 30; }
    EXPECT_FALSE(RestFloor::cold(rooms.data(), rooms.size())) << "0.3 degC short is not cold";
    rooms[1].errorCentiC = 31;
    EXPECT_TRUE(RestFloor::cold(rooms.data(), rooms.size()));
    rooms[1].usable = false;
    EXPECT_FALSE(RestFloor::cold(rooms.data(), rooms.size())) << "only usable rooms";
    rooms[2].errorCentiC = 200; rooms[2].status = RoomDemand::Status::inactive;
    EXPECT_FALSE(RestFloor::cold(rooms.data(), rooms.size()));
}

// The plan's generator (2.4): a boiler that holds its target up to +5 K, burner off, its own
// anti-cycle 10 min (the "0Y" boiler). Its least power (5 kW) is more than the circuit takes
// (0.1 kW per K of water above the room), so whatever the E32 asks, the water runs up to the
// request + 5 K and the burner waits. The E32 asks 45 degC (the rule) for 2 h, then rests 30 min.
struct HoldingBoiler {
    double water = 30, room = 20.8, leastKw = 5, nominalKw = 24, kwPerK = 0.1, waterKwhPerK = 0.06, pump = 0.2;
    bool on = false, stopped = false;
    uint64_t offAt = 0;
    double burnKw = 0, absorbedKw = 0;
    void step(uint64_t now, uint8_t requestC) {
        absorbedKw = std::max(0.0, kwPerK * (water - room));
        if (!requestC) on = false;
        else if (on && water >= requestC + 5) { on = false; stopped = true; offAt = now; }
        else if (!on && water < requestC && (!stopped || now - offAt >= 10 * minute)) on = true;
        // On: as much as holds the water at the request, at least its least power.
        burnKw = on ? std::clamp(absorbedKw + (requestC - water) * waterKwhPerK * 60, leastKw, nominalKw) : 0;
        water += (burnKw - absorbedKw) * (10.0 / 3600) / waterKwhPerK;
    }
    int16_t flow() const { return int16_t(std::lround(water * 100)); }
    int16_t ret() const { return int16_t(std::lround((water - absorbedKw / (pump * 4.186)) * 100)); }
    uint8_t pct() const { return uint8_t(std::lround(burnKw / (nominalKw * FlowLearner::efficiency(float(water - 5))) * 100)); }
};

// The ceiling learned from the boiler's own answer and applied by FlowPolicy (Smart warm-up on,
// the E32 driving): the request goes down to it and stays there; the boiler's rest (its 10 min
// anti-cycle) becomes the E32's burner rest; another controller or the option off: no cap.
TEST(BoilerResponse, AHoldingBoilerTeachesItsCeilingAndFlowPolicyAsksNoMore) {
    RoomPlan plan; plan.rooms.resize(1);
    plan.rooms[0].id = "woonkamer"; plan.rooms[0].emitter = RoomPlan::Emitter::radiator; plan.rooms[0].state = RoomDemand::State::active;
    FlowLearner learner; learner.setPlan(plan);
    FlowPolicy policy; policy.setPlan(plan);
    FlowSettings smart; smart.weatherCurve = false; smart.applyLearned = true;
    policy.setSettings(smart);
    std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
    rooms[0].status = RoomDemand::Status::ok; rooms[0].usable = true; rooms[0].temperature = 2080; rooms[0].setpoint = 2100; rooms[0].errorCentiC = 20;
    HoldingBoiler boiler;
    BoilerResponse response;
    uint64_t now = 0;
    uint8_t requestC = 0, highest = 0;
    std::vector<uint8_t> perRun;
    int stops = 0;
    bool wasOn = false;
    for (int run = 0; run < 8; ++run) {
        uint8_t runHighest = 0;
        for (uint64_t t = 0; t < 150 * minute; t += 10 * second) {
            now += 10 * second;
            const bool heat = t < 120 * minute;
            FlowPolicy::Inputs in;
            in.now = now; in.plan = &plan; in.rooms = rooms.data(); in.outdoorCentiC = 700;
            in.rule = heat ? FlowDemand::Request{true, 45, FlowDemand::Reason::heating} : FlowDemand::Request{false, 0, FlowDemand::Reason::satisfied};
            in.ownRequest = true; in.ceilingC = response.ceilingC(700);
            const auto out = policy.apply(in, learner);
            if (in.ceilingC && out.heat) EXPECT_LE(out.flowC, *in.ceilingC) << "never above the learned ceiling";
            // The guard sends it; the boiler answers at its next poll (the next step).
            boiler.step(now, requestC);
            BoilerResponse::Sample s;
            s.now = now; s.requestC = requestC; s.ownRequest = true; s.demand = heat; s.shortfallCentiC = 20;
            s.flowCentiC = boiler.flow(); s.returnCentiC = boiler.ret(); s.outdoorCentiC = 700; s.roomMeanCentiC = 2080;
            s.burnerOn = boiler.on; s.hotWater = false; s.modulationPct = boiler.pct(); s.nominalKw = 24; s.minimumC = 30; s.maximumC = 60;
            response.sample(s);
            stops += wasOn && !boiler.on && requestC; wasOn = boiler.on;
            requestC = out.heat ? out.flowC : 0;
            runHighest = std::max(runHighest, requestC);
        }
        perRun.push_back(runHighest);
        highest = std::max(highest, runHighest);
    }
    std::printf("[ boiler response ] holding boiler, 8 requests of 2 h at 45 degC: highest request per request");
    for (const auto r : perRun) std::printf(" %u", unsigned(r));
    std::printf("; ceiling %u degC, %u over-asked, rest %u s, %d stops, held today %u\n", unsigned(response.ceilingC(700).value_or(0)),
                unsigned(response.overAsked()), unsigned(response.restS().value_or(0)), stops, unsigned(response.heldToday()));
    EXPECT_EQ(perRun[0], 45) << "the first request still asks the rule's 45";
    EXPECT_STREQ(response.state(), "learned");
    ASSERT_TRUE(response.ceilingC(700));
    EXPECT_LE(*response.ceilingC(700), 43);
    EXPECT_GE(*response.ceilingC(700), 30) << "never below the lowest flow the E32 asks";
    for (size_t k = 1; k < perRun.size(); ++k) EXPECT_LT(perRun[k], 45) << "capped from the second request on: " << k;
    // The page and the flow topic: the cap in effect and "held".
    Json status(cJSON_CreateObject(), cJSON_Delete);
    {
        FlowPolicy::Inputs in;
        in.now = now + 10 * second; in.plan = &plan; in.rooms = rooms.data(); in.outdoorCentiC = 700;
        in.rule = {true, 45, FlowDemand::Reason::heating}; in.ownRequest = true; in.ceilingC = response.ceilingC(700);
        EXPECT_EQ(policy.apply(in, learner).flowC, *response.ceilingC(700));
        ASSERT_TRUE(policy.addSummary(status.get()));
        EXPECT_EQ(at(at(status.get(), "flow"), "ceiling_c")->valuedouble, *response.ceilingC(700));
        EXPECT_STREQ(at(at(at(status.get(), "flow"), "learned"), "state")->valuestring, "held");
        // Another controller drives the boiler, or Smart warm-up is off: the rule's 45 again.
        in.ownRequest = false; in.now += 10 * second;
        EXPECT_EQ(policy.apply(in, learner).flowC, 45);
        in.ownRequest = true; smart.applyLearned = false; policy.setSettings(smart); in.now += 10 * second;
        EXPECT_EQ(policy.apply(in, learner).flowC, 45);
    }
    // Its own rest, its 10 min anti-cycle, is the E32's burner rest from now on.
    ASSERT_TRUE(response.restS());
    EXPECT_GE(*response.restS(), 600u); EXPECT_LE(*response.restS(), 660u);
    ControlTuning t;
    EXPECT_TRUE(RestFloor::apply(t, response.restS(), false));
    EXPECT_EQ(t.minOffS, *response.restS());
    // Its burns at the least power warm the water all the way to the stop: never steady, so the
    // absorption is not learned from this boiler (rather nothing than a figure that is wrong).
    EXPECT_FALSE(response.pumpKgPerS());
}

// The same circuit later in the season (colder, the valves open: it takes 0.4 kW per K): the
// boiler modulates at the ceiling without holding, so the ceiling rises 1 degC per 6 hours of heat
// asked at it, back towards what the rule asks.
TEST(BoilerResponse, WhenTheBoilerNoLongerHoldsTheCeilingRisesAgain) {
    Bench b;
    b.run(11 * minute);
    b.hold(); b.hold();
    ASSERT_EQ(b.r.ceilingC(700).value_or(0), 43);
    HoldingBoiler boiler; boiler.kwPerK = 0.4; boiler.water = 43;
    uint64_t now = b.s.now;
    uint8_t ceiling = 43;
    for (int h = 0; h < 25; ++h)
        for (int k = 0; k < 360; ++k) {
            now += 10 * second;
            const uint8_t request = std::min<uint8_t>(45, *b.r.ceilingC(700));
            boiler.step(now, request);
            b.s.now = now; b.s.requestC = request; b.s.burnerOn = boiler.on; b.s.modulationPct = boiler.pct();
            b.s.flowCentiC = boiler.flow(); b.s.returnCentiC = boiler.ret();
            b.r.sample(b.s);
            ceiling = *b.r.ceilingC(700);
        }
    EXPECT_EQ(ceiling, 46) << "43 + 1 per 6 h of steady heat asked at the ceiling, until it no longer caps the request (45)";
    EXPECT_EQ(b.r.heldToday(), 2u) << "no new held target";
}
}
