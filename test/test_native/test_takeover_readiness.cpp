#include "control/TakeoverReadiness.h"
#include "control/ShadowComparison.h"
#include "control/TelemetryPolicy.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstring>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace {
using heating::control::FlowDemand;
using heating::control::RoomDemand;
using heating::control::ShadowComparison;
using heating::control::TakeoverReadiness;
using heating::diagnostics::SupervisorPolicy;
using Result = TakeoverReadiness::Result;
using Restart = TakeoverReadiness::Restart;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60 * second, hour = 60 * minute;
// 2026-10-28 00:00 CET (23:00 UTC the day before); the tests set the Amsterdam TZ.
const uint32_t midnight = uint32_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 - 3600;

struct Period { uint64_t from, to; uint8_t flowC = 45; }; // ms since the run's start
bool within(const std::vector<Period>& ps, uint64_t t, uint8_t* flow = nullptr) {
    for (const auto& p : ps) if (t >= p.from && t < p.to) { if (flow) *flow = p.flowC; return true; }
    return false;
}

// One shadow period sampled every 10 s: the thermostat's and the E32's heat,
// one room (two sources, measured, 20 degC) and a boiler that is heard.
struct Shadow {
    TakeoverReadiness r;
    uint64_t t = 0;                  // uptime ms
    uint32_t utcAtZero = midnight;   // local midnight at t = 0
    std::vector<Period> thermostat, e32;
    bool thermostatOnBus = true;
    std::function<void(uint64_t, TakeoverReadiness::Inputs&)> adjust;
    TakeoverReadiness::Inputs base() const {
        TakeoverReadiness::Inputs in;
        in.planMaximumC = 60; in.boilerLimitC = 70; in.limitRead = true;
        in.roomCount = 1; in.rooms[0] = {RoomDemand::Status::ok, int16_t(2000), 2};
        return in;
    }
    void until(uint64_t endMs) {
        for (; t < endMs; t += 10 * second) {
            auto in = base();
            in.utc = utcAtZero + uint32_t(t / 1000);
            in.boilerHeardAtMs = t;
            uint8_t flow = 0;
            if (within(e32, t, &flow)) in.e32 = {true, flow, FlowDemand::Reason::heating};
            if (thermostatOnBus) in.thermostatFlowC = uint8_t(within(thermostat, t) ? 45 : 0);
            if (adjust) adjust(t, in);
            r.sample(t, in);
        }
    }
};
// n periods of 30 min, every 2 h from 00:30; the E32 offset by `lagMs`.
void regular(Shadow& run, int n, int64_t lagMs = 0, uint8_t flowC = 45) {
    for (int i = 0; i < n; ++i) {
        const uint64_t from = 30 * minute + uint64_t(i) * 2 * hour;
        run.thermostat.push_back({from, from + 30 * minute});
        run.e32.push_back({uint64_t(int64_t(from) + lagMs), uint64_t(int64_t(from + 30 * minute) + lagMs), flowC});
    }
}
Json json(const TakeoverReadiness& r) { return Json(r.json(), cJSON_Delete); }
const cJSON* item(const cJSON* o, const char* key) { return cJSON_GetObjectItemCaseSensitive(o, key); }
double num(const cJSON* o, const char* key) { return cJSON_GetNumberValue(item(o, key)); }
std::string result(const cJSON* o, const char* key) { return cJSON_GetStringValue(item(item(o, key), "result")); }

TEST(TakeoverReadiness, OnlyASoftwareRestartWithoutAFaultIsPlanned) {
    using R = SupervisorPolicy::Reason;
    EXPECT_EQ(TakeoverReadiness::classify(3, R::none), Restart::planned);            // update, restart button
    EXPECT_EQ(TakeoverReadiness::classify(3, R::bluetoothApply), Restart::planned);
    EXPECT_EQ(TakeoverReadiness::classify(3, R::settingsRestore), Restart::planned);
    EXPECT_EQ(TakeoverReadiness::classify(3, R::setupReenter), Restart::planned); // the owner asked for Wi-Fi setup (R2-07)
    for (R fault : {R::loopStall, R::wifiLost, R::brokerLost, R::networkDead, R::updateStuck, R::bluetoothSilent, R::controlFault})
        EXPECT_EQ(TakeoverReadiness::classify(3, fault), Restart::unexpected) << SupervisorPolicy::name(fault);
    for (int reset : {0, 4, 5, 6, 7}) EXPECT_EQ(TakeoverReadiness::classify(reset, R::none), Restart::unexpected) << reset; // panic, watchdogs
    for (int reset : {1, 2, 9}) EXPECT_EQ(TakeoverReadiness::classify(reset, R::none), Restart::power) << reset;
}

TEST(TakeoverReadiness, StableAfterExactly72Hours) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    run.until(72 * hour - 10 * second);
    EXPECT_EQ(run.r.stable(), Result::wait);
    EXPECT_EQ(run.r.stableS(), 72 * 3600 - 20u); // the last sample was 10 s before
    run.until(72 * hour + 10 * second);
    EXPECT_EQ(run.r.stable(), Result::pass);
    EXPECT_EQ(run.r.restart(), Restart::first);
}

TEST(TakeoverReadiness, APlannedRestartKeepsTheStableTimeAnUnexpectedOneResetsIt) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow before;
    regular(before, 6);
    before.until(40 * hour);
    const auto stored = before.r.stored();
    EXPECT_EQ(stored.stableS, 40 * 3600 - 10u);
    for (Restart restart : {Restart::planned, Restart::unexpected, Restart::power}) {
        Shadow after;
        after.utcAtZero = midnight + 40 * 3600;
        after.r.restore(&stored, restart);
        EXPECT_EQ(after.r.restart(), restart);
        EXPECT_EQ(after.r.saveDue(0), restart != Restart::planned); // the stored stable time no longer holds
        after.until(32 * hour + 20 * second);
        const auto t = after.r.totals();
        EXPECT_EQ(t.thermostatPeriods, 6u) << "counters survive every restart";
        if (restart == Restart::planned) {
            EXPECT_EQ(after.r.stable(), Result::pass);
            EXPECT_GE(after.r.stableS(), 72 * 3600u);
        } else {
            EXPECT_EQ(after.r.stable(), Result::wait);
            EXPECT_EQ(after.r.stableS(), 32 * 3600 + 10u);
            Json j = json(after.r);
            EXPECT_STREQ(cJSON_GetStringValue(item(item(j.get(), "stable"), "restart")), TakeoverReadiness::restartName(restart));
        }
    }
    // An unreadable record (another version) is a first start: nothing carried.
    auto other = stored; other.version = 2;
    TakeoverReadiness fresh; fresh.restore(&other, Restart::planned);
    EXPECT_EQ(fresh.restart(), Restart::first);
    EXPECT_EQ(fresh.stableS(), 0u);
    EXPECT_EQ(fresh.totals().thermostatPeriods, 0u);
    fresh.restore(nullptr, Restart::planned);
    EXPECT_EQ(fresh.restart(), Restart::first);
}

TEST(TakeoverReadiness, StoredAtADayChangeEverySixHoursAndAfterAnUnexpectedRestart) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    run.utcAtZero = midnight + 20 * 3600; // 20:00
    run.until(5 * hour);                   // past midnight
    EXPECT_TRUE(run.r.saveDue(run.t));
    run.r.saved(run.t);
    EXPECT_FALSE(run.r.saveDue(run.t + 6 * hour - 1));
    EXPECT_TRUE(run.r.saveDue(run.t + 6 * hour));
    const auto stored = run.r.stored();
    TakeoverReadiness crashed; crashed.restore(&stored, Restart::unexpected);
    EXPECT_TRUE(crashed.saveDue(0)); // the stored stable time no longer holds
    TakeoverReadiness updated; updated.restore(&stored, Restart::planned);
    EXPECT_FALSE(updated.saveDue(0));
}

TEST(TakeoverReadiness, TenPeriodsWithASetbackAWarmUpAndAQuietHour) {
    ScopedTz tz(ScopedTz::amsterdam);
    // Day 1: 9 periods (00:30 .. 16:30), the target falls at 22:00 and rises at 06:30 the next day.
    Shadow run;
    regular(run, 9);
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) {
        if (t >= 22 * hour && t < 30 * hour + 30 * minute) in.rooms[0].setpoint = int16_t(1700);
    };
    run.until(24 * hour);
    auto t = run.r.totals();
    EXPECT_EQ(t.thermostatPeriods, 9u);
    EXPECT_EQ(t.setbacks, 1u);
    EXPECT_GE(t.quiet, 1u); // 1.5 h between the periods, the E32 quiet too
    EXPECT_EQ(t.warmups, 0u);
    EXPECT_EQ(run.r.periods(t), Result::wait);
    Json j = json(run.r);
    EXPECT_EQ(result(j.get(), "periods"), "wait");
    EXPECT_EQ(num(item(j.get(), "periods"), "thermostat"), 9);
    // Day 2, 07:00: the thermostat starts within the hour after the 06:30 rise.
    run.thermostat.push_back({24 * hour + 7 * hour, 24 * hour + 7 * hour + 40 * minute});
    run.e32.push_back({24 * hour + 7 * hour, 24 * hour + 7 * hour + 40 * minute});
    run.until(24 * hour + 9 * hour);
    t = run.r.totals();
    EXPECT_EQ(t.thermostatPeriods, 10u);
    EXPECT_EQ(t.warmups, 1u);
    EXPECT_EQ(run.r.periods(t), Result::pass);
}

TEST(TakeoverReadiness, ARiseWithoutAThermostatStartWithinTheHourIsNoWarmUp) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    run.thermostat.push_back({7 * hour + 31 * minute, 8 * hour});
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) { if (t < 6 * hour + 30 * minute) in.rooms[0].setpoint = int16_t(1700); };
    run.until(9 * hour);
    EXPECT_EQ(run.r.totals().warmups, 0u);
    // A setback of 0.4 degC in the evening is too small; one in the afternoon is no night setback.
    Shadow small;
    small.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) {
        if (t >= 21 * hour) in.rooms[0].setpoint = int16_t(1960);
        if (t >= 14 * hour && t < 15 * hour) in.rooms[0].setpoint = int16_t(1500);
    };
    small.until(23 * hour);
    EXPECT_EQ(small.r.totals().setbacks, 0u);
}

TEST(TakeoverReadiness, AGapUnderTwoMinutesIsOnePeriod) {
    ScopedTz tz(ScopedTz::amsterdam);
    for (uint64_t gap : {110 * second, 120 * second}) {
        Shadow run;
        run.thermostat = {{1 * hour, 2 * hour}, {2 * hour + gap, 3 * hour}};
        run.until(4 * hour);
        EXPECT_EQ(run.r.totals().thermostatPeriods, gap < 120 * second ? 1u : 2u) << gap;
    }
}

TEST(TakeoverReadiness, TimingWaitsForTwentyEventsThenJudgesTheMatches) {
    ScopedTz tz(ScopedTz::amsterdam);
    {   // 9 periods: 18 events, wait; the 10th makes 20, all matched within 5 min.
        Shadow run;
        regular(run, 10, 3 * minute);
        run.until(17 * hour + 10 * minute);
        auto t = run.r.totals();
        EXPECT_EQ(t.events, 18u);
        EXPECT_EQ(run.r.timing(t), Result::wait);
        run.until(20 * hour);
        t = run.r.totals();
        EXPECT_EQ(t.events, 20u); EXPECT_EQ(t.matched, 20u); EXPECT_EQ(t.close, 20u);
        EXPECT_EQ(run.r.timing(t), Result::pass);
    }
    {   // Every E32 start and stop 6 min late: matched, but the median is over 5 min.
        Shadow run;
        regular(run, 10, 6 * minute);
        run.until(22 * hour);
        const auto t = run.r.totals();
        EXPECT_EQ(t.matched, 20u); EXPECT_EQ(t.close, 0u); EXPECT_EQ(t.near, 20u);
        EXPECT_EQ(run.r.timing(t), Result::fail);
    }
    {   // Half within 5 min, half at 14 min: median 5 min and 90 % within 15, pass; at 16 min the 90 % fails.
        for (uint64_t late : {14 * minute, 16 * minute}) {
            Shadow run;
            regular(run, 10);
            for (size_t i = 5; i < 10; ++i) { run.e32[i].from += late; run.e32[i].to += late; }
            run.until(22 * hour);
            const auto t = run.r.totals();
            EXPECT_EQ(t.matched, 20u);
            EXPECT_EQ(run.r.timing(t), late < 15 * minute ? Result::pass : Result::fail) << late;
        }
    }
    {   // 16 of 20 matched (80 %) passes, 15 of 20 fails: the E32 skips 2 periods, then also stops one 35 min late.
        for (bool late : {false, true}) {
            Shadow run;
            regular(run, 10);
            run.e32.erase(run.e32.begin(), run.e32.begin() + 2);
            if (late) run.e32[0].to += 35 * minute;
            run.until(22 * hour);
            const auto t = run.r.totals();
            EXPECT_EQ(t.events, 20u);
            EXPECT_EQ(t.matched, late ? 15u : 16u);
            EXPECT_EQ(run.r.timing(t), late ? Result::fail : Result::pass) << late;
        }
    }
}

TEST(TakeoverReadiness, TheNearestE32EventBeforeOrAfterCounts) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run; // the E32 starts 4 min before the thermostat and stops 20 min after it
    run.thermostat = {{2 * hour, 3 * hour}};
    run.e32 = {{2 * hour - 4 * minute, 3 * hour + 20 * minute}};
    run.until(5 * hour);
    const auto t = run.r.totals();
    EXPECT_EQ(t.events, 2u); EXPECT_EQ(t.matched, 2u); EXPECT_EQ(t.close, 1u); EXPECT_EQ(t.near, 1u);
}

TEST(TakeoverReadiness, TheRequestNeverAboveTheHardLimit) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto flow = [](uint8_t flowC, uint8_t planMax, std::optional<uint8_t> boiler, uint64_t length) {
        Shadow run;
        run.e32 = {{1 * hour, 1 * hour + length, flowC}};
        run.adjust = [=](uint64_t, TakeoverReadiness::Inputs& in) { in.planMaximumC = planMax; in.boilerLimitC = boiler; };
        run.until(1 * hour + length + minute);
        return run.r.flow(run.r.totals());
    };
    EXPECT_EQ(flow(60, 60, 70, 2 * hour), Result::pass);       // at the plan maximum
    EXPECT_EQ(flow(61, 60, 70, 2 * hour), Result::fail);       // one degree above it
    EXPECT_EQ(flow(55, 60, 55, 2 * hour), Result::pass);       // at the boiler's own limit
    EXPECT_EQ(flow(56, 60, 55, 2 * hour), Result::fail);
    EXPECT_EQ(flow(80, 80, std::nullopt, 2 * hour), Result::pass); // unknown boiler limit: 80 degC
    EXPECT_EQ(flow(81, 80, std::nullopt, 2 * hour), Result::fail);
    EXPECT_EQ(flow(45, 60, 70, 59 * minute), Result::wait);    // less than an hour of requests
    EXPECT_EQ(flow(45, 60, 70, 61 * minute), Result::pass);
    EXPECT_EQ(flow(61, 60, 70, 5 * minute), Result::fail);     // a breach fails at once
}

TEST(TakeoverReadiness, CyclingNotMoreE32PeriodsThanTheThermostat) {
    ScopedTz tz(ScopedTz::amsterdam);
    for (int extra : {0, 1}) {
        Shadow run;
        regular(run, 10);
        if (extra) { run.e32[9].to = run.e32[9].from + 10 * minute; run.e32.push_back({run.e32[9].from + 15 * minute, run.e32[9].from + 30 * minute}); }
        run.until(17 * hour);
        EXPECT_EQ(run.r.cycling(run.r.totals()), Result::wait) << "9 thermostat periods";
        run.until(22 * hour);
        const auto t = run.r.totals();
        EXPECT_EQ(t.e32Periods, 10u + extra);
        EXPECT_EQ(run.r.cycling(t), extra ? Result::fail : Result::pass);
    }
}

TEST(TakeoverReadiness, SourcesWorkAndAFallbackTookOver) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto sources = [](std::function<void(uint64_t, TakeoverReadiness::Inputs&)> adjust) {
        Shadow run; run.adjust = std::move(adjust);
        run.until(2 * hour);
        return run.r.sources(run.r.totals());
    };
    EXPECT_EQ(sources(nullptr), Result::wait); // two sources, no fallback yet
    EXPECT_EQ(sources([](uint64_t, auto& in) { in.rooms[0].sources = 1; }), Result::fail); // no fallback possible
    EXPECT_EQ(sources([](uint64_t t, auto& in) { if (t >= hour && t < hour + 20 * minute) in.rooms[0].status = RoomDemand::Status::fallback; }),
              Result::pass); // took over once, the main sensor is back
    EXPECT_EQ(sources([](uint64_t t, auto& in) { if (t < hour) in.rooms[0].status = RoomDemand::Status::fallback;
                                                 else in.rooms[0].status = RoomDemand::Status::lost; }), Result::fail);
    EXPECT_EQ(sources([](uint64_t, auto& in) { in.rooms[0].status = RoomDemand::Status::stale; }), Result::fail);
    EXPECT_EQ(sources([](uint64_t, auto& in) { in.roomCount = 0; }), Result::fail);
    // An inactive room needs nothing; the active one decides.
    EXPECT_EQ(sources([](uint64_t t, auto& in) {
        in.roomCount = 2; in.rooms[1] = {RoomDemand::Status::inactive, std::nullopt, 1};
        if (t < 10 * minute) in.rooms[0].status = RoomDemand::Status::fallback; }), Result::pass);
}

TEST(TakeoverReadiness, AHomeWithoutAThermostatOnTheBusChecksTheBoilerInstead) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    run.thermostatOnBus = false;
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) {
        if (t < 10 * minute) in.rooms[0].status = RoomDemand::Status::fallback;
        if (t < 20 * minute) { in.limitRead = false; in.boilerLimitC = std::nullopt; }
    };
    run.until(4 * minute);
    EXPECT_EQ(run.r.boiler(), Result::pass);
    EXPECT_EQ(run.r.boilerLimit(), Result::wait); // the first 15 minutes
    run.until(16 * minute);
    EXPECT_EQ(run.r.boilerLimit(), Result::fail);
    EXPECT_STREQ(run.r.state(), "not_ready");
    run.until(72 * hour + 10 * second);
    EXPECT_STREQ(run.r.state(), "ready");
    Json j = json(run.r);
    EXPECT_FALSE(cJSON_IsTrue(item(j.get(), "comparison")));
    std::vector<std::string> keys;
    for (const cJSON* c = j->child; c; c = c->next) keys.push_back(c->string);
    EXPECT_EQ(keys, (std::vector<std::string>{"state", "comparison", "stable", "sources", "boiler", "boiler_limit"}));
    EXPECT_EQ(num(item(j.get(), "boiler_limit"), "limit_c"), 70);
    EXPECT_EQ(num(item(j.get(), "boiler"), "age_s"), 0);
    // The boiler silent for more than 5 minutes.
    auto in = run.base(); in.boilerHeardAtMs = run.t - 6 * minute;
    run.r.sample(run.t, in);
    EXPECT_EQ(run.r.boiler(), Result::fail);
    EXPECT_STREQ(run.r.state(), "not_ready");
}

TEST(TakeoverReadiness, OverallReadyOnlyWhenEverythingPasses) {
    ScopedTz tz(ScopedTz::amsterdam);
    // Three days like the owner's plan: 10 periods a day, a 22:00 setback and a 06:30 rise.
    Shadow run;
    for (int d = 0; d < 3; ++d)
        for (int i = 0; i < 8; ++i) {
            const uint64_t from = uint64_t(d) * 24 * hour + 7 * hour + uint64_t(i) * 2 * hour;
            run.thermostat.push_back({from, from + 30 * minute});
            run.e32.push_back({from + 2 * minute, from + 32 * minute, 44});
        }
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) {
        const uint64_t local = t % (24 * hour);
        if (local >= 22 * hour || local < 6 * hour + 30 * minute) in.rooms[0].setpoint = int16_t(1700);
        if (t >= 30 * hour && t < 30 * hour + 15 * minute) in.rooms[0].status = RoomDemand::Status::fallback;
    };
    run.until(48 * hour);
    EXPECT_STREQ(run.r.state(), "waiting"); // everything but the 72 hours
    for (const char* key : {"periods", "timing", "flow", "cycling", "sources"}) EXPECT_EQ(result(json(run.r).get(), key), "pass") << key;
    EXPECT_EQ(result(json(run.r).get(), "stable"), "wait");
    run.until(72 * hour + 10 * second);
    EXPECT_STREQ(run.r.state(), "ready");
    // One request over the limit: not ready, whatever else passes.
    auto in = run.base(); in.utc = run.utcAtZero + uint32_t(run.t / 1000); in.e32 = {true, 61, FlowDemand::Reason::heating};
    run.r.sample(run.t, in);
    EXPECT_STREQ(run.r.state(), "not_ready");
    EXPECT_EQ(result(json(run.r).get(), "flow"), "fail");
    // Taken over: not applicable, and the counters stand still.
    const auto before = run.r.totals();
    in.active = true; in.e32 = {true, 45, FlowDemand::Reason::heating}; in.thermostatFlowC.reset();
    for (int i = 0; i < 100; ++i) run.r.sample(run.t += 10 * second, in);
    EXPECT_STREQ(run.r.state(), "not_applicable");
    EXPECT_EQ(run.r.totals().requestS, before.requestS);
    Json active = json(run.r);
    EXPECT_EQ(cJSON_GetArraySize(active.get()), 1);
}

TEST(TakeoverReadiness, TheWindowIsTheLastSevenDays) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    regular(run, 3);
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) { if (t < 10 * minute) in.rooms[0].status = RoomDemand::Status::fallback; };
    run.until(7 * 24 * hour - minute); // day 7: the first day is the oldest one kept
    EXPECT_EQ(run.r.totals().thermostatPeriods, 3u);
    EXPECT_TRUE(run.r.totals().flags & TakeoverReadiness::fallbackSeen);
    run.until(7 * 24 * hour + minute);
    EXPECT_EQ(run.r.totals().thermostatPeriods, 0u);
    EXPECT_FALSE(run.r.totals().flags & TakeoverReadiness::fallbackSeen);
    // Three days off: those days stay empty, the days before move back three places.
    Shadow gap;
    regular(gap, 2);
    gap.until(2 * hour);
    gap.utcAtZero += 3 * 86400;
    gap.thermostat.push_back({3 * hour, 4 * hour});
    gap.until(5 * hour);
    EXPECT_EQ(gap.r.day(0).thermostatPeriods, 1u);
    EXPECT_EQ(gap.r.day(3).thermostatPeriods, 1u);
    EXPECT_EQ(gap.r.day(3).day + 3, gap.r.day(0).day);
}

// The owner's shadow period (no replay fixture with the thermostat request is
// in the repository; shadow_exit.py on his Home Assistant history, 1 Nov 2026):
// stable 50.6 of 72 h, 9 of 10 periods, 18 of 20 timing events, flow maximum
// 54 degC under the hard limit, cycling waiting for its 10 periods. WAIT, no FAIL.
TEST(TakeoverReadiness, TheOwnersPeriodWaitsWithoutAFailure) {
    ScopedTz tz(ScopedTz::amsterdam);
    Shadow run;
    run.utcAtZero = midnight + 17 * 3600; // 30 Oct 17:10 local, the install of beta.20
    for (int i = 0; i < 9; ++i) {
        const uint64_t from = 2 * hour + uint64_t(i) * 5 * hour + 30 * minute;
        run.thermostat.push_back({from, from + 40 * minute});
        run.e32.push_back({from + 3 * minute, from + 38 * minute, uint8_t(46 + i)}); // up to 54 degC
    }
    run.adjust = [](uint64_t t, TakeoverReadiness::Inputs& in) {
        in.planMaximumC = 60;
        if (t >= 20 * hour && t < 20 * hour + 30 * minute) in.rooms[0].status = RoomDemand::Status::fallback;
    };
    run.until(uint64_t(50.6 * double(hour)));
    const auto t = run.r.totals();
    EXPECT_NEAR(run.r.stableS() / 3600.0, 50.6, 0.01);
    EXPECT_EQ(t.thermostatPeriods, 9u);
    EXPECT_EQ(t.events, 18u);
    EXPECT_EQ(t.flowMaxC, 54u);
    EXPECT_EQ(run.r.flow(t), Result::pass);
    EXPECT_EQ(run.r.cycling(t), Result::wait);
    EXPECT_EQ(run.r.timing(t), Result::wait);
    EXPECT_EQ(run.r.periods(t), Result::wait);
    EXPECT_EQ(run.r.stable(), Result::wait);
    EXPECT_STREQ(run.r.state(), "waiting");
    Json j = json(run.r);
    for (const cJSON* c = j->child; c; c = c->next)
        if (cJSON_IsObject(c)) { EXPECT_NE(result(j.get(), c->string), "fail") << c->string; }
}

TEST(TakeoverReadiness, TheJsonStaysWithinTheTelemetryBudget) {
    ScopedTz tz(ScopedTz::amsterdam);
    TakeoverReadiness::Stored worst;
    for (auto& d : worst.days) {
        d.day = 99999; d.requestS = 86400;
        d.thermostatPeriods = d.e32Periods = d.events = d.matched = d.close = d.near = d.over = 65535;
        d.setbacks = d.warmups = d.quiet = d.flowMaxC = 255; d.flags = 3;
    }
    worst.stableS = 4294967295u;
    for (bool thermostat : {true, false}) {
        if (!thermostat) { for (auto& d : worst.days) d.flags = 2; }
        TakeoverReadiness r; r.restore(&worst, Restart::unexpected);
        TakeoverReadiness::Inputs in; in.roomCount = 8; in.boilerHeardAtMs = 0; in.limitRead = true; in.boilerLimitC = 255;
        for (auto& room : in.rooms) room = {RoomDemand::Status::fallback, int16_t(2000), 4};
        r.sample(uint64_t(4294967) * 1000, in);
        Json j = json(r);
        ASSERT_TRUE(j);
        char* text = cJSON_PrintUnformatted(j.get());
        EXPECT_LE(std::strlen(text), heating::control::telemetrySoftBytes - 20) << text; // + "schema":1
        cJSON_free(text);
    }
}
}
