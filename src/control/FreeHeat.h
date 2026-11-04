#pragma once
#include "control/FlowLearner.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include "control/ShadowComparison.h"
#include "control/WarmupPlanner.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
namespace heating::control {
// Free heat (rc.5, P3): sun through the windows, cooking and people warm a room without the
// boiler, so a warm-up in that part of the day needs less time (owner, 4 Nov: "top of the bill
// self learning"). Per plan room and per local daypart (six of 4 h: 0-4, 4-8, 8-12, 12-16, 16-20,
// 20-24) it learns how fast the room rises by itself. Evidence: a window in which no heat reached
// the room, from the emitter's coast time after the last heat on (FlowLearner::Params: floor 2 h,
// radiators 30 min), with a fresh reading every sample, no step over 0.3 degC between samples (a
// source change), a trusted clock and not warmer outside than inside (then the outdoor warms it;
// a reading of either missing: it counts). A window of at least 30 min is judged when it ends
// (heat, a missing reading, a step, a gap, the end of its daypart): a rise of at least 0.2 degC
// joins the daypart's average (EMA, weight 0.3; the first window sets it) as degC/h, at most 3
// (FlowLearner's maxRateCentiCPerHour); a fall or a flat window joins it as a zero. Hot water heats
// no room (heatDelivered). From 5 judged windows a daypart's rate counts: FlowPolicy::optimumStart()
// shortens a planned lead whose warm-up lies in that daypart (the middle of the lead) to lead x
// max(0.5, 1 - free / warm-up rate) (shortenLeadS), never below half; a start whose shortened time
// has passed begins at once. The ArrivalLearner judges the result like any other morning, so a
// wrong estimate is corrected the usual way (its factor of up to 2 gives back at least the whole
// lead). Universal: no house is assumed, and a room that never warms by itself sees zeros and keeps
// its lead. Pure and single-threaded: sample() every 10 s; LearnedState keeps the dayparts that
// matter (frame 'F').
class FreeHeat {
public:
    static constexpr size_t dayparts = 6;
    static constexpr uint8_t maxCount = 99;    // "n" saturates here (2 digits in the telemetry)
    struct Params {
        uint32_t maxGapMs = 60000;              // a longer silence ends a window and restarts the coast wait
        uint32_t floorCoastMs = FlowLearner::Params{}.floorCoastMs, radiatorCoastMs = FlowLearner::Params{}.radiatorCoastMs;
        uint32_t minWindowMs = 1800000;         // a window counts from 30 min
        int16_t minRiseCentiC = 20;             // less is flat: a zero
        int16_t maxStepCentiC = 30;             // a bigger jump between samples is a source change
        float alpha = 0.3f;                     // the weight of a new window in its daypart's average
        uint8_t minCount = 5;                   // judged windows before a daypart's rate counts
        float maxRateKPerH = 3;                 // FlowLearner::Params::maxRateCentiCPerHour
        float minFactor = 0.5f;                 // a lead never shrinks below half
    };
    // Per plan room, every step: the fresh reading (nullopt: none) and whether heat reached the room.
    struct RoomSample { std::optional<int16_t> temperatureCentiC; bool heatDelivered = false; };
    // The frame payload's largest size: 8 rooms with 32-character ids and 3 dayparts each (LearnedState
    // adds 8 B of frame: 353 B in the global record, within the 360 B of the rc.5 plan).
    static constexpr size_t maxStoredBytes = 1 + RoomPlan::maxRooms * (1 + 32 + 1 + 3 * 3);
    static_assert(maxStoredBytes + 8 <= 360, "frame 'F' within its 360 B (RC5-PLAN.md 2.3)");

    FreeHeat() = default;
    explicit FreeHeat(Params p) : p_(p) {}

    // Whether heat reaches the rooms in a step (HeatingController, the replay): the burner on for
    // heating (a hot-water round heats no room), or a heating request (the E32's own while it drives
    // the boiler, else the thermostat's 0x1A: FlowLearner::heatingReference) of at least
    // ShadowComparison::tadoHeatFromC, as FlowLearner counts one. Unknown counts as heat.
    static bool heatDelivered(std::optional<bool> burnerOn, std::optional<bool> hotWater, std::optional<uint8_t> requestC) {
        const bool requested = requestC && *requestC >= ShadowComparison::tadoHeatFromC;
        return requested || (burnerOn.value_or(true) && !hotWater.value_or(false));
    }
    static uint8_t daypart(int localHour) { return uint8_t(std::clamp(localHour, 0, 23) / 4); }
    static int localHour(int64_t utc) { return RoomSchedule::localAt(utc).minute / 60; }

    // An edit keeps each room's evidence by id (also when its emitter changed: the free rise is the
    // room's, not the emitter's); its open window restarts.
    void setPlan(const RoomPlan& plan) {
        std::vector<Room> next(plan.rooms.size());
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            auto old = std::find_if(rooms_.begin(), rooms_.end(), [&](const Room& r) { return r.id == plan.rooms[i].id; });
            if (old != rooms_.end()) next[i] = std::move(*old);
            else next[i].id = plan.rooms[i].id;
            next[i].emitter = plan.rooms[i].emitter;
            next[i].w = {};
        }
        rooms_ = std::move(next);
    }

    void sample(uint64_t now, std::optional<int64_t> utc, std::optional<int16_t> outdoorCentiC, const RoomSample* rooms, size_t count) {
        const bool gap = !haveLast_ || now <= lastMs_ || now - lastMs_ > p_.maxGapMs;
        lastMs_ = now; haveLast_ = true;
        if (utc && *utc / 60 != partMinute_) { partMinute_ = *utc / 60; part_ = daypart(localHour(*utc)); } // once a minute
        for (size_t i = 0; i < count && i < rooms_.size(); ++i) {
            auto& r = rooms_[i];
            const auto& s = rooms[i];
            if (gap || s.heatDelivered || !r.heatAtMs) r.heatAtMs = now; // unknown since when: the coast wait starts now
            const uint32_t coast = r.emitter == RoomPlan::Emitter::floor ? p_.floorCoastMs : p_.radiatorCoastMs;
            const auto t = s.temperatureCentiC;
            if (gap || now - *r.heatAtMs < coast || !utc || !t) { finish(r); continue; }
            if (r.w.open && (r.w.part != part_ || std::abs(*t - r.w.last) > p_.maxStepCentiC)) finish(r);
            if (!r.w.open) { r.w = {}; r.w.open = true; r.w.part = part_; r.w.first = *t; r.w.startMs = now; }
            r.w.last = *t; r.w.lastMs = now;
            r.w.warm = r.w.warm || (outdoorCentiC && *outdoorCentiC >= *t);
        }
    }

    // The expected free rise (degC/h) of the room in the daypart of `localHour`; nullopt below minCount windows.
    std::optional<float> rateKPerH(size_t room, int localHour) const {
        if (room >= rooms_.size()) return std::nullopt;
        const auto& part = rooms_[room].parts[daypart(localHour)];
        return part.n >= p_.minCount ? std::optional<float>(part.rate) : std::nullopt;
    }
    uint8_t count(size_t room, int localHour) const { return room < rooms_.size() ? rooms_[room].parts[daypart(localHour)].n : 0; }
    // A warm-up of `leadS` at `warmupKPerH` in the daypart of `localHour`: lead x max(0.5, 1 - free /
    // warm), rounded up to whole minutes and never below half; unchanged without a counted free rise.
    uint32_t shortenLeadS(size_t room, int localHour, uint32_t leadS, float warmupKPerH) const {
        const auto free = rateKPerH(room, localHour);
        if (!leadS || !free || !(*free > 0) || !(warmupKPerH > 0)) return leadS;
        const double k = std::max(double(p_.minFactor), 1.0 - double(*free) / warmupKPerH);
        uint32_t out = static_cast<uint32_t>(leadS * k);
        out = (out + 59) / 60 * 60;
        return std::min(leadS, std::max(out, static_cast<uint32_t>(leadS * double(p_.minFactor) + 0.999)));
    }
    // FlowPolicy::optimumStart(): a planned start moved later by the free rise of the daypart in which
    // its warm-up lies (the middle of the planned lead), at the rate the plan assumes (shortfall / lead).
    // Once the shortened start has passed it starts at once: WarmupPlanner calls a start "not reachable"
    // as soon as the full lead no longer fits, which is the case between the two starts, so that flag
    // is no reason to keep the full lead; a room far behind gets at least half of its lead from now,
    // which is more than is left. record: the minutes saved become the room's "applied_min" (not while
    // a begun start holds). The seconds saved.
    uint32_t shorten(size_t room, int64_t utc, WarmupPlanner::Start& s, bool record = true) {
        uint32_t saved = 0;
        const int16_t shortfall = static_cast<int16_t>(s.rise.toCentiC - s.startTemperatureCentiC);
        if (room < rooms_.size() && s.reason[0] == 'p' && s.leadS && shortfall > 0) {
            const int hour = localHour(s.rise.atUtc - int64_t(s.leadS / 2));
            const uint32_t lead = shortenLeadS(room, hour, s.leadS, shortfall / 100.0f * 3600.0f / s.leadS);
            saved = s.leadS - lead;
            s.leadS = lead; s.startUtc = s.rise.atUtc - lead;
            s.startNow = utc >= s.startUtc && utc < s.rise.atUtc;
        }
        if (record && room < rooms_.size()) rooms_[room].appliedMin = static_cast<uint16_t>((saved + 30) / 60);
        return saved;
    }
    uint16_t appliedMin(size_t room) const { return room < rooms_.size() ? rooms_[room].appliedMin : 0; }
    size_t rooms() const { return rooms_.size(); }
    const Params& params() const { return p_; }

    // "free_heat":{"rate":[6 x degC/h at 0.1, null below minCount],"n":[6 judged windows],"applied_min":n},
    // or null while no window of the room was judged; at most 88 B. Per room in fw/telemetry/learned/<id>
    // and /status/heating ("learned").
    bool addJson(cJSON* parent, size_t room) const {
        const bool none = room >= rooms_.size()
            || std::all_of(rooms_[room].parts.begin(), rooms_[room].parts.end(), [](const Part& p) { return !p.n; });
        if (none) return cJSON_AddNullToObject(parent, "free_heat") != nullptr;
        const auto& r = rooms_[room];
        cJSON* o = cJSON_AddObjectToObject(parent, "free_heat");
        cJSON* rate = o ? cJSON_AddArrayToObject(o, "rate") : nullptr;
        cJSON* n = rate ? cJSON_AddArrayToObject(o, "n") : nullptr;
        if (!n) return false;
        for (const auto& p : r.parts) {
            cJSON* v = p.n >= p_.minCount ? cJSON_CreateNumber(learnmath::round(double(p.rate) * 10) / 10) : cJSON_CreateNull();
            if (!v || !cJSON_AddItemToArray(rate, v)) { cJSON_Delete(v); return false; }
            cJSON* c = cJSON_CreateNumber(p.n);
            if (!c || !cJSON_AddItemToArray(n, c)) { cJSON_Delete(c); return false; }
        }
        return cJSON_AddNumberToObject(o, "applied_min", r.appliedMin) != nullptr;
    }

    // The payload of LearnedState's frame kind 'F' version 1: a count, then per room with a judged
    // window its id (u8 length, bytes), a mask of the stored dayparts and per daypart (in order) its
    // count (u8) and rate (u16 LE, 0.001 degC/h). At most 3 dayparts a room: first those whose rate
    // shortens a warm-up (counted, the highest first), then the busiest. Empty: nothing judged yet.
    std::string stored() const {
        std::string out(1, '\0');
        uint8_t rooms = 0;
        for (const auto& r : rooms_) {
            const auto value = [&](int d) { const auto& p = r.parts[d]; return p.n >= p_.minCount && p.rate > 0 ? p.rate : 0.0f; };
            uint8_t mask = 0;
            for (int k = 0; k < 3; ++k) {                       // the highest value, then the most windows, then the earliest
                int best = -1;
                for (int d = 0; d < int(dayparts); ++d)
                    if (r.parts[d].n && !(mask >> d & 1)
                        && (best < 0 || value(d) > value(best) || (value(d) == value(best) && r.parts[d].n > r.parts[best].n))) best = d;
                if (best >= 0) mask = uint8_t(mask | 1u << best);
            }
            if (!mask || rooms == RoomPlan::maxRooms) continue;
            const uint8_t size = uint8_t(std::min<size_t>(r.id.size(), 32));
            out += char(size); out.append(r.id, 0, size); out += char(mask);
            for (uint8_t d = 0; d < dayparts; ++d) {
                if (!(mask >> d & 1)) continue;
                const auto milli = static_cast<uint16_t>(std::clamp(learnmath::round(double(r.parts[d].rate) * 1000), 0.0, 65535.0));
                out += char(r.parts[d].n); out += char(milli & 0xFF); out += char(milli >> 8);
            }
            ++rooms;
        }
        if (!rooms) return {};
        out[0] = char(rooms);
        return out;
    }
    // A payload of stored(), into the plan rooms with its ids (the others keep theirs); a room in it gets
    // exactly its stored dayparts. false: not one (nothing applied). With a plan: setPlan(plan) first.
    bool restore(std::string_view payload) {
        return read(payload, p_, [&](std::string_view id, const std::array<Part, dayparts>& parts) {
            for (auto& r : rooms_) if (r.id == id) { r.parts = parts; r.w = {}; }
        });
    }
    bool restore(std::string_view payload, const RoomPlan& plan) {
        if (!valid(payload, p_)) return false;
        setPlan(plan);
        return restore(payload);
    }
    // A payload that restore() would take (the settings backup's check); nothing is applied.
    static bool valid(std::string_view payload, const Params& p) { return read(payload, p, [](std::string_view, const std::array<Part, dayparts>&) {}); }
    static bool valid(std::string_view payload) { return valid(payload, Params()); }

private:
    struct Part { float rate = 0; uint8_t n = 0; };             // degC/h (EMA) and judged windows
    struct Window {
        bool open = false, warm = false;                        // warm: it was warmer outside than inside
        uint8_t part = 0;
        int16_t first = 0, last = 0;
        uint64_t startMs = 0, lastMs = 0;
    };
    struct Room {
        std::string id;
        RoomPlan::Emitter emitter = RoomPlan::Emitter::radiator;
        std::array<Part, dayparts> parts{};
        std::optional<uint64_t> heatAtMs;                       // the last step that delivered heat (or a gap)
        Window w;
        uint16_t appliedMin = 0;
    };
    void finish(Room& r) {
        auto& w = r.w;
        if (!w.open) return;
        w.open = false;
        if (w.warm || w.lastMs - w.startMs < p_.minWindowMs) return;
        const int rise = w.last - w.first;
        const float hours = float(w.lastMs - w.startMs) / 3600000.0f;
        const float rate = rise >= p_.minRiseCentiC ? std::min(rise / 100.0f / hours, p_.maxRateKPerH) : 0.0f;
        auto& part = r.parts[w.part];
        part.rate = part.n ? part.rate + p_.alpha * (rate - part.rate) : rate;
        if (part.n < maxCount) ++part.n;
    }
    // A payload of stored(), walked twice: first all of it is checked, then `apply(id, dayparts)` per
    // room, so nothing is applied unless all of it is valid (small: no copy on the loop stack).
    template <class Apply> static bool read(std::string_view b, const Params& p, Apply&& apply) {
        for (int pass = 0; pass < 2; ++pass) {
            std::array<std::string_view, RoomPlan::maxRooms> seen{};
            size_t at = 0;
            const auto byte = [&](uint8_t& v) { if (at >= b.size()) return false; v = uint8_t(b[at++]); return true; };
            uint8_t rooms = 0;
            if (!byte(rooms) || !rooms || rooms > RoomPlan::maxRooms) return false;
            for (uint8_t k = 0; k < rooms; ++k) {
                uint8_t size = 0, mask = 0;
                if (!byte(size) || !size || size > 32 || b.size() - at < size) return false;
                seen[k] = b.substr(at, size); at += size;
                for (uint8_t o = 0; o < k; ++o) if (seen[o] == seen[k]) return false; // a room twice: not ours
                if (!byte(mask) || !mask || mask >> dayparts) return false;
                std::array<Part, dayparts> parts{};
                uint8_t used = 0;
                for (uint8_t d = 0; d < dayparts; ++d) {
                    if (!(mask >> d & 1)) continue;
                    uint8_t n = 0, lo = 0, hi = 0;
                    if (++used > 3 || !byte(n) || !byte(lo) || !byte(hi)) return false;
                    const float rate = float(lo | uint16_t(hi) << 8) / 1000.0f;
                    if (!n || n > maxCount || rate > p.maxRateKPerH + 0.0005f) return false;
                    parts[d] = {rate, n};
                }
                if (pass) apply(seen[k], parts);
            }
            if (at != b.size()) return false;
        }
        return true;
    }

    Params p_;
    std::vector<Room> rooms_;
    uint64_t lastMs_ = 0;
    bool haveLast_ = false;
    int64_t partMinute_ = -1;
    uint8_t part_ = 0;
};
}
