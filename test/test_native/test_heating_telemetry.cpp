#include "control/ActiveHeatGuard.h"
#include "control/DhwEpisodes.h"
#include "control/HeatingTelemetry.h"
#include "control/RoomEngine.h"
#include "control/ShadowComparison.h"
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

// Eight active plan rooms, alternating floor and radiator, all with the
// owner's week program. Realistic: an HA climate (source and setpoint) and a
// Bluetooth sensor each. Worst case: 32-char ids, 40-char names and 4 sources
// (3 HA sensors and a Bluetooth sensor) with 80-char entity ids, plus an
// 80-char setpoint entity: 32 HA entities.
std::string pad(std::string s, size_t n, char c) { s.resize(n, c); return s; }
RoomPlan eightRooms(bool worst) {
    static const char* ids[8] = {"woonkamer", "keuken", "badkamer", "slaapkamer_voor", "slaapkamer_achter", "werkkamer", "logeerkamer", "zolder_studio"};
    static const char* names[8] = {"Woonkamer", "Keuken", "Badkamer", "Slaapkamer voor", "Slaapkamer achter", "Werkkamer", "Logeerkamer", "Zolder studio"};
    RoomPlan plan;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = worst ? pad(ids[i] + std::string("_"), 32, char('a' + i)) : ids[i];
        r.name = worst ? pad(names[i] + std::string(" "), 40, 'x') : names[i];
        r.state = RoomDemand::State::active;
        r.emitter = i % 2 ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        char ble[13]; std::snprintf(ble, sizeof ble, "a4c138a3e8%02x", i);
        if (worst) {
            for (int s = 0; s < 3; ++s) r.sources.push_back({RoomPlan::SourceType::ha, pad("sensor." + r.id + "_" + char('0' + s) + "_", 80, 't')});
            r.sources.push_back({RoomPlan::SourceType::ble, ble});
            r.setpointEntity = pad("climate." + r.id + "_", 80, 's');
        } else {
            r.sources = {{RoomPlan::SourceType::ha, "climate." + r.id}, {RoomPlan::SourceType::ble, ble}};
            r.setpointEntity = "climate." + r.id;
        }
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
constexpr uint64_t statusNow = 600 * minute;

struct Bench {
    RoomPlan plan;
    FlowLearner learner;
    RoomEngine engine;
    std::vector<std::optional<int16_t>> temperatures;
    LearnedContext context;
    Bench(bool worst, bool trained, bool clock) : plan(eightRooms(worst)) {
        learner.setPlan(plan);
        if (trained) train(learner, plan.rooms.size());
        engine.setPlan(plan);
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            for (const auto& s : plan.rooms[i].sources)
                if (s.type == RoomPlan::SourceType::ha) engine.haState(s.id, int16_t(1960 + 10 * i), std::nullopt, statusNow - minute);
                else engine.bleReading(s.id, int16_t(1955 + 10 * i), statusNow - minute);
            engine.haState(plan.rooms[i].setpointEntity, std::nullopt, 2100, statusNow - minute);
        }
        engine.step(statusNow, uint32_t(wednesday23));
        for (size_t i = 0; i < plan.rooms.size(); ++i) temperatures.push_back(engine.freshTemperature(i, statusNow));
        if (clock) context.utc = wednesday23;
        context.temperatures = temperatures.data(); context.outdoorCentiC = int16_t(500); context.outdoorSource = "ha"; context.now = statusNow;
    }
    // Assembled like HeatingController::heatingStatusJson.
    Json status(size_t nameLength = 24) const {
        Json root(engine.json(), cJSON_Delete);
        cJSON* sensors = cJSON_AddArrayToObject(root.get(), "ble_sensors");
        for (size_t i = 0; i < 8; ++i) {
            cJSON* s = cJSON_CreateObject(); cJSON_AddItemToArray(sensors, s);
            cJSON_AddStringToObject(s, "id", plan.rooms[i].sources.back().id.c_str());
            cJSON_AddStringToObject(s, "name", pad("Thermometer " + plan.rooms[i].name, nameLength, 'x').c_str());
            cJSON_AddStringToObject(s, "profile", "mibeacon_encrypted");
            cJSON_AddNumberToObject(s, "temperature", 19.55 + i / 10.0); cJSON_AddNumberToObject(s, "humidity", 55.37);
            cJSON_AddNumberToObject(s, "battery", 87); cJSON_AddNumberToObject(s, "age_s", 142);
        }
        cJSON* burner = cJSON_AddObjectToObject(root.get(), "burner");
        cJSON_AddNumberToObject(burner, "starts_last_hour", 14); cJSON_AddNumberToObject(burner, "heating_starts_last_hour", 13);
        cJSON_AddBoolToObject(burner, "short_cycling", true);
        ShadowComparison shadow;                          // a full week of past days plus today
        const FlowDemand::Request heat{true, 44, FlowDemand::Reason::heating};
        for (int d = 0; d < 8; ++d)
            for (uint64_t t = 0; t < 24 * hour; t += 10 * minute)
                shadow.sample(d * 24 * hour + t, uint32_t(wednesday23 - (8 - d) * 86400 + t / 1000),
                              t % (3 * hour) < hour ? heat : FlowDemand::Request{}, uint8_t(t % (2 * hour) < hour ? 45 : 0));
        cJSON_AddItemToObject(root.get(), "shadow", shadow.json());
        ActiveHeatGuard guard;
        cJSON_AddItemToObject(root.get(), "active", guard.json(statusNow));
        cJSON_AddBoolToObject(cJSON_GetObjectItem(root.get(), "active"), "enabled", false);
        cJSON_AddItemToObject(root.get(), "learned", learnedJson(learner, plan, context));
        DhwEpisodes dhw;
        heating::ems::ClassicBoilerMonitor monitor;
        dhw.observe(monitor, 0, uint32_t(wednesday23));  // the clock is known
        dhw.flow(25); dhw.flow(60);                      // live flow: peak reported
        for (uint64_t ms = 0; ms < 20 * 60000; ms += 60000) { dhw.state(0x0A, ms * 100); dhw.flow(85); dhw.state(0x00, ms * 100 + 30000); }
        cJSON_AddItemToObject(root.get(), "dhw", dhw.summaryJson());
        addHaLink(root.get(), statusNow - 12 * second, statusNow, true);
        return root;
    }
    std::string mqtt() const {
        auto s = status(40);
        compactHeatingTelemetry(s.get());
        return print(s.get());
    }
};

void breakdown(const char* label, const std::string& payload) {
    Json j(cJSON_Parse(payload.c_str()), cJSON_Delete);
    std::printf("[ heating telemetry ] %s %zu B:", label, payload.size());
    for (const cJSON* c = j ? j->child : nullptr; c; c = c->next) std::printf(" %s %zu", c->string, print(c).size());
    std::printf("\n");
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

TEST(HeatingTelemetry, MainPayloadKeepsTheShapeWithoutPageOnlyFields) {
    const Bench b(false, true, true);
    auto status = b.status();
    ASSERT_TRUE(status);
    const auto full = print(status.get());
    compactHeatingTelemetry(status.get());
    const auto mqtt = print(status.get());
    breakdown("realistic full", full); breakdown("realistic mqtt", mqtt);
    // 8 rooms with a tado and a Bluetooth sensor each, 8 sensors: measured 3974 B
    // (target 3800 not met; no further fields dropped by decision). Must stay
    // under ModernTransport's heatingTelemetryMaxBytes (4096) or HA loses it all.
    EXPECT_LE(mqtt.size(), 4000u);
    const cJSON* room = cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0);
    for (const char* gone : {"fallback_centi_c", "minimum_centi_c", "maximum_centi_c"}) EXPECT_FALSE(cJSON_GetObjectItem(room, gone)) << gone;
    for (const char* kept : {"id", "name", "state", "inactive_until", "status", "source", "temperature", "setpoint", "setpoint_source", "demand"}) EXPECT_TRUE(cJSON_GetObjectItem(room, kept)) << kept;
    const cJSON* learned = cJSON_GetObjectItem(status.get(), "learned");
    EXPECT_EQ(cJSON_GetObjectItem(learned, "schema")->valuedouble, 1);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(learned, "applied")));
    EXPECT_TRUE(cJSON_IsString(cJSON_GetObjectItem(learned, "status")));
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(learned, "heating_periods")));
    EXPECT_FALSE(cJSON_GetObjectItem(learned, "rooms"));
    EXPECT_FALSE(cJSON_GetObjectItem(learned, "plans"));
    const cJSON* inputs = cJSON_GetObjectItem(learned, "inputs");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(inputs, "gas_meter")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(inputs, "gas_price")));
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "outdoor")->valuestring, "ha");
    EXPECT_EQ(cJSON_GetObjectItem(inputs, "boiler_kw")->valuedouble, 22);
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "boiler_kw_source")->valuestring, "default");
    EXPECT_EQ(cJSON_GetObjectItem(inputs, "gas_kwh_per_m3")->valuedouble, 9.77);
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "gas_kwh_per_m3_source")->valuestring, "default");
    EXPECT_FALSE(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "shadow"), "days"));
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "shadow"), "today")));
    const cJSON* dhw = cJSON_GetObjectItem(status.get(), "dhw");
    EXPECT_STREQ(cJSON_GetObjectItem(dhw, "method")->valuestring, "flow");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(dhw, "clock_known")));
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetObjectItem(dhw, "today"), "tapping"), "count")->valuedouble, 20);
    EXPECT_FALSE(cJSON_GetObjectItem(dhw, "last_7_days"));
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "ha"), "input_age_s")->valuedouble, 12);
    // The full form keeps everything for the page.
    Json again(cJSON_Parse(full.c_str()), cJSON_Delete);
    const cJSON* fullLearned = cJSON_GetObjectItem(again.get(), "learned");
    const cJSON* fullRoom = cJSON_GetArrayItem(cJSON_GetObjectItem(fullLearned, "rooms"), 0);
    EXPECT_GT(cJSON_GetArraySize(cJSON_GetObjectItem(fullRoom, "curve")), 0);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(fullRoom, "advice")), 4);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(cJSON_GetObjectItem(fullLearned, "plans"), "rooms")), 8);
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(cJSON_GetObjectItem(again.get(), "dhw"), "last_7_days")));
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(again.get(), "rooms"), 0), "fallback_centi_c")));
    EXPECT_GT(cJSON_GetArraySize(cJSON_GetObjectItem(cJSON_GetObjectItem(again.get(), "shadow"), "days")), 0);
}

TEST(HeatingTelemetry, WorstCasePlanMainPayloadSize) {
    // 8 rooms x 4 sources with 80-char entity ids, 32-char room ids, 40-char
    // names, 8 Bluetooth sensors with 40-char names. Reported, not trimmed further.
    const Bench b(true, false, true);
    const auto mqtt = b.mqtt();
    breakdown("worst-case mqtt", mqtt);
    Json j(cJSON_Parse(mqtt.c_str()), cJSON_Delete);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j.get(), "ha_entities")), 32);
    // Measured 7473 B, mostly ha_entities (32 x 80 chars, 2657 B): such a plan
    // is dropped (heating_telemetry_dropped counts it). Known limit, reported.
    EXPECT_GT(mqtt.size(), 4096u) << "the worst case fits now: tighten the bound below";
    EXPECT_LE(mqtt.size(), 7500u);
}

TEST(HeatingTelemetry, PerRoomLearnedPayloadsStayUnder900Bytes) {
    for (const bool worst : {false, true}) {
        const Bench b(worst, true, true);
        size_t largest = 0;
        for (size_t i = 0; i < b.plan.rooms.size(); ++i) {
            const auto payload = learnedRoomTelemetry(b.learner, b.plan, i, b.context);
            ASSERT_FALSE(payload.empty());
            largest = std::max(largest, payload.size());
            EXPECT_LE(payload.size(), 900u) << i;
            Json j(cJSON_Parse(payload.c_str()), cJSON_Delete);
            ASSERT_TRUE(j);
            EXPECT_EQ(cJSON_GetObjectItem(j.get(), "schema")->valuedouble, 1);
            EXPECT_EQ(std::string(cJSON_GetObjectItem(j.get(), "id")->valuestring), b.plan.rooms[i].id);
            const cJSON* learned = cJSON_GetObjectItem(j.get(), "learned");
            EXPECT_STREQ(cJSON_GetObjectItem(learned, "readiness")->valuestring, "ready");
            EXPECT_FALSE(cJSON_GetObjectItem(learned, "curve"));
            ASSERT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(learned, "advice")), 1);
            EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(learned, "advice"), 0), "shortfall_c")->valuedouble, 1);
            EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(learned, "now")));
            const cJSON* plan = cJSON_GetObjectItem(j.get(), "plan");
            const cJSON* start = cJSON_GetObjectItem(plan, "optimum_start");
            EXPECT_STREQ(cJSON_GetObjectItem(start, "reason")->valuestring, "planned");
            EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(start, "predicted_start_utc")));
            EXPECT_TRUE(cJSON_IsBool(cJSON_GetObjectItem(start, "start_now")));
            EXPECT_FALSE(cJSON_GetObjectItem(start, "next_switch"));
            const cJSON* night = cJSON_GetObjectItem(plan, "night");
            EXPECT_STREQ(cJSON_GetObjectItem(night, "reason")->valuestring, "estimated");
            EXPECT_TRUE(cJSON_IsString(cJSON_GetObjectItem(night, "recommended")));
            EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(night, "recommended_night_c")));
            EXPECT_FALSE(cJSON_GetObjectItem(night, "strategies"));
            if (worst && i == 0) std::printf("[ heating telemetry ] per-room example %s\n", payload.c_str());
        }
        std::printf("[ heating telemetry ] per-room %s largest %zu B\n", worst ? "worst-case" : "realistic", largest);
        EXPECT_TRUE(learnedRoomTelemetry(b.learner, b.plan, 8, b.context).empty());
    }
}

TEST(HeatingTelemetry, WithoutClockPlansAreNullAndTheShapeStays) {
    const Bench b(false, false, false);
    const auto payload = learnedRoomTelemetry(b.learner, b.plan, 3, b.context);
    Json j(cJSON_Parse(payload.c_str()), cJSON_Delete);
    ASSERT_TRUE(j);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "plan")));
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "learned"), "readiness")->valuestring, "collecting");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "learned"), "now"))); // no sample yet
    auto status = b.status();
    EXPECT_FALSE(cJSON_GetObjectItem(cJSON_GetObjectItem(status.get(), "learned"), "plans"));
    compactHeatingTelemetry(status.get());
    const auto once = print(status.get());
    EXPECT_LE(once.size(), 4000u);
    // Compacting is idempotent and harmless on older documents.
    compactHeatingTelemetry(status.get());
    EXPECT_EQ(print(status.get()), once);
    Json old(cJSON_Parse(R"({"schema":1,"rooms":[{"id":"a","inactive_until":0}],"shadow":{"today":{},"days":[]}})"), cJSON_Delete);
    compactHeatingTelemetry(old.get());
    EXPECT_EQ(print(old.get()), R"({"schema":1,"rooms":[{"id":"a","inactive_until":0}],"shadow":{"today":{}}})");
}

TEST(HeatingTelemetry, RotationPublishesTwoDistinctRoomsPerTick) {
    RoomRotation rotation;
    std::vector<size_t> seen;
    for (int tick = 0; tick < 4; ++tick) rotation.tick(8, 2, [&](size_t i) { seen.push_back(i); });
    EXPECT_EQ(seen, (std::vector<size_t>{0, 1, 2, 3, 4, 5, 6, 7})); // every room within 60 s
    seen.clear();
    rotation.tick(1, 2, [&](size_t i) { seen.push_back(i); });      // one room: once per tick
    rotation.tick(1, 2, [&](size_t i) { seen.push_back(i); });
    EXPECT_EQ(seen, (std::vector<size_t>{0, 0}));
    seen.clear();
    rotation.tick(0, 2, [&](size_t i) { seen.push_back(i); });
    EXPECT_TRUE(seen.empty());
    rotation.next = 7;                                               // the plan shrank
    rotation.tick(3, 2, [&](size_t i) { seen.push_back(i); });
    EXPECT_EQ(seen, (std::vector<size_t>{0, 1}));
    EXPECT_TRUE(topicSafeRoomId("slaapkamer_2"));
    for (const char* bad : {"", "a/b", "a+", "#", "Woonkamer", "a b"}) EXPECT_FALSE(topicSafeRoomId(bad)) << bad;
    EXPECT_FALSE(topicSafeRoomId(std::string(33, 'a')));
}
}
