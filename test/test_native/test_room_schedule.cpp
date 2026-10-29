#include "control/RoomSchedule.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstdlib>
#include <memory>
#include <string>

namespace {
using heating::control::RoomSchedule;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
enum : uint8_t { mon, tue, wed, thu, fri, sat, sun };

// Weekdays up 06:30, setback 22:30; weekend up 08:00, setback 23:00; Wednesday same as Tuesday.
const char* week = R"([[[390,2050],[1350,1800]],[[390,2050],[1350,1800]],[],
 [[390,2050],[1350,1800]],[[390,2050],[1350,1800]],[[480,2100],[1380,1800]],[[480,2100],[1380,1700]]])";

const char* parseError(const std::string& text, RoomSchedule& out, int16_t lo = 500, int16_t hi = 2500) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    return RoomSchedule::parse(root.get(), lo, hi, out);
}
RoomSchedule parsed(const std::string& text) {
    RoomSchedule s;
    EXPECT_EQ(parseError(text, s), nullptr) << text;
    return s;
}
std::string print(const RoomSchedule& s) {
    Json j(s.json(), cJSON_Delete);
    std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(j.get()), cJSON_free);
    return text ? text.get() : "";
}

TEST(RoomSchedule, ParsesTheWeekAndRoundTripsUnchanged) {
    const auto s = parsed(week);
    ASSERT_EQ(s.days[mon].count, 2);
    EXPECT_EQ(s.days[mon].points[0].minute, 390);
    EXPECT_EQ(s.days[mon].points[0].centiC, 2050);
    EXPECT_EQ(s.days[wed].count, 0);
    EXPECT_FALSE(s.empty());
    EXPECT_EQ(print(parsed(print(s))), print(s));
    EXPECT_EQ(print(s), "[[[390,2050],[1350,1800]],[[390,2050],[1350,1800]],[],"
        "[[390,2050],[1350,1800]],[[390,2050],[1350,1800]],[[480,2100],[1380,1800]],[[480,2100],[1380,1700]]]");
    EXPECT_TRUE(parsed("[[],[],[],[],[],[],[]]").empty());
}

TEST(RoomSchedule, RejectsBadShapesOrderAndRangesAndKeepsTheOldSchedule) {
    auto s = parsed(week);
    const std::string days6 = "[[],[],[],[],[],[]]", tail = ",[],[],[],[],[],[]]";
    EXPECT_STREQ(parseError(days6, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[],[],[],[],[],[],[],[]]", s), "invalid_schedule");
    EXPECT_STREQ(parseError("{}", s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[600,2000],[390,1800]]" + tail, s), "invalid_schedule");   // unsorted
    EXPECT_STREQ(parseError("[[[390,2000],[390,1800]]" + tail, s), "invalid_schedule");   // duplicate minute
    EXPECT_STREQ(parseError("[[[1440,2000]]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[-1,2000]]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[390.5,2000]]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[\"06:30\",2000]]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[390,2000,1]]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[390,2000]" + tail, s), "invalid_schedule");
    EXPECT_STREQ(parseError("[[[0,1],[1,1],[2,1],[3,1],[4,1],[5,1],[6,1]]" + tail, s, 0, 10), "invalid_schedule"); // 7 points
    EXPECT_EQ(parseError("[[[0,1],[1,1],[2,1],[3,1],[4,1],[5,1]]" + tail, s, 0, 10), nullptr); // 6 points
    s = parsed(week);
    EXPECT_STREQ(parseError("[[[390,2600]]" + tail, s), "invalid_schedule_limits");    // above the room maximum
    EXPECT_STREQ(parseError("[[[390,1500]]" + tail, s, 1600, 2400), "invalid_schedule_limits");
    EXPECT_EQ(print(s), print(parsed(week)));
}

TEST(RoomSchedule, NightSetbackAndMorningWarmUp) {
    const auto s = parsed(week);
    EXPECT_EQ(s.at(tue, 389), 1800);  // still last night's setback
    EXPECT_EQ(s.at(tue, 390), 2050);  // warm-up starts on the switch minute
    EXPECT_EQ(s.at(tue, 1349), 2050);
    EXPECT_EQ(s.at(tue, 1350), 1800);
    EXPECT_EQ(s.at(tue, 1439), 1800);
    EXPECT_EQ(s.at(sat, 400), 1800);  // weekend sleeps in
    EXPECT_EQ(s.at(sat, 480), 2100);
}

TEST(RoomSchedule, WrapsFromSundayToMondayAndAcrossEmptyDays) {
    const auto s = parsed(week);
    EXPECT_EQ(s.at(mon, 0), 1700);    // Sunday's last point
    EXPECT_EQ(s.at(mon, 389), 1700);
    EXPECT_EQ(s.at(wed, 900), 1800);  // empty Wednesday keeps Tuesday's last value
    EXPECT_EQ(s.at(thu, 100), 1800);
    // Only Friday programmed: Friday morning still runs last Friday's last point.
    const auto friday = parsed("[[],[],[],[],[[420,2100],[1320,1600]],[],[]]");
    EXPECT_EQ(friday.at(fri, 100), 1600);
    EXPECT_EQ(friday.at(fri, 420), 2100);
    EXPECT_EQ(friday.at(mon, 600), 1600);
    EXPECT_EQ(parsed("[[],[],[],[],[],[],[]]").at(mon, 600), std::nullopt);
    EXPECT_EQ(RoomSchedule{}.at(sun, 0), std::nullopt);
    EXPECT_EQ(s.at(7, 0), std::nullopt);
}

TEST(RoomSchedule, LocalTimeFromTmStartsTheWeekOnMonday) {
    std::tm t{}; t.tm_wday = 0; t.tm_hour = 6; t.tm_min = 30;
    ASSERT_TRUE(RoomSchedule::local(t));
    EXPECT_EQ(RoomSchedule::local(t)->weekday, sun);
    EXPECT_EQ(RoomSchedule::local(t)->minute, 390);
    t.tm_wday = 1; EXPECT_EQ(RoomSchedule::local(t)->weekday, mon);
    t.tm_hour = 24; EXPECT_FALSE(RoomSchedule::local(t));
}

void expectLocal(int64_t utc, uint8_t weekday, uint16_t minute) {
    const auto t = RoomSchedule::localAt(utc);
    EXPECT_EQ(t.weekday, weekday) << utc;
    EXPECT_EQ(t.minute, minute) << utc;
}

// The week program runs on the device's own TZ (network settings), not a fixed zone.
TEST(RoomSchedule, LocalTimeFollowsTheDeviceTimeZoneAndItsDaylightSavingTime) {
    const int64_t mar29 = 1774742400, oct25 = 1792886400; // 2026, 00:00 UTC, both Sundays (EU switch days)
    const int64_t mar8 = 1772928000, nov1 = 1793491200;   // 2026, 00:00 UTC, both Sundays (US switch days)
    {
        ScopedTz tz(ScopedTz::amsterdam);
        expectLocal(mar29 - 3601, sat, 1439);  // Saturday 23:59 CET
        expectLocal(mar29 - 3600, sun, 0);     // Saturday 23:00 UTC = Sunday 00:00 CET
        expectLocal(mar29 + 3599, sun, 119);   // 01:59 CET
        expectLocal(mar29 + 3600, sun, 180);   // 03:00 CEST
        expectLocal(oct25 + 3599, sun, 179);   // 02:59 CEST
        expectLocal(oct25 + 3600, sun, 120);   // 02:00 CET again
        expectLocal(1767223800, thu, 30);      // 2025-12-31 23:30 UTC = New Year 00:30 CET
        expectLocal(1782941400, wed, 1410);    // 2026-07-01 21:30 UTC = 23:30 CEST
    }
    {
        ScopedTz tz(ScopedTz::london);
        expectLocal(mar29 - 1, sat, 1439);     // 23:59 GMT
        expectLocal(mar29 + 3599, sun, 59);    // 00:59 GMT
        expectLocal(mar29 + 3600, sun, 120);   // 02:00 BST
        expectLocal(oct25 + 3599, sun, 119);   // 01:59 BST
        expectLocal(oct25 + 3600, sun, 60);    // 01:00 GMT again
    }
    {
        ScopedTz tz(ScopedTz::newYork);
        expectLocal(mar8 + 7 * 3600 - 1, sun, 119); // 01:59 EST
        expectLocal(mar8 + 7 * 3600, sun, 180);     // 03:00 EDT
        expectLocal(nov1 + 4 * 3600 - 1, sat, 1439); // Saturday 23:59 EDT
        expectLocal(nov1 + 4 * 3600, sun, 0);
        expectLocal(nov1 + 6 * 3600 - 1, sun, 119); // 01:59 EDT
        expectLocal(nov1 + 6 * 3600, sun, 60);      // 01:00 EST again
        expectLocal(mar29 + 3600, sat, 1260);       // the EU switch moment is Saturday 21:00 EDT
    }
}

// A Monday 06:30 warm-up starts at 06:30 local wall time in every zone, winter and summer.
TEST(RoomSchedule, WarmupFollowsTheLocalWallClockInEveryZone) {
    const auto s = parsed(week);
    const auto rises = [&s](const char* zone, int64_t winter, int64_t summer) {
        ScopedTz tz(zone);
        EXPECT_EQ(s.at(RoomSchedule::localAt(winter - 1)), 1700) << zone; // Sunday's 23:00 setback
        EXPECT_EQ(s.at(RoomSchedule::localAt(winter)), 2050) << zone;
        EXPECT_EQ(s.at(RoomSchedule::localAt(summer - 1)), 1700) << zone;
        EXPECT_EQ(s.at(RoomSchedule::localAt(summer)), 2050) << zone;
    };
    // Mon 2026-01-05 and Mon 2026-07-06, 06:30 local in UTC.
    rises(ScopedTz::amsterdam, 1767591000, 1783312200);                    // 05:30 / 04:30 UTC
    rises(ScopedTz::london, 1767591000 + 3600, 1783312200 + 3600);         // 06:30 / 05:30 UTC
    rises(ScopedTz::newYork, 1767591000 + 6 * 3600, 1783312200 + 6 * 3600); // 11:30 / 10:30 UTC
    rises("UTC0", 1767591000 + 3600, 1783312200 + 2 * 3600);
}

// localAt() agrees with the C library's tm for several POSIX rules, also minute
// by minute across the switch Sundays.
TEST(RoomSchedule, LocalAtMatchesLocaltime) {
    for (const char* zone : {ScopedTz::amsterdam, ScopedTz::london, ScopedTz::newYork, "UTC0", "AEST-10AEDT,M10.1.0,M4.1.0/3"}) {
        ScopedTz tz(zone);
        const auto check = [zone](int64_t utc) {
            const std::time_t t = static_cast<std::time_t>(utc);
            std::tm tm{}; ASSERT_TRUE(localtime_r(&t, &tm));
            const auto want = RoomSchedule::local(tm);
            const auto got = RoomSchedule::localAt(utc);
            ASSERT_TRUE(want);
            ASSERT_EQ(got.weekday, want->weekday) << zone << " " << utc;
            ASSERT_EQ(got.minute, want->minute) << zone << " " << utc;
        };
        for (int64_t u = 946684800; u < 4102444800; u += 7 * 86400 + 1237) check(u);
        for (int64_t day = 20089; day < 21915; ++day) { // every Sunday in Mar/Apr/Oct/Nov 2025..2029, 00:00-12:00 UTC
            std::tm tm{}; const std::time_t t = static_cast<std::time_t>(day * 86400);
            gmtime_r(&t, &tm);
            if (tm.tm_wday != 0 || (tm.tm_mon != 2 && tm.tm_mon != 3 && tm.tm_mon != 9 && tm.tm_mon != 10)) continue;
            for (int64_t u = day * 86400; u < day * 86400 + 12 * 3600; u += 60) check(u);
        }
    }
}
}
