#include "control/FreeHeat.h"
#include "control/LearnedState.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cmath>
#include <memory>
#include <string>

// rc.5 (P3): free heat. Sun, cooking and people warm a room without the boiler; per room and
// local daypart (six of 4 h) the rise without heat (from the emitter's coast time on) joins an
// average with its count, and from 5 windows Smart warm-up starts that much later, never below
// half the lead. Kept over restarts as LearnedState frame 'F' (rooms by id, at most 3 dayparts).
namespace {
using heating::control::FreeHeat;
using heating::control::LearnedState;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::ShadowComparison;
using heating::control::WarmupPlanner;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000;
// Thursday 29 Oct 2026, 00:00 CET (UTC+1): local midnight of the first test day.
const int64_t day0 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 29)) * 86400 - 3600;
constexpr int64_t daySeconds = 86400;

RoomPlan plan(std::initializer_list<const char*> ids = {"woonkamer"}, RoomPlan::Emitter e = RoomPlan::Emitter::radiator) {
    RoomPlan p;
    for (const char* id : ids) { RoomPlan::Room r; r.id = r.name = id; r.emitter = e; r.state = RoomDemand::State::active; p.rooms.push_back(r); }
    return p;
}
std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}
std::string json(const FreeHeat& f, size_t room) {
    Json o(cJSON_CreateObject(), cJSON_Delete);
    EXPECT_TRUE(f.addJson(o.get(), room));
    return print(o.get());
}
// A room reading that rises (or falls) linearly from `at`, to 0.1 degC like a sensor.
auto ramp(int64_t at, double startC, double kPerH) {
    return [=](int64_t u) -> std::optional<int16_t> { return int16_t(std::lround((startC + kPerH * double(u - at) / 3600.0) * 10) * 10); };
}
auto flat(double c) { return ramp(0, c, 0); }

// FreeHeat fed every 10 s of local time; the uptime clock runs on with every sample.
struct Feed {
    FreeHeat heat;
    uint64_t now = 0;
    size_t rooms = 1;
    explicit Feed(const RoomPlan& p, FreeHeat::Params params = {}) : heat(params), rooms(p.rooms.size()) { heat.setPlan(p); }
    // From `from` to `to` (local minutes after `day`'s midnight, `to` excluded): every room reads
    // `temperature(utc)`; heat delivered or not; the outdoor; with or without a trusted clock.
    template <class T> void run(int64_t day, int from, int to, T temperature, bool heated,
                                std::optional<int16_t> outdoor = int16_t(500), bool clock = true) {
        for (int64_t u = day + from * 60; u < day + to * 60; u += 10) {
            now += 10 * second;
            std::array<FreeHeat::RoomSample, RoomPlan::maxRooms> s{};
            for (size_t i = 0; i < rooms; ++i) s[i] = {temperature(u), heated};
            heat.sample(now, clock ? std::optional<int64_t>(u) : std::nullopt, outdoor, s.data(), rooms);
        }
    }
    // One judged window of `minutes` from local `start` (minutes) of `day` at `kPerH`: heat for
    // 40 min until the radiator's coast time before `start`, then none, then heat again.
    void window(int64_t day, int start, int minutes, double kPerH) {
        run(day, start - 70, start - 30, flat(20.0), true);
        run(day, start - 30, start + minutes, ramp(day + start * 60, 20.0, kPerH), false);
        run(day, start + minutes, start + minutes + 1, flat(20.0), true);
    }
};
}

// The afternoon sun: without heat (after the radiator's 30 min) the room rises 0.4 degC/h from
// 12:30 to 15:00; each afternoon is one window of the 12-16 daypart, counted from the fifth.
TEST(FreeHeat, ARiseWithoutHeatJoinsItsDaypart) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    for (int d = 0; d < 5; ++d) {
        const int64_t day = day0 + d * daySeconds;
        f.run(day, 10 * 60, 12 * 60, flat(20.0), true);
        f.run(day, 12 * 60, 15 * 60, ramp(day + 12 * 3600, 20.0, 0.4), false);
        f.run(day, 15 * 60, 15 * 60 + 10, flat(21.2), true);
        EXPECT_EQ(f.heat.count(0, 13), d + 1);
        if (d < 4) EXPECT_FALSE(f.heat.rateKPerH(0, 13)) << "counted from 5 windows";
    }
    ASSERT_TRUE(f.heat.rateKPerH(0, 13));
    EXPECT_NEAR(*f.heat.rateKPerH(0, 13), 0.4f, 1e-4) << "1.0 degC from 12:29:50 to 14:59:50";
    for (const int h : {12, 14, 15}) EXPECT_NEAR(*f.heat.rateKPerH(0, h), 0.4f, 1e-4) << "the daypart 12-16";
    for (const int h : {0, 4, 8, 16, 20}) { EXPECT_EQ(f.heat.count(0, h), 0) << h; EXPECT_FALSE(f.heat.rateKPerH(0, h)); }
    EXPECT_EQ(FreeHeat::daypart(13), 3); EXPECT_EQ(FreeHeat::daypart(0), 0); EXPECT_EQ(FreeHeat::daypart(23), 5);
}

// A night without heat cools the room: each window counts a zero, so nothing shortens there.
TEST(FreeHeat, FallsAndFlatWindowsCountAZero) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan({"woonkamer"}, RoomPlan::Emitter::floor));
    for (int d = 0; d < 5; ++d) {
        const int64_t day = day0 + d * daySeconds;
        f.run(day, 20 * 60, 22 * 60, flat(21.0), true);
        f.run(day, 22 * 60, 31 * 60, ramp(day + 22 * 3600, 21.0, -0.2), false); // until 07:00 the next day
        f.run(day, 31 * 60, 31 * 60 + 10, flat(19.2), true);
    }
    // The floor's 2 h: from midnight on; 00-04 and 04-07 are windows, 22-24 none.
    EXPECT_EQ(f.heat.count(0, 22), 0);
    EXPECT_EQ(f.heat.count(0, 2), 5); EXPECT_EQ(f.heat.count(0, 5), 5);
    EXPECT_FLOAT_EQ(*f.heat.rateKPerH(0, 2), 0.0f);
    EXPECT_FLOAT_EQ(*f.heat.rateKPerH(0, 5), 0.0f);
    EXPECT_EQ(f.heat.shortenLeadS(0, 5, 7200, 0.5f), 7200u) << "no free heat: the lead stays";
}

// Within the emitter's coast time the room still gets heat from it, and a window counts from 30 min.
TEST(FreeHeat, TheCoastTimeAndShortWindowsTeachNothing) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed radiator(plan());
    radiator.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    radiator.run(day0, 12 * 60, 12 * 60 + 50, ramp(day0 + 12 * 3600, 20.0, 1.0), false); // a window of 20 min
    radiator.run(day0, 12 * 60 + 50, 13 * 60, flat(20.8), true);
    EXPECT_EQ(radiator.heat.count(0, 12), 0);
    Feed floor(plan({"woonkamer"}, RoomPlan::Emitter::floor));
    floor.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    floor.run(day0, 12 * 60, 14 * 60 + 20, ramp(day0 + 12 * 3600, 20.0, 1.0), false); // 2 h coast: 20 min left
    floor.run(day0, 14 * 60 + 20, 14 * 60 + 30, flat(22.3), true);
    EXPECT_EQ(floor.heat.count(0, 12), 0);
    floor.run(day0 + daySeconds, 11 * 60, 12 * 60, flat(20.0), true);
    floor.run(day0 + daySeconds, 12 * 60, 15 * 60, ramp(day0 + daySeconds + 12 * 3600, 20.0, 0.3), false); // 1 h after the coast
    floor.run(day0 + daySeconds, 15 * 60, 15 * 60 + 10, flat(20.9), true);
    EXPECT_EQ(floor.heat.count(0, 12), 1);
    EXPECT_EQ(floor.heat.params().floorCoastMs, heating::control::FlowLearner::Params{}.floorCoastMs);
    EXPECT_EQ(floor.heat.params().radiatorCoastMs, heating::control::FlowLearner::Params{}.radiatorCoastMs);
}

// Heat reaches the rooms when the burner heats or heating is asked; a hot-water round heats no room.
TEST(FreeHeat, HotWaterHeatsNoRoom) {
    EXPECT_TRUE(FreeHeat::heatDelivered(true, false, uint8_t(0)));
    EXPECT_FALSE(FreeHeat::heatDelivered(true, true, uint8_t(0))) << "the burner serves the store or a tap";
    EXPECT_TRUE(FreeHeat::heatDelivered(true, true, uint8_t(45))) << "heating is asked: it resumes after the hot water";
    EXPECT_FALSE(FreeHeat::heatDelivered(false, false, uint8_t(19))) << "below 20 degC the 0x1A asks no heat";
    EXPECT_TRUE(FreeHeat::heatDelivered(false, false, uint8_t(20)));
    EXPECT_FALSE(FreeHeat::heatDelivered(false, false, std::nullopt));
    EXPECT_TRUE(FreeHeat::heatDelivered(std::nullopt, std::nullopt, std::nullopt)) << "unknown: the emitter may be warm";
    EXPECT_TRUE(FreeHeat::heatDelivered(true, std::nullopt, std::nullopt));
    EXPECT_FALSE(FreeHeat::heatDelivered(std::nullopt, true, std::nullopt));
    // A keep-warm round in the middle of the afternoon leaves the window running.
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    f.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    const auto rise = ramp(day0 + 12 * 3600, 20.0, 0.4);
    f.run(day0, 12 * 60, 13 * 60 + 30, rise, FreeHeat::heatDelivered(false, false, uint8_t(0)));
    f.run(day0, 13 * 60 + 30, 13 * 60 + 40, rise, FreeHeat::heatDelivered(true, true, uint8_t(0)));
    f.run(day0, 13 * 60 + 40, 15 * 60, rise, false);
    f.run(day0, 15 * 60, 15 * 60 + 10, flat(21.2), true);
    EXPECT_EQ(f.heat.count(0, 13), 1);
    for (int d = 1; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    EXPECT_NEAR(*f.heat.rateKPerH(0, 13), 0.4f, 0.01f);
}

// A jump of more than 0.3 degC between two samples is another source: the window ends there (the
// part before it is judged) and a new one begins; the jump is never counted as a rise. A missing
// reading ends a window too, and a silence of more than a minute restarts the coast wait.
TEST(FreeHeat, AStepAMissingReadingOrAGapEndsTheWindow) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    f.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    f.run(day0, 12 * 60, 13 * 60 + 30, flat(20.0), false);
    f.run(day0, 13 * 60 + 30, 15 * 60, flat(20.5), false);    // +0.5 degC at once
    f.run(day0, 15 * 60, 15 * 60 + 10, flat(20.5), true);
    EXPECT_EQ(f.heat.count(0, 13), 2) << "1 h before the step and 1.5 h after it";
    Feed g(plan());
    for (int d = 0; d < 5; ++d) {
        const int64_t day = day0 + d * daySeconds;
        g.run(day, 11 * 60, 12 * 60, flat(20.0), true);
        g.run(day, 12 * 60, 13 * 60 + 30, flat(20.0), false);
        g.run(day, 13 * 60 + 30, 15 * 60, flat(20.5), false);
        g.run(day, 15 * 60, 15 * 60 + 10, flat(20.5), true);
    }
    EXPECT_FLOAT_EQ(*g.heat.rateKPerH(0, 13), 0.0f) << "the step is not a rise";
    // A reading missing for a minute: the window before it is judged, a new one starts after it.
    Feed m(plan());
    m.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    m.run(day0, 12 * 60, 13 * 60 + 30, flat(20.0), false);
    m.run(day0, 13 * 60 + 30, 13 * 60 + 31, [](int64_t) { return std::optional<int16_t>(); }, false);
    m.run(day0, 13 * 60 + 31, 15 * 60, flat(20.0), false);
    m.run(day0, 15 * 60, 15 * 60 + 10, flat(20.0), true);
    EXPECT_EQ(m.heat.count(0, 13), 2);
    // A gap of 5 min at 12:40: the 10 min before it are too short, and the radiator's 30 min start
    // again; from 13:15 to 15:00 is one window.
    Feed gap(plan());
    gap.run(day0, 11 * 60, 12 * 60, flat(20.0), true);
    gap.run(day0, 12 * 60, 12 * 60 + 40, flat(20.0), false);
    gap.now += 5 * minute;
    gap.run(day0, 12 * 60 + 45, 13 * 60 + 14, flat(20.0), false);
    EXPECT_EQ(gap.heat.count(0, 13), 0);
    gap.run(day0, 13 * 60 + 14, 15 * 60, flat(20.0), false);
    gap.run(day0, 15 * 60, 15 * 60 + 10, flat(20.0), true);
    EXPECT_EQ(gap.heat.count(0, 13), 1);
}

// Warmer outside than inside: the outdoor warms the room, which says nothing about sun or people.
// Without a trusted clock there is no daypart: nothing is learned either.
TEST(FreeHeat, WarmerOutsideOrWithoutAClockNothingIsLearned) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    f.run(day0, 11 * 60, 12 * 60, flat(20.0), true, int16_t(2500));
    f.run(day0, 12 * 60, 15 * 60, ramp(day0 + 12 * 3600, 20.0, 0.4), false, int16_t(2500));
    f.run(day0, 15 * 60, 15 * 60 + 10, flat(21.2), true, int16_t(2500));
    EXPECT_EQ(f.heat.count(0, 13), 0);
    f.run(day0 + daySeconds, 11 * 60, 12 * 60, flat(20.0), true, std::nullopt);
    f.run(day0 + daySeconds, 12 * 60, 15 * 60, ramp(day0 + daySeconds + 12 * 3600, 20.0, 0.4), false, std::nullopt);
    f.run(day0 + daySeconds, 15 * 60, 15 * 60 + 10, flat(21.2), true, std::nullopt);
    EXPECT_EQ(f.heat.count(0, 13), 1) << "an unknown outdoor counts";
    Feed c(plan());
    c.run(day0, 11 * 60, 12 * 60, flat(20.0), true, int16_t(500), false);
    c.run(day0, 12 * 60, 15 * 60, ramp(day0 + 12 * 3600, 20.0, 0.4), false, int16_t(500), false);
    c.run(day0, 15 * 60, 15 * 60 + 10, flat(21.2), true, int16_t(500), false);
    for (int h = 0; h < 24; h += 4) EXPECT_EQ(c.heat.count(0, h), 0);
}

// The average: the first window sets it, each next one weighs 0.3; the count stops at 99; a rise
// faster than 3 degC/h counts as 3 (FlowLearner's limit: no emitter, a sensor in the sun).
TEST(FreeHeat, TheAverageItsCountAndItsLimit) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    f.window(day0, 12 * 60 + 30, 150, 0.4);
    for (int d = 1; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    EXPECT_NEAR(*f.heat.rateKPerH(0, 13), 0.4f, 0.01f);
    f.window(day0 + 5 * daySeconds, 12 * 60 + 30, 150, -0.1);   // a cloudy afternoon
    EXPECT_NEAR(*f.heat.rateKPerH(0, 13), 0.28f, 0.01f) << "0.4 + 0.3 x (0 - 0.4)";
    Feed s(plan());
    for (int d = 0; d < 5; ++d) s.window(day0 + d * daySeconds, 13 * 60, 40, 6.0);
    EXPECT_FLOAT_EQ(*s.heat.rateKPerH(0, 13), 3.0f);
    for (int d = 5; d < 110; ++d) s.window(day0 + d * daySeconds, 13 * 60, 40, 0.0);
    EXPECT_EQ(s.heat.count(0, 13), FreeHeat::maxCount);
    EXPECT_LT(*s.heat.rateKPerH(0, 13), 0.001f);
}

// lead x max(0.5, 1 - free / warm), up to whole minutes, never below half, only with 5 windows.
TEST(FreeHeat, ShortenLeadSFollowsTheRuleAndItsFloor) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    for (int d = 0; d < 4; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 3600, 1.0f), 3600u) << "4 windows: not yet";
    f.window(day0 + 4 * daySeconds, 12 * 60 + 30, 150, 0.4);
    const float free = *f.heat.rateKPerH(0, 13);
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 3600, 1.0f), (uint32_t(3600 * (1 - free / 1.0)) + 59) / 60 * 60);
    EXPECT_NEAR(double(f.heat.shortenLeadS(0, 13, 3600, 1.0f)), 2160, 60);
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 3600, 0.5f), 1800u) << "1 - 0.8 = 0.2: never below half";
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 3600, 0.1f), 1800u);
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 1010, 1.0f) % 60, 0u) << "whole minutes";
    EXPECT_GE(f.heat.shortenLeadS(0, 13, 1010, 0.1f), 505u);
    EXPECT_EQ(f.heat.shortenLeadS(0, 9, 3600, 1.0f), 3600u) << "another daypart";
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 3600, 0.0f), 3600u) << "no warm-up rate";
    EXPECT_EQ(f.heat.shortenLeadS(0, 13, 0, 1.0f), 0u);
    EXPECT_EQ(f.heat.shortenLeadS(1, 13, 3600, 1.0f), 3600u) << "no such room";
}

// FlowPolicy's step: the daypart is that of the middle of the planned lead (the warm-up, not the
// switch), the rate is the plan's own (shortfall / lead); once the shortened start has passed it
// starts at once, also when the planner calls the full lead too late already (not reachable).
TEST(FreeHeat, AStartMovesLaterByTheFreeHeatOfItsWarmUp) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    for (int d = 0; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    const float free = *f.heat.rateKPerH(0, 13);
    const int64_t day = day0 + 6 * daySeconds;
    WarmupPlanner::Start s;
    s.reason = "planned"; s.rise.atUtc = day + 16 * 3600; s.rise.toCentiC = 2100; s.startTemperatureCentiC = 2000;
    s.leadS = 3600; s.startUtc = s.rise.atUtc - 3600; s.reachable = true;
    const int64_t utc = s.rise.atUtc - 3000;
    s.startNow = true;                                            // 50 min before the switch: within the 1 h lead
    const auto saved = f.heat.shorten(0, utc, s);
    const uint32_t lead = (uint32_t(3600 * (1 - free)) + 59) / 60 * 60;
    EXPECT_EQ(s.leadS, lead);
    EXPECT_EQ(saved, 3600 - lead);
    EXPECT_EQ(s.startUtc, s.rise.atUtc - int64_t(lead));
    EXPECT_FALSE(s.startNow) << "it starts later now";
    EXPECT_EQ(f.heat.appliedMin(0), (3600 - lead + 30) / 60);
    // The switch at 17:00 with 4 h of lead: its warm-up (13-17) lies mostly in 12-16.
    WarmupPlanner::Start late = s;
    late.rise.atUtc = day + 17 * 3600; late.leadS = 4 * 3600; late.rise.toCentiC = 2400;
    EXPECT_GT(f.heat.shorten(0, utc, late, false), 0u);
    EXPECT_EQ(f.heat.appliedMin(0), (3600 - lead + 30) / 60) << "not recorded while a begun start holds";
    // The switch at 12:00: its warm-up lies in 8-12, without free heat.
    WarmupPlanner::Start morning = s;
    morning.rise.atUtc = day + 12 * 3600; morning.leadS = 3600;
    EXPECT_EQ(f.heat.shorten(0, utc, morning), 0u);
    EXPECT_EQ(morning.leadS, 3600u);
    EXPECT_EQ(f.heat.appliedMin(0), 0);
    // Between the full start and the shortened one the planner reports "not reachable" (the full
    // lead no longer fits): it still starts later; past the shortened start it starts at once.
    WarmupPlanner::Start between = s;
    between.leadS = 3600; between.startUtc = s.rise.atUtc - 3600; between.reachable = false; between.startNow = true;
    EXPECT_GT(f.heat.shorten(0, s.rise.atUtc - 3000, between), 0u);
    EXPECT_FALSE(between.startNow);
    WarmupPlanner::Start behind = between;
    behind.leadS = 3600; behind.startUtc = s.rise.atUtc - 3600; behind.startNow = true;
    f.heat.shorten(0, s.rise.atUtc - 1800, behind);
    EXPECT_TRUE(behind.startNow) << "past the shortened start too";
    EXPECT_GE(behind.leadS, 1800u);
    // No shortfall, or no planned rise: nothing moves.
    for (auto variant : {1, 2}) {
        WarmupPlanner::Start v = s;
        v.leadS = 3600;
        if (variant == 1) v.startTemperatureCentiC = 2100;
        if (variant == 2) v.reason = "no_rise_within_24h";
        EXPECT_EQ(f.heat.shorten(0, utc, v), 0u) << variant;
        EXPECT_EQ(v.leadS, 3600u);
    }
}

// "free_heat" per room: null until a window was judged; the rate (0.1 degC/h) from 5 windows, else
// null; the count of each daypart; the minutes the room's planned start moved. At most 88 B.
TEST(FreeHeat, TelemetryStaysSmall) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan());
    EXPECT_EQ(json(f.heat, 0), R"({"free_heat":null})");
    EXPECT_EQ(json(f.heat, 3), R"({"free_heat":null})");
    f.window(day0, 12 * 60 + 30, 150, 0.4);
    EXPECT_EQ(json(f.heat, 0), R"({"free_heat":{"rate":[null,null,null,null,null,null],"n":[0,0,0,1,0,0],"applied_min":0}})");
    for (int d = 1; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    EXPECT_EQ(json(f.heat, 0), R"({"free_heat":{"rate":[null,null,null,0.4,null,null],"n":[0,0,0,5,0,0],"applied_min":0}})");
    // The widest: six dayparts at 1.3 degC/h (3 characters), 99 windows each and a start moved by
    // 240 min (half of the planner's 8 h). The sawtooth restarts at every daypart.
    Feed w(plan());
    for (int64_t u = day0; u < day0 + 100 * daySeconds; u += 10) {
        w.now += 10 * second;
        const int64_t local = (u - day0) % (4 * 3600);
        FreeHeat::RoomSample s{int16_t(std::lround((20.0 + 1.3 * local / 3600.0) * 10) * 10), false};
        w.heat.sample(w.now, u, int16_t(500), &s, 1);
    }
    WarmupPlanner::Start s;
    s.reason = "planned"; s.rise.atUtc = day0 + 101 * daySeconds + 16 * 3600; s.rise.toCentiC = 2400; s.startTemperatureCentiC = 2000;
    s.leadS = WarmupPlanner::maxLeadS; s.reachable = true;
    w.heat.shorten(0, s.rise.atUtc - WarmupPlanner::maxLeadS, s);
    const auto widest = json(w.heat, 0);
    EXPECT_EQ(widest, R"({"free_heat":{"rate":[1.3,1.3,1.3,1.3,1.3,1.3],"n":[99,99,99,99,99,99],"applied_min":240}})");
    EXPECT_EQ(widest.size() - 2, 88u) << "the member alone";
    EXPECT_LE(widest.size() - 2, 90u);
}

// Frame 'F': per room with evidence its id and at most 3 dayparts, those that shorten a warm-up
// first (counted and the highest rate), then the busiest; back into the plan rooms by id.
TEST(FreeHeat, StoredAndRestoredByRoomId) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan({"woonkamer", "keuken", "zolder"}));
    EXPECT_EQ(f.heat.stored(), "") << "nothing judged: no frame";
    int64_t day = day0;
    const auto days = [&](int n, int start, int minutes, double k) { for (int d = 0; d < n; ++d, day += daySeconds) f.window(day, start, minutes, k); };
    days(5, 12 * 60 + 30, 150, 0.4);   // 12-16: 0.4, counted
    days(6, 16 * 60 + 40, 120, 0.2);   // 16-20: 0.2, counted
    days(2, 8 * 60 + 40, 120, 0.5);    // 8-12: 0.5, not counted yet
    days(9, 40, 120, 0.0);             // 0-4: zero, the busiest
    days(7, 4 * 60 + 40, 120, -0.2);   // 4-8: zero
    days(8, 20 * 60 + 40, 120, 0.0);   // 20-24: zero
    const auto body = f.heat.stored();
    // 3 rooms (all three had the same windows), each: id, mask, 3 x (n, rate).
    ASSERT_EQ(body.size(), 1u + (1 + 9 + 1 + 9) + (1 + 6 + 1 + 9) + (1 + 6 + 1 + 9));
    EXPECT_EQ(uint8_t(body[0]), 3);
    EXPECT_EQ(uint8_t(body[1 + 1 + 9]), (1u << 0) | (1u << 3) | (1u << 4)) << "12-16 and 16-20 (counted), then 0-4 (the busiest)";
    // Into another plan: the rooms swapped, one gone, one new.
    FreeHeat back;
    ASSERT_TRUE(back.restore(body, plan({"keuken", "badkamer", "woonkamer"})));
    for (const size_t i : {size_t(0), size_t(2)}) {
        EXPECT_NEAR(*back.rateKPerH(i, 13), *f.heat.rateKPerH(0, 13), 0.001f);
        EXPECT_NEAR(*back.rateKPerH(i, 17), *f.heat.rateKPerH(0, 17), 0.001f);
        EXPECT_EQ(back.count(i, 13), 5); EXPECT_EQ(back.count(i, 17), 6); EXPECT_EQ(back.count(i, 2), 9);
        EXPECT_EQ(back.count(i, 9), 0); EXPECT_EQ(back.count(i, 5), 0); EXPECT_EQ(back.count(i, 21), 0) << "not stored";
    }
    for (int h = 0; h < 24; h += 4) EXPECT_EQ(back.count(1, h), 0) << "a new room starts empty";
    EXPECT_EQ(back.shortenLeadS(2, 13, 3600, 1.0f), f.heat.shortenLeadS(0, 13, 3600, 1.0f));
    // The widest payload: 8 rooms with 32-character ids, each 3 dayparts.
    RoomPlan eight;
    for (int i = 0; i < 8; ++i) { RoomPlan::Room r; r.id = std::string(32, char('a' + i)); eight.rooms.push_back(r); }
    Feed all(eight);
    for (int d = 0; d < 4; ++d) for (const int start : {40, 4 * 60 + 40, 8 * 60 + 40, 12 * 60 + 40}) all.window(day0 + d * daySeconds, start, 120, 0.3);
    EXPECT_EQ(all.heat.stored().size(), FreeHeat::maxStoredBytes);
    EXPECT_EQ(LearnedState::freeHeatFrame(heating::control::FlowPolicy{}), "") << "a policy without free heat writes no frame";
}

// A payload that is not one is refused whole: nothing is applied.
TEST(FreeHeat, AnInvalidPayloadIsIgnoredWhole) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan({"woonkamer", "keuken"}));
    for (int d = 0; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    const auto good = f.heat.stored();
    ASSERT_FALSE(good.empty());
    FreeHeat t; t.setPlan(plan({"woonkamer", "keuken"}));
    ASSERT_TRUE(t.restore(good));
    const auto before = t.stored();
    const std::string room = std::string("\x09woonkamer") + char(1 << 3) + char(5) + char(0x90) + char(0x01); // n 5, 0.400 degC/h
    const std::vector<std::pair<const char*, std::string>> bad = {
        {"empty", ""}, {"no rooms", std::string(1, '\0')}, {"nine rooms", std::string(1, '\x09') + room},
        {"truncated", good.substr(0, good.size() - 1)}, {"a byte too many", good + '\0'},
        {"id of 0", std::string("\x01\x00", 2) + char(8) + "\x05\x90\x01"}, {"id of 33", "\x01\x21" + std::string(33, 'a') + char(8) + "\x05\x90\x01"},
        {"mask 0", std::string("\x01\x09woonkamer") + char(0)}, {"mask beyond 6", std::string("\x01\x09woonkamer") + char(0x40) + "\x05\x90\x01"},
        {"4 dayparts", std::string("\x01\x09woonkamer") + char(0x0F) + std::string("\x05\x90\x01", 3) + std::string("\x05\x90\x01", 3) + std::string("\x05\x90\x01", 3) + std::string("\x05\x90\x01", 3)},
        {"n 0", std::string("\x01\x09woonkamer") + char(8) + std::string("\x00\x90\x01", 3)},
        {"n 100", std::string("\x01\x09woonkamer") + char(8) + std::string("\x64\x90\x01", 3)},
        {"3.001 degC/h", std::string("\x01\x09woonkamer") + char(8) + std::string("\x05\xB9\x0B", 3)},
        {"a room twice", std::string(1, '\x02') + room + room},
    };
    for (const auto& [why, payload] : bad) {
        EXPECT_FALSE(FreeHeat::valid(payload)) << why;
        EXPECT_FALSE(t.restore(payload)) << why;
        EXPECT_EQ(t.stored(), before) << why << ": nothing applied";
    }
    EXPECT_TRUE(FreeHeat::valid(std::string(1, '\x01') + room));
    EXPECT_TRUE(FreeHeat::valid(std::string("\x01\x09woonkamer") + char(8) + std::string("\x05\xB8\x0B", 3))) << "3.000 degC/h";
    // An unknown room id is skipped; the frame is still valid.
    FreeHeat other; other.setPlan(plan({"zolder"}));
    EXPECT_TRUE(other.restore(good));
    EXPECT_EQ(other.stored(), "");
}

// A plan edit keeps each room's evidence by id, also when the emitter changed; a new room starts empty.
TEST(FreeHeat, APlanEditKeepsTheEvidenceById) {
    ScopedTz tz(ScopedTz::amsterdam);
    Feed f(plan({"woonkamer", "keuken"}));
    for (int d = 0; d < 5; ++d) f.window(day0 + d * daySeconds, 12 * 60 + 30, 150, 0.4);
    const float rate = *f.heat.rateKPerH(0, 13);
    auto edited = plan({"zolder", "keuken", "woonkamer"});
    edited.rooms[2].emitter = RoomPlan::Emitter::floor;
    f.heat.setPlan(edited);
    EXPECT_EQ(f.heat.rooms(), 3u);
    EXPECT_FALSE(f.heat.rateKPerH(0, 13));
    EXPECT_FLOAT_EQ(*f.heat.rateKPerH(1, 13), rate);
    EXPECT_FLOAT_EQ(*f.heat.rateKPerH(2, 13), rate);
    f.heat.setPlan(plan({"zolder"}));
    f.heat.setPlan(plan({"woonkamer"}));
    EXPECT_FALSE(f.heat.rateKPerH(0, 13)) << "a room that left the plan took its evidence with it";
}
