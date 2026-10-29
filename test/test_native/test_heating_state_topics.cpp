#include "control/ActiveHeatGuard.h"
#include "control/ControlPartitionBudget.h"
#include "control/DhwEpisodes.h"
#include "control/HeatingStateTopics.h"
#include "control/RoomEngine.h"
#include "control/ShadowComparison.h"
#include "control/TelemetryPolicy.h"
#include <cmath>
#include <cstdio>
#include <gtest/gtest.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

// The telemetry budget (docs/modern-thermostat/TELEMETRIEBUDGET.nl.md): every
// MQTT document <= 1 KB (hard 1.5 KB) for a worst-case plan, deadbands and cadences.
namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;
constexpr uint64_t statusNow = 600 * minute;

std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}
std::string pad(std::string s, size_t n, char c) { s.resize(n, c); return s; }
struct Message { HeatingTopic kind; std::string topic, payload; };
std::vector<Message> split(cJSON* status) {
    std::vector<Message> out;
    EXPECT_TRUE(splitHeatingStatus(status, [&](HeatingTopic kind, const std::string& topic, const cJSON* doc) {
        out.push_back({kind, topic, print(doc)});
    }));
    return out;
}

// Eight rooms at their longest: 32-character ids, 40-character names (escaped
// to 6 bytes each when `escaped`), 4 HA sources and a setpoint entity of 80
// characters (40 entities), a Bluetooth sensor per room.
RoomPlan worstPlan(bool escaped = false) {
    RoomPlan plan;
    plan.revision = 4294967295u;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = pad(std::string(1, char('a' + i)) + "_", 32, char('a' + i));
        r.name = escaped ? std::string(40, '\x01') : pad("Room " + std::to_string(i) + " ", 40, 'x');
        r.state = RoomDemand::State::active;
        r.emitter = i % 2 ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        for (int s = 0; s < 4; ++s) r.sources.push_back({RoomPlan::SourceType::ha, pad("sensor." + r.id + char('0' + s) + "_", 80, 't')});
        r.setpointEntity = pad("climate." + r.id + "_", 80, 's');
        r.fallbackCentiC = 2155; r.minimumCentiC = 500; r.maximumCentiC = 2999;
        for (auto& d : r.schedule.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
        plan.rooms.push_back(r);
    }
    return plan;
}
// Trains every room to "ready" (the synthetic house of test_heating_telemetry).
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
    run(30 * minute, 40);
}
// The compact status as HeatingController::heatingStatusJson(true), every value at its longest.
Json worstStatus(const RoomPlan& plan) {
    RoomEngine engine; engine.setPlan(plan);
    for (const auto& room : plan.rooms) {
        for (const auto& src : room.sources) engine.haState(src.id, int16_t(-1234), std::nullopt, statusNow - minute);
        engine.haState(room.setpointEntity, std::nullopt, int16_t(2155), statusNow - minute);
    }
    engine.step(statusNow, uint32_t(wednesday23));
    Json root(engine.json(), cJSON_Delete);
    cJSON* sensors = cJSON_AddArrayToObject(root.get(), "ble_sensors");
    for (int i = 0; i < 8; ++i) {
        cJSON* s = cJSON_CreateObject(); cJSON_AddItemToArray(sensors, s);
        char id[13]; std::snprintf(id, sizeof id, "a4c138a3e8%02x", i);
        cJSON_AddStringToObject(s, "id", id);
        cJSON_AddStringToObject(s, "name", std::string(40, '"').c_str()); // 80 bytes escaped
        cJSON_AddStringToObject(s, "profile", "shelly_ht_display");
        cJSON_AddNumberToObject(s, "temperature", -12.34); cJSON_AddNumberToObject(s, "humidity", 99.99);
        cJSON_AddNumberToObject(s, "battery", 100); cJSON_AddNumberToObject(s, "age_s", 4294967);
    }
    BurnerCycleMonitor::Summary cycles; cycles.known = true; cycles.starts = cycles.heatingStarts = BurnerCycleMonitor::capacity;
    addBurnerJson(root.get(), cycles);
    ShadowComparison shadow;
    const FlowDemand::Request heat{true, 44, FlowDemand::Reason::heating};
    for (int d = 0; d < 8; ++d)
        for (uint64_t t = 0; t < 24 * hour; t += 10 * minute)
            shadow.sample(d * 24 * hour + t, uint32_t(wednesday23 - (8 - d) * 86400 + t / 1000),
                          t % (3 * hour) < hour ? heat : FlowDemand::Request{}, uint8_t(t % (2 * hour) < hour ? 45 : 0));
    cJSON_AddItemToObject(root.get(), "shadow", shadow.json());
    ActiveHeatGuard guard;
    cJSON* active = guard.json(statusNow);
    cJSON_ReplaceItemInObjectCaseSensitive(active, "state", cJSON_CreateString("blocked_foreign_controller"));
    cJSON* command = cJSON_GetObjectItem(active, "command");
    cJSON_ReplaceItemInObjectCaseSensitive(command, "why", cJSON_CreateString("boiler_limit_unknown"));
    cJSON_ReplaceItemInObjectCaseSensitive(command, "flow_c", cJSON_CreateNumber(80));
    for (const char* key : {"last_sent", "foreign_controller", "confirmation"}) {
        cJSON* o = cJSON_CreateObject();
        cJSON_AddNumberToObject(o, "age_s", 4294967295.0);
        if (key[0] != 'c') cJSON_AddNumberToObject(o, key[0] == 'l' ? "flow_c" : "address", 255);
        cJSON_ReplaceItemInObjectCaseSensitive(active, key, o);
    }
    cJSON* warnings = cJSON_GetObjectItem(active, "warnings");
    for (const char* w : {"foreign_controller", "measurement_lost", "boiler_no_response", "transmit_failed", "boiler_limit_unknown"})
        cJSON_AddItemToArray(warnings, cJSON_CreateString(w));
    cJSON_AddBoolToObject(active, "enabled", false);
    cJSON_AddBoolToObject(active, "confirmation_stored", true);
    cJSON* limit = cJSON_AddObjectToObject(active, "boiler_limit");
    cJSON_AddNumberToObject(limit, "flow_c", 90); cJSON_AddNumberToObject(limit, "age_s", 4294967295.0); cJSON_AddNumberToObject(limit, "reads", 4294967295.0);
    cJSON_AddItemToObject(root.get(), "active", active);
    addHaLink(root.get(), uint64_t(0), 4294967295000ull, false);
    compactHeatingTelemetry(root.get());
    return root;
}
DhwEpisodes dhw() {
    DhwEpisodes e;
    heating::ems::ClassicBoilerMonitor monitor;
    e.observe(monitor, 0, uint32_t(wednesday23));
    e.flow(25); e.flow(60);
    for (uint64_t ms = 0; ms < 20 * 60000; ms += 60000) { e.state(0x0A, ms * 100); e.flow(85); e.state(0x00, ms * 100 + 30000); }
    return e;
}
void report(const char* label, const std::string& topic, size_t bytes) {
    std::printf("[ telemetry budget ] %-9s %-34s %4zu B\n", label, topic.c_str(), bytes);
}
}

TEST(HeatingStateTopics, WorstCasePlanMakesOnlySmallMessages) {
    std::map<HeatingTopic, size_t> largest;
    for (const bool escaped : {false, true}) {
        const auto plan = worstPlan(escaped);
        auto status = worstStatus(plan);
        const auto messages = split(status.get());
        size_t rooms = 0, ble = 0, parts = 0;
        for (const auto& m : messages) {
            EXPECT_LE(m.payload.size(), telemetryHardBytes) << m.topic;
            EXPECT_LE(m.payload.size(), telemetrySoftBytes) << m.topic;
            largest[m.kind] = std::max(largest[m.kind], m.payload.size());
            Json j(cJSON_Parse(m.payload.c_str()), cJSON_Delete);
            ASSERT_TRUE(j) << m.topic;
            EXPECT_EQ(cJSON_GetObjectItem(j.get(), "schema")->valuedouble, 1) << m.topic;
            rooms += m.kind == HeatingTopic::room; ble += m.kind == HeatingTopic::ble; parts += m.kind == HeatingTopic::entities;
            if (!escaped && (m.kind != HeatingTopic::room || rooms == 1) && (m.kind != HeatingTopic::ble || ble == 1)
                && (m.kind != HeatingTopic::entities || parts == 1)) report("worst", m.topic, m.payload.size());
        }
        EXPECT_EQ(rooms, 8u); EXPECT_EQ(ble, 8u);
        EXPECT_EQ(parts, 5u);                                          // 40 entities of 80 characters
        // Every entity once, in order, over the parts.
        std::vector<std::string> entities;
        for (const auto& m : messages)
            if (m.kind == HeatingTopic::entities) {
                Json j(cJSON_Parse(m.payload.c_str()), cJSON_Delete);
                EXPECT_EQ(cJSON_GetObjectItem(j.get(), "parts")->valuedouble, 5);
                EXPECT_EQ(cJSON_GetObjectItem(j.get(), "revision")->valuedouble, 4294967295.0);
                for (const cJSON* e = cJSON_GetObjectItem(j.get(), "entities")->child; e; e = e->next) entities.push_back(e->valuestring);
            }
        ASSERT_EQ(entities.size(), 40u);
        EXPECT_EQ(entities[0], plan.rooms[0].sources[0].id);
        EXPECT_EQ(entities[39], plan.rooms[7].setpointEntity);
    }
    // The learned header, hot water, flow and night gas; the per-room learned values.
    const auto plan = worstPlan();
    FlowLearner learner;
    learner.setPlan(plan);
    train(learner, plan.rooms.size());
    learner.gasPrice(FlowLearner::maxGasPrice);
    RoomEngine engine; engine.setPlan(plan);
    for (const auto& room : plan.rooms) for (const auto& src : room.sources) engine.haState(src.id, int16_t(1960), std::nullopt, statusNow - minute);
    engine.step(statusNow, uint32_t(wednesday23));
    std::vector<std::optional<int16_t>> temperatures;
    for (size_t i = 0; i < plan.rooms.size(); ++i) temperatures.push_back(engine.freshTemperature(i, statusNow));
    LearnedContext context;
    context.utc = wednesday23; context.temperatures = temperatures.data(); context.outdoorCentiC = int16_t(-1234);
    context.outdoorSource = "boiler"; context.now = statusNow;
    FlowPolicy policy;
    const auto summary = heatingSummaryTelemetry(learner, context, dhw().summaryJson(), &policy);
    ASSERT_FALSE(summary.empty());
    report("worst", "fw/telemetry/summary", summary.size());
    EXPECT_LE(summary.size(), telemetrySoftBytes);
    size_t learnedLargest = 0;
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto payload = learnedRoomTelemetry(learner, plan, i, context);
        ASSERT_FALSE(payload.empty());
        learnedLargest = std::max(learnedLargest, payload.size());
        EXPECT_LE(payload.size(), telemetrySoftBytes) << i;
    }
    report("worst", "fw/telemetry/learned/<id>", learnedLargest);
    for (const auto& [kind, bytes] : largest) EXPECT_GT(bytes, 0u) << int(kind);
}

TEST(HeatingStateTopics, EveryStatusMemberLandsInExactlyOneTopic) {
    auto status = worstStatus(worstPlan());
    cJSON_AddStringToObject(status.get(), "added_by_another_module", "flows through");
    const auto messages = split(status.get());
    std::map<std::string, std::string> by;
    for (const auto& m : messages) by[m.topic] = m.payload;
    Json heating(cJSON_Parse(by.at("fw/state/heating").c_str()), cJSON_Delete);
    for (const char* kept : {"schema", "revision", "mode", "request", "burner", "active", "ha", "added_by_another_module"})
        EXPECT_TRUE(cJSON_GetObjectItem(heating.get(), kept)) << kept;
    for (const char* moved : {"rooms", "ble_sensors", "ha_entities", "shadow"}) EXPECT_FALSE(cJSON_GetObjectItem(heating.get(), moved)) << moved;
    Json room(cJSON_Parse(by.at("fw/state/room/" + pad("a_", 32, 'a')).c_str()), cJSON_Delete);
    for (const char* kept : {"id", "name", "state", "inactive_until", "status", "source", "temperature", "setpoint", "setpoint_source", "demand"})
        EXPECT_TRUE(cJSON_GetObjectItem(room.get(), kept)) << kept;
    Json ble(cJSON_Parse(by.at("fw/state/ble/a4c138a3e800").c_str()), cJSON_Delete);
    EXPECT_EQ(cJSON_GetObjectItem(ble.get(), "battery")->valuedouble, 100);
    Json plan(cJSON_Parse(by.at("fw/config/plan").c_str()), cJSON_Delete);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(plan.get(), "rooms")), 8);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(plan.get(), "ble")), 8);
    EXPECT_EQ(cJSON_GetObjectItem(plan.get(), "entity_parts")->valuedouble, 5);
    EXPECT_STREQ(cJSON_GetObjectItem(plan.get(), "mode")->valuestring, "shadow");
    Json shadow(cJSON_Parse(by.at("fw/telemetry/shadow").c_str()), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(shadow.get(), "today")));
    // An empty plan still names its (zero) rooms and one empty entity part.
    Json empty(cJSON_Parse(R"({"schema":1,"revision":0,"mode":"shadow","request":{"heat":false,"flow_c":0,"reason":"no_rooms"},"ha_entities":[],"rooms":[]})"), cJSON_Delete);
    const auto none = split(empty.get());
    std::map<std::string, std::string> e;
    for (const auto& m : none) e[m.topic] = m.payload;
    EXPECT_EQ(e.at("fw/config/plan"), R"({"rooms":[],"ble":[],"schema":1,"revision":0,"mode":"shadow","entity_parts":1})");
    EXPECT_EQ(e.at("fw/config/entities"), R"({"entities":[],"schema":1,"revision":0,"part":0,"parts":1})");
    EXPECT_FALSE(e.count("fw/telemetry/shadow"));
}

TEST(TelemetryPolicy, DeadbandsIgnoreNoiseAndAges) {
    const auto parsed = [](const char* s) { return Json(cJSON_Parse(s), cJSON_Delete); };
    const std::string room = R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21,"demand":true,"status":"ok"})";
    EXPECT_FALSE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.55,"setpoint":21,"demand":true,"status":"ok"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.6,"setpoint":21,"demand":true,"status":"ok"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21.5,"demand":true,"status":"ok"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21,"demand":false,"status":"ok"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21,"demand":true,"status":"stale"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":null,"setpoint":21,"demand":true,"status":"ok"})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21,"demand":true})").get(), roomBands));
    EXPECT_TRUE(changedBeyond(room, parsed(R"({"schema":1,"id":"a","temperature":20.5,"setpoint":21,"demand":true,"status":"ok","x":1})").get(), roomBands));
    EXPECT_TRUE(changedBeyond("", parsed(room.c_str()).get(), roomBands));
    EXPECT_TRUE(changedBeyond("{broken", parsed(room.c_str()).get(), roomBands));
    // The requested flow by whole degrees; ages never count.
    const std::string heating = R"({"request":{"heat":true,"flow_c":44,"reason":"heating"},"ha":{"input_age_s":3,"broker_connected":true},"active":{"last_sent":{"age_s":10}}})";
    EXPECT_FALSE(changedBeyond(heating, parsed(R"({"request":{"heat":true,"flow_c":44,"reason":"heating"},"ha":{"input_age_s":250,"broker_connected":true},"active":{"last_sent":{"age_s":99}}})").get(), heatingBands));
    EXPECT_TRUE(changedBeyond(heating, parsed(R"({"request":{"heat":true,"flow_c":45,"reason":"heating"},"ha":{"input_age_s":3,"broker_connected":true},"active":{"last_sent":{"age_s":10}}})").get(), heatingBands));
    EXPECT_TRUE(changedBeyond(heating, parsed(R"({"request":{"heat":false,"flow_c":44,"reason":"heating"},"ha":{"input_age_s":3,"broker_connected":true},"active":{"last_sent":{"age_s":10}}})").get(), heatingBands));
    EXPECT_TRUE(changedBeyond(heating, parsed(R"({"request":{"heat":true,"flow_c":44,"reason":"heating"},"ha":{"input_age_s":3,"broker_connected":false},"active":{"last_sent":{"age_s":10}}})").get(), heatingBands));
    const std::string sensor = R"({"temperature":19.5,"humidity":55.3,"battery":87,"age_s":3})";
    EXPECT_FALSE(changedBeyond(sensor, parsed(R"({"temperature":19.55,"humidity":55.9,"battery":87,"age_s":300})").get(), bleBands));
    EXPECT_TRUE(changedBeyond(sensor, parsed(R"({"temperature":19.5,"humidity":56.3,"battery":87,"age_s":3})").get(), bleBands));
    EXPECT_TRUE(changedBeyond(sensor, parsed(R"({"temperature":19.5,"humidity":55.3,"battery":86,"age_s":3})").get(), bleBands));
    // A new learned result, not the advice that follows the room.
    const std::string learned = R"({"schema":1,"id":"a","learned":{"readiness":"learning","segments":3,"now":{"flow_c":40}},"plan":{"optimum_start":{"lead_minutes":30}}})";
    EXPECT_FALSE(changedBeyond(learned, parsed(R"({"schema":1,"id":"a","learned":{"readiness":"learning","segments":3,"now":{"flow_c":45}},"plan":{"optimum_start":{"lead_minutes":40}}})").get(), learnedBands));
    EXPECT_TRUE(changedBeyond(learned, parsed(R"({"schema":1,"id":"a","learned":{"readiness":"ready","segments":4,"now":{"flow_c":40}},"plan":{"optimum_start":{"lead_minutes":30}}})").get(), learnedBands));
}

TEST(TelemetryPolicy, BoilerRowsChangeByValueNotByObservation) {
    const auto parsed = [](const char* s) { return Json(cJSON_Parse(s), cJSON_Delete); };
    const auto bands = [](size_t index) { return index == 1 ? 50.0 : index == 4 ? 5.0 : 0.0; };
    const std::string before = R"({"schema":1,"values":{"schema":1,"sampled_at_ms":1000,"profile":"classic_observed","fields":[[1,4500,900,0,24],[4,30,900,0,24],[7,1,900,1,24]]}})";
    EXPECT_FALSE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"classic_observed","fields":[[1,4549,8900,0,24],[4,34,8900,0,24],[7,1,8900,1,24]]}})").get(), bands));
    EXPECT_TRUE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"classic_observed","fields":[[1,4550,8900,0,24],[4,30,8900,0,24],[7,1,8900,1,24]]}})").get(), bands));
    EXPECT_TRUE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"classic_observed","fields":[[1,4500,8900,0,24],[4,35,8900,0,24],[7,1,8900,1,24]]}})").get(), bands));
    EXPECT_TRUE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"classic_observed","fields":[[1,4500,8900,0,24],[4,30,8900,0,24],[7,0,8900,1,24]]}})").get(), bands));
    EXPECT_TRUE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"classic_observed","fields":[[1,null,900,0,24],[4,30,8900,0,24],[7,1,8900,1,24]]}})").get(), bands));
    EXPECT_TRUE(boilerFieldsChanged(before, parsed(R"({"schema":1,"values":{"schema":1,"sampled_at_ms":9000,"profile":"plus_observed","fields":[[1,4500,8900,0,24],[4,30,8900,0,24],[7,1,8900,1,24]]}})").get(), bands));
}

TEST(TelemetryPolicy, CadenceSendsOnceThenOnChangeAtMostEveryTenSecondsElseEveryFiveMinutes) {
    TelemetrySlot slot;
    EXPECT_TRUE(slot.due(1000, stateCadence, false));        // after (re)connect: once
    slot.mark(1000, 1);
    EXPECT_FALSE(slot.due(5000, stateCadence, true));        // a change within 10 s waits
    EXPECT_TRUE(slot.due(11000, stateCadence, true));
    EXPECT_FALSE(slot.due(11000, stateCadence, false));
    EXPECT_FALSE(slot.due(1000 + 299999, stateCadence, false));
    EXPECT_TRUE(slot.due(1000 + 300000, stateCadence, false)); // the 5-minute refresh
    EXPECT_FALSE(slot.due(1000 + 59999, fieldsCadence, true)); // boiler groups: 60 s
    EXPECT_TRUE(slot.due(1000 + 60000, fieldsCadence, true));
    EXPECT_TRUE(slot.due(1000 + 900000, fieldsCadence, false)); // and every 15 min
    EXPECT_TRUE(slot.due(500, stateCadence, false));          // a clock step back sends
    slot.reset();
    EXPECT_TRUE(slot.due(2000, stateCadence, false));
}
