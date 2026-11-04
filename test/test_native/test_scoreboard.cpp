#include "control/Scoreboard.h"
#include "control/ShadowComparison.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <memory>

// rc.4 (F1): the daily scoreboard: a day's outdoor mean and heating gas, the judged mornings,
// the self-tuner's counts of the same day, the JSON for HA and the page, and the record that
// survives a restart (today, or yesterday when the E32 was off at the day change).
namespace {
using heating::control::AutoTuner;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::RoomSchedule;
using heating::control::Scoreboard;
using heating::control::ShadowComparison;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
// Wednesday 4 Nov 2026, local midnight (CET).
const int64_t wednesday = int64_t(ShadowComparison::daysFromCivil(2026, 11, 4)) * 86400 - 3600;

RoomPlan plan() {
    RoomPlan p;
    for (const char* id : {"woonkamer", "keuken"}) { RoomPlan::Room r; r.id = r.name = id; r.state = RoomDemand::State::active; p.rooms.push_back(r); }
    return p;
}
const cJSON* at(const cJSON* o, const char* key) { return cJSON_GetObjectItemCaseSensitive(o, key); }
}

TEST(Scoreboard, CivilDateOfALocalDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    char text[11];
    Scoreboard::civil(RoomSchedule::localDay(wednesday + 3600), text);
    EXPECT_STREQ(text, "2026-11-04");
    Scoreboard::civil(RoomSchedule::localDay(wednesday - 1), text);
    EXPECT_STREQ(text, "2026-11-03");
    Scoreboard::civil(RoomSchedule::localDay(int64_t(ShadowComparison::daysFromCivil(2000, 2, 29)) * 86400 + 43200), text);
    EXPECT_STREQ(text, "2000-02-29");
}

TEST(Scoreboard, SumsTheDayAndMovesItToYesterdayAtMidnight) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    AutoTuner tuner;
    double kwh = 0;
    for (int64_t t = wednesday + 6 * 3600; t < wednesday + 86400 + 1800; t += 60) {
        kwh += 0.1 / 60;                                                 // 0.1 kWh an hour
        s.step(t, 60, int16_t(t < wednesday + 86400 ? 800 : 300), kwh); // 8 degC, then 3 degC
    }
    s.arrival(0, wednesday + 7 * 3600, 12);                                // judged this morning: 12 min late
    s.arrival(1, wednesday + 2 * 86400 + 7 * 3600, -5);                    // the day after tomorrow: not a day we hold
    ASSERT_TRUE(s.yesterday());
    EXPECT_NEAR(s.yesterday()->heatingKwh, 1.8, 0.01);                     // 18 h
    EXPECT_NEAR(s.yesterday()->outdoorSum / s.yesterday()->outdoorS, 8, 1e-6);
    EXPECT_EQ(s.yesterday()->arrivalSeen, 1); EXPECT_EQ(s.yesterday()->arrivalMin[0], 12);
    EXPECT_EQ(s.today().arrivalSeen, 0);
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.addJson(root.get(), tuner, plan()));
    const cJSON* y = at(at(root.get(), "scoreboard"), "yesterday");
    ASSERT_TRUE(cJSON_IsObject(y));
    EXPECT_STREQ(at(y, "day")->valuestring, "2026-11-04");
    EXPECT_DOUBLE_EQ(at(y, "degree_days")->valuedouble, 10);                 // 18 - 8
    EXPECT_DOUBLE_EQ(at(y, "heating_kwh")->valuedouble, 1.8);
    EXPECT_TRUE(cJSON_IsNull(at(y, "heating_h")));                           // the tuner knows no such day
    const cJSON* rooms = at(y, "rooms");
    ASSERT_EQ(cJSON_GetArraySize(rooms), 1) << "only the room with a measurement";
    EXPECT_STREQ(at(cJSON_GetArrayItem(rooms, 0), "id")->valuestring, "woonkamer");
    EXPECT_EQ(at(cJSON_GetArrayItem(rooms, 0), "on_time_min")->valueint, 12);
    EXPECT_TRUE(cJSON_IsNull(at(cJSON_GetArrayItem(rooms, 0), "overshoot_c")));
    const cJSON* today = at(at(root.get(), "scoreboard"), "today");
    EXPECT_STREQ(at(today, "day")->valuestring, "2026-11-05");
    EXPECT_DOUBLE_EQ(at(today, "degree_days")->valuedouble, 15);
    EXPECT_EQ(cJSON_GetArraySize(at(today, "rooms")), 0);
    char* text = cJSON_PrintUnformatted(root.get());
    EXPECT_LT(std::strlen(text), 450u) << text;
    cJSON_free(text);
}

// rc.4 (B1): the MQTT form (fw/telemetry/scoreboard, addJson compact) leaves out today's rooms,
// so eight rooms with 32-character ids stay within 1 KB (Home Assistant shows today's room
// figures only as attributes); yesterday keeps its rooms, and the page's full form has both.
TEST(Scoreboard, TheCompactFormLeavesOutTodaysRooms) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    AutoTuner tuner;
    s.step(wednesday + 6 * 3600, 60, int16_t(800), 0.1);
    s.step(wednesday + 86400 + 60, 60, int16_t(300), 0.2);                   // Thursday: Wednesday is yesterday
    s.arrival(0, wednesday + 7 * 3600, 12);                                   // yesterday: the living room
    s.arrival(1, wednesday + 86400 + 7 * 3600, -3);                           // today: the kitchen
    for (const bool compact : {false, true}) {
        Json root(cJSON_CreateObject(), cJSON_Delete);
        ASSERT_TRUE(s.addJson(root.get(), tuner, plan(), compact));
        const cJSON* board = at(root.get(), "scoreboard");
        const cJSON* y = at(at(board, "yesterday"), "rooms");
        ASSERT_TRUE(cJSON_IsArray(y)) << compact;
        ASSERT_EQ(cJSON_GetArraySize(y), 1) << compact;
        EXPECT_STREQ(at(cJSON_GetArrayItem(y, 0), "id")->valuestring, "woonkamer");
        EXPECT_EQ(at(cJSON_GetArrayItem(y, 0), "on_time_min")->valueint, 12);
        const cJSON* today = at(board, "today");
        ASSERT_TRUE(cJSON_IsObject(today));
        const cJSON* t = at(today, "rooms");
        if (compact) { EXPECT_EQ(t, nullptr) << "compact: no \"rooms\" key for today"; }
        else {
            ASSERT_TRUE(cJSON_IsArray(t));
            ASSERT_EQ(cJSON_GetArraySize(t), 1);
            EXPECT_STREQ(at(cJSON_GetArrayItem(t, 0), "id")->valuestring, "keuken");
            EXPECT_EQ(at(cJSON_GetArrayItem(t, 0), "on_time_min")->valueint, -3);
        }
        // The rest of today stays in both forms.
        EXPECT_STREQ(at(today, "day")->valuestring, "2026-11-05");
        EXPECT_DOUBLE_EQ(at(today, "degree_days")->valuedouble, 15);
        EXPECT_TRUE(cJSON_IsNull(at(today, "heating_h")));
    }
    // The default (the page, /status/heating) is the full form.
    Json full(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.addJson(full.get(), tuner, plan()));
    EXPECT_TRUE(cJSON_IsArray(at(at(at(full.get(), "scoreboard"), "today"), "rooms")));
}

TEST(Scoreboard, TheRecordComesBackForTodayOrYesterdayOnly) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    for (int64_t t = wednesday + 3600; t < wednesday + 5 * 3600; t += 60) s.step(t, 60, int16_t(500), 0.5 * (t - wednesday) / 3600);
    s.arrival(0, wednesday + 4 * 3600, -3);
    const auto text = s.stored();
    EXPECT_LE(text.size(), Scoreboard::storedMaxBytes);
    const int32_t day = RoomSchedule::localDay(wednesday + 3600);
    Scoreboard same;
    ASSERT_TRUE(same.restore(text.c_str(), day));
    EXPECT_EQ(same.today().day, day);
    EXPECT_EQ(same.today().arrivalMin[0], -3); EXPECT_EQ(same.today().arrivalSeen, 1);
    EXPECT_NEAR(same.today().heatingKwh, s.today().heatingKwh, 0.01);
    EXPECT_EQ(same.today().outdoorS, s.today().outdoorS);
    Scoreboard next;                                                        // booted the day after: yesterday
    ASSERT_TRUE(next.restore(text.c_str(), day + 1));
    ASSERT_TRUE(next.yesterday()); EXPECT_EQ(next.yesterday()->day, day); EXPECT_EQ(next.today().day, day + 1);
    Scoreboard stale;
    EXPECT_FALSE(stale.restore(text.c_str(), day + 2));
    EXPECT_FALSE(stale.restore("not json", day));
    EXPECT_FALSE(stale.restore(R"({"t":{"d":1,"os":0,"on":-5,"k":0,"a":null}})", 1));
}
