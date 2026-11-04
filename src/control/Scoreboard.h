#pragma once
#include "control/AutoTuner.h"
#include "control/BoundedJson.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
namespace heating::control {
// The daily scoreboard (rc.4, F1): per local day what the owner judges the thermostat on, and
// what the arrival feedback (L2) and the self-tuning (AutoTuner) read back. Per room: was it
// warm on time (minutes late, negative = early) and how far it overshot; per house: heating
// starts per heating hour, hours of short cycling, the heating gas (kWh, the learner's estimate)
// and the degree-days (18 degC base, the Dutch "graaddagen"). Today and yesterday are kept;
// the counts of starts, hours, short cycling and overshoot come from AutoTuner's days (the same
// local day), only the outdoor, the gas and the arrivals are summed here. Pure; stored() and
// restore() keep it over a restart (ScoreboardNvs, hourly with the self-tuning's record).
class Scoreboard {
public:
    static constexpr double degreeDayBaseC = 18;
    static constexpr size_t storedMaxBytes = 400;
    struct Day {
        int32_t day = -1;
        double outdoorSum = 0;      // degC x s
        uint32_t outdoorS = 0;
        double heatingKwh = 0;
        std::array<int16_t, RoomPlan::maxRooms> arrivalMin{};
        uint8_t arrivalSeen = 0;    // bit i: arrivalMin[i] holds a judged morning
    };

    // Every step with a trusted clock: the seconds since the last step, the outdoor (fresh only)
    // and the learner's heating energy total (GasCalibration::heatingKwh, this boot).
    void step(int64_t utc, uint32_t dtS, std::optional<int16_t> outdoorCentiC, double heatingKwhTotal) {
        const int32_t day = RoomSchedule::localDay(utc);
        if (today_.day < 0) today_.day = day;
        else if (day > today_.day) { yesterday_ = today_; hasYesterday_ = true; today_ = {}; today_.day = day; }
        if (outdoorCentiC && dtS) { today_.outdoorSum += *outdoorCentiC / 100.0 * dtS; today_.outdoorS += dtS; }
        if (haveKwh_ && heatingKwhTotal >= kwh_) today_.heatingKwh += heatingKwhTotal - kwh_;
        kwh_ = heatingKwhTotal; haveKwh_ = true;
    }
    // A judged morning (ArrivalLearner): into the day of its switch time, if that is today or yesterday.
    void arrival(size_t room, int64_t atUtc, int16_t errorMin) {
        if (room >= RoomPlan::maxRooms) return;
        const int32_t day = RoomSchedule::localDay(atUtc);
        Day* d = day == today_.day ? &today_ : hasYesterday_ && day == yesterday_.day ? &yesterday_ : nullptr;
        if (!d) return;
        d->arrivalMin[room] = errorMin; d->arrivalSeen |= uint8_t(1u << room);
    }
    const Day& today() const { return today_; }
    const Day* yesterday() const { return hasYesterday_ ? &yesterday_ : nullptr; }
    // A plan edit: the arrivals follow their rooms (new index -> old index, -1: none).
    void remap(const std::array<int8_t, RoomPlan::maxRooms>& from) {
        for (Day* d : {&today_, &yesterday_}) {
            std::array<int16_t, RoomPlan::maxRooms> a{};
            uint8_t seen = 0;
            for (size_t i = 0; i < RoomPlan::maxRooms; ++i)
                if (from[i] >= 0 && (d->arrivalSeen >> from[i] & 1)) { a[i] = d->arrivalMin[from[i]]; seen |= uint8_t(1u << i); }
            d->arrivalMin = a; d->arrivalSeen = seen;
        }
    }
    // New index -> old index of two plans (-1: a new room).
    static std::array<int8_t, RoomPlan::maxRooms> roomMap(const RoomPlan& from, const RoomPlan& to) {
        std::array<int8_t, RoomPlan::maxRooms> map{};
        map.fill(-1);
        for (size_t i = 0; i < to.rooms.size() && i < RoomPlan::maxRooms; ++i)
            for (size_t o = 0; o < from.rooms.size() && o < RoomPlan::maxRooms; ++o)
                if (from.rooms[o].id == to.rooms[i].id) { map[i] = int8_t(o); break; }
        return map;
    }

    // "scoreboard": {"yesterday":{..}|null,"today":{..}}; a day: {"day":"2026-11-04","heating_h",
    // "heating_starts_per_h","short_cycle_h","heating_kwh","degree_days","rooms":[{"id","on_time_min",
    // "overshoot_c"}]} with null where nothing was measured; rooms without any measurement that day
    // are left out. compact (the MQTT topic fw/telemetry/scoreboard, at most 1.5 KB): today without
    // its rooms, so eight rooms with 32-character ids stay within 1 KB. false: no memory.
    bool addJson(cJSON* parent, const AutoTuner& tuner, const RoomPlan& plan, bool compact = false) const {
        cJSON* o = cJSON_AddObjectToObject(parent, "scoreboard");
        if (!o) return false;
        if (hasYesterday_) { if (!dayJson(o, "yesterday", yesterday_, tuner.yesterday(), plan, true)) return false; }
        else if (!cJSON_AddNullToObject(o, "yesterday")) return false;
        return today_.day >= 0 ? dayJson(o, "today", today_, tuner.today(), plan, !compact) : cJSON_AddNullToObject(o, "today") != nullptr;
    }
    // {"t":{"d":..,"os":..,"on":..,"k":..,"a":[..]},"y":{..}|null}; a: the arrivals (null: none).
    std::string stored() const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        if (!root) return {};
        if (!storedDay(root.get(), "t", today_)) return {};
        if (hasYesterday_) { if (!storedDay(root.get(), "y", yesterday_)) return {}; }
        else cJSON_AddNullToObject(root.get(), "y");
        char* text = cJSON_PrintUnformatted(root.get());
        std::string out = text ? text : "";
        cJSON_free(text);
        return out.size() <= storedMaxBytes ? out : std::string();
    }
    // A stored record: today when its day is `today`, yesterday when it is the day before; anything else is dropped.
    bool restore(const char* text, int32_t today) {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(parseNestedJson(text, text ? std::strlen(text) : 0));
        if (!root) return false;
        Day t, y;
        const bool hasT = readDay(cJSON_GetObjectItemCaseSensitive(root.get(), "t"), t);
        const bool hasY = readDay(cJSON_GetObjectItemCaseSensitive(root.get(), "y"), y);
        if (!hasT) return false;
        if (t.day == today) { today_ = t; if (hasY && y.day == today - 1) { yesterday_ = y; hasYesterday_ = true; } }
        else if (t.day == today - 1) { yesterday_ = t; hasYesterday_ = true; today_ = {}; today_.day = today; }
        else return false;
        return true;
    }
    // "2026-11-04" of a local day number (RoomSchedule::localDay). H. Hinnant's civil_from_days.
    static void civil(int32_t z, char (&out)[11]) {
        z += 719468;
        const int32_t era = (z >= 0 ? z : z - 146096) / 146097;
        const uint32_t doe = uint32_t(z - era * 146097);
        const uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        const int32_t y = int32_t(yoe) + era * 400;
        const uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100), mp = (5 * doy + 2) / 153;
        const uint32_t d = doy - (153 * mp + 2) / 5 + 1, m = mp < 10 ? mp + 3 : mp - 9;
        std::snprintf(out, sizeof out, "%04d-%02u-%02u", y + (m <= 2), m, d);
    }

private:
    static bool dayJson(cJSON* parent, const char* key, const Day& d, const AutoTuner::Day& t, const RoomPlan& plan, bool withRooms) {
        cJSON* o = cJSON_AddObjectToObject(parent, key);
        if (!o) return false;
        char date[11];
        civil(d.day, date);
        cJSON_AddStringToObject(o, "day", date);
        const bool tuned = t.day == d.day;
        const int hours = tuned ? __builtin_popcount(t.hours) : 0;
        const auto number = [&](const char* k, std::optional<double> v, double scale) {
            if (v && std::isfinite(*v)) cJSON_AddNumberToObject(o, k, std::floor(*v * scale + 0.5) / scale); else cJSON_AddNullToObject(o, k);
        };
        number("heating_h", tuned ? std::optional<double>(hours) : std::nullopt, 1);
        number("heating_starts_per_h", tuned && hours ? std::optional<double>(double(t.starts) / hours) : std::nullopt, 10);
        number("short_cycle_h", tuned ? std::optional<double>(t.shortS / 3600.0) : std::nullopt, 10);
        number("heating_kwh", d.heatingKwh > 0 ? std::optional<double>(d.heatingKwh) : std::nullopt, 10);
        number("degree_days", d.outdoorS ? std::optional<double>(std::max(0.0, degreeDayBaseC - d.outdoorSum / d.outdoorS)) : std::nullopt, 10);
        // Only the rooms with a measurement that day (the topic goes out every 5 minutes; HA and the
        // page read a missing room as "nothing measured", like a null). Without rooms: no "rooms" key.
        if (!withRooms) return true;
        cJSON* rooms = cJSON_AddArrayToObject(o, "rooms");
        if (!rooms) return false;
        for (size_t i = 0; i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
            const bool arrived = d.arrivalSeen >> i & 1, over = tuned && (t.overSeen >> i & 1);
            if (!arrived && !over) continue;
            cJSON* r = cJSON_CreateObject();
            if (!r || !cJSON_AddItemToArray(rooms, r)) { cJSON_Delete(r); return false; }
            cJSON_AddStringToObject(r, "id", plan.rooms[i].id.c_str());
            if (arrived) cJSON_AddNumberToObject(r, "on_time_min", d.arrivalMin[i]); else cJSON_AddNullToObject(r, "on_time_min");
            if (over) cJSON_AddNumberToObject(r, "overshoot_c", t.over[i] / 100.0); else cJSON_AddNullToObject(r, "overshoot_c");
        }
        return true;
    }
    static bool storedDay(cJSON* parent, const char* key, const Day& d) {
        cJSON* o = cJSON_AddObjectToObject(parent, key);
        if (!o) return false;
        cJSON_AddNumberToObject(o, "d", d.day);
        cJSON_AddNumberToObject(o, "os", std::floor(d.outdoorSum + 0.5));
        cJSON_AddNumberToObject(o, "on", d.outdoorS);
        cJSON_AddNumberToObject(o, "k", std::floor(d.heatingKwh * 100 + 0.5) / 100);
        if (!d.arrivalSeen) return cJSON_AddNullToObject(o, "a") != nullptr;
        cJSON* a = cJSON_AddArrayToObject(o, "a");
        for (size_t i = 0; a && i < RoomPlan::maxRooms; ++i)
            cJSON_AddItemToArray(a, d.arrivalSeen >> i & 1 ? cJSON_CreateNumber(d.arrivalMin[i]) : cJSON_CreateNull());
        return a != nullptr;
    }
    static bool readDay(const cJSON* o, Day& d) {
        if (!cJSON_IsObject(o)) return false;
        const cJSON* day = cJSON_GetObjectItemCaseSensitive(o, "d");
        const cJSON* os = cJSON_GetObjectItemCaseSensitive(o, "os");
        const cJSON* on = cJSON_GetObjectItemCaseSensitive(o, "on");
        const cJSON* k = cJSON_GetObjectItemCaseSensitive(o, "k");
        if (!cJSON_IsNumber(day) || !cJSON_IsNumber(os) || !cJSON_IsNumber(on) || !cJSON_IsNumber(k)) return false;
        if (!(on->valuedouble >= 0 && on->valuedouble <= 86400 * 2 && k->valuedouble >= 0 && k->valuedouble <= 1000)) return false;
        d = {};
        d.day = int32_t(day->valuedouble); d.outdoorSum = os->valuedouble; d.outdoorS = uint32_t(on->valuedouble); d.heatingKwh = k->valuedouble;
        const cJSON* a = cJSON_GetObjectItemCaseSensitive(o, "a");
        if (cJSON_IsArray(a)) {
            size_t i = 0;
            for (const cJSON* e = a->child; e && i < RoomPlan::maxRooms; e = e->next, ++i)
                if (cJSON_IsNumber(e) && std::fabs(e->valuedouble) <= 32000) { d.arrivalMin[i] = int16_t(e->valuedouble); d.arrivalSeen |= uint8_t(1u << i); }
        }
        return true;
    }
    Day today_, yesterday_;
    bool hasYesterday_ = false, haveKwh_ = false;
    double kwh_ = 0;
};
}
