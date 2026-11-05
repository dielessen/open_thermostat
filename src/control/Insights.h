#pragma once
#include "control/RoomPlan.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <optional>
namespace heating::control {
// Insights (rc.5; owner, 4 Nov 2026: the thermostat says what it knows): yesterday against the
// house's own usual figures, in plain language. Information only: never a Problem, never a
// Repair. Per local day the Scoreboard hands over yesterday's figures (Scoreboard::judge):
//  - gas per degree-day (kWh/DD: the learner's gas estimate over the 18 degC degree-days),
//  - heating starts per heating hour,
//  - heating hours per degree-day,
//  - per plan room the warm-up minutes per degC (the learned model at the flow the room
//    correction asks for one degree, as AutoTuner's Learned::minutesPerC).
// Each has a baseline: a plain mean over its first five days, then an exponential mean (alpha
// 0.2), so the first day never weighs more than the others. At the day change each figure is
// first judged against its baseline, from the 5th day on (the baseline holds four earlier days),
// and only then folded in. A figure more than 30 % AND more than its floor (0.5 kWh/DD, 1
// start/h, 0.5 h/DD, 15 min/degC) away from its baseline makes one item {"kind","pct","room"?}:
// gas_per_dd_up / gas_per_dd_down, starts_up, hours_per_dd_up, warmup_slower (per room; a room
// that got faster is good news the Scoreboard already shows). At most four items: the house's
// first (gas, starts, hours), then the rooms with the largest change. They describe yesterday:
// every day change replaces them, and a day without heating (< 1 heating hour) neither judges
// nor folds (it leaves no items). A figure that is unknown that day (no gas estimate, no outdoor
// temperature, too mild, no learned room model) is skipped alone. The baselines and the items
// live in the Scoreboard's NVS record (Scoreboard::stored(), "b" and "x"). Pure, single-threaded.
class Insights {
public:
    enum class Kind : uint8_t { gasPerDdUp, gasPerDdDown, startsUp, hoursPerDdUp, warmupSlower };
    static constexpr size_t kindCount = 5, maxItems = 4, houseFigures = 3, figures = houseFigures + RoomPlan::maxRooms;
    static const char* name(Kind k) {
        static constexpr const char* names[kindCount] = {"gas_per_dd_up", "gas_per_dd_down", "starts_up", "hours_per_dd_up", "warmup_slower"};
        return names[uint8_t(k)];
    }
    struct Params {
        float alpha = 0.2f;          // the exponential mean's weight of a new day (a plain mean before)
        uint8_t judgeAfterDays = 4;  // days in a baseline before one is judged: from the 5th day
        float deviation = 0.3f;      // more than 30 % ...
        float gasFloor = 0.5f, startsFloor = 1, hoursFloor = 0.5f, warmupFloor = 15; // ... and more than this
    };
    // Yesterday's figures (Scoreboard::judge); nullopt: unknown that day.
    struct Day {
        bool heated = false;                                       // at least one heating hour
        std::optional<float> gasPerDegreeDay, startsPerHour, hoursPerDegreeDay;
        std::array<std::optional<float>, RoomPlan::maxRooms> warmupMinPerC{};
    };
    struct Item { Kind kind = Kind::gasPerDdUp; uint16_t pct = 0; int8_t room = -1; };
    struct Baseline { float value = 0; uint8_t days = 0; };       // days: folded so far (at most maxDays)
    static constexpr uint8_t maxDays = 9;
    // Bounds of a stored baseline (fixed point below): gas per DD, starts per hour, hours per DD, minutes per degC.
    static constexpr float maxValue[houseFigures + 1] = {999.99f, 99.99f, 24, 999};

    Insights() = default;
    explicit Insights(Params p) : p_(p) {}

    // At the day change: judge yesterday against the baselines, then fold it in.
    void dayChange(const Day& y) {
        count_ = 0;
        if (!y.heated) return;
        std::array<Item, figures> found{};
        size_t n = 0;
        const auto judge = [&](size_t f, std::optional<float> v, float floor, std::optional<Kind> up, std::optional<Kind> down, int8_t room) {
            const auto& b = base_[f];
            if (!v || b.days < p_.judgeAfterDays) return;
            const float diff = *v - b.value, limit = std::max(p_.deviation * b.value, floor);
            if (std::fabs(diff) <= limit) return;
            const auto kind = diff > 0 ? up : down;
            if (!kind) return;
            const float pct = b.value > 0 ? std::fabs(diff) / b.value * 100 : 999;
            // Rounded in double: the e32v2 link review approves libm's s_floor, not the float sf_floor.
            found[n++] = {*kind, uint16_t(std::min(999.0, std::floor(double(pct) + 0.5))), room};
        };
        judge(0, y.gasPerDegreeDay, p_.gasFloor, Kind::gasPerDdUp, Kind::gasPerDdDown, -1);
        judge(1, y.startsPerHour, p_.startsFloor, Kind::startsUp, std::nullopt, -1);
        judge(2, y.hoursPerDegreeDay, p_.hoursFloor, Kind::hoursPerDdUp, std::nullopt, -1);
        const size_t house = n;
        for (size_t r = 0; r < RoomPlan::maxRooms; ++r)
            judge(houseFigures + r, y.warmupMinPerC[r], p_.warmupFloor, Kind::warmupSlower, std::nullopt, int8_t(r));
        for (size_t i = house + 1; i < n; ++i) // the rooms by their change, largest first (stable: plan order on a tie)
            for (size_t j = i; j > house && found[j - 1].pct < found[j].pct; --j) std::swap(found[j - 1], found[j]);
        count_ = std::min(n, maxItems);
        std::copy(found.begin(), found.begin() + count_, items_.begin());
        fold(0, y.gasPerDegreeDay); fold(1, y.startsPerHour); fold(2, y.hoursPerDegreeDay);
        for (size_t r = 0; r < RoomPlan::maxRooms; ++r) fold(houseFigures + r, y.warmupMinPerC[r]);
    }
    size_t count() const { return count_; }
    const Item& item(size_t i) const { return items_[i]; }
    const Baseline& baseline(size_t figure) const { return base_[figure]; }
    // The gas per degree-day baseline (kWh/DD, the learner's estimate) once it holds `days` days.
    std::optional<float> gasPerDegreeDay(uint8_t days = 1) const {
        return base_[0].days >= std::max<uint8_t>(days, 1) ? std::optional<float>(base_[0].value) : std::nullopt;
    }
    // A plan edit: the rooms' baselines and items follow their rooms (new index -> old index, -1: a new room).
    void remap(const std::array<int8_t, RoomPlan::maxRooms>& from) {
        std::array<Baseline, RoomPlan::maxRooms> rooms{};
        for (size_t i = 0; i < RoomPlan::maxRooms; ++i) if (from[i] >= 0) rooms[i] = base_[houseFigures + size_t(from[i])];
        std::copy(rooms.begin(), rooms.end(), base_.begin() + houseFigures);
        size_t kept = 0;
        for (size_t k = 0; k < count_; ++k) {
            Item it = items_[k];
            if (it.room >= 0) {
                const auto at = std::find(from.begin(), from.end(), it.room);
                if (at == from.end()) continue; // its room left the plan
                it.room = int8_t(at - from.begin());
            }
            items_[kept++] = it;
        }
        count_ = kept;
    }

    // "insights": [{"kind","pct"[,"room"]}] (the room's plan id). false: no memory.
    bool addJson(cJSON* parent, const RoomPlan& plan) const {
        cJSON* list = cJSON_AddArrayToObject(parent, "insights");
        if (!list) return false;
        for (size_t k = 0; k < count_; ++k) {
            const Item& it = items_[k];
            cJSON* o = cJSON_CreateObject();
            if (!o || !cJSON_AddItemToArray(list, o)) { cJSON_Delete(o); return false; }
            if (!cJSON_AddStringToObject(o, "kind", name(it.kind)) || !cJSON_AddNumberToObject(o, "pct", it.pct)) return false;
            if (it.room >= 0 && size_t(it.room) < plan.rooms.size() && !cJSON_AddStringToObject(o, "room", plan.rooms[size_t(it.room)].id.c_str())) return false;
        }
        return true;
    }

    // In the Scoreboard record, two arrays of packed whole numbers ("b" at most 65 B, "x" 30 B with their keys):
    //  "b": the baselines [gas, starts, hours, room 0, room 1, ..] (rooms after the last known one left
    //       out), each round(value x scale) x 10 + days (at most 9; the scale: 100 for the house's
    //       three, 1 for minutes per degC), 0 = none: 2354 is 2.35 kWh/DD over 4 days;
    //  "x": the items, each pct x 100 + kind x 10 + room + 1 (0: the house): 3500 is gas_per_dd_up 35 %.
    // withItems false (or none): "x" is left out. false: no memory.
    bool addStored(cJSON* root, bool withItems) const {
        size_t last = 0;
        for (size_t f = 0; f < figures; ++f) if (base_[f].days) last = f + 1;
        if (last) {
            cJSON* b = cJSON_AddArrayToObject(root, "b");
            if (!b) return false;
            for (size_t f = 0; f < std::max(last, houseFigures); ++f)
                if (!cJSON_AddItemToArray(b, cJSON_CreateNumber(pack(f)))) return false;
        }
        if (!withItems || !count_) return true;
        cJSON* x = cJSON_AddArrayToObject(root, "x");
        if (!x) return false;
        for (size_t k = 0; k < count_; ++k)
            if (!cJSON_AddItemToArray(x, cJSON_CreateNumber(double(items_[k].pct) * 100 + uint8_t(items_[k].kind) * 10 + (items_[k].room + 1)))) return false;
        return true;
    }
    // A stored record's "b" and "x" (a record of rc.4 has neither: everything starts empty). Anything
    // unreadable leaves that part empty, never half loaded.
    void restoreStored(const cJSON* root) {
        base_ = {}; count_ = 0;
        const cJSON* b = cJSON_GetObjectItemCaseSensitive(root, "b");
        std::array<Baseline, figures> read{};
        size_t f = 0;
        bool ok = cJSON_IsArray(b) && cJSON_GetArraySize(b) <= int(figures);
        for (const cJSON* e = ok ? b->child : nullptr; e && ok; e = e->next, ++f) ok = unpack(f, e, read[f]);
        if (ok) base_ = read;
        const cJSON* x = cJSON_GetObjectItemCaseSensitive(root, "x");
        std::array<Item, maxItems> items{};
        size_t n = 0;
        ok = cJSON_IsArray(x) && cJSON_GetArraySize(x) <= int(maxItems);
        for (const cJSON* e = ok ? x->child : nullptr; e && ok; e = e->next) {
            const double v = cJSON_IsNumber(e) ? e->valuedouble : -1;
            ok = v >= 0 && v <= 99999 && v == std::floor(v);
            if (!ok) break;
            const auto i = uint32_t(v);
            Item it{Kind(i / 10 % 10), uint16_t(i / 100), int8_t(int(i % 10) - 1)};
            ok = i / 10 % 10 < kindCount && it.room < int(RoomPlan::maxRooms) && (it.room >= 0) == (it.kind == Kind::warmupSlower);
            items[n++] = it;
        }
        if (ok) { items_ = items; count_ = n; }
    }

private:
    static float scale(size_t f) { return f < houseFigures ? 100.0f : 1.0f; }
    static float bound(size_t f) { return maxValue[std::min(f, houseFigures)]; }
    double pack(size_t f) const {
        const auto& b = base_[f];
        return b.days ? std::floor(double(std::clamp(b.value, 0.0f, bound(f))) * scale(f) + 0.5) * 10 + b.days : 0;
    }
    static bool unpack(size_t f, const cJSON* e, Baseline& out) {
        const double v = cJSON_IsNumber(e) ? e->valuedouble : -1;
        if (!(v >= 0 && v <= (double(bound(f)) * scale(f) + 0.5) * 10 + maxDays) || v != std::floor(v)) return false;
        const auto i = uint64_t(v);
        out.days = uint8_t(i % 10);
        out.value = out.days ? float(double(i / 10) / scale(f)) : 0;
        return true;
    }
    void fold(size_t f, std::optional<float> v) {
        if (!v || !std::isfinite(*v) || *v < 0) return;
        auto& b = base_[f];
        const float value = std::min(*v, bound(f));
        b.days = uint8_t(std::min<int>(b.days + 1, maxDays));
        // A plain mean over the first 1 / alpha days, then the exponential mean (days beyond 9 count as 9).
        b.value += std::max(p_.alpha, 1.0f / b.days) * (value - b.value);
    }
    Params p_;
    std::array<Baseline, figures> base_{};
    std::array<Item, maxItems> items_{};
    size_t count_ = 0;
};
}
