#include "control/FlowPolicy.h"
#include "control/RoomEngine.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <functional>
#include <memory>
#include <string>

// The 1.0 tuning knobs (control/ControlTuning.h): an absent or older record is
// today's behaviour exactly (a replay against a golden hash taken from the code
// before the knobs), each knob moves its part in the intended direction, and
// out-of-range values are refused.
namespace {
using heating::control::ControlTuning;
using heating::control::FlowDemand;
using heating::control::FlowLearner;
using heating::control::FlowPolicy;
using heating::control::FlowSettings;
using heating::control::RoomDemand;
using heating::control::RoomEngine;
using heating::control::RoomPlan;
using heating::control::RoomSchedule;
using heating::control::ShadowComparison;
using heating::control::WarmupPlanner;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;
Json parse(const char* text) { return Json(cJSON_Parse(text), cJSON_Delete); }

// replay-begin: also built against the code before the knobs, for the golden hash.
RoomSchedule program() {
    RoomSchedule s;
    for (auto& d : s.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
    return s;
}
RoomPlan replayPlan() {
    RoomPlan p; p.rooms.resize(2);
    const char* ids[2] = {"woonkamer", "slaapkamer"};
    for (size_t i = 0; i < 2; ++i) {
        auto& r = p.rooms[i];
        r.id = ids[i]; r.name = ids[i]; r.state = RoomDemand::State::active;
        r.emitter = i ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        r.sources = {{RoomPlan::SourceType::ha, std::string("climate.") + ids[i]}};
        r.schedule = program();
    }
    return p;
}
// Two rooms on one boiler: rate = a (flow - room) - b (room - outdoor), outdoor
// 2..11 degC over the day. The learner first learns at fixed flows, then the
// rule, the options and the learner run in a closed loop for three days; every
// request, the learner's and the planner's JSON go into one FNV-1a hash.
struct Replay {
    RoomPlan plan = replayPlan();
    RoomEngine engine;
    FlowLearner learner;
    FlowPolicy policy;
    double T[2] = {19.5, 18.0}, coast[2] = {0, 0};
    const double a[2] = {0.035, 0.09}, b[2] = {0.02, 0.03};
    uint64_t now = 0, hash = 1469598103934665603ull;
    unsigned starts = 0, heatSteps = 0, flowSum = 0;
    void mix(const std::string& text) { for (const char c : text) { hash ^= uint8_t(c); hash *= 1099511628211ull; } }
    void mixJson(cJSON* o) {
        if (!o) { mix("null"); return; }
        char* text = cJSON_PrintUnformatted(o);
        mix(text ? text : "oom"); cJSON_free(text); cJSON_Delete(o);
    }
    static int16_t outdoor(int64_t utc) { const int h = int((utc / 3600) % 24); return int16_t(200 + 75 * (h < 12 ? h : 24 - h)); }
    void physics(std::optional<uint8_t> flowC, int16_t out) {
        const double dt = 10.0 / 3600, o = out / 100.0;
        for (int i = 0; i < 2; ++i) {
            const double emit = flowC ? a[i] * (*flowC - T[i]) : 0;
            if (flowC) coast[i] = emit; else coast[i] *= std::exp(-dt / (i ? 0.5 : 1.5));
            T[i] += (flowC ? emit : coast[i]) * dt - b[i] * (T[i] - o) * dt;
        }
    }
    void sample(std::optional<uint8_t> flowC, int16_t out) {
        FlowLearner::Boiler boiler;
        const double flow = flowC ? *flowC + ((now / (5 * minute)) % 2 ? 1 : -1) : T[0] + 3;
        boiler.flowCentiC = int16_t(std::lround(flow * 100)); boiler.returnCentiC = int16_t(std::lround((flow - 5) * 100));
        boiler.burnerOn = flowC.has_value(); boiler.requestedFlowC = flowC.value_or(0); boiler.hotWater = false;
        boiler.outdoorCentiC = out; boiler.modulationPct = uint8_t(flowC ? 30 : 0);
        FlowLearner::RoomInput in[2];
        for (int i = 0; i < 2; ++i) { in[i].temperatureCentiC = int16_t(std::lround(T[i] * 10) * 10); in[i].setpointCentiC = 2100; in[i].source = 0; }
        learner.sample(now, boiler, in, 2);
    }
    void run(const std::function<void(Replay&)>& tune) {
        engine.setPlan(plan); learner.setPlan(plan);
        FlowSettings on; on.weatherCurve = on.applyLearned = true;
        policy.setSettings(on); learner.setApplied(true);
        if (tune) tune(*this);
        int64_t utc = wednesday23 - 9 * 86400;
        for (int c = 0; c < 3; ++c)
            for (const uint8_t f : {32, 36, 40, 44, 48, 52}) {
                T[0] = 20; T[1] = 19;
                for (uint64_t t = 0; t < 690 * minute; t += 10 * second) {
                    now += 10 * second; utc += 10;
                    const auto heat = t < 210 * minute ? std::optional<uint8_t>(f) : std::nullopt;
                    physics(heat, outdoor(utc)); sample(heat, outdoor(utc));
                }
            }
        mixJson(learner.json());
        bool was = false;
        for (int step = 0; step < 3 * 8640; ++step) {
            now += 10 * second; utc += 10;
            const int16_t out = outdoor(utc);
            for (int i = 0; i < 2; ++i)
                engine.haState(plan.rooms[i].sources[0].id, int16_t(std::lround(T[i] * 10) * 10), std::nullopt, now);
            const auto rule = engine.step(now, uint32_t(utc));
            std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
            for (size_t i = 0; i < 2; ++i) rooms[i] = engine.result(i);
            FlowPolicy::Inputs in;
            in.now = now; in.utc = utc; in.rule = rule; in.plan = &engine.plan(); in.rooms = rooms.data();
            in.outdoorCentiC = out; in.boilerLimitC = 70; in.flowCentiC = int16_t(std::lround(T[0] * 100 + 300));
            in.burnerOn = was; in.hotWater = false;
            const auto request = policy.apply(in, learner);
            char line[48];
            std::snprintf(line, sizeof line, "%d%d%u%u%u;", rule.heat, request.heat, unsigned(rule.flowC), unsigned(request.flowC), unsigned(policy.source()));
            mix(line);
            if (request.heat && !was) ++starts;
            if (request.heat) { ++heatSteps; flowSum += request.flowC; }
            was = request.heat;
            const auto flow = request.heat ? std::optional<uint8_t>(request.flowC) : std::nullopt;
            physics(flow, out); sample(flow, out);
            if (step % 360 == 0) {
                const std::optional<int16_t> temperatures[2] = {rooms[0].temperature, rooms[1].temperature};
                mixJson(WarmupPlanner::json(learner, engine.plan(), utc, temperatures, out));
                cJSON* status = cJSON_CreateObject();
                if (status && policy.addSummary(status)) mixJson(status); else cJSON_Delete(status);
                mixJson(engine.json());
            }
        }
        mixJson(learner.json());
    }
};
// replay-end

// The replay above built against the code before the knobs (a81d991, 1 Nov 2026), g++ on x86-64:
// 12 burner starts, 5219 heating steps of 10 s. rc.2 (learning in active mode): a floor room's
// segment counts from 30 min instead of 45, so the learner's JSON in the hash holds more
// segments; every request, start and heating step is unchanged (was 0x092730cbef929f94).
// rc.3: the planner's JSON says whether a start "applies" and the summary's curve its
// "windows"; still 12 starts and 5219 heating steps (was 0x0e57c515176989e2).
// rc.4: estimate starts are applied, each room's start has its own rest, the planner's JSON
// carries "estimate" and "arrival" and the learner's "readiness_timing"; still 12 starts and
// 5219 heating steps (was 0x76c5bb38db527eec).
// rc.5 (P1): the flow summary carries "ceiling_c" (null: no boiler ceiling in effect); still 12
// starts and 5219 heating steps, and the same run with that key left out still gives the rc.4
// hash 0x1a32287f37d8bf9a.
constexpr uint64_t goldenHash = 0xce5e6c6f47d567daull;

Replay replay(const std::function<void(Replay&)>& tune = nullptr) {
    ScopedTz tz(ScopedTz::amsterdam);
    Replay r; r.run(tune);
    return r;
}
// The untouched run, once for every test (a learned two-room house).
const Replay& untouched() { static const Replay r = replay(); return r; }
ControlTuning tuned(const char* text) {
    ControlTuning t;
    EXPECT_EQ(ControlTuning::parse(parse(text).get(), t), nullptr) << text;
    return t;
}
void tune(Replay& r, const ControlTuning& t) {
    auto s = r.policy.settings(); s.tuning = t;
    r.policy.setSettings(s); r.learner.setTuning(t); r.engine.setTuning(t);
}

TEST(ControlTuning, DefaultsReplayTodaysControlExactly) {
    const auto& d = untouched();
    std::printf("[ tuning ] replay hash 0x%016llx, %u starts, %u heating steps\n", (unsigned long long)d.hash, d.starts, d.heatSteps);
    EXPECT_EQ(d.hash, goldenHash);
    EXPECT_GT(d.starts, 3u);
    // An older record (no "tuning") given to every part in place: the same run.
    FlowSettings old;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"weather_curve":true,"apply_learned":true,"curve_design_flow_c":0})").get(), old), nullptr);
    EXPECT_TRUE(old.tuning == ControlTuning{});
    EXPECT_TRUE(tuned(ControlTuning{}.json().c_str()) == ControlTuning{});   // and the defaults as JSON
    EXPECT_EQ(replay([&](Replay& r) { tune(r, old.tuning); }).hash, d.hash);
    // A knob away from its default changes the run.
    const auto changed = replay([&](Replay& r) { tune(r, tuned(R"({"flow_per_degree_c":20})")); });
    EXPECT_NE(changed.hash, d.hash);
    EXPECT_GT(double(changed.flowSum) / changed.heatSteps, double(d.flowSum) / d.heatSteps); // a harder rule: warmer flows
}

TEST(ControlTuning, ParsesRangesStrictly) {
    ControlTuning t;
    EXPECT_EQ(t.json(), R"({"min_on_s":300,"min_off_s":300,"heat_start_c":0.20,"heat_stop_c":0.20,"flow_per_degree_c":10,)"
                        R"("curve_correction_pct":50,"floor_lead_min_per_c":120,"radiator_lead_min_per_c":45,"learned_accept_pct":100,)"
                        R"("night_saving_min_pct":2})");
    size_t n; const auto* k = ControlTuning::knobs(n);
    ASSERT_EQ(n, 10u);
    // Every knob at both ends is accepted; one step beyond is refused and changes nothing.
    ControlTuning widest;
    for (size_t i = 0; i < n; ++i) {
        const double unit = k[i].centi ? 0.01 : 1;
        for (const double v : {k[i].low * unit, k[i].high * unit}) {
            char text[80]; std::snprintf(text, sizeof text, "{\"%s\":%.3f}", k[i].key, v);
            ControlTuning one;
            EXPECT_EQ(ControlTuning::parse(parse(text).get(), one), nullptr) << text;
            EXPECT_EQ(one.*k[i].field, uint16_t(v / unit + 0.5)) << text;
        }
        for (const double v : {k[i].low * unit - unit, k[i].high * unit + unit}) {
            char text[80]; std::snprintf(text, sizeof text, "{\"%s\":%.3f}", k[i].key, v);
            ControlTuning one = t;
            EXPECT_STREQ(ControlTuning::parse(parse(text).get(), one), "invalid_value") << text;
            EXPECT_TRUE(one == t);
        }
        widest.*k[i].field = k[i].high;
    }
    EXPECT_LE(widest.json().size(), ControlTuning::maxBytes);
    ControlTuning back;
    ASSERT_EQ(ControlTuning::parse(parse(widest.json().c_str()).get(), back), nullptr);
    EXPECT_TRUE(back == widest);
    // Whole numbers, degC with at most 2 decimals.
    for (const char* bad : {R"({"min_on_s":300.5})", R"({"heat_start_c":0.205})", R"({"night_saving_min_pct":2.5})",
                            R"({"min_on_s":"300"})", R"({"heat_stop_c":true})", R"({"flow_per_degree_c":null})", R"({"min_on_s":-300})"})
        EXPECT_STREQ(ControlTuning::parse(parse(bad).get(), t), "invalid_value") << bad;
    EXPECT_STREQ(ControlTuning::parse(parse(R"({"min_on_s":600,"frost_on_c":7})").get(), t), "invalid_key");
    EXPECT_STREQ(ControlTuning::parse(parse("[]").get(), t), "invalid_value");
    EXPECT_TRUE(t == ControlTuning{});
    // Partial: other knobs keep their value; null gives the built-in values again.
    ASSERT_EQ(ControlTuning::parse(parse(R"({"heat_stop_c":0.05,"night_saving_min_pct":10})").get(), t), nullptr);
    ASSERT_EQ(ControlTuning::parse(parse(R"({"min_on_s":600})").get(), t), nullptr);
    EXPECT_EQ(t.stopCentiC, 5); EXPECT_EQ(t.nightSavingPct, 10); EXPECT_EQ(t.minOnS, 600); EXPECT_EQ(t.startCentiC, 20);
    ASSERT_EQ(ControlTuning::parse(parse("null").get(), t), nullptr);
    EXPECT_TRUE(t == ControlTuning{});
    EXPECT_EQ(ControlTuning::parse(parse("{}").get(), t), nullptr);
}

TEST(ControlTuning, TravelsInTheFlowRecord) {
    // An older record (beta.19..1.0 without knobs) and an absent one: the built-in values.
    FlowSettings s;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"weather_curve":true,"apply_learned":false,"curve_design_flow_c":45})").get(), s), nullptr);
    EXPECT_TRUE(s.tuning == ControlTuning{}); EXPECT_EQ(s.designFlowC, 45);
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":{"min_on_s":600,"heat_start_c":0.3}})").get(), s), nullptr);
    EXPECT_TRUE(s.weatherCurve); EXPECT_EQ(s.tuning.minOnS, 600); EXPECT_EQ(s.tuning.startCentiC, 30); EXPECT_EQ(s.tuning.minOffS, 300);
    const FlowSettings before = s;
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"weather_curve":false,"tuning":{"min_on_s":60}})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"tuning":{"hysteresis":1}})").get(), s), "invalid_key");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"tuning":5})").get(), s), "invalid_value");
    EXPECT_TRUE(s == before);
    FlowSettings widest; widest.designFlowC = 80; widest.weatherCurve = widest.applyLearned = true;
    size_t n; const auto* k = ControlTuning::knobs(n);
    for (size_t i = 0; i < n; ++i) widest.tuning.*k[i].field = k[i].high;
    widest.manual = ControlTuning::autoKnobs; // rc.2: knobs away from the built-in value are the owner's
    EXPECT_LE(widest.json().size(), FlowSettings::maxBytes);
    FlowSettings back;
    ASSERT_EQ(FlowSettings::parse(parse(widest.json().c_str()).get(), back), nullptr);
    EXPECT_TRUE(back == widest);
    EXPECT_FALSE(back == FlowSettings{});
    ASSERT_EQ(FlowSettings::parse(parse(R"({"tuning":null})").get(), back), nullptr);
    EXPECT_TRUE(back.tuning == ControlTuning{}); EXPECT_EQ(back.designFlowC, 80);
}

// One floor room on the HA sensor, as the owner's plan.
struct Engine {
    RoomEngine e;
    uint64_t now = 0;
    explicit Engine(const ControlTuning& t = {}) {
        RoomPlan p; p.rooms.resize(1);
        auto& r = p.rooms[0];
        r.id = "woonkamer"; r.state = RoomDemand::State::active; r.emitter = RoomPlan::Emitter::floor;
        r.sources = {{RoomPlan::SourceType::ha, "climate.woonkamer"}}; r.fallbackCentiC = 2000;
        e.setPlan(p); e.setTuning(t);
    }
    FlowDemand::Request at(int16_t temperature, uint64_t after = 10 * second) {
        now += after;
        e.haState("climate.woonkamer", temperature, std::nullopt, now);
        return e.step(now, std::nullopt);
    }
};

TEST(ControlTuning, HeatStartAndStopThresholds) {
    // Default: heat from 0.2 degC below the setpoint until 0.2 above it.
    Engine d, early(tuned(R"({"heat_start_c":0.1})")), late(tuned(R"({"heat_start_c":0.5})"));
    EXPECT_FALSE(d.at(1985).heat); EXPECT_TRUE(early.at(1985).heat); EXPECT_FALSE(late.at(1970).heat);
    EXPECT_TRUE(d.at(1980).heat); EXPECT_FALSE(late.at(1960).heat); EXPECT_TRUE(late.at(1950).heat);
    Engine stopEarly(tuned(R"({"heat_stop_c":0})")), stopLate(tuned(R"({"heat_stop_c":0.4})"));
    for (auto* x : {&d, &stopEarly, &stopLate}) { EXPECT_TRUE(x->at(1950).heat); x->at(1950, 10 * minute); }
    EXPECT_TRUE(d.at(2000).heat); EXPECT_FALSE(stopEarly.at(2000).heat);     // at the setpoint
    EXPECT_FALSE(d.at(2020).heat); EXPECT_TRUE(stopLate.at(2020).heat);      // 0.2 above it
    EXPECT_FALSE(stopLate.at(2040).heat);
}

TEST(ControlTuning, BurnerMinimumOnAndOffTimes) {
    const auto onFor = [](Engine& x) {   // heat starts, the room is warm at once: how long it still runs
        x.at(1900);
        uint64_t s = 0;
        while (x.at(2100).heat) s += 10;
        return s;
    };
    const auto offFor = [](Engine& x) {  // then cold again at once: how long until it may start
        uint64_t s = 0;
        while (!x.at(1900).heat) s += 10;
        return s;
    };
    Engine d, longer(tuned(R"({"min_on_s":900,"min_off_s":1200})")), shorter(tuned(R"({"min_on_s":120,"min_off_s":120})"));
    EXPECT_EQ(onFor(d), 290u); EXPECT_EQ(offFor(d), 290u);
    EXPECT_EQ(onFor(longer), 890u); EXPECT_EQ(offFor(longer), 1190u);
    EXPECT_EQ(onFor(shorter), 110u); EXPECT_EQ(offFor(shorter), 110u);
    // A change in place keeps the running timers (no restart of the hold).
    Engine x; x.at(1900); x.at(2100, 60 * second);
    x.e.setTuning(tuned(R"({"min_on_s":120})"));
    EXPECT_EQ(x.at(2100, 50 * second).reason, FlowDemand::Reason::holdOn);
    EXPECT_EQ(x.at(2100, 20 * second).reason, FlowDemand::Reason::satisfied);
}

TEST(ControlTuning, RuleGainSetsTheFlowPerDegree) {
    Engine d, soft(tuned(R"({"flow_per_degree_c":5})")), hard(tuned(R"({"flow_per_degree_c":20})"));
    EXPECT_EQ(d.at(1940).flowC, 36);             // 0.6 degC short: 30 + 6
    EXPECT_EQ(soft.at(1940).flowC, 33);
    EXPECT_EQ(hard.at(1940).flowC, 42);
    // The learner's view of the rule (advice, unlearned optimum start) follows the same gain.
    FlowLearner l; RoomPlan p; p.rooms.resize(1); p.rooms[0].id = "w"; l.setPlan(p);
    EXPECT_EQ(l.ruleFlow(100), 40);
    l.setTuning(tuned(R"({"flow_per_degree_c":20})"));
    EXPECT_EQ(l.ruleFlow(100), 50);
}

TEST(ControlTuning, CurveCorrectionShare) {
    RoomPlan p; p.rooms.resize(1); p.rooms[0].id = "w"; p.rooms[0].state = RoomDemand::State::active; p.rooms[0].emitter = RoomPlan::Emitter::floor;
    FlowLearner l; l.setPlan(p);
    std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
    rooms[0].status = RoomDemand::Status::ok; rooms[0].usable = true; rooms[0].temperature = 2000; rooms[0].setpoint = 2100; rooms[0].errorCentiC = 100;
    const auto flowWith = [&](const char* tuning) {
        FlowPolicy policy; FlowSettings s; s.weatherCurve = true; s.applyLearned = false; s.tuning = tuned(tuning); policy.setSettings(s);
        FlowPolicy::Inputs in; in.now = 10 * second; in.plan = &p; in.rooms = rooms.data(); in.outdoorCentiC = 500;
        in.rule = {true, 40, FlowDemand::Reason::heating};
        const auto with = policy.apply(in, l).flowC;
        in.rule = {true, 30, FlowDemand::Reason::heating};
        return std::make_pair(with, policy.apply(in, l).flowC);
    };
    const auto d = flowWith("{}"), none = flowWith(R"({"curve_correction_pct":0})"), full = flowWith(R"({"curve_correction_pct":100})");
    EXPECT_EQ(d.first, d.second + 5);            // half of the rule's 10 degC above the plan minimum
    EXPECT_EQ(none.first, none.second);
    EXPECT_EQ(full.first, full.second + 10);
    EXPECT_EQ(d.second, none.second);            // the curve's base itself is not a knob
}

TEST(ControlTuning, UnlearnedWarmupLeads) {
    using E = RoomPlan::Emitter;
    EXPECT_EQ(WarmupPlanner::defaultLeadS(E::floor, 100), 7200u);   // 2 h per degC
    EXPECT_EQ(WarmupPlanner::defaultLeadS(E::radiator, 100), 2700u); // 45 min per degC
    const auto t = tuned(R"({"floor_lead_min_per_c":60,"radiator_lead_min_per_c":90})");
    EXPECT_EQ(WarmupPlanner::defaultLeadS(E::floor, 100, t), 3600u);
    EXPECT_EQ(WarmupPlanner::defaultLeadS(E::radiator, 100, t), 5400u);
    EXPECT_EQ(WarmupPlanner::defaultLeadS(E::floor, 500, tuned(R"({"floor_lead_min_per_c":360})")), 21600u); // the 6 h maximum stays
    // The optimum start plan (default confidence) follows the learner's tuning. rc.4: an estimate
    // no morning has judged yet is capped at 3 h (floor); trusted arrival feedback lifts the cap.
    ScopedTz tz(ScopedTz::amsterdam);
    FlowLearner l; RoomPlan p; p.rooms.resize(1); p.rooms[0].id = "w"; p.rooms[0].emitter = E::floor; l.setPlan(p);
    const heating::control::LeadFactor trusted{1.0f, true};
    EXPECT_EQ(WarmupPlanner::optimumStart(l, 0, program(), wednesday23, int16_t(1850), std::nullopt).leadS, WarmupPlanner::estimateCapFloorS);
    const auto before = WarmupPlanner::optimumStart(l, 0, program(), wednesday23, int16_t(1850), std::nullopt, trusted);
    l.setTuning(tuned(R"({"floor_lead_min_per_c":60})"));
    const auto after = WarmupPlanner::optimumStart(l, 0, program(), wednesday23, int16_t(1850), std::nullopt, trusted);
    ASSERT_STREQ(after.confidence, "default");
    EXPECT_EQ(before.leadS, 18000u);            // 2.5 degC at 2 h per degC
    EXPECT_EQ(after.leadS, 9000u);
    EXPECT_GT(after.startUtc, before.startUtc);
    EXPECT_EQ(WarmupPlanner::optimumStart(l, 0, program(), wednesday23, int16_t(1850), std::nullopt).leadS, 9000u) << "under the cap";
}

TEST(ControlTuning, OptimumStartRunsTheMinimumOnTime) {
    // An applied (learned) optimum start that reaches its target at once still runs
    // the minimum on time: 5 min by default, the tuning's min_on_s otherwise.
    ScopedTz tz(ScopedTz::amsterdam);
    const FlowLearner learner = untouched().learner; // a learned house
    const auto plan = replayPlan();
    const auto runFor = [&](const char* tuning) {
        FlowPolicy policy; FlowSettings s; s.applyLearned = true; s.weatherCurve = false; s.tuning = tuned(tuning); policy.setSettings(s);
        const auto planned = WarmupPlanner::optimumStart(learner, 0, plan.rooms[0].schedule, wednesday23, int16_t(1850), int16_t(500));
        EXPECT_STREQ(planned.confidence, "learned");
        std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
        const auto room = [&](int16_t t) {
            auto& x = rooms[0];
            x.status = RoomDemand::Status::ok; x.source = 0; x.usable = true; x.temperature = t; x.setpoint = 1850; x.errorCentiC = int16_t(1850 - t);
        };
        room(1850);
        FlowPolicy::Inputs in; in.plan = &plan; in.rooms = rooms.data(); in.outdoorCentiC = 500;
        in.rule = {false, 0, FlowDemand::Reason::idle}; in.now = 10 * second; in.utc = planned.startUtc + 60;
        EXPECT_TRUE(policy.apply(in, learner).heat);
        room(2110);                             // warm at once
        unsigned s10 = 0;
        for (; s10 < 360; ++s10) { in.now += 10 * second; *in.utc += 10; if (!policy.apply(in, learner).heat) break; }
        return s10 * 10;
    };
    EXPECT_EQ(runFor("{}"), 290u);
    EXPECT_EQ(runFor(R"({"min_on_s":900})"), 890u);
    EXPECT_EQ(runFor(R"({"min_on_s":120})"), 110u);
}

TEST(ControlTuning, LearnedFlowAcceptance) {
    RoomPlan p; p.rooms.resize(2); p.rooms[0].id = "v"; p.rooms[0].emitter = RoomPlan::Emitter::floor; p.rooms[1].id = "r";
    FlowLearner l; l.setPlan(p);
    const float floorRate = l.advise(0, 100, std::nullopt).requiredRate, radiatorRate = l.advise(1, 100, std::nullopt).requiredRate;
    EXPECT_FLOAT_EQ(floorRate, 0.5f);           // 1 degC in 2 h
    EXPECT_FLOAT_EQ(radiatorRate, 1.0f);        // 1 degC in 1 h
    l.setTuning(tuned(R"({"learned_accept_pct":200})"));   // slower warm-ups accepted: a lower flow suffices
    EXPECT_FLOAT_EQ(l.advise(0, 100, std::nullopt).requiredRate, 0.25f);
    EXPECT_FLOAT_EQ(l.advise(1, 100, std::nullopt).requiredRate, 0.5f);
    Json j(l.roomJson(0), cJSON_Delete);
    EXPECT_EQ(cJSON_GetObjectItem(j.get(), "accept_base_min")->valuedouble, 120);
    p.rooms.resize(3); p.rooms[2].id = "new"; l.setPlan(p);     // a room added later gets it too
    EXPECT_FLOAT_EQ(l.advise(2, 100, std::nullopt).requiredRate, 0.5f);
    l.setTuning(tuned(R"({"learned_accept_pct":50})"));
    EXPECT_FLOAT_EQ(l.advise(0, 100, std::nullopt).requiredRate, 1.0f);
    l.setTuning(ControlTuning{});
    EXPECT_FLOAT_EQ(l.advise(0, 100, std::nullopt).requiredRate, floorRate);
}

TEST(ControlTuning, NightSavingThreshold) {
    // The learned floor of the replay on a -10 degC night: holding 1 degC higher saves
    // 0.05 m3 of 6.4, under the 2 % noise threshold: the program stays, unless the
    // threshold is lowered; a higher one never recommends more.
    ScopedTz tz(ScopedTz::amsterdam);
    FlowLearner learner = untouched().learner;
    const int64_t utc = wednesday23 - 6 * 86400 - 3 * 3600;     // a Thursday, 20:00 local
    const auto night = [&](const char* tuning) {
        learner.setTuning(tuned(tuning));
        return WarmupPlanner::night(learner, 0, program(), utc, int16_t(1950), int16_t(-1000));
    };
    const auto d = night("{}"), zero = night(R"({"night_saving_min_pct":0})"), strict = night(R"({"night_saving_min_pct":20})");
    ASSERT_STREQ(d.reason, "estimated");
    EXPECT_STREQ(d.strategies[d.best].name, "program"); EXPECT_EQ(d.savingM3, 0.0f);
    EXPECT_STREQ(zero.strategies[zero.best].name, "hold_1_0");
    EXPECT_GT(zero.savingM3, 0.05f); EXPECT_LT(zero.savingM3, 0.02f * zero.strategies[0].m3);
    EXPECT_EQ(strict.best, 0); EXPECT_EQ(strict.savingM3, 0.0f);
}
}
