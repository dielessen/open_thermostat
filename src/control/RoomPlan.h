#pragma once
#include "control/ControlPartitionBudget.h"
#include "control/RoomDemand.h"
#include "control/RoomSchedule.h"
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
#include <string_view>
#include <vector>
namespace heating::control {
// The E32-owned room plan (schema 1), stored on the device so control keeps
// running without Home Assistant. HA and the web pages edit it; this is the
// only room list the heating control uses.
//
// Two JSON forms, both read by parse(): the API form (GET/POST /config/heating,
// week programs as "schedule" arrays) and the stored form (storedJson(), one
// NVS blob of at most storeBytes incl. its NUL). The stored form is the API
// form whenever that fits, so firmware before beta.19 still reads it after a
// rollback; only a larger plan packs each week program into a "week" string
// (4 characters per switch point instead of up to 12). 8 rooms with 4 switch
// points a day no longer exceed the store.
struct RoomPlan {
    static constexpr size_t maxRooms = 8;
    static constexpr size_t storeBytes = ControlPartitionBudget::configBytes;
    // POST /config/heating body bound: the API form of any storable plan stays
    // below it, also as Home Assistant prints it (ensure_ascii: a 40-byte name
    // grows by at most 80 bytes), also with the planner's levels in every room (beta.23: 8192 -> 9216).
    // Tests: TheApiFormOfAnyStorablePlanFitsTheRequestBound, ...WithLevelsFitsTheRequestBound.
    static constexpr size_t requestBytes = 9216;
    enum class Mode : uint8_t { shadow, active };
    enum class Emitter : uint8_t { floor, radiator };
    enum class SourceType : uint8_t { ha, ble };
    struct Source { SourceType type = SourceType::ha; std::string id; };
    struct Room {
        std::string id, name;
        RoomDemand::State state = RoomDemand::State::inactive;
        uint32_t inactiveUntil = 0;  // unix seconds; 0 = no end
        Emitter emitter = Emitter::radiator;
        std::vector<Source> sources; // priority order, 1..RoomDemand::maxSources
        std::string setpointEntity;  // HA entity with the target (e.g. the tado climate); empty = fixed only
        int16_t fallbackCentiC = 2000;  // setpoint without a fresh HA target
        int16_t minimumCentiC = 500, maximumCentiC = 2500;
        RoomSchedule schedule;  // the E32 week program without HA; empty = fallback only
        // The week planner's named levels (beta.23, "plan.levels.v1"): Comfort, Eco and Night in centi
        // degC, set independently. Only for editing and the HA presets: control keeps using the
        // temperatures of the switch points. pointLevels marks each switch point, 2 bits per point
        // (bit pair i of a day = point i): 0 own temperature, 1 Comfort, 2 Eco, 3 Night; a marked
        // point always has its level's temperature. Firmware before beta.23 ignores both fields.
        bool hasLevels = false;
        std::array<int16_t, 3> levels{};
        std::array<uint16_t, 7> pointLevels{};
        uint8_t pointLevel(size_t day, size_t i) const { return uint8_t(pointLevels[day] >> (2 * i) & 3); }
    };
    uint32_t revision = 0;  // +1 on every save; a write must name the revision it was based on
    Mode mode = Mode::shadow;
    // Flow limits for this home: minimum 20..79, maximum 21..80 degC (default 60).
    // The boiler's own heating limit still caps every request (ActiveHeatGuard).
    uint8_t minimumFlowC = 30, maximumFlowC = 60;
    std::vector<Room> rooms;

    // nullptr on success, else a short error name for the API.
    static const char* parse(const cJSON* root, RoomPlan& out) {
        RoomPlan plan;
        if (!cJSON_IsObject(root) || number(root, "schema") != 1) return "invalid_schema";
        const auto* mode = string(root, "mode");
        if (!mode || (std::strcmp(mode, "shadow") && std::strcmp(mode, "active"))) return "invalid_mode";
        plan.mode = std::strcmp(mode, "active") ? Mode::shadow : Mode::active;
        if (const auto* rev = cJSON_GetObjectItemCaseSensitive(root, "revision")) { // absent in beta.16 plans
            if (!cJSON_IsNumber(rev) || !whole(rev->valuedouble, 0, 4294967295.0)) return "invalid_revision";
            plan.revision = static_cast<uint32_t>(rev->valuedouble);
        }
        const double minFlow = number(root, "minimum_flow_c"), maxFlow = number(root, "maximum_flow_c");
        if (!whole(minFlow, 20, 79) || !whole(maxFlow, 21, 80) || minFlow >= maxFlow) return "invalid_flow_limits";
        plan.minimumFlowC = static_cast<uint8_t>(minFlow); plan.maximumFlowC = static_cast<uint8_t>(maxFlow);
        const auto* rooms = cJSON_GetObjectItemCaseSensitive(root, "rooms");
        if (!cJSON_IsArray(rooms) || cJSON_GetArraySize(rooms) > int(maxRooms)) return "invalid_rooms";
        for (const cJSON* r = rooms->child; r; r = r->next) {
            Room room;
            if (const char* e = parseRoom(r, room)) return e;
            for (const auto& other : plan.rooms) if (other.id == room.id) return "duplicate_room";
            plan.rooms.push_back(std::move(room));
        }
        out = std::move(plan);
        return nullptr;
    }
    // The capability of this firmware's plan, only in the API form (GET /config/heating): HA and the
    // pages send levels only to firmware that names it. Not in the hello: HA 0.4.0b13 accepts at most
    // 8 control capabilities there.
    static constexpr const char* levelsFeature = "plan.levels.v1";
    // The API form; empty when out of memory.
    std::string json() const { return print(false, true); }
    // The NVS form: the API form (without "features") when it fits the store, else with packed week
    // programs and levels (may still exceed storeBytes: the caller refuses plan_too_large).
    std::string storedJson() const {
        auto text = print(false, false);
        return text.size() < storeBytes ? text : print(true, false);
    }
    // A plan with levels that does not fit the store gives them up (the planner infers them again);
    // the week programs and everything control uses are kept. True when it dropped any.
    bool dropLevelsToFit() {
        if (storedJson().size() < storeBytes) return false;
        bool dropped = false;
        for (auto& r : rooms) if (r.hasLevels) { r.hasLevels = false; r.levels = {}; r.pointLevels = {}; dropped = true; }
        return dropped;
    }
    const Room* find(const std::string& id) const {
        for (const auto& r : rooms) if (r.id == id) return &r;
        return nullptr;
    }

private:
    // "week": the 7 days Mon..Sun separated by '.', each switch point 4 characters
    // of this alphabet: 24 bits = minute of day << 12 | centi degC (500..3000).
    static constexpr std::string_view weekAlphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    static constexpr size_t weekChars = 7 * RoomSchedule::maxPoints * 4 + 6;
    static std::string packWeek(const RoomSchedule& s) {
        std::string out;
        for (size_t d = 0; d < s.days.size(); ++d) {
            if (d) out += '.';
            for (uint8_t i = 0; i < s.days[d].count; ++i) {
                const uint32_t v = uint32_t(s.days[d].points[i].minute) << 12 | uint32_t(s.days[d].points[i].centiC & 4095);
                for (int shift = 18; shift >= 0; shift -= 6) out += weekAlphabet[(v >> shift) & 63];
            }
        }
        return out;
    }
    // The same rules as RoomSchedule::parse: per day at most maxPoints strictly
    // increasing minutes 0..1439, temperatures within the room's limits.
    static const char* parseWeek(const char* text, int16_t minimumCentiC, int16_t maximumCentiC, RoomSchedule& out) {
        if (!text || std::strlen(text) > weekChars) return "invalid_schedule";
        RoomSchedule s;
        size_t day = 0, digits = 0;
        uint32_t value = 0;
        for (const char* p = text;; ++p) {
            if (!*p || *p == '.') {
                if (digits) return "invalid_schedule"; // a partial switch point
                if (!*p) break;
                if (++day > 6) return "invalid_schedule";
                continue;
            }
            const auto digit = weekAlphabet.find(*p);
            if (digit == std::string_view::npos) return "invalid_schedule";
            value = value << 6 | uint32_t(digit);
            if (++digits < 4) continue;
            const auto minute = uint16_t(value >> 12);
            const auto centi = int16_t(value & 4095);
            digits = 0; value = 0;
            auto& today = s.days[day];
            if (minute > 1439 || today.count >= RoomSchedule::maxPoints
                || (today.count && minute <= today.points[today.count - 1].minute)) return "invalid_schedule";
            if (centi < minimumCentiC || centi > maximumCentiC) return "invalid_schedule_limits";
            today.points[today.count++] = {minute, centi};
        }
        if (day != 6) return "invalid_schedule";
        out = s;
        return nullptr;
    }
    std::string print(bool packedWeek, bool features) const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        if (!root) return {};
        cJSON_AddNumberToObject(root.get(), "schema", 1);
        cJSON_AddNumberToObject(root.get(), "revision", revision);
        cJSON_AddStringToObject(root.get(), "mode", mode == Mode::active ? "active" : "shadow");
        cJSON_AddNumberToObject(root.get(), "minimum_flow_c", minimumFlowC);
        cJSON_AddNumberToObject(root.get(), "maximum_flow_c", maximumFlowC);
        if (features) {
            cJSON* f = cJSON_AddArrayToObject(root.get(), "features");
            if (!f || !cJSON_AddItemToArray(f, cJSON_CreateString(levelsFeature))) return {};
        }
        cJSON* list = cJSON_AddArrayToObject(root.get(), "rooms");
        for (const auto& room : rooms) {
            cJSON* r = cJSON_CreateObject();
            if (!r || !cJSON_AddItemToArray(list, r)) { cJSON_Delete(r); return {}; }
            cJSON_AddStringToObject(r, "id", room.id.c_str());
            cJSON_AddStringToObject(r, "name", room.name.c_str());
            cJSON_AddStringToObject(r, "state", room.state == RoomDemand::State::active ? "active" : "inactive");
            cJSON_AddNumberToObject(r, "inactive_until", room.inactiveUntil);
            cJSON_AddStringToObject(r, "emitter", room.emitter == Emitter::floor ? "floor" : "radiator");
            cJSON* sources = cJSON_AddArrayToObject(r, "sources");
            for (const auto& s : room.sources) {
                cJSON* item = cJSON_CreateObject();
                if (!item || !cJSON_AddItemToArray(sources, item)) { cJSON_Delete(item); return {}; }
                cJSON_AddStringToObject(item, "type", s.type == SourceType::ble ? "ble" : "ha");
                cJSON_AddStringToObject(item, "id", s.id.c_str());
            }
            cJSON_AddStringToObject(r, "setpoint_entity", room.setpointEntity.c_str());
            cJSON_AddNumberToObject(r, "fallback_centi_c", room.fallbackCentiC);
            cJSON_AddNumberToObject(r, "minimum_centi_c", room.minimumCentiC);
            cJSON_AddNumberToObject(r, "maximum_centi_c", room.maximumCentiC);
            if (!room.schedule.empty() && packedWeek) {
                if (!cJSON_AddStringToObject(r, "week", packWeek(room.schedule).c_str())) return {};
            } else if (!room.schedule.empty()) {
                cJSON* schedule = room.schedule.json();
                if (!schedule || !cJSON_AddItemToObject(r, "schedule", schedule)) { cJSON_Delete(schedule); return {}; }
            }
            if (room.hasLevels && packedWeek) {
                if (!cJSON_AddStringToObject(r, "lv", packLevels(room).c_str())) return {};
            } else if (room.hasLevels) {
                cJSON* lv = cJSON_AddObjectToObject(r, "levels");
                if (!lv || !cJSON_AddNumberToObject(lv, "comfort", room.levels[0]) || !cJSON_AddNumberToObject(lv, "eco", room.levels[1])
                    || !cJSON_AddNumberToObject(lv, "night", room.levels[2])) return {};
                if (!room.schedule.empty() && !cJSON_AddStringToObject(r, "schedule_levels", markText(room, true).c_str())) return {};
            }
        }
        std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(root.get()), cJSON_free);
        return text ? text.get() : "";
    }
    static const char* parseRoom(const cJSON* r, Room& room) {
        const auto* id = string(r, "id");
        const auto* name = string(r, "name");
        if (!id || !identifier(id, 32)) return "invalid_room_id";
        if (!name || !*name || std::strlen(name) > 40) return "invalid_room_name";
        room.id = id; room.name = name;
        const auto* state = string(r, "state");
        if (!state || (std::strcmp(state, "active") && std::strcmp(state, "inactive"))) return "invalid_room_state";
        room.state = std::strcmp(state, "active") ? RoomDemand::State::inactive : RoomDemand::State::active;
        const double until = number(r, "inactive_until");
        if (!whole(until, 0, 4102444800.0)) return "invalid_inactive_until";
        room.inactiveUntil = static_cast<uint32_t>(until);
        const auto* emitter = string(r, "emitter");
        if (!emitter || (std::strcmp(emitter, "floor") && std::strcmp(emitter, "radiator"))) return "invalid_emitter";
        room.emitter = std::strcmp(emitter, "floor") ? Emitter::radiator : Emitter::floor;
        const auto* sources = cJSON_GetObjectItemCaseSensitive(r, "sources");
        if (!cJSON_IsArray(sources)) return "invalid_sources";
        for (const cJSON* s = sources->child; s; s = s->next) {
            const auto* type = string(s, "type");
            const auto* sid = string(s, "id");
            if (!type || !sid || room.sources.size() >= RoomDemand::maxSources) return "invalid_sources";
            Source source;
            if (!std::strcmp(type, "ble") && bleAddress(sid)) source.type = SourceType::ble;
            else if (!std::strcmp(type, "ha") && entity(sid)) source.type = SourceType::ha;
            else return "invalid_sources";
            source.id = sid;
            for (const auto& other : room.sources) if (other.type == source.type && other.id == source.id) return "duplicate_source";
            room.sources.push_back(std::move(source));
        }
        if (room.sources.empty()) return "invalid_sources";
        const auto* setpoint = string(r, "setpoint_entity");
        if (!setpoint || (*setpoint && !entity(setpoint))) return "invalid_setpoint_entity";
        room.setpointEntity = setpoint;
        const double fallback = number(r, "fallback_centi_c"), lo = number(r, "minimum_centi_c"), hi = number(r, "maximum_centi_c");
        if (!whole(lo, 500, 3000) || !whole(hi, 500, 3000) || lo > hi || !whole(fallback, lo, hi)) return "invalid_room_limits";
        room.fallbackCentiC = int16_t(fallback); room.minimumCentiC = int16_t(lo); room.maximumCentiC = int16_t(hi);
        // Optional (absent in beta.16 plans); "week" only in the stored form of a large plan.
        const auto* schedule = cJSON_GetObjectItemCaseSensitive(r, "schedule");
        const auto* week = cJSON_GetObjectItemCaseSensitive(r, "week");
        if (schedule && week) return "invalid_schedule";
        const char* error = nullptr;
        if (week) error = cJSON_IsString(week) ? parseWeek(week->valuestring, room.minimumCentiC, room.maximumCentiC, room.schedule)
                                               : "invalid_schedule";
        else if (schedule) error = RoomSchedule::parse(schedule, room.minimumCentiC, room.maximumCentiC, room.schedule);
        return error ? error : parseLevels(r, room);
    }
    // Optional levels (beta.23): "levels" {comfort, eco, night} with "schedule_levels" (one digit 0..3
    // per switch point, days separated by '.'), or in the packed stored form "lv": Comfort, Eco and Night as 2 characters of the week alphabet each
    // (12 bits), then the marks of all switch points of the week, 3 per character (2 bits each, first
    // point in the high bits).
    static const char* parseLevels(const cJSON* r, Room& room) {
        const auto* levels = cJSON_GetObjectItemCaseSensitive(r, "levels");
        const auto* marks = cJSON_GetObjectItemCaseSensitive(r, "schedule_levels");
        const auto* packed = cJSON_GetObjectItemCaseSensitive(r, "lv");
        if (!levels && !marks && !packed) return nullptr;
        if (packed && (levels || marks)) return "invalid_levels";
        if (marks && !levels) return "invalid_schedule_levels";
        size_t total = 0;
        for (const auto& d : room.schedule.days) total += d.count;
        std::string digits;
        if (packed) {
            if (!cJSON_IsString(packed)) return "invalid_levels";
            const std::string_view text = packed->valuestring;
            if (text.size() != 6 && text.size() != 6 + (total + 2) / 3) return "invalid_levels";
            std::array<uint32_t, 32> values{};
            for (size_t c = 0; c < text.size(); ++c) {
                const auto v = weekAlphabet.find(text[c]);
                if (v == std::string_view::npos) return "invalid_levels";
                values[c] = uint32_t(v);
            }
            for (size_t k = 0; k < 3; ++k) room.levels[k] = int16_t(values[2 * k] << 6 | values[2 * k + 1]);
            if (text.size() > 6)
                for (size_t i = 0; i < total; ++i) digits += char('0' + (values[6 + i / 3] >> (4 - 2 * (i % 3)) & 3));
        } else {
            if (!cJSON_IsObject(levels)) return "invalid_levels";
            const char* keys[] = {"comfort", "eco", "night"};
            for (size_t k = 0; k < 3; ++k) {
                const double v = number(levels, keys[k]);
                if (!whole(v, 500, 3000)) return "invalid_levels";
                room.levels[k] = int16_t(v);
            }
            if (marks) {
                if (!cJSON_IsString(marks) || room.schedule.empty()) return "invalid_schedule_levels";
                const std::string_view text = marks->valuestring;
                size_t day = 0, n = 0;
                for (const char ch : text) {
                    if (ch == '.') {
                        if (n != room.schedule.days[day].count || ++day > 6) return "invalid_schedule_levels";
                        n = 0;
                        continue;
                    }
                    ++n;
                    digits += ch;
                }
                if (day != 6 || n != room.schedule.days[6].count) return "invalid_schedule_levels";
            }
        }
        for (const auto v : room.levels) if (v < room.minimumCentiC || v > room.maximumCentiC) return "invalid_levels";
        size_t at = 0;
        for (size_t d = 0; d < 7 && !digits.empty(); ++d)
            for (uint8_t i = 0; i < room.schedule.days[d].count; ++i, ++at) {
                const char ch = digits[at];
                if (ch < '0' || ch > '3') return "invalid_schedule_levels";
                const uint8_t level = uint8_t(ch - '0');
                // A marked point carries its level's temperature, so control and the planner agree.
                if (level && room.schedule.days[d].points[i].centiC != room.levels[level - 1]) return "invalid_schedule_levels";
                room.pointLevels[d] |= uint16_t(level << (2 * i));
            }
        room.hasLevels = true;
        return nullptr;
    }
    static std::string markText(const Room& room, bool dots) {
        std::string out;
        for (size_t d = 0; d < 7; ++d) {
            if (d && dots) out += '.';
            for (uint8_t i = 0; i < room.schedule.days[d].count; ++i) out += char('0' + room.pointLevel(d, i));
        }
        return out;
    }
    static std::string packLevels(const Room& room) {
        std::string out;
        for (const auto v : room.levels) { out += weekAlphabet[(v >> 6) & 63]; out += weekAlphabet[v & 63]; }
        const auto marks = markText(room, false);
        for (size_t i = 0; i < marks.size(); i += 3) {
            uint32_t v = 0;
            for (size_t j = 0; j < 3; ++j) v = v << 2 | uint32_t(i + j < marks.size() ? marks[i + j] - '0' : 0);
            out += weekAlphabet[v];
        }
        return out;
    }
    static const char* string(const cJSON* o, const char* key) {
        const auto* p = cJSON_GetObjectItemCaseSensitive(o, key);
        return cJSON_IsString(p) ? p->valuestring : nullptr;
    }
    static double number(const cJSON* o, const char* key) {
        const auto* p = cJSON_GetObjectItemCaseSensitive(o, key);
        return cJSON_IsNumber(p) ? p->valuedouble : NAN;
    }
    static bool whole(double v, double lo, double hi) { return std::isfinite(v) && v >= lo && v <= hi && std::floor(v) == v; }
    static bool identifier(const char* s, size_t max) {
        const size_t n = std::strlen(s);
        if (!n || n > max) return false;
        for (size_t i = 0; i < n; ++i) if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '_')) return false;
        return true;
    }
    // HA entity id: domain.object_id, lower case
    static bool entity(const char* s) {
        const char* dot = std::strchr(s, '.');
        if (!dot || dot == s || !dot[1] || std::strlen(s) > 80) return false;
        for (const char* p = s; *p; ++p) if (p != dot && !((*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') || *p == '_')) return false;
        return true;
    }
    static bool bleAddress(const char* s) {
        if (std::strlen(s) != 12) return false;
        for (const char* p = s; *p; ++p) if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
        return true;
    }
};
}
