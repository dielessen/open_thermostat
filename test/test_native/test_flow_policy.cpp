#include "control/FlowPolicy.h"
#include "control/HeatingTelemetry.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <memory>

namespace {
using heating::control::FlowCompare;
using heating::control::LearnedContext;
using heating::control::heatingSummaryTelemetry;
using heating::control::FlowDemand;
using heating::control::FlowLearner;
using heating::control::FlowPolicy;
using heating::control::FlowSettings;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::RoomSchedule;
using heating::control::ShadowComparison;
using heating::control::WarmupPlanner;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;

Json parse(const char* text) { return Json(cJSON_Parse(text), cJSON_Delete); }
const cJSON* at(const cJSON* o, const char* key) { return cJSON_GetObjectItemCaseSensitive(o, key); }

RoomSchedule program() {
    RoomSchedule s;
    for (auto& d : s.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
    return s;
}
RoomPlan plan(RoomPlan::Emitter e = RoomPlan::Emitter::floor, bool schedule = false) {
    RoomPlan p; p.rooms.resize(1);
    p.rooms[0].id = "woonkamer"; p.rooms[0].emitter = e; p.rooms[0].state = RoomDemand::State::active;
    if (schedule) p.rooms[0].schedule = program();
    return p;
}
RoomDemand::Result room(int16_t temperature, int16_t setpoint) {
    RoomDemand::Result r;
    r.status = RoomDemand::Status::ok; r.source = 0; r.usable = true;
    r.temperature = temperature; r.setpoint = setpoint; r.errorCentiC = int16_t(setpoint - temperature);
    return r;
}

// The learner's synthetic floor (test_flow_learner.cpp): rate = a (flow - room) - b (room - outdoor).
struct House {
    double a = 0.035, b = 0.02, T = 20, coast = 0, outdoor = 5;
    uint64_t now = 0;
    FlowLearner learner;
    explicit House(const RoomPlan& p) { learner.setPlan(p); }
    void run(uint64_t ms, std::optional<double> flowC) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            const double dt = 10.0 / 3600;
            const double emit = flowC ? a * (*flowC - T) : 0;
            if (flowC) coast = emit; else coast *= std::exp(-dt / 1.5);
            T += (flowC ? emit : coast) * dt - b * (T - outdoor) * dt;
            FlowLearner::Boiler boiler;
            const double flow = flowC ? *flowC + ((now / (5 * minute)) % 2 ? 1 : -1) : T + 3;
            boiler.flowCentiC = int16_t(std::lround(flow * 100));
            boiler.returnCentiC = int16_t(std::lround((flow - 5) * 100));
            boiler.burnerOn = flowC.has_value();
            boiler.requestedFlowC = flowC ? uint8_t(*flowC) : uint8_t(0);
            boiler.hotWater = false;
            boiler.outdoorCentiC = int16_t(std::lround(outdoor * 100));
            boiler.modulationPct = uint8_t(flowC ? 30 : 0);
            FlowLearner::RoomInput in;
            in.temperatureCentiC = int16_t(std::lround(T * 10) * 10); in.setpointCentiC = 2100; in.source = 0;
            learner.sample(now, boiler, &in, 1);
        }
    }
    void learn() {
        for (int c = 0; c < 3; ++c)
            for (const double o : {0.0, 10.0})
                for (const double f : {32, 36, 40, 44, 48, 52}) { outdoor = o; T = 20; run(210 * minute, f); run(8 * hour, std::nullopt); }
        outdoor = 5;
    }
};

struct Step {
    FlowPolicy policy;
    FlowLearner learner;
    RoomPlan p = plan();
    std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
    FlowPolicy::Inputs in;
    Step() { learner.setPlan(p); rooms[0] = room(2000, 2100); in.plan = &p; in.rooms = rooms.data(); }
    FlowDemand::Request apply(FlowDemand::Request rule, const FlowLearner* l = nullptr) {
        in.now += 10 * second; in.rule = rule;
        return policy.apply(in, l ? *l : learner);
    }
};
const FlowDemand::Request heat40{true, 40, FlowDemand::Reason::heating};
const FlowDemand::Request idle{false, 0, FlowDemand::Reason::idle};

TEST(FlowSettings, ParsesPartialUpdatesStrictly) {
    FlowSettings s;
    EXPECT_EQ(s.json(), R"({"weather_curve":false,"apply_learned":false,"curve_design_flow_c":0})");
    EXPECT_LE(s.json().size(), FlowSettings::maxBytes);
    EXPECT_EQ(FlowSettings::parse(parse(R"({"weather_curve":true})").get(), s), nullptr);
    EXPECT_TRUE(s.weatherCurve); EXPECT_FALSE(s.applyLearned);
    EXPECT_EQ(FlowSettings::parse(parse(R"({"apply_learned":true,"curve_design_flow_c":45})").get(), s), nullptr);
    EXPECT_TRUE(s.weatherCurve); EXPECT_TRUE(s.applyLearned); EXPECT_EQ(s.designFlowC, 45);
    FlowSettings back;
    ASSERT_EQ(FlowSettings::parse(parse(s.json().c_str()).get(), back), nullptr);
    EXPECT_TRUE(back == s);
    const FlowSettings before = s;
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"weather_curve":1})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"curve_design_flow_c":24})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"curve_design_flow_c":81})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"curve_design_flow_c":40.5})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"weather_curve":false,"mode":"x"})").get(), s), "invalid_key");
    EXPECT_STREQ(FlowSettings::parse(parse("{}").get(), s), "invalid_request");
    EXPECT_STREQ(FlowSettings::parse(parse("[]").get(), s), "invalid_request");
    EXPECT_STREQ(FlowSettings::parse(nullptr, s), "invalid_request");
    EXPECT_TRUE(s == before);                  // a refused update changes nothing
    EXPECT_EQ(FlowSettings::parse(parse(R"({"curve_design_flow_c":0})").get(), s), nullptr);
    EXPECT_EQ(s.designFlowC, 0);
}

TEST(FlowPolicy, OptionsOffLeaveTheRuleAndAdvise) {
    Step s;
    s.in.outdoorCentiC = -1000;
    s.in.boilerLimitC = 35;                    // the guard caps what it sends; the rule passes unchanged
    for (const auto& rule : {heat40, idle, FlowDemand::Request{true, 33, FlowDemand::Reason::holdOn},
                             FlowDemand::Request{false, 0, FlowDemand::Reason::noDemand}}) {
        const auto out = s.apply(rule);
        EXPECT_EQ(out.heat, rule.heat); EXPECT_EQ(out.flowC, rule.flowC); EXPECT_EQ(out.reason, rule.reason);
        EXPECT_EQ(s.policy.source(), FlowPolicy::Source::rule);
    }
    s.in.boilerLimitC.reset();
    s.apply(heat40);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON* request = cJSON_AddObjectToObject(status.get(), "request");
    cJSON_AddBoolToObject(request, "heat", true); cJSON_AddNumberToObject(request, "flow_c", 40); cJSON_AddStringToObject(request, "reason", "heating");
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    const cJSON* flow = at(status.get(), "flow");
    EXPECT_STREQ(at(flow, "source")->valuestring, "rule");
    // Advice: floor curve at -10 degC for 21 degC (21 + 0.667 x 31 = 41.7 -> 42) + (40 - 30) / 2.
    EXPECT_STREQ(at(at(flow, "curve"), "state")->valuestring, "advice");
    EXPECT_EQ(at(at(flow, "curve"), "flow_c")->valuedouble, 47);
    EXPECT_EQ(at(at(flow, "curve"), "base_c")->valuedouble, 41.7);
    EXPECT_STREQ(at(at(flow, "curve"), "slope_source")->valuestring, "design");
    EXPECT_STREQ(at(at(flow, "learned"), "state")->valuestring, "not_ready");
    EXPECT_STREQ(at(at(flow, "learned"), "room")->valuestring, "woonkamer");
    EXPECT_STREQ(at(at(flow, "optimum_start"), "state")->valuestring, "no_clock");
    EXPECT_EQ(at(request, "flow_c")->valuedouble, 40);
    s.in.outdoorCentiC.reset(); s.apply(heat40);
    Json again(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(again.get(), false));
    EXPECT_STREQ(at(at(at(again.get(), "flow"), "curve"), "state")->valuestring, "no_outdoor");
}

TEST(FlowPolicy, WeatherCurveSetsTheFlowWithinAllBounds) {
    Step s;
    FlowSettings on; on.weatherCurve = true;
    s.policy.setSettings(on);
    s.rooms[0] = room(1980, 2000);
    const FlowDemand::Request small{true, 32, FlowDemand::Reason::heating}; // 0.2 degC short: 30 + 2
    s.in.outdoorCentiC = 1200;                 // mild: 20 + 0.667 x 8 = 25.3 -> the plan minimum
    auto out = s.apply(small);
    EXPECT_TRUE(out.heat); EXPECT_EQ(out.flowC, 30); EXPECT_EQ(s.policy.source(), FlowPolicy::Source::curve);
    EXPECT_LT(out.flowC, small.flowC);         // lower than the rule at mild weather
    s.in.outdoorCentiC = -1000;                // design point: 40 + (32 - 30) / 2
    EXPECT_EQ(s.apply(small).flowC, 41);
    EXPECT_EQ(s.apply(FlowDemand::Request{true, 60, FlowDemand::Reason::heating}).flowC, 55); // half the PI on top
    s.in.boilerLimitC = 45;                    // the boiler's own 0x16 limit caps it
    EXPECT_EQ(s.apply(FlowDemand::Request{true, 60, FlowDemand::Reason::heating}).flowC, 45);
    s.in.boilerLimitC = 25;                    // and wins over the plan minimum
    EXPECT_EQ(s.apply(small).flowC, 25);
    s.in.boilerLimitC.reset();
    s.p.maximumFlowC = 38;
    EXPECT_EQ(s.apply(small).flowC, 38);       // the plan maximum
    s.p.maximumFlowC = 60;
    s.in.outdoorCentiC = -3500;                // 20 + 0.667 x 55 = 56.7
    EXPECT_EQ(s.apply(small).flowC, 58);
    // Radiators on the circuit: the radiator design flow (55 at -10).
    s.p.rooms[0].emitter = RoomPlan::Emitter::radiator; s.in.outdoorCentiC = -1000;
    EXPECT_EQ(s.apply(small).flowC, 56);
    on.designFlowC = 35; s.policy.setSettings(on);
    EXPECT_EQ(s.apply(small).flowC, 36);       // the owner's own design flow
    // Whether to heat stays the rule's; without an outdoor the rule's flow returns.
    out = s.apply(idle);
    EXPECT_FALSE(out.heat); EXPECT_EQ(out.flowC, 0);
    s.in.outdoorCentiC.reset();
    out = s.apply(small);
    EXPECT_EQ(out.flowC, 32); EXPECT_EQ(s.policy.source(), FlowPolicy::Source::rule);
    // No usable room: no curve, the rule (a stop) unchanged.
    s.in.outdoorCentiC = 0; s.rooms[0].usable = false;
    out = s.apply(FlowDemand::Request{false, 0, FlowDemand::Reason::noDemand});
    EXPECT_FALSE(out.heat); EXPECT_EQ(out.reason, FlowDemand::Reason::noDemand);
}

TEST(FlowPolicy, TheHighestRoomBaseCountsOnOneCircuit) {
    Step s;
    s.p.rooms.resize(2); s.p.rooms[1].id = "badkamer"; s.p.rooms[1].emitter = RoomPlan::Emitter::floor;
    s.rooms[0] = room(2050, 2100); s.rooms[1] = room(2250, 2300); // the bathroom is warmer, nearly satisfied
    FlowSettings on; on.weatherCurve = true; s.policy.setSettings(on);
    s.in.outdoorCentiC = 0;
    // Bath: 23 + 0.667 x 23 = 38.3 -> 39; the living room has the larger error (lead) and a lower base.
    EXPECT_EQ(s.apply(FlowDemand::Request{true, 35, FlowDemand::Reason::heating}).flowC, 39 + 2);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "learned"), "room")->valuestring, "woonkamer");
}

TEST(FlowPolicy, LearnedFlowAppliesDuringAWarmUp) {
    House h(plan()); h.learn();
    ASSERT_STREQ(h.learner.readiness(0), "ready");
    Step s; s.in.outdoorCentiC = 500;
    s.rooms[0] = room(2000, 2100);             // 1 degC short
    const auto advice = h.learner.advise(0, 100, int16_t(500));
    ASSERT_TRUE(advice.flowC);
    auto out = s.apply(heat40, &h.learner);
    EXPECT_EQ(out.flowC, 40);                  // advice only
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "learned"), "state")->valuestring, "advice");
    EXPECT_EQ(at(at(at(status.get(), "flow"), "learned"), "flow_c")->valuedouble, *advice.flowC);
    FlowSettings on; on.applyLearned = true; s.policy.setSettings(on);
    out = s.apply(heat40, &h.learner);
    EXPECT_EQ(out.flowC, *advice.flowC); EXPECT_EQ(s.policy.source(), FlowPolicy::Source::learned);
    on.weatherCurve = true; s.policy.setSettings(on);
    EXPECT_EQ(s.apply(heat40, &h.learner).flowC, *advice.flowC); // the warm-up beats the curve
    s.rooms[0] = room(2080, 2100);             // holding: the curve again
    s.apply(FlowDemand::Request{true, 34, FlowDemand::Reason::heating}, &h.learner);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::curve);
    Json held(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(held.get(), false));
    EXPECT_STREQ(at(at(at(held.get(), "flow"), "learned"), "state")->valuestring, "holding");
    s.p.maximumFlowC = 36;                     // bounds hold for learned flow too
    s.rooms[0] = room(1900, 2100);
    EXPECT_LE(s.apply(heat40, &h.learner).flowC, 36);
}

TEST(FlowPolicy, LearnedOptimumStartHeatsAheadOfTheProgram) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan(RoomPlan::Emitter::floor, true)); h.learn();
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.in.outdoorCentiC = 500;
    const auto planned = WarmupPlanner::optimumStart(h.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), int16_t(500));
    ASSERT_STREQ(planned.confidence, "learned");
    s.rooms[0] = room(1850, 1850);             // night setpoint, satisfied: the rule is idle
    s.in.utc = planned.startUtc - 600;
    auto out = s.apply(idle, &h.learner);
    EXPECT_FALSE(out.heat);
    s.in.utc = planned.startUtc + 60;
    out = s.apply(idle, &h.learner);
    EXPECT_FALSE(out.heat);                    // advice only by default
    Json advice(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(advice.get(), false));
    EXPECT_STREQ(at(at(at(advice.get(), "flow"), "optimum_start"), "state")->valuestring, "advice");
    FlowSettings on; on.applyLearned = true; s.policy.setSettings(on);
    s.in.utc = *s.in.utc + 60;
    out = s.apply(idle, &h.learner);
    ASSERT_TRUE(out.heat);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
    EXPECT_GE(out.flowC, 30); EXPECT_LE(out.flowC, 60);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON* request = cJSON_AddObjectToObject(status.get(), "request");
    cJSON_AddBoolToObject(request, "heat", false); cJSON_AddNumberToObject(request, "flow_c", 0); cJSON_AddStringToObject(request, "reason", "idle");
    ASSERT_TRUE(s.policy.addStatus(status.get(), true));
    EXPECT_TRUE(cJSON_IsTrue(at(request, "heat")));
    EXPECT_STREQ(at(request, "reason")->valuestring, "optimum_start");
    EXPECT_FALSE(at(status.get(), "flow"));           // the main topic keeps its size: details are in heating_summary
    // Warmer now, so a fresh plan would start later: the begun start holds until its rise.
    s.rooms[0] = room(2000, 1850); s.in.now += 20 * minute; s.in.utc = *s.in.utc + 1200;
    EXPECT_GT(WarmupPlanner::optimumStart(h.learner, 0, s.p.rooms[0].schedule, *s.in.utc, int16_t(2000), int16_t(500)).startUtc, *s.in.utc);
    EXPECT_TRUE(s.apply(idle, &h.learner).heat);
    s.rooms[0] = room(1850, 1850);
    // Never during the rule's minimum off time or without a usable room.
    EXPECT_FALSE(s.apply(FlowDemand::Request{false, 0, FlowDemand::Reason::holdOff}, &h.learner).heat);
    EXPECT_FALSE(s.apply(FlowDemand::Request{false, 0, FlowDemand::Reason::noDemand}, &h.learner).heat);
    // Reached early: it still runs its 5 minutes, then stops.
    EXPECT_TRUE(s.apply(idle, &h.learner).heat);
    s.rooms[0] = room(2110, 1850);
    s.in.utc = *s.in.utc + 60;
    EXPECT_TRUE(s.apply(idle, &h.learner).heat);
    s.in.now += 6 * minute; s.in.utc = *s.in.utc + 360;
    EXPECT_FALSE(s.apply(idle, &h.learner).heat);
    // The rule heating anyway: the start's flow when it is higher.
    s.rooms[0] = room(1850, 1850);
    const auto both = s.apply(FlowDemand::Request{true, 31, FlowDemand::Reason::heating}, &h.learner);
    EXPECT_TRUE(both.heat); EXPECT_GE(both.flowC, 31);
}

TEST(FlowPolicy, DefaultLeadsAreOnlyAdvice) {
    ScopedTz tz(ScopedTz::amsterdam);
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.learner.setPlan(s.p);
    FlowSettings on; on.applyLearned = true; s.policy.setSettings(on);
    const auto planned = WarmupPlanner::optimumStart(s.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt);
    ASSERT_STREQ(planned.confidence, "default");
    s.rooms[0] = room(1850, 1850); s.in.utc = planned.startUtc + 60;
    EXPECT_FALSE(s.apply(idle).heat);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "optimum_start"), "state")->valuestring, "advice");
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "optimum_start"), "confidence")->valuestring, "default");
}

TEST(FlowCompare, MeansAtTheSameMomentsPerDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    FlowCompare c;
    uint64_t now = 0;
    const auto day = uint32_t(wednesday23 - 20 * 3600);  // Wednesday 03:00 local
    for (int i = 0; i < 360; ++i) {
        now += 10 * second;
        c.sample(now, day + i * 10, heat40, FlowDemand::Request{true, 36, FlowDemand::Reason::heating},
                 i < 180 ? std::optional<uint8_t>(36) : std::nullopt, std::nullopt);
    }
    for (int i = 0; i < 60; ++i) { now += 10 * second; c.sample(now, day + 3600 + i * 10, idle, FlowDemand::Request{true, 44, FlowDemand::Reason::heating}, std::nullopt, std::nullopt); }
    EXPECT_EQ(c.today().heatS, 3590u);         // the first sample only starts the clock
    EXPECT_EQ(c.today().curveS, 1790u);
    EXPECT_EQ(c.today().startS, 600u);
    Json o(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(FlowCompare::dayJson(o.get(), "today", c.today()));
    const cJSON* t = at(o.get(), "today");
    EXPECT_EQ(at(t, "rule_mean_c")->valuedouble, 40);
    EXPECT_EQ(at(t, "applied_mean_c")->valuedouble, 36);
    EXPECT_EQ(at(t, "curve_mean_c")->valuedouble, 36);
    EXPECT_EQ(at(t, "curve_rule_mean_c")->valuedouble, 40);
    EXPECT_TRUE(cJSON_IsNull(at(t, "learned_mean_c")));
    c.sample(now + 10 * second, day + 86400, heat40, heat40, std::nullopt, std::nullopt);
    ASSERT_TRUE(c.yesterday());
    EXPECT_EQ(c.yesterday()->heatS, 3590u);
    EXPECT_EQ(c.today().heatS, 10u);
}

// A night with a gas meter: the measured gas, its hot water share and the model's prediction.
TEST(NightLedger, MeasuresEachNightAgainstTheModel) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan(RoomPlan::Emitter::floor, true)); h.learn();
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.in.outdoorCentiC = 500;
    s.rooms[0] = room(1900, 1850);
    uint64_t now = h.now;
    double total = 2000;
    h.learner.gasMeter(total, now);
    s.in.now = now; s.in.utc = wednesday23 - 3 * 3600;   // Wednesday 20:00 local: the drop is ahead
    s.apply(idle, &h.learner);
    Json before(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.nights().json(before.get()));
    EXPECT_STREQ(at(before.get(), "state")->valuestring, "waiting");
    EXPECT_TRUE(cJSON_IsNull(at(before.get(), "last")));
    // 23:00 local: after the 22:30 drop, the night opens (prediction from now).
    s.in.utc = wednesday23; s.in.now = now += minute;
    h.learner.gasMeter(total, now);
    s.apply(idle, &h.learner);
    Json open(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.nights().json(open.get()));
    EXPECT_STREQ(at(open.get(), "state")->valuestring, "open");
    // The night: 2.5 m3, of which a shower (hot water at 100 % x 22 kW for 590 s after a gap = 3.6 kWh).
    FlowLearner::Boiler hot; hot.flowCentiC = 6000; hot.burnerOn = true; hot.hotWater = true; hot.modulationPct = 100;
    FlowLearner::RoomInput in; in.temperatureCentiC = 1900; in.setpointCentiC = 1850; in.source = 0;
    for (int i = 0; i < 60; ++i) { now += 10 * second; h.learner.sample(now, hot, &in, 1); }
    total += 2.5;
    // Until 6 h after the 06:30 switch (12:30 local) it stays open; then it closes.
    for (int64_t utc = wednesday23 + 60; utc <= wednesday23 + 14 * 3600; utc += 600) {
        now += 600 * second;
        if ((utc - wednesday23) % 3600 == 60) h.learner.gasMeter(total, now);
        s.in.utc = utc; s.in.now = now; s.apply(idle, &h.learner);
    }
    Json done(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.nights().json(done.get()));
    EXPECT_EQ(at(done.get(), "nights")->valuedouble, 1);
    const cJSON* last = at(done.get(), "last");
    ASSERT_TRUE(cJSON_IsObject(last));
    EXPECT_STREQ(at(last, "status")->valuestring, "measured");
    EXPECT_EQ(at(last, "measured_m3")->valuedouble, 2.5);
    const double shower = 22 * 590 / 3600.0 / 9.77;
    EXPECT_NEAR(at(last, "hot_water_m3")->valuedouble, shower, 0.001);
    EXPECT_NEAR(at(last, "heating_m3")->valuedouble, 2.5 - shower, 0.001);
    EXPECT_EQ(at(last, "switch_utc")->valuedouble, double(wednesday23 + 7 * 3600 + 30 * 60));
    EXPECT_TRUE(cJSON_IsNumber(at(last, "predicted_program_m3")));
    EXPECT_TRUE(cJSON_IsString(at(last, "recommended")));
    EXPECT_TRUE(cJSON_IsNumber(at(done.get(), "model_ratio")));
    EXPECT_STREQ(at(done.get(), "state")->valuestring, "waiting");
}

TEST(NightLedger, WithoutAMeterTheNightSaysSo) {
    ScopedTz tz(ScopedTz::amsterdam);
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.learner.setPlan(s.p);
    s.rooms[0] = room(1900, 1850);
    for (int64_t utc = wednesday23; utc <= wednesday23 + 15 * 3600; utc += 600) { s.in.utc = utc; s.apply(idle); }
    ASSERT_TRUE(s.policy.nights().last());
    EXPECT_STREQ(s.policy.nights().last()->status, "no_meter");
    EXPECT_FALSE(s.policy.nights().last()->programM3); // not learned: no prediction either
    Json summary(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addSummary(summary.get()));
    EXPECT_TRUE(cJSON_IsObject(at(summary.get(), "night_gas")));
    EXPECT_TRUE(cJSON_IsObject(at(at(summary.get(), "flow"), "curve")));
    EXPECT_FALSE(at(at(summary.get(), "flow"), "settings"));   // static: GET /config/heating/flow
}

// The summary topic at its longest: every option on, a learned curve slope,
// an applied optimum start, a measured night and yesterday's comparison.
TEST(FlowPolicy, WorstCaseSummaryStaysSmall) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan(RoomPlan::Emitter::floor, true)); h.learn();
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.p.rooms[0].id = std::string(32, 'w');
    s.in.outdoorCentiC = -1234;
    FlowSettings on; on.weatherCurve = on.applyLearned = true; on.designFlowC = 55; s.policy.setSettings(on);
    h.learner.setApplied(true);           // as HeatingController::setFlowSettings does
    uint64_t now = h.now; double total = 12345678.123;
    for (int64_t utc = wednesday23 - 26 * 3600; utc <= wednesday23 + 14 * 3600; utc += 60) {
        now += 60 * second;
        if (utc % 3600 == 0) { total += 1.234; h.learner.gasMeter(total, now); }
        s.rooms[0] = room(int16_t(1850 + (utc / 60) % 50), 2100);
        s.in.utc = utc; s.in.now = now; s.apply(FlowDemand::Request{true, 77, FlowDemand::Reason::heating}, &h.learner);
    }
    ASSERT_TRUE(s.policy.nights().last());
    LearnedContext c; c.now = now; c.outdoorCentiC = -1234; c.outdoorSource = "boiler";
    const auto summary = heatingSummaryTelemetry(h.learner, c, cJSON_CreateObject(), &s.policy);
    std::printf("[ flow policy ] worst-case summary %zu B: %s\n", summary.size(), summary.c_str());
    EXPECT_LE(summary.size(), 1024u);                  // the telemetry budget: about 1 KB per topic
    Json root(cJSON_Parse(summary.c_str()), cJSON_Delete);
    ASSERT_TRUE(root);
    EXPECT_TRUE(cJSON_IsObject(at(at(root.get(), "flow"), "yesterday")));
    EXPECT_TRUE(cJSON_IsTrue(at(at(root.get(), "learned"), "applied")));
}
}
