#include "control/ActiveHeatGuard.h"
#include "control/DhwEpisodes.h"
#include "control/HeatingTelemetry.h"
#include "control/RoomEngine.h"
#include "control/ShadowComparison.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <vector>

namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;

std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}

// Eight plan rooms with realistic ids/names, an HA climate (source and
// setpoint) and a Bluetooth sensor each, alternating floor and radiator,
// all with the owner's week program.
RoomPlan eightRooms() {
    static const char* ids[8] = {"woonkamer", "keuken", "badkamer", "slaapkamer_voor", "slaapkamer_achter", "werkkamer", "logeerkamer", "zolder_studio"};
    static const char* names[8] = {"Woonkamer", "Keuken", "Badkamer", "Slaapkamer voor", "Slaapkamer achter", "Werkkamer", "Logeerkamer", "Zolder studio"};
    RoomPlan plan;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = ids[i]; r.name = names[i];
        r.emitter = i % 2 ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        char ble[13]; std::snprintf(ble, sizeof ble, "a4c138a3e8%02x", i);
        r.sources = {{RoomPlan::SourceType::ha, std::string("climate.") + ids[i]}, {RoomPlan::SourceType::ble, ble}};
        r.setpointEntity = std::string("climate.") + ids[i];
        for (auto& d : r.schedule.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
        plan.rooms.push_back(r);
    }
    return plan;
}

// Trains every room of the learner to "ready" with a heat model (synthetic
// house as in test_flow_learner: rate = a (flow - room) - b (room - outdoor)).
void train(FlowLearner& learner, size_t rooms) {
    struct Room { double a, b, capacity, coastHours, T = 20, coast = 0; };
    std::vector<Room> house;
    for (size_t i = 0; i < rooms; ++i) house.push_back(i % 2 ? Room{0.1, 0.05, 3, 0.2} : Room{0.035, 0.02, 10, 1.5});
    uint64_t now = 0;
    double outdoor = 5;
    const auto run = [&](uint64_t ms, std::optional<double> flowC) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            const double dt = 10.0 / 3600;
            double heatKw = 0;
            for (auto& r : house) {
                const double emit = flowC ? r.a * (*flowC - r.T) : 0;
                if (flowC) r.coast = emit; else r.coast *= std::exp(-dt / r.coastHours);
                r.T += (flowC ? emit : r.coast) * dt - r.b * (r.T - outdoor) * dt;
                heatKw += r.capacity * emit;
            }
            FlowLearner::Boiler b;
            const double flow = flowC ? *flowC + ((now / (5 * minute)) % 2 ? 1 : -1) : house[0].T + 3;
            b.flowCentiC = int16_t(std::lround(flow * 100)); b.returnCentiC = int16_t(std::lround((flow - 5) * 100));
            b.burnerOn = flowC.has_value(); b.hotWater = false;
            b.requestedFlowC = flowC ? uint8_t(*flowC) : uint8_t(0);
            b.outdoorCentiC = int16_t(std::lround(outdoor * 100));
            b.modulationPct = uint8_t(std::clamp(std::lround(heatKw / FlowLearner::efficiency(flow - 5) / 22 * 100), 0L, 100L));
            std::vector<FlowLearner::RoomInput> in(house.size());
            for (size_t i = 0; i < house.size(); ++i) {
                in[i].temperatureCentiC = int16_t(std::lround(house[i].T * 10) * 10);
                in[i].setpointCentiC = 2100; in[i].source = 0;
            }
            learner.sample(now, b, in.data(), in.size());
        }
    };
    for (int c = 0; c < 3; ++c)
        for (const double o : {0.0, 10.0})
            for (const double f : {32.0, 36.0, 40.0, 44.0, 48.0, 52.0}) {
                outdoor = o;
                for (auto& r : house) r.T = 20;
                run(210 * minute, f); run(8 * hour, std::nullopt);
            }
    run(30 * minute, 40); // a room short of its setpoint now: "now" advice everywhere
}

// 2026-10-28 (Wednesday) 23:00 CET.
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;

// Assembled like HeatingController::heatingStatusJson.
Json fullStatus(const RoomPlan& plan, const FlowLearner& learner, bool clock) {
    RoomEngine engine; engine.setPlan(plan);
    const uint64_t now = 600 * minute;
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        engine.haState(plan.rooms[i].setpointEntity, int16_t(1960 + 10 * i), 2100, now - minute);
        engine.bleReading(plan.rooms[i].sources[1].id, int16_t(1955 + 10 * i), now - minute);
    }
    const auto request = engine.step(now, uint32_t(wednesday23));
    Json root(engine.json(), cJSON_Delete);
    cJSON* sensors = cJSON_AddArrayToObject(root.get(), "ble_sensors");
    for (size_t i = 0; i < 8; ++i) {
        cJSON* s = cJSON_CreateObject(); cJSON_AddItemToArray(sensors, s);
        cJSON_AddStringToObject(s, "id", plan.rooms[i].sources[1].id.c_str());
        cJSON_AddStringToObject(s, "name", ("Thermometer " + plan.rooms[i].name).c_str());
        cJSON_AddStringToObject(s, "profile", "pvvx");
        cJSON_AddNumberToObject(s, "temperature", 19.55 + i / 10.0); cJSON_AddNumberToObject(s, "humidity", 55.37);
        cJSON_AddNumberToObject(s, "battery", 87); cJSON_AddNumberToObject(s, "age_s", 42);
    }
    cJSON* burner = cJSON_AddObjectToObject(root.get(), "burner");
    cJSON_AddNumberToObject(burner, "starts_last_hour", 4); cJSON_AddNumberToObject(burner, "heating_starts_last_hour", 3);
    cJSON_AddBoolToObject(burner, "short_cycling", false);
    ShadowComparison shadow;
    for (int d = 0; d < 8; ++d)                          // a full week of past days plus today
        for (uint64_t t = 0; t < 24 * hour; t += 10 * minute)
            shadow.sample(d * 24 * hour + t, uint32_t(wednesday23 - (8 - d) * 86400 + t / 1000), request, uint8_t(t % (2 * hour) < hour ? 45 : 0));
    cJSON_AddItemToObject(root.get(), "shadow", shadow.json());
    ActiveHeatGuard guard;
    cJSON_AddItemToObject(root.get(), "active", guard.json(now));
    cJSON_AddBoolToObject(cJSON_GetObjectItem(root.get(), "active"), "enabled", false);
    std::vector<std::optional<int16_t>> temperatures;
    for (size_t i = 0; i < plan.rooms.size(); ++i) temperatures.push_back(engine.freshTemperature(i, now));
    LearnedContext context;
    if (clock) context.utc = wednesday23;
    context.temperatures = temperatures.data(); context.outdoorCentiC = int16_t(500); context.outdoorSource = "ha"; context.now = now;
    cJSON_AddItemToObject(root.get(), "learned", learnedJson(learner, plan, context));
    DhwEpisodes dhw;
    dhw.flow(25); dhw.flow(60);                          // live flow: peak reported
    for (uint64_t ms = 0; ms < 20 * 60000; ms += 60000) { dhw.state(0x0A, ms * 100); dhw.flow(85); dhw.state(0x00, ms * 100 + 30000); }
    cJSON_AddItemToObject(root.get(), "dhw", dhw.summaryJson());
    addHaLink(root.get(), now - 12 * second, now, true);
    return root;
}

TEST(HeatingTelemetry, HaLinkReportsTheInputAgeAndTheBroker) {
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addHaLink(root.get(), 1000, 43999, true));
    const cJSON* ha = cJSON_GetObjectItem(root.get(), "ha");
    EXPECT_EQ(cJSON_GetObjectItem(ha, "input_age_s")->valuedouble, 42);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(ha, "broker_connected")));
    Json none(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addHaLink(none.get(), std::nullopt, 5000, false));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(none.get(), "ha"), "input_age_s")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(cJSON_GetObjectItem(none.get(), "ha"), "broker_connected")));
    Json future(cJSON_CreateObject(), cJSON_Delete);  // never a negative age
    ASSERT_TRUE(addHaLink(future.get(), 9000, 5000, true));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(future.get(), "ha"), "input_age_s")));
}

TEST(HeatingTelemetry, EightLearnedRoomsWithPlansFitTheMqttPayload) {
    const auto plan = eightRooms();
    FlowLearner learner; learner.setPlan(plan);
    train(learner, plan.rooms.size());
    for (size_t i = 0; i < plan.rooms.size(); ++i) ASSERT_STREQ(learner.readiness(i), "ready") << i;
    const auto started = std::chrono::steady_clock::now();
    auto status = fullStatus(plan, learner, true);
    const auto ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    ASSERT_TRUE(status);
    const auto full = print(status.get());
    compactHeatingTelemetry(status.get());
    const auto mqtt = print(status.get());
    for (const cJSON* c = status->child; c; c = c->next) std::printf("DBG %s %zu;", c->string, print(c).size());
    for (const cJSON* c = cJSON_GetObjectItem(status.get(), "learned")->child; c; c = c->next) std::printf("DBG learned.%s %zu;", c->string, print(c).size());
    std::puts(print(cJSON_GetArrayItem(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "learned"), "rooms"), 0)).c_str());
    std::puts(print(cJSON_GetArrayItem(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "learned"), "plans"), "rooms"), 0)).c_str());
    std::puts(print(cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0)).c_str());
    std::puts(print(cJSON_GetObjectItem(status.get(), "shadow")).c_str());std::puts(print(cJSON_GetObjectItem(status.get(), "dhw")).c_str());
    std::printf("[ heating telemetry ] full %zu B, mqtt %zu B, host build %.1f ms\n", full.size(), mqtt.size(), ms);
    EXPECT_LE(mqtt.size(), 3500u);  // headroom under ModernTransport's heatingTelemetryMaxBytes (4096)
    // The compact form keeps the shape HA reads.
    const cJSON* learned = cJSON_GetObjectItem(status.get(), "learned");
    EXPECT_EQ(cJSON_GetObjectItem(learned, "schema")->valuedouble, 1);
    const cJSON* inputs = cJSON_GetObjectItem(learned, "inputs");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(inputs, "gas_meter")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(inputs, "gas_price")));
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "outdoor")->valuestring, "ha");
    EXPECT_EQ(cJSON_GetObjectItem(inputs, "boiler_kw")->valuedouble, 22);
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "boiler_kw_source")->valuestring, "default");
    const cJSON* room = cJSON_GetArrayItem(cJSON_GetObjectItem(learned, "rooms"), 0);
    EXPECT_STREQ(cJSON_GetObjectItem(room, "readiness")->valuestring, "ready");
    EXPECT_FALSE(cJSON_GetObjectItem(room, "curve"));
    ASSERT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(room, "advice")), 1);
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(room, "advice"), 0), "shortfall_c")->valuedouble, 1);
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(room, "now")));
    const cJSON* p = cJSON_GetArrayItem(cJSON_GetObjectItem(cJSON_GetObjectItem(learned, "plans"), "rooms"), 0);
    ASSERT_TRUE(p);
    EXPECT_STREQ(cJSON_GetObjectItem(p, "id")->valuestring, "woonkamer");
    const cJSON* start = cJSON_GetObjectItem(p, "optimum_start");
    EXPECT_STREQ(cJSON_GetObjectItem(start, "reason")->valuestring, "planned");
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(start, "predicted_start_utc")));
    EXPECT_TRUE(cJSON_IsBool(cJSON_GetObjectItem(start, "start_now")));
    EXPECT_FALSE(cJSON_GetObjectItem(start, "next_switch"));
    const cJSON* night = cJSON_GetObjectItem(p, "night");
    EXPECT_STREQ(cJSON_GetObjectItem(night, "reason")->valuestring, "estimated");
    EXPECT_TRUE(cJSON_IsString(cJSON_GetObjectItem(night, "recommended")));
    EXPECT_FALSE(cJSON_GetObjectItem(night, "strategies"));
    EXPECT_FALSE(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "shadow"), "days"));
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "shadow"), "today")));
    const cJSON* dhw = cJSON_GetObjectItem(status.get(), "dhw");
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(dhw, "today")));
    EXPECT_FALSE(cJSON_GetObjectItem(dhw, "last_7_days"));
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "ha"), "input_age_s")->valuedouble, 12);
    // The full form keeps everything for the page.
    Json again(cJSON_Parse(full.c_str()), cJSON_Delete);
    const cJSON* fullRoom = cJSON_GetArrayItem(cJSON_GetObjectItem(cJSON_GetObjectItem(again.get(), "learned"), "rooms"), 0);
    EXPECT_GT(cJSON_GetArraySize(cJSON_GetObjectItem(fullRoom, "curve")), 0);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(fullRoom, "advice")), 4);
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(cJSON_GetObjectItem(again.get(), "dhw"), "last_7_days")));
}

TEST(HeatingTelemetry, WithoutClockThereAreNoPlansAndANewLearnerIsSmall) {
    const auto plan = eightRooms();
    FlowLearner learner; learner.setPlan(plan);
    auto status = fullStatus(plan, learner, false);
    ASSERT_TRUE(status);
    const cJSON* learned = cJSON_GetObjectItem(status.get(), "learned");
    EXPECT_FALSE(cJSON_GetObjectItem(learned, "plans"));
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(learned, "rooms"), 7), "readiness")->valuestring, "collecting");
    compactHeatingTelemetry(status.get());
    EXPECT_LE(print(status.get()).size(), 3500u);
    // Compacting is idempotent and harmless on older documents.
    const auto once = print(status.get());
    compactHeatingTelemetry(status.get());
    EXPECT_EQ(print(status.get()), once);
    Json old(cJSON_Parse(R"({"schema":1,"rooms":[],"shadow":{"today":{},"days":[]}})"), cJSON_Delete);
    compactHeatingTelemetry(old.get());
    EXPECT_EQ(print(old.get()), R"({"schema":1,"rooms":[],"shadow":{"today":{}}})");
}
}
