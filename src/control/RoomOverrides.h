#pragma once
#include "control/BoundedJson.h"
#include "control/RoomEngine.h"
#include "control/WarmupPlanner.h"
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
// Comfort on top of the room plan (beta.19 items 16-18), without changing the
// plan or its format: a temporary override per room (boost, "until the next
// switch point", "2 h at 21 degC"), a window/door pause per room from Home
// Assistant contacts, and away (until a date, or "everyone away" from HA's
// presence). Only room TARGETS change: the flow limits, frost protection and
// ActiveHeatGuard stay as they are (the guard still heats any room below 8 degC).
//
// Priority per active room: open window (after its delay; target = frost floor)
// > override > away return (warm-up before the away end) > away (the plan target,
// at most the away temperature) > the plan (HA target, week program, fallback).
//
// Time: an override set with a trusted clock ends at a wall-clock time, kept in
// NVS (one small versioned record beside the plan, "ot_heating"/"comfort"), and
// also at the same uptime: whichever comes first. After a restart an override or
// a dated away waits for a trusted clock and is dropped when its end has passed;
// until then the room simply follows its plan (conservative: never warmer, and
// never longer, than asked). Without a trusted clock an override lasts its
// duration in uptime and is not kept across a restart. Contact and presence
// reports expire after 15 min without a refresh (HA resends every 5 min); an
// unknown contact never pauses and unknown presence is "home".
//
// House mode (beta.23, "house.mode.v1"): auto (presence decides), home (presence
// ignored: the week programs always), away (until switched back) and holiday
// (away until a date, warm again in time). Away and holiday are the existing
// away state; "home" is one extra optional field in the same v1 record, which
// beta.21 ignores on a rollback (it then simply runs auto). Frost protection
// (ActiveHeatGuard, any room below 8 degC) is never affected.
// Pure and single-threaded: the caller owns timing, storage and transmission.
class RoomOverrides {
public:
    static constexpr int16_t frostCentiC = 800;          // a paused room still asks for heat below this
    static constexpr int16_t defaultAwayCentiC = 1500;
    static constexpr int16_t minimumAwayCentiC = 500, maximumAwayCentiC = 2500;
    static constexpr uint32_t maxMinutes = 1440;         // longest override, also "until the next switch point"
    static constexpr uint32_t boostMinutes = 60;
    static constexpr uint32_t inputMaxAgeMs = 900000;    // contact and presence reports
    static constexpr uint32_t maxContactDelayS = 1800, defaultContactDelayS = 120;
    static constexpr uint32_t maxAwayS = 366u * 86400u;
    static constexpr uint32_t latestUtc = 4102444800u;   // as RoomPlan's inactive_until
    static constexpr size_t storeBytes = 768, inputBytes = 192, commandBytes = 192; // store: 8 rooms with 32-character ids
    enum class Kind : uint8_t { none, boost, timed, next };

    // Per plan room after refresh(): what it does now (for the status and HA).
    struct View {
        const char* mode = nullptr;  // nullptr: the plan; else window_open, boost, timed, next, away_return, away, presence_away
        const char* window = nullptr; // open (paused), pending (delay running)
        uint32_t until = 0;           // end of the mode (unix s); 0: none or unknown
        uint32_t remainingS = 0;      // override without a trusted clock
        std::optional<int16_t> targetCentiC; // the mode's own target
        Kind kind = Kind::none;       // the room's override, also while a window holds it
        bool waiting = false;         // an override (or away) kept across a restart waits for the clock
    };

    // --- commands (POST /config/heating/comfort) ---------------------------------
    // {"room":id,"override":"boost"|"timed"|"next"|"none","temperature":21.0,"minutes":120}
    // {"away":true,"temperature":15.0,"until":unix|0} / {"away":false}
    // {"house_mode":"auto"|"home"|"away"|"holiday","temperature":15.0,"until":unix}
    //   (until only and always for holiday; temperature: the away temperature)
    // nullptr on success, else a short error name. `persist` tells whether the
    // stored record changed (the caller writes stored() and keeps this state only
    // when that succeeds).
    const char* command(const cJSON* o, const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc, bool& persist) {
        persist = false;
        if (!cJSON_IsObject(o)) return "invalid_request";
        const cJSON* away = cJSON_GetObjectItemCaseSensitive(o, "away");
        const cJSON* temperature = cJSON_GetObjectItemCaseSensitive(o, "temperature");
        if (const cJSON* mode = cJSON_GetObjectItemCaseSensitive(o, "house_mode")) {
            if (!cJSON_IsString(mode) || away || cJSON_GetObjectItemCaseSensitive(o, "room")) return "invalid_request";
            const std::string_view m = mode->valuestring;
            if (m != "auto" && m != "home" && m != "away" && m != "holiday") return "invalid_house_mode";
            int16_t c = awayCentiC_;
            if (temperature && !centi(temperature, minimumAwayCentiC, maximumAwayCentiC, c)) return "invalid_temperature";
            const cJSON* u = cJSON_GetObjectItemCaseSensitive(o, "until");
            uint32_t until = 0;
            if (m == "holiday") {
                if (!cJSON_IsNumber(u) || !whole(u->valuedouble, 1, latestUtc)) return "invalid_until";
                until = uint32_t(u->valuedouble);
                if (!utc) return "no_clock";
                if (until <= *utc || until - *utc > maxAwayS) return "invalid_until";
            } else if (u) return "invalid_until";
            const Away next = m == "away" || m == "holiday" ? Away{true, until} : Away{false, 0};
            const bool home = m == "home";
            persist = next.on != away_.on || next.until != away_.until || home != home_ || c != awayCentiC_;
            if (next.on && (!away_.on || next.until != away_.until)) leadMinute_ = 0; // the warm-up lead at the next step
            away_ = next; home_ = home; awayCentiC_ = c;
            refresh(plan, now, utc);
            return nullptr;
        }
        if (away) {
            if (!cJSON_IsBool(away) || cJSON_GetObjectItemCaseSensitive(o, "room")) return "invalid_request";
            if (!cJSON_IsTrue(away)) {
                if (away_.on) { away_ = Away{false, 0}; persist = true; }
                refresh(plan, now, utc);
                return nullptr;
            }
            int16_t c = awayCentiC_;
            if (temperature && !centi(temperature, minimumAwayCentiC, maximumAwayCentiC, c)) return "invalid_temperature";
            uint32_t until = 0;
            if (const cJSON* u = cJSON_GetObjectItemCaseSensitive(o, "until")) {
                if (!cJSON_IsNumber(u) || !whole(u->valuedouble, 0, latestUtc)) return "invalid_until";
                until = uint32_t(u->valuedouble);
            }
            if (until) {
                if (!utc) return "no_clock";  // a date needs the E32's own clock
                if (until <= *utc || until - *utc > maxAwayS) return "invalid_until";
            }
            persist = !away_.on || away_.until != until || awayCentiC_ != c || home_;
            away_ = Away{true, until}; awayCentiC_ = c; home_ = false;
            leadMinute_ = 0; // the warm-up lead at the next step
            refresh(plan, now, utc);
            return nullptr;
        }
        const cJSON* id = cJSON_GetObjectItemCaseSensitive(o, "room");
        const cJSON* kind = cJSON_GetObjectItemCaseSensitive(o, "override");
        if (!cJSON_IsString(id) || !cJSON_IsString(kind)) return "invalid_request";
        const RoomPlan::Room* room = plan.find(id->valuestring);
        if (!room) return "unknown_room";
        const std::string_view k = kind->valuestring;
        if (k == "none") {
            Slot* s = find(room->id);
            if (s && s->kind != Kind::none) { persist = s->untilUtc != 0; s->clearOverride(); }
            refresh(plan, now, utc);
            return nullptr;
        }
        Slot candidate;
        candidate.kind = k == "boost" ? Kind::boost : k == "timed" ? Kind::timed : k == "next" ? Kind::next : Kind::none;
        if (candidate.kind == Kind::none) return "invalid_override";
        if (room->state != RoomDemand::State::active) return "room_inactive";
        if (candidate.kind == Kind::boost) candidate.centiC = room->maximumCentiC;
        else if (!centi(temperature, room->minimumCentiC, room->maximumCentiC, candidate.centiC)) return "invalid_temperature";
        uint32_t seconds = 0;
        const cJSON* minutes = cJSON_GetObjectItemCaseSensitive(o, "minutes");
        if (candidate.kind == Kind::next) {
            if (minutes) return "invalid_minutes";
            if (!utc) return "no_clock";
            const uint32_t next = nextSwitchUtc(room->schedule, *utc);
            if (!next) return "no_schedule";
            seconds = std::min<uint32_t>(next - *utc, maxMinutes * 60);
        } else if (minutes) {
            if (!cJSON_IsNumber(minutes) || !whole(minutes->valuedouble, 1, maxMinutes)) return "invalid_minutes";
            seconds = uint32_t(minutes->valuedouble) * 60;
        } else if (candidate.kind == Kind::boost) {
            seconds = boostMinutes * 60;
        } else return "invalid_minutes";
        Slot* s = find(room->id);
        if (!s) s = claim(room->id.c_str());
        if (!s) return "invalid_request"; // unreachable: one slot per plan room
        persist = utc || s->untilUtc;
        s->kind = candidate.kind; s->centiC = candidate.centiC;
        s->untilUtc = utc ? *utc + seconds : 0;
        s->untilMs = now + uint64_t(seconds) * 1000;
        refresh(plan, now, utc);
        return nullptr;
    }

    // --- HA inputs (ha/heating_input) ------------------------------------------
    // {"kind":"contact","room":id,"open":bool,"delay_s":0..1800}: the room's window/door
    // contacts (HA aggregates: any open = open); {"kind":"presence","home":bool}.
    // True when the payload was one of these (consumed, also when invalid).
    bool input(std::string_view payload, const RoomPlan& plan, uint64_t now) {
        if (payload.size() > inputBytes || (payload.find("\"contact\"") == std::string_view::npos
                                            && payload.find("\"presence\"") == std::string_view::npos)) return false;
        if (!jsonNestingWithin(payload.data(), payload.size(), 2)) return false;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root.get(), "kind");
        if (!cJSON_IsString(kind)) return false;
        const std::string_view k = kind->valuestring;
        if (k == "presence") {
            const cJSON* home = cJSON_GetObjectItemCaseSensitive(root.get(), "home");
            if (cJSON_IsBool(home)) { presenceKnown_ = true; presenceHome_ = cJSON_IsTrue(home); presenceAt_ = now; }
            return true;
        }
        if (k != "contact") return false;
        const cJSON* id = cJSON_GetObjectItemCaseSensitive(root.get(), "room");
        const cJSON* open = cJSON_GetObjectItemCaseSensitive(root.get(), "open");
        const cJSON* delay = cJSON_GetObjectItemCaseSensitive(root.get(), "delay_s");
        if (!cJSON_IsString(id) || !cJSON_IsBool(open) || !plan.find(id->valuestring)) return true;
        uint32_t delayS = defaultContactDelayS;
        if (delay) {
            if (!cJSON_IsNumber(delay) || !whole(delay->valuedouble, 0, maxContactDelayS)) return true;
            delayS = uint32_t(delay->valuedouble);
        }
        Slot* s = find(id->valuestring);
        if (!s) s = claim(id->valuestring);
        if (!s) return true;
        const bool isOpen = cJSON_IsTrue(open);
        // The delay counts from the first open report after a closed (or unknown) state.
        if (isOpen && !(s->contactFresh(now) && s->open)) s->openSince = now;
        s->contactKnown = true; s->open = isOpen; s->contactAt = now; s->delayS = uint16_t(delayS);
        return true;
    }

    // --- control ---------------------------------------------------------------
    // Every RoomEngine step: expire, then the per-room adjustment for RoomEngine::step().
    // lead(room index, away end, away degC*100, target at the return) -> seconds of
    // warm-up before the away end (returnLeadS() with the learner); asked at most
    // once a minute per room and only within WarmupPlanner::maxLeadS of the end.
    template <class Lead>
    const RoomEngine::Adjust* step(const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc, Lead&& lead) {
        if (utc && *utc / 60 != leadMinute_) {
            leadMinute_ = *utc / 60;
            for (size_t i = 0; i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
                leadS_[i] = 0;
                if (plan.rooms[i].state != RoomDemand::State::active) continue;
                const auto ret = returnTarget(plan.rooms[i]);
                if (away_.on && away_.until > *utc && away_.until - *utc <= WarmupPlanner::maxLeadS && ret > awayCentiC_)
                    leadS_[i] = std::min<uint32_t>(lead(i, away_.until, awayCentiC_, ret), WarmupPlanner::maxLeadS);
            }
        }
        return refresh(plan, now, utc);
    }
    // Expiry and the adjustments with the last warm-up leads (also right after a command).
    const RoomEngine::Adjust* refresh(const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc) {
        for (auto& s : slots_) if (s.id[0] && !plan.find(s.id)) s = Slot{}; // the room left the plan
        if (away_.on && away_.until && utc && *utc >= away_.until) away_ = Away{false, 0};
        // House mode "home": presence never lowers a room.
        const bool presenceAway = !home_ && presenceKnown_ && !presenceHome_ && presenceAt_ <= now && now - presenceAt_ < inputMaxAgeMs;
        for (size_t i = 0; i < RoomPlan::maxRooms; ++i) { adjust_[i] = {}; views_[i] = {}; }
        for (size_t i = 0; i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
            const auto& room = plan.rooms[i];
            auto& a = adjust_[i];
            auto& v = views_[i];
            Slot* s = find(room.id);
            if (s && s->kind != Kind::none) {
                // Kept across a restart: the remaining time, once the clock is trusted again.
                if (!s->untilMs && utc) {
                    if (*utc < s->untilUtc) s->untilMs = now + uint64_t(s->untilUtc - *utc) * 1000;
                    else s->clearOverride();
                }
                if (s->kind != Kind::none && ((s->untilMs && now >= s->untilMs) || (s->untilUtc && utc && *utc >= s->untilUtc)))
                    s->clearOverride();
            }
            const bool overriding = s && s->kind != Kind::none && s->untilMs;
            if (s && s->kind != Kind::none) {
                v.kind = s->kind; v.waiting = !s->untilMs;
                v.until = s->untilUtc;
                if (!s->untilUtc && s->untilMs > now) v.remainingS = uint32_t((s->untilMs - now + 999) / 1000);
            }
            if (s && s->contactFresh(now) && s->open) {
                if (now - s->openSince >= uint64_t(s->delayS) * 1000) {
                    v.window = "open"; v.mode = "window_open"; v.targetCentiC = frostCentiC;
                    a.pause = true; a.setpoint = frostCentiC;
                    continue;
                }
                v.window = "pending";
            }
            if (overriding) {
                v.mode = s->kind == Kind::boost ? "boost" : s->kind == Kind::next ? "next" : "timed";
                v.targetCentiC = s->centiC; a.setpoint = s->centiC;
                continue;
            }
            const bool dated = away_.on && away_.until;
            if (away_.on && (!dated || utc)) {
                if (dated && leadS_[i] && *utc + leadS_[i] >= away_.until) {
                    v.mode = "away_return"; v.until = away_.until;
                    v.targetCentiC = returnTarget(room); a.setpoint = v.targetCentiC;
                } else {
                    v.mode = "away"; v.until = away_.until; v.targetCentiC = awayCentiC_; a.ceiling = awayCentiC_;
                }
            } else if (presenceAway) {
                v.mode = "presence_away"; v.targetCentiC = awayCentiC_; a.ceiling = awayCentiC_;
            }
            if (away_.on && dated && !utc) v.waiting = true;
        }
        return adjust_.data();
    }
    const View& view(size_t room) const { return views_[room < RoomPlan::maxRooms ? room : 0]; }
    const RoomEngine::Adjust* adjust() const { return adjust_.data(); }
    // Away or an open window holds the week program: no optimum start towards its next rise.
    bool holdsProgram(size_t room) const {
        const char* m = view(room).mode;
        return m && (!std::strcmp(m, "away") || !std::strcmp(m, "presence_away") || !std::strcmp(m, "window_open"));
    }

    // The warm-up before the away end from the learner (WarmupPlanner's optimum
    // start towards the return target), else its default lead per emitter.
    static uint32_t returnLeadS(const FlowLearner& l, size_t room, uint32_t untilUtc, int16_t awayCentiC, int16_t targetCentiC,
                                std::optional<int16_t> temperature, uint32_t utc, std::optional<int16_t> outdoor) {
        if (room >= l.rooms() || targetCentiC <= awayCentiC || untilUtc <= utc) return 0;
        WarmupPlanner::Rise rise;
        rise.atUtc = untilUtc; rise.nightUtc = utc; rise.fromCentiC = awayCentiC; rise.toCentiC = targetCentiC;
        WarmupPlanner::Start start;
        WarmupPlanner::lead(l, room, rise, awayCentiC, temperature, utc, outdoor, l.heatModel(room).lossPerHour, start);
        return start.leadS;
    }
    // The target at the away end: the week program then, else the plan fallback
    // (an HA setpoint entity's own program is not known here).
    int16_t returnTarget(const RoomPlan::Room& room) const {
        const auto at = room.schedule.empty() || !away_.until ? std::nullopt : room.schedule.at(RoomSchedule::localAt(away_.until));
        return at.value_or(room.fallbackCentiC);
    }

    // The next switch point of a week program after utc (any point), within 8 days; 0: none.
    // A DST change in between moves the local clock: the result is corrected by it.
    static uint32_t nextSwitchUtc(const RoomSchedule& s, uint32_t utc) {
        if (s.empty()) return 0;
        const auto t = RoomSchedule::localAt(utc);
        for (int d = 0; d <= 7; ++d) {
            const auto& day = s.days[(t.weekday + d) % 7];
            for (uint8_t i = 0; i < day.count; ++i) {
                const int delta = d * 1440 + day.points[i].minute - t.minute;
                if (delta <= 0) continue;
                int64_t at = int64_t(utc) - utc % 60 + int64_t(delta) * 60;
                at -= (RoomSchedule::localSeconds(at) - at) - (RoomSchedule::localSeconds(utc) - int64_t(utc));
                return at > int64_t(utc) && at < int64_t(latestUtc) ? uint32_t(at) : 0;
            }
        }
        return 0;
    }

    // --- status -------------------------------------------------------------------
    // Adds "comfort" to each room of a /status/heating document (only when the room
    // deviates from its plan) and the top-level "away". False: no memory.
    bool addStatus(cJSON* status, const RoomPlan& plan, uint64_t now) const {
        const cJSON* rooms = cJSON_GetObjectItemCaseSensitive(status, "rooms");
        for (cJSON* r = cJSON_IsArray(rooms) ? rooms->child : nullptr; r; r = r->next) {
            const cJSON* id = cJSON_GetObjectItemCaseSensitive(r, "id");
            const auto* room = cJSON_IsString(id) ? plan.find(id->valuestring) : nullptr;
            if (!room) continue;
            const auto& v = views_[size_t(room - plan.rooms.data())];
            if (!v.mode && !v.window && v.kind == Kind::none) continue;
            cJSON* c = cJSON_AddObjectToObject(r, "comfort");
            if (!c || !roomJson(c, v)) return false;
        }
        return awayJson(cJSON_AddObjectToObject(status, "away"), now);
    }
    // GET/POST /config/heating/comfort: {"schema":1,"away":{..},"away_c":..,"rooms":[{"id",..}]}.
    cJSON* json(const RoomPlan& plan, uint64_t now) const {
        cJSON* root = cJSON_CreateObject();
        cJSON* rooms = root && cJSON_AddNumberToObject(root, "schema", 1) ? cJSON_AddArrayToObject(root, "rooms") : nullptr;
        if (!rooms || !awayJson(cJSON_AddObjectToObject(root, "away"), now)) { cJSON_Delete(root); return nullptr; }
        for (size_t i = 0; i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
            cJSON* r = cJSON_CreateObject();
            if (!r || !cJSON_AddItemToArray(rooms, r) || !cJSON_AddStringToObject(r, "id", plan.rooms[i].id.c_str())
                || !roomJson(r, views_[i])) { cJSON_Delete(root); return nullptr; }
        }
        return root;
    }

    // --- storage ------------------------------------------------------------------
    // The NVS record: {"v":1,"away_c":1500,"away_until":0 (present while away),
    // "home":true (present in house mode home), "o":[{"id","k","c","u"}]} with only
    // clocked overrides. Empty: no memory. "home" is optional so beta.21 still
    // reads the record after a rollback (it ignores the field and runs auto).
    std::string stored() const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        cJSON* list = root && cJSON_AddNumberToObject(root.get(), "v", 1) && cJSON_AddNumberToObject(root.get(), "away_c", awayCentiC_)
            ? cJSON_AddArrayToObject(root.get(), "o") : nullptr;
        if (!list || (away_.on && !cJSON_AddNumberToObject(root.get(), "away_until", away_.until))
            || (home_ && !cJSON_AddBoolToObject(root.get(), "home", true))) return {};
        for (const auto& s : slots_) {
            if (!s.id[0] || s.kind == Kind::none || !s.untilUtc) continue;
            cJSON* o = cJSON_CreateObject();
            if (!o || !cJSON_AddItemToArray(list, o) || !cJSON_AddStringToObject(o, "id", s.id)
                || !cJSON_AddStringToObject(o, "k", kindName(s.kind)) || !cJSON_AddNumberToObject(o, "c", s.centiC)
                || !cJSON_AddNumberToObject(o, "u", s.untilUtc)) return {};
        }
        char* text = cJSON_PrintUnformatted(root.get());
        std::string out = text ? text : "";
        cJSON_free(text);
        return out;
    }
    // At boot, before the first step: false (and nothing kept) for a record this
    // firmware cannot read. Overrides wait for a trusted clock (refresh()).
    bool restore(std::string_view text) {
        *this = RoomOverrides{};
        if (text.empty() || text.size() > storeBytes || !jsonNestingWithin(text.data(), text.size(), 3)) return false;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(text.data(), text.size()), cJSON_Delete);
        const cJSON* v = cJSON_GetObjectItemCaseSensitive(root.get(), "v");
        const cJSON* c = cJSON_GetObjectItemCaseSensitive(root.get(), "away_c");
        const cJSON* list = cJSON_GetObjectItemCaseSensitive(root.get(), "o");
        if (!cJSON_IsNumber(v) || v->valuedouble != 1 || !cJSON_IsArray(list)) return false;
        RoomOverrides next;
        if (c && !centi100(c, minimumAwayCentiC, maximumAwayCentiC, next.awayCentiC_)) return false;
        if (const cJSON* u = cJSON_GetObjectItemCaseSensitive(root.get(), "away_until")) {
            if (!cJSON_IsNumber(u) || !whole(u->valuedouble, 0, latestUtc)) return false;
            next.away_ = Away{true, uint32_t(u->valuedouble)};
        }
        if (const cJSON* h = cJSON_GetObjectItemCaseSensitive(root.get(), "home")) {
            if (!cJSON_IsBool(h) || (cJSON_IsTrue(h) && next.away_.on)) return false;
            next.home_ = cJSON_IsTrue(h);
        }
        size_t n = 0;
        for (const cJSON* o = list->child; o; o = o->next) {
            const cJSON* id = cJSON_GetObjectItemCaseSensitive(o, "id");
            const cJSON* k = cJSON_GetObjectItemCaseSensitive(o, "k");
            const cJSON* oc = cJSON_GetObjectItemCaseSensitive(o, "c");
            const cJSON* u = cJSON_GetObjectItemCaseSensitive(o, "u");
            if (n >= RoomPlan::maxRooms || !cJSON_IsString(id) || std::strlen(id->valuestring) >= sizeof(Slot::id) || !*id->valuestring
                || !cJSON_IsString(k) || !cJSON_IsNumber(u) || !whole(u->valuedouble, 1, latestUtc)) return false;
            Slot& s = next.slots_[n++];
            std::strcpy(s.id, id->valuestring);
            s.kind = kindFrom(k->valuestring);
            if (s.kind == Kind::none || !centi100(oc, 500, 3500, s.centiC)) return false;
            s.untilUtc = uint32_t(u->valuedouble);
        }
        *this = next;
        return true;
    }
    int16_t awayCentiC() const { return awayCentiC_; }
    bool awayOn() const { return away_.on; }
    bool homeMode() const { return home_; }
    // auto, home, away or holiday (house.mode.v1).
    const char* houseMode() const { return home_ ? "home" : !away_.on ? "auto" : away_.until ? "holiday" : "away"; }
    uint32_t awayUntil() const { return away_.until; }
    static const char* kindName(Kind k) {
        return k == Kind::boost ? "boost" : k == Kind::next ? "next" : k == Kind::timed ? "timed" : "none";
    }

private:
    struct Slot {
        char id[33]{};
        Kind kind = Kind::none;
        int16_t centiC = 0;
        uint32_t untilUtc = 0;  // 0: set without a trusted clock (not stored)
        uint64_t untilMs = 0;   // uptime end; 0: restored, waiting for the clock
        bool contactKnown = false, open = false;
        uint16_t delayS = 0;
        uint64_t contactAt = 0, openSince = 0;
        void clearOverride() { kind = Kind::none; centiC = 0; untilUtc = 0; untilMs = 0; }
        bool contactFresh(uint64_t now) const { return contactKnown && contactAt <= now && now - contactAt < inputMaxAgeMs; }
    };
    struct Away { bool on = false; uint32_t until = 0; };
    Slot* find(const std::string& id) { return find(id.c_str()); }
    Slot* find(const char* id) {
        for (auto& s : slots_) if (s.id[0] && !std::strcmp(s.id, id)) return &s;
        return nullptr;
    }
    Slot* claim(const char* id) {
        if (!id || !*id || std::strlen(id) >= sizeof(Slot::id)) return nullptr;
        for (auto& s : slots_) if (!s.id[0]) { s = Slot{}; std::strcpy(s.id, id); return &s; }
        return nullptr;
    }
    static Kind kindFrom(std::string_view k) {
        return k == "boost" ? Kind::boost : k == "next" ? Kind::next : k == "timed" ? Kind::timed : Kind::none;
    }
    static bool whole(double v, double lo, double hi) { return std::isfinite(v) && v >= lo && v <= hi && std::floor(v) == v; }
    // degC with at most 0.01 precision, within lo..hi (centi degC).
    static bool centi(const cJSON* t, int16_t lo, int16_t hi, int16_t& out) {
        if (!cJSON_IsNumber(t) || !std::isfinite(t->valuedouble)) return false;
        const double c = t->valuedouble * 100;
        if (!(c >= lo - 0.5 && c <= hi + 0.5)) return false;
        out = static_cast<int16_t>(std::lround(c));
        return out >= lo && out <= hi;
    }
    static bool centi100(const cJSON* t, int16_t lo, int16_t hi, int16_t& out) {
        if (!cJSON_IsNumber(t) || !whole(t->valuedouble, lo, hi)) return false;
        out = static_cast<int16_t>(t->valuedouble);
        return true;
    }
    static bool celsius(cJSON* o, const char* key, std::optional<int16_t> v) {
        return v ? cJSON_AddNumberToObject(o, key, *v / 100.0) != nullptr : cJSON_AddNullToObject(o, key) != nullptr;
    }
    static bool roomJson(cJSON* c, const View& v) {
        if (!cJSON_AddStringToObject(c, "mode", v.mode ? v.mode : "program")) return false;
        if (v.window && !cJSON_AddStringToObject(c, "window", v.window)) return false;
        if (v.targetCentiC && !celsius(c, "target_c", v.targetCentiC)) return false;
        if (v.until && !cJSON_AddNumberToObject(c, "until", v.until)) return false;
        if (v.remainingS && !cJSON_AddNumberToObject(c, "remaining_s", v.remainingS)) return false;
        if (v.kind != Kind::none && !cJSON_AddStringToObject(c, "override", kindName(v.kind))) return false;
        if (v.waiting && !cJSON_AddBoolToObject(c, "waiting_for_clock", true)) return false;
        return true;
    }
    bool awayJson(cJSON* a, uint64_t now) const {
        if (!a) return false;
        const bool presenceFresh = presenceKnown_ && presenceAt_ <= now && now - presenceAt_ < inputMaxAgeMs;
        const char* presence = !presenceFresh ? "unknown" : presenceHome_ ? "home" : "away";
        const bool on = away_.on || (!home_ && presenceFresh && !presenceHome_);
        return cJSON_AddBoolToObject(a, "on", on)
            && cJSON_AddStringToObject(a, "source", away_.on ? "manual" : on ? "presence" : "none")
            && cJSON_AddNumberToObject(a, "target_c", awayCentiC_ / 100.0)
            && (away_.on && away_.until ? cJSON_AddNumberToObject(a, "until", away_.until) : cJSON_AddNullToObject(a, "until"))
            && cJSON_AddStringToObject(a, "presence", presence)
            && cJSON_AddStringToObject(a, "mode", houseMode());
    }

    std::array<Slot, RoomPlan::maxRooms> slots_{};
    std::array<RoomEngine::Adjust, RoomPlan::maxRooms> adjust_{};
    std::array<View, RoomPlan::maxRooms> views_{};
    std::array<uint32_t, RoomPlan::maxRooms> leadS_{};
    uint32_t leadMinute_ = 0;
    Away away_{};
    int16_t awayCentiC_ = defaultAwayCentiC;
    bool home_ = false;  // house mode home: presence ignored (never together with away)
    bool presenceKnown_ = false, presenceHome_ = true;
    uint64_t presenceAt_ = 0;
};
}
