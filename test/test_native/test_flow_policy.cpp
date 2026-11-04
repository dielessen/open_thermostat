#include "control/BoundedJson.h"
#include "control/ControlPartitionBudget.h"
#include "control/FlowPolicy.h"
#include "control/HeatingTelemetry.h"
#include "control/TelemetryPolicy.h"
#include "BoilerResponseWidest.h"
#include "FlowSettingsRc2.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <limits>
#include <memory>
#include <tuple>

namespace {
using heating::control::FlowCompare;
using heating::control::LearnedContext;
using heating::control::heatingSummaryTelemetry;
using heating::control::FlowDemand;
using heating::control::FlowLearner;
using heating::control::FlowPolicy;
using heating::control::FlowSettings;
using heating::control::FlowSettingsRc2;
using heating::control::FreeHeat;
using heating::control::readFlowRecordRc2;
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
    // Options off (Smart warm-up is on by default since rc.3: the tests turn it on themselves).
    Step() { learner.setPlan(p); rooms[0] = room(2000, 2100); in.plan = &p; in.rooms = rooms.data(); policy.setSettings(off()); }
    static FlowSettings off() { FlowSettings s; s.applyLearned = s.weatherCurve = false; return s; }
    FlowDemand::Request apply(FlowDemand::Request rule, const FlowLearner* l = nullptr) {
        in.now += 10 * second; in.rule = rule;
        return policy.apply(in, l ? *l : learner);
    }
};
const FlowDemand::Request heat40{true, 40, FlowDemand::Reason::heating};
const FlowDemand::Request idle{false, 0, FlowDemand::Reason::idle};

// Review of rc.2 (finding 6): GET /config/heating/flow answers ~0.5 KB, but the POST took
// at most 256 bytes, so posting the record back (a backup, a script) was refused.
TEST(FlowSettings, TheWholeRecordPostsBack) {
    FlowSettings s;
    s.weatherCurve = s.applyLearned = true; s.designFlowC = 80;
    size_t n; const auto* k = heating::control::ControlTuning::knobs(n);
    for (size_t i = 0; i < n; ++i) s.tuning.*k[i].field = k[i].high;
    s.manual = heating::control::ControlTuning::autoKnobs;
    const auto compact = s.json(&s.tuning);
    EXPECT_LE(compact.size(), FlowSettings::maxBytes);
    EXPECT_GT(compact.size(), 256u) << "the old POST limit";
    const auto root = parse(compact.c_str());
    char* text = cJSON_Print(root.get()); // as a person or a script may post it
    const std::string pretty = text; cJSON_free(text);
    for (const auto& body : {compact, pretty}) {
        EXPECT_LE(body.size(), FlowSettings::postMaxBytes);
        const auto posted = heating::control::parseNestedJson(body, true, 2); // the route's depth limit
        ASSERT_TRUE(posted) << body;
        FlowSettings back;
        ASSERT_EQ(FlowSettings::parse(posted.get(), back), nullptr);
        EXPECT_TRUE(back == s);
    }
    EXPECT_FALSE(heating::control::parseNestedJson(std::string(R"({"tuning":{"a":{"b":1}}})"), true, 2)) << "still 2 levels at most";
}

TEST(FlowSettings, ParsesPartialUpdatesStrictly) {
    FlowSettings s; s.applyLearned = s.weatherCurve = false;
    EXPECT_EQ(s.json(), R"({"weather_curve":false,"apply_learned":false,"curve_design_flow_c":0,"tuning":)" + s.tuning.json() + R"(,"tuning_manual":[],"version":2})");
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
    // "version": the record format; any whole number from 1 (a newer backup restores too), ignored here.
    EXPECT_EQ(FlowSettings::parse(parse(R"({"version":3})").get(), s), nullptr);
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"version":"2"})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"version":0})").get(), s), "invalid_value");
    EXPECT_STREQ(FlowSettings::parse(parse(R"({"version":2.5})").get(), s), "invalid_value");
}

// rc.3 (owner, 3 Nov 2026): a time in the week program means "warm at that time",
// and the E32 decides itself when what it learned is good enough. Smart warm-up
// (apply_learned) and the heating curve (weather_curve) are on for a fresh install.
TEST(FlowSettings, SmartWarmupAndTheCurveAreOnForAFreshInstall) {
    const FlowSettings fresh;
    EXPECT_TRUE(fresh.applyLearned);
    EXPECT_TRUE(fresh.weatherCurve);
    EXPECT_EQ(fresh.designFlowC, 0) << "automatic by emitter";
    FlowSettings read;
    EXPECT_FALSE(FlowSettings::readStored("", 0, read)) << "absent: the defaults (FlowSettingsNvs::read)";
    EXPECT_FALSE(FlowSettings::readStored("{", 1, read));
    EXPECT_TRUE(read.applyLearned); EXPECT_TRUE(read.weatherCurve);
}

// The record rc.2 (and every firmware before rc.3) wrote: its apply_learned and
// weather_curve false were the old defaults, so they read as on; everything else is kept.
TEST(FlowSettings, AnOlderRecordsDefaultOffBecomesOn) {
    FlowSettingsRc2 old; old.designFlowC = 45; old.tuning.minOnS = 600; old.manual = 1;
    ASSERT_FALSE(old.applyLearned); ASSERT_FALSE(old.weatherCurve);
    const auto text = old.json();
    FlowSettings read;
    ASSERT_TRUE(FlowSettings::readStored(text.c_str(), text.size(), read));
    EXPECT_TRUE(read.applyLearned);
    EXPECT_TRUE(read.weatherCurve); EXPECT_EQ(read.designFlowC, 45); EXPECT_EQ(read.tuning.minOnS, 600); EXPECT_EQ(read.manual, 1);
    old.applyLearned = old.weatherCurve = true;    // on stays on
    const auto on = old.json();
    ASSERT_TRUE(FlowSettings::readStored(on.c_str(), on.size(), read));
    EXPECT_TRUE(read.applyLearned); EXPECT_TRUE(read.weatherCurve);
    // A broken format line after it is no rc.3 record either.
    const auto broken = text + "\n{\"version\":";
    ASSERT_TRUE(FlowSettings::readStored(broken.c_str(), broken.size(), read));
    EXPECT_TRUE(read.applyLearned); EXPECT_TRUE(read.weatherCurve);
}

// The owner's off, saved by rc.3 (POST, the E32 page, Home Assistant or a restore), stays off.
TEST(FlowSettings, AnExplicitOffIsKept) {
    FlowSettings s;
    ASSERT_EQ(FlowSettings::parse(parse(R"({"apply_learned":false})").get(), s), nullptr);
    EXPECT_FALSE(s.applyLearned);
    const auto text = s.stored();
    EXPECT_EQ(text, s.json().substr(0, s.json().size() - std::string(R"(,"version":2})").size()) + "}\n{\"version\":2}");
    FlowSettings read;
    ASSERT_TRUE(FlowSettings::readStored(text.c_str(), text.size(), read));
    EXPECT_FALSE(read.applyLearned);
    EXPECT_TRUE(read == s);
    s.applyLearned = true;                          // and on again
    const auto on = s.stored();
    ASSERT_TRUE(FlowSettings::readStored(on.c_str(), on.size(), read));
    EXPECT_TRUE(read.applyLearned);
    // The heating curve the same way: the owner's off stays, the rest is untouched.
    ASSERT_EQ(FlowSettings::parse(parse(R"({"weather_curve":false})").get(), s), nullptr);
    const auto curveOff = s.stored();
    ASSERT_TRUE(FlowSettings::readStored(curveOff.c_str(), curveOff.size(), read));
    EXPECT_FALSE(read.weatherCurve); EXPECT_TRUE(read.applyLearned);
    // The GET answer (and a backup) carries the format; posted back it is the same.
    s.applyLearned = false;
    FlowSettings back;
    ASSERT_EQ(FlowSettings::parse(parse(s.json().c_str()).get(), back), nullptr);
    EXPECT_TRUE(back == s);
}

// A rollback to rc.2 reads the record rc.3 wrote: the same options, its widest
// form within rc.2's read buffer and the partition budget's flow record.
TEST(FlowSettings, Rc2ReadsTheRecordAfterARollback) {
    for (const bool smart : {false, true}) {
        FlowSettings s;
        s.weatherCurve = !smart; s.applyLearned = smart; s.designFlowC = 80;
        size_t n; const auto* k = heating::control::ControlTuning::knobs(n);
        for (size_t i = 0; i < n; ++i) s.tuning.*k[i].field = k[i].high;
        s.manual = heating::control::ControlTuning::autoKnobs;
        const auto text = s.stored();
        EXPECT_LE(text.size(), FlowSettingsRc2::maxBytes);
        EXPECT_LE(text.size() + 1, heating::control::ControlPartitionBudget::flowRecordBytes);
        EXPECT_LE(s.json().size(), FlowSettings::postMaxBytes);
        FlowSettingsRc2 old;
        ASSERT_TRUE(readFlowRecordRc2(text, old)) << text;
        EXPECT_EQ(old.applyLearned, smart); EXPECT_EQ(old.weatherCurve, !smart);
        EXPECT_EQ(old.designFlowC, 80);
        EXPECT_TRUE(old.tuning == s.tuning); EXPECT_EQ(old.manual, s.manual);
        // What rc.2 writes after that reads back here by the older rule.
        const auto again = old.json();
        FlowSettings forward;
        ASSERT_TRUE(FlowSettings::readStored(again.c_str(), again.size(), forward));
        EXPECT_TRUE(forward.applyLearned); EXPECT_TRUE(forward.weatherCurve);
    }
    FlowSettingsRc2 old;
    EXPECT_FALSE(readFlowRecordRc2(FlowSettings{}.json(), old)) << "the GET form is not the record: rc.2 refuses \"version\"";
}

// Options on but neither a curve (no outdoor) nor a learned flow: the rule's
// flow passes through, still within [plan min, min(plan max, 80, 0x16)].
TEST(FlowPolicy, OptionsOnClampTheRulesFlowToTheBoilerLimit) {
    Step s;
    s.in.boilerLimitC = 45;
    const FlowDemand::Request rule{true, 60, FlowDemand::Reason::heating};
    FlowSettings on = Step::off(); on.weatherCurve = on.applyLearned = true;
    s.policy.setSettings(on);
    auto out = s.apply(rule);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::rule);
    EXPECT_TRUE(out.heat); EXPECT_EQ(out.flowC, 45); EXPECT_EQ(out.reason, rule.reason);
    s.in.boilerLimitC = 20; // a limit below the plan minimum: the limit wins
    EXPECT_EQ(s.apply(rule).flowC, 20);
    s.policy.setSettings(Step::off()); // off: byte for byte the rule (the guard caps what it sends)
    out = s.apply(rule);
    EXPECT_EQ(out.flowC, 60); EXPECT_FALSE(out.capped);
    const FlowDemand::Request capped{true, 45, FlowDemand::Reason::holdOn, true}; // a rule the boiler's limit lowered
    s.in.boilerLimitC = 45;
    out = s.apply(capped);
    EXPECT_EQ(out.flowC, 45); EXPECT_EQ(out.reason, capped.reason); EXPECT_TRUE(out.capped);
    s.policy.setSettings(on); // on: the flag follows the option's own wish
    out = s.apply(rule);
    EXPECT_EQ(out.flowC, 45); EXPECT_TRUE(out.capped);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON* request = cJSON_AddObjectToObject(status.get(), "request");
    cJSON_AddBoolToObject(request, "heat", true); cJSON_AddNumberToObject(request, "flow_c", 60);
    cJSON_AddStringToObject(request, "reason", "heating"); cJSON_AddNullToObject(request, "capped_by");
    ASSERT_TRUE(s.policy.addStatus(status.get(), true));
    EXPECT_STREQ(cJSON_GetStringValue(at(request, "capped_by")), "boiler_limit");
    EXPECT_EQ(at(request, "flow_c")->valuedouble, 45);
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
    // The page's "last night" line: the ledger in its full form, no night closed yet.
    EXPECT_STREQ(at(at(status.get(), "night_gas"), "state")->valuestring, "waiting");
    EXPECT_TRUE(cJSON_IsNull(at(at(status.get(), "night_gas"), "last")));
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

// rc.5 (P2): the curve's slope in this order: CurveLearner's once it has its six steady periods, else
// the house model's (HouseModel: heat loss over emitter output, within the curve's bounds and at least
// half the design slope), else the design slope. "slope_source" says which.
TEST(FlowPolicy, TheHouseSlopeComesBetweenTheLearnedCurveAndTheDesign) {
    Step s;
    FlowSettings on = Step::off(); on.weatherCurve = true;
    s.policy.setSettings(on);
    s.rooms[0] = room(2000, 2100);
    s.in.outdoorCentiC = -1000;
    const auto curve = [&] {
        Json status(cJSON_CreateObject(), cJSON_Delete);
        EXPECT_TRUE(s.policy.addStatus(status.get(), false));
        const cJSON* c = at(at(status.get(), "flow"), "curve");
        return std::make_tuple(std::string(at(c, "slope_source")->valuestring), at(c, "slope")->valuedouble, int(at(c, "flow_c")->valuedouble));
    };
    // The design: floor 0.67, 21 + 0.667 x 31 = 41.7 -> 42, + (40 - 30) / 2.
    EXPECT_EQ(s.apply(heat40).flowC, 47);
    EXPECT_EQ(curve(), std::make_tuple(std::string("design"), 0.67, 47));
    s.in.houseSlope = 0.4f;                                        // 21 + 0.4 x 31 = 33.4 -> 34, + 5
    EXPECT_EQ(s.apply(heat40).flowC, 39);
    EXPECT_EQ(curve(), std::make_tuple(std::string("house"), 0.4, 39));
    s.in.houseSlope = 9.0f;                                        // bounded to the curve's 2.5, the flow to the plan's 60
    EXPECT_EQ(s.apply(heat40).flowC, 60);
    EXPECT_EQ(std::get<1>(curve()), 2.5);
    // Comfort first: an estimate takes at most half off the design slope (0.667 / 2: 21 + 0.333 x 31 = 31.3 -> 32, + 5).
    s.in.houseSlope = 0.2f;
    EXPECT_EQ(s.apply(heat40).flowC, 37);
    EXPECT_EQ(curve(), std::make_tuple(std::string("house"), 0.33, 37));
    for (const float bad : {0.0f, -1.0f, std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()}) {
        s.in.houseSlope = bad;
        EXPECT_EQ(s.apply(heat40).flowC, 47) << bad;
        EXPECT_EQ(std::get<0>(curve()), "design") << bad;
    }
    // Six steady 3-hour periods at 50 degC with the burner on half the time, 15 K colder outside: the
    // learned slope (20 + 0.5 x 30 = 35 against 20: 15 / 15 = 1.0) wins over the house model's.
    s.in.houseSlope = 0.4f;
    s.rooms[0] = room(2000, 2000);
    s.in.outdoorCentiC = 500; s.in.flowCentiC = 5000; s.in.hotWater = false;
    for (int i = 0; i < 7 * 1081; ++i) { s.in.burnerOn = (i / 30) % 2 == 0; s.apply(idle); }
    const auto learned = s.policy.curveLearner().slope();
    ASSERT_TRUE(learned);
    EXPECT_NEAR(*learned, 1.0, 0.01);
    s.rooms[0] = room(2000, 2100);
    s.in.outdoorCentiC = -1000;
    const int flow = (heating::control::WeatherCurve::baseCentiC(*learned, 2100, -1000) + 99) / 100 + 5; // 21 + 1.0 x 31 = 52, + 5
    EXPECT_EQ(s.apply(heat40).flowC, flow);
    EXPECT_EQ(std::get<0>(curve()), "learned");
    EXPECT_EQ(std::get<2>(curve()), flow);
}

TEST(FlowPolicy, WeatherCurveSetsTheFlowWithinAllBounds) {
    Step s;
    FlowSettings on = Step::off(); on.weatherCurve = true;
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
    FlowSettings on = Step::off(); on.weatherCurve = true; s.policy.setSettings(on);
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
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
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
    EXPECT_FALSE(out.heat);                    // advice only while off
    Json advice(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(advice.get(), false));
    EXPECT_STREQ(at(at(at(advice.get(), "flow"), "optimum_start"), "state")->valuestring, "advice");
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
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
    EXPECT_FALSE(at(status.get(), "night_gas"));
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

// rc.4 (L3): a learned warm-up curve without a usable cooling model (no outdoor reading) plans
// from the current temperature and is applied as an estimate; with the outdoor it is a measurement.
TEST(FlowPolicy, OptimumStartWithoutTheCoolingModelAppliesAsAnEstimate) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan(RoomPlan::Emitter::floor, true)); h.learn();
    ASSERT_TRUE(h.learner.heatModel(0).lossPerHour);
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.policy.setPlan(s.p);
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    const auto planned = WarmupPlanner::optimumStart(h.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt);
    ASSERT_STREQ(planned.confidence, "learned");
    EXPECT_FALSE(planned.coolingLearned);
    EXPECT_FALSE(planned.applicable());
    EXPECT_TRUE(planned.estimate);
    s.rooms[0] = room(1850, 1850); s.in.utc = planned.startUtc + 60;
    EXPECT_TRUE(s.apply(idle, &h.learner).heat);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "optimum_start"), "state")->valuestring, "applied");
    EXPECT_TRUE(cJSON_IsTrue(at(at(at(status.get(), "flow"), "optimum_start"), "estimate")));
    // With the outdoor known, both models count: no estimate.
    const auto both = WarmupPlanner::optimumStart(h.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), int16_t(500));
    EXPECT_TRUE(both.applicable()); EXPECT_FALSE(both.estimate);
}

// rc.4 (L3, R1-07): the default lead is applied as a capped estimate (floor 3 h until the arrival
// feedback is trusted), only on fresh readings, with the start's own rest after it ended, and for
// every room that needs it.
TEST(FlowPolicy, DefaultLeadsAreAppliedAsACappedEstimateWithARest) {
    ScopedTz tz(ScopedTz::amsterdam);
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.learner.setPlan(s.p); s.policy.setPlan(s.p);
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    const auto planned = WarmupPlanner::optimumStart(s.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt);
    ASSERT_STREQ(planned.confidence, "default");
    EXPECT_TRUE(planned.estimate);
    EXPECT_EQ(planned.leadS, WarmupPlanner::estimateCapFloorS) << "2.5 degC x 2 h would be 5 h: capped";
    EXPECT_EQ(WarmupPlanner::optimumStart(s.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt, {1.0f, true}).leadS, 18000u)
        << "a trusted factor lifts the cap";
    EXPECT_EQ(WarmupPlanner::optimumStart(s.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt, {0.5f, false}).leadS, 9000u);
    s.rooms[0] = room(1850, 1850); s.in.utc = planned.startUtc + 60;
    EXPECT_TRUE(s.apply(idle).heat);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));
    const cJSON* start = at(at(status.get(), "flow"), "optimum_start");
    EXPECT_STREQ(at(start, "state")->valuestring, "applied");
    EXPECT_STREQ(at(start, "confidence")->valuestring, "default");
    EXPECT_TRUE(cJSON_IsTrue(at(start, "estimate")));
    EXPECT_EQ(at(start, "rooms")->valueint, 1);
    // A stale reading is not served.
    s.rooms[0].status = RoomDemand::Status::stale; s.in.now += 6 * minute; s.in.utc = *s.in.utc + 360;
    EXPECT_FALSE(s.apply(idle).heat);
    s.rooms[0].status = RoomDemand::Status::ok;
    // Arrived 40 min before the rise: the start ends after its minimum on. A dip to 20.7 right
    // after plans a 40-minute start again (0.3 degC x 2 h): it waits the burner rest first.
    s.in.utc = *s.in.utc + 60; EXPECT_TRUE(s.apply(idle).heat);
    s.rooms[0] = room(2100, 1850); s.in.now += 6 * minute; s.in.utc = planned.rise.atUtc - 40 * 60;
    EXPECT_FALSE(s.apply(idle).heat);
    s.rooms[0] = room(2070, 1850); s.in.now += minute; s.in.utc = *s.in.utc + 60;
    EXPECT_FALSE(s.apply(idle).heat) << "within the rest";
    s.in.now += 6 * minute; s.in.utc = *s.in.utc + 360;
    EXPECT_TRUE(s.apply(idle).heat) << "after the rest";
    // Two rooms: both served, the higher flow wins. The radiator room rises to 22.5 degC (4 degC
    // from the setback: 3 h by default, capped at 90 min); 80 min before the rise both starts run.
    Step two; two.p = plan(RoomPlan::Emitter::floor, true);
    two.p.rooms.push_back(two.p.rooms[0]); two.p.rooms[1].id = "keuken"; two.p.rooms[1].emitter = RoomPlan::Emitter::radiator;
    for (auto& d : two.p.rooms[1].schedule.days) d.points[0].centiC = 2250;
    two.learner.setPlan(two.p); two.policy.setPlan(two.p); two.policy.setSettings(on);
    two.rooms[0] = room(1850, 1850); two.rooms[1] = room(1850, 1850);
    two.in.utc = planned.rise.atUtc - 80 * 60;
    const auto both = two.apply(idle);
    ASSERT_TRUE(both.heat);
    Json st(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(two.policy.addStatus(st.get(), false));
    EXPECT_EQ(at(at(at(st.get(), "flow"), "optimum_start"), "rooms")->valueint, 2);
    EXPECT_EQ(both.flowC, two.learner.ruleFlow(400)) << "the radiator room's larger shortfall sets the flow";
    EXPECT_GT(both.flowC, two.learner.ruleFlow(250));
}

// rc.4 (L1, R1-07): a start whose room arrived while the burner's minimum on still held kept
// `apply` true but forgot its rooms (heating_ took the empty wants), so when the hold ended no
// room had "arrived": the start never ended and never rested, and a dip of 0.3 degC a minute
// later restarted the burner at once. A held-on start keeps its rooms and rests after it.
TEST(FlowPolicy, AStartThatArrivesWithinItsMinimumOnStillRestsAfterwards) {
    ScopedTz tz(ScopedTz::amsterdam);
    Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.learner.setPlan(s.p); s.policy.setPlan(s.p);
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    const auto planned = WarmupPlanner::optimumStart(s.learner, 0, s.p.rooms[0].schedule, wednesday23, int16_t(1850), std::nullopt);
    ASSERT_STREQ(planned.confidence, "default");
    EXPECT_TRUE(planned.estimate);
    // 45 min before the rise the room still reads its night 18.5 degC: the (late) default start begins.
    s.rooms[0] = room(1850, 1850); s.in.utc = planned.rise.atUtc - 45 * 60;
    ASSERT_TRUE(s.apply(idle).heat);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
    // A minute later the room reads 21.0: arrived within the 5-minute minimum on, the burner stays on.
    s.rooms[0] = room(2100, 1850); s.in.now += minute; s.in.utc = *s.in.utc + 60;
    EXPECT_TRUE(s.apply(idle).heat) << "held on for the minimum on time";
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
    // Six minutes later the hold is over: the start ends.
    s.in.now += 6 * minute; s.in.utc = *s.in.utc + 360;
    EXPECT_FALSE(s.apply(idle).heat);
    // A dip to 20.7 right after plans a 40-minute start again (0.3 degC x 2 h): the burner rests first.
    s.rooms[0] = room(2070, 1850); s.in.now += minute; s.in.utc = *s.in.utc + 60;
    EXPECT_FALSE(s.apply(idle).heat) << "within the rest of a start that arrived during its minimum on";
    s.in.now += 6 * minute; s.in.utc = *s.in.utc + 360;
    EXPECT_TRUE(s.apply(idle).heat) << "after the rest";
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
}

// rc.4 (L2): a morning that arrived late raises the room's lead factor through the policy, so the
// next morning starts earlier; the status shows the estimate and the arrival.
TEST(FlowPolicy, ALateMorningStartsTheNextOneEarlier) {
    ScopedTz tz(ScopedTz::amsterdam);
    RoomSchedule mild;                                         // 06:30 -> 21 degC, 22:30 -> 20 degC: 1 degC, 2 h by default
    for (auto& d : mild.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 2000}; d.count = 2; }
    Step s; s.p = plan(RoomPlan::Emitter::floor); s.p.rooms[0].schedule = mild; s.learner.setPlan(s.p); s.policy.setPlan(s.p);
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    const int64_t rise = wednesday23 + 7 * 3600 + 1800;        // Thursday 06:30 local
    const auto first = WarmupPlanner::optimumStart(s.learner, 0, mild, wednesday23, int16_t(2000), std::nullopt);
    EXPECT_EQ(first.leadS, 7200u);
    int64_t startedAt = 0;
    const int64_t arriveAt = rise + 15 * 60;                   // the room is within 0.1 degC of 21 only 15 min after the switch
    for (int64_t t = wednesday23; t <= rise + 30 * 60; t += 60) {
        int16_t temp = 2000;
        if (startedAt) temp = t < arriveAt ? int16_t(2000 + 90 * (t - startedAt) / std::max<int64_t>(60, arriveAt - startedAt)) : int16_t(2100);
        s.rooms[0] = room(temp, t < rise ? 2000 : 2100);
        s.in.now += minute; s.in.utc = t; s.in.rule = t < rise ? idle : FlowDemand::Request{true, 40, FlowDemand::Reason::heating};
        const auto out = s.policy.apply(s.in, s.learner);
        if (out.heat && !startedAt) startedAt = t;
    }
    EXPECT_NEAR(double(startedAt), double(rise - 7200), 120);
    EXPECT_EQ(s.policy.arrival().events(0), 1u);
    EXPECT_NEAR(s.policy.arrival().lead(0).factor, 1.10f, 1e-5);
    ASSERT_TRUE(s.policy.arrival().lastErrorMin(0));
    EXPECT_GE(*s.policy.arrival().lastErrorMin(0), 11); EXPECT_LE(*s.policy.arrival().lastErrorMin(0), 16);
    const auto next = WarmupPlanner::optimumStart(s.learner, 0, mild, wednesday23 + 86400, int16_t(2000), std::nullopt, s.policy.arrival().lead(0));
    EXPECT_EQ(next.leadS, 8100u) << "7200 x 1.1 = 7920, the next 5-minute step";
    // The arrival travels with the plans telemetry.
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temps{}; temps[0] = 2000;
    Json plans(WarmupPlanner::json(s.learner, s.p, wednesday23 + 86400, temps.data(), std::nullopt, &s.policy.arrival()), cJSON_Delete);
    const cJSON* r0 = cJSON_GetArrayItem(at(plans.get(), "rooms"), 0);
    EXPECT_EQ(at(at(r0, "arrival"), "events")->valueint, 1);
    EXPECT_TRUE(cJSON_IsTrue(at(at(r0, "optimum_start"), "estimate")));
    EXPECT_EQ(at(at(r0, "optimum_start"), "lead_minutes")->valueint, 135);
}

// rc.5 (P3): one morning of free heat for the policy's FreeHeat: the floor's heat ends at 02:00 and
// the room rises `kPerH` without it until 07:00, so 04:00-07:00 is one judged window of the 4-8 daypart.
void freeMorning(FreeHeat& f, uint64_t& now, int64_t midnight, double kPerH) {
    const auto step = [&](int64_t u, double c, bool heat) {
        now += 10 * second;
        const FreeHeat::RoomSample s{int16_t(std::lround(c * 10) * 10), heat};
        f.sample(now, u, int16_t(500), &s, 1);
    };
    for (int64_t u = midnight; u < midnight + 2 * 3600; u += 10) step(u, 20.0, true);
    for (int64_t u = midnight + 2 * 3600; u < midnight + 7 * 3600; u += 10) step(u, 20.0 + kPerH * double(u - midnight - 2 * 3600) / 3600, false);
    step(midnight + 7 * 3600, 21.0, true);
}
// rc.5 (P3): a room that warms by itself in the morning (5 judged windows of 4-8) starts Smart warm-up
// later: lead x (1 - free / warm), never below half; with 4 windows the default lead stays.
TEST(FlowPolicy, FreeHeatStartsTheWarmUpLaterNeverBelowHalf) {
    ScopedTz tz(ScopedTz::amsterdam);
    RoomSchedule mild;                                         // 06:30 -> 21 degC, 22:30 -> 20 degC: 1 degC, 2 h by default
    for (auto& d : mild.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 2000}; d.count = 2; }
    const int64_t thursday = wednesday23 + 3600, monday = thursday + 4 * 86400; // local midnights, after the DST change
    const int64_t rise = monday + 6 * 3600 + 1800;
    const auto startOf = [&](int windows, double kPerH) {
        Step s; s.p = plan(RoomPlan::Emitter::floor); s.p.rooms[0].schedule = mild; s.learner.setPlan(s.p); s.policy.setPlan(s.p);
        FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
        uint64_t now = 0;
        for (int d = 0; d < windows; ++d) freeMorning(s.policy.freeHeat(), now, thursday + (d - 1) * 86400, kPerH);
        EXPECT_EQ(s.policy.freeHeat().count(0, 5), windows);
        int64_t startedAt = 0;
        for (int64_t t = monday + 3 * 3600; t < rise && !startedAt; t += 60) {
            s.rooms[0] = room(2000, 2000); s.in.now += minute; s.in.utc = t; s.in.rule = idle;
            if (s.policy.apply(s.in, s.learner).heat) startedAt = t;
        }
        return std::pair<int64_t, uint16_t>{startedAt, s.policy.freeHeat().appliedMin(0)};
    };
    EXPECT_EQ(startOf(0, 0).first, rise - 7200) << "no free heat: the default 2 h";
    EXPECT_EQ(startOf(4, 0.2).first, rise - 7200) << "4 windows: not yet";
    const auto [start, applied] = startOf(5, 0.2);
    EXPECT_EQ(start, rise - 4320) << "the warm-up (05:30) lies in 4-8: 1 - 0.2 / 0.5 of 2 h";
    EXPECT_EQ(applied, 48);
    EXPECT_EQ(startOf(5, 0.6).first, rise - 3600) << "1 - 1.2: never below half the lead";
    EXPECT_EQ(startOf(5, -0.1).first, rise - 7200) << "a room that cools by itself keeps its lead";
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
    FlowSettings on = Step::off(); on.weatherCurve = on.applyLearned = true; on.designFlowC = 55; s.policy.setSettings(on);
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
    // rc.3: how far the curve learned, for "standard for now (2 of 6 steady periods)" / "learned for your house".
    const cJSON* curve = at(at(root.get(), "flow"), "curve");
    EXPECT_TRUE(cJSON_IsNumber(at(curve, "windows")));
    EXPECT_EQ(at(curve, "windows")->valuedouble, s.policy.curveLearner().windows());
    // rc.5 (P1): fw/telemetry/flow as TelemetryPublisher::summary() splits it, with the boiler's object
    // at its widest (BoilerResponseWidest.h) and no cap in effect ("ceiling_c": null is wider than a number).
    const auto withBoiler = heatingSummaryTelemetry(h.learner, c, cJSON_CreateObject(), &s.policy,
                                                    [](cJSON* root) { return widestBoilerResponse().addJson(root); });
    Json doc(cJSON_Parse(withBoiler.c_str()), cJSON_Delete), flowTopic(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(doc);
    cJSON_AddNumberToObject(flowTopic.get(), "schema", 1);
    for (const char* key : {"flow", "night_gas", "boiler"}) {
        cJSON* part = cJSON_DetachItemFromObjectCaseSensitive(doc.get(), key);
        ASSERT_TRUE(part) << key;
        cJSON_AddItemToObject(flowTopic.get(), key, part);
    }
    char* text = cJSON_PrintUnformatted(flowTopic.get());
    const std::string flow = text ? text : "";
    cJSON_free(text);
    std::printf("[ flow policy ] worst-case fw/telemetry/flow %zu B: %s\n", flow.size(), flow.c_str());
    EXPECT_LE(flow.size(), heating::control::telemetrySoftBytes);
    EXPECT_TRUE(cJSON_IsNull(at(at(flowTopic.get(), "flow"), "ceiling_c")));
    EXPECT_STREQ(at(at(flowTopic.get(), "boiler"), "state")->valuestring, "not_driving");
}

// rc.5 (P1): the ceiling the boiler itself showed (BoilerResponse). With Smart warm-up on and the
// E32 driving the boiler no request goes above it, never below the plan's minimum either; the flow
// document shows the cap in effect ("ceiling_c", null without one) and "held" while it bound.
TEST(FlowPolicy, TheBoilersCeilingCapsTheRequestWhileTheE32Drives) {
    Step s;
    s.rooms[0] = room(2050, 2100); // rc.5: half a degree short, near its target: where the ceiling applies
    s.in.outdoorCentiC = -1000;
    const FlowDemand::Request rule{true, 50, FlowDemand::Reason::heating};
    const auto summary = [&](const char* key) {
        Json o(cJSON_CreateObject(), cJSON_Delete);
        EXPECT_TRUE(s.policy.addSummary(o.get()));
        const cJSON* flow = at(o.get(), "flow");
        const cJSON* v = std::string(key) == "learned" ? at(at(flow, "learned"), "state") : at(flow, key);
        return v && cJSON_IsString(v) ? std::string(v->valuestring) : v && cJSON_IsNumber(v) ? std::to_string(v->valueint) : "null";
    };
    s.in.ceilingC = 42;
    EXPECT_EQ(s.apply(rule).flowC, 50) << "options off: the rule, byte for byte";
    s.in.ownRequest = true;
    EXPECT_EQ(s.apply(rule).flowC, 50) << "Smart warm-up off";
    EXPECT_EQ(summary("ceiling_c"), "null");
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    s.in.ownRequest = false;
    EXPECT_EQ(s.apply(rule).flowC, 50) << "another controller drives the boiler";
    EXPECT_EQ(summary("ceiling_c"), "null");
    s.in.ownRequest = true;
    auto out = s.apply(rule);
    EXPECT_TRUE(out.heat); EXPECT_EQ(out.flowC, 42); EXPECT_EQ(out.reason, rule.reason); EXPECT_FALSE(out.capped);
    EXPECT_EQ(summary("ceiling_c"), "42");
    EXPECT_EQ(summary("learned"), "held");
    Json status(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.policy.addStatus(status.get(), false));     // the page's form
    EXPECT_EQ(at(at(status.get(), "flow"), "ceiling_c")->valuedouble, 42);
    EXPECT_STREQ(at(at(at(status.get(), "flow"), "learned"), "state")->valuestring, "held");
    // Asking less than the ceiling: unchanged and not "held"; the cap still shows.
    EXPECT_EQ(s.apply(FlowDemand::Request{true, 38, FlowDemand::Reason::heating}).flowC, 38);
    EXPECT_EQ(summary("ceiling_c"), "42");
    EXPECT_EQ(summary("learned"), "not_ready");
    // The weather curve above it (42 + (40 - 30) / 2 = 47): capped as well.
    on.weatherCurve = true; s.policy.setSettings(on);
    EXPECT_EQ(s.apply(FlowDemand::Request{true, 40, FlowDemand::Reason::heating}).flowC, 42);
    EXPECT_EQ(s.policy.source(), FlowPolicy::Source::curve);
    // Never below the plan's minimum (30), and the boiler's own limit still wins below it.
    s.in.ceilingC = 25;
    EXPECT_EQ(s.apply(rule).flowC, 30);
    s.in.boilerLimitC = 28;
    EXPECT_EQ(s.apply(rule).flowC, 28);
    s.in.boilerLimitC.reset();
    // None learned: the curve's 52 again. Whether to heat stays the rule's.
    s.in.ceilingC.reset();
    EXPECT_EQ(s.apply(rule).flowC, 52);
    s.in.ceilingC = 42;
    EXPECT_FALSE(s.apply(idle).heat);
}

// rc.5: the ceiling is what the house absorbs near its targets. A room a warm-up short (1 K or more,
// FlowPolicy::warmupCapCentiC) gets the full request, so a cold morning is not slowed by yesterday's
// holds; held targets are not counted during warm-ups either (BoilerResponse), so the two agree.
TEST(FlowPolicy, TheCeilingDoesNotCapAWarmUp) {
    Step s;
    s.in.outdoorCentiC = -1000;
    FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
    s.in.ownRequest = true; s.in.ceilingC = 42;
    const FlowDemand::Request rule{true, 50, FlowDemand::Reason::heating};
    s.rooms[0] = room(1950, 2100);                          // 1.5 K short: a warm-up
    EXPECT_EQ(s.apply(rule).flowC, 50) << "a warm-up gets the full request";
    Json o(cJSON_CreateObject(), cJSON_Delete);
    EXPECT_TRUE(s.policy.addSummary(o.get()));
    EXPECT_TRUE(cJSON_IsNull(at(at(o.get(), "flow"), "ceiling_c"))) << "no cap in effect";
    s.rooms[0] = room(2000, 2100);                          // exactly 1 K: still a warm-up
    EXPECT_EQ(s.apply(rule).flowC, 50);
    s.rooms[0] = room(2010, 2100);                          // 0.9 K: near the target, the ceiling applies
    EXPECT_EQ(s.apply(rule).flowC, 42);
    // (The lead room, the usable room with the largest error, decides: see apply().)
}

// rc.5 (P1): an optimum start under the boiler's ceiling asks at most the ceiling, and its lead is
// the learned warm-up time at that lower flow: it starts earlier, so the room is still warm on time.
TEST(FlowPolicy, AnOptimumStartUnderTheCeilingStartsEarlierAtThatFlow) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan(RoomPlan::Emitter::floor, true)); h.learn();
    const auto schedule = plan(RoomPlan::Emitter::floor, true).rooms[0].schedule;
    const auto free = WarmupPlanner::optimumStart(h.learner, 0, schedule, wednesday23, int16_t(1850), int16_t(500));
    ASSERT_STREQ(free.confidence, "learned");
    ASSERT_GE(free.flowC, 38);
    const uint8_t ceiling = uint8_t(free.flowC - 4);
    const auto capped = WarmupPlanner::optimumStart(h.learner, 0, schedule, wednesday23, int16_t(1850), int16_t(500), {}, ceiling);
    EXPECT_EQ(capped.flowC, ceiling);
    EXPECT_GT(capped.leadS, free.leadS) << "a lower flow warms slower";
    ASSERT_LT(capped.startUtc, free.startUtc);
    const auto expected = h.learner.warmupSeconds(0, int16_t(free.rise.toCentiC - capped.startTemperatureCentiC), ceiling, int16_t(500));
    ASSERT_TRUE(expected);
    EXPECT_GE(capped.leadS, std::min<uint32_t>(*expected, WarmupPlanner::maxLeadS)) << "the learned time at the ceiling";
    EXPECT_EQ(WarmupPlanner::optimumStart(h.learner, 0, schedule, wednesday23, int16_t(1850), int16_t(500), {}, uint8_t(free.flowC + 6)).leadS, free.leadS)
        << "a ceiling above the start's flow changes nothing";
    // Applied: between the two start times only the capped plan heats, at the ceiling.
    const int64_t between = capped.startUtc + (free.startUtc - capped.startUtc) / 2;
    const auto run = [&](std::optional<uint8_t> c) {
        Step s; s.p = plan(RoomPlan::Emitter::floor, true); s.in.outdoorCentiC = 500;
        FlowSettings on = Step::off(); on.applyLearned = true; s.policy.setSettings(on);
        s.rooms[0] = room(1850, 1850);
        s.in.ownRequest = true; s.in.ceilingC = c; s.in.utc = between;
        const auto out = s.apply(idle, &h.learner);
        if (out.heat) EXPECT_EQ(s.policy.source(), FlowPolicy::Source::optimumStart);
        return out;
    };
    const auto withCeiling = run(ceiling);
    ASSERT_TRUE(withCeiling.heat);
    EXPECT_LE(withCeiling.flowC, ceiling);
    EXPECT_FALSE(run(std::nullopt).heat) << "without the ceiling it is not time yet";
}
}
