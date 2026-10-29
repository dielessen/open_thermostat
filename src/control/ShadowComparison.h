#pragma once
#include "control/FlowDemand.h"
#include "control/RoomSchedule.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <optional>
namespace heating::control {
// Shadow mode: the E32 boiler request next to the tado's real one (0x1A from
// 0x17), summed per local day (device TZ) for the owner's exit check:
// heat at the same moments, flow in the same range, not more starts.
// Pure and single-threaded: call sample() every 10 s; fixed size, no heap.
class ShadowComparison {
public:
    static constexpr uint32_t maxCreditMs = 30000;  // a longer gap counts as 30 s: no invented time
    static constexpr uint8_t tadoHeatFromC = 20;    // 0x1A flow below this (0 = off) is no heat
    static constexpr uint64_t pairWindowMs = 1800000; // starts further apart than 30 min do not pair
    static constexpr uint32_t closeStartS = 300;    // "same moment": within 5 min
    static constexpr size_t history = 7;            // completed days kept
    static constexpr int32_t unknownDay = -1;

    struct Side {
        uint32_t heatS = 0, starts = 0, flowSum = 0; // flowSum: degC x s while heating
        uint8_t flowMin = 255, flowMax = 0;
    };
    struct Day {
        int32_t day = unknownDay;    // local days since 1970-01-01; unknownDay until the clock is known
        uint32_t s = 0, tadoUnknownS = 0;
        Side e32, tado;
        uint32_t bothS = 0, neitherS = 0, e32OnlyS = 0, tadoOnlyS = 0, flowDiffSum = 0; // tado known
        uint32_t paired = 0, close = 0, offsetMaxS = 0; // each pair: one tado start, one E32 start
        int32_t offsetSumS = 0;                         // > 0: the E32 starts later than the tado
    };

    // tadoFlowC: 0x1A requested flow, nullopt while unknown or stale. unixNow:
    // nullopt while the clock is unknown; such time counts into the current day.
    void sample(uint64_t nowMs, std::optional<uint32_t> unixNow, const FlowDemand::Request& e32,
                std::optional<uint8_t> tadoFlowC) {
        if (unixNow) {
            const int32_t day = localDay(*unixNow);
            if (today_.day == unknownDay) today_.day = day; // boot time joins the first known day
            else if (day > today_.day) roll(day);           // an earlier day (clock step back) stays today
        }
        // Whole seconds; the millisecond rest carries over so a 9.99 s cadence is not lost.
        carryMs_ += static_cast<uint32_t>(haveLast_ && nowMs > lastMs_ ? std::min<uint64_t>(nowMs - lastMs_, maxCreditMs) : 0);
        const uint32_t dt = carryMs_ / 1000;
        carryMs_ %= 1000; lastMs_ = nowMs; haveLast_ = true;
        today_.s += dt;
        const bool eHeat = e32.heat;
        add(today_.e32, eHeat, e32.flowC, dt);
        if (eHeat && e32Was_ && !*e32Was_) start(nowMs, pendingE32_, pendingTado_, true);
        e32Was_ = eHeat;
        if (!tadoFlowC) { today_.tadoUnknownS += dt; return; } // last known tado state is kept
        const bool tHeat = *tadoFlowC >= tadoHeatFromC;
        add(today_.tado, tHeat, *tadoFlowC, dt);
        if (tHeat && tadoWas_ && !*tadoWas_) start(nowMs, pendingTado_, pendingE32_, false);
        tadoWas_ = tHeat;
        (eHeat && tHeat ? today_.bothS : eHeat ? today_.e32OnlyS : tHeat ? today_.tadoOnlyS : today_.neitherS) += dt;
        if (eHeat && tHeat) today_.flowDiffSum += dt * static_cast<uint32_t>(std::abs(int(e32.flowC) - int(*tadoFlowC)));
    }

    const Day& today() const { return today_; }
    size_t completedDays() const { return count_; }
    const Day& completed(size_t i) const { return days_[(head_ + history - 1 - i) % history]; } // 0: yesterday

    // {"today":{..},"days":[yesterday, ..]} in seconds and degC.
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON* days = nullptr;
        if (!dayJson(root, "today", today_) || !(days = cJSON_AddArrayToObject(root, "days"))) { cJSON_Delete(root); return nullptr; }
        for (size_t i = 0; i < count_; ++i)
            if (!dayJson(days, nullptr, completed(i))) { cJSON_Delete(root); return nullptr; }
        return root;
    }

    // The device's local day (TZ from the network settings, any DST rule).
    static int32_t localDay(uint32_t utc) { return RoomSchedule::localDay(utc); }
    static int32_t daysFromCivil(int y, unsigned m, unsigned d) { // H. Hinnant's algorithm
        y -= m <= 2;
        const int era = (y >= 0 ? y : y - 399) / 400;
        const unsigned yoe = static_cast<unsigned>(y - era * 400);
        const unsigned doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
        return era * 146097 + static_cast<int32_t>(yoe * 365 + yoe / 4 - yoe / 100 + doy) - 719468;
    }

private:
    static void civil(int32_t z, int& y, unsigned& m, unsigned& d) {
        z += 719468;
        const int32_t era = (z >= 0 ? z : z - 146096) / 146097;
        const unsigned doe = static_cast<unsigned>(z - era * 146097);
        const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        const unsigned mp = (5 * doy + 2) / 153;
        d = doy - (153 * mp + 2) / 5 + 1;
        m = mp < 10 ? mp + 3 : mp - 9;
        y = static_cast<int>(yoe) + era * 400 + (m <= 2);
    }
    static void add(Side& side, bool heat, uint8_t flowC, uint32_t dt) {
        if (!heat) return;
        side.flowMin = std::min(side.flowMin, flowC); side.flowMax = std::max(side.flowMax, flowC);
        side.heatS += dt; side.flowSum += dt * flowC;
    }
    // A start pairs with the other side's latest unpaired start within 30 min;
    // otherwise it waits for the other side's next start.
    void start(uint64_t nowMs, std::optional<uint64_t>& mine, std::optional<uint64_t>& other, bool isE32) {
        ++(isE32 ? today_.e32 : today_.tado).starts;
        if (other && nowMs - *other <= pairWindowMs) {
            const uint32_t gap = static_cast<uint32_t>((nowMs - *other) / 1000);
            ++today_.paired;
            if (gap <= closeStartS) ++today_.close;
            today_.offsetMaxS = std::max(today_.offsetMaxS, gap);
            today_.offsetSumS += isE32 ? int32_t(gap) : -int32_t(gap);
            other.reset(); mine.reset();
        } else {
            mine = nowMs;
        }
    }
    void roll(int32_t day) {
        days_[head_] = today_; head_ = (head_ + 1) % history;
        if (count_ < history) ++count_;
        today_ = {}; today_.day = day;
    }
    static cJSON* number(cJSON* o, const char* key, double v) { return cJSON_AddNumberToObject(o, key, v); }
    static double mean(uint32_t sum, uint32_t s) { return static_cast<int>(10.0 * sum / s + 0.5) / 10.0; }
    static bool sideJson(cJSON* parent, const char* key, const Side& side) {
        cJSON* o = cJSON_AddObjectToObject(parent, key);
        if (!o || !number(o, "heat_s", side.heatS) || !number(o, "starts", side.starts)) return false;
        if (!side.heatS) return cJSON_AddNullToObject(o, "flow_min_c") && cJSON_AddNullToObject(o, "flow_max_c") && cJSON_AddNullToObject(o, "flow_mean_c");
        return number(o, "flow_min_c", side.flowMin) && number(o, "flow_max_c", side.flowMax) && number(o, "flow_mean_c", mean(side.flowSum, side.heatS));
    }
    static bool dayJson(cJSON* parent, const char* key, const Day& d) {
        cJSON* o = cJSON_CreateObject();
        if (!o || !(key ? cJSON_AddItemToObject(parent, key, o) : cJSON_AddItemToArray(parent, o))) { cJSON_Delete(o); return false; }
        if (d.day == unknownDay) { if (!cJSON_AddNullToObject(o, "day")) return false; }
        else {
            int y; unsigned m, dd; civil(d.day, y, m, dd);
            char text[12]; std::snprintf(text, sizeof text, "%04d-%02u-%02u", y, m, dd);
            if (!cJSON_AddStringToObject(o, "day", text)) return false;
        }
        const bool ok = number(o, "s", d.s) && number(o, "tado_unknown_s", d.tadoUnknownS)
            && sideJson(o, "e32", d.e32) && sideJson(o, "tado", d.tado)
            && number(o, "both_s", d.bothS) && number(o, "agree_s", d.bothS + d.neitherS)
            && number(o, "e32_only_s", d.e32OnlyS) && number(o, "tado_only_s", d.tadoOnlyS)
            && (d.bothS ? number(o, "flow_diff_mean_c", mean(d.flowDiffSum, d.bothS)) : cJSON_AddNullToObject(o, "flow_diff_mean_c"))
            && number(o, "starts_paired", d.paired) && number(o, "starts_within_5min", d.close);
        if (!ok) return false;
        if (!d.paired) return cJSON_AddNullToObject(o, "start_offset_mean_s") && cJSON_AddNullToObject(o, "start_offset_max_s");
        return number(o, "start_offset_mean_s", d.offsetSumS / int32_t(d.paired)) && number(o, "start_offset_max_s", d.offsetMaxS);
    }
    Day today_{};
    std::array<Day, history> days_{};
    size_t head_ = 0, count_ = 0;
    uint64_t lastMs_ = 0;
    uint32_t carryMs_ = 0;
    bool haveLast_ = false;
    std::optional<bool> e32Was_, tadoWas_;           // nullopt: first sample sets the state, no start
    std::optional<uint64_t> pendingE32_, pendingTado_; // unpaired start times (ms)
};
}
