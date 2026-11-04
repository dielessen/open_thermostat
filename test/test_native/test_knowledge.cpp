#include "control/Knowledge.h"
#include "control/ShadowComparison.h"
#include "SyntheticHouse.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <memory>
#include <string>
#include <vector>

// rc.5 (P2): Knowledge, one figure for how much the E32 learned about the house and the keys of
// what it still misses, and the insight topic's document (fw/telemetry/insight) at its worst case.
namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
const int64_t monday = int64_t(ShadowComparison::daysFromCivil(2026, 11, 2)) * 86400 + 7 * 3600; // 08:00 CET

// Any class with state() and addJson() stands in for P1's BoilerResponse. width: the "boiler" member's
// bytes (P1's bound is 140 B).
struct FakeBoiler {
    const char* s = "not_driving";
    size_t width = 0;
    const char* state() const { return s; }
    bool addJson(cJSON* parent) const {
        cJSON* o = cJSON_AddObjectToObject(parent, "boiler");
        const size_t fixed = std::string(R"("boiler":{"state":""})").size();
        return o && cJSON_AddStringToObject(o, "state", width > fixed ? std::string(width - fixed, 'x').c_str() : s);
    }
};
RoomSchedule rising() {
    RoomSchedule s;
    for (auto& d : s.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
    return s;
}
// Six steady 3-hour windows: the room at its target, 15 K colder outside, the burner on half the time at 40 degC.
void learnCurve(CurveLearner& c) {
    uint64_t now = 0;
    for (int i = 0; i < 7 * 1081; ++i) {
        now += 10000;
        CurveLearner::Sample s;
        s.room = 0; s.roomCentiC = 2000; s.setpointCentiC = 2000; s.outdoorCentiC = 500; s.flowCentiC = 4000;
        s.burnerOn = (i / 30) % 2 == 0; s.hotWater = false;
        c.sample(now, s);
    }
}
// Three mornings warm on time: trusted.
void trustArrival(ArrivalLearner& a, size_t room) {
    for (int d = 0; d < 3; ++d) {
        const int64_t at = monday + d * 86400;
        const ArrivalLearner::Rise rise{at, at - 3600, 2100};
        a.observe(room, at - 3600, rise, true, int16_t(1800));
        a.observe(room, at, rise, true, int16_t(2100));
    }
}
// The E32 asks 35 degC, a room is cold and the boiler does not fire for 16 minutes: a minimum of 37 degC.
void learnMinimum(FlowLearner& l, size_t rooms) {
    uint64_t now = 0;
    std::vector<FlowLearner::RoomInput> in(rooms);
    for (auto& r : in) { r.temperatureCentiC = 1900; r.setpointCentiC = 2100; r.source = 0; }
    for (int i = 0; i < 6 * 16; ++i) {
        now += 10000;
        FlowLearner::Boiler b;
        b.flowCentiC = 3000; b.burnerOn = false; b.hotWater = false; b.requestedFlowC = 35; b.ownRequest = true;
        l.sample(now, b, in.data(), in.size());
    }
}
std::vector<std::string> keys(const Knowledge::Result& r, const RoomPlan& plan) {
    std::vector<std::string> out;
    for (size_t i = 0; i < r.count; ++i) out.push_back(Knowledge::text(r.missing[i], plan));
    return out;
}
std::string print(const cJSON* o) { char* t = cJSON_PrintUnformatted(o); std::string s = t ? t : ""; cJSON_free(t); return s; }
// fw/telemetry/insight as TelemetryPublisher::summary() publishes it: {"schema":1,<the insight's members>}.
std::string published(const cJSON* summary) {
    Json doc(cJSON_CreateObject(), cJSON_Delete);
    cJSON_AddNumberToObject(doc.get(), "schema", 1);
    for (const cJSON* m = cJSON_GetObjectItem(summary, "insight")->child; m; m = m->next) cJSON_AddItemToObject(doc.get(), m->string, cJSON_Duplicate(m, true));
    return print(doc.get());
}

// Everything learned: the synthetic house's two rooms with week programs, the curve, three mornings
// each, the boiler's response, and the house model.
struct Learned {
    SyntheticHouse house{2};
    CurveLearner curve;
    ArrivalLearner arrival;
    FakeBoiler boiler{"learned"};
    HouseModel model;
    Learned() {
        for (auto& r : house.plan.rooms) r.schedule = rising();
        house.learner.setPlan(house.plan);
        house.learn();
        house.learner.setApplied(true);
        learnCurve(curve);
        arrival.setPlan(house.plan);
        trustArrival(arrival, 0); trustArrival(arrival, 1);
        model.update({&house.learner, nullptr, std::nullopt, &house.plan});
    }
    Knowledge::Result percent() const { return Knowledge::percent(house.learner, curve, arrival, &boiler, model, house.plan); }
};
}

TEST(Knowledge, NothingLearnedIsZeroAndEveryPartIsNamed) {
    RoomPlan plan;
    for (const char* id : {"woonkamer", "keuken", "zolder"}) { RoomPlan::Room r; r.id = r.name = id; r.state = RoomDemand::State::active; plan.rooms.push_back(r); }
    plan.rooms[0].schedule = rising();                        // only the living room has a morning rise
    plan.rooms[2].state = RoomDemand::State::inactive;        // an inactive room is no part of it
    FlowLearner learner; learner.setPlan(plan); learner.setApplied(true);
    CurveLearner curve; ArrivalLearner arrival; arrival.setPlan(plan);
    HouseModel house; house.update({&learner, nullptr, std::nullopt, &plan});
    const auto r = Knowledge::percent(learner, curve, arrival, nullptr, house, plan);
    EXPECT_EQ(r.pct, 0);
    EXPECT_EQ(keys(r, plan), (std::vector<std::string>{"warmup:woonkamer", "warmup:keuken", "cooling:woonkamer", "cooling:keuken", "curve",
                                                       "arrival:woonkamer", "boiler_minimum", "boiler_response", "house"}));
}

TEST(Knowledge, EverythingLearnedIsAHundredAndEachPartHasItsWeight) {
    Learned l;
    ASSERT_STREQ(l.model.state(), "learned");
    ASSERT_TRUE(l.curve.slope());
    auto r = l.percent();
    EXPECT_EQ(r.pct, 100) << ::testing::PrintToString(keys(r, l.house.plan));
    EXPECT_EQ(r.count, 0u);
    // The boiler's response not learned and the E32 not driving the boiler (no minimum learned): 80 %.
    l.boiler.s = "not_driving";
    r = l.percent();
    EXPECT_EQ(r.pct, 80);
    EXPECT_EQ(keys(r, l.house.plan), (std::vector<std::string>{"boiler_minimum", "boiler_response"}));
    // Driving (any other state): the minimum counts; the response still waits for "learned".
    l.boiler.s = "collecting";
    EXPECT_EQ(l.percent().pct, 90);
    // One of two rooms without three judged mornings: half of arrival's 15 (82.5 rounded down).
    ArrivalLearner one; one.setPlan(l.house.plan); trustArrival(one, 1);
    r = Knowledge::percent(l.house.learner, l.curve, one, &l.boiler, l.model, l.house.plan);
    EXPECT_EQ(r.pct, 82);
    EXPECT_EQ(keys(r, l.house.plan), (std::vector<std::string>{"arrival:room0", "boiler_response"}));
    // Without the curve's six steady periods: 15 less.
    CurveLearner fresh;
    EXPECT_EQ(Knowledge::percent(l.house.learner, fresh, one, &l.boiler, l.model, l.house.plan).pct, 67);
}

// Only rooms whose week program rises have mornings to judge; with Smart warm-up off there are none.
TEST(Knowledge, ArrivalCountsOnlyWhereThereIsAMorningToJudge) {
    Learned l;
    for (auto& r : l.house.plan.rooms) r.schedule = RoomSchedule{};      // no programs: nothing to judge
    ArrivalLearner none; none.setPlan(l.house.plan);
    auto r = Knowledge::percent(l.house.learner, l.curve, none, &l.boiler, l.model, l.house.plan);
    EXPECT_EQ(r.pct, 100);
    for (auto& room : l.house.plan.rooms) room.schedule = rising();
    l.house.learner.setApplied(false);                                   // Smart warm-up off
    r = Knowledge::percent(l.house.learner, l.curve, none, &l.boiler, l.model, l.house.plan);
    EXPECT_EQ(r.pct, 100);
    l.house.learner.setApplied(true);
    EXPECT_EQ(Knowledge::percent(l.house.learner, l.curve, none, &l.boiler, l.model, l.house.plan).pct, 85);
    // The week wraps around: a program whose only rise is Monday's first point after Sunday's last.
    RoomSchedule wrap;
    wrap.days[0].points[0] = {390, 2100}; wrap.days[0].count = 1;
    wrap.days[6].points[0] = {1350, 1800}; wrap.days[6].count = 1;
    EXPECT_TRUE(Knowledge::hasRise(wrap));
    RoomSchedule flat;
    for (auto& d : flat.days) { d.points[0] = {0, 2000}; d.count = 1; }
    EXPECT_FALSE(Knowledge::hasRise(flat));
    EXPECT_FALSE(Knowledge::hasRise(RoomSchedule{}));
    EXPECT_TRUE(Knowledge::hasRise(rising()));
}

// The boiler minimum: learned by the learner, or the E32 drives the boiler (it would have found one).
TEST(Knowledge, TheBoilerMinimumIsKnownWhenLearnedOrWhileTheE32Drives) {
    RoomPlan plan;
    RoomPlan::Room room; room.id = room.name = "woonkamer"; room.state = RoomDemand::State::active; plan.rooms.push_back(room);
    FlowLearner learner; learner.setPlan(plan);
    CurveLearner curve; ArrivalLearner arrival; arrival.setPlan(plan); HouseModel house;
    const auto has = [&](const FakeBoiler* b) {
        const auto r = b ? Knowledge::percent(learner, curve, arrival, b, house, plan) : Knowledge::percent(learner, curve, arrival, nullptr, house, plan);
        const auto k = keys(r, plan);
        return std::find(k.begin(), k.end(), "boiler_minimum") == k.end();
    };
    const FakeBoiler shadow{"not_driving"}, driving{"no_return"};
    EXPECT_FALSE(has(nullptr)); EXPECT_FALSE(has(&shadow)); EXPECT_TRUE(has(&driving));
    learnMinimum(learner, 1);
    ASSERT_EQ(learner.boilerMinimum().learnedC(), 37);
    EXPECT_TRUE(has(nullptr)); EXPECT_TRUE(has(&shadow));
}

// The document as published: the shape, then the worst case within 700 B (eight rooms with 32-character
// ids and nothing learned, four room insights, a boiler member of P1's full 140 B).
TEST(Knowledge, TheInsightDocumentStaysWithinItsBound) {
    {
        Learned l;
        l.boiler.s = "not_driving";
        const auto r = l.percent();
        Insights insights;
        for (int i = 0; i < 5; ++i) { Insights::Day d; d.heated = true; d.gasPerDegreeDay = 2.0f; d.warmupMinPerC[1] = 40; insights.dayChange(d); }
        Insights::Day y; y.heated = true; y.gasPerDegreeDay = 2.8f; y.warmupMinPerC[1] = 60;
        insights.dayChange(y);
        Json summary(cJSON_CreateObject(), cJSON_Delete);
        BoilerResponse stub;                                    // the stub (or P1's class once merged)
        ASSERT_TRUE(addInsightJson(summary.get(), r, l.model, &l.boiler, insights, l.house.plan));
        const auto doc = published(summary.get());
        std::printf("[ insight ] typical %zu B: %s\n", doc.size(), doc.c_str());
        Json parsed(cJSON_Parse(doc.c_str()), cJSON_Delete);
        ASSERT_TRUE(parsed);
        const cJSON* k = cJSON_GetObjectItem(parsed.get(), "knowledge");
        EXPECT_EQ(cJSON_GetObjectItem(k, "pct")->valueint, 80);
        EXPECT_EQ(print(cJSON_GetObjectItem(k, "missing")), R"(["boiler_minimum","boiler_response"])");
        EXPECT_EQ(cJSON_GetObjectItem(k, "more")->valueint, 0);
        EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(parsed.get(), "house"), "state")->valuestring, "learned");
        EXPECT_EQ(print(cJSON_GetObjectItem(parsed.get(), "insights")),
                  R"([{"kind":"gas_per_dd_up","pct":40},{"kind":"warmup_slower","pct":50,"room":"room1"}])");
        // As HeatingController publishes it while the E32 drives the boiler (the stub until P1's BoilerResponse lands).
        BoilerResponse::Sample driving; driving.ownRequest = true; driving.returnCentiC = 3500;
        stub.sample(driving);
        const auto withStubKnowledge = Knowledge::percent(l.house.learner, l.curve, l.arrival, &stub, l.model, l.house.plan);
        Json withStub(cJSON_CreateObject(), cJSON_Delete);
        ASSERT_TRUE(addInsightJson(withStub.get(), withStubKnowledge, l.model, &stub, insights, l.house.plan));
        std::printf("[ insight ] as published with the boiler stub %zu B: %s\n", published(withStub.get()).size(), published(withStub.get()).c_str());
        Json none(cJSON_CreateObject(), cJSON_Delete);
        ASSERT_TRUE(addInsightJson(none.get(), r, l.model, nullptr, insights, l.house.plan));
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(none.get(), "insight"), "boiler")));
    }
    SyntheticHouse worst(8, 32);
    for (auto& room : worst.plan.rooms) room.schedule = rising();
    worst.learner.setPlan(worst.plan); worst.learner.setApplied(true);
    CurveLearner curve; ArrivalLearner arrival; arrival.setPlan(worst.plan);
    HouseModel house; house.update({&worst.learner, nullptr, 0.123456f, &worst.plan});
    const auto r = Knowledge::percent(worst.learner, curve, arrival, nullptr, house, worst.plan);
    ASSERT_EQ(r.count, 3 * 8 + 4u) << "warm-up, cooling and arrival per room, the curve, the boiler's two and the house";
    Insights insights;
    for (int i = 0; i < 5; ++i) { Insights::Day d; d.heated = true; for (auto& w : d.warmupMinPerC) w = 20; insights.dayChange(d); }
    Insights::Day y; y.heated = true; for (auto& w : y.warmupMinPerC) w = 999;
    insights.dayChange(y);
    ASSERT_EQ(insights.count(), 4u);
    const FakeBoiler wide{"not_driving", 140};
    Json summary(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addInsightJson(summary.get(), r, house, &wide, insights, worst.plan));
    const auto doc = published(summary.get());
    std::printf("[ insight ] worst case %zu B of %zu: %s\n", doc.size(), insightMaxBytes, doc.c_str());
    EXPECT_LE(doc.size(), insightMaxBytes);
    Json parsed(cJSON_Parse(doc.c_str()), cJSON_Delete);
    const cJSON* k = cJSON_GetObjectItem(parsed.get(), "knowledge");
    const int shown = cJSON_GetArraySize(cJSON_GetObjectItem(k, "missing"));
    EXPECT_GE(shown, 1) << "the first missing keys still fit";
    EXPECT_EQ(shown + cJSON_GetObjectItem(k, "more")->valueint, int(r.count));
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(parsed.get(), "insights")), 4);
    // Short ids: at most eight keys, the rest counted in "more"; the page takes them all.
    SyntheticHouse eight(8);
    eight.learner.setApplied(true);
    const auto all = Knowledge::percent(eight.learner, curve, arrival, nullptr, house, eight.plan);
    Json mqtt(cJSON_CreateObject(), cJSON_Delete), page(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addInsightJson(mqtt.get(), all, house, &wide, Insights{}, eight.plan));
    ASSERT_TRUE(addInsightJson(page.get(), all, house, &wide, Insights{}, eight.plan, all.missing.size(), SIZE_MAX));
    const auto missingOf = [](const cJSON* root) { return cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetObjectItem(root, "insight"), "knowledge"), "missing"); };
    EXPECT_EQ(cJSON_GetArraySize(missingOf(mqtt.get())), int(insightMaxKeys));
    EXPECT_EQ(cJSON_GetArraySize(missingOf(page.get())), int(all.count));
    EXPECT_LE(published(mqtt.get()).size(), insightMaxBytes);
}
