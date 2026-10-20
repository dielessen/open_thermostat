#pragma once
#include <algorithm>
#include <cstdint>
#include <optional>

namespace heating::ems {

// Observation-driven, boot-local totals. Snapshot/GET never advances time.
// Nominal power * modulation is an ESTIMATE, never measured gas or heat output.
class EmsMetricTotals {
public:
    static constexpr uint64_t ttlMs = 30000;
    struct Snapshot {
        double energyKwh = 0, heatingKwh = 0, dhwKwh = 0, unattributedKwh = 0;
        double waterLitres = 0, burnerSeconds = 0;
        std::optional<double> averageFlow, currentFlow;
        bool powerFresh = false, energyObserved = false, flowObserved = false, burnerObserved = false;
    };

    void nominal(uint64_t now, std::optional<uint8_t> value) {
        advance(now);
        nominalKw_ = value && *value > 0 && *value < 255 ? value : std::nullopt;
        markObserved(now);
    }
    void power(uint64_t now, std::optional<uint8_t> value) {
        advance(now);
        power_ = {value && *value <= 100 ? value : std::nullopt, now};
        markObserved(now);
    }
    void modes(uint64_t now, bool heating, bool dhw, bool burning) {
        advance(now);
        heating_ = {heating, now}; dhw_ = {dhw, now}; burning_ = {burning, now};
        totals_.burnerObserved = true;
        markObserved(now);
    }
    void flow(uint64_t now, std::optional<uint8_t> tenthsLitresPerMinute) {
        advance(now);
        flow_ = {tenthsLitresPerMinute && *tenthsLitresPerMinute < 255
                 ? tenthsLitresPerMinute : std::nullopt, now};
        if (flow_.value) totals_.flowObserved = true;
    }

    Snapshot snapshot(uint64_t now) const {
        Snapshot result = totals_;
        result.powerFresh = fresh(power_, now);
        if (flowMs_) result.averageFlow = totals_.waterLitres * 60000.0 / flowMs_;
        if (fresh(flow_, now)) result.currentFlow = *flow_.value / 10.0;
        return result;
    }

private:
    template<class T> struct Sample {
        std::optional<T> value;
        uint64_t observed = 0;
    };
    template<class T> static bool fresh(const Sample<T>& s, uint64_t now) {
        return s.value.has_value() && now >= s.observed && now - s.observed < ttlMs;
    }
    template<class T> static uint64_t duration(const Sample<T>& s, uint64_t from, uint64_t until) {
        if (!s.value || from < s.observed || from - s.observed >= ttlMs) return 0;
        return std::min(until - from, ttlMs - (from - s.observed));
    }
    void markObserved(uint64_t now) {
        if (nominalKw_ && fresh(power_, now) && fresh(burning_, now))
            totals_.energyObserved = true;
    }
    void advance(uint64_t now) {
        if (!haveStep_) { lastStep_ = now; haveStep_ = true; return; }
        if (now < lastStep_) {
            // A backwards/restarted monotonic clock cannot revive historical samples.
            power_ = {}; flow_ = {}; heating_ = {}; dhw_ = {}; burning_ = {};
            lastStep_ = now; return;
        }
        const auto powerMs = std::min(duration(power_, lastStep_, now),
                                      duration(burning_, lastStep_, now));
        if (nominalKw_ && powerMs && *burning_.value) {
            const double kw = *nominalKw_ * *power_.value / 100.0;
            const double energy = kw * powerMs / 3600000.0;
            totals_.energyKwh += energy;
            const auto modeMs = std::min({powerMs, duration(heating_, lastStep_, now),
                                          duration(dhw_, lastStep_, now)});
            double assigned = 0;
            if (modeMs && *heating_.value != *dhw_.value) {
                assigned = kw * modeMs / 3600000.0;
                if (*heating_.value) totals_.heatingKwh += assigned;
                else totals_.dhwKwh += assigned;
            }
            totals_.unattributedKwh += energy - assigned;
            totals_.energyObserved = true;
        }
        const auto flowMs = duration(flow_, lastStep_, now);
        if (flowMs) {
            totals_.waterLitres += *flow_.value / 10.0 * flowMs / 60000.0;
            flowMs_ += flowMs;
        }
        const auto burnerMs = duration(burning_, lastStep_, now);
        if (burnerMs && *burning_.value) totals_.burnerSeconds += burnerMs / 1000.0;
        lastStep_ = now;
    }

    Snapshot totals_;
    Sample<uint8_t> power_, flow_;
    Sample<bool> heating_, dhw_, burning_;
    std::optional<uint8_t> nominalKw_;
    uint64_t lastStep_ = 0, flowMs_ = 0;
    bool haveStep_ = false;
};
}
