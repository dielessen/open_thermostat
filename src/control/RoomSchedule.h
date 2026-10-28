#pragma once
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <optional>
namespace heating::control {
// A room's own week program: per day (Mon..Sun) up to maxPoints switch points
// {minute of day, centi degC}. A point holds until the next one, also across
// midnight and empty days, so a night setback and morning warm-up keep running
// on the E32 without Home Assistant. JSON: 7 arrays of [minute, centi_c],
// e.g. [[[390,2050],[1350,1800]],[],[],[],[],[],[]]. Pure: no IO or clock.
struct RoomSchedule {
    static constexpr size_t maxPoints = 6;
    struct Point { uint16_t minute = 0; int16_t centiC = 0; };
    struct Day { std::array<Point, maxPoints> points{}; uint8_t count = 0; };
    struct LocalTime { uint8_t weekday = 0; uint16_t minute = 0; }; // weekday 0 = Monday
    std::array<Day, 7> days{};

    bool empty() const {
        for (const auto& d : days) if (d.count) return false;
        return true;
    }

    // nullptr on success, else a short error name. Temperatures must lie
    // within the room's limits; out is untouched on error.
    static const char* parse(const cJSON* array, int16_t minimumCentiC, int16_t maximumCentiC, RoomSchedule& out) {
        RoomSchedule s;
        if (!cJSON_IsArray(array) || cJSON_GetArraySize(array) != 7) return "invalid_schedule";
        size_t d = 0;
        for (const cJSON* day = array->child; day; day = day->next, ++d) {
            if (!cJSON_IsArray(day) || cJSON_GetArraySize(day) > int(maxPoints)) return "invalid_schedule";
            auto& today = s.days[d];
            for (const cJSON* p = day->child; p; p = p->next) {
                if (!cJSON_IsArray(p) || cJSON_GetArraySize(p) != 2
                    || !cJSON_IsNumber(p->child) || !cJSON_IsNumber(p->child->next)) return "invalid_schedule";
                const double minute = p->child->valuedouble, centi = p->child->next->valuedouble;
                if (!whole(minute, 0, 1439) || (today.count && minute <= today.points[today.count - 1].minute))
                    return "invalid_schedule"; // strictly increasing within the day
                if (!whole(centi, minimumCentiC, maximumCentiC)) return "invalid_schedule_limits";
                today.points[today.count++] = {uint16_t(minute), int16_t(centi)};
            }
        }
        out = s;
        return nullptr;
    }
    // The 7-day array; nullptr when out of memory.
    cJSON* json() const {
        cJSON* week = cJSON_CreateArray();
        for (const auto& d : days) {
            cJSON* day = cJSON_CreateArray();
            if (!day || !cJSON_AddItemToArray(week, day)) { cJSON_Delete(day); cJSON_Delete(week); return nullptr; }
            for (uint8_t i = 0; i < d.count; ++i) {
                const int pair[2]{d.points[i].minute, d.points[i].centiC};
                cJSON* p = cJSON_CreateIntArray(pair, 2);
                if (!p || !cJSON_AddItemToArray(day, p)) { cJSON_Delete(p); cJSON_Delete(week); return nullptr; }
            }
        }
        return week;
    }

    // Setpoint at local time: the last switch point at or before it, looking
    // back across earlier days (and last week); nullopt for an empty schedule.
    std::optional<int16_t> at(uint8_t weekday, uint16_t minute) const {
        if (weekday > 6) return std::nullopt;
        const auto& today = days[weekday];
        for (int i = today.count - 1; i >= 0; --i)
            if (today.points[i].minute <= minute) return today.points[i].centiC;
        for (int back = 1; back <= 7; ++back) {
            const auto& d = days[(weekday + 7 - back) % 7];
            if (d.count) return d.points[d.count - 1].centiC;
        }
        return std::nullopt;
    }
    std::optional<int16_t> at(const LocalTime& t) const { return at(t.weekday, t.minute); }

    // From the device's own localtime_r() (TZ from the network settings).
    static std::optional<LocalTime> local(const std::tm& t) {
        if (t.tm_wday < 0 || t.tm_wday > 6 || t.tm_hour < 0 || t.tm_hour > 23 || t.tm_min < 0 || t.tm_min > 59)
            return std::nullopt;
        return LocalTime{uint8_t((t.tm_wday + 6) % 7), uint16_t(t.tm_hour * 60 + t.tm_min)};
    }
    // Europe/Amsterdam from unix seconds (>= 0) without TZ: CET, CEST from the last
    // Sunday of March to the last Sunday of October, both at 01:00 UTC.
    static LocalTime amsterdam(int64_t utc) {
        int year = 1970 + int(floorDiv(utc, 86400) / 366);
        while (daysFromCivil(year + 1, 1, 1) * 86400 <= utc) ++year;
        const auto lastSunday = [year](unsigned m) { // seconds at 01:00 UTC
            const int64_t d = daysFromCivil(year, m, 31);
            return (d - (floorMod(d, 7) + 4) % 7) * 86400 + 3600; // day 0 was a Thursday
        };
        const bool summer = utc >= lastSunday(3) && utc < lastSunday(10);
        const int64_t local = utc + (summer ? 7200 : 3600);
        return {uint8_t(floorMod(floorDiv(local, 86400) + 3, 7)), uint16_t(floorMod(local, 86400) / 60)};
    }

private:
    static bool whole(double v, double lo, double hi) { return std::isfinite(v) && v >= lo && v <= hi && std::floor(v) == v; }
    static int64_t floorDiv(int64_t a, int64_t b) { return a / b - (a % b < 0); }
    static int64_t floorMod(int64_t a, int64_t b) { return a - floorDiv(a, b) * b; }
    // Days since 1970-01-01 (H. Hinnant's days_from_civil).
    static int64_t daysFromCivil(int y, unsigned m, unsigned d) {
        y -= m <= 2;
        const int era = (y >= 0 ? y : y - 399) / 400;
        const unsigned yoe = unsigned(y - era * 400);
        const unsigned doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
        return int64_t(era) * 146097 + int64_t(yoe * 365 + yoe / 4 - yoe / 100 + doy) - 719468;
    }
};
}
