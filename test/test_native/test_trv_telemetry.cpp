#include "control/HeatingStateTopics.h"
#include "control/TelemetryPolicy.h"
#include "control/TrvControl.h"
#include <cstdio>
#include <gtest/gtest.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

// Radiator valves in telemetry: one small document per room under fw/state/trv/<room>,
// a short summary in fw/state/heating, and nothing at all without valves.
namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}
std::map<std::string, std::string> split(cJSON* status, std::map<std::string, HeatingTopic>* kinds = nullptr) {
    std::map<std::string, std::string> out;
    EXPECT_TRUE(splitHeatingStatus(status, [&](HeatingTopic kind, const std::string& topic, const cJSON* doc) {
        out[topic] = print(doc);
        if (kinds) (*kinds)[topic] = kind;
    }));
    return out;
}
const char* base = R"({"schema":1,"revision":3,"mode":"shadow","request":{"heat":false,"flow_c":0,"reason":"no_demand"},"rooms":[],"ha_entities":[]})";

// The longest record TrvConfig takes: 8 rooms of 32 characters, 16 valves of 64, every value reported.
TrvConfig worstConfig() {
    TrvConfig c;
    for (int r = 0; r < 8; ++r) {
        TrvConfig::Room room;
        room.id = std::string(31, 'a' + r) + "_";
        room.control = true;
        for (int v = 0; v < (r < 4 ? 4 : 0); ++v)
            room.valves.push_back({std::string(62, 'A' + r) + "/" + char('0' + v), trvModel("bosch_bth_ra")});
        c.rooms.push_back(room);
    }
    return c;
}
}

TEST(TrvTelemetry, WithoutValvesTheSplitIsByteForByteAsBefore) {
    Json before(cJSON_Parse(base), cJSON_Delete), after(cJSON_Parse(base), cJSON_Delete);
    TrvControl trv;
    trv.setConfig({});
    if (cJSON* status = trv.statusJson(0, {})) cJSON_AddItemToObject(after.get(), "trv", status);  // as HeatingController does
    std::map<std::string, HeatingTopic> kinds;
    EXPECT_EQ(split(before.get()), split(after.get(), &kinds));
    for (const auto& [topic, kind] : kinds) EXPECT_NE(kind, HeatingTopic::trv) << topic;
}

TEST(TrvTelemetry, WorstCaseValvesMakeOnlySmallMessagesAndASummary) {
    TrvControl trv;
    const auto config = worstConfig();
    trv.setConfig(config);
    const uint64_t now = 3600000;
    for (const auto& room : config.rooms)
        for (const auto& v : room.valves)
            trv.receive("zigbee2mqtt/" + v.name, R"({"pi_heating_demand":100,"battery":100,"local_temperature":21.55,"occupied_heating_setpoint":21.5})", now - 1000);
    std::vector<TrvControl::Room> views;
    for (const auto& room : config.rooms) views.push_back({room.id, true, int16_t(2150), int16_t(1900), true, 250, 4});
    Json status(cJSON_Parse(base), cJSON_Delete);
    cJSON_AddItemToObject(status.get(), "trv", trv.statusJson(now, views));
    std::map<std::string, HeatingTopic> kinds;
    const auto messages = split(status.get(), &kinds);
    size_t rooms = 0, largest = 0;
    for (const auto& [topic, payload] : messages) {
        EXPECT_LE(payload.size(), telemetrySoftBytes) << topic;
        if (kinds[topic] != HeatingTopic::trv) continue;
        ++rooms; largest = std::max(largest, payload.size());
        Json doc(cJSON_Parse(payload.c_str()), cJSON_Delete);
        ASSERT_TRUE(doc) << topic;
        EXPECT_EQ(cJSON_GetObjectItem(doc.get(), "schema")->valuedouble, 1);
        EXPECT_EQ(topic, std::string("fw/state/trv/") + cJSON_GetObjectItem(doc.get(), "room")->valuestring);
        EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(doc.get(), "valves")), 4);
    }
    std::printf("[ telemetry budget ] worst     %-34s %4zu B\n", "fw/state/trv/<room>", largest);
    EXPECT_EQ(rooms, 4u);  // rooms without valves have no document
    Json heating(cJSON_Parse(messages.at("fw/state/heating").c_str()), cJSON_Delete);
    const cJSON* summary = cJSON_GetObjectItem(heating.get(), "trv");
    ASSERT_TRUE(cJSON_IsObject(summary));
    EXPECT_TRUE(cJSON_IsBool(cJSON_GetObjectItem(summary, "output")));
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(summary, "flow_offset_c")));
    EXPECT_FALSE(cJSON_GetObjectItem(summary, "rooms"));
    Json plan(cJSON_Parse(messages.at("fw/config/plan").c_str()), cJSON_Delete);
    const cJSON* ids = cJSON_GetObjectItem(plan.get(), "trv");
    ASSERT_EQ(cJSON_GetArraySize(ids), 4);
    EXPECT_STREQ(cJSON_GetArrayItem(ids, 0)->valuestring, config.rooms[0].id.c_str());
}
