#pragma once
#include "control/BoundedJson.h"
#include "control/RoomEngine.h"
#include "control/WarmupPlanner.h"
#include <algorithm>
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
// Away is a ceiling: a room whose program is already cooler stays cooler.
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
// (away until a date, warm again in time). Away is the existing away state; "home"
// is one extra optional field in the same v1 record, which beta.21 ignores on a
// rollback (it then simply runs auto). Frost protection (ActiveHeatGuard, any room
// below 8 degC) is never affected.
//
// Holidays (rc.4, "house.holidays.v1", announced as the list away.holidays): up to
// 8 periods {from, until} in unix UTC (the pages and Home Assistant convert the
// owner's local date and time), planned ahead and kept with the holiday
// temperature in their own NVS record ("ot_heating"/"holidays", holidaysStored()).
// Inside a period the house mode is holiday: every room at most the holiday
// temperature, warm again in time for the end (the warm-up of rule 1 below, from
// the holiday temperature); afterwards the house mode is what it was (auto, home or
// away). Periods that overlap or touch are merged; a period that already ended is
// refused; the running one is shortened or ended by sending the list with it
// changed or left out. "Holiday until" (house_mode holiday) sets the end of the
// running holiday, or starts one from now that returns to auto (as before rc.4).
// Choosing auto, home or away ends a running holiday. The holiday temperature is
// the away temperature until the owner sets one (null: the away temperature again).
// A holiday needs the E32's clock: without it the rooms follow their plan
// (waiting_for_clock), as a dated away did. Rollback: the comfort record keeps its
// v1 form; a holiday running when it is written is also kept there as the dated
// away of rc.3 ("away_until", only while the house returns to auto), which this
// firmware ignores once its own holidays record exists, and converts once into a
// period when it does not (a holiday set before the update).
//
// Persons per room (beta.23, "room.presence.v1", announced as away.room_presence):
// HA reports {"kind":"room_presence","room":id,"home":bool} for a room with its own
// persons (home as soon as one of them is home; away after the house's away delay;
// unknown is never sent). In house mode auto such a room goes to the away
// temperature when its persons are away, even while others are home; a room
// without a fresh report follows the house presence. Home ignores both, away and
// holiday lower every room. Reports are not stored and expire like presence
// (15 min); an older firmware does not consume "room_presence" at all.
//
// Away temperature per room ("plan.room_away.v1", the plan's optional
// away_centi_c, RoomPlan.h). Which away temperature a room gets:
//  1. everyone away (house presence), house mode away or holiday: the house away
//     temperature for every room, also for a room with its own value;
//  2. a room whose own persons are all away while the house is not: the room's
//     own away temperature (status "away_by":"room");
//  3. a room without persons of its own follows the house (rule 1 only);
//  4. a room with persons but without its own value: the house value in rule 2.
// House mode home ignores presence (rules 1 and 2). Rule 2 has no known end, so
// no warm-up lead: the room heats again as soon as one of its persons is back.
// On holiday every room gets the holiday temperature (rule 1 with the holiday
// value); the warm-up before its end starts from there.
// Per-room state is kept by room id (R1-04): a room added, removed or moved in the
// plan never takes over another room's override, window or warm-up lead.
// Pure and single-threaded: the caller owns timing, storage and transmission.
class RoomOverrides {
public:
    static constexpr int16_t frostCentiC = 800;          // a paused room still asks for heat below this
    static constexpr int16_t defaultAwayCentiC = 1500;
    static constexpr int16_t minimumAwayCentiC = 500, maximumAwayCentiC = 2500; // also the holiday temperature
    static constexpr uint32_t maxMinutes = 1440;         // longest override, also "until the next switch point"
    static constexpr uint32_t boostMinutes = 60;
    static constexpr uint32_t inputMaxAgeMs = 900000;    // contact and presence reports
    static constexpr uint32_t maxContactDelayS = 1800, defaultContactDelayS = 120;
    static constexpr uint32_t maxAwayS = 366u * 86400u;  // also: a holiday ends within a year
    static constexpr uint32_t latestUtc = 4102444800u;   // as RoomPlan's inactive_until
    // store: 8 rooms with 32-character ids; command: 8 holidays (holidayCommandBytes in the tests).
    static constexpr size_t storeBytes = 768, inputBytes = 192, commandBytes = 512;
    static constexpr size_t maxHolidays = 8;
    static constexpr size_t holidayStoreBytes = 223;     // the holidays record without its NUL (8 periods: 214)
    static constexpr size_t statusHolidays = 2;          // in /status/heating and fw/state/heating: the next ones
    enum class Kind : uint8_t { none, boost, timed, next };

    // A planned holiday: from <= t < until (unix s); from 0: running since before (rc.3's dated away).
    struct Holiday {
        uint32_t from = 0, until = 0;
        bool operator==(const Holiday& o) const { return from == o.from && until == o.until; }
    };
    // The periods, sorted by start and never overlapping or touching (merge()). One more place
    // than kept, so a command can add one before merging (and refuse when nine remain).
    struct Holidays {
        std::array<Holiday, maxHolidays + 1> items{};
        uint8_t count = 0;
        const Holiday* begin() const { return items.data(); }
        const Holiday* end() const { return items.data() + count; }
        bool operator==(const Holidays& o) const {
            if (count != o.count) return false;
            for (size_t i = 0; i < count; ++i) if (!(items[i] == o.items[i])) return false;
            return true;
        }
        bool add(Holiday h) { if (count >= items.size()) return false; items[count++] = h; return true; }
        void erase(size_t i) { if (i >= count) return; for (; i + 1 < count; ++i) items[i] = items[i + 1]; --count; }
        // Sorted by start; periods that overlap or touch become one.
        void merge() {
            for (size_t i = 1; i < count; ++i)
                for (size_t j = i; j > 0 && (items[j].from < items[j - 1].from
                                             || (items[j].from == items[j - 1].from && items[j].until < items[j - 1].until)); --j)
                    std::swap(items[j], items[j - 1]);
            size_t n = 0;
            for (size_t i = 0; i < count; ++i) {
                if (n && items[i].from <= items[n - 1].until) items[n - 1].until = std::max(items[n - 1].until, items[i].until);
                else items[n++] = items[i];
            }
            count = uint8_t(n);
        }
        // Periods that ended by utc leave the list.
        void prune(uint32_t utc) {
            size_t n = 0;
            for (size_t i = 0; i < count; ++i) if (items[i].until > utc) items[n++] = items[i];
            count = uint8_t(n);
        }
        // The period running at utc, or -1.
        int running(uint32_t utc) const {
            for (size_t i = 0; i < count; ++i) if (items[i].from <= utc && utc < items[i].until) return int(i);
            return -1;
        }
    };

    // Per plan room after refresh(): what it does now (for the status and HA).
    struct View {
        const char* mode = nullptr;  // nullptr: the plan; else window_open, boost, timed, next, away_return, away, presence_away
        const char* window = nullptr; // open (paused), pending (delay running)
        const char* persons = nullptr; // home / away: the room's own persons (fresh report), else nullptr
        const char* awayBy = nullptr;  // presence_away: "room" (its own persons, its own value) or "house" (everyone)
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
    // {"holidays":[{"from":unix,"until":unix}],"holiday_temperature":12.0|null} (rc.4): the
    //   whole list of planned holidays; holiday_temperature also alone or with a house mode.
    // nullptr on success, else a short error name. `persist` tells whether the
    // stored record changed (the caller writes stored() and keeps this state only
    // when that succeeds); `holidays` likewise for holidaysStored() (written first).
    const char* command(const cJSON* o, const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc, bool& persist,
                        bool* holidays = nullptr) {
        persist = false;
        if (holidays) *holidays = false;
        if (!cJSON_IsObject(o)) return "invalid_request";
        const cJSON* away = cJSON_GetObjectItemCaseSensitive(o, "away");
        const cJSON* temperature = cJSON_GetObjectItemCaseSensitive(o, "temperature");
        const cJSON* mode = cJSON_GetObjectItemCaseSensitive(o, "house_mode");
        const cJSON* list = cJSON_GetObjectItemCaseSensitive(o, "holidays");
        const cJSON* holidayC = cJSON_GetObjectItemCaseSensitive(o, "holiday_temperature");
        if (!mode && !away && !list && !holidayC) return roomCommand(o, plan, now, utc, persist);
        if (cJSON_GetObjectItemCaseSensitive(o, "room") || (mode && away) || (list && (mode || away))) return "invalid_request";
        // Everything is checked before anything changes.
        std::optional<int16_t> nextHolidayC = holidayCentiC_;
        if (holidayC && !cJSON_IsNull(holidayC)) {
            int16_t c = 0;
            if (!centi(holidayC, minimumAwayCentiC, maximumAwayCentiC, c)) return "invalid_temperature";
            nextHolidayC = c;
        } else if (holidayC) nextHolidayC.reset();  // the away temperature again
        int16_t c = awayCentiC_;
        Away nextAway = away_;
        bool nextHome = home_;
        Holidays next = holidays_;
        if (utc) next.prune(*utc);
        if (list) {
            if (temperature) return "invalid_request";
            if (!utc) return "no_clock";  // "in the past" needs the E32's own clock
            if (const char* error = parseHolidays(list, *utc, next)) return error;
        } else if (mode || away) {
            // The mode and, for a holiday, its end: house_mode, or the older away command.
            std::string_view m;
            uint32_t until = 0;
            const cJSON* u = cJSON_GetObjectItemCaseSensitive(o, "until");
            if (mode) {
                if (!cJSON_IsString(mode)) return "invalid_request";
                m = mode->valuestring;
                if (m != "auto" && m != "home" && m != "away" && m != "holiday") return "invalid_house_mode";
                if (temperature && !centi(temperature, minimumAwayCentiC, maximumAwayCentiC, c)) return "invalid_temperature";
                if (m == "holiday") {
                    if (!cJSON_IsNumber(u) || !whole(u->valuedouble, 1, latestUtc)) return "invalid_until";
                    until = uint32_t(u->valuedouble);
                    if (!utc) return "no_clock";
                    if (until <= *utc || until - *utc > maxAwayS) return "invalid_until";
                } else if (u) return "invalid_until";
            } else {
                if (!cJSON_IsBool(away)) return "invalid_request";
                if (cJSON_IsTrue(away)) {
                    if (temperature && !centi(temperature, minimumAwayCentiC, maximumAwayCentiC, c)) return "invalid_temperature";
                    if (u) {
                        if (!cJSON_IsNumber(u) || !whole(u->valuedouble, 0, latestUtc)) return "invalid_until";
                        until = uint32_t(u->valuedouble);
                    }
                    if (until) {
                        if (!utc) return "no_clock";  // a date needs the E32's own clock
                        if (until <= *utc || until - *utc > maxAwayS) return "invalid_until";
                    }
                    m = until ? "holiday" : "away";
                } else m = "off";  // the older "away off": a holiday ends, away returns to auto, home stays
            }
            const int running = utc ? next.running(*utc) : -1;
            if (m == "holiday") {
                if (running >= 0) {
                    // A new end for the running holiday (shortened or longer); the mode after it stays.
                    next.items[size_t(running)].until = until;
                    next.merge();
                } else {
                    // A holiday from now: back home at its end, so auto afterwards (as before rc.4).
                    next.add(Holiday{*utc, until});
                    next.merge();
                    if (next.count > maxHolidays) return "too_many_holidays";
                    nextAway = Away{}; nextHome = false;
                }
            } else {
                if (running >= 0) next.erase(size_t(running));  // a chosen mode ends the running holiday
                if (m == "off") nextAway = Away{};
                else { nextAway = m == "away" ? Away{true, 0} : Away{}; nextHome = m == "home"; }
            }
        } else if (temperature) return "invalid_request";  // the away temperature goes with a mode
        const std::string comfortBefore = stored(), holidaysBefore = holidaysStored();
        if (!(next == holidays_) || nextHolidayC != holidayCentiC_) leadMinute_ = 0; // the warm-up lead at the next step
        away_ = nextAway; home_ = nextHome; awayCentiC_ = c;
        holidays_ = next; holidayCentiC_ = nextHolidayC;
        refresh(plan, now, utc);
        persist = stored() != comfortBefore;
        if (holidays) *holidays = holidaysStored() != holidaysBefore;
        return nullptr;
    }
    // {"room":id,"override":..}: an override of one room.
    const char* roomCommand(const cJSON* o, const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc, bool& persist) {
        const cJSON* temperature = cJSON_GetObjectItemCaseSensitive(o, "temperature");
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
    // contacts (HA aggregates: any open = open); {"kind":"presence","home":bool};
    // {"kind":"room_presence","room":id,"home":bool}: the room's own persons.
    // True when the payload was one of these (consumed, also when invalid). rejected: set to why an
    // invalid one was refused (a string literal: unknown_room, invalid_value; ha.last_rejected, P22).
    bool input(std::string_view payload, const RoomPlan& plan, uint64_t now, const char** rejected = nullptr) {
        if (payload.size() > inputBytes || (payload.find("\"contact\"") == std::string_view::npos
                                            && payload.find("\"presence\"") == std::string_view::npos
                                            && payload.find("\"room_presence\"") == std::string_view::npos)) return false;
        if (!jsonNestingWithin(payload.data(), payload.size(), 2)) return false;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root.get(), "kind");
        if (!cJSON_IsString(kind)) return false;
        const std::string_view k = kind->valuestring;
        const auto refuse = [&](const char* reason) { if (rejected) *rejected = reason; return true; };
        if (k == "presence") {
            const cJSON* home = cJSON_GetObjectItemCaseSensitive(root.get(), "home");
            if (!cJSON_IsBool(home)) return refuse("invalid_value");
            presenceKnown_ = true; presenceHome_ = cJSON_IsTrue(home); presenceAt_ = now;
            return true;
        }
        if (k == "room_presence") {
            const cJSON* id = cJSON_GetObjectItemCaseSensitive(root.get(), "room");
            const cJSON* home = cJSON_GetObjectItemCaseSensitive(root.get(), "home");
            if (!cJSON_IsString(id) || !cJSON_IsBool(home)) return refuse("invalid_value");
            if (!plan.find(id->valuestring)) return refuse("unknown_room");
            Slot* s = find(id->valuestring);
            if (!s) s = claim(id->valuestring);
            if (s) { s->personsKnown = true; s->personsHome = cJSON_IsTrue(home); s->personsAt = now; }
            return true;
        }
        if (k != "contact") return false;
        const cJSON* id = cJSON_GetObjectItemCaseSensitive(root.get(), "room");
        const cJSON* open = cJSON_GetObjectItemCaseSensitive(root.get(), "open");
        const cJSON* delay = cJSON_GetObjectItemCaseSensitive(root.get(), "delay_s");
        if (!cJSON_IsString(id) || !cJSON_IsBool(open)) return refuse("invalid_value");
        if (!plan.find(id->valuestring)) return refuse("unknown_room");
        uint32_t delayS = defaultContactDelayS;
        if (delay) {
            if (!cJSON_IsNumber(delay) || !whole(delay->valuedouble, 0, maxContactDelayS)) return refuse("invalid_value");
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
    // lead(room index, holiday end, holiday degC*100, target at the return) -> seconds of
    // warm-up before the holiday's end (returnLeadS() with the learner); asked at most
    // once a minute per room and only within WarmupPlanner::maxLeadS of the end. The
    // lead is kept by room id (R1-04), so a plan edit never moves it to another room.
    template <class Lead>
    const RoomEngine::Adjust* step(const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc, Lead&& lead) {
        if (utc && *utc / 60 != leadMinute_) {
            leadMinute_ = *utc / 60;
            forgetLeftRooms(plan);
            holidays_.prune(*utc);
            const int running = holidays_.running(*utc);
            const uint32_t end = running >= 0 ? holidays_.items[size_t(running)].until : 0;
            const int16_t from = holidayCentiC();
            for (auto& s : slots_) s.leadS = 0;
            for (size_t i = 0; end && end - *utc <= WarmupPlanner::maxLeadS && i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
                const auto& room = plan.rooms[i];
                if (room.state != RoomDemand::State::active) continue;
                const auto ret = returnTarget(room, end);
                if (ret <= from) continue;
                const uint32_t seconds = std::min<uint32_t>(lead(i, end, from, ret), WarmupPlanner::maxLeadS);
                Slot* s = seconds ? find(room.id) : nullptr;
                if (seconds && !s) s = claim(room.id.c_str());
                if (s) s->leadS = seconds;
            }
        }
        return refresh(plan, now, utc);
    }
    // The plan changed (HeatingController::setHeatingPlan): the views and adjustments follow its
    // rooms at once; what is kept per room stays with the room's id.
    const RoomEngine::Adjust* planChanged(const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc) {
        return refresh(plan, now, utc);
    }
    // Expiry and the adjustments with the last warm-up leads (also right after a command).
    const RoomEngine::Adjust* refresh(const RoomPlan& plan, uint64_t now, std::optional<uint32_t> utc) {
        forgetLeftRooms(plan);
        if (utc) {
            holidays_.prune(*utc);
            const int running = holidays_.running(*utc);
            holidayEnd_ = running >= 0 ? holidays_.items[size_t(running)].until : 0;
        }
        const bool holiday = holidayEnd_ && utc;  // without the clock a holiday waits (as a dated away did)
        const int16_t holidayC = holidayCentiC();
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
            // The room's own persons (auto mode): a fresh report decides for this room alone.
            const bool personsFresh = s && s->personsFresh(now);
            if (personsFresh) v.persons = s->personsHome ? "home" : "away";
            const bool roomAway = !home_ && (personsFresh ? !s->personsHome : presenceAway);
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
            const uint32_t lead = s ? s->leadS : 0;
            if (holiday) {
                // On holiday: at most the holiday temperature, warm again in time for its end.
                if (lead && *utc + lead >= holidayEnd_) {
                    v.mode = "away_return"; v.until = holidayEnd_;
                    v.targetCentiC = returnTarget(room, holidayEnd_); a.setpoint = v.targetCentiC;
                } else {
                    v.mode = "away"; v.until = holidayEnd_; v.targetCentiC = holidayC; a.ceiling = holidayC;
                }
            } else if (away_.on) {
                v.mode = "away"; v.targetCentiC = awayCentiC_; a.ceiling = awayCentiC_;
            } else if (roomAway) {
                // Everyone away: the house value for every room. Only the room's own persons: its own value.
                const int16_t c = presenceAway ? awayCentiC_ : room.awayCentiC.value_or(awayCentiC_);
                v.mode = "presence_away"; v.awayBy = presenceAway ? "house" : "room";
                v.targetCentiC = c; a.ceiling = c;
            }
            if (!utc && holidays_.count) v.waiting = true;  // a holiday needs the clock
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

    // The warm-up before a holiday's end from the learner (WarmupPlanner's optimum
    // start towards the return target), else its default lead per emitter.
    static uint32_t returnLeadS(const FlowLearner& l, size_t room, uint32_t untilUtc, int16_t awayCentiC, int16_t targetCentiC,
                                std::optional<int16_t> temperature, uint32_t utc, std::optional<int16_t> outdoor) {
        if (room >= l.rooms() || targetCentiC <= awayCentiC || untilUtc <= utc) return 0;
        WarmupPlanner::Rise rise;
        rise.atUtc = untilUtc; rise.nightUtc = utc; rise.fromCentiC = awayCentiC; rise.toCentiC = targetCentiC;
        WarmupPlanner::Start start;
        // rc.4: no morning judges a return, so the default lead is taken as it is (the arrival
        // feedback's cap on an untrusted estimate is for the program's rises; the return must be warm).
        WarmupPlanner::lead(l, room, rise, awayCentiC, temperature, utc, outdoor, l.heatModel(room).lossPerHour, start, false, LeadFactor{1.0f, true});
        return start.leadS;
    }
    // The target at a holiday's end: the week program then (its local time, also across a
    // DST change), else the plan fallback (an HA setpoint entity's own program is not known
    // here); at most the away temperature when the house returns to away.
    int16_t returnTarget(const RoomPlan::Room& room, uint32_t end) const {
        const auto at = room.schedule.empty() || !end ? std::nullopt : room.schedule.at(RoomSchedule::localAt(end));
        const int16_t target = at.value_or(room.fallbackCentiC);
        return away_.on ? std::min(target, awayCentiC_) : target;
    }
    int16_t returnTarget(const RoomPlan::Room& room) const { return returnTarget(room, holidayEnd_); }

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
            if (!v.mode && !v.window && !v.persons && v.kind == Kind::none) continue;
            cJSON* c = cJSON_AddObjectToObject(r, "comfort");
            if (!c || !roomJson(c, v)) return false;
        }
        return awayJson(cJSON_AddObjectToObject(status, "away"), now);
    }
    // GET/POST /config/heating/comfort: {"schema":1,"away":{..},"rooms":[{"id",..}],
    // "holidays":[{"from","until"}] (every planned one),"holiday_temperature":12.5}.
    cJSON* json(const RoomPlan& plan, uint64_t now) const {
        cJSON* root = cJSON_CreateObject();
        cJSON* rooms = root && cJSON_AddNumberToObject(root, "schema", 1) ? cJSON_AddArrayToObject(root, "rooms") : nullptr;
        if (!rooms || !awayJson(cJSON_AddObjectToObject(root, "away"), now)
            || !holidaysJson(cJSON_AddArrayToObject(root, "holidays"), maxHolidays)
            || !cJSON_AddNumberToObject(root, "holiday_temperature", holidayCentiC() / 100.0)) { cJSON_Delete(root); return nullptr; }
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
    // rc.4: "away_until" > 0 is the holiday running at the write, for a rollback only
    // (rc.3's dated away; never with "home", which rc.3 refuses together with it).
    std::string stored() const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        cJSON* list = root && cJSON_AddNumberToObject(root.get(), "v", 1) && cJSON_AddNumberToObject(root.get(), "away_c", awayCentiC_)
            ? cJSON_AddArrayToObject(root.get(), "o") : nullptr;
        const uint32_t rollbackHoliday = !away_.on && !home_ ? holidayEnd_ : 0;
        if (!list || ((away_.on || rollbackHoliday) && !cJSON_AddNumberToObject(root.get(), "away_until", away_.on ? 0 : rollbackHoliday))
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
    // firmware cannot read. Overrides wait for a trusted clock (refresh()). A dated
    // away (rc.3's holiday, or the rollback copy of rc.4's) becomes a running holiday
    // here; restoreHolidays() then replaces it with the holidays record when there is one.
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
            const uint32_t until = uint32_t(u->valuedouble);
            if (until) {  // a holiday running since before, until then (waits for the clock)
                next.holidays_.add(Holiday{0, until});
                next.holidayEnd_ = until;
                next.legacyHoliday_ = true;
            } else next.away_ = Away{true, 0};
        }
        if (const cJSON* h = cJSON_GetObjectItemCaseSensitive(root.get(), "home")) {
            if (!cJSON_IsBool(h) || (cJSON_IsTrue(h) && (next.away_.on || next.legacyHoliday_))) return false;
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
    // The holidays record (rc.4, "ot_heating"/"holidays"): {"v":1,"c":1400 (absent: the
    // away temperature),"p":[[from,until],..]}, at most holidayStoreBytes. After restore():
    // a readable record replaces the dated away of the comfort record (its rollback copy);
    // false: absent or unreadable, the comfort record's holiday (if any) stays.
    bool restoreHolidays(std::string_view text) {
        if (text.empty() || text.size() > holidayStoreBytes || !jsonNestingWithin(text.data(), text.size(), 3)) return false;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(text.data(), text.size()), cJSON_Delete);
        const cJSON* v = cJSON_GetObjectItemCaseSensitive(root.get(), "v");
        const cJSON* c = cJSON_GetObjectItemCaseSensitive(root.get(), "c");
        const cJSON* list = cJSON_GetObjectItemCaseSensitive(root.get(), "p");
        if (!cJSON_IsNumber(v) || v->valuedouble != 1 || !cJSON_IsArray(list) || cJSON_GetArraySize(list) > int(maxHolidays)) return false;
        std::optional<int16_t> centiC;
        int16_t value = 0;
        if (c) { if (!centi100(c, minimumAwayCentiC, maximumAwayCentiC, value)) return false; centiC = value; }
        Holidays next;
        for (const cJSON* p = list->child; p; p = p->next) {
            const cJSON* from = cJSON_GetArrayItem(p, 0);
            const cJSON* until = cJSON_GetArrayItem(p, 1);
            if (!cJSON_IsArray(p) || cJSON_GetArraySize(p) != 2 || !cJSON_IsNumber(from) || !cJSON_IsNumber(until)
                || !whole(from->valuedouble, 0, latestUtc) || !whole(until->valuedouble, 1, latestUtc)
                || from->valuedouble >= until->valuedouble) return false;
            next.add(Holiday{uint32_t(from->valuedouble), uint32_t(until->valuedouble)});
        }
        next.merge();
        holidays_ = next; holidayCentiC_ = centiC;
        holidayEnd_ = 0; legacyHoliday_ = false;  // known again once the clock is
        leadMinute_ = 0;
        return true;
    }
    std::string holidaysStored() const { return holidaysRecord(holidays_, holidayCentiC_); }
    // The record of a merged list (also the settings backup's restore, control/ConfigBackup.h); empty: no memory.
    static std::string holidaysRecord(const Holidays& holidays, std::optional<int16_t> centiC) {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        if (!root || !cJSON_AddNumberToObject(root.get(), "v", 1)
            || (centiC && !cJSON_AddNumberToObject(root.get(), "c", *centiC))) return {};
        cJSON* list = cJSON_AddArrayToObject(root.get(), "p");
        for (const auto& h : holidays) {
            const double pair[2] = {double(h.from), double(h.until)};
            cJSON* p = cJSON_CreateDoubleArray(pair, 2);
            if (!list || !p || !cJSON_AddItemToArray(list, p)) { cJSON_Delete(p); return {}; }
        }
        char* text = cJSON_PrintUnformatted(root.get());
        std::string out = text ? text : "";
        cJSON_free(text);
        return out.size() <= holidayStoreBytes ? out : std::string();
    }
    // A holiday temperature in degC (5-25, at most 0.01 precision) as centi degC; false: not one.
    static bool holidayCelsius(const cJSON* t, int16_t& out) { return centi(t, minimumAwayCentiC, maximumAwayCentiC, out); }
    // A holiday of the comfort record without a holidays record (set before rc.4): the
    // caller writes the holidays record (and then the comfort record) once at boot.
    bool legacyHoliday() const { return legacyHoliday_; }
    void legacyHolidaySaved() { legacyHoliday_ = false; }
    int16_t awayCentiC() const { return awayCentiC_; }
    // The holiday temperature: the owner's own, else the away temperature.
    int16_t holidayCentiC() const { return holidayCentiC_.value_or(awayCentiC_); }
    bool holidayTemperatureSet() const { return holidayCentiC_.has_value(); }
    const Holidays& holidays() const { return holidays_; }
    // The house away as rc.3 saw it: away, or a holiday running (until its end).
    bool awayOn() const { return away_.on || holidayEnd_; }
    bool homeMode() const { return home_; }
    // auto, home, away or holiday (house.mode.v1); holiday while one runs (by the last clock).
    const char* houseMode() const { return holidayEnd_ ? "holiday" : home_ ? "home" : away_.on ? "away" : "auto"; }
    uint32_t awayUntil() const { return holidayEnd_; }
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
        bool personsKnown = false, personsHome = true;  // the room's own persons (volatile, not stored)
        uint64_t personsAt = 0;
        uint32_t leadS = 0;     // the warm-up before the holiday's end (step(), once a minute)
        void clearOverride() { kind = Kind::none; centiC = 0; untilUtc = 0; untilMs = 0; }
        bool contactFresh(uint64_t now) const { return contactKnown && contactAt <= now && now - contactAt < inputMaxAgeMs; }
        bool personsFresh(uint64_t now) const { return personsKnown && personsAt <= now && now - personsAt < inputMaxAgeMs; }
    };
    struct Away { bool on = false; uint32_t until = 0; };  // until: always 0 since rc.4 (a holiday is a period)
    // A room that left the plan takes nothing of its own along (also its warm-up lead).
    void forgetLeftRooms(const RoomPlan& plan) {
        for (auto& s : slots_) if (s.id[0] && !plan.find(s.id)) s = Slot{};
    }
    // POST "holidays": at most maxHolidays periods {"from","until"} (whole unix seconds,
    // from < until); each still to end (else holiday_in_past) and within a year; merged.
    static const char* parseHolidays(const cJSON* list, uint32_t utc, Holidays& out) {
        if (!cJSON_IsArray(list) || cJSON_GetArraySize(list) > int(maxHolidays)) return "invalid_holidays";
        Holidays next;
        for (const cJSON* h = list->child; h; h = h->next) {
            const cJSON* from = cJSON_GetObjectItemCaseSensitive(h, "from");
            const cJSON* until = cJSON_GetObjectItemCaseSensitive(h, "until");
            if (!cJSON_IsObject(h) || !cJSON_IsNumber(from) || !cJSON_IsNumber(until)
                || !whole(from->valuedouble, 0, latestUtc) || !whole(until->valuedouble, 1, latestUtc)
                || from->valuedouble >= until->valuedouble) return "invalid_holidays";
            const uint32_t end = uint32_t(until->valuedouble);
            if (end <= utc) return "holiday_in_past";
            if (end - utc > maxAwayS) return "holiday_too_far";
            next.add(Holiday{uint32_t(from->valuedouble), end});
        }
        next.merge();
        out = next;
        return nullptr;
    }
    bool holidaysJson(cJSON* list, size_t most) const {
        if (!list) return false;
        size_t n = 0;
        for (const auto& h : holidays_) {
            if (n++ >= most) break;
            cJSON* o = cJSON_CreateObject();
            if (!o || !cJSON_AddItemToArray(list, o)) { cJSON_Delete(o); return false; }
            if (!cJSON_AddNumberToObject(o, "from", h.from) || !cJSON_AddNumberToObject(o, "until", h.until)) return false;
        }
        return true;
    }
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
        if (v.persons && !cJSON_AddStringToObject(c, "persons", v.persons)) return false;
        if (v.awayBy && !cJSON_AddStringToObject(c, "away_by", v.awayBy)) return false;
        if (v.targetCentiC && !celsius(c, "target_c", v.targetCentiC)) return false;
        if (v.until && !cJSON_AddNumberToObject(c, "until", v.until)) return false;
        if (v.remainingS && !cJSON_AddNumberToObject(c, "remaining_s", v.remainingS)) return false;
        if (v.kind != Kind::none && !cJSON_AddStringToObject(c, "override", kindName(v.kind))) return false;
        if (v.waiting && !cJSON_AddBoolToObject(c, "waiting_for_clock", true)) return false;
        return true;
    }
    // The house's away state; "holidays" (the next statusHolidays periods, also an empty list)
    // announces house.holidays.v1, "holiday_temperature_c" goes with it.
    bool awayJson(cJSON* a, uint64_t now) const {
        if (!a) return false;
        const bool presenceFresh = presenceKnown_ && presenceAt_ <= now && now - presenceAt_ < inputMaxAgeMs;
        const char* presence = !presenceFresh ? "unknown" : presenceHome_ ? "home" : "away";
        const bool manual = away_.on || holidayEnd_;
        const bool on = manual || (!home_ && presenceFresh && !presenceHome_);
        return cJSON_AddBoolToObject(a, "on", on)
            && cJSON_AddStringToObject(a, "source", manual ? "manual" : on ? "presence" : "none")
            && cJSON_AddNumberToObject(a, "target_c", awayCentiC_ / 100.0)
            && (holidayEnd_ ? cJSON_AddNumberToObject(a, "until", holidayEnd_) : cJSON_AddNullToObject(a, "until"))
            && cJSON_AddStringToObject(a, "presence", presence)
            && cJSON_AddStringToObject(a, "mode", houseMode())
            && cJSON_AddBoolToObject(a, "room_presence", true)   // room.presence.v1
            && cJSON_AddNumberToObject(a, "holiday_temperature_c", holidayCentiC() / 100.0)
            && holidaysJson(cJSON_AddArrayToObject(a, "holidays"), statusHolidays);  // house.holidays.v1
    }

    std::array<Slot, RoomPlan::maxRooms> slots_{};
    std::array<RoomEngine::Adjust, RoomPlan::maxRooms> adjust_{};
    std::array<View, RoomPlan::maxRooms> views_{};
    uint32_t leadMinute_ = 0;
    Away away_{};
    int16_t awayCentiC_ = defaultAwayCentiC;
    Holidays holidays_{};                    // planned (and running) holidays, merged
    std::optional<int16_t> holidayCentiC_;   // the owner's holiday temperature; none: the away temperature
    uint32_t holidayEnd_ = 0;                // the end of the holiday running at the last clock; 0: none
    bool legacyHoliday_ = false;             // restore() took a holiday from the comfort record only
    bool home_ = false;  // house mode home: presence ignored (never together with away)
    bool presenceKnown_ = false, presenceHome_ = true;
    uint64_t presenceAt_ = 0;
};
}
