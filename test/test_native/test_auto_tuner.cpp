#include "control/AutoTuner.h"
#include "control/FlowPolicy.h"
#include "control/RoomEngine.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <memory>
#include <string>
#include <vector>

// The rc.2 self-tuning (control/AutoTuner.h): every rule at its edges, the
// conservatism (evidence, one step a day, bounds, shadow = no change, the
// grace after a boot or a change, reset), the stored record and the flow
// record's manual knobs, and two 14-day closed loops: a short-cycling room
// and an overshooting floor.
namespace {
using heating::control::AutoTuner;
using heating::control::ControlTuning;
using heating::control::FlowDemand;
using heating::control::FlowSettings;
using heating::control::RoomDemand;
using heating::control::RoomEngine;
using heating::control::RoomPlan;
using heating::control::ShadowComparison;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
using Reason = FlowDemand::Reason;
Json parse(const char* text) { return Json(cJSON_Parse(text), cJSON_Delete); }
// Monday 2 Nov 2026, local midnight (CET).
const uint32_t monday = uint32_t(ShadowComparison::daysFromCivil(2026, 11, 2)) * 86400 - 3600;

RoomPlan plan(std::initializer_list<RoomPlan::Emitter> emitters = {RoomPlan::Emitter::radiator}) {
    RoomPlan p;
    const char* ids[] = {"woonkamer", "keuken", "slaapkamer"};
    for (const auto e : emitters) {
        RoomPlan::Room r;
        r.id = r.name = ids[p.rooms.size()]; r.state = RoomDemand::State::active; r.emitter = e;
        r.sources = {{RoomPlan::SourceType::ha, "climate." + r.id}}; r.fallbackCentiC = 2000;
        p.rooms.push_back(r);
    }
    return p;
}

// What one 10 s step shows the tuner: the request, the burner and one room.
struct S {
    bool heat = false;
    Reason reason = Reason::idle;
    bool burner = false, hotWater = false, shortCycling = false;
    int16_t temp = 2000, sp = 2000;
    bool demand = false;
};
// Feeds whole local days; the step at the next midnight closes the day and evaluates it.
struct Driver {
    ScopedTz tz{ScopedTz::amsterdam};
    AutoTuner tuner;
    RoomPlan rooms = plan();
    ControlTuning owner;
    uint16_t manual = 0;
    uint64_t now = 0;
    uint32_t utc = monday;
    bool active = true;
    std::vector<AutoTuner::Learned> learned = std::vector<AutoTuner::Learned>(1);
    ControlTuning tuning() const { return tuner.effective(owner, manual); }
    void step(const S& x) {
        now += 10000; utc += 10;
        const auto t = tuning();
        AutoTuner::Room r{x.temp, x.sp, x.demand};
        AutoTuner::Step s;
        s.now = now; s.utc = utc; s.request = {x.heat, uint8_t(x.heat ? 40 : 0), x.reason};
        s.burnerOn = x.burner; s.hotWater = x.hotWater; s.shortCycling = x.shortCycling; s.active = active;
        s.tuning = &t; s.rooms = &r; s.count = 1;
        if (tuner.sample(s)) tuner.evaluate(now, utc, manual, rooms, learned.data(), learned.size());
    }
    void day(const std::function<S(uint32_t)>& f) { for (uint32_t t = 10; t <= 86400; t += 10) step(f(t % 86400)); }
    std::string key(size_t i) const { size_t n; return ControlTuning::knobs(n)[tuner.change(i).knob].key; }
};
// Heating all day in cycles: `on` minutes heat (burner on, the room asks), then `off` minutes rest.
std::function<S(uint32_t)> cycles(int on, int off, int16_t low = 1985, int16_t high = 2010) {
    return [=](uint32_t t) {
        const uint32_t phase = t % uint32_t((on + off) * 60);
        S x; x.heat = x.burner = x.demand = phase < uint32_t(on * 60);
        x.reason = x.heat ? Reason::heating : Reason::satisfied;
        x.temp = x.heat ? int16_t(low + (high - low) * int(phase) / (on * 60)) : high;
        return x;
    };
}

constexpr uint16_t e_start = 1u << 2; // the start margin as the owner's: out of a test of other knobs

TEST(AutoTuner, ManyStartsLengthenTheBurnerRestOneStepADay) {
    Driver d;
    d.day(cycles(5, 5)); // 144 starts in 24 heating hours: 6 per hour
    EXPECT_STREQ(d.tuner.state(d.now), "active");
    ASSERT_EQ(d.tuner.logCount(), 2u); // the newest first
    EXPECT_EQ(d.key(1), "min_off_s"); EXPECT_EQ(d.key(0), "heat_start_c");
    EXPECT_EQ(d.tuner.change(1).from, 300); EXPECT_EQ(d.tuner.change(1).to, 450);
    EXPECT_EQ(d.tuner.change(1).reason, AutoTuner::Reason::manyStarts);
    EXPECT_EQ(d.tuner.change(1).figure, 143); // the first burn of the boot is no measured start
    EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::hovering);
    EXPECT_EQ(d.tuning().minOffS, 450);
    EXPECT_EQ(d.tuning().startCentiC, 25) << "the rooms hover within 0.15 degC: the start margin widens too";
    // One step a day, up to 1200 s; the start margin up to 0.50.
    for (int i = 0; i < 12; ++i) d.day(cycles(5, 5));
    EXPECT_EQ(d.tuning().minOffS, 1200);
    EXPECT_EQ(d.tuning().startCentiC, 50);
    EXPECT_EQ(d.tuner.logCount(), AutoTuner::logSize) << "the newest ten";
    // At most 3 starts per heating hour: nothing more.
    const auto before = d.tuning();
    d.day(cycles(10, 10)); // exactly 3 per hour (72 in 24 h, one unmeasured)
    EXPECT_EQ(d.tuning().minOffS, before.minOffS);
}

TEST(AutoTuner, ShortCyclingCountsWithTwoStartsAnHour) {
    Driver d;
    d.manual = e_start;
    auto f = cycles(15, 12, 1990, 2005); // 53 starts in 24 h: 2.2 per hour
    d.day([&](uint32_t t) { auto x = f(t); x.shortCycling = true; return x; });
    ASSERT_EQ(d.tuner.logCount(), 1u);
    EXPECT_EQ(d.key(0), "min_off_s"); EXPECT_EQ(d.tuning().minOffS, 450);
    Driver e; // the same without the boiler's short-cycling flag
    e.manual = e_start;
    e.day(f);
    EXPECT_EQ(e.tuning().minOffS, 300);
}

TEST(AutoTuner, AColdRestShortensTheRestComfortFirst) {
    Driver d;
    d.manual = e_start;
    ASSERT_TRUE(d.tuner.restore(R"({"values":{"min_off_s":900},"log":[]})"));
    EXPECT_EQ(d.tuning().minOffS, 900);
    // 5 min heat, 5 min off, 5 min held back while the room asks and falls to 0.40 below.
    const auto rests = [](int16_t deepest) {
        return [=](uint32_t t) {
            const uint32_t phase = t % 900;
            S x; x.heat = x.burner = phase < 300; x.demand = x.heat || phase >= 600;
            x.reason = x.heat ? Reason::heating : phase >= 600 ? Reason::holdOff : Reason::satisfied;
            x.temp = phase >= 600 ? int16_t(2000 - 20 - (deepest - 20) * int(phase - 600) / 290) : 2010;
            return x;
        };
    };
    d.day(rests(40));
    ASSERT_EQ(d.tuner.logCount(), 1u);
    EXPECT_EQ(d.key(0), "min_off_s"); EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::coldDuringRest);
    EXPECT_EQ(d.tuner.change(0).figure, 40);
    EXPECT_EQ(d.tuning().minOffS, 750) << "comfort beats the 96 starts";
    // 0.30 below is the edge (start 0.20 + 0.10): no shortening; the starts would lengthen it,
    // but not back to the rest that proved too cold (this boot).
    d.day(rests(30));
    EXPECT_EQ(d.tuning().minOffS, 750);
    d.tuner.reset(d.now); ASSERT_TRUE(d.tuner.restore(R"({"values":{"min_off_s":750},"log":[]})"));
    d.day(rests(30)); // a reset forgets it
    EXPECT_EQ(d.tuning().minOffS, 900);
    // Not below 300.
    for (int i = 0; i < 6; ++i) d.day(rests(45));
    EXPECT_EQ(d.tuning().minOffS, 300);
    // A rest that began far below the target (a program step, a window) is no evidence.
    Driver e;
    ASSERT_TRUE(e.tuner.restore(R"({"values":{"min_off_s":900},"log":[]})"));
    e.manual = e_start;
    e.day([&](uint32_t t) { auto x = rests(80)(t); if (x.reason == Reason::holdOff) x.temp = 1920; return x; });
    EXPECT_EQ(e.tuning().minOffS, 1050);
}

// Review of rc.2 (finding 1): a cold rest at the automatic floor (300 s) set the
// ceiling to 300; "many starts" then proposed with the upper bound 150 below the
// lower bound 300 (std::clamp UB; 150 on the E32). Also reached when the cold
// day was a shadow day or the rest the owner's.
TEST(AutoTuner, ManyStartsNeverShortenTheRestBelowItsFloor) {
    const auto rests = [](int16_t deepest) {
        return [=](uint32_t t) {
            const uint32_t phase = t % 900;
            S x; x.heat = x.burner = phase < 300; x.demand = x.heat || phase >= 600;
            x.reason = x.heat ? Reason::heating : phase >= 600 ? Reason::holdOff : Reason::satisfied;
            x.temp = phase >= 600 ? int16_t(2000 - 20 - (deepest - 20) * int(phase - 600) / 290) : 2010;
            return x;
        };
    };
    Driver d;
    d.manual = e_start;
    d.day(rests(45)); // too cold, already at 300: nothing to shorten
    EXPECT_EQ(d.tuning().minOffS, 300);
    for (int i = 0; i < 3; ++i) {
        d.day(cycles(5, 5)); // many starts: the ceiling (300) leaves no room to lengthen
        EXPECT_EQ(d.tuning().minOffS, 300) << "day " << i;
    }
    for (size_t i = 0; i < d.tuner.logCount(); ++i) EXPECT_GE(d.tuner.change(i).to, 300);
    // A ceiling below the value in effect: many starts must not shorten it.
    Driver c;
    c.manual = e_start;
    ASSERT_TRUE(c.tuner.restore(R"({"values":{"min_off_s":600},"log":[]})"));
    c.day(rests(45)); // 600 too cold: 450, ceiling 600
    EXPECT_EQ(c.tuning().minOffS, 450);
    c.day(rests(45)); // 450 too cold: 300, ceiling 450
    EXPECT_EQ(c.tuning().minOffS, 300);
    ASSERT_TRUE(c.tuner.restore(R"({"values":{"min_off_s":750},"log":[]})")); // e.g. a backup restored
    c.day(cycles(5, 5));
    EXPECT_EQ(c.tuning().minOffS, 750) << "many starts lengthen or leave it, never shorten";
    // The cold rest was the owner's (manual); back to automatic, many starts lengthen as usual.
    Driver m;
    m.manual = e_start | 2; m.owner.minOffS = 300;
    m.day(rests(45));
    m.manual = e_start;
    m.day(cycles(5, 5));
    EXPECT_EQ(m.tuning().minOffS, 450) << "an owner's rest is no automatic ceiling";
    // The cold rest was only shown (shadow): no ceiling either.
    Driver s;
    s.manual = e_start; s.active = false;
    s.day(rests(45));
    s.active = true;
    s.day(cycles(5, 5));
    EXPECT_EQ(s.tuning().minOffS, 450) << "a shadow day sets no ceiling";
}

TEST(AutoTuner, ShortBurnsLengthenTheBurnerRun) {
    Driver d;
    d.manual = 0b110; // rest and start margin stay: only the run time here
    // The request holds 5 min, the burner stops itself after 2 min with the room satisfied.
    d.day([](uint32_t t) {
        const uint32_t phase = t % 1500;
        S x; x.heat = phase < 300; x.reason = x.heat ? Reason::heating : Reason::satisfied;
        x.burner = phase < 120; x.demand = phase < 60; x.temp = 2005;
        return x;
    });
    ASSERT_EQ(d.tuner.logCount(), 1u);
    EXPECT_EQ(d.key(0), "min_on_s"); EXPECT_EQ(d.tuning().minOnS, 360);
    EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::shortBurns);
    for (int i = 0; i < 8; ++i) d.day([](uint32_t t) {
        const uint32_t phase = t % 1500;
        S x; x.heat = phase < 300; x.burner = phase < 120; x.temp = 2005; x.reason = x.heat ? Reason::heating : Reason::satisfied;
        return x;
    });
    EXPECT_EQ(d.tuning().minOnS, 600) << "the automatic upper bound";
}

TEST(AutoTuner, OvershootLowersTheStopMarginThenTheGain) {
    Driver d;
    // 40 min heat up to 0.50 above, 80 min off: 12 starts in 24 h, 0.5 per hour.
    const auto overshoot = [](int16_t peak) {
        return [=](uint32_t t) {
            const uint32_t phase = t % 7200;
            S x; x.heat = x.burner = x.demand = phase < 2400; x.reason = x.heat ? Reason::heating : Reason::satisfied;
            x.temp = int16_t(phase < 2400 ? 1980 + (peak + 20) * int(phase) / 2400 : 2000 + peak - (peak + 20) * int(phase - 2400) / 4800);
            return x;
        };
    };
    d.day(overshoot(50));
    ASSERT_EQ(d.tuner.logCount(), 1u);
    EXPECT_EQ(d.key(0), "heat_stop_c"); EXPECT_EQ(d.tuner.change(0).figure, 50);
    EXPECT_EQ(d.tuning().stopCentiC, 15);
    d.day(overshoot(50)); EXPECT_EQ(d.tuning().stopCentiC, 10);
    d.day(overshoot(50)); EXPECT_EQ(d.tuning().stopCentiC, 10);
    EXPECT_EQ(d.tuning().flowPerDegreeC, 9); EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::overshootGain);
    for (int i = 0; i < 6; ++i) d.day(overshoot(50));
    EXPECT_EQ(d.tuning().flowPerDegreeC, 5) << "the automatic lower bound";
    // 0.30 is the edge: nothing; a small overshoot brings the margin back up, to 0.20 at most.
    d.day(overshoot(30)); EXPECT_EQ(d.tuning().stopCentiC, 10);
    d.day(overshoot(13)); EXPECT_EQ(d.tuning().stopCentiC, 10) << "the median of the last 24 cycles: half still 0.30";
    d.day(overshoot(13)); EXPECT_EQ(d.tuning().stopCentiC, 15); EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::settled);
    d.day(overshoot(18)); EXPECT_EQ(d.tuning().stopCentiC, 20);
    d.day(overshoot(10)); EXPECT_EQ(d.tuning().stopCentiC, 20);
    // A lowered target (the evening program) is no overshoot: 2 h before the room counts again.
    Driver e;
    e.day([&](uint32_t t) { auto x = overshoot(10)(t); x.sp = t < 12 * 3600 ? 2000 : 1850; if (t >= 12 * 3600) x.temp -= 150; if (t >= 12 * 3600 && t < 14 * 3600) x.temp = 2000; return x; });
    EXPECT_EQ(e.tuning().stopCentiC, 20);
}

// Review of rc.2 (finding 2): a slow floor that overshoots 0.5 degC every cycle
// but closes only 3 cycles a day never had 5 cycles of evidence, because every
// gain raise wiped it; so the gain rose daily (11..15) with the stop margin unchanged.
TEST(AutoTuner, NoGainRaiseWhileTheRoomOvershoots) {
    Driver d;
    d.rooms = plan({RoomPlan::Emitter::floor});
    d.learned[0] = {RoomPlan::Emitter::floor, 180}; // target gain 20
    // 3 requests a day of 3 h (the burner 10 min on, 10 off inside), each up to 0.50 above.
    const auto probe = [](uint32_t t) {
        const uint32_t phase = t % 28800;
        S x; x.heat = x.demand = phase < 10800; x.burner = x.heat && (phase / 600) % 2 == 0;
        x.reason = x.heat ? Reason::heating : Reason::satisfied;
        x.temp = int16_t(phase < 10800 ? 1980 + 70 * int(phase) / 10800 : 2050 - 70 * int(phase - 10800) / 18000);
        return x;
    };
    for (int i = 0; i < 5; ++i) {
        d.day(probe);
        EXPECT_LE(d.tuning().flowPerDegreeC, 10) << "day " << i + 1 << ": no raise while overshooting";
    }
    EXPECT_LT(d.tuning().stopCentiC, 20) << "the stop margin comes down first";
    for (size_t i = 0; i < d.tuner.logCount(); ++i) EXPECT_NE(d.tuner.change(i).reason, AutoTuner::Reason::roomResponse);
}

TEST(AutoTuner, FewStartsNarrowAWidenedStartMargin) {
    Driver d;
    ASSERT_TRUE(d.tuner.restore(R"({"values":{"heat_start_c":0.35},"log":[]})"));
    d.day(cycles(60, 60)); // 12 starts in 24 h
    EXPECT_EQ(d.tuning().startCentiC, 30); EXPECT_EQ(d.tuner.change(0).reason, AutoTuner::Reason::fewStarts);
    for (int i = 0; i < 4; ++i) d.day(cycles(60, 60));
    EXPECT_EQ(d.tuning().startCentiC, 20) << "back to the built-in value, not below";
}

TEST(AutoTuner, LearnedRoomsSetTheGainAndTheLeads) {
    Driver d;
    d.rooms = plan({RoomPlan::Emitter::floor});
    d.learned[0] = {RoomPlan::Emitter::floor, 180};
    d.day(cycles(60, 60));
    EXPECT_EQ(d.tuning().flowPerDegreeC, 11);
    EXPECT_EQ(d.tuning().floorLeadMinutes, 150); EXPECT_EQ(d.tuning().radiatorLeadMinutes, 45);
    for (int i = 0; i < 12; ++i) d.day(cycles(60, 60));
    EXPECT_EQ(d.tuning().flowPerDegreeC, 20); EXPECT_EQ(d.tuning().floorLeadMinutes, 180);
    const auto& c = d.tuner.change(0);
    EXPECT_STREQ(c.room, "woonkamer"); EXPECT_EQ(c.reason, AutoTuner::Reason::roomResponse); EXPECT_EQ(c.figure, 180);
    // A fast room: a gentler gain, a shorter lead (radiators: 15 min a day, at least 10).
    Driver r;
    r.rooms = plan({RoomPlan::Emitter::radiator, RoomPlan::Emitter::radiator});
    r.learned = {{RoomPlan::Emitter::radiator, 20}, {RoomPlan::Emitter::radiator, 30}};
    r.day(cycles(60, 60));
    EXPECT_EQ(r.tuning().flowPerDegreeC, 9); EXPECT_EQ(r.tuning().radiatorLeadMinutes, 30);
    EXPECT_STREQ(r.tuner.change(0).room, "") << "two rooms: the house";
    for (int i = 0; i < 6; ++i) r.day(cycles(60, 60));
    EXPECT_EQ(r.tuning().flowPerDegreeC, 5); EXPECT_EQ(r.tuning().radiatorLeadMinutes, 25);
    // Not learned: nothing.
    Driver n;
    n.day(cycles(60, 60));
    EXPECT_EQ(n.tuner.logCount(), 0u);
}

TEST(AutoTuner, NeedsEnoughEvidence) {
    // 5 heating hours: too few.
    Driver d;
    d.day([](uint32_t t) { return t < 5 * 3600 ? cycles(5, 5)(t) : S{}; });
    EXPECT_STREQ(d.tuner.state(d.now), "collecting"); EXPECT_EQ(d.tuner.logCount(), 0u);
    // 6 hours: enough.
    d.day([](uint32_t t) { return t < 6 * 3600 ? cycles(5, 5)(t) : S{}; });
    EXPECT_EQ(d.tuning().minOffS, 450);
    // Four starts over the day are not enough either.
    Driver f;
    f.day([](uint32_t t) { S x; x.heat = x.burner = x.demand = (t / 3600) % 6 < 3; return x; });
    EXPECT_STREQ(f.tuner.state(f.now), "collecting");
    // Hot-water burns are no heating starts.
    Driver h;
    h.day([](uint32_t t) { S x = cycles(5, 5)(t); x.hotWater = x.burner; return x; });
    EXPECT_EQ(h.tuning().minOffS, 300);
}

// Replay of the owner's data (31 Oct): the hot-water bit of a keep-warm round often
// comes after the burner start, so those rounds counted as heating starts (31 where 3
// were real). A burn is classified as a whole, with a minute before and after it.
TEST(AutoTuner, KeepWarmRoundsWithALateHotWaterBitAreNoHeatingStarts) {
    Driver d;
    d.manual = e_start;
    d.day([](uint32_t t) {
        S x;
        const uint32_t hour = t / 3600;
        if (hour == 6 || hour == 12 || hour == 18) { x.heat = x.burner = x.demand = true; x.reason = Reason::heating; return x; } // 3 real starts
        const uint32_t round = t / 1800, phase = t % 1800; // a keep-warm round every 30 min: 3 min burner
        x.burner = phase < 180;
        switch (round % 3) {
            case 0: x.hotWater = phase >= 30 && phase < 180; break;  // the bit 30 s after the start
            case 1: x.hotWater = (phase >= 200 && phase < 220) || phase >= 1780; break; // 20 s after its end; 20 s before the next start
            default: break;                                          // the next round: the bit only before its start
        }
        return x;
    });
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(d.tuner.addStatus(root.get(), d.now, d.tuning(), 0));
    const cJSON* y = cJSON_GetObjectItem(cJSON_GetObjectItem(root.get(), "tuning"), "yesterday");
    EXPECT_EQ(cJSON_GetObjectItem(y, "starts")->valueint, 3) << "only the heating burns";
    EXPECT_EQ(cJSON_GetObjectItem(y, "burns")->valueint, 3);
    EXPECT_EQ(d.tuning().minOffS, 300);
}

TEST(AutoTuner, WaitsADayAfterABootOrAChange) {
    Driver d;
    d.now = 0; d.utc = monday + 12 * 3600; // a boot at noon: the half day is no evidence
    for (uint32_t t = 12 * 3600 + 10; t <= 86400; t += 10) d.step(cycles(5, 5)(t));
    EXPECT_STREQ(d.tuner.state(d.now), "waiting"); EXPECT_EQ(d.tuner.logCount(), 0u);
    d.day(cycles(5, 5));
    EXPECT_EQ(d.tuning().minOffS, 450);
    // A plan or tuning change at noon: that day and the next midnight wait.
    for (uint32_t t = 10; t <= 43200; t += 10) d.step(cycles(5, 5)(t));
    d.tuner.restart(d.now);
    for (uint32_t t = 43210; t <= 86400; t += 10) d.step(cycles(5, 5)(t));
    EXPECT_EQ(d.tuning().minOffS, 450); EXPECT_STREQ(d.tuner.state(d.now), "waiting");
    d.day(cycles(5, 5));
    EXPECT_EQ(d.tuning().minOffS, 600);
}

TEST(AutoTuner, ShadowModeOnlyShowsWhatItWouldDo) {
    Driver d;
    d.active = false;
    d.day(cycles(5, 5));
    EXPECT_STREQ(d.tuner.state(d.now), "shadow");
    EXPECT_EQ(d.tuner.logCount(), 0u); EXPECT_TRUE(d.tuning() == ControlTuning{});
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(d.tuner.addStatus(root.get(), d.now, d.tuning(), 0));
    char* text = cJSON_PrintUnformatted(cJSON_GetObjectItem(root.get(), "tuning"));
    const std::string json = text; cJSON_free(text);
    EXPECT_NE(json.find(R"("would":[["min_off_s",300,450,"many_starts",143,""],["heat_start_c",0.2,0.25,"hovering",143,""]])"), std::string::npos) << json;
    EXPECT_NE(json.find(R"("log":[])"), std::string::npos);
    EXPECT_NE(json.find(R"("yesterday":{"starts":143,"heating_h":24,"burns":143,"burn_s":300})"), std::string::npos) << json;
    // An owner's knob is not proposed; the rest of the record is the owner's value.
    Driver m;
    m.manual = 2; m.owner.minOffS = 600;
    m.day(cycles(5, 5));
    EXPECT_EQ(m.tuning().minOffS, 600); EXPECT_EQ(m.tuner.values().minOffS, 300);
    EXPECT_EQ(m.tuning().startCentiC, 25);
}

// Review of rc.2 (finding 5): changed() (store and apply the values) only when a value
// changed: never on a shadow day, however many proposals it shows.
TEST(AutoTuner, ChangedOnlyWhenAValueChanged) {
    Driver s;
    s.active = false;
    bool changed = false;
    const auto f = cycles(5, 5);
    for (uint32_t t = 10; t <= 86400; t += 10) { s.step(f(t % 86400)); changed = changed || s.tuner.changed(); }
    EXPECT_STREQ(s.tuner.state(s.now), "shadow");
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.tuner.addStatus(root.get(), s.now, s.tuning(), 0));
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(cJSON_GetObjectItem(root.get(), "tuning"), "would")), 2);
    EXPECT_FALSE(changed) << "nothing applied, nothing to store";
    Driver a;
    for (uint32_t t = 10; t <= 86400; t += 10) a.step(f(t % 86400));
    EXPECT_TRUE(a.tuner.changed());
    // Still one step a day per knob.
    for (uint32_t t = 10; t <= 86400; t += 10) a.step(f(t % 86400));
    EXPECT_EQ(a.tuning().minOffS, 600);
}

// Review of rc.2 (finding 4): an applied change is in the log only, not also under "would".
TEST(AutoTuner, AppliedChangesAreNotAlsoProposals) {
    Driver d;
    d.day(cycles(5, 5));
    ASSERT_EQ(d.tuner.logCount(), 2u);
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(d.tuner.addStatus(root.get(), d.now, d.tuning(), 0));
    const cJSON* tuning = cJSON_GetObjectItem(root.get(), "tuning");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(tuning, "would")), 0);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(tuning, "log")), 2);
}

TEST(AutoTuner, ResetAndTheStoredRecord) {
    Driver d;
    for (int i = 0; i < 3; ++i) d.day(cycles(5, 5));
    ASSERT_EQ(d.tuner.logCount(), 6u);
    const auto record = d.tuner.stored();
    EXPECT_LE(record.size(), AutoTuner::storedMaxBytes);
    AutoTuner back;
    ASSERT_TRUE(back.restore(record.c_str()));
    EXPECT_TRUE(back.values() == d.tuner.values()); EXPECT_EQ(back.stored(), record);
    EXPECT_EQ(back.change(0).to, d.tuner.change(0).to); EXPECT_EQ(back.change(0).utc, d.tuner.change(0).utc);
    // A full log of the widest entries fits.
    AutoTuner full;
    std::string wide = R"({"values":{"min_on_s":1800},"log":[)";
    for (size_t i = 0; i < AutoTuner::logSize; ++i) wide += std::string(i ? "," : "") + R"([4294967295,"radiator_lead_min_per_c",180,180,"cold_during_rest",-327.68,"abcdefghijklmnopqrstuvwxyz012345"])";
    ASSERT_TRUE(full.restore((wide + "]}").c_str()));
    EXPECT_LE(full.stored().size(), AutoTuner::storedMaxBytes);
    EXPECT_EQ(full.change(9).figure, -32768);
    // Its MQTT form (fw/telemetry/tuning) at the widest stays within 1 KB; the page gets all ten.
    ControlTuning widest; size_t kn; const auto* kk = ControlTuning::knobs(kn);
    for (size_t i = 0; i < kn; ++i) widest.*kk[i].field = kk[i].high;
    for (const size_t entries : {AutoTuner::mqttEntries, AutoTuner::logSize + 7}) {
        Json doc(cJSON_CreateObject(), cJSON_Delete);
        cJSON_AddNumberToObject(doc.get(), "schema", 1);
        ASSERT_TRUE(full.addStatus(doc.get(), 0, widest, ControlTuning::autoKnobs, entries));
        char* text = cJSON_PrintUnformatted(doc.get());
        const size_t size = std::strlen(text); cJSON_free(text);
        if (entries == AutoTuner::mqttEntries) { EXPECT_LE(size, 1024u); }
        EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(cJSON_GetObjectItem(doc.get(), "tuning"), "log")), int(std::min(entries, AutoTuner::logSize)));
    }
    // Unreadable: nothing changes.
    for (const char* bad : {"", "[]", R"({"values":{"min_on_s":1},"log":[]})", R"({"values":{},"log":[[1,"x",1,2,"many_starts",1,""]]})",
                            R"({"values":{},"log":[[1,"min_on_s",1,2,"why",1,""]]})", R"({"values":{}})"})
        EXPECT_FALSE(back.restore(bad)) << bad;
    EXPECT_TRUE(back.values() == d.tuner.values());
    // Back to start values: built-in, no log, a day's wait.
    d.tuner.reset(d.now);
    EXPECT_TRUE(d.tuning() == ControlTuning{}); EXPECT_EQ(d.tuner.logCount(), 0u); EXPECT_STREQ(d.tuner.state(d.now), "waiting");
    d.day(cycles(5, 5)); // the reset was at midnight: this whole day counts again
    EXPECT_EQ(d.tuning().minOffS, 450); EXPECT_EQ(d.tuner.logCount(), 2u);
}

TEST(AutoTuner, ManualKnobsInTheFlowRecord) {
    size_t n; const auto* k = ControlTuning::knobs(n);
    // A 1.0 record (before rc.2): every knob given, the changed ones are the owner's.
    FlowSettings s;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"weather_curve":false,"apply_learned":false,"curve_design_flow_c":0,"tuning":)"
        R"({"min_on_s":300,"min_off_s":600,"heat_start_c":0.20,"heat_stop_c":0.10,"flow_per_degree_c":10,"curve_correction_pct":40,)"
        R"("floor_lead_min_per_c":120,"radiator_lead_min_per_c":45,"learned_accept_pct":100,"night_saving_min_pct":2}})").get(), s), nullptr);
    EXPECT_EQ(s.manual, (1u << 1) | (1u << 3)) << "the curve share is never automatic";
    EXPECT_EQ(s.json(), R"({"weather_curve":false,"apply_learned":false,"curve_design_flow_c":0,"tuning":{"min_on_s":300,"min_off_s":600,)"
        R"("heat_start_c":0.20,"heat_stop_c":0.10,"flow_per_degree_c":10,"curve_correction_pct":40,"floor_lead_min_per_c":120,)"
        R"("radiator_lead_min_per_c":45,"learned_accept_pct":100,"night_saving_min_pct":2},"tuning_manual":["min_off_s","heat_stop_c"]})");
    FlowSettings back;
    ASSERT_EQ(FlowSettings::parse(parse(s.json().c_str()).get(), back), nullptr);
    EXPECT_TRUE(back == s);
    // No record, or one without knobs: all automatic.
    FlowSettings none;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"weather_curve":true})").get(), none), nullptr);
    EXPECT_EQ(none.manual, 0);
    // "Set it myself" and "back to automatic" (one knob: its own value is forgotten; all).
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":{"min_on_s":300},"tuning_manual":["min_off_s","heat_stop_c","min_on_s"]})").get(), s), nullptr);
    EXPECT_EQ(s.manual, 0b1011);
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning_manual":["min_on_s","heat_stop_c"]})").get(), s), nullptr);
    EXPECT_EQ(s.manual, 0b1001); EXPECT_EQ(s.tuning.minOffS, 300); EXPECT_EQ(s.tuning.stopCentiC, 10);
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning_manual":[]})").get(), s), nullptr);
    EXPECT_EQ(s.manual, 0); EXPECT_EQ(s.tuning.stopCentiC, 20); EXPECT_EQ(s.tuning.curveCorrectionPct, 40);
    // A partial "tuning" of the older page: what it changes becomes the owner's.
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":{"flow_per_degree_c":14}})").get(), s), nullptr);
    EXPECT_EQ(s.manual, 1u << 4);
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":null})").get(), s), nullptr);
    EXPECT_EQ(s.manual, 0); EXPECT_TRUE(s.tuning == ControlTuning{});
    // Refused: a fixed knob or an unknown name, not a list.
    const FlowSettings before = s;
    for (const char* bad : {R"({"tuning_manual":["curve_correction_pct"]})", R"({"tuning_manual":["x"]})", R"({"tuning_manual":"min_on_s"})",
                            R"({"tuning_manual":[1]})"})
        EXPECT_STREQ(FlowSettings::parse(parse(bad).get(), s), "invalid_value") << bad;
    EXPECT_TRUE(s == before);
    // GET shows the knobs in effect; a backup of it restores the same record (one key at a time).
    AutoTuner t;
    ASSERT_TRUE(t.restore(R"({"values":{"min_off_s":750,"heat_stop_c":0.15},"log":[]})"));
    FlowSettings stored;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":{"min_on_s":420},"tuning_manual":["min_on_s"]})").get(), stored), nullptr);
    const auto shown = t.effective(stored.tuning, stored.manual);
    EXPECT_EQ(shown.minOnS, 420); EXPECT_EQ(shown.minOffS, 750); EXPECT_EQ(shown.stopCentiC, 15);
    const auto get = parse(stored.json(&shown).c_str());
    FlowSettings restored;
    for (const cJSON* c = get->child; c; c = c->next) {
        Json one(cJSON_CreateObject(), cJSON_Delete);
        cJSON_AddItemToObject(one.get(), c->string, cJSON_Duplicate(c, true));
        ASSERT_EQ(FlowSettings::parse(one.get(), restored), nullptr) << c->string;
    }
    EXPECT_TRUE(restored == stored);
    (void)k; (void)n;
}

// Closed loops: RoomEngine (the rule), the tuner and one room, 14 days, active.
// rate = a (flow - T) - b (T - outdoor); after heat stops the emitter keeps giving
// its last rate, fading with tau (h): a floor slab. Optional: a week program
// (20 degC 06:00..22:00, else 18).
struct Loop {
    ScopedTz tz{ScopedTz::amsterdam};
    RoomPlan rooms;
    RoomEngine engine;
    AutoTuner tuner;
    double T = 20, S = 22, coastRate = 0;
    double a, b, outdoor, tau;
    bool tune = true, slab = false;
    uint64_t now = 0;
    uint32_t utc = monday;
    struct DayResult { unsigned starts = 0; double meanDev = 0, lowest = 99, overshoot = 0; };
    Loop(RoomPlan::Emitter e, double a_, double b_, double out, double tau_, bool program = false)
        : rooms(plan({e})), a(a_), b(b_), outdoor(out), tau(tau_) {
        if (e == RoomPlan::Emitter::floor) { rooms.minimumFlowC = 30; rooms.maximumFlowC = 45; }
        if (program) for (auto& d : rooms.rooms[0].schedule.days) { d.points[0] = {360, 2000}; d.points[1] = {1320, 1800}; d.count = 2; }
        engine.setPlan(rooms); engine.setTuning(tuner.values());
    }
    // Per day: heating starts, mean |T - target| and the lowest T - target (3 h after a step on),
    // and the mean of the per-cycle highest T - target.
    DayResult day() {
        DayResult r;
        bool was = false;
        double devSum = 0, peak = -99, overSum = 0; int n = 0, cyclesSeen = 0;
        int16_t lastSp = 0; uint64_t spAt = 0;
        for (uint32_t t = 10; t <= 86400; t += 10) {
            now += 10000; utc += 10;
            const int16_t measured = int16_t(std::lround(T * 10) * 10);
            engine.haState("climate.woonkamer", measured, std::nullopt, now);
            const auto request = engine.step(now, utc);
            const int16_t sp = engine.result(0).setpoint.value_or(2000);
            if (sp != lastSp) { lastSp = sp; spAt = now; }
            const double dev = T - sp / 100.0;
            if (request.heat && !was) { ++r.starts; if (peak > -99) { overSum += std::max(0.0, peak); ++cyclesSeen; } peak = -99; }
            peak = std::max(peak, dev);
            was = request.heat;
            const double dt = 10.0 / 3600;
            if (slab) { // a floor: the water heats the slab (a), the slab the room (tau: 1 / its coupling)
                const double toRoom = (S - T) / tau;
                S += ((request.heat ? a * (request.flowC - S) : 0) - 0.3 * toRoom) * dt;
                T += (toRoom - b * (T - outdoor)) * dt;
            } else {
                const double emit = request.heat ? a * (request.flowC - T) : 0;
                if (request.heat) coastRate = emit; else coastRate *= std::exp(-dt / tau);
                T += (request.heat ? emit : coastRate) * dt - b * (T - outdoor) * dt;
            }
            if (now - spAt >= 3 * 3600000ull) { devSum += std::fabs(dev); ++n; r.lowest = std::min(r.lowest, dev); }
            const auto tuning = engine.tuning();
            AutoTuner::Room room{measured, sp, engine.demand(0)};
            AutoTuner::Step s;
            s.now = now; s.utc = utc; s.request = request; s.burnerOn = request.heat; s.hotWater = false; s.active = true;
            s.tuning = &tuning; s.rooms = &room; s.count = 1;
            if (tuner.sample(s)) {
                AutoTuner::Learned none;
                tuner.evaluate(now, utc, 0, rooms, &none, 1);
                if (tuner.changed() && tune) engine.setTuning(tuner.values());
            }
        }
        r.meanDev = n ? devSum / n : 0; r.overshoot = cyclesSeen ? overSum / cyclesSeen : 0;
        return r;
    }
};

TEST(AutoTuner, ClosedLoopShortCyclingRoomStartsLessWithoutComfortLoss) {
    // A small, fast radiator room on a mild day (10 degC): heat 3.5 degC/h, cooling 3.5 degC/h.
    Loop l(RoomPlan::Emitter::radiator, 0.7, 0.35, 10, 0.05);
    std::vector<Loop::DayResult> days;
    for (int i = 0; i < 14; ++i) days.push_back(l.day());
    const auto& t = l.tuner.values();
    std::printf("[ autotune ] short cycling: day 1 %u starts (mean |dev| %.2f, lowest %+.2f), day 14 %u starts (mean |dev| %.2f, lowest %+.2f); "
                "min_off %u s, heat_start %.2f, %zu changes\n", days[0].starts, days[0].meanDev, days[0].lowest, days[13].starts,
                days[13].meanDev, days[13].lowest, unsigned(t.minOffS), t.startCentiC / 100.0, l.tuner.logCount());
    EXPECT_GT(days[0].starts, 3u * 24) << "more than 3 an hour";
    EXPECT_LE(days[13].starts * 10, days[0].starts * 8) << "at least 20 % fewer";
    EXPECT_LE(days[13].starts, 3u * 24) << "at most 3 an hour";
    EXPECT_LT(days[13].meanDev, 0.2); EXPECT_GT(days[13].lowest, -0.4) << "never 0.4 degC below the target";
    for (int i = 10; i < 14; ++i) EXPECT_NEAR(days[i].starts, days[13].starts, 2) << "settled";
}

TEST(AutoTuner, ClosedLoopOvershootingFloorOvershootsLess) {
    // A floor: the water heats the slab, the slab the room; the rule's integral
    // keeps raising the flow while the room still lags (3 h), so the slab overshoots; 0 degC outside.
    Loop l(RoomPlan::Emitter::floor, 0.2, 0.05, 0, 3);
    l.slab = true;
    std::vector<Loop::DayResult> days;
    for (int i = 0; i < 14; ++i) days.push_back(l.day());
    const auto& t = l.tuner.values();
    const auto mean = [&](int from, int to) { double sum = 0; for (int i = from; i < to; ++i) sum += days[i].overshoot; return sum / (to - from); };
    std::printf("[ autotune ] floor overshoot: days 1-3 %.2f degC (%u starts on day 1, lowest %+.2f), days 12-14 %.2f degC (%u starts, lowest %+.2f); "
                "heat_stop %.2f, flow_per_degree %u, %zu changes\n", mean(0, 3), days[0].starts, days[0].lowest, mean(11, 14),
                days[13].starts, days[13].lowest, t.stopCentiC / 100.0, unsigned(t.flowPerDegreeC), l.tuner.logCount());
    EXPECT_GT(mean(0, 3), 0.4);
    EXPECT_LT(mean(11, 14), mean(0, 3) - 0.15);
    EXPECT_LT(t.stopCentiC, 20);
    for (int i = 0; i < 14; ++i) EXPECT_GT(days[i].lowest, -0.3) << "no comfort loss, day " << i + 1;
}
}
