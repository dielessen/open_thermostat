// Week planner levels in the room plan (beta.23, "plan.levels.v1"): stored per room, independent of
// each other, never used by control, and invisible to the beta.21 parser after a rollback.
#include "control/RoomPlan.h"
#include "RoomPlanBeta21.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <memory>
#include <string>

namespace {
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::RoomPlanBeta21;
using heating::control::RoomSchedule;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

// The owner's living room with a week program and its three levels; Eco equals Night on purpose.
const std::string levelsPlan = R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[
 {"id":"woonkamer","name":"Woonkamer","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ha","id":"climate.woonkamer"},{"type":"ble","id":"a4c138a3e8db"}],
  "setpoint_entity":"climate.woonkamer","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500,
  "schedule":[[[390,2100],[510,1850],[1020,2100],[1350,1850]],[[390,2100],[1350,1850]],[],[],[],[[480,2050]],[]],
  "levels":{"comfort":2100,"eco":1850,"night":1850},"schedule_levels":"1213.13....0."},
 {"id":"badkamer","name":"Badkamer","state":"inactive","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000001"}],
  "setpoint_entity":"","fallback_centi_c":2200,"minimum_centi_c":500,"maximum_centi_c":2500,
  "levels":{"comfort":2300,"eco":2000,"night":2400}}]})";

RoomPlan parsed(const std::string& text) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    RoomPlan plan;
    EXPECT_EQ(RoomPlan::parse(root.get(), plan), nullptr) << text;
    return plan;
}
const char* parseError(const std::string& text) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    RoomPlan plan;
    return RoomPlan::parse(root.get(), plan);
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const auto at = text.find(from);
    EXPECT_NE(at, std::string::npos) << from;
    return text.replace(at, from.size(), to);
}
// What the beta.21 firmware makes of a stored plan after a rollback.
RoomPlanBeta21 beta21(const std::string& stored) {
    Json root(cJSON_Parse(stored.c_str()), cJSON_Delete);
    RoomPlanBeta21 plan;
    EXPECT_EQ(RoomPlanBeta21::parse(root.get(), plan), nullptr) << stored;
    return plan;
}

TEST(RoomPlanLevels, StoredPerRoomAndReturnedInTheApiForm) {
    const auto plan = parsed(levelsPlan);
    const auto& room = plan.rooms[0];
    ASSERT_TRUE(room.hasLevels);
    EXPECT_EQ(room.levels[0], 2100); EXPECT_EQ(room.levels[1], 1850); EXPECT_EQ(room.levels[2], 1850);
    EXPECT_EQ(room.pointLevel(0, 0), 1); EXPECT_EQ(room.pointLevel(0, 1), 2); EXPECT_EQ(room.pointLevel(0, 3), 3);
    EXPECT_EQ(room.pointLevel(5, 0), 0);   // an own temperature
    // A room without a program keeps its levels for the thermostat presets; Night may be the warmest.
    EXPECT_TRUE(plan.rooms[1].hasLevels);
    EXPECT_EQ(plan.rooms[1].levels[2], 2400);
    const auto api = plan.json();
    EXPECT_NE(api.find(R"("features":["plan.levels.v1"])"), std::string::npos);
    EXPECT_NE(api.find(R"("levels":{"comfort":2100,"eco":1850,"night":1850},"schedule_levels":"1213.13....0.")"), std::string::npos);
    EXPECT_EQ(api.find("schedule_levels", api.find("badkamer")), std::string::npos);
    EXPECT_EQ(parsed(api).json(), api);
}
TEST(RoomPlanLevels, ControlKeepsUsingTheTemperatures) {
    const auto with = parsed(levelsPlan);
    std::string text = levelsPlan;
    text = replaced(text, R"(,
  "levels":{"comfort":2100,"eco":1850,"night":1850},"schedule_levels":"1213.13....0.")", "");
    text = replaced(text, R"(,
  "levels":{"comfort":2300,"eco":2000,"night":2400})", "");
    const auto without = parsed(text);
    for (uint8_t d = 0; d < 7; ++d)
        for (uint16_t m = 0; m < 1440; m += 15)
            EXPECT_EQ(with.rooms[0].schedule.at(d, m), without.rooms[0].schedule.at(d, m));
    EXPECT_FALSE(without.rooms[0].hasLevels);
    EXPECT_EQ(without.json().find("\"levels\""), std::string::npos);
}
TEST(RoomPlanLevels, InvalidLevelsAreRefused) {
    const std::string marks = R"("schedule_levels":"1213.13....0.")";
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("comfort":2100)", R"("comfort":2600)")), "invalid_levels");  // above the room maximum
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("eco":1850,)", "")), "invalid_levels");
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("night":1850})", R"("night":18.5})")), "invalid_levels");
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":"1214.13....0.")")), "invalid_schedule_levels");
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":"121.13....0.")")), "invalid_schedule_levels");   // too few
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":"1213.13....0")")), "invalid_schedule_levels");   // 6 days
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":"1213.13....0..")")), "invalid_schedule_levels"); // 8 days
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":"1213.13....1.")")), "invalid_schedule_levels"); // 2050 is not Comfort
    EXPECT_STREQ(parseError(replaced(levelsPlan, marks, R"("schedule_levels":1213)")), "invalid_schedule_levels");
    // Marks need levels, and the room's own program.
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("levels":{"comfort":2100,"eco":1850,"night":1850},)", "")), "invalid_schedule_levels");
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("levels":{"comfort":2300,"eco":2000,"night":2400})",
        R"("levels":{"comfort":2300,"eco":2000,"night":2400},"schedule_levels":".......")")), "invalid_schedule_levels");
    EXPECT_STREQ(parseError(replaced(levelsPlan, R"("levels":{"comfort":2300)", R"("lv":"8fc7d0960","levels":{"comfort":2300)")), "invalid_levels");
}
// 8 rooms of 4 switch points a day, each with levels: the packed stored form still fits, and both
// the API-sized and the packed stored form load in the beta.21 parser with the same programs.
TEST(RoomPlanLevels, EightRoomsWithLevelsFitTheStoreAndRollBackToBeta21) {
    const char* ids[] = {"woonkamer", "keuken", "badkamer", "slaapkamer", "kinderkamer", "logeerkamer", "werkkamer", "zolder"};
    RoomPlan plan;
    plan.revision = 12;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = ids[i]; r.name = ids[i];
        r.state = RoomDemand::State::active;
        r.sources = {{RoomPlan::SourceType::ha, std::string("sensor.") + ids[i] + "_temperature"},
                     {RoomPlan::SourceType::ble, "a4c13800000" + std::to_string(i)}};
        r.setpointEntity = std::string("climate.") + ids[i];
        const RoomSchedule::Point weekday[] = {{390, 2050}, {480, 1800}, {1020, 2100}, {1350, 1700}};
        const uint16_t weekdayMarks = 0 | 2 << 2 | 1 << 4 | 3 << 6;  // own, Eco, Comfort, Night
        for (int d = 0; d < 7; ++d) {
            auto& day = r.schedule.days[d];
            for (const auto& p : weekday) day.points[day.count++] = p;
            r.pointLevels[d] = weekdayMarks;
        }
        r.hasLevels = true; r.levels = {2100, 1800, 1700};
        plan.rooms.push_back(r);
    }
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room plan ] 8 rooms x 4 points with levels: API form %zu B, stored form %zu B (store %zu B incl. NUL)\n",
                api.size(), stored.size(), RoomPlan::storeBytes);
    EXPECT_LE(stored.size() + 1, RoomPlan::storeBytes);
    EXPECT_LT(stored.size(), 3900u);
    // Comfort 2100, Eco 1800, Night 1700 (2 characters each), then 28 marks 0213 0213 ... 3 per character.
    EXPECT_NE(stored.find(R"("lv":"g0cIak)"), std::string::npos);
    const auto at = stored.find(R"("lv":")") + 6;
    EXPECT_EQ(stored.find('"', at) - at, 6u + 10u);
    EXPECT_EQ(stored.find("features"), std::string::npos);
    const auto back = parsed(stored);
    EXPECT_EQ(back.json(), api);
    EXPECT_EQ(back.rooms[7].pointLevel(6, 2), 1);
    // A rollback to beta.21: the same rooms and temperatures, the levels are simply absent.
    const auto old = beta21(stored);
    ASSERT_EQ(old.rooms.size(), 8u);
    for (size_t i = 0; i < 8; ++i)
        for (uint8_t d = 0; d < 7; ++d)
            for (uint16_t m = 0; m < 1440; m += 30) EXPECT_EQ(old.rooms[i].schedule.at(d, m), plan.rooms[i].schedule.at(d, m));
    EXPECT_EQ(old.json().find("levels"), std::string::npos);
    // A small plan is stored in the API form (without "features"); beta.21 reads that as well.
    const auto small = parsed(levelsPlan);
    const auto smallStored = small.storedJson();
    EXPECT_NE(smallStored.find("\"schedule_levels\""), std::string::npos);
    EXPECT_EQ(smallStored.find("features"), std::string::npos);
    const auto oldSmall = beta21(smallStored);
    EXPECT_EQ(oldSmall.rooms[0].schedule.at(0, 500), 2100);
    EXPECT_EQ(parsed(smallStored).json(), small.json());
}
// The largest storable plan with levels in every room still has an API form within the request bound.
TEST(RoomPlanLevels, TheApiFormOfAStorablePlanWithLevelsFitsTheRequestBound) {
    RoomPlan plan;
    plan.revision = 4294967295u; plan.minimumFlowC = 20; plan.maximumFlowC = 80;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = std::string(32, char('a' + i));
        r.name = std::string(40, '\x01');
        r.inactiveUntil = 4102444800u;
        r.sources.push_back({RoomPlan::SourceType::ha, "sensor." + std::string(72, char('a' + i))});
        r.setpointEntity = "climate." + std::string(72, char('a' + i));
        r.fallbackCentiC = 2999; r.minimumCentiC = 1000; r.maximumCentiC = 3000;
        for (auto& day : r.schedule.days)
            for (uint16_t m = 1434; day.count < RoomSchedule::maxPoints; ++m)
                day.points[day.count++] = {m, int16_t(2990 + day.count)};
        // Points 1..3 of every day are Comfort, Eco and Night (their own temperatures, whatever they are).
        r.hasLevels = true;
        r.levels = {r.schedule.days[0].points[1].centiC, r.schedule.days[0].points[2].centiC, r.schedule.days[0].points[3].centiC};
        for (auto& marks : r.pointLevels) marks = 1 << 2 | 2 << 4 | 3 << 6;
        plan.rooms.push_back(r);
    }
    for (size_t turn = 0; plan.storedJson().size() + 1 > RoomPlan::storeBytes; ++turn) {
        ASSERT_LT(turn, 20000u) << plan.storedJson().size();
        auto& r = plan.rooms[turn % 8];
        if (r.name.size() > 1) { r.name.pop_back(); continue; }
        for (auto& s : r.sources) if (s.id.size() > 9) s.id.erase(7, 1);
        if (r.setpointEntity.size() > 9) r.setpointEntity.erase(8, 1);
    }
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room plan ] largest storable plan with levels: stored %zu B, API form %zu B (request bound %zu B)\n",
                stored.size(), api.size(), RoomPlan::requestBytes);
    EXPECT_EQ(parsed(stored).json(), api);
    EXPECT_LE(api.size() + 8 * 80, RoomPlan::requestBytes);
}
// A plan that only fits without its levels keeps every room and switch point and gives up the levels.
TEST(RoomPlanLevels, APlanThatOnlyFitsWithoutLevelsDropsThem) {
    RoomPlan plan;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = std::string(32, char('a' + i)); r.name = "n";
        r.sources.push_back({RoomPlan::SourceType::ha, "sensor." + std::string(12, char('a' + i))});
        r.setpointEntity = "climate." + std::string(12, char('a' + i));
        for (auto& day : r.schedule.days)
            for (uint16_t m = 360; day.count < RoomSchedule::maxPoints; m += 120) day.points[day.count++] = {m, int16_t(1800 + 100 * (day.count % 3))};
        r.hasLevels = true; r.levels = {1900, 2000, 1800};
        plan.rooms.push_back(r);
    }
    // Longer names until only the levels make the plan too large (the packed levels cost 28 B a room).
    const auto bare = [](RoomPlan p) { for (auto& r : p.rooms) r.hasLevels = false; return p; };
    for (size_t turn = 0; plan.storedJson().size() + 1 <= RoomPlan::storeBytes; ++turn) {   // while it still fits
        ASSERT_LT(turn, 400u);
        plan.rooms[turn % 8].name += 'n';
    }
    const auto without = bare(plan);
    ASSERT_LE(without.storedJson().size() + 1, RoomPlan::storeBytes) << "the plan itself fits";
    ASSERT_GT(plan.storedJson().size() + 1, RoomPlan::storeBytes) << "only the levels make it too large";
    EXPECT_TRUE(plan.dropLevelsToFit());
    EXPECT_EQ(plan.storedJson(), without.storedJson());
    EXPECT_FALSE(plan.dropLevelsToFit());   // nothing left to drop
}
}
