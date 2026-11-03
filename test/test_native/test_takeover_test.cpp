#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "control/ActiveHeatGuard.h"
#include "control/ConfigBackup.h"
#include "control/HttpAccessPolicy.h"
#include "control/NewPlanDefault.h"
#include "control/RoomPlan.h"
#include "control/ControlPartitionBudget.h"
#include "control/TakeoverReadiness.h"
#include "control/TakeoverTest.h"
#include <cstdio>
#include <gtest/gtest.h>
#include <functional>
#include <memory>
#include <string>
#include <vector>

// rc.2 (owner, 2 Nov 2026): a new plan follows the boiler bus (a trial run beside an EMS thermostat,
// else active), the guided boiler test leads to the takeover, and nothing reaches the boiler before
// the owner confirms it.
namespace {
using heating::control::ActiveHeatGuard;
using heating::control::RoomPlan;
using heating::control::TakeoverTest;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
using Step = TakeoverTest::Step;
using Mark = TakeoverTest::Mark;
using State = TakeoverTest::State;
constexpr uint64_t second = 1000, minute = 60000;

Json parse(const std::string& text) { return Json(cJSON_Parse(text.c_str()), cJSON_Delete); }
std::string text(const cJSON* o, const char* key) {
    const cJSON* v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsString(v) ? v->valuestring : "";
}

// --- the new defaults (from the boiler bus) ------------------------------------------------------------------------------

using heating::control::NewPlanDefault;
using Reason = NewPlanDefault::Reason;

TEST(NewPlanDefault, AThermostatOnTheBusGivesATrialRun) {
    // Another EMS controller asked the boiler for heat this boot: run beside it first.
    for (const uint64_t listened : {uint64_t(0), 30 * second, 2 * minute, 600 * minute}) {
        const auto d = NewPlanDefault::decide(true, listened, true);
        EXPECT_EQ(d.mode, RoomPlan::Mode::shadow);
        EXPECT_EQ(d.reason, Reason::thermostatHeard);
    }
}

TEST(NewPlanDefault, NoThermostatGoesStraightToTheBoilerTest) {
    const auto d = NewPlanDefault::decide(false, 2 * minute, true);
    EXPECT_EQ(d.mode, RoomPlan::Mode::active);
    EXPECT_EQ(d.reason, Reason::noThermostat);
    // Firmware without the active gate keeps the trial run.
    EXPECT_EQ(NewPlanDefault::decide(false, 2 * minute, false).mode, RoomPlan::Mode::shadow);
}

TEST(NewPlanDefault, UndecidedUntilTheBusWasHeardIsNeverActive) {
    for (const uint64_t listened : {uint64_t(0), 10 * second, 2 * minute - 1}) {
        const auto d = NewPlanDefault::decide(false, listened, true);
        EXPECT_EQ(d.mode, RoomPlan::Mode::shadow) << listened;
        EXPECT_EQ(d.reason, Reason::checking);
    }
    // The plan of an E32 without a stored one starts in shadow mode until the bus decides.
    RoomPlan fresh;
    ASSERT_EQ(RoomPlan::parse(parse(RoomPlan{}.documentJson()).get(), fresh), nullptr);
    EXPECT_EQ(fresh.mode, RoomPlan::Mode::shadow);
    EXPECT_TRUE(fresh.rooms.empty());
    // Bus timeline: checking, then active without a thermostat; a thermostat heard later turns it back.
    RoomPlan plan = fresh;
    EXPECT_FALSE(NewPlanDefault::decide(false, minute, true).apply(plan, false));
    EXPECT_TRUE(NewPlanDefault::decide(false, 2 * minute, true).apply(plan, false));
    EXPECT_EQ(plan.mode, RoomPlan::Mode::active);
    EXPECT_TRUE(NewPlanDefault::decide(true, 3 * minute, true).apply(plan, false));
    EXPECT_EQ(plan.mode, RoomPlan::Mode::shadow);
    // Status: {"new_plan":{"stored","mode","reason"}}.
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(NewPlanDefault::decide(true, 0, true).addJson(root.get(), false));
    std::unique_ptr<char, decltype(&cJSON_free)> t(cJSON_PrintUnformatted(root.get()), cJSON_free);
    EXPECT_STREQ(t.get(), R"({"new_plan":{"stored":false,"mode":"shadow","reason":"thermostat_heard"}})");
}

TEST(NewPlanDefault, AStoredPlanAndTheOwnersChoiceKeepTheirMode) {
    // An existing installation, or a plan the owner saved (trial run first / straight to the test).
    for (const auto mode : {RoomPlan::Mode::shadow, RoomPlan::Mode::active}) {
        RoomPlan plan; plan.mode = mode;
        EXPECT_FALSE(NewPlanDefault::decide(false, 10 * minute, true).apply(plan, true));
        EXPECT_FALSE(NewPlanDefault::decide(true, 10 * minute, true).apply(plan, true));
        EXPECT_FALSE(NewPlanDefault::decide(false, 0, true).apply(plan, true));
        EXPECT_EQ(plan.mode, mode);
    }
}

TEST(NewPlanDefault, AStoredShadowPlanStaysShadow) {
    // An existing installation in the trial run: its stored plan is read and written back as it is.
    const std::string stored = R"({"schema":1,"revision":7,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":55,"rooms":[)"
        R"({"id":"woonkamer","name":"Woonkamer","state":"active","inactive_until":0,"emitter":"floor","sources":[{"type":"ha","id":"climate.woonkamer"}],)"
        R"("setpoint_entity":"climate.woonkamer","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500}]})";
    RoomPlan plan;
    ASSERT_EQ(RoomPlan::parse(parse(stored).get(), plan), nullptr);
    EXPECT_EQ(plan.mode, RoomPlan::Mode::shadow);
    RoomPlan again;
    ASSERT_EQ(RoomPlan::parse(parse(plan.storedJson()).get(), again), nullptr);
    EXPECT_EQ(again.mode, RoomPlan::Mode::shadow);
    EXPECT_EQ(text(parse(plan.json()).get(), "mode"), "shadow");
    // A plan without a mode is still refused: nothing falls back to the new default.
    RoomPlan none;
    EXPECT_STREQ(RoomPlan::parse(parse(R"({"schema":1,"minimum_flow_c":30,"maximum_flow_c":60,"rooms":[]})").get(), none), "invalid_mode");
}

// A new installation with an active plan: heat wanted for hours, the old thermostat still on
// the bus for the first hour, never confirmed. Not one byte goes to the boiler.
bool encode(const heating::ems::BoilerTestSession::Intent& intent, heating::ems::EmsRawFrame& frame) {
    constexpr auto addressing = heating::ems::ClassicBoilerTestEncoder::Addressing::classicService();
    return heating::ems::ClassicBoilerTestEncoder::encode(addressing, intent, frame);
}
struct NewInstall {
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    heating::ems::ClassicBoilerMonitor monitor;
    heating::ems::ActiveHeatPollDriver driver{0x2a, true};
    std::vector<std::vector<uint8_t>> frames;
    uint64_t now = 0;
    NewInstall() {
        in.mode = NewPlanDefault::decide(false, 2 * minute, true).mode; // no thermostat heard: active
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 1850;
        in.request.heat = true; in.request.flowC = 50;
        in.routeReady = true; in.boilerLimitC = 60;
        EXPECT_TRUE(monitor.receive({heating::ems::EmsTelegram::WRITE, 8, 0x17, 1, 0x16, {60}}, 1000));
    }
    void run(uint64_t ms, bool thermostat) {
        for (const uint64_t end = now + ms; now < end;) {
            now += 10 * second;
            in.uptimeMs = now; in.boilerHeardAtMs = now;
            if (thermostat && now % (40 * second) == 0) in.foreign = ActiveHeatGuard::Foreign{0x10, now};
            const auto c = guard.step(now, in);
            driver.post(now, c.send ? std::optional<uint8_t>(c.flowC) : std::nullopt,
                        in.mode == RoomPlan::Mode::active && (guard.confirmed() || guard.reconfirmPending()), guard.claimsBoiler());
            driver.poll(now, monitor, [] { return true; }, encode, [&](const heating::ems::EmsRawFrame& f) {
                frames.emplace_back(f.data.begin(), f.data.begin() + f.length);
                return true;
            });
            guard.transmitted(now, driver.last() && driver.last()->ok);
        }
    }
};

TEST(NewPlanDefault, NothingIsSentBeforeTheConfirmation) {
    NewInstall b;
    b.run(60 * minute, true);   // the old thermostat still connected
    b.in.foreign.reset();
    b.run(6 * 60 * minute, false); // disconnected, but not confirmed
    EXPECT_EQ(b.guard.state(), ActiveHeatGuard::State::awaitingConfirmation);
    EXPECT_FALSE(b.guard.claimsBoiler());
    EXPECT_FALSE(b.guard.outputActive());
    EXPECT_TRUE(b.frames.empty()) << b.frames.size() << " frames sent";
    // Frost in a room does not change that either: only a takeover the owner confirmed heats.
    b.in.rooms.coldestCentiC = 600;
    b.run(30 * minute, false);
    EXPECT_TRUE(b.frames.empty());
    // The confirmation is the only way in: then the request goes out (0B 08 1A 00 <flow> <crc>).
    b.in.rooms.coldestCentiC = 1850;
    b.guard.confirm(b.now, true);
    b.run(2 * minute, false);
    ASSERT_FALSE(b.frames.empty());
    EXPECT_EQ(b.frames[0][0], 0x0b); EXPECT_EQ(b.frames[0][2], 0x1a); EXPECT_EQ(b.frames[0][4], 50);
}

// --- restore ---------------------------------------------------------------------------------------

namespace b = heating::control::backup;
TEST(RestoreMode, AnActivePlanStaysActiveAndAsksForTheConfirmation) {
    const auto plan = [](const char* mode) {
        return std::string(R"({"schema":1,"revision":3,"mode":")") + mode + R"(","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[)"
            R"({"id":"living","name":"Living","state":"active","inactive_until":0,"emitter":"radiator","sources":[{"type":"ble","id":"a4c138a3e8db"}],)"
            R"("setpoint_entity":"","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500}]})";
    };
    for (const char* mode : {"active", "shadow"}) {
        const auto backup = parse(std::string(R"({"heating":)") + plan(mode) + "}");
        b::DeviceState state;
        b::Report report;
        std::string out;
        ASSERT_EQ(b::preparePlan(backup.get(), state, out, report), nullptr);
        EXPECT_EQ(text(parse(out).get(), "mode"), mode);
        const auto warnings = report.warnings.get();
        bool asks = false, old = false;
        for (const cJSON* w = warnings ? warnings->child : nullptr; w; w = w->next) {
            asks |= cJSON_IsString(w) && std::string(w->valuestring) == "plan_takeover_confirm";
            old |= cJSON_IsString(w) && std::string(w->valuestring) == "plan_mode_shadow";
        }
        EXPECT_EQ(asks, std::string(mode) == "active");
        EXPECT_FALSE(old);
    }
}

// --- the guided boiler test ------------------------------------------------------------------------

// Boiler telemetry and the guard's view, stepped every 10 s like stepActiveHeat.
struct Sim {
    TakeoverTest test;
    TakeoverTest::Inputs in;
    uint64_t now = 10 * minute;
    std::vector<std::optional<int16_t>> targets; // every change of the test target
    Sim() {
        in.boilerHeardAtMs = now; in.roomCentiC = 2040; in.flowCentiC = 3000;
        in.burnerOn = false; in.hotWater = false; in.ceilingC = 60;
        test.start(now, "living", 1762070400);
        take();
    }
    void take() { if (test.takeTargetChange()) targets.push_back(test.target()); }
    void run(uint64_t ms, const std::function<void()>& each = {}) {
        for (const uint64_t end = now + ms; now < end && test.running();) {
            now += 10 * second;
            in.boilerHeardAtMs = now;
            if (each) each();
            test.step(now, in);
            take();
        }
    }
    std::string json() const {
        Json j(test.json(now), cJSON_Delete);
        std::unique_ptr<char, decltype(&cJSON_free)> t(cJSON_PrintUnformatted(j.get()), cJSON_free);
        return t.get();
    }
    void disconnect() { run(2 * minute + 10 * second); }
    void confirm() { in.confirmed = true; run(10 * second); in.owning = true; in.released = false; run(10 * second); }
    // The burner starts and the flow climbs 0.5 degC per 10 s.
    void heat() { in.burnerOn = true; run(3 * minute, [&] { *in.flowCentiC += 50; }); }
    void tap() { in.hotWater = true; run(3 * minute); in.hotWater = false; in.burnerOn = false; run(minute); in.burnerOn = true; run(10 * second); }
};

TEST(TakeoverTest, AllStepsPass) {
    Sim s;
    EXPECT_EQ(s.test.state(), State::running);
    EXPECT_EQ(s.test.current(), Step::disconnect);
    EXPECT_NE(s.json().find(R"("step":"disconnect","phase":"listening")"), std::string::npos) << s.json();
    s.disconnect();
    EXPECT_EQ(s.test.mark(Step::disconnect), Mark::pass);
    EXPECT_EQ(s.test.current(), Step::confirm);
    s.run(minute);
    EXPECT_NE(s.json().find(R"("phase":"waiting_confirmation")"), std::string::npos);
    s.confirm();
    EXPECT_EQ(s.test.mark(Step::confirm), Mark::pass);
    s.in.requestC = 52; // the E32's flow request from here on (the record keeps the highest)
    // Start: 1 degC above the room (20.4 -> 21.4), as a temporary override.
    ASSERT_EQ(s.test.current(), Step::start);
    s.run(10 * second);
    ASSERT_EQ(s.targets.size(), 1u);
    EXPECT_EQ(s.targets[0], std::optional<int16_t>(2140));
    EXPECT_EQ(s.test.overrideMinutes(), 60);
    s.heat();
    EXPECT_EQ(s.test.mark(Step::start), Mark::pass);
    // Hot water while heating: the target is kept (at least 1 degC above the room).
    ASSERT_EQ(s.test.current(), Step::hotWater);
    s.run(30 * second);
    EXPECT_NE(s.json().find(R"("phase":"waiting_tap")"), std::string::npos);
    s.tap();
    EXPECT_EQ(s.test.mark(Step::hotWater), Mark::pass);
    // Stop: 0.5 degC below the room (20.4 -> 19.9); the zero is delivered after the minimum burn.
    ASSERT_EQ(s.test.current(), Step::stop);
    s.in.roomCentiC = 2080;
    s.run(10 * second);
    EXPECT_EQ(s.test.target(), std::optional<int16_t>(2030));
    s.run(4 * minute); // minimum burner time
    EXPECT_NE(s.json().find(R"("phase":"waiting_zero")"), std::string::npos);
    s.in.released = true;
    s.run(20 * second);
    s.in.burnerOn = false;
    s.run(5 * minute + 10 * second);
    EXPECT_EQ(s.test.state(), State::passed);
    EXPECT_EQ(s.test.mark(Step::stop), Mark::pass);
    // Done: the override ends, the program continues; the result is kept.
    EXPECT_EQ(s.test.target(), std::nullopt);
    EXPECT_EQ(s.targets.back(), std::nullopt);
    EXPECT_EQ(s.test.record(), "1762070400 ppppp p - 52 - -");
    EXPECT_EQ(s.json(), R"({"state":"passed","at":1762070400,"steps":{"disconnect":"pass","confirm":"pass","start":"pass",)"
                        R"("hot_water":"pass","stop":"pass"},"reason":null,"summary":"passed","flow_c":52,"marked":false,"marked_at":null})");
    TakeoverTest kept;
    ASSERT_TRUE(kept.restore(s.test.record()));
    EXPECT_EQ(kept.state(), State::passed);
    EXPECT_EQ(kept.mark(Step::hotWater), Mark::pass);
}

TEST(TakeoverTest, DisconnectWaitsForTheOldThermostatAndTimesOut) {
    Sim s;
    // The old thermostat asks every 40 s: never 2 quiet minutes.
    s.run(20 * minute, [&] { if (s.now % (40 * second) == 0) s.in.foreignAtMs = s.now; });
    EXPECT_EQ(s.test.current(), Step::disconnect);
    EXPECT_NE(s.json().find(R"("phase":"thermostat_heard")"), std::string::npos) << s.json();
    // Unplugged: two quiet minutes from its last request pass the step.
    const uint64_t last = *s.in.foreignAtMs;
    s.run(2 * minute);
    EXPECT_EQ(s.test.mark(Step::disconnect), Mark::pass);
    EXPECT_GE(s.now - last, 2 * minute);
    // The boiler switched off and never back on: no boiler messages, the step times out.
    Sim off;
    off.run(30 * minute + 10 * second, [&] { off.in.boilerHeardAtMs = 0; });
    EXPECT_EQ(off.test.state(), State::failed);
    EXPECT_EQ(off.test.mark(Step::disconnect), Mark::fail);
    EXPECT_EQ(off.test.reason(), "boiler_silent");
    // Already taken over (confirmed, owning, no foreign request since): passes at once.
    Sim owned;
    owned.in.confirmed = owned.in.owning = true;
    owned.run(20 * second);
    EXPECT_EQ(owned.test.mark(Step::disconnect), Mark::pass);
    EXPECT_EQ(owned.test.mark(Step::confirm), Mark::pass);
    EXPECT_EQ(owned.test.current(), Step::start);
}

TEST(TakeoverTest, ConfirmTimesOutOrFailsOnAnotherThermostat) {
    Sim s;
    s.disconnect();
    s.run(30 * minute);
    EXPECT_EQ(s.test.state(), State::failed);
    EXPECT_EQ(s.test.mark(Step::confirm), Mark::fail);
    EXPECT_EQ(s.test.reason(), "not_confirmed");
    Sim slow; // confirmed, but the guard never takes over (no fresh rooms, route not ready)
    slow.disconnect();
    slow.in.confirmed = true;
    slow.run(30 * minute);
    EXPECT_EQ(slow.test.reason(), "no_takeover");
    Sim foreign;
    foreign.disconnect();
    foreign.in.blocked = true;
    foreign.run(10 * second);
    EXPECT_EQ(foreign.test.reason(), "foreign_controller");
    EXPECT_EQ(foreign.test.mark(Step::confirm), Mark::fail);
}

TEST(TakeoverTest, StartFailsWithoutBurnerOrFlowRise) {
    Sim s;
    s.disconnect(); s.confirm();
    s.run(10 * minute + 10 * second);
    EXPECT_EQ(s.test.state(), State::failed);
    EXPECT_EQ(s.test.mark(Step::start), Mark::fail);
    EXPECT_EQ(s.test.reason(), "no_burner");
    EXPECT_EQ(s.test.target(), std::nullopt); // the override ends with the test
    Sim flat;
    flat.disconnect(); flat.confirm();
    flat.in.burnerOn = true;
    flat.run(15 * minute + 10 * second, [&] { *flat.in.flowCentiC = int16_t(3000 + (flat.now / second) % 2 * 100); });
    EXPECT_EQ(flat.test.reason(), "no_flow_rise");
    // Hot water does not count as heating: the burner for a tap is no start.
    Sim tap;
    tap.disconnect(); tap.confirm();
    tap.in.burnerOn = tap.in.hotWater = true;
    tap.run(10 * minute + 10 * second, [&] { *tap.in.flowCentiC += 50; });
    EXPECT_EQ(tap.test.reason(), "no_burner");
    // No fresh reading of the test room, or its maximum leaves no room for +1 degC.
    Sim blind;
    blind.disconnect(); blind.confirm();
    blind.in.roomCentiC.reset();
    blind.run(10 * second);
    EXPECT_EQ(blind.test.reason(), "no_room_reading");
    Sim capped;
    capped.disconnect(); capped.confirm();
    capped.in.roomMaxCentiC = 2040;
    capped.run(10 * second);
    EXPECT_EQ(capped.test.reason(), "room_limit");
}

TEST(TakeoverTest, HotWaterPassesSkipsOrFails) {
    Sim s;
    s.disconnect(); s.confirm(); s.heat();
    ASSERT_EQ(s.test.current(), Step::hotWater);
    s.run(15 * minute + 10 * second);
    EXPECT_EQ(s.test.reason(), "no_hot_water");
    EXPECT_EQ(s.test.mark(Step::hotWater), Mark::fail);
    Sim slow; // heating does not come back within 5 minutes after the tap
    slow.disconnect(); slow.confirm(); slow.heat();
    slow.in.hotWater = true; slow.run(3 * minute);
    slow.in.hotWater = false; slow.in.burnerOn = false;
    slow.run(5 * minute + 10 * second);
    EXPECT_EQ(slow.test.reason(), "heating_not_resumed");
    Sim warned; // a warning during the step stops the test
    warned.disconnect(); warned.confirm(); warned.heat();
    warned.in.hotWater = true; warned.run(minute);
    warned.in.warning = "transmit_failed";
    warned.run(10 * second);
    EXPECT_EQ(warned.test.state(), State::stopped);
    EXPECT_EQ(warned.test.reason(), "transmit_failed");
    Sim none; // a boiler without hot water: the step can be skipped, only this one
    none.disconnect();
    EXPECT_FALSE(none.test.skip(none.now));
    none.confirm(); none.heat();
    EXPECT_TRUE(none.test.skip(none.now));
    EXPECT_EQ(none.test.mark(Step::hotWater), Mark::skipped);
    EXPECT_EQ(none.test.current(), Step::stop);
    EXPECT_FALSE(none.test.skip(none.now));
}

TEST(TakeoverTest, StopFailsWhenTheBurnerKeepsGoingOrRestarts) {
    const auto atStop = [](Sim& s) { s.disconnect(); s.confirm(); s.heat(); s.tap(); ASSERT_EQ(s.test.current(), Step::stop); };
    Sim never;
    atStop(never);
    never.run(30 * minute + 10 * second);
    EXPECT_EQ(never.test.reason(), "no_stop_request");
    Sim on;
    atStop(on);
    on.in.released = true;
    on.run(70 * second);
    EXPECT_EQ(on.test.reason(), "burner_still_on");
    EXPECT_EQ(on.test.mark(Step::stop), Mark::fail);
    Sim again;
    atStop(again);
    again.in.released = true; again.in.burnerOn = false;
    again.run(2 * minute);
    again.in.burnerOn = true;
    again.run(10 * second);
    EXPECT_EQ(again.test.reason(), "restarted");
    // A tap after the stop is hot water, not a restart.
    Sim tap;
    atStop(tap);
    tap.in.released = true; tap.in.burnerOn = false;
    tap.run(minute);
    tap.in.burnerOn = tap.in.hotWater = true;
    tap.run(2 * minute);
    tap.in.burnerOn = tap.in.hotWater = false;
    tap.run(3 * minute);
    EXPECT_EQ(tap.test.state(), State::passed);
    // The room's minimum leaves no room 0.5 degC below it.
    Sim low;
    low.disconnect(); low.confirm(); low.heat(); low.tap();
    low.in.roomMinCentiC = 2040;
    low.in.roomCentiC = 2040;
    low.run(10 * second);
    EXPECT_EQ(low.test.reason(), "room_limit");
}

TEST(TakeoverTest, AbortRulesStopTheTest) {
    using Rule = std::function<void(TakeoverTest::Inputs&)>;
    const std::vector<std::pair<Rule, const char*>> rules = {
        {[](auto& in) { in.blocked = true; }, "foreign_controller"},
        {[](auto& in) { in.confirmed = false; }, "handed_back"},
        {[](auto& in) { in.warning = "measurement_lost"; }, "measurement_lost"},
        {[](auto& in) { in.warning = "boiler_no_response"; }, "boiler_no_response"},
    };
    for (const auto& [rule, why] : rules)
        for (int at = 0; at < 3; ++at) { // in the start, hot-water and stop steps
            Sim s;
            s.disconnect(); s.confirm();
            if (at > 0) s.heat();
            if (at > 1) s.tap();
            rule(s.in);
            s.run(10 * second);
            EXPECT_EQ(s.test.state(), State::stopped) << why << " " << at;
            EXPECT_EQ(s.test.reason(), why);
            EXPECT_EQ(s.test.mark(Step(uint8_t(Step::start) + at)), Mark::fail);
            EXPECT_EQ(s.test.target(), std::nullopt);
        }
    // The flow above the ceiling while heating, twice in a row (not for hot water).
    Sim hot;
    hot.disconnect(); hot.confirm();
    hot.in.burnerOn = true; hot.in.flowCentiC = 6600;
    hot.in.hotWater = true;
    hot.run(minute);
    EXPECT_TRUE(hot.test.running());
    hot.in.hotWater = false;
    hot.run(10 * second);
    EXPECT_TRUE(hot.test.running());
    hot.run(10 * second);
    EXPECT_EQ(hot.test.reason(), "flow_above_limit");
    // The boiler silent for 3 minutes.
    Sim quiet;
    quiet.disconnect(); quiet.confirm();
    const uint64_t heard = quiet.now;
    quiet.run(3 * minute + 20 * second, [&] { quiet.in.boilerHeardAtMs = heard; });
    EXPECT_EQ(quiet.test.reason(), "boiler_silent");
    EXPECT_EQ(quiet.test.state(), State::stopped);
    // The caller's own rules (the plan back to the trial run).
    Sim trial;
    trial.disconnect();
    trial.test.interrupt("trial_run", trial.now);
    EXPECT_EQ(trial.test.state(), State::stopped);
    EXPECT_EQ(trial.test.mark(Step::confirm), Mark::fail);
}

TEST(TakeoverTest, TheOwnerAbortsAnyStep) {
    for (int at = 0; at < 5; ++at) {
        Sim s;
        if (at > 0) s.disconnect();
        if (at > 1) s.confirm();
        if (at > 2) s.heat();
        if (at > 3) s.tap();
        ASSERT_EQ(s.test.current(), Step(at));
        s.test.abort(s.now);
        s.take();
        EXPECT_EQ(s.test.state(), State::aborted);
        EXPECT_EQ(s.test.mark(Step(at)), Mark::aborted);
        EXPECT_EQ(s.test.reason(), "owner");
        EXPECT_EQ(s.test.target(), std::nullopt);
        if (at > 2) { EXPECT_EQ(s.targets.back(), std::nullopt); }
        TakeoverTest kept;
        ASSERT_TRUE(kept.restore(s.test.record()));
        EXPECT_EQ(kept.mark(Step(at)), Mark::aborted);
        EXPECT_EQ(kept.state(), State::aborted);
    }
}

TEST(TakeoverTest, RecordsAndRunningStatus) {
    TakeoverTest t;
    EXPECT_EQ(t.state(), State::idle);
    EXPECT_EQ(t.record(), "");
    Json idle(t.json(0), cJSON_Delete);
    EXPECT_EQ(text(idle.get(), "state"), "idle");
    for (const char* bad : {"", "x", "1 ppp p -", "1 ppppx p -", "1 ppppp r -", "1 ppppp q -", "1 ppppp"})
        EXPECT_FALSE(t.restore(bad)) << bad;
    EXPECT_EQ(t.state(), State::idle);
    ASSERT_TRUE(t.restore("0 pff-- f no_burner") == false); // '-' is no mark
    ASSERT_TRUE(t.restore("0 ppfnn f no_burner"));
    Json failed(t.json(0), cJSON_Delete);
    EXPECT_EQ(text(failed.get(), "reason"), "no_burner");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(failed.get(), "at")));
    EXPECT_EQ(text(cJSON_GetObjectItemCaseSensitive(failed.get(), "steps"), "start"), "fail");
    EXPECT_EQ(text(cJSON_GetObjectItemCaseSensitive(failed.get(), "steps"), "stop"), "not_run");
    // Running: the step, its phase and figures; the current step "wait".
    Sim s;
    s.disconnect(); s.confirm();
    s.in.burnerOn = true;
    s.run(minute, [&] { *s.in.flowCentiC += 30; });
    Json run(s.test.json(s.now), cJSON_Delete);
    EXPECT_EQ(text(run.get(), "state"), "running");
    EXPECT_EQ(text(run.get(), "step"), "start");
    EXPECT_EQ(text(run.get(), "phase"), "waiting_flow_rise");
    EXPECT_EQ(text(run.get(), "room"), "living");
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(run.get(), "target_c")->valuedouble, 21.4);
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(run.get(), "rise_c")->valuedouble, 1.5);
    EXPECT_EQ(text(cJSON_GetObjectItemCaseSensitive(run.get(), "steps"), "start"), "wait");
    EXPECT_LE(s.json().size(), 400u);
    // A new start clears the previous result.
    s.test.start(s.now, "living", 0);
    EXPECT_EQ(s.test.mark(Step::disconnect), Mark::none);
    EXPECT_EQ(s.test.reason(), "");
}

// --- rc.3: the one boiler test remembers itself ------------------------------------------------------------------------

TEST(BoilerTestRecord, ARc2RecordIsReadAndRewrittenWithTheNewFields) {
    // rc.2 kept "<utc> <marks> <state> <reason>"; rc.3 reads it and adds flow, mark and thermostat.
    TakeoverTest t;
    ASSERT_TRUE(t.restore("1762070400 ppppp p -"));
    EXPECT_EQ(t.state(), State::passed);
    EXPECT_EQ(t.flowC(), 0);
    EXPECT_FALSE(t.marked());
    EXPECT_FALSE(t.thermostatSeen());
    EXPECT_EQ(t.record(), "1762070400 ppppp p - 0 - -");
    // rc.2 after a rollback reads the first four fields of an rc.3 record (it ignores the rest).
    char marks[6] = {}, state = 0, reason[25] = {};
    unsigned long at = 0;
    EXPECT_EQ(std::sscanf("1762070400 ppfnn f no_burner 55 - t", "%lu %5s %c %24s", &at, marks, &state, reason), 4);
    EXPECT_EQ(std::string(reason), "no_burner");
}

TEST(BoilerTestRecord, TheLastResultSurvivesARestartWithTheFlowUsed) {
    Sim s;
    s.disconnect(); s.confirm();
    s.in.requestC = 48;
    s.run(30 * second);
    s.in.requestC = 55;
    s.run(30 * second);
    s.in.requestC = 50;
    s.run(10 * minute + 10 * second); // no burner within 10 minutes
    ASSERT_EQ(s.test.state(), State::failed);
    EXPECT_EQ(s.test.reason(), "no_burner");
    EXPECT_EQ(s.test.flowC(), 55);
    EXPECT_EQ(s.test.record(), "1762070400 ppfnn f no_burner 55 - -");
    TakeoverTest kept;
    ASSERT_TRUE(kept.restore(s.test.record()));
    EXPECT_EQ(kept.state(), State::failed);
    EXPECT_EQ(kept.reason(), "no_burner");
    EXPECT_EQ(kept.flowC(), 55);
    EXPECT_EQ(kept.record(), s.test.record());
    Json j(kept.json(0), cJSON_Delete);
    EXPECT_EQ(text(j.get(), "summary"), "failed");
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(j.get(), "flow_c")->valuedouble, 55);
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(j.get(), "at")->valuedouble, 1762070400);
}

TEST(BoilerTestRecord, ATestRunningAtARestartReadsBackAsStopped) {
    // The record is written at every step; the override was RAM only, so the restart ended the test.
    Sim s;
    s.disconnect();
    ASSERT_EQ(s.test.current(), Step::confirm);
    EXPECT_EQ(s.test.record(), "1762070400 pnnnn r - 0 - -");
    TakeoverTest kept;
    ASSERT_TRUE(kept.restore(s.test.record()));
    EXPECT_FALSE(kept.running());
    EXPECT_EQ(kept.state(), State::stopped);
    EXPECT_EQ(kept.reason(), "e32_restarted");
    EXPECT_EQ(kept.mark(Step::disconnect), Mark::pass);
    EXPECT_EQ(kept.mark(Step::confirm), Mark::fail);
    EXPECT_EQ(kept.mark(Step::start), Mark::none);
    EXPECT_EQ(kept.record(), "1762070400 pfnnn s e32_restarted 0 - -");
}

TEST(BoilerTestRecord, MarkedAsDoneIsKeptAsAMarkAndCanBeUndone) {
    TakeoverTest t;
    Json never(t.json(0), cJSON_Delete);
    EXPECT_EQ(text(never.get(), "summary"), "never");
    EXPECT_EQ(t.markDone(1762180000), nullptr);
    EXPECT_TRUE(t.marked());
    EXPECT_EQ(t.state(), State::idle); // a mark, never a measured pass
    EXPECT_EQ(t.summary(false), std::string("marked"));
    EXPECT_EQ(t.record(), "0 nnnnn i - 0 1762180000 -");
    Json marked(t.json(0), cJSON_Delete);
    EXPECT_EQ(text(marked.get(), "state"), "idle");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(marked.get(), "marked")));
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(marked.get(), "marked_at")->valuedouble, 1762180000);
    // Across a restart.
    TakeoverTest kept;
    ASSERT_TRUE(kept.restore(t.record()));
    EXPECT_TRUE(kept.marked());
    EXPECT_EQ(kept.markedAt(), 1762180000u);
    EXPECT_EQ(kept.summary(false), std::string("marked"));
    // Undo: nothing left to keep; the stored record is replaced by the idle one.
    EXPECT_TRUE(kept.unmark());
    EXPECT_FALSE(kept.unmark());
    EXPECT_EQ(kept.summary(false), std::string("never"));
    EXPECT_EQ(kept.record(), "");
    TakeoverTest empty;
    ASSERT_TRUE(empty.restore(TakeoverTest::emptyRecord()));
    EXPECT_EQ(empty.state(), State::idle);
    EXPECT_FALSE(empty.marked());
    EXPECT_EQ(empty.record(), "");
    // The clock unknown: a mark without a date.
    TakeoverTest undated;
    EXPECT_EQ(undated.markDone(0), nullptr);
    EXPECT_EQ(undated.record(), "0 nnnnn i - 0 0 -");
    Json u(undated.json(0), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(u.get(), "marked")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(u.get(), "marked_at")));
}

TEST(BoilerTestRecord, AMarkBesideAFailedTestAndANewStartReplacesIt) {
    TakeoverTest t;
    ASSERT_TRUE(t.restore("1762070400 ppfnn f no_burner 55 - -"));
    EXPECT_EQ(t.markDone(1762180000), nullptr); // newer than the failure: the owner's word
    EXPECT_EQ(t.summary(true), std::string("marked"));
    EXPECT_EQ(t.record(), "1762070400 ppfnn f no_burner 55 1762180000 -");
    EXPECT_TRUE(t.unmark());
    EXPECT_EQ(t.summary(false), std::string("failed")); // the measured result again
    // A start: what the E32 measures replaces the mark.
    EXPECT_EQ(t.markDone(1762180000), nullptr);
    t.start(0, "living", 1762190000);
    EXPECT_FALSE(t.marked());
    EXPECT_EQ(t.summary(false), std::string("running"));
    EXPECT_EQ(t.markDone(1762190100), std::string("test_running"));
    t.abort(10 * second);
    EXPECT_EQ(t.summary(false), std::string("aborted"));
    EXPECT_EQ(t.markDone(1762190200), nullptr);
    // A measured pass needs no mark.
    TakeoverTest passed;
    ASSERT_TRUE(passed.restore("1762070400 ppppp p - 52 - -"));
    EXPECT_EQ(passed.markDone(1762180000), std::string("test_passed"));
    EXPECT_FALSE(passed.marked());
    EXPECT_FALSE(passed.unmark());
}

TEST(BoilerTestRecord, AnInstallationTheE32ControlledBeforeNeedsNoTest) {
    TakeoverTest never;
    EXPECT_EQ(never.summary(true), std::string("not_needed"));
    Json j(never.json(0, true), cJSON_Delete);
    EXPECT_EQ(text(j.get(), "summary"), "not_needed");
    EXPECT_EQ(text(j.get(), "state"), "idle");
    TakeoverTest aborted;
    ASSERT_TRUE(aborted.restore("1762070400 pannn a owner 0 - -"));
    EXPECT_EQ(aborted.summary(true), std::string("not_needed"));
    EXPECT_EQ(aborted.summary(false), std::string("aborted"));
    // A measured failure or a safety stop stays visible: it says what to check.
    for (const char* record : {"1762070400 ppfnn f no_burner 0 - -", "1762070400 ppfnn s flow_above_limit 60 - -"}) {
        TakeoverTest t;
        ASSERT_TRUE(t.restore(record)) << record;
        EXPECT_NE(t.summary(true), std::string("not_needed")) << record;
    }
    TakeoverTest passed;
    ASSERT_TRUE(passed.restore("1762070400 ppppp p - 52 - -"));
    EXPECT_EQ(passed.summary(true), std::string("passed"));
}

TEST(BoilerTestRecord, APastThermostatIsKept) {
    TakeoverTest t;
    EXPECT_FALSE(t.thermostatSeen());
    EXPECT_TRUE(t.sawThermostat());
    EXPECT_FALSE(t.sawThermostat()); // once: written only when new
    EXPECT_EQ(t.record(), "0 nnnnn i - 0 - t");
    TakeoverTest kept;
    ASSERT_TRUE(kept.restore(t.record()));
    EXPECT_TRUE(kept.thermostatSeen());
    EXPECT_EQ(kept.summary(false), std::string("never"));
    // A start, an abort or a mark keeps the fact.
    kept.start(0, "living", 0);
    EXPECT_TRUE(kept.thermostatSeen());
    kept.abort(second);
    EXPECT_EQ(kept.markDone(1762180000), nullptr);
    EXPECT_EQ(kept.record(), "0 annnn a owner 0 1762180000 t");
    // Before rc.3: a thermostat period in the stored readiness window is the same fact.
    using Readiness = heating::control::TakeoverReadiness;
    Readiness::Stored stored;
    EXPECT_FALSE(Readiness::thermostatSeenIn(stored));
    stored.days[4].flags = Readiness::fallbackSeen;
    EXPECT_FALSE(Readiness::thermostatSeenIn(stored));
    stored.days[4].flags |= Readiness::thermostatSeen;
    EXPECT_TRUE(Readiness::thermostatSeenIn(stored));
    stored.version = 2;
    EXPECT_FALSE(Readiness::thermostatSeenIn(stored));
}

TEST(BoilerTestRecord, MalformedRecordsAreRefused) {
    for (const char* bad : {"1 ppppp p - x - -", "1 ppppp p - 100 - -", "1 ppppp p - -1 - -", "1 ppppp p - 0 abc -", "1 ppppp p - 0 12a -",
                            "1 ppppp p - 0 - x", "1 pnnnn i - 0 - -", "1 ppppp r - 0", "1 ppppp p - 0 -", "1 ppppp q - 0 - -",
                            "1 ppppp i -", "1 ppppp r -", "1 ppppp p - 0 99999999999 -"}) {
        TakeoverTest t;
        EXPECT_FALSE(t.restore(bad)) << bad;
        EXPECT_EQ(t.state(), State::idle) << bad;
        EXPECT_FALSE(t.marked()) << bad;
    }
}

TEST(BoilerTestRecord, TheRecordFitsTheSmallNoteOfRc2) {
    // The same NVS key and bound as rc.2 (a string < 64 bytes: the 3 entries of a handover record),
    // never among the records erased to make room.
    TakeoverTest t;
    ASSERT_TRUE(t.restore("4294967295 ppppf s abcdefghijklmnopqrstuvwx 99 4294967295 t"));
    EXPECT_EQ(t.record(), "4294967295 ppppf s abcdefghijklmnopqrstuvwx 99 4294967295 t");
    EXPECT_LT(t.record().size(), 64u);
    EXPECT_LE(t.record().size(), 59u);
    using B = heating::control::ControlPartitionBudget;
    EXPECT_LE(B::reclaimEntries(t.record().size() + 1), B::handoverEntries); // 1 + 2 entries
    for (const char* key : B::optionalKeys) EXPECT_STRNE(key, "takeover_test");
}

TEST(BoilerTestSafety, TheAttendedTestsRulesStopTheMergedTest) {
    // Another controller, a hand-back, the flow ceiling and the stop check (above) stay; and from the
    // attended test: a boiler settings write or an attended bus check holding the bus ends it.
    Sim busy;
    busy.disconnect(); busy.confirm();
    busy.in.busy = true;
    busy.run(10 * second);
    EXPECT_EQ(busy.test.state(), State::stopped);
    EXPECT_EQ(busy.test.reason(), "boiler_busy");
    EXPECT_EQ(busy.test.target(), std::nullopt);
    // Before the E32 owns the boiler the bus check may run (the takeover waits for it).
    Sim early;
    early.in.busy = true;
    early.run(minute);
    EXPECT_TRUE(early.test.running());
    // The flow ceiling while heating: twice in a row above min(plan maximum, boiler limit) + 5 degC.
    Sim hot;
    hot.disconnect(); hot.confirm();
    hot.in.burnerOn = true; hot.in.flowCentiC = 6600; // ceiling 60
    hot.run(20 * second);
    EXPECT_EQ(hot.test.state(), State::stopped);
    EXPECT_EQ(hot.test.reason(), "flow_above_limit");
    // Another controller once the E32 owns the boiler.
    Sim foreign;
    foreign.disconnect(); foreign.confirm();
    foreign.in.blocked = true;
    foreign.run(10 * second);
    EXPECT_EQ(foreign.test.reason(), "foreign_controller");
}

TEST(TakeoverTest, TheRouteTakesPostOnly) {
    EXPECT_TRUE(heating::control::allowedHttpMethod("/config/heating/takeover-test", "POST"));
    for (const char* method : {"GET", "DELETE", "PUT"}) EXPECT_FALSE(heating::control::allowedHttpMethod("/config/heating/takeover-test", method));
}
}
