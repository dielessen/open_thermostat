#include "control/RoomEngine.h"
#include <gtest/gtest.h>
#include <memory>

namespace {
using heating::control::RoomEngine;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t minute = 60000;

// The owner's first release: living room (floor, tado then Xiaomi), bathroom off.
const char* ownerPlan = R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[
 {"id":"woonkamer","name":"Woonkamer","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ha","id":"climate.woonkamer"},{"type":"ble","id":"a4c138a3e8db"}],
  "setpoint_entity":"climate.woonkamer","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500},
 {"id":"badkamer","name":"Badkamer","state":"inactive","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000001"}],
  "setpoint_entity":"","fallback_centi_c":2200,"minimum_centi_c":500,"maximum_centi_c":2500}]})";

RoomPlan parsed(const char* text) {
    Json root(cJSON_Parse(text), cJSON_Delete);
    RoomPlan plan;
    EXPECT_EQ(RoomPlan::parse(root.get(), plan), nullptr);
    return plan;
}
const char* parseError(const std::string& text) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    RoomPlan plan;
    return RoomPlan::parse(root.get(), plan);
}

TEST(RoomPlan, OwnerPlanRoundTripsUnchanged) {
    const auto plan = parsed(ownerPlan);
    ASSERT_EQ(plan.rooms.size(), 2u);
    EXPECT_EQ(plan.rooms[0].sources[1].type, RoomPlan::SourceType::ble);
    EXPECT_EQ(plan.rooms[0].emitter, RoomPlan::Emitter::floor);
    const auto again = parsed(plan.json().c_str());
    EXPECT_EQ(again.json(), plan.json());
}
TEST(RoomPlan, FlowAboveSixtyAndBadSourcesAreRejected) {
    std::string text = ownerPlan;
    EXPECT_STREQ(parseError(std::string(text).replace(text.find("\"maximum_flow_c\":60"), 19, "\"maximum_flow_c\":75")), "invalid_flow_limits");
    EXPECT_STREQ(parseError(std::string(text).replace(text.find("a4c138a3e8db"), 12, "A4:C1:38:A3")), "invalid_sources");
    EXPECT_STREQ(parseError(std::string(text).replace(text.find("\"badkamer\""), 10, "\"woonkamer\"")), "duplicate_room");
    EXPECT_STREQ(parseError(R"({"schema":2})"), "invalid_schema");
}

TEST(RoomEngine, TadoLeadsAndTheFloorRequestStaysWithinSixty) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 2040, 2100, 10 * minute);
    e.bleReading("a4c138000001", 1500, 10 * minute); // cold bathroom is inactive
    const auto r = e.step(10 * minute, 1761650000);
    EXPECT_TRUE(r.heat); EXPECT_EQ(r.flowC, 36); // 0.6 degC short
    Json j(e.json(), cJSON_Delete);
    const auto* rooms = cJSON_GetObjectItem(j.get(), "rooms");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, 0), "source")), "climate.woonkamer");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, 1), "status")), "inactive");
    // Source and setpoint are the same tado entity: HA forwards it once.
    const auto* entities = cJSON_GetObjectItem(j.get(), "ha_entities");
    ASSERT_EQ(cJSON_GetArraySize(entities), 1);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(entities, 0)), "climate.woonkamer");
}
TEST(RoomEngine, BluetoothTakesOverWhenHomeAssistantStopsReporting) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 2040, 2100, 0);
    e.bleReading("a4c138a3e8db", 2110, 20 * minute);
    e.step(20 * minute, std::nullopt);
    Json j(e.json(), cJSON_Delete);
    const auto* room = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(room, "status")), "fallback");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(room, "source")), "a4c138a3e8db");
    // The tado target is 20 minutes old as well: the room's own fallback (20.0) applies.
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(room, "setpoint")), 20.0);
}
TEST(RoomEngine, AllSourcesLostStopsTheRequestAfterThirtyMinutes) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 1900, 2100, 0);
    EXPECT_TRUE(e.step(0, std::nullopt).heat);
    EXPECT_TRUE(e.step(29 * minute, std::nullopt).heat);  // holding the last value
    EXPECT_FALSE(e.step(30 * minute, std::nullopt).heat); // lost: immediate safety stop
}
TEST(RoomEngine, TemporarilyInactiveRoomReturnsWhenItsPauseEnds) {
    std::string text = ownerPlan;
    const std::string from = R"("state":"active","inactive_until":0)";
    text.replace(text.find(from), from.size(), R"("state":"inactive","inactive_until":1761650000)");
    RoomEngine e; e.setPlan(parsed(text.c_str()));
    e.haState("climate.woonkamer", 1900, 2100, 0);
    EXPECT_FALSE(e.step(0, 1761649999).heat);
    EXPECT_FALSE(e.step(minute, std::nullopt).heat); // clock unknown: the pause holds
    EXPECT_TRUE(e.step(2 * minute, 1761650000).heat);
}
TEST(RoomEngine, RoomWithinHysteresisDoesNotStartTheBoiler) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 2090, 2100, 0); // 0.1 degC short, hysteresis 0.2
    const auto r = e.step(0, std::nullopt);
    EXPECT_FALSE(r.heat); EXPECT_EQ(r.reason, heating::control::FlowDemand::Reason::idle);
}
}
