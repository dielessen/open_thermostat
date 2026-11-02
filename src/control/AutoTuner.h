#pragma once
#include "control/ControlTuning.h"
#include "control/FlowDemand.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
namespace heating::control {
// Self-tuning of the ControlTuning knobs (owner, 2 Nov 2026: "it must be a
// self-learning thermostat ... you must make the best settings"). Per local day
// it measures the boiler and the rooms; at the day change it takes yesterday,
// at most one step per knob, within the bounds below (inside ControlTuning's):
//  - burner rest (min_off_s, 300..1200, 150 s): a room that, while the burner
//    rested, fell more than max(0.3, start + 0.1) degC below its target (median
//    over the rests) shortens it, comfort first (and is not tried again this
//    boot); else more than 3 heating starts
//    per heating hour, or 2 h of short cycling with more than 2, lengthen it;
//  - burner run (min_on_s, 300..600, 60 s): at least 3 heating burns shorter than
//    it that ended with no room asking, and half of all burns;
//  - stop margin (heat_stop_c, 0.10..0.50, 0.05): the worst room's median
//    overshoot per cycle (at least 5 cycles since the margin or the gain last
//    moved, so a slow floor counts over days) above 0.3 degC lowers it, at 0.10
//    the gain instead;
//    an overshoot below stop + 0.05 brings a lowered margin back towards 0.20;
//  - start margin (heat_start_c, 0.10..0.50, 0.05): many starts while the rooms
//    stay within 0.15 degC of their target (mean) widen it (so about 0.35 at most);
//    at most 1.5 starts per heating hour bring a widened one back towards 0.20;
//  - room correction gain (flow_per_degree_c, 5..20, 1): towards the learned
//    minutes per degC / 9 (90 min: 10), raised only on at least 5 cycles with
//    an overshoot of at most 0.20 degC (an overshoot lowers the margin first);
//  - unlearned warm-up leads (floor 30..360 / 30, radiators 10..180 / 15 min):
//    towards the learned minutes per degC of those rooms.
// The other knobs stay the owner's. Evidence: at least 6 heating hours and 5
// starts; nothing in the first 24 h after a boot, a plan or a tuning change.
// Only a day the E32 drove the boiler (90 % of it) is applied; otherwise the
// proposals are only shown ("would"). Rooms count only 2 h after their target
// changed (a program step is no cold rest), for the overshoot 2 h after it was
// lowered (the warm-up after a night setback counts: there floors overshoot). Safety limits are no
// knobs. Pure and single-threaded: the caller stores stored() and applies values().
class AutoTuner {
public:
    static constexpr uint64_t graceMs = 24 * 3600000ull, settleMs = 2 * 3600000ull, gapMs = 60000;
    static constexpr uint8_t minHours = 6, minStarts = 5;
    static constexpr size_t logSize = 10, ringSize = 24, roomIdBytes = 33;
    enum class Reason : uint8_t { manyStarts, coldDuringRest, shortBurns, overshoot, overshootGain, settled, hovering, fewStarts, roomResponse, learnedWarmup };
    static const char* name(Reason r) {
        static constexpr const char* names[] = {"many_starts", "cold_during_rest", "short_burns", "overshoot", "overshoot_gain",
                                                "settled", "hovering", "few_starts", "room_response", "learned_warmup"};
        return names[uint8_t(r)];
    }
    // degC figures (centi stored): overshoot, cold rest, settled.
    static bool centiFigure(Reason r) { return r == Reason::coldDuringRest || r == Reason::overshoot || r == Reason::overshootGain || r == Reason::settled; }
    struct Change {
        uint32_t utc = 0;
        uint8_t knob = 0;          // ControlTuning::knobs() index
        uint16_t from = 0, to = 0; // raw (centi degC for the margins)
        Reason reason = Reason::manyStarts;
        int16_t figure = 0;        // starts, burns, centi degC or minutes per degC
        char room[roomIdBytes] = {};
    };
    struct Room { std::optional<int16_t> temperature, setpoint; bool demand = false; };
    struct Step {
        uint64_t now = 0;
        std::optional<uint32_t> utc;           // nothing is counted without a trusted clock
        FlowDemand::Request request;           // the request handed to the boiler (or, in shadow mode, shown)
        std::optional<bool> burnerOn, hotWater;
        bool shortCycling = false, active = false; // BurnerCycleMonitor; the E32 drives the boiler
        const ControlTuning* tuning = nullptr; // in effect
        const Room* rooms = nullptr;
        size_t count = 0;
    };
    // Per plan room at the day change: its emitter and, once learned, its minutes per degC.
    struct Learned { RoomPlan::Emitter emitter = RoomPlan::Emitter::radiator; std::optional<uint16_t> minutesPerC; };

    const ControlTuning& values() const { return values_; }
    // The knobs in effect: the owner's where set (manual), else the automatic ones.
    ControlTuning effective(const ControlTuning& owner, uint16_t manual) const {
        ControlTuning t = owner;
        size_t n; const auto* k = ControlTuning::knobs(n);
        for (size_t i = 0; i < n; ++i) if ((ControlTuning::autoKnobs >> i & 1) && !(manual >> i & 1)) t.*k[i].field = values_.*k[i].field;
        return t;
    }
    // A boot, a plan or a tuning change: 24 h without changes, today counts anew.
    void restart(uint64_t now) { graceUntil_ = now + graceMs; const int32_t d = today_.day; today_ = {}; today_.day = d; open_ = {}; overCount_ = {}; }
    // "Back to start values": the built-in values, an empty log, learning anew.
    void reset(uint64_t now) { values_ = {}; log_ = {}; logCount_ = 0; would_ = {}; wouldCount_ = 0; restCeiling_ = 0; state_ = "waiting"; restart(now); }

    // Every step; true when a local day ended (then call evaluate()).
    bool sample(const Step& s) {
        if (!s.utc || !s.tuning) { last_ = 0; return false; }
        const int32_t day = RoomSchedule::localDay(*s.utc);
        bool closed = false;
        if (today_.day < 0) today_.day = day;
        else if (day > today_.day) { yesterday_ = today_; today_ = {}; today_.day = day; closed = true; }
        const bool gap = !last_ || s.now <= last_ || s.now - last_ > gapMs;
        const uint32_t dt = gap ? 0 : uint32_t((s.now - last_) / 1000);
        last_ = s.now;
        auto& d = today_;
        d.observedS += dt;
        if (s.active) d.activeS += dt;
        if (s.request.heat) { d.hours |= 1u << (RoomSchedule::localAt(*s.utc).minute / 60); if (s.shortCycling) d.shortS += dt; }
        const size_t count = std::min(s.count, RoomPlan::maxRooms);
        bool demand = false;
        for (size_t i = 0; i < count; ++i) {
            const auto& r = s.rooms[i];
            auto& rt = rooms_[i];
            demand = demand || r.demand;
            if (r.setpoint != rt.setpoint) {
                if (r.setpoint && rt.setpoint && *r.setpoint < *rt.setpoint) rt.droppedAt = s.now;
                rt.setpoint = r.setpoint; rt.changedAt = s.now;
            }
            rt.settled = r.temperature && r.setpoint && s.now - rt.changedAt >= settleMs;
            rt.measurable = r.temperature && r.setpoint && (!rt.droppedAt || s.now - *rt.droppedAt >= settleMs);
            if (rt.settled && dt) { d.deviationSum += uint32_t(std::abs(*r.temperature - *r.setpoint)) * dt; d.deviationS += dt; }
        }
        // Burner: heating starts and burns (hot water excluded), continuous reports only;
        // a start counts once the burner was seen off before it.
        if (gap || !s.burnerOn) burn_ = {};
        else if (*s.burnerOn && !burn_.on) {
            burn_ = {true, burn_.offSeen, !s.hotWater.value_or(false), true, s.now};
            if (burn_.measured && burn_.heating && d.starts < UINT16_MAX) ++d.starts;
        } else if (*s.burnerOn) burn_.heating = burn_.heating && !s.hotWater.value_or(false);
        else {
            if (burn_.on && burn_.measured && burn_.heating) {
                const uint64_t ms = s.now - burn_.at;
                ++d.burns; d.burnS += uint32_t(ms / 1000);
                if (ms < s.tuning->minOnS * 1000ull && !demand) ++d.shortBurns;
            }
            burn_ = {false, false, false, true, s.now};
        }
        // Cycles from request start to request start: per room the highest overshoot.
        if (s.request.heat && !heating_) { closeCycle(); open_.used = true; }
        heating_ = s.request.heat;
        for (size_t i = 0; open_.used && i < count; ++i) {
            const auto& r = s.rooms[i];
            if (!rooms_[i].measurable) { open_.invalid |= 1u << i; continue; }
            if (r.demand) open_.demanded |= 1u << i;
            open_.over[i] = std::max<int16_t>(open_.over[i], int16_t(*r.temperature - *r.setpoint));
        }
        // Rests: the burner minimum off holds back a room that asks; its deepest shortfall.
        const bool hold = s.request.reason == FlowDemand::Reason::holdOff;
        int16_t deficit = INT16_MIN; uint8_t worst = 0;
        for (size_t i = 0; hold && i < count; ++i)
            if (s.rooms[i].demand && rooms_[i].settled && *s.rooms[i].setpoint - *s.rooms[i].temperature > deficit) {
                deficit = int16_t(*s.rooms[i].setpoint - *s.rooms[i].temperature); worst = uint8_t(i);
            }
        if (hold && !rest_.on) rest_ = {true, deficit != INT16_MIN && deficit <= int(s.tuning->startCentiC) + 10, deficit, worst};
        else if (hold && deficit > rest_.deficit) { rest_.deficit = deficit; rest_.room = worst; }
        else if (!hold && rest_.on) {
            if (rest_.valid) push(d.rests, d.restRoom, d.restCount, rest_.deficit, rest_.room);
            rest_ = {};
        }
        return closed;
    }

    // Yesterday (after sample() returned true): the proposals, and with an active day
    // the changes to values() for the automatic knobs. learned: per plan room.
    void evaluate(uint64_t now, uint32_t utc, uint16_t manual, const RoomPlan& plan, const Learned* learned, size_t count) {
        wouldCount_ = 0; changed_ = 0;
        if (now < graceUntil_ || yesterday_.day < 0) { state_ = "waiting"; return; }
        const Day& d = yesterday_;
        const int hours = __builtin_popcount(d.hours);
        const bool enough = hours >= minHours && d.starts >= minStarts;
        apply_ = d.observedS && uint64_t(d.activeS) * 10 >= uint64_t(d.observedS) * 9;
        manual_ = manual; utc_ = utc; plan_ = &plan;
        const bool many = enough && (d.starts > 3 * hours || (d.shortS >= 7200 && d.starts > 2 * hours));
        const auto cold = median(d.rests, &d.restRoom, d.restCount, 2);
        std::optional<std::pair<int16_t, uint8_t>> over; // over the cycles since the margin or gain last moved
        for (size_t i = 0; hours >= minHours && i < plan.rooms.size() && i < RoomPlan::maxRooms; ++i) {
            const auto m = median(over_[i], nullptr, overCount_[i], minStarts);
            if (m && (!over || m->first > over->first)) over = std::make_pair(m->first, uint8_t(i));
        }
        state_ = !enough && !over ? "collecting" : apply_ ? "active" : "shadow";
        const auto& v = values_;
        if (enough && cold && cold->first > std::max(30, v.startCentiC + 10)) {
            // A rest that proved too cold is not tried again: only an automatic rest the E32 applied.
            if (apply_ && !(manual_ >> 1 & 1)) restCeiling_ = restCeiling_ ? std::min(restCeiling_, v.minOffS) : v.minOffS;
            propose(1, v.minOffS - 150, 300, 1200, Reason::coldDuringRest, cold->first, cold->second);
        } else if (many && (!restCeiling_ || restCeiling_ >= v.minOffS + 300)) // room below the ceiling: lengthen
            propose(1, v.minOffS + 150, 300, restCeiling_ ? restCeiling_ - 150 : 1200, Reason::manyStarts, int16_t(d.starts));
        if (enough && d.shortBurns >= 3 && d.shortBurns * 2 >= d.burns)
            propose(0, v.minOnS + 60, 300, 600, Reason::shortBurns, int16_t(d.shortBurns));
        if (over && over->first > 30) {
            if (v.stopCentiC > 10) propose(3, v.stopCentiC - 5, 10, 50, Reason::overshoot, over->first, over->second);
            else propose(4, v.flowPerDegreeC - 1, 5, 20, Reason::overshootGain, over->first, over->second);
        } else if (over && over->first < v.stopCentiC + 5 && v.stopCentiC < 20)
            propose(3, v.stopCentiC + 5, 10, 50, Reason::settled, over->first, over->second);
        if (many && d.deviationS && d.deviationSum / d.deviationS <= 15)
            propose(2, v.startCentiC + 5, 10, 50, Reason::hovering, int16_t(d.starts));
        else if (enough && d.starts * 2 <= 3 * hours && v.startCentiC > 20)
            propose(2, v.startCentiC - 5, 10, 50, Reason::fewStarts, int16_t(d.starts));
        // The learned rooms: their mean minutes per degC (one room: named).
        const auto mean = [&](int emitter, int& room) -> std::optional<int> {
            int sum = 0, n = 0;
            for (size_t i = 0; i < count && i < plan.rooms.size(); ++i)
                if (learned[i].minutesPerC && (emitter < 0 || int(learned[i].emitter) == emitter)) { sum += *learned[i].minutesPerC; ++n; room = int(i); }
            if (n != 1) room = -1;
            return n ? std::optional<int>((sum + n / 2) / n) : std::nullopt;
        };
        int room = -1;
        if (const auto m = enough && !(changed_ & 16) ? mean(-1, room) : std::nullopt) {
            const int target = std::clamp((*m + 4) / 9, 5, 20);
            // Raised only on evidence: at least 5 cycles, all but a small overshoot (none: no raise).
            if (target > v.flowPerDegreeC && over && over->first <= 20) propose(4, v.flowPerDegreeC + 1, 5, 20, Reason::roomResponse, int16_t(*m), room);
            else if (target < v.flowPerDegreeC) propose(4, v.flowPerDegreeC - 1, 5, 20, Reason::roomResponse, int16_t(*m), room);
        }
        for (const int e : {int(RoomPlan::Emitter::floor), int(RoomPlan::Emitter::radiator)}) {
            const bool floor = e == int(RoomPlan::Emitter::floor);
            const auto m = mean(e, room);
            if (!m) continue;
            const int step = floor ? 30 : 15, lead = floor ? v.floorLeadMinutes : v.radiatorLeadMinutes;
            const int target = (*m + 2) / 5 * 5;
            propose(floor ? 6 : 7, lead + std::clamp(target - lead, -step, step), floor ? 30 : 10, floor ? 360 : 180,
                    Reason::learnedWarmup, int16_t(*m), room);
        }
    }
    // The last evaluate() changed values() (store them).
    bool changed() const { return changed_ != 0; }
    const char* state(uint64_t now) const { return now < graceUntil_ ? "waiting" : state_; }
    size_t logCount() const { return logCount_; }
    const Change& change(size_t i) const { return log_[i]; } // 0: the newest

    // "tuning" (/status/heating and fw/telemetry/tuning, one compact form):
    // {"state","values":{ControlTuning},"manual":[keys],"yesterday":{"starts","heating_h","burns","burn_s"}|null,
    //  "today":{"starts","heating_h"},"would":[[knob,from,to,reason,figure,room]],"log":[[utc,knob,from,to,reason,figure,room]]}
    // The margins in degC; a figure of a degC reason in degC; room: "" for the house.
    // entries: at most this many of "would" and "log" together (MQTT: mqttEntries, within 1 KB).
    static constexpr size_t mqttEntries = 4; // HA keeps the last ten it saw
    bool addStatus(cJSON* root, uint64_t now, const ControlTuning& effective, uint16_t manual, size_t entries = logSize + 7) const {
        cJSON* o = cJSON_AddObjectToObject(root, "tuning");
        if (!o || !cJSON_AddStringToObject(o, "state", state(now))) return false;
        cJSON* values = cJSON_Parse(effective.json().c_str());
        if (!values || !cJSON_AddItemToObject(o, "values", values)) { cJSON_Delete(values); return false; }
        cJSON* list = cJSON_AddArrayToObject(o, "manual");
        size_t n; const auto* k = ControlTuning::knobs(n);
        for (size_t i = 0; list && i < n; ++i) if (manual >> i & 1) cJSON_AddItemToArray(list, cJSON_CreateString(k[i].key));
        const auto day = [&](const char* key, const Day& d, bool burns) {
            cJSON* y = cJSON_AddObjectToObject(o, key);
            if (!y) return false;
            cJSON_AddNumberToObject(y, "starts", d.starts);
            cJSON_AddNumberToObject(y, "heating_h", __builtin_popcount(d.hours));
            if (burns) { cJSON_AddNumberToObject(y, "burns", d.burns); cJSON_AddNumberToObject(y, "burn_s", d.burns ? d.burnS / d.burns : 0); }
            return true;
        };
        if (!(yesterday_.day >= 0 ? day("yesterday", yesterday_, true) : cJSON_AddNullToObject(o, "yesterday") != nullptr)) return false;
        if (!day("today", today_, false)) return false;
        cJSON* would = cJSON_AddArrayToObject(o, "would");
        const size_t w = std::min(wouldCount_, entries), l = std::min(logCount_, entries - w);
        for (size_t i = 0; would && i < w; ++i) cJSON_AddItemToArray(would, changeJson(would_[i], false));
        cJSON* log = cJSON_AddArrayToObject(o, "log");
        for (size_t i = 0; log && i < l; ++i) cJSON_AddItemToArray(log, changeJson(log_[i], true));
        return would && log && cJSON_GetArraySize(would) == int(w) && cJSON_GetArraySize(log) == int(l);
    }
    // NVS: {"values":{ControlTuning},"log":[[utc,knob,from,to,reason,figure,room]]}.
    std::string stored() const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        cJSON* values = root ? cJSON_Parse(values_.json().c_str()) : nullptr;
        if (!values || !cJSON_AddItemToObject(root.get(), "values", values)) { cJSON_Delete(values); return {}; }
        cJSON* log = cJSON_AddArrayToObject(root.get(), "log");
        for (size_t i = 0; log && i < logCount_; ++i) cJSON_AddItemToArray(log, changeJson(log_[i], true));
        char* text = log ? cJSON_PrintUnformatted(root.get()) : nullptr;
        std::string out = text ? text : "";
        cJSON_free(text);
        return out;
    }
    static constexpr size_t storedMaxBytes = ControlTuning::maxBytes + 30 + logSize * 115;
    // A stored record; anything unreadable keeps the built-in values (and no log).
    bool restore(const char* text) {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(text ? text : ""), cJSON_Delete);
        ControlTuning v;
        const cJSON* log = cJSON_GetObjectItemCaseSensitive(root.get(), "log");
        if (!root || ControlTuning::parse(cJSON_GetObjectItemCaseSensitive(root.get(), "values"), v) || !cJSON_IsArray(log)) return false;
        std::array<Change, logSize> entries{};
        size_t count = 0;
        for (const cJSON* e = log->child; e && count < logSize; e = e->next) if (!parseChange(e, entries[count++])) return false;
        values_ = v; log_ = entries; logCount_ = count;
        return true;
    }

private:
    struct Day {
        int32_t day = -1;
        uint32_t hours = 0, observedS = 0, activeS = 0, shortS = 0, burnS = 0, deviationSum = 0, deviationS = 0;
        uint16_t starts = 0, burns = 0, shortBurns = 0;
        std::array<int16_t, ringSize> rests{};
        std::array<uint8_t, ringSize> restRoom{};
        uint8_t restCount = 0;
    };
    struct RoomState { std::optional<int16_t> setpoint; uint64_t changedAt = 0; std::optional<uint64_t> droppedAt; bool settled = false, measurable = false; };
    struct Burn { bool on = false, measured = false, heating = false, offSeen = false; uint64_t at = 0; };
    struct Cycle { bool used = false; uint8_t invalid = 0, demanded = 0; std::array<int16_t, RoomPlan::maxRooms> over{}; };
    struct Rest { bool on = false, valid = false; int16_t deficit = 0; uint8_t room = 0; };
    // Up to ringSize values a day (the newest replace the oldest).
    static void push(std::array<int16_t, ringSize>& values, std::array<uint8_t, ringSize>& rooms, uint8_t& count, int16_t v, uint8_t room) {
        values[count % ringSize] = v; rooms[count % ringSize] = room;
        if (++count == 2 * ringSize) count = ringSize; // the write position stays count % ringSize
    }
    static void push(std::array<int16_t, ringSize>& values, uint8_t& count, int16_t v) {
        std::array<uint8_t, ringSize> none{}; push(values, none, count, v, 0);
    }
    // The median (upper) and the room it came from, from at least `least` values.
    static std::optional<std::pair<int16_t, uint8_t>> median(const std::array<int16_t, ringSize>& values, const std::array<uint8_t, ringSize>* rooms,
                                                             uint8_t count, size_t least) {
        const size_t n = std::min<size_t>(count, ringSize);
        if (n < least) return std::nullopt;
        std::array<uint8_t, ringSize> order{};
        for (size_t i = 0; i < n; ++i) order[i] = uint8_t(i);
        std::sort(order.begin(), order.begin() + n, [&](uint8_t a, uint8_t b) { return values[a] < values[b]; });
        const uint8_t m = order[n / 2];
        return std::make_pair(values[m], rooms ? (*rooms)[m] : uint8_t(0));
    }
    void closeCycle() {
        if (open_.used)
            for (size_t i = 0; i < RoomPlan::maxRooms; ++i)
                if ((open_.demanded >> i & 1) && !(open_.invalid >> i & 1)) push(over_[i], overCount_[i], open_.over[i]);
        open_ = {};
        for (auto& v : open_.over) v = INT16_MIN;
    }
    void propose(uint8_t knob, int to, int low, int high, Reason reason, int16_t figure, int room = -1) {
        size_t n; const auto* k = ControlTuning::knobs(n);
        const uint16_t from = values_.*k[knob].field;
        const int lo = std::max<int>(low, k[knob].low), hi = std::min<int>(high, k[knob].high);
        if (lo > hi) return; // no room (never std::clamp with hi < lo)
        const int wanted = to;
        to = std::clamp(to, lo, hi);
        if ((wanted > from && to < from) || (wanted < from && to > from)) return; // a bound never turns a step around
        if (to == from || (changed_ >> knob & 1) || (manual_ >> knob & 1)) return;
        Change c;
        c.utc = utc_; c.knob = knob; c.from = from; c.to = uint16_t(to); c.reason = reason; c.figure = figure;
        if (room >= 0 && plan_ && size_t(room) < plan_->rooms.size()) std::snprintf(c.room, sizeof c.room, "%s", plan_->rooms[room].id.c_str());
        changed_ |= uint16_t(1u << knob);
        if (wouldCount_ < would_.size()) would_[wouldCount_++] = c;
        if (!apply_) return;
        values_.*k[knob].field = uint16_t(to);
        // The overshoot starts anew after a margin step or a gentler gain; a raise keeps the
        // evidence (it was raised on it), so a cycle-poor floor cannot be raised day after day.
        if (knob == 3 || (knob == 4 && to < from)) overCount_ = {};
        std::move_backward(log_.begin(), log_.end() - 1, log_.end());
        log_[0] = c; logCount_ = std::min(logCount_ + 1, logSize);
    }
    static void figureJson(cJSON* a, uint16_t v, bool centi) { cJSON_AddItemToArray(a, cJSON_CreateNumber(centi ? v / 100.0 : v)); }
    static cJSON* changeJson(const Change& c, bool withTime) {
        size_t n; const auto* k = ControlTuning::knobs(n);
        cJSON* a = cJSON_CreateArray();
        if (!a) return nullptr;
        if (withTime) cJSON_AddItemToArray(a, cJSON_CreateNumber(c.utc));
        cJSON_AddItemToArray(a, cJSON_CreateString(k[c.knob].key));
        figureJson(a, c.from, k[c.knob].centi); figureJson(a, c.to, k[c.knob].centi);
        cJSON_AddItemToArray(a, cJSON_CreateString(name(c.reason)));
        cJSON_AddItemToArray(a, cJSON_CreateNumber(centiFigure(c.reason) ? c.figure / 100.0 : c.figure));
        cJSON_AddItemToArray(a, cJSON_CreateString(c.room));
        return a;
    }
    static bool parseChange(const cJSON* e, Change& c) {
        const auto at = [&](int i) { return cJSON_GetArrayItem(e, i); };
        if (cJSON_GetArraySize(e) != 7 || !cJSON_IsNumber(at(0)) || !cJSON_IsString(at(1)) || !cJSON_IsString(at(4)) || !cJSON_IsString(at(6))
            || std::strlen(at(6)->valuestring) >= roomIdBytes) return false;
        size_t n; const auto* k = ControlTuning::knobs(n);
        size_t knob = n, reason = 10;
        for (size_t i = 0; i < n; ++i) if (!std::strcmp(k[i].key, at(1)->valuestring)) knob = i;
        for (size_t i = 0; i < 10; ++i) if (!std::strcmp(name(Reason(i)), at(4)->valuestring)) reason = i;
        if (knob == n || reason == 10 || !cJSON_IsNumber(at(2)) || !cJSON_IsNumber(at(3)) || !cJSON_IsNumber(at(5))) return false;
        const double scale = k[knob].centi ? 100 : 1;
        c.utc = uint32_t(at(0)->valuedouble); c.knob = uint8_t(knob); c.reason = Reason(reason);
        c.from = uint16_t(at(2)->valuedouble * scale + 0.5); c.to = uint16_t(at(3)->valuedouble * scale + 0.5);
        c.figure = int16_t(at(5)->valuedouble * (centiFigure(c.reason) ? 100 : 1) + (at(5)->valuedouble < 0 ? -0.5 : 0.5));
        std::snprintf(c.room, sizeof c.room, "%s", at(6)->valuestring);
        return true;
    }
    ControlTuning values_;
    std::array<Change, logSize> log_{};
    size_t logCount_ = 0;
    std::array<Change, 7> would_{};
    size_t wouldCount_ = 0;
    Day today_, yesterday_;
    std::array<RoomState, RoomPlan::maxRooms> rooms_{};
    Burn burn_;
    Cycle open_;
    Rest rest_;
    std::array<std::array<int16_t, ringSize>, RoomPlan::maxRooms> over_{}; // per room the overshoot of the recent cycles
    std::array<uint8_t, RoomPlan::maxRooms> overCount_{};
    uint16_t restCeiling_ = 0; // this boot: the shortest rest that was too cold (0: none)
    uint64_t last_ = 0, graceUntil_ = graceMs;
    const RoomPlan* plan_ = nullptr;
    const char* state_ = "waiting";
    uint32_t utc_ = 0;
    uint16_t manual_ = 0, changed_ = 0;
    bool heating_ = false, apply_ = false;
};
}
