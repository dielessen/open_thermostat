#include "control/ControlPartitionBudget.h"
#include "control/Scoreboard.h"
#include "control/ShadowComparison.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstring>
#include <memory>

// rc.4 (F1): the daily scoreboard: a day's outdoor mean and heating gas, the judged mornings,
// the self-tuner's counts of the same day, the JSON for HA and the page, and the record that
// survives a restart (today, or yesterday when the E32 was off at the day change).
namespace {
using heating::control::AutoTuner;
using heating::control::Insights;
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

// The record's bound (storedMaxBytes, 15 NVS entries): two days with the widest values that can occur
// (999.99 kWh a day, -50 degC all day, every arrival beyond the stored limit) and rc.5's Insights
// baselines after a week at two degree-days a day (gas 500 kWh/DD, the starts and the rooms at their
// bounds). The widest baselines of all ("b", 65 B, test_insights.cpp) beside the widest days fit too.
TEST(Scoreboard, TheWidestRecordStaysWithinItsBound) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    const int64_t day0 = int64_t(ShadowComparison::daysFromCivil(2099, 12, 21)) * 86400 - 3600;  // a five-digit day number
    double kwh = 0;
    std::array<std::optional<uint16_t>, RoomPlan::maxRooms> slow{};
    slow.fill(uint16_t(1000));
    for (int d = 0; d < 9; ++d) {                                                              // nine whole days, up to 23:59
        const int16_t outdoor = d < 7 ? 1600 : -5000;                                          // 2 degree-days a week, then -50 degC
        for (int64_t t = day0 + d * 86400 + 60; t < day0 + (d + 1) * 86400; t += 60) {
            if (s.step(t, 60, outdoor, kwh += 999.99 / 1439)) {                                // 999.99 kWh a day
                AutoTuner::Day tuned; tuned.day = s.yesterday()->day; tuned.hours = 0xFFFFFF; tuned.starts = 65535;
                s.judge(tuned, slow.data(), slow.size());
            }
        }
        for (size_t r = 0; r < RoomPlan::maxRooms; ++r) s.arrival(r, day0 + d * 86400 + 3600, int16_t(-32000));
    }
    ASSERT_EQ(s.insights().baseline(0).days, 8);
    const auto text = s.stored();
    std::printf("[ scoreboard ] widest record %zu B of %zu: %s\n", text.size(), Scoreboard::storedMaxBytes, text.c_str());
    ASSERT_FALSE(text.empty()) << "a record wider than the bound is not stored at all";
    EXPECT_LE(text.size(), Scoreboard::storedMaxBytes);
    EXPECT_GE(text.size(), 260u) << "the widest values really are in it";
    EXPECT_NE(text.find(R"("k":999.99,"a":[-9999,)"), std::string::npos) << "an arrival is stored within a week either way";
    EXPECT_NE(text.find(R"(,9998,9998])"), std::string::npos) << "the rooms' baselines at their bound";
    EXPECT_EQ(heating::control::ControlPartitionBudget::blobEntries(Scoreboard::storedMaxBytes + 1), 15u);
    // The widest days without any baselines, plus the widest baselines of all: still within the bound.
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    cJSON_DeleteItemFromObject(root.get(), "b"); cJSON_DeleteItemFromObject(root.get(), "x");
    char* days = cJSON_PrintUnformatted(root.get());
    const size_t widestDays = std::strlen(days);
    cJSON_free(days);
    EXPECT_EQ(widestDays, 213u);
    EXPECT_LE(widestDays + 65, Scoreboard::storedMaxBytes);
    Scoreboard back;
    ASSERT_TRUE(back.restore(text.c_str(), RoomSchedule::localDay(day0 + 8 * 86400 + 3600)));
    ASSERT_TRUE(back.yesterday()); EXPECT_EQ(back.yesterday()->arrivalMin[7], -9999); EXPECT_EQ(back.today().arrivalSeen, 0xFF);
    EXPECT_EQ(back.insights().baseline(Insights::houseFigures + 7).days, 8);
    EXPECT_NEAR(back.insights().baseline(Insights::houseFigures + 7).value, 999, 1e-3);
}

// rc.5 (P2): at the day change step() says so; judge() then takes yesterday's gas per degree-day, starts
// and heating hours (AutoTuner's same day) and the rooms' warm-up, judges them and only then folds them.
TEST(Scoreboard, TheDayChangeJudgesYesterdayBeforeFoldingItIn) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    double kwh = 0;
    int changes = 0;
    const auto run = [&](int days, double kwhPerDay, int16_t outdoor, uint32_t hours, uint16_t starts, std::optional<uint16_t> warmup) {
        for (int64_t end = wednesday + (changes + days) * 86400 + 60, t = wednesday + changes * 86400 + 60; t <= end; t += 60) {
            if (!s.step(t, 60, outdoor, kwh += kwhPerDay / 1440)) continue;
            ++changes;
            AutoTuner::Day tuned; tuned.day = s.yesterday()->day; tuned.hours = hours; tuned.starts = starts;
            const std::optional<uint16_t> rooms[2] = {warmup, std::nullopt};
            s.judge(tuned, rooms, 2);
        }
    };
    EXPECT_FALSE(s.step(wednesday + 60, 60, int16_t(800), kwh)) << "the first step starts a day, it ends none";
    run(4, 40, 800, 0xFFF, 24, 45);                          // 4 usual days: 4 kWh/DD, 2 starts/h, 1.2 h/DD, 45 min/degC
    EXPECT_EQ(changes, 4);
    EXPECT_EQ(s.insights().count(), 0u) << "four days only build the baseline";
    EXPECT_NEAR(*s.insights().gasPerDegreeDay(4), 4.0, 0.01);
    run(1, 60, 800, 0xFFFFF, 80, 70);                         // +50 % gas, 4 starts/h, 2 h/DD, 70 min/degC
    ASSERT_EQ(s.insights().count(), 4u);
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(s.insights().addJson(root.get(), plan()));
    char* text = cJSON_PrintUnformatted(root.get());
    EXPECT_STREQ(text, R"({"insights":[{"kind":"gas_per_dd_up","pct":50},{"kind":"starts_up","pct":100},)"
                       R"({"kind":"hours_per_dd_up","pct":67},{"kind":"warmup_slower","pct":56,"room":"woonkamer"}]})");
    cJSON_free(text);
    EXPECT_NEAR(*s.insights().gasPerDegreeDay(), 4.4, 0.02) << "folded in after the judgement";
    run(1, 0, 1700, 0, 0, 45);                                // no heating (and 1 degree-day): neither judged nor folded
    EXPECT_EQ(s.insights().count(), 0u);
    EXPECT_EQ(s.insights().baseline(0).days, 5);
    run(1, 40, 1700, 0xF, 3, 45);                             // heated but mild: the per-degree-day figures are skipped
    EXPECT_EQ(s.insights().baseline(0).days, 5);
    EXPECT_EQ(s.insights().baseline(1).days, 6);
    // A day the E32 was off (two days later) ends no day to judge: its figures would be partial.
    EXPECT_FALSE(s.step(wednesday + (changes + 2) * 86400 + 600, 60, int16_t(800), kwh));
}

// rc.5 (P2): the baselines come back with any readable record; the items only on the day they were made.
// A record of rc.4 (no baselines) restores as before, with empty baselines.
TEST(Scoreboard, TheBaselinesSurviveARestartAndTheItemsOnlyTheSameDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    Scoreboard s;
    double kwh = 0;
    int changes = 0;
    for (int64_t t = wednesday + 60; changes < 6; t += 60)
        if (s.step(t, 60, int16_t(800), kwh += (changes < 5 ? 40.0 : 80.0) / 1440)) {
            AutoTuner::Day tuned; tuned.day = s.yesterday()->day; tuned.hours = 0xFFF; tuned.starts = 24;
            s.judge(tuned, nullptr, 0);
            ++changes;
        }
    ASSERT_EQ(s.insights().count(), 1u);
    const auto text = s.stored();
    EXPECT_NE(text.find(R"("x":[)"), std::string::npos) << text;
    const int32_t today = s.today().day;
    Scoreboard same, next, later;
    ASSERT_TRUE(same.restore(text.c_str(), today));
    EXPECT_EQ(same.insights().count(), 1u);
    EXPECT_NEAR(*same.insights().gasPerDegreeDay(5), *s.insights().gasPerDegreeDay(), 0.01);
    ASSERT_TRUE(next.restore(text.c_str(), today + 1));
    EXPECT_EQ(next.insights().count(), 0u) << "the item described the day before yesterday";
    EXPECT_EQ(next.insights().baseline(0).days, 6);
    EXPECT_FALSE(later.restore(text.c_str(), today + 5)) << "no day comes back";
    EXPECT_EQ(later.insights().baseline(0).days, 6) << "the baselines span weeks: they still do";
    Scoreboard rc4;
    ASSERT_TRUE(rc4.restore(R"({"t":{"d":20761,"os":0,"on":0,"k":1.5,"a":null},"y":null})", 20761));
    EXPECT_EQ(rc4.insights().baseline(0).days, 0);
    EXPECT_NEAR(rc4.today().heatingKwh, 1.5, 1e-9);
}
