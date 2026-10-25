#include <ctime>
#include "Arduino.h"
namespace {
bool roomClockAvailable = true;
int roomClockHour = 12, roomClockMinute = 0, roomClockDay = 3;
uint32_t roomClockWaitMs = 5000;
}
// Native SDK boundary only. The production Room.cpp below is compiled unchanged.
inline bool getLocalTime(std::tm* value, uint32_t waitMs = 5000) {
    roomClockWaitMs = waitMs;
    *value = {};
    value->tm_hour = roomClockHour;
    value->tm_min = roomClockMinute;
    value->tm_wday = roomClockDay;
    return roomClockAvailable;
}
#include "../../src/Room.cpp"
#include <cJSON.h>
#include <gtest/gtest.h>

namespace {
using heating::Room;
using heating::RoomConfig;
RoomConfig namedConfig(std::string name = "Room") {
    RoomConfig cfg{};
    cfg.name_ = std::move(name); cfg.id_ = "a1b2c3d4"; cfg.enabled_ = true;
    return cfg;
}
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json status(const Room& room) {
    return Json(cJSON_Parse(room.getStatus().c_str()), cJSON_Delete);
}
TEST(RoomStatus, NameAndIdentityRemainJsonStringsWithQuotesBackslashesAndControls) {
    auto cfg = namedConfig("Room \"west\"\\floor\nZoë");
    cfg.id_ = "id\"\\\t";
    const auto expectedName = cfg.name_, expectedId = cfg.id_;
    Room room({}, std::move(cfg));
    auto value = status(room); ASSERT_TRUE(value);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(value.get(), "name")), expectedName.c_str());
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(value.get(), "id")), expectedId.c_str());
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(value.get(), "enabled")));
}
TEST(RoomStatus, ValveLabelsCannotBreakTheStatusEnvelope) {
    auto cfg = namedConfig(); cfg.valves_ = {"A\"B", "C\\D\n"};
    Room room({}, std::move(cfg));
    auto value = status(room); ASSERT_TRUE(value);
    auto valves = cJSON_GetObjectItem(value.get(), "valves");
    ASSERT_EQ(cJSON_GetArraySize(valves), 2);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(valves, 0)), "A\"B");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(valves, 1)), "C\\D\n");
}
TEST(RoomStatus, ActualSelectedProgramNameRemainsAJsonString) {
    roomClockAvailable = true;
    auto cfg = namedConfig();
    RoomConfig::TemperatureSetting program{};
    program.name_ = "Warm \"morning\"\n"; program.timeFrom_ = 0; program.timeTo_ = 2359;
    program.temperature_ = 2200; cfg.temperatures_.push_back(program);
    Room room({}, std::move(cfg)); room.storeTemperature(1900);
    ASSERT_EQ(std::get<0>(room.shouldStartBoilerAndHeat()), Room::TemperatureStatus::START_HEATING);
    auto value = status(room); ASSERT_TRUE(value);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(value.get(), "currentProgram")), program.name_.c_str());
}
TEST(RoomStatus, FailedWallClockWithdrawsPriorHeatDecisionWithoutInventingAWeekday) {
    roomClockAvailable = true;
    Room room({}, namedConfig()); room.storeTemperature(1900);
    ASSERT_EQ(std::get<0>(room.shouldStartBoilerAndHeat()), Room::TemperatureStatus::START_HEATING);
    roomClockAvailable = false;
    const auto decision = room.shouldStartBoilerAndHeat();
    roomClockAvailable = true;
    EXPECT_NE(std::get<0>(decision), Room::TemperatureStatus::START_HEATING);
    EXPECT_NE(std::get<0>(decision), Room::TemperatureStatus::CONTINUE_HEATING);
    EXPECT_FALSE(std::get<1>(decision));
    auto value = status(room); ASSERT_TRUE(value);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(value.get(), "shouldStartBoiler")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(value.get(), "shouldContinueHeating")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(value.get(), "currentProgram")));
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(value.get(), "controlStatus")), "clock_unavailable");
}
}

TEST(RoomStatus, TemperatureOnlyReportDoesNotInventZeroHumidity) {
    heating::Room room({}, namedConfig()); room.storeTemperature(1950);
    auto value = status(room); ASSERT_TRUE(value);
    const auto humidity = cJSON_GetObjectItem(value.get(), "currentHumidity");
    EXPECT_EQ(humidity, nullptr); // Older HA readers also treat an absent value as unknown.
}

TEST(RoomStatus, ClockReadsHaveAShortWaitAndInvalidCalendarFieldsCannotSelectProgram) {
    roomClockAvailable = true;
    for (const auto bad : {std::array<int,3>{24,0,3}, {12,60,3}, {12,0,7}, {-1,0,3}, {12,0,-1}}) {
        roomClockHour = bad[0]; roomClockMinute = bad[1]; roomClockDay = bad[2];
        heating::Room room({}, namedConfig()); room.storeTemperature(1900);
        const auto result = std::get<0>(room.shouldStartBoilerAndHeat());
        roomClockHour = 12; roomClockMinute = 0; roomClockDay = 3;
        EXPECT_EQ(result, heating::Room::TemperatureStatus::TIME_UNAVAILABLE);
        EXPECT_LE(roomClockWaitMs, 100u);
    }
}

TEST(RoomStatus, ActualScheduleHelperRejectsInvalidMinuteOrWeekdayBeforeIndexing) {
    heating::RoomConfig::TemperatureSetting program{};
    program.timeFrom_ = 0; program.timeTo_ = 2359;
    EXPECT_TRUE(program.doesFit(2359, 6));
    for (const auto minute : {60, 1260, 2360, 2400, 65535})
        EXPECT_FALSE(program.doesFit(static_cast<uint16_t>(minute), 0));
    for (const auto day : {7, 8, 255}) EXPECT_FALSE(program.doesFit(1200, static_cast<uint8_t>(day)));
}

TEST(RoomStatus, HumidityUnknownAndInvalidValuesAreOmittedWhileZeroAndFullScaleRemainValid) {
    for (const auto raw : {-32768, -1, 0, 10000, 10001, 32767}) {
        heating::Room room({}, namedConfig()); room.storeTemperature(1950);
        room.storeHumidity(static_cast<int16_t>(raw));
        auto value = status(room); ASSERT_TRUE(value);
        const auto humidity = cJSON_GetObjectItem(value.get(), "currentHumidity");
        if (raw < 0 || raw > 10000) EXPECT_EQ(humidity, nullptr);
        else { ASSERT_TRUE(cJSON_IsNumber(humidity)); EXPECT_EQ(humidity->valueint, raw); }
    }
}

TEST(RoomStatus, BatteryUnknownAndOutOfRangeAreOmittedButZeroRemainsValid) {
    for (const auto raw : {-128, -1, 0, 100, 101, 127}) {
        heating::Room room({}, namedConfig()); room.storeTemperature(1950);
        room.storeBattery(static_cast<int8_t>(raw));
        auto value = status(room); ASSERT_TRUE(value);
        const auto battery = cJSON_GetObjectItem(value.get(), "batteryLevel");
        if (raw < 0 || raw > 100) EXPECT_EQ(battery, nullptr);
        else { ASSERT_TRUE(cJSON_IsNumber(battery)); EXPECT_EQ(battery->valueint, raw); }
    }
}
TEST(RoomStatus, MissingAverageIsOmittedAndMeasuredZeroIsPreserved) {
    heating::Room room({}, namedConfig());
    auto empty = status(room); ASSERT_TRUE(empty);
    EXPECT_EQ(cJSON_GetObjectItem(empty.get(), "meanTemp"), nullptr);
    room.storeTemperature(0);
    auto measured = status(room); ASSERT_TRUE(measured);
    const auto mean = cJSON_GetObjectItem(measured.get(), "meanTemp");
    ASSERT_TRUE(cJSON_IsNumber(mean)); EXPECT_EQ(mean->valueint, 0);
}
