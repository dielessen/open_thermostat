// The holiday planner (rc.4, F8, "house.holidays.v1"): up to 8 periods planned ahead with
// their own holiday temperature (control/RoomOverrides.h). The house mode is holiday inside a
// period and returns to what it was afterwards; the warm-up before the end works as for the
// older "holiday until"; periods are merged, a past one refused, the running one shortened or
// ended. Also the records (their bounds, a restart inside a period, an older record without
// holidays, the rollback copy for rc.3) and R1-04 (the warm-up lead stays with its room id).
#include "control/ControlPartitionBudget.h"
#include "control/RoomOverrides.h"
#include "RoomOverridesBeta21.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstring>
#include <initializer_list>
#include <memory>
#include <string>
#include <utility>

namespace {
using heating::control::ControlPartitionBudget;
using heating::control::RoomEngine;
using heating::control::RoomOverrides;
using heating::control::RoomOverridesBeta21;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t minute = 60000;
constexpr uint32_t hour = 3600, day = 86400;
constexpr uint32_t monNoon = 1793617200;    // Mon 2 Nov 2026 12:00 Amsterdam (CET)
constexpr uint32_t tue1000 = 1793696400;    // Tue 3 Nov 10:00
constexpr uint32_t fri1800 = 1793984400;    // Fri 6 Nov 18:00
constexpr uint32_t mon0630 = 1794202200;    // Mon 9 Nov 06:30
constexpr uint32_t dec19 = 1797670800;      // Sat 19 Dec 10:00
constexpr uint32_t jan3 = 1798995600;       // Sun 3 Jan 2027 18:00
constexpr uint32_t satNoonDst = 1792836000; // Sat 24 Oct 2026 12:00 CEST, DST ends Sunday 03:00
constexpr uint32_t mon0630Cet = 1792992600; // Mon 26 Oct 06:30 CET

// As test_room_overrides: a radiator room with a Monday program (06:30 20.5, 22:30 18.0, which
// holds the rest of the week), a floor room without a program (fallback 20.0) and an inactive bath.
std::string room(const char* id) {
    if (!std::strcmp(id, "living"))
        return R"({"id":"living","name":"Living","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000001"}],"setpoint_entity":"","fallback_centi_c":2000,
  "minimum_centi_c":500,"maximum_centi_c":2400,"schedule":[[[390,2050],[1350,1800]],[],[],[],[],[],[]]})";
    if (!std::strcmp(id, "study"))
        return R"({"id":"study","name":"Study","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ble","id":"a4c138000002"}],"setpoint_entity":"","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500})";
    return R"({"id":"bath","name":"Bath","state":"inactive","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000003"}],"setpoint_entity":"","fallback_centi_c":2200,"minimum_centi_c":500,"maximum_centi_c":2500})";
}
RoomPlan plan(std::initializer_list<const char*> ids = {"living", "study", "bath"}) {
    std::string text = R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[)";
    bool first = true;
    for (const char* id : ids) { text += (first ? "" : ",") + room(id); first = false; }
    Json root(cJSON_Parse((text + "]}").c_str()), cJSON_Delete);
    RoomPlan p;
    EXPECT_EQ(RoomPlan::parse(root.get(), p), nullptr);
    return p;
}
struct Saved { bool comfort = false, holidays = false; };
const char* command(RoomOverrides& o, const RoomPlan& p, const std::string& body, std::optional<uint32_t> utc, Saved* saved = nullptr,
                    uint64_t now = 0) {
    Json root(cJSON_Parse(body.c_str()), cJSON_Delete);
    Saved s;
    const char* error = o.command(root.get(), p, now, utc, s.comfort, &s.holidays);
    if (saved) *saved = s;
    return error;
}
std::string periods(std::initializer_list<std::pair<uint32_t, uint32_t>> list, const std::string& extra = "") {
    std::string out = R"({"holidays":[)";
    bool first = true;
    for (const auto& [from, until] : list) {
        out += std::string(first ? "" : ",") + R"({"from":)" + std::to_string(from) + R"(,"until":)" + std::to_string(until) + "}";
        first = false;
    }
    return out + "]" + extra + "}";
}
std::string holidayMode(uint32_t until) { return R"({"house_mode":"holiday","until":)" + std::to_string(until) + "}"; }
const auto noLead = [](size_t, uint32_t, int16_t, int16_t) { return uint32_t(0); };
std::string print(const cJSON* item) {
    char* text = cJSON_PrintUnformatted(item);
    std::string out = text ? text : "";
    cJSON_free(text);
    return out;
}
// The house's "away" status as /status/heating and fw/state/heating carry it.
Json away(const RoomOverrides& o, const RoomPlan& p, uint64_t now = 0) {
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON_AddArrayToObject(status.get(), "rooms");
    EXPECT_TRUE(o.addStatus(status.get(), p, now));
    return Json(cJSON_DetachItemFromObject(status.get(), "away"), cJSON_Delete);
}
std::string list(const RoomOverrides& o) {
    std::string out;
    for (const auto& h : o.holidays()) out += "[" + std::to_string(h.from) + "," + std::to_string(h.until) + "]";
    return out;
}
std::string pair(uint32_t from, uint32_t until) { return "[" + std::to_string(from) + "," + std::to_string(until) + "]"; }
std::optional<int16_t> setpoint(const RoomPlan& p, const RoomOverrides& o, size_t room, uint64_t now, std::optional<uint32_t> utc) {
    RoomEngine e; e.setPlan(p);
    for (const char* id : {"a4c138000001", "a4c138000002", "a4c138000003"}) e.bleReading(id, 1900, now);
    e.step(now, utc, o.adjust());
    return e.result(room).setpoint;
}
}

TEST(RoomHolidays, APlannedHolidayStartsAndEndsByItself) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    Saved saved;
    ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_FALSE(saved.comfort);  // nothing runs yet: the comfort record stays as it is
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_EQ(print(cJSON_GetObjectItem(away(o, p).get(), "holidays")), R"([{"from":1793696400,"until":1793984400}])");
    o.step(p, minute, tue1000 - 1, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");
    // It begins by itself: every room at most the holiday temperature (the away temperature here).
    o.step(p, 2 * minute, tue1000, noLead);
    EXPECT_STREQ(o.houseMode(), "holiday");
    EXPECT_STREQ(o.view(0).mode, "away");
    EXPECT_EQ(o.view(0).until, fri1800);
    EXPECT_EQ(o.view(0).targetCentiC, 1500);
    EXPECT_EQ(o.adjust()[1].ceiling, 1500);
    EXPECT_EQ(setpoint(p, o, 1, 2 * minute, tue1000), 1500);
    EXPECT_TRUE(o.awayOn());
    EXPECT_EQ(o.awayUntil(), fri1800);
    const auto a = away(o, p);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(a.get(), "on")));
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(a.get(), "source")), "manual");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(a.get(), "until")), fri1800);
    // Warm again in time for its end: the floor room 3 h ahead, the radiator room 1 h.
    size_t asked = 0;
    const auto lead = [&](size_t room, uint32_t until, int16_t from, int16_t target) {
        ++asked;
        EXPECT_EQ(until, fri1800);
        EXPECT_EQ(from, 1500);
        EXPECT_EQ(target, room == 0 ? 1800 : 2000);  // living: Monday 22:30 holds on Friday; study: its fallback
        return uint32_t(room == 0 ? hour : 3 * hour);
    };
    o.step(p, 3 * minute, fri1800 - 2 * hour, lead);
    EXPECT_GT(asked, 0u);
    EXPECT_STREQ(o.view(1).mode, "away_return");
    EXPECT_EQ(o.adjust()[1].setpoint, 2000);
    EXPECT_STREQ(o.view(0).mode, "away");
    o.step(p, 4 * minute, fri1800 - 30 * 60, lead);
    EXPECT_STREQ(o.view(0).mode, "away_return");
    EXPECT_EQ(setpoint(p, o, 0, 4 * minute, fri1800 - 30 * 60), 1800);
    // It ends by itself and leaves the list.
    o.step(p, 5 * minute, fri1800, lead);
    EXPECT_STREQ(o.houseMode(), "auto");
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_EQ(o.holidays().count, 0);
    EXPECT_FALSE(o.awayOn());
    EXPECT_EQ(print(cJSON_GetObjectItem(away(o, p).get(), "holidays")), "[]");
}

TEST(RoomHolidays, TheHouseReturnsToTheModeItHad) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    {   // At home before: at home again afterwards.
        RoomOverrides o;
        ASSERT_EQ(command(o, p, R"({"house_mode":"home"})", monNoon), nullptr);
        ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon), nullptr);
        o.step(p, 0, tue1000, noLead);
        EXPECT_STREQ(o.houseMode(), "holiday");
        EXPECT_STREQ(o.view(1).mode, "away");
        o.step(p, minute, fri1800, noLead);
        EXPECT_STREQ(o.houseMode(), "home");
        EXPECT_EQ(o.view(1).mode, nullptr);
    }
    {   // Away before: away again afterwards, and the warm-up only up to the away temperature.
        RoomOverrides o;
        ASSERT_EQ(command(o, p, R"({"house_mode":"away","temperature":15,"holiday_temperature":12})", monNoon), nullptr);
        ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon), nullptr);
        o.step(p, 0, tue1000, noLead);
        EXPECT_EQ(o.view(1).targetCentiC, 1200);
        size_t asked = 0;
        o.step(p, minute, fri1800 - hour, [&](size_t, uint32_t until, int16_t from, int16_t target) {
            ++asked; EXPECT_EQ(until, fri1800); EXPECT_EQ(from, 1200); EXPECT_EQ(target, 1500); return uint32_t(2 * hour); });
        EXPECT_GT(asked, 0u);
        EXPECT_STREQ(o.view(1).mode, "away_return");
        EXPECT_EQ(o.adjust()[1].setpoint, 1500);
        o.step(p, 2 * minute, fri1800, noLead);
        EXPECT_STREQ(o.houseMode(), "away");
        EXPECT_EQ(o.view(1).targetCentiC, 1500);
        EXPECT_EQ(o.view(1).until, 0u);
    }
    {   // Automatic: everyone away during the holiday still gets the holiday temperature.
        RoomOverrides o;
        ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}, R"(,"holiday_temperature":11.5)"), monNoon), nullptr);
        EXPECT_TRUE(o.input(R"({"kind":"presence","home":false})", p, 0));
        o.step(p, 0, tue1000, noLead);
        EXPECT_STREQ(o.view(0).mode, "away");
        EXPECT_EQ(o.view(0).targetCentiC, 1150);
        o.step(p, minute, fri1800, noLead);
        EXPECT_STREQ(o.view(0).mode, "presence_away");  // the people decide again
        EXPECT_EQ(o.view(0).targetCentiC, 1500);
    }
}

TEST(RoomHolidays, TheHolidayTemperatureIsTheAwayTemperatureUntilSet) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    EXPECT_EQ(o.holidayCentiC(), 1500);
    EXPECT_FALSE(o.holidayTemperatureSet());
    ASSERT_EQ(command(o, p, R"({"house_mode":"auto","temperature":16})", monNoon), nullptr);
    EXPECT_EQ(o.holidayCentiC(), 1600);  // follows the away temperature
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(away(o, p).get(), "holiday_temperature_c")), 16);
    Saved saved;
    ASSERT_EQ(command(o, p, R"({"holiday_temperature":12.5})", std::nullopt, &saved), nullptr);  // no clock needed
    EXPECT_TRUE(saved.holidays);
    EXPECT_FALSE(saved.comfort);
    EXPECT_EQ(o.holidayCentiC(), 1250);
    EXPECT_EQ(o.awayCentiC(), 1600);
    EXPECT_EQ(o.holidaysStored(), R"({"v":1,"c":1250,"p":[]})");
    ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon), nullptr);
    o.step(p, 0, tue1000, noLead);
    EXPECT_EQ(o.adjust()[0].ceiling, 1250);
    ASSERT_EQ(command(o, p, R"({"house_mode":"away"})", tue1000), nullptr);  // away ends the holiday: its own value
    EXPECT_EQ(o.adjust()[0].ceiling, 1600);
    // null: the away temperature again.
    ASSERT_EQ(command(o, p, R"({"holiday_temperature":null})", tue1000, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_EQ(o.holidayCentiC(), 1600);
    EXPECT_EQ(o.holidaysStored(), R"({"v":1,"p":[]})");
    // The same limits as the away temperature; never with a room or the away temperature alone.
    for (const char* bad : {R"({"holiday_temperature":4.5})", R"({"holiday_temperature":25.5})", R"({"holiday_temperature":"12"})"})
        EXPECT_STREQ(command(o, p, bad, tue1000), "invalid_temperature") << bad;
    EXPECT_STREQ(command(o, p, R"({"holiday_temperature":12,"temperature":15})", tue1000), "invalid_request");
    EXPECT_STREQ(command(o, p, R"({"holiday_temperature":12,"room":"living"})", tue1000), "invalid_request");
    ASSERT_EQ(command(o, p, R"({"house_mode":"auto","temperature":17,"holiday_temperature":13})", tue1000, &saved), nullptr);
    EXPECT_TRUE(saved.comfort && saved.holidays);
    EXPECT_EQ(o.awayCentiC(), 1700);
    EXPECT_EQ(o.holidayCentiC(), 1300);
}

TEST(RoomHolidays, PeriodsAreMergedAndCheckedOnSave) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    // Overlapping and touching periods become one, in any order; a separate one stays apart.
    Saved saved;
    ASSERT_EQ(command(o, p, periods({{dec19, jan3}, {fri1800, mon0630}, {tue1000, fri1800 - hour}, {fri1800 - 2 * hour, fri1800}}),
                      monNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_EQ(list(o), pair(tue1000, mon0630) + pair(dec19, jan3));
    ASSERT_EQ(command(o, p, periods({{dec19, jan3}, {tue1000, mon0630}}), monNoon, &saved), nullptr);
    EXPECT_FALSE(saved.holidays);  // the same list: nothing to write
    // A period that already ended is refused, and nothing changes.
    EXPECT_STREQ(command(o, p, periods({{monNoon - day, monNoon - hour}}), monNoon), "holiday_in_past");
    EXPECT_STREQ(command(o, p, periods({{dec19, jan3}, {monNoon - day, monNoon}}), monNoon), "holiday_in_past");
    EXPECT_EQ(list(o), pair(tue1000, mon0630) + pair(dec19, jan3));
    // One that began already and still runs is fine.
    ASSERT_EQ(command(o, p, periods({{monNoon - day, tue1000}}), monNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "holiday");
    EXPECT_STREQ(command(o, p, periods({{tue1000, monNoon + 367 * day}}), monNoon), "holiday_too_far");
    for (const std::string& bad : {periods({{tue1000, tue1000}}), periods({{fri1800, tue1000}}),
                                   std::string(R"({"holidays":[{"from":1793696400}]})"), std::string(R"({"holidays":[{"from":1.5,"until":1793984400}]})"),
                                   std::string(R"({"holidays":[[1793696400,1793984400]]})"), std::string(R"({"holidays":{"from":1}})"),
                                   std::string(R"({"holidays":[{"from":-1,"until":1793984400}]})"),
                                   periods({{tue1000, tue1000 + 1}, {tue1000 + 2, tue1000 + 3}, {tue1000 + 4, tue1000 + 5}, {tue1000 + 6, tue1000 + 7},
                                            {tue1000 + 8, tue1000 + 9}, {tue1000 + 10, tue1000 + 11}, {tue1000 + 12, tue1000 + 13},
                                            {tue1000 + 14, tue1000 + 15}, {tue1000 + 16, tue1000 + 17}})})
        EXPECT_STREQ(command(o, p, bad, monNoon), "invalid_holidays") << bad;
    EXPECT_STREQ(command(o, p, periods({{tue1000, fri1800}}), std::nullopt), "no_clock");
    EXPECT_STREQ(command(o, p, periods({{tue1000, fri1800}}, R"(,"temperature":15)"), monNoon), "invalid_request");
    EXPECT_STREQ(command(o, p, periods({{tue1000, fri1800}}, R"(,"house_mode":"auto")"), monNoon), "invalid_request");
    EXPECT_STREQ(command(o, p, periods({{tue1000, fri1800}}, R"(,"away":true)"), monNoon), "invalid_request");
    EXPECT_STREQ(command(o, p, periods({{tue1000, fri1800}}, R"(,"room":"living")"), monNoon), "invalid_request");
    EXPECT_EQ(list(o), pair(monNoon - day, tue1000));
    // Eight separate ones fit; an empty list removes every holiday.
    ASSERT_EQ(command(o, p, periods({{tue1000, tue1000 + 1}, {tue1000 + 2, tue1000 + 3}, {tue1000 + 4, tue1000 + 5}, {tue1000 + 6, tue1000 + 7},
                                     {tue1000 + 8, tue1000 + 9}, {tue1000 + 10, tue1000 + 11}, {tue1000 + 12, tue1000 + 13},
                                     {tue1000 + 14, tue1000 + 15}}), monNoon), nullptr);
    EXPECT_EQ(o.holidays().count, 8);
    // "Holiday from now" needs a ninth place unless it joins one of them.
    EXPECT_STREQ(command(o, p, holidayMode(monNoon + hour), monNoon), "too_many_holidays");
    ASSERT_EQ(command(o, p, holidayMode(tue1000 + 1), monNoon), nullptr);
    EXPECT_EQ(o.holidays().count, 8);
    EXPECT_EQ(o.holidays().items[0].from, monNoon);
    ASSERT_EQ(command(o, p, R"({"holidays":[]})", monNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays && saved.comfort);  // the running one ended: the rollback copy too
    EXPECT_EQ(o.holidays().count, 0);
    EXPECT_STREQ(o.houseMode(), "auto");
}

TEST(RoomHolidays, TheRunningHolidayIsShortenedOrEnded) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    const uint32_t wedNoon = monNoon + 2 * day, thuNoon = monNoon + 3 * day;
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"house_mode":"home"})", monNoon), nullptr);
    ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}, {dec19, jan3}}), monNoon), nullptr);
    o.step(p, 0, wedNoon, noLead);
    EXPECT_STREQ(o.houseMode(), "holiday");
    // Shortened: the list with its new end.
    Saved saved;
    ASSERT_EQ(command(o, p, periods({{tue1000, thuNoon}, {dec19, jan3}}), wedNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_EQ(o.awayUntil(), thuNoon);
    // "Holiday until" while one runs: a new end for it; the mode after it (at home) stays.
    ASSERT_EQ(command(o, p, holidayMode(fri1800), wedNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_EQ(list(o), pair(tue1000, fri1800) + pair(dec19, jan3));
    EXPECT_TRUE(o.homeMode());
    // The same end again (an older Home Assistant sends it with the away temperature): nothing changes.
    ASSERT_EQ(command(o, p, R"({"house_mode":"holiday","temperature":15,"until":1793984400})", wedNoon, &saved), nullptr);
    EXPECT_FALSE(saved.holidays || saved.comfort);
    EXPECT_TRUE(o.homeMode());
    // Ended now: the list without it. At home again, the December holiday stays planned.
    ASSERT_EQ(command(o, p, periods({{dec19, jan3}}), wedNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays);
    EXPECT_STREQ(o.houseMode(), "home");
    EXPECT_EQ(list(o), pair(dec19, jan3));
    // "Holiday until" with none running: one from now, back to Automatic afterwards (as before rc.4).
    ASSERT_EQ(command(o, p, holidayMode(thuNoon), wedNoon, &saved), nullptr);
    EXPECT_TRUE(saved.holidays && saved.comfort);
    EXPECT_EQ(list(o), pair(wedNoon, thuNoon) + pair(dec19, jan3));
    EXPECT_FALSE(o.homeMode());
    o.step(p, minute, thuNoon, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");
    // Choosing a mode ends a running holiday (Home Assistant's select, the older away command).
    ASSERT_EQ(command(o, p, holidayMode(thuNoon + day), thuNoon), nullptr);
    ASSERT_EQ(command(o, p, R"({"house_mode":"away"})", thuNoon + hour), nullptr);
    EXPECT_STREQ(o.houseMode(), "away");
    EXPECT_EQ(list(o), pair(dec19, jan3));
    ASSERT_EQ(command(o, p, holidayMode(thuNoon + day), thuNoon + hour), nullptr);
    ASSERT_EQ(command(o, p, R"({"away":false})", thuNoon + 2 * hour), nullptr);
    EXPECT_STREQ(o.houseMode(), "auto");
    EXPECT_EQ(list(o), pair(dec19, jan3));
    // The older dated away command is a holiday from now as well.
    ASSERT_EQ(command(o, p, R"({"away":true,"until":1793984400})", wedNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "holiday");
    EXPECT_EQ(list(o), pair(wedNoon, fri1800) + pair(dec19, jan3));
}

TEST(RoomHolidays, APeriodAcrossTheDstChange) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    // Saturday 12:00 summer time to Monday 06:30 winter time: 43.5 h on the E32's clock.
    ASSERT_EQ(command(o, p, periods({{satNoonDst, mon0630Cet}}), satNoonDst - day), nullptr);
    o.step(p, 0, satNoonDst - 1, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");
    o.step(p, minute, satNoonDst, noLead);
    EXPECT_STREQ(o.houseMode(), "holiday");
    // The warm-up towards the program at the local end time (Monday 06:30, 20.5 degC).
    size_t asked = 0;
    const auto lead = [&](size_t room, uint32_t until, int16_t, int16_t target) {
        ++asked;
        EXPECT_EQ(until, mon0630Cet);
        EXPECT_EQ(target, room == 0 ? 2050 : 2000);
        return uint32_t(2 * hour);
    };
    o.step(p, 2 * minute, mon0630Cet - 3 * hour, lead);
    EXPECT_GT(asked, 0u);
    EXPECT_STREQ(o.view(0).mode, "away");
    o.step(p, 3 * minute, mon0630Cet - 2 * hour, lead);
    EXPECT_STREQ(o.view(0).mode, "away_return");
    EXPECT_EQ(o.adjust()[0].setpoint, 2050);
    o.step(p, 4 * minute, mon0630Cet - 1, lead);
    EXPECT_STREQ(o.houseMode(), "holiday");
    o.step(p, 5 * minute, mon0630Cet, lead);
    EXPECT_STREQ(o.houseMode(), "auto");
    EXPECT_EQ(o.holidays().count, 0);
}

TEST(RoomHolidays, KeptAcrossARestartInsideAPeriod) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    const uint32_t wedNoon = monNoon + 2 * day;
    RoomOverrides before;
    ASSERT_EQ(command(before, p, periods({{tue1000, fri1800}, {dec19, jan3}}, R"(,"holiday_temperature":12)"), monNoon), nullptr);
    before.step(p, 0, wedNoon, noLead);
    const auto comfort = before.stored(), holidays = before.holidaysStored();
    EXPECT_EQ(holidays, R"({"v":1,"c":1200,"p":[[1793696400,1793984400],[1797670800,1798995600]]})");
    EXPECT_EQ(comfort, R"({"v":1,"away_c":1500,"o":[],"away_until":1793984400})");  // the rollback copy
    // After the restart, before the clock: the rooms follow their plan and wait for it.
    RoomOverrides after;
    ASSERT_TRUE(after.restore(comfort));
    ASSERT_TRUE(after.restoreHolidays(holidays));
    EXPECT_FALSE(after.legacyHoliday());  // the holidays record wins over the rollback copy
    after.step(p, 0, std::nullopt, noLead);
    EXPECT_EQ(after.view(0).mode, nullptr);
    EXPECT_TRUE(after.view(0).waiting);
    EXPECT_EQ(setpoint(p, after, 1, 0, std::nullopt), 2000);
    // With the clock: still on holiday, at the holiday temperature.
    after.step(p, minute, wedNoon + 60, noLead);
    EXPECT_STREQ(after.houseMode(), "holiday");
    EXPECT_EQ(after.view(1).targetCentiC, 1200);
    EXPECT_EQ(after.view(1).until, fri1800);
    EXPECT_FALSE(after.view(1).waiting);
    // A restart after its end: gone once the clock is known, the next one stays.
    RoomOverrides late;
    ASSERT_TRUE(late.restore(comfort));
    ASSERT_TRUE(late.restoreHolidays(holidays));
    late.step(p, 0, fri1800 + hour, noLead);
    EXPECT_STREQ(late.houseMode(), "auto");
    EXPECT_EQ(list(late), pair(dec19, jan3));
    EXPECT_EQ(late.stored(), R"({"v":1,"away_c":1500,"o":[]})");
}

TEST(RoomHolidays, AnOlderRecordWithoutHolidays) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    // rc.3's comfort record and no holidays record: no holidays, the away temperature on holiday.
    RoomOverrides o;
    ASSERT_TRUE(o.restore(R"({"v":1,"away_c":1550,"o":[]})"));
    EXPECT_FALSE(o.restoreHolidays(""));
    EXPECT_EQ(o.holidays().count, 0);
    EXPECT_EQ(o.holidayCentiC(), 1550);
    const auto a = away(o, p);
    EXPECT_EQ(print(cJSON_GetObjectItem(a.get(), "holidays")), "[]");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(a.get(), "holiday_temperature_c")), 15.5);
    // Records this firmware cannot read change nothing.
    for (const char* bad : {"{", R"({"v":2,"p":[]})", R"({"v":1})", R"({"v":1,"p":[[5,1]]})", R"({"v":1,"p":[[1,2,3]]})",
                            R"({"v":1,"p":[[1.5,2]]})", R"({"v":1,"c":9000,"p":[]})", R"({"v":1,"c":"x","p":[]})",
                            R"({"v":1,"p":[[1,2],[3,4],[5,6],[7,8],[9,10],[11,12],[13,14],[15,16],[17,18]]})"}) {
        EXPECT_FALSE(o.restoreHolidays(bad)) << bad;
        EXPECT_EQ(o.holidaysStored(), R"({"v":1,"p":[]})") << bad;
    }
    EXPECT_FALSE(o.restoreHolidays(std::string(RoomOverrides::holidayStoreBytes + 1, ' ')));
    // A holiday set before rc.4 (rc.3's dated away) runs on, and moves to its own record once.
    RoomOverrides legacy;
    ASSERT_TRUE(legacy.restore(R"({"v":1,"away_c":1600,"o":[],"away_until":1793984400})"));
    EXPECT_FALSE(legacy.restoreHolidays(""));
    EXPECT_TRUE(legacy.legacyHoliday());
    EXPECT_STREQ(legacy.houseMode(), "holiday");
    EXPECT_EQ(legacy.holidaysStored(), R"({"v":1,"p":[[0,1793984400]]})");
    legacy.step(p, 0, std::nullopt, noLead);
    EXPECT_EQ(legacy.view(0).mode, nullptr);   // without a clock: comfort, never a cold return
    EXPECT_TRUE(legacy.view(0).waiting);
    legacy.step(p, minute, monNoon, noLead);
    EXPECT_STREQ(legacy.view(0).mode, "away");
    EXPECT_EQ(legacy.adjust()[0].ceiling, 1600);
    legacy.legacyHolidaySaved();
    EXPECT_FALSE(legacy.legacyHoliday());
    // Home and a dated away together: no record this firmware (or rc.3) wrote.
    EXPECT_FALSE(legacy.restore(R"({"v":1,"away_c":1500,"o":[],"away_until":1793984400,"home":true})"));
}

TEST(RoomHolidays, TheRollbackCopyKeepsAHolidayForRc3) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    const uint32_t wedNoon = monNoon + 2 * day;
    for (const char* mode : {"auto", "home", "away"}) {
        RoomOverrides o;
        ASSERT_EQ(command(o, p, std::string(R"({"house_mode":")") + mode + R"(","temperature":16})", monNoon), nullptr);
        ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon), nullptr);
        o.step(p, 0, wedNoon, noLead);
        RoomOverridesBeta21 old;
        ASSERT_TRUE(old.restore(o.stored())) << o.stored();
        old.step(p, 0, wedNoon, noLead);
        if (!std::strcmp(mode, "auto")) {  // rc.3 keeps the holiday until its end, then Automatic
            EXPECT_TRUE(old.awayOn());
            EXPECT_EQ(old.awayUntil(), fri1800);
            EXPECT_STREQ(old.view(0).mode, "away");
        } else if (!std::strcmp(mode, "home")) {  // rc.3 refuses home with a dated away: at home only
            EXPECT_FALSE(old.awayOn());
        } else {  // away until switched back
            EXPECT_TRUE(old.awayOn());
            EXPECT_EQ(old.awayUntil(), 0u);
        }
        EXPECT_EQ(old.awayCentiC(), 1600);
    }
    // Ended by itself: the next comfort write carries no copy any more.
    RoomOverrides o;
    ASSERT_EQ(command(o, p, periods({{tue1000, fri1800}}), monNoon), nullptr);
    o.step(p, 0, fri1800, noLead);
    EXPECT_EQ(o.stored(), R"({"v":1,"away_c":1500,"o":[]})");
}

TEST(RoomHolidays, TheRecordsAndTheLargestCommandFitTheirBounds) {
    std::string record = R"({"v":1,"c":2500,"p":[)";
    for (int i = 0; i < 8; ++i)
        record += std::string(i ? "," : "") + "[" + std::to_string(4102444000u + 2 * i) + "," + std::to_string(4102444001u + 2 * i) + "]";
    record += "]}";
    RoomOverrides o;
    ASSERT_TRUE(o.restoreHolidays(record)) << record;
    EXPECT_EQ(o.holidaysStored(), record);
    EXPECT_LE(record.size(), RoomOverrides::holidayStoreBytes);
    EXPECT_LT(record.size() + 1, ControlPartitionBudget::holidayRecordBytes + 1);  // with its NUL
    // The largest command: 8 periods of ten-digit seconds and a holiday temperature, as the pages
    // send it (JSON.stringify) and as Home Assistant does (json.dumps with spaces).
    std::string compact = R"({"holidays":[)", spaced = R"({"holidays": [)";
    for (int i = 0; i < 8; ++i) {
        const std::string f = std::to_string(1893456000u + 2 * i), u = std::to_string(1893456001u + 2 * i);
        compact += std::string(i ? "," : "") + R"({"from":)" + f + R"(,"until":)" + u + "}";
        spaced += std::string(i ? ", " : "") + R"({"from": )" + f + R"(, "until": )" + u + "}";
    }
    compact += R"(],"holiday_temperature":12.25})";
    spaced += R"(], "holiday_temperature": 12.25})";
    EXPECT_LE(compact.size(), RoomOverrides::commandBytes);
    EXPECT_LE(spaced.size(), RoomOverrides::commandBytes);
    EXPECT_TRUE(heating::control::jsonNestingWithin(spaced.data(), spaced.size(), 3));
    std::printf("[ holidays ] record %zu B (of %zu), command %zu/%zu B (of %zu)\n", record.size(), RoomOverrides::holidayStoreBytes,
                compact.size(), spaced.size(), RoomOverrides::commandBytes);
}

TEST(RoomHolidays, TheStatusAnnouncesThemAndTheApiListsEveryOne) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    ASSERT_EQ(command(o, p, periods({{dec19, jan3}, {tue1000, fri1800}, {fri1800 + day, mon0630}}, R"(,"holiday_temperature":12.5)"),
                      monNoon), nullptr);
    o.step(p, 0, monNoon, noLead);
    const auto a = away(o, p);
    EXPECT_EQ(print(cJSON_GetObjectItem(a.get(), "holidays")),
              R"([{"from":1793696400,"until":1793984400},{"from":1794070800,"until":1794202200}])");  // the next two
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(a.get(), "holiday_temperature_c")), 12.5);
    Json api(o.json(p, 0), cJSON_Delete);
    ASSERT_TRUE(api);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(api.get(), "holidays")), 3);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(api.get(), "holiday_temperature")), 12.5);
    EXPECT_TRUE(cJSON_IsArray(cJSON_GetObjectItem(cJSON_GetObjectItem(api.get(), "away"), "holidays")));
}

// R1-04: the warm-up lead is kept per room id, so a plan edit (a room moved, removed or added)
// never hands it to another room.
TEST(RoomHolidays, AWarmUpLeadStaysWithItsRoomAcrossAPlanEdit) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto first = plan({"living", "study", "bath"}), moved = plan({"study", "living", "bath"}),
               without = plan({"living", "bath"});
    RoomOverrides o;
    ASSERT_EQ(command(o, first, periods({{tue1000, fri1800}}), monNoon), nullptr);
    const auto lead = [&](size_t room, uint32_t, int16_t, int16_t) { return uint32_t(room == 1 ? 3 * hour : 0); };
    o.step(first, 0, fri1800 - 2 * hour, lead);
    EXPECT_STREQ(o.view(1).mode, "away_return");  // the study
    EXPECT_STREQ(o.view(0).mode, "away");
    // The study moves to the front: its lead goes along, the living room does not get it.
    o.planChanged(moved, 0, fri1800 - 2 * hour);
    EXPECT_STREQ(o.view(0).mode, "away_return");
    EXPECT_EQ(o.adjust()[0].setpoint, 2000);
    EXPECT_STREQ(o.view(1).mode, "away");
    EXPECT_EQ(o.adjust()[1].ceiling, 1500);
    // Removed: nobody warms early; added again: it waits for its own lead (the next minute).
    o.planChanged(without, 0, fri1800 - 2 * hour);
    EXPECT_STREQ(o.view(0).mode, "away");
    o.planChanged(first, 0, fri1800 - 2 * hour);
    EXPECT_STREQ(o.view(1).mode, "away");
    o.step(first, minute, fri1800 - 2 * hour + 60, lead);
    EXPECT_STREQ(o.view(1).mode, "away_return");
}
