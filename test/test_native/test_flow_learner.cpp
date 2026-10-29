#include "control/WarmupPlanner.h"
#include <functional>
#include <gtest/gtest.h>
#include <memory>

namespace {
using heating::control::FlowLearner;
using heating::control::RoomPlan;
using heating::control::RoomSchedule;
using heating::control::ShadowComparison;
using heating::control::WarmupPlanner;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;

// A synthetic house: room rate = a (flow - room) - b (room - outdoor) degC/h while
// heated; after heating a floor keeps giving heat (slab, 1.5 h), radiators 12 min.
// Floor: a 0.035, b 0.02 -> ~0.2 degC/h at 35 degC flow; radiator a 0.1, b 0.05.
struct House {
    struct Room { double a, b, capacity, coastHours, T = 20, coast = 0; };
    std::vector<Room> rooms;
    double outdoor = 5, gasScale = 1, gasKwh = 0;
    bool outdoorKnown = false, hotWaterKnown = true;
    uint64_t now = 0;
    // Per sample: edit the room input; false drops the sample (a gap).
    std::function<bool(uint64_t, size_t, FlowLearner::RoomInput&)> hook;
    FlowLearner learner;

    static House floor() { House h; h.rooms.push_back({0.035, 0.02, 10, 1.5}); h.plan(RoomPlan::Emitter::floor); return h; }
    static House radiator() { House h; h.rooms.push_back({0.1, 0.05, 3, 0.2}); h.plan(RoomPlan::Emitter::radiator); return h; }
    void plan(RoomPlan::Emitter e) {
        RoomPlan p; p.rooms.resize(1); p.rooms[0].id = "woonkamer"; p.rooms[0].emitter = e;
        learner.setPlan(p);
    }
    void run(uint64_t ms, std::optional<double> flowC, bool hotWater = false) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            const double dt = 10.0 / 3600;
            const bool heat = flowC && !hotWater;
            double heatKw = 0;
            for (auto& r : rooms) {
                const double emit = heat ? r.a * (*flowC - r.T) : 0;
                if (heat) r.coast = emit; else r.coast *= std::exp(-dt / r.coastHours);
                r.T += (heat ? emit : r.coast) * dt - r.b * (r.T - outdoor) * dt;
                heatKw += r.capacity * emit;
            }
            FlowLearner::Boiler b;
            const double flow = hotWater ? 65 : heat ? *flowC + ((now / (5 * minute)) % 2 ? 1 : -1) : rooms[0].T + 3;
            b.flowCentiC = int16_t(std::lround(flow * 100));
            b.returnCentiC = int16_t(std::lround((flow - 5) * 100));
            b.burnerOn = heat || hotWater;
            b.requestedFlowC = flowC ? uint8_t(*flowC) : uint8_t(0);
            if (hotWaterKnown) b.hotWater = hotWater;
            if (outdoorKnown) b.outdoorCentiC = int16_t(std::lround(outdoor * 100));
            const double gasKw = hotWater ? 22 : heatKw / FlowLearner::efficiency(flow - 5);
            b.modulationPct = uint8_t(std::clamp(std::lround(gasKw / 22 * 100 / gasScale), 0L, 100L));
            gasKwh += *b.modulationPct / 100.0 * 22 * gasScale * dt;
            std::vector<FlowLearner::RoomInput> in(rooms.size());
            bool keep = true;
            for (size_t i = 0; i < rooms.size(); ++i) {
                in[i].temperatureCentiC = int16_t(std::lround(rooms[i].T * 10) * 10); // 0.1 degC like the tado
                in[i].setpointCentiC = 2100; in[i].source = 0;
                if (hook) keep = hook(now, i, in[i]) && keep;
            }
            if (keep) learner.sample(now, b, in.data(), in.size());
        }
    }
    // tado-like days: heat at each flow for 3.5 h, then 8 h off, room back at 20.
    void days(std::initializer_list<double> flows, int cycles, std::initializer_list<double> outdoors = {5}) {
        for (int c = 0; c < cycles; ++c)
            for (const double o : outdoors)
                for (const double f : flows) {
                    outdoor = o;
                    for (auto& r : rooms) r.T = 20;
                    run(210 * minute, f);
                    run(8 * hour, std::nullopt);
                }
    }
};
const std::initializer_list<double> tadoFlows{32, 36, 40, 44, 48, 52};

TEST(FlowLearner, FloorLearnsTheLowestSufficientFlow) {
    auto h = House::floor();
    h.days(tadoFlows, 1);
    EXPECT_STREQ(h.learner.readiness(0), "learning");  // one pass: every bin from one period only
    EXPECT_FALSE(h.learner.advise(0, 100, std::nullopt).flowC);
    h.days(tadoFlows, 2);
    ASSERT_STREQ(h.learner.readiness(0), "ready");
    // Floor rate at 35 degC lies in the owner's 0.2..0.5 degC/h.
    const auto slow = h.learner.rate(0, 36, std::nullopt);
    ASSERT_TRUE(slow);
    EXPECT_GT(*slow, 0.15f); EXPECT_LT(*slow, 0.5f);
    // Hold: the lowest learned flow already keeps the room warm.
    const auto hold = h.learner.advise(0, 0, std::nullopt);
    EXPECT_STREQ(hold.reason, "lowest_learned");
    EXPECT_LE(*hold.flowC, 33);
    // 0.5 degC in 1.5 h (0.33 degC/h) and 1 degC in 2 h (0.5 degC/h): true flow 39 and 44 degC.
    const auto half = h.learner.advise(0, 50, std::nullopt), one = h.learner.advise(0, 100, std::nullopt);
    EXPECT_STREQ(one.reason, "learned");
    EXPECT_GE(*half.flowC, 37); EXPECT_LE(*half.flowC, 42);
    EXPECT_GE(*one.flowC, 42); EXPECT_LE(*one.flowC, 48);
    EXPECT_LE(*one.warmupS, 2 * 3600u + 60);
    // FlowDemand's rule (30 + 10 x shortfall) is too slow for this floor.
    EXPECT_EQ(one.ruleFlowC, 40);
    EXPECT_STREQ(one.rule, "lower_too_slow");
    EXPECT_GT(*one.ruleWarmupS, *one.warmupS);
}

TEST(FlowLearner, RadiatorWarmsFasterThanTheFloor) {
    auto floor = House::floor(), radiator = House::radiator();
    floor.days(tadoFlows, 3); radiator.days(tadoFlows, 3);
    ASSERT_STREQ(radiator.learner.readiness(0), "ready");
    EXPECT_GT(*radiator.learner.rate(0, 40, std::nullopt), 2 * *floor.learner.rate(0, 40, std::nullopt));
    // 1 degC in 1 h needs ~38 degC from the radiator, the floor ~44 degC for 1 degC in 2 h.
    const auto r = radiator.learner.advise(0, 100, std::nullopt);
    EXPECT_GE(*r.flowC, 36); EXPECT_LE(*r.flowC, 41);
    EXPECT_LT(*r.flowC, *floor.learner.advise(0, 100, std::nullopt).flowC);
    EXPECT_LE(*r.warmupS, 3600u + 60);
}

TEST(FlowLearner, UnreachableShortfallRecommendsTheMaximum) {
    auto h = House::floor();
    h.days(tadoFlows, 3);
    ASSERT_TRUE(h.learner.setAcceptance(0, {0, 30}));     // 2 degC/h: no floor does that
    auto a = h.learner.advise(0, 100, std::nullopt);
    EXPECT_EQ(*a.flowC, 60); EXPECT_STREQ(a.reason, "above_learned_range");
    auto full = House::floor();
    full.days({36, 46, 59}, 3);
    ASSERT_TRUE(full.learner.setAcceptance(0, {0, 30}));
    a = full.learner.advise(0, 100, std::nullopt);
    EXPECT_EQ(*a.flowC, 60); EXPECT_STREQ(a.reason, "not_reachable_in_time");
    EXPECT_GT(*a.warmupS, 3600u);                          // the time it would really take
    EXPECT_FALSE(h.learner.setAcceptance(0, {0, 5}));      // invalid acceptance is refused
}

TEST(FlowLearner, HotWaterIsNotLearned) {
    auto clean = House::floor(), mixed = House::floor();
    clean.days(tadoFlows, 3);
    // Every heating period: 20 min hot water in the middle (65 degC flow, no room heat).
    for (int c = 0; c < 3; ++c)
        for (const double f : tadoFlows) {
            mixed.rooms[0].T = 20;
            mixed.run(95 * minute, f); mixed.run(20 * minute, f, true); mixed.run(95 * minute, f);
            mixed.run(8 * hour, std::nullopt);
        }
    ASSERT_STREQ(mixed.learner.readiness(0), "ready");
    Json root(mixed.learner.json(), cJSON_Delete);
    for (const cJSON* p = cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root.get(), "rooms"), 0), "curve")->child; p; p = p->next)
        EXPECT_LT(cJSON_GetObjectItem(p, "flow_c")->valuedouble, 54);
    EXPECT_NEAR(*mixed.learner.advise(0, 100, std::nullopt).flowC, *clean.learner.advise(0, 100, std::nullopt).flowC, 2);
    // Without a known hot-water state nothing is learned.
    auto unknown = House::floor();
    unknown.hotWaterKnown = false;
    unknown.days(tadoFlows, 1);
    EXPECT_STREQ(unknown.learner.readiness(0), "collecting");
}

TEST(FlowLearner, StaleDataGapsAndSourceSwitchesEndSegments) {
    // 70 min periods: after settling 60 min, split by 15 min stale room data -> nothing.
    auto stale = House::floor();
    uint64_t start = 0;
    stale.hook = [&](uint64_t now, size_t, FlowLearner::RoomInput& in) {
        if (now >= start + 35 * minute && now < start + 50 * minute) in.temperatureCentiC.reset();
        return true;
    };
    for (int c = 0; c < 6; ++c) { start = stale.now; stale.rooms[0].T = 20; stale.run(70 * minute, 40); stale.run(11 * hour, std::nullopt); }
    EXPECT_EQ(stale.learner.segments(0), 0);
    // The same with 2 minutes without any sample.
    auto gap = House::floor();
    gap.hook = [&](uint64_t now, size_t, FlowLearner::RoomInput&) { return !(now >= start + 40 * minute && now < start + 42 * minute); };
    for (int c = 0; c < 6; ++c) { start = gap.now; gap.rooms[0].T = 20; gap.run(70 * minute, 40); gap.run(11 * hour, std::nullopt); }
    EXPECT_EQ(gap.learner.segments(0), 0);
    // Tado and Bluetooth differ by 0.7 degC: a switch ends the segment, no false rate.
    auto clean = House::floor(), switching = House::floor();
    clean.days(tadoFlows, 3);
    switching.hook = [](uint64_t now, size_t, FlowLearner::RoomInput& in) {
        if ((now / (100 * minute)) % 2) { in.source = 1; *in.temperatureCentiC -= 70; }
        return true;
    };
    switching.days(tadoFlows, 4);
    ASSERT_TRUE(switching.learner.rate(0, 44, std::nullopt));
    EXPECT_EQ(switching.learner.heatModel(0).coolSegments, 0); // no outdoor: no cooling either
    EXPECT_NEAR(*switching.learner.rate(0, 44, std::nullopt), *clean.learner.rate(0, 44, std::nullopt), 0.05);
}

TEST(FlowLearner, OutdoorShiftsTheRecommendationAndCoolingGivesTheHeatLoss) {
    auto h = House::floor();
    h.outdoorKnown = true;
    h.days(tadoFlows, 3, {0, 10});
    ASSERT_STREQ(h.learner.readiness(0), "ready");
    ASSERT_TRUE(h.learner.outdoorSlope(0));
    EXPECT_NEAR(*h.learner.outdoorSlope(0), 0.02, 0.01);  // = b: warmer outside, faster rise
    const auto cold = h.learner.advise(0, 100, int16_t(0)), mild = h.learner.advise(0, 100, int16_t(1000));
    EXPECT_GE(*cold.flowC, *mild.flowC + 3);              // true: 47 vs 41 degC
    const auto m = h.learner.heatModel(0);
    ASSERT_TRUE(m.lossPerHour); ASSERT_TRUE(m.capacityKwhPerK);
    EXPECT_NEAR(*m.lossPerHour, 0.02, 0.004);
    EXPECT_NEAR(*m.capacityKwhPerK, 10, 1.5);
    EXPECT_NEAR(*m.uaKwPerK, 0.2, 0.05);
    // Without outdoor there is no heat-loss model.
    auto blind = House::floor();
    blind.days(tadoFlows, 3);
    EXPECT_FALSE(blind.learner.heatModel(0).lossPerHour);
}

TEST(FlowLearner, GasMeterCalibratesTheBurnerEstimate) {
    auto h = House::floor();
    h.outdoorKnown = true; h.gasScale = 1.1;              // the boiler burns 10 % more than modulation x 22 kW
    for (int c = 0; c < 3; ++c)
        for (const double o : {0.0, 10.0})
            for (const double f : tadoFlows) {
                h.outdoor = o; h.rooms[0].T = 20;
                for (int k = 0; k < 4; ++k) { h.learner.gasMeter(h.gasKwh / 9.77, h.now); h.run(hour, f); }
                h.run(10 * minute, f, true);              // hot water: this interval does not count
                h.learner.gasMeter(h.gasKwh / 9.77, h.now);
                h.run(8 * hour, std::nullopt);
            }
    EXPECT_GE(h.learner.gasIntervals(), 3);
    EXPECT_NEAR(h.learner.calibration(), 1.1, 0.03);
    EXPECT_NEAR(*h.learner.heatModel(0).capacityKwhPerK, 10, 1.5); // real kWh, not modulation units
}

// 2026-10-28 (Wednesday) 23:00 CET = 22:00 UTC; program 06:30 -> 21 degC, 22:30 -> 18.5 degC.
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;
RoomSchedule program() {
    RoomSchedule s;
    for (auto& d : s.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
    return s;
}

TEST(WarmupPlanner, DefaultLeadWhileNotLearned) {
    auto h = House::floor();
    const auto s = WarmupPlanner::optimumStart(h.learner, 0, program(), wednesday23, int16_t(1900), std::nullopt);
    ASSERT_STREQ(s.reason, "planned");
    EXPECT_EQ(s.rise.atUtc, wednesday23 + 7 * 3600 + 30 * 60); // Thursday 06:30 local
    EXPECT_EQ(s.rise.toCentiC, 2100); EXPECT_EQ(s.rise.fromCentiC, 1850);
    EXPECT_STREQ(s.confidence, "default");
    EXPECT_EQ(s.leadS, 5 * 3600u);                         // 2.5 degC x 2 h
    EXPECT_EQ(s.startUtc, s.rise.atUtc - 5 * 3600);
    EXPECT_FALSE(s.startNow);
    EXPECT_STREQ(WarmupPlanner::optimumStart(h.learner, 0, RoomSchedule{}, wednesday23, int16_t(1900), std::nullopt).reason, "no_schedule");
}

TEST(WarmupPlanner, LearnedFloorStartsEarlyEnoughAtTheLowestFlow) {
    auto h = House::floor();
    h.outdoorKnown = true;
    h.days(tadoFlows, 3, {0, 10});
    const int16_t outdoor = 500;
    // Evening 20.5 degC: the slow floor cools towards 18.5 but not all the way.
    const auto s = WarmupPlanner::optimumStart(h.learner, 0, program(), wednesday23, int16_t(2050), outdoor);
    ASSERT_STREQ(s.confidence, "learned");
    EXPECT_TRUE(s.reachable);
    EXPECT_GT(s.startTemperatureCentiC, 1850); EXPECT_LT(s.startTemperatureCentiC, 2050);
    const int16_t shortfall = int16_t(2100 - s.startTemperatureCentiC);
    EXPECT_EQ(s.flowC, *h.learner.advise(0, shortfall, outdoor).flowC);
    const auto need = *h.learner.warmupSeconds(0, shortfall, s.flowC, outdoor);
    EXPECT_GE(s.leadS, need); EXPECT_LT(s.leadS, need + 300);  // the shortest 5-minute lead that covers it
    EXPECT_GT(s.leadS, 2 * 3600u); EXPECT_LE(s.leadS, WarmupPlanner::maxLeadS);
    // The active mode would raise the setpoint from predicted_start on.
    EXPECT_TRUE(WarmupPlanner::optimumStart(h.learner, 0, program(), s.startUtc + 60, s.startTemperatureCentiC, outdoor).startNow);
    EXPECT_FALSE(WarmupPlanner::optimumStart(h.learner, 0, program(), s.startUtc - 1800, s.startTemperatureCentiC, outdoor).startNow);
}

TEST(WarmupPlanner, NightEconomicsComparesStrategies) {
    auto h = House::floor();
    h.outdoorKnown = true;
    h.days(tadoFlows, 3, {0, 10});
    h.learner.gasPrice(1.35f);
    EXPECT_STREQ(WarmupPlanner::night(h.learner, 0, program(), wednesday23, int16_t(2050), std::nullopt).reason, "outdoor_unknown");
    const auto n = WarmupPlanner::night(h.learner, 0, program(), wednesday23, int16_t(2050), int16_t(500));
    ASSERT_STREQ(n.reason, "estimated");
    ASSERT_EQ(n.count, 4);
    EXPECT_STREQ(n.confidence, "low");                     // no gas meter yet
    const auto& programmed = n.strategies[0];
    EXPECT_STREQ(programmed.name, "program");
    EXPECT_TRUE(programmed.onTime);
    // 4.5 h night + 6 h day at ~0.2 kW/K x 16 K: ~35..60 kWh gas.
    EXPECT_GT(programmed.kwh, 30); EXPECT_LT(programmed.kwh, 70);
    EXPECT_NEAR(programmed.m3, programmed.kwh / 9.77, 1e-3);
    EXPECT_NEAR(*programmed.eur, programmed.m3 * 1.35, 1e-3);
    // The slow floor never cools below ~19.3 degC before its start: the variants cost about the same.
    for (uint8_t i = 1; i < n.count; ++i) EXPECT_NEAR(n.strategies[i].kwh, programmed.kwh, 0.05 * programmed.kwh);
    EXPECT_FALSE(n.strategies[3].onTime);                  // tado-like start at 06:30 is late
    EXPECT_LT(n.strategies[3].endCentiC, 1900);
    EXPECT_STREQ(n.strategies[n.best].name, "program");    // no significant saving
    EXPECT_EQ(n.savingM3, 0);
    // From 20:00 on a -5 degC night: every optimum start is on time (21.0 at 06:30).
    // Holding 19.5 at a low flow is slightly cheaper (efficiency), but under 2 %: the program stays.
    const auto cold = WarmupPlanner::night(h.learner, 0, program(), wednesday23 - 3 * 3600, int16_t(2050), int16_t(-500));
    ASSERT_STREQ(cold.reason, "estimated");
    for (uint8_t i = 0; i < 3; ++i) EXPECT_GE(cold.strategies[i].endCentiC, 2090);
    EXPECT_LT(cold.strategies[2].kwh, cold.strategies[0].kwh);
    EXPECT_STREQ(cold.strategies[cold.best].name, "program");
}

TEST(FlowLearner, JsonReportsReadinessCurveAndAdvice) {
    auto h = House::floor();
    h.outdoorKnown = true;
    h.days(tadoFlows, 3, {0, 10});
    Json root(h.learner.json(), cJSON_Delete);
    ASSERT_TRUE(root);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(root.get(), "applied")));
    const cJSON* room = cJSON_GetArrayItem(cJSON_GetObjectItem(root.get(), "rooms"), 0);
    EXPECT_STREQ(cJSON_GetObjectItem(room, "readiness")->valuestring, "ready");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(room, "curve")), 6);
    const cJSON* advice = cJSON_GetObjectItem(room, "advice");
    ASSERT_EQ(cJSON_GetArraySize(advice), 4);
    const cJSON* one = cJSON_GetArrayItem(advice, 2);
    EXPECT_EQ(cJSON_GetObjectItem(one, "shortfall_c")->valuedouble, 1);
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(one, "flow_c")));
    EXPECT_STREQ(cJSON_GetObjectItem(one, "rule")->valuestring, "lower_too_slow");
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(room, "loss_per_h")));
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(room, "now")));
    RoomPlan plan; plan.rooms.resize(1); plan.rooms[0].id = "woonkamer"; plan.rooms[0].emitter = RoomPlan::Emitter::floor;
    plan.rooms[0].schedule = program();
    const std::optional<int16_t> temperatures[1]{int16_t(2050)};
    Json planned(WarmupPlanner::json(h.learner, plan, wednesday23, temperatures, int16_t(500)), cJSON_Delete);
    const cJSON* p = cJSON_GetArrayItem(cJSON_GetObjectItem(planned.get(), "rooms"), 0);
    const cJSON* start = cJSON_GetObjectItem(p, "optimum_start");
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(start, "next_switch"), "time")->valuestring, "thu 06:30");
    EXPECT_TRUE(cJSON_IsString(cJSON_GetObjectItem(start, "predicted_start")));
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(p, "night"), "reason")->valuestring, "estimated");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(cJSON_GetObjectItem(p, "night"), "strategies")), 4);
}
}
