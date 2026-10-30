#pragma once
#include "control/BoundedJson.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include <array>
#include <cJSON.h>
#include <climits>
#include <cstring>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
// The week program a followed thermostat or radiator valve runs, learned by
// watching its target (owner, 30 Oct 2026: "can the E32 remember the program
// that is set on the thermostat?"). HA does not expose tado/TRV schedules, so
// per room following a device the target is recorded over each local day,
// quantised to 15 min and 0.5 degC; a change has to last 15 min (blips are
// dropped). A day with fresh data from its start to its end (gaps under 30 min)
// becomes that weekday's program, replacing the older one: 7 days, so a changed
// schedule is followed within a week. At most 8 switch points a day; a day with
// more is not a schedule and is not kept. Replayed only while the device's own
// target is stale (RoomOverrides); never written to the device. A temporary
// change made by hand on the device looks like its schedule and is learned as
// such (nothing universal tells them apart); the next week replaces it.
// Pure and single-threaded; observe() from the 10 s step, with a trusted clock.
class LearnedProgram {
public:
    static constexpr size_t maxPoints = 8;
    static constexpr uint32_t stableMs = 15 * 60000, gapMs = 30 * 60000;
    static constexpr size_t storeBytes = 2048;
    struct Day { int32_t localDay = -1; uint8_t count = 0; std::array<RoomSchedule::Point, maxPoints> points{}; };

    // One step of a following room: its fresh target, or nullopt while it is stale.
    void observe(const std::string& id, std::optional<int16_t> target, uint64_t now, uint32_t utc) {
        Room* r = find(id);
        if (!r) r = claim(id);
        if (!r) return;
        const int32_t day = RoomSchedule::localDay(utc);
        const auto local = RoomSchedule::localAt(utc);
        const uint16_t minute = uint16_t(local.minute / 15 * 15);
        if (day != r->day) {
            // A whole day seen, fresh up to its end: it becomes its weekday's program.
            if (r->day == day - 1 && r->whole && !r->overflow && r->count && r->seen && now - r->lastFreshMs <= gapMs) {
                Day& d = r->days[r->weekday];
                d.localDay = r->day; d.count = r->count; d.points = r->points;
                dirty_ = true;
            }
            r->day = day; r->weekday = local.weekday; r->count = 0; r->overflow = false;
            r->whole = target.has_value() && local.minute < 15;
            r->pending.reset();
            if (target && r->haveCurrent) add(*r, 0, r->current); // the target the day starts with
        }
        if (!target) return;
        if (r->seen && now - r->lastFreshMs > gapMs) r->whole = false;
        r->seen = true; r->lastFreshMs = now;
        const int16_t q = int16_t((*target + 25) / 50 * 50);
        if (!r->haveCurrent) { r->haveCurrent = true; r->current = q; if (!r->count) add(*r, 0, q); return; }
        if (!r->count) add(*r, 0, r->current);
        if (q == r->current) { r->pending.reset(); return; }
        if (!r->pending || r->pending->centiC != q) { r->pending = Pending{q, minute, now}; return; }
        if (now - r->pending->sinceMs < stableMs) return;
        r->current = q;
        add(*r, r->pending->minute, q);
        r->pending.reset();
    }
    // The learned target now, or nullopt when this weekday is not learned.
    std::optional<int16_t> at(const std::string& id, uint32_t utc) const {
        const Room* r = find(id);
        if (!r) return std::nullopt;
        const auto t = RoomSchedule::localAt(utc);
        const Day& d = r->days[t.weekday];
        if (d.localDay < 0 || !d.count) return std::nullopt;
        for (int i = d.count - 1; i >= 0; --i) if (d.points[i].minute <= t.minute) return d.points[i].centiC;
        return d.points[0].centiC;
    }
    const Day* days(const std::string& id) const { const Room* r = find(id); return r ? r->days.data() : nullptr; }
    // Rooms that left the plan or no longer follow a device are forgotten.
    void keepOnly(const RoomPlan& plan) {
        for (auto& r : rooms_) {
            const auto* room = r.id[0] ? plan.find(r.id) : nullptr;
            if (r.id[0] && (!room || room->followedThermostat().empty())) { dirty_ = dirty_ || r.learned(); r = Room{}; }
        }
    }
    bool takeDirty() { const bool d = dirty_; dirty_ = false; return d; }

    // {"from":entity,"days":[null|{"local_day":n,"points":[[minute,centi_c],..]} x 7 (Mon..Sun)]}; nullptr: none.
    cJSON* json(const RoomPlan::Room& room) const {
        const Room* r = find(room.id);
        cJSON* o = cJSON_CreateObject();
        cJSON* list = o && cJSON_AddStringToObject(o, "from", std::string(room.followedThermostat()).c_str())
            ? cJSON_AddArrayToObject(o, "days") : nullptr;
        if (!list) { cJSON_Delete(o); return nullptr; }
        for (size_t w = 0; w < 7; ++w) {
            const Day* d = r ? &r->days[w] : nullptr;
            if (!d || d->localDay < 0 || !d->count) { cJSON_AddItemToArray(list, cJSON_CreateNull()); continue; }
            cJSON* day = cJSON_CreateObject();
            cJSON* points = day && cJSON_AddItemToArray(list, day) && cJSON_AddNumberToObject(day, "local_day", d->localDay)
                ? cJSON_AddArrayToObject(day, "points") : nullptr;
            if (!points) { cJSON_Delete(o); return nullptr; }
            for (uint8_t i = 0; i < d->count; ++i) {
                const int pair[2]{d->points[i].minute, d->points[i].centiC};
                cJSON_AddItemToArray(points, cJSON_CreateIntArray(pair, 2));
            }
        }
        return o;
    }

    // NVS: {"v":1,"r":[{"id":..,"w":"DDDppp...|.."}]}: per weekday Mon..Sun, '.'-separated, the
    // local day in 3 and each point in 3 characters (minute/15 << 7 | centi/50), '-' unknown.
    std::string stored() const {
        std::string out = R"({"v":1,"r":[)";
        bool first = true;
        for (const auto& r : rooms_) {
            if (!r.id[0] || !r.learned()) continue;
            out += first ? "" : ","; first = false;
            out += R"({"id":")"; out += r.id; out += R"(","w":")";
            for (size_t w = 0; w < 7; ++w) {
                if (w) out += '.';
                const Day& d = r.days[w];
                if (d.localDay < 0 || !d.count) { out += '-'; continue; }
                put(out, uint32_t(d.localDay));
                for (uint8_t i = 0; i < d.count; ++i) put(out, uint32_t(d.points[i].minute / 15) << 7 | uint32_t(d.points[i].centiC / 50));
            }
            out += R"("})";
        }
        return out + "]}";
    }
    bool restore(std::string_view text) {
        *this = LearnedProgram{};
        if (text.empty() || text.size() > storeBytes || !jsonNestingWithin(text.data(), text.size(), 3)) return false;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(text.data(), text.size()), cJSON_Delete);
        const cJSON* v = cJSON_GetObjectItemCaseSensitive(root.get(), "v");
        const cJSON* list = cJSON_GetObjectItemCaseSensitive(root.get(), "r");
        if (!cJSON_IsNumber(v) || v->valuedouble != 1 || !cJSON_IsArray(list)) return false;
        LearnedProgram next;
        for (const cJSON* o = list->child; o; o = o->next) {
            const cJSON* id = cJSON_GetObjectItemCaseSensitive(o, "id");
            const cJSON* w = cJSON_GetObjectItemCaseSensitive(o, "w");
            if (!cJSON_IsString(id) || !*id->valuestring || std::strlen(id->valuestring) >= sizeof(Room::id) || !cJSON_IsString(w)) return false;
            Room* r = next.claim(id->valuestring);
            if (!r || !parseWeek(w->valuestring, *r)) return false;
        }
        *this = next;
        return true;
    }

private:
    struct Pending { int16_t centiC; uint16_t minute; uint64_t sinceMs; };
    struct Room {
        char id[33]{};
        std::array<Day, 7> days{};                 // learned, Mon..Sun
        int32_t day = INT32_MIN; uint8_t weekday = 0; // the day being recorded
        std::array<RoomSchedule::Point, maxPoints> points{};
        uint8_t count = 0;
        bool whole = false, overflow = false, seen = false, haveCurrent = false;
        int16_t current = 0;
        uint64_t lastFreshMs = 0;
        std::optional<Pending> pending;
        bool learned() const { for (const auto& d : days) if (d.localDay >= 0 && d.count) return true; return false; }
    };
    static constexpr std::string_view alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    static void put(std::string& out, uint32_t v) { for (int shift = 12; shift >= 0; shift -= 6) out += alphabet[(v >> shift) & 63]; }
    static void add(Room& r, uint16_t minute, int16_t centi) {
        // Strictly increasing within the day; a change in the same quarter (or the repeated DST hour) replaces it.
        if (r.count && minute <= r.points[r.count - 1].minute) { r.points[r.count - 1].centiC = centi; return; }
        if (r.count && r.points[r.count - 1].centiC == centi) return;
        if (r.count >= maxPoints) { r.overflow = true; return; }
        r.points[r.count++] = {minute, centi};
    }
    static bool parseWeek(const char* text, Room& r) {
        size_t w = 0;
        for (const char* p = text;; ++w) {
            if (w >= 7) return false;
            const char* end = std::strchr(p, '.');
            const size_t n = end ? size_t(end - p) : std::strlen(p);
            Day& d = r.days[w];
            if (!(n == 1 && *p == '-')) {
                if (n < 6 || n % 3 || n > 3 + 3 * maxPoints) return false;
                uint32_t value[1 + maxPoints];
                for (size_t k = 0; k < n / 3; ++k) {
                    value[k] = 0;
                    for (size_t c = 0; c < 3; ++c) {
                        const auto digit = alphabet.find(p[k * 3 + c]);
                        if (digit == std::string_view::npos) return false;
                        value[k] = value[k] << 6 | uint32_t(digit);
                    }
                }
                d.localDay = int32_t(value[0]);
                for (size_t k = 1; k < n / 3; ++k) {
                    const uint16_t minute = uint16_t((value[k] >> 7) * 15);
                    const int16_t centi = int16_t((value[k] & 127) * 50);
                    if (minute > 1439 || centi < 500 || centi > 3500 || (d.count && minute <= d.points[d.count - 1].minute)) return false;
                    d.points[d.count++] = {minute, centi};
                }
            }
            if (!end) return w == 6;
            p = end + 1;
        }
    }
    Room* find(const std::string& id) { for (auto& r : rooms_) if (r.id[0] && id == r.id) return &r; return nullptr; }
    const Room* find(const std::string& id) const { for (const auto& r : rooms_) if (r.id[0] && id == r.id) return &r; return nullptr; }
    Room* claim(const std::string& id) {
        if (id.empty() || id.size() >= sizeof(Room::id)) return nullptr;
        for (auto& r : rooms_) if (!r.id[0]) { r = Room{}; std::strcpy(r.id, id.c_str()); return &r; }
        return nullptr;
    }
    std::array<Room, RoomPlan::maxRooms> rooms_{};
    bool dirty_ = false;
};
}
