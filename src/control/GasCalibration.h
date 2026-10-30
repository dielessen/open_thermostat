#pragma once
#include <algorithm>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <optional>
namespace heating::control {
// Gas input per burner modulation from a real gas meter (beta.19 item 7; owner,
// 29 Oct: "dat kunnen we zien aan het gasverbruik en de verbruikte kilowatts").
// Without a meter the estimate is modulation x the nominal input (boiler_kw from
// HA, else 22 kW): rough, and the reports say so. With a meter (HA sends m3; a
// kWh meter is converted with the calorific value, so any meter works) each
// interval of at least 55 min without hot water, gaps or unknown modulation
// compares the measured gas with the estimate. The meter total may arrive often
// (DSMR 5: every few minutes, HA repeats it every 5 min) or once an hour (DSMR 4):
// an interval runs on over repeated or small readings until it is long enough,
// and ends only on a reading whose total changed (a repeat says nothing new).
// factor() = measured / estimated over the accepted intervals (kWh-weighted,
// halved past 200 kWh so it follows the boiler), 1 until three intervals.
// Efficiency stays the model's (FlowLearner::efficiency): without a heat meter
// the gas meter cannot separate it from the house's heat capacity. Pure,
// single-threaded; burner() every 10 s, meter() per HA reading.
class GasCalibration {
public:
    struct Params {
        uint32_t minIntervalMs = 3300000, maxIntervalMs = 21600000; // 55 min .. 6 h
        double minEstimatedKwh = 1;
        double minRatio = 0.3, maxRatio = 3;
        double memoryKwh = 200;
        uint8_t minIntervals = 3;
    };
    GasCalibration() = default;
    explicit GasCalibration(Params p) : p_(p) {}

    // One burner step of dtMs (0 after a gap). modulationPct nullopt: unknown.
    void burner(uint32_t dtMs, std::optional<uint8_t> modulationPct, std::optional<bool> hotWater, float nominalKw) {
        if (!dtMs || !modulationPct || !hotWater) { invalidate("gap_or_unknown_modulation"); return; }
        const double kwh = *modulationPct / 100.0 * nominalKw * dtMs / 3600000.0;
        if (*hotWater) { hotWaterKwh_ += kwh; invalidate("hot_water"); return; }
        heatingKwh_ += kwh;
        if (valid_) estimatedKwh_ += kwh;
    }
    // The meter total in m3 at uptime atMs; kwhPerM3: the calorific value in use.
    void meter(double totalM3, uint64_t atMs, float kwhPerM3) {
        lastAt_ = atMs; haveLast_ = true;
        if (!open_ || totalM3 < baseM3_ || atMs <= baseAt_) { if (open_) last_ = "meter_reset"; restart(totalM3, atMs); return; }
        lastM3_ = totalM3;
        if (totalM3 == baseM3_ && atMs - baseAt_ <= p_.maxIntervalMs) return; // a repeat: nothing new
        const uint64_t span = atMs - baseAt_;
        if (!valid_ || span > p_.maxIntervalMs) { rejected_ = sat(rejected_); if (span > p_.maxIntervalMs) last_ = "interval_too_long"; restart(totalM3, atMs); return; }
        if (span < p_.minIntervalMs) return; // runs on until long enough
        const double measured = (totalM3 - baseM3_) * kwhPerM3, ratio = measured / std::max(estimatedKwh_, 1e-9);
        if (estimatedKwh_ < p_.minEstimatedKwh) last_ = "too_little_heat";
        else if (ratio < p_.minRatio || ratio > p_.maxRatio) { rejected_ = sat(rejected_); last_ = "ratio_out_of_range"; }
        else {
            if (predicted_ > p_.memoryKwh) { measuredSum_ *= 0.5; predicted_ *= 0.5; n_ *= 0.5; r_ *= 0.5; rr_ *= 0.5; }
            measuredSum_ += measured; predicted_ += estimatedKwh_;
            n_ += 1; r_ += ratio; rr_ += ratio * ratio;
            intervals_ = sat(intervals_); last_ = "interval_compared";
        }
        restart(totalM3, atMs);
    }

    uint16_t intervals() const { return intervals_; }
    uint16_t rejected() const { return rejected_; }
    bool calibrated() const { return intervals_ >= p_.minIntervals && predicted_ > 0; }
    // Measured / estimated gas; 1 until calibrated.
    float factor() const { return calibrated() ? static_cast<float>(std::clamp(measuredSum_ / predicted_, 0.5, 2.0)) : 1.0f; }
    // Relative spread (sd / mean) of the per-interval ratios; nullopt below two.
    std::optional<float> spread() const {
        if (n_ < 1.5 || r_ <= 0) return std::nullopt;
        const double mean = r_ / n_, var = std::max(0.0, rr_ / n_ - mean * mean);
        double sd = 1; // Newton square root (no libm sqrt member)
        for (int k = 0; k < 40 && var > 0; ++k) sd = 0.5 * (sd + var / sd);
        return static_cast<float>((var > 0 ? sd : 0) / mean);
    }
    // none (not calibrated) / low / medium / high: intervals and their agreement.
    const char* confidence() const {
        if (!calibrated()) return "none";
        const float s = spread().value_or(1);
        if (intervals_ >= 12 && s <= 0.15f) return "high";
        if (intervals_ >= 6 && s <= 0.3f) return "medium";
        return "low";
    }
    // no_meter / meter_stale (none for freshMs) / collecting / calibrated.
    const char* status(uint64_t now, uint64_t freshMs) const {
        if (!haveLast_) return calibrated() ? "meter_stale" : "no_meter";
        if (lastAt_ > now || now - lastAt_ > freshMs) return "meter_stale";
        return calibrated() ? "calibrated" : "collecting";
    }
    std::optional<uint64_t> meterAt() const { return haveLast_ ? std::optional<uint64_t>(lastAt_) : std::nullopt; }
    std::optional<double> meterM3() const { return open_ ? std::optional<double>(lastM3_) : std::nullopt; }
    const char* last() const { return last_; }
    // Estimated gas (kWh, uncalibrated) since boot, split by use: the night ledger's hot water share.
    double heatingKwh() const { return heatingKwh_; }
    double hotWaterKwh() const { return hotWaterKwh_; }

    // {"status","confidence","factor","kw_at_full_modulation","kw_source":"meter"|"boiler_kw"}
    // and, unless compact (heating_summary), "intervals","rejected","last","spread".
    bool json(cJSON* o, uint64_t now, uint64_t freshMs, float nominalKw, bool compact = false) const {
        const bool head = cJSON_AddStringToObject(o, "status", status(now, freshMs)) && cJSON_AddStringToObject(o, "confidence", confidence())
            && cJSON_AddNumberToObject(o, "factor", round(factor(), 1000))
            // Gas kWh per hour at 100 % modulation: per burner-modulation-hour.
            && cJSON_AddNumberToObject(o, "kw_at_full_modulation", round(nominalKw * factor(), 10))
            && cJSON_AddStringToObject(o, "kw_source", calibrated() ? "meter" : "boiler_kw");
        if (!head || compact) return head;
        const auto spreadValue = spread();
        return cJSON_AddNumberToObject(o, "intervals", intervals_) && cJSON_AddNumberToObject(o, "rejected", rejected_)
            && cJSON_AddStringToObject(o, "last", last_)
            && (spreadValue ? cJSON_AddNumberToObject(o, "spread", round(*spreadValue, 1000)) : cJSON_AddNullToObject(o, "spread"));
    }

private:
    static double round(double v, int scale) { return std::floor(v * scale + 0.5) / scale; }
    void invalidate(const char* why) { if (valid_ && open_) last_ = why; valid_ = false; }
    void restart(double totalM3, uint64_t atMs) {
        open_ = valid_ = true; baseM3_ = lastM3_ = totalM3; baseAt_ = atMs; estimatedKwh_ = 0;
    }
    template <typename T> static T sat(T v) { return v == T(~T(0)) ? v : T(v + 1); }
    Params p_;
    bool open_ = false, valid_ = false, haveLast_ = false;
    uint16_t intervals_ = 0, rejected_ = 0;
    uint64_t baseAt_ = 0, lastAt_ = 0;
    double baseM3_ = 0, lastM3_ = 0, estimatedKwh_ = 0, measuredSum_ = 0, predicted_ = 0, n_ = 0, r_ = 0, rr_ = 0;
    double heatingKwh_ = 0, hotWaterKwh_ = 0;
    const char* last_ = "no_interval";
};
}
