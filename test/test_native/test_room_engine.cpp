#include "control/RoomEngine.h"
#include "control/HeatingTelemetry.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string_view>

namespace {
using heating::control::RoomEngine;
using heating::control::compactHeatingTelemetry;
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
TEST(RoomPlan, FlowLimitsAcceptEveryHomeUpToEighty) {
    const std::string text = ownerPlan;
    const auto limits = [&](const char* min, const char* max) {
        const std::string original = "\"minimum_flow_c\":30,\"maximum_flow_c\":60";
        std::string t = text;
        t.replace(t.find(original), original.size(),
            std::string("\"minimum_flow_c\":") + min + ",\"maximum_flow_c\":" + max);
        return t;
    };
    for (const auto& ok : {std::make_pair("20", "21"), std::make_pair("30", "75"), std::make_pair("79", "80"), std::make_pair("45", "80")}) {
        const auto plan = parsed(limits(ok.first, ok.second).c_str());
        EXPECT_EQ(plan.minimumFlowC, std::stoi(ok.first));
        EXPECT_EQ(plan.maximumFlowC, std::stoi(ok.second));
        EXPECT_EQ(parsed(plan.json().c_str()).maximumFlowC, plan.maximumFlowC);
    }
    for (const auto& bad : {std::make_pair("30", "81"), std::make_pair("19", "60"), std::make_pair("80", "80"),
             std::make_pair("50", "50"), std::make_pair("60", "40"), std::make_pair("30", "20"), std::make_pair("30.5", "60")})
        EXPECT_STREQ(parseError(limits(bad.first, bad.second)), "invalid_flow_limits") << bad.first << ".." << bad.second;
    EXPECT_EQ(RoomPlan{}.maximumFlowC, 60); // new plans keep the 60 degC default
}
TEST(RoomPlan, FlowAboveEightyAndBadSourcesAreRejected) {
    std::string text = ownerPlan;
    EXPECT_STREQ(parseError(std::string(text).replace(text.find("\"maximum_flow_c\":60"), 19, "\"maximum_flow_c\":85")), "invalid_flow_limits");
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
// The calculated request never exceeds what the boiler accepts (0x16), in shadow too.
TEST(RoomEngine, TheBoilersLimitCapsTheCalculatedRequest) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 1700, 2100, 10 * minute); // 4 degC short: 70 -> plan max 60
    EXPECT_EQ(e.step(10 * minute, 1761650000).flowC, 60);
    Json open(e.json(), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(open.get(), "request"), "capped_by")));
    e.setBoilerLimit(50);
    const auto r = e.step(11 * minute, 1761650060);
    EXPECT_TRUE(r.heat); EXPECT_EQ(r.flowC, 50); EXPECT_TRUE(r.capped);
    Json capped(e.json(), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(capped.get(), "request"), "capped_by")), "boiler_limit");
    e.setPlan(parsed(ownerPlan)); // a plan edit keeps the limit
    EXPECT_EQ(e.step(12 * minute, 1761650120).flowC, 50);
    // fw/telemetry/heating: capped_by only while set (no bytes in the usual case).
    compactHeatingTelemetry(capped.get());
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(capped.get(), "request"), "capped_by")), "boiler_limit");
    compactHeatingTelemetry(open.get());
    EXPECT_FALSE(cJSON_GetObjectItem(cJSON_GetObjectItem(open.get(), "request"), "capped_by"));
    e.setBoilerLimit(std::nullopt); // unknown: the plan's ceiling, the shadow calculation goes on
    EXPECT_EQ(e.step(13 * minute, 1761650180).flowC, 60);
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
    // HA shows the effective state: active again, the plan keeps its pause date.
    Json j(e.json(), cJSON_Delete);
    const auto* room = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(room, "state")), "active");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(room, "inactive_until")), 1761650000);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(room, "fallback_centi_c")), 2000);
}
TEST(RoomEngine, RoomWithinHysteresisDoesNotStartTheBoiler) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 2090, 2100, 0); // 0.1 degC short, hysteresis 0.2
    const auto r = e.step(0, std::nullopt);
    EXPECT_FALSE(r.heat); EXPECT_EQ(r.reason, heating::control::FlowDemand::Reason::idle);
}
}

namespace {
TEST(RoomPlan, RevisionRoundTripsAndOldPlansStartAtZero) {
    EXPECT_EQ(parsed(ownerPlan).revision, 0u);
    std::string text = ownerPlan;
    auto plan = parsed(text.replace(1, 0, "\"revision\":41,").c_str());
    EXPECT_EQ(plan.revision, 41u);
    EXPECT_EQ(parsed(plan.json().c_str()).revision, 41u);
    text = ownerPlan;
    EXPECT_STREQ(parseError(text.replace(1, 0, "\"revision\":-1,")), "invalid_revision");
}
// Renaming a room or reordering its sources from HA must not reset what the
// engine knows: readings follow their source and the burner keeps running.
TEST(RoomEngine, EditingThePlanKeepsReadingsAndTheRunningRequest) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.haState("climate.woonkamer", 2040, 2100, 10 * minute);
    e.bleReading("a4c138a3e8db", 1990, 10 * minute);
    ASSERT_TRUE(e.step(10 * minute, 1761650000).heat);
    std::string text = ownerPlan;
    text.replace(text.find("\"Woonkamer\""), 11, "\"Living\"");
    const auto first = text.find("{\"type\":\"ha\",\"id\":\"climate.woonkamer\"}");
    text.erase(first, 39);  // drop the tado source and its comma: Bluetooth only
    auto edited = parsed(text.c_str());
    ASSERT_EQ(edited.rooms[0].sources.size(), 1u);
    e.setPlan(edited);
    const auto r = e.step(11 * minute, 1761650060);
    EXPECT_TRUE(r.heat);  // min on time continues; not restarted from off
    Json j(e.json(), cJSON_Delete);
    const auto* room = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(room, "source")), "a4c138a3e8db");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(room, "name")), "Living");
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(room, "temperature")), 19.9);
}
}

namespace {
// Without HA the E32 follows its own week program; without a clock the fallback.
// Owner, 30 Oct 2026: the E32 week program leads; HA pushes it to the room's setting device and
// sends a knob change as an override. The device's reported target counts only without the clock.
TEST(RoomEngine, TheWeekProgramLeadsAndAnHaTargetCountsOnlyWithoutAClock) {
    ScopedTz tz(ScopedTz::amsterdam);
    std::string text = ownerPlan;
    // Every day: 18.0 from 22:30, 20.5 from 06:30 local time.
    const std::string week = R"(,"schedule":[[[390,2050],[1350,1800]],[],[],[],[],[],[]])";
    text.insert(text.find("\"maximum_centi_c\":2500}") + 22, week);
    RoomEngine e; e.setPlan(parsed(text.c_str()));
    ASSERT_FALSE(e.plan().rooms[0].schedule.empty());
    EXPECT_NE(e.plan().json().find("\"schedule\""), std::string::npos);
    e.haState("climate.woonkamer", 1950, 2100, 0);
    const auto room = [&](uint64_t now, std::optional<uint32_t> utc) {
        e.step(now, utc);
        Json j(e.json(), cJSON_Delete);
        const auto* r = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
        return std::make_pair(cJSON_GetNumberValue(cJSON_GetObjectItem(r, "setpoint")),
                              std::string(cJSON_GetStringValue(cJSON_GetObjectItem(r, "setpoint_source"))));
    };
    EXPECT_EQ(room(minute, 1761650000), std::make_pair(18.0, std::string("schedule"))); // a fresh 21 from HA does not lead
    EXPECT_EQ(room(2 * minute, std::nullopt), std::make_pair(21.0, std::string("ha")));  // no clock: the device's target
    // Mon 26 Oct 2026 03:00 local (CET) = 02:00 UTC: before 06:30, so the 22:30 night value.
    e.bleReading("a4c138a3e8db", 1950, 20 * minute);
    EXPECT_EQ(room(20 * minute, 1792980000), std::make_pair(18.0, std::string("schedule")));
    EXPECT_EQ(room(21 * minute, std::nullopt), std::make_pair(20.0, std::string("fallback")));
}

// The week program follows the device's TZ: 06:30 in New York is 11:30 UTC.
TEST(RoomEngine, WeekProgramRunsOnTheDeviceTimeZone) {
    ScopedTz tz(ScopedTz::newYork);
    std::string text = ownerPlan;
    const std::string week = R"(,"schedule":[[[390,2050],[1350,1800]],[],[],[],[],[],[]])"; // Mon 06:30 20.5, 22:30 18.0
    text.insert(text.find("\"maximum_centi_c\":2500}") + 22, week);
    RoomEngine e; e.setPlan(parsed(text.c_str()));
    const auto setpoint = [&](uint64_t now, uint32_t utc) {
        e.bleReading("a4c138a3e8db", 1950, now);
        e.step(now, utc);
        Json j(e.json(), cJSON_Delete);
        const auto* r = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
        EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(r, "setpoint_source")), "schedule");
        return cJSON_GetNumberValue(cJSON_GetObjectItem(r, "setpoint"));
    };
    const uint32_t monday0630Est = 1767591000 + 6 * 3600; // Mon 2026-01-05 06:30 EST
    EXPECT_EQ(setpoint(minute, monday0630Est - 3600), 18.0);    // 05:30 EST (10:30 UTC, after 06:30 in Amsterdam)
    EXPECT_EQ(setpoint(2 * minute, monday0630Est), 20.5);
}
}

namespace {
// Removing the leading source must not leave the status pointing past the
// edited source list (read before the next step: web reload, MQTT publish).
TEST(RoomEngine, RemovingTheLeadingSourceForgetsItBeforeTheNextStep) {
    RoomEngine e; e.setPlan(parsed(ownerPlan));
    e.bleReading("a4c138a3e8db", 1990, 10 * minute); // HA silent: Bluetooth (index 1) leads
    e.step(10 * minute, 1761650000);
    std::string text = ownerPlan;
    const std::string ble = R"(,{"type":"ble","id":"a4c138a3e8db"})";
    text.erase(text.find(ble), ble.size());
    e.setPlan(parsed(text.c_str()));
    Json j(e.json(), cJSON_Delete);
    const auto* room = cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "rooms"), 0);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(room, "source")));
}
}

namespace {
// HeatingController::setHeatingPlan skips the NVS write when the posted plan
// (same revision) serialises exactly like the stored one: HA automations that
// resend the plan neither wear the flash nor bump the revision.
TEST(RoomPlan, ResentPlanIsDetectedAsUnchangedButAnEditIsNot) {
    std::string text = ownerPlan;
    const auto stored = parsed(text.replace(1, 0, "\"revision\":7,").c_str());
    const auto resent = parsed(stored.json().c_str());
    EXPECT_EQ(resent.json(), stored.json());
    std::string edited = stored.json();
    edited.replace(edited.find("\"Woonkamer\""), 11, "\"Living\"");
    EXPECT_NE(parsed(edited.c_str()).json(), stored.json());
}

// Every cJSON allocation of json() failing in turn: nullptr or a document,
// never a crash or a leak (the ha_entities array once dereferenced null).
size_t engineAllocations = 0, engineLive = 0, engineFailAt = 0;
void* engineAllocate(size_t size) {
    if (engineAllocations++ == engineFailAt) return nullptr;
    void* p = std::malloc(size);
    if (p) ++engineLive;
    return p;
}
void engineRelease(void* p) { if (p) { --engineLive; std::free(p); } }
TEST(RoomEngine, JsonSurvivesEveryAllocationFailure) {
    RoomEngine e; e.setPlan(parsed(ownerPlan)); e.step(minute, std::nullopt);
    struct Restore { ~Restore() { cJSON_InitHooks(nullptr); } } restore;
    cJSON_Hooks hooks{engineAllocate, engineRelease};
    cJSON_InitHooks(&hooks);
    bool completed = false;
    for (engineFailAt = 0; engineFailAt < 200 && !completed; ++engineFailAt) {
        engineAllocations = engineLive = 0;
        cJSON* j = e.json();
        completed = engineAllocations <= engineFailAt; // nothing failed: the whole document
        if (completed) { EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j, "ha_entities")), 1); }
        cJSON_Delete(j);
        EXPECT_EQ(engineLive, 0u) << engineFailAt;
    }
    EXPECT_TRUE(completed);
}
}

namespace {
using heating::control::RoomDemand;
using heating::control::RoomSchedule;
// A realistic home (beta.19 item 8): 8 rooms, each with an HA thermometer and a
// Bluetooth sensor, the room's climate entity as target and a week program of
// 4 switch points per weekday and per weekend day.
RoomPlan eightRoomHome() {
    const char* ids[] = {"woonkamer", "keuken", "badkamer", "slaapkamer", "kinderkamer", "logeerkamer", "werkkamer", "zolder"};
    const char* names[] = {"Woonkamer", "Keuken", "Badkamer", "Slaapkamer", "Kinderkamer", "Logeerkamer", "Werkkamer", "Zolder"};
    RoomPlan plan;
    plan.revision = 12;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = ids[i]; r.name = names[i];
        r.state = RoomDemand::State::active;
        r.emitter = i ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        r.sources = {{RoomPlan::SourceType::ha, std::string("sensor.") + ids[i] + "_temperature"},
                     {RoomPlan::SourceType::ble, "a4c13800000" + std::to_string(i)}};
        r.setpointEntity = std::string("climate.") + ids[i];
        r.fallbackCentiC = 2000; r.minimumCentiC = 500; r.maximumCentiC = 2500;
        const RoomSchedule::Point weekday[] = {{390, 2050}, {480, 1800}, {1020, 2100}, {1350, 1700}};
        const RoomSchedule::Point weekend[] = {{450, 2100}, {720, 2000}, {1050, 2100}, {1380, 1700}};
        for (int d = 0; d < 7; ++d) {
            auto& day = r.schedule.days[d];
            for (const auto& p : d < 5 ? weekday : weekend) day.points[day.count++] = p;
        }
        plan.rooms.push_back(r);
    }
    return plan;
}
RoomPlan reloaded(const std::string& stored) {
    Json root(cJSON_Parse(stored.c_str()), cJSON_Delete);
    RoomPlan plan;
    EXPECT_EQ(RoomPlan::parse(root.get(), plan), nullptr) << stored;
    return plan;
}
std::string packedPoint(unsigned minute, unsigned centi) {
    const std::string_view a = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    const unsigned v = minute << 12 | centi;
    return std::string{a[(v >> 18) & 63], a[(v >> 12) & 63], a[(v >> 6) & 63], a[v & 63]};
}

TEST(RoomPlan, EightRoomsWithFourSwitchPointsADayFitTheStore) {
    const auto plan = eightRoomHome();
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room plan ] 8 rooms x 4 points: API form %zu B, stored form %zu B (store %zu B incl. NUL)\n",
                api.size(), stored.size(), RoomPlan::storeBytes);
    EXPECT_GT(api.size() + 1, RoomPlan::storeBytes);   // refused before beta.19
    EXPECT_LE(stored.size() + 1, RoomPlan::storeBytes);
    EXPECT_LT(stored.size(), 3600u);                   // room left for longer names and entities
    EXPECT_EQ(stored.find("\"schedule\""), std::string::npos);
    // Loaded back at the next boot: the same plan, and HA reads the same API form.
    const auto back = reloaded(stored);
    EXPECT_EQ(back.json(), api);
    EXPECT_EQ(back.storedJson(), stored);
    EXPECT_EQ(back.rooms[3].schedule.at(5, 719), 2100);
    EXPECT_EQ(back.rooms[3].schedule.at(0, 300), 1700); // Sunday's last point holds into Monday
}
TEST(RoomPlan, PlansThatFitAreStoredInTheFormOlderFirmwareReads) {
    std::string text = ownerPlan;
    text.insert(text.find("\"fallback_centi_c\":2000"), "\"schedule\":[[[390,2050],[1350,1800]],[],[],[],[],[],[]],");
    const auto plan = parsed(text.c_str());
    ASSERT_FALSE(plan.rooms[0].schedule.empty());
    // A rollback to beta.18 keeps the week program: the stored form is the API form without "features".
    auto api = plan.json();
    const std::string features = R"("features":["plan.levels.v1"],)";
    api.erase(api.find(features), features.size());
    EXPECT_EQ(plan.storedJson(), api);
    EXPECT_NE(plan.storedJson().find("\"schedule\":[[[390,2050]"), std::string::npos);
    // Old stored plans (with or without a week program) load unchanged.
    EXPECT_EQ(reloaded(plan.storedJson()).json(), plan.json());
    EXPECT_EQ(reloaded(ownerPlan).json(), parsed(ownerPlan).json());
}
TEST(RoomPlan, PackedWeekProgramsAreValidatedLikeArrays) {
    const auto stored = eightRoomHome().storedJson();
    const auto week = [&](const std::string& value) {
        std::string t = stored;
        const auto at = t.find("\"week\":\"") + 8;
        t.replace(at, t.find('"', at) - at, value);
        return t;
    };
    const auto p390 = packedPoint(390, 2050), p1350 = packedPoint(1350, 1800);
    EXPECT_EQ(reloaded(week(p390 + p1350 + "......")).rooms[0].schedule.days[0].count, 2);
    EXPECT_TRUE(reloaded(week("......")).rooms[0].schedule.empty());
    EXPECT_STREQ(parseError(week(p390 + ".....")), "invalid_schedule");              // 6 days
    EXPECT_STREQ(parseError(week(p390 + ".......")), "invalid_schedule");            // 8 days
    EXPECT_STREQ(parseError(week(p390.substr(0, 3) + "......")), "invalid_schedule"); // a partial point
    EXPECT_STREQ(parseError(week(p1350 + p390 + "......")), "invalid_schedule");     // not increasing
    EXPECT_STREQ(parseError(week(p390 + p390 + "......")), "invalid_schedule");      // the same minute twice
    EXPECT_STREQ(parseError(week(packedPoint(1440, 2000) + "......")), "invalid_schedule");
    EXPECT_STREQ(parseError(week(packedPoint(390, 2600) + "......")), "invalid_schedule_limits");
    EXPECT_STREQ(parseError(week(packedPoint(390, 499) + "......")), "invalid_schedule_limits");
    EXPECT_STREQ(parseError(week("A=AA......")), "invalid_schedule");
    std::string seven;
    for (unsigned m = 0; m < 7; ++m) seven += packedPoint(m, 2000);
    EXPECT_STREQ(parseError(week(seven + "......")), "invalid_schedule");            // above maxPoints
    EXPECT_STREQ(parseError(week(std::string(400, 'A'))), "invalid_schedule");
    std::string both = stored;
    both.insert(both.find("\"week\""), "\"schedule\":[[],[],[],[],[],[],[]],");
    EXPECT_STREQ(parseError(both), "invalid_schedule");
    std::string number = stored;
    const auto at = number.find("\"week\":\"") + 7;
    number.replace(at, number.find('"', at + 1) + 1 - at, "7");
    EXPECT_STREQ(parseError(number), "invalid_schedule");
}
// POST /config/heating accepts requestBytes: the API form of the largest
// storable plan (every week program full with the longest points, the rest
// filled to the store byte) plus Home Assistant's ensure_ascii growth of the
// names (at most 80 B per 40-byte name) still fits.
TEST(RoomPlan, TheApiFormOfAnyStorablePlanFitsTheRequestBound) {
    RoomPlan plan;
    plan.revision = 4294967295u; plan.minimumFlowC = 20; plan.maximumFlowC = 80;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = std::string(32, char('a' + i));
        r.name = std::string(40, '\x01');
        r.inactiveUntil = 4102444800u;
        // Full week programs leave room for one source per room (the strings
        // grow neither form more than the other).
        r.sources.push_back({RoomPlan::SourceType::ha, "sensor." + std::string(72, char('a' + i))});
        r.setpointEntity = "climate." + std::string(72, char('a' + i));
        r.fallbackCentiC = 2999; r.minimumCentiC = 1000; r.maximumCentiC = 3000;
        for (auto& day : r.schedule.days)
            for (uint16_t m = 1434; day.count < RoomSchedule::maxPoints; ++m)
                day.points[day.count++] = {m, int16_t(2990 + day.count)};
        plan.rooms.push_back(r);
    }
    for (size_t turn = 0; plan.storedJson().size() + 1 > RoomPlan::storeBytes; ++turn) {
        ASSERT_LT(turn, 10000u) << plan.storedJson().size();
        auto& r = plan.rooms[turn % 8];
        if (r.name.size() > 1) { r.name.pop_back(); continue; }
        for (auto& s : r.sources) if (s.id.size() > 9) s.id.erase(7, 1);
        if (r.setpointEntity.size() > 9) r.setpointEntity.erase(8, 1);
    }
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room plan ] largest storable plan: stored %zu B, API form %zu B (request bound %zu B)\n",
                stored.size(), api.size(), RoomPlan::requestBytes);
    EXPECT_GE(stored.size() + 16, RoomPlan::storeBytes - 1);
    EXPECT_EQ(reloaded(stored).json(), api);
    EXPECT_LE(api.size() + 8 * 80, RoomPlan::requestBytes);
}
}
