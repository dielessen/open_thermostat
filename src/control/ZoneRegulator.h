#pragma once
#include <algorithm>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class ZoneControl { hysteresis, directPi, slowBinaryPi, localTrv };
struct ZoneControlProfile {
    ZoneControl mode = ZoneControl::hysteresis;
    int32_t hysteresisCentiC = 20;
    int32_t kpPermillePerC = 0, kiPermillePerCMinute = 0;
    uint32_t cycleMs = 0, minimumOnMs = 0, minimumOffMs = 0;
    bool valid() const {
        if (hysteresisCentiC < 1 || hysteresisCentiC > 200) return false;
        if (mode == ZoneControl::hysteresis || mode == ZoneControl::localTrv) return true;
        if (mode != ZoneControl::directPi && mode != ZoneControl::slowBinaryPi) return false;
        if (kpPermillePerC < 1 || kpPermillePerC > 1000
            || kiPermillePerCMinute < 0 || kiPermillePerCMinute > 1000) return false;
        return mode == ZoneControl::directPi || (cycleMs >= 600000 && cycleMs <= 3600000
            && minimumOnMs >= 120000 && minimumOffMs >= 120000
            && minimumOnMs <= cycleMs / 2 && minimumOffMs <= cycleMs / 2);
    }
};

// Pure logical demand, not an actuator/boiler write or readiness proof.
class ZoneRegulator {
public:
    struct Result { bool demand = false; uint16_t dutyPermille = 0; };
    explicit ZoneRegulator(ZoneControlProfile profile = {}) : profile_(profile) {}
    Result step(uint64_t now, std::optional<int16_t> temperature,
                std::optional<int16_t> target, bool usable, bool deliveryAvailable = true,
                uint32_t controlGeneration = 0) {
        const bool reset = !haveTime_ || now < last_ || now - last_ > 300000
            || controlGeneration != generation_;
        const uint64_t dt = reset ? 0 : now - last_;
        if (reset) { integral_ = 0; demand_ = false; switchedAt_ = now; }
        last_ = now; haveTime_ = true; generation_ = controlGeneration;
        if (!usable || !deliveryAvailable || !profile_.valid() || !temperature || !target
            || *temperature < -4000 || *temperature > 8500 || *target < 500 || *target > 3500) {
            integral_ = 0; demand_ = false; switchedAt_ = now;
            return {};
        }
        const int32_t error = *target - *temperature;
        if (profile_.mode == ZoneControl::hysteresis || profile_.mode == ZoneControl::localTrv) {
            if (error >= profile_.hysteresisCentiC) demand_ = true;
            else if (error <= -profile_.hysteresisCentiC) demand_ = false;
            return {demand_, static_cast<uint16_t>(demand_ ? 1000 : 0)};
        }
        const int64_t proportional = static_cast<int64_t>(profile_.kpPermillePerC) * error / 100;
        // Retain fractional integral across short ticks, not per-tick truncation.
        constexpr int64_t integralScale = 6000000;
        const int64_t delta = static_cast<int64_t>(profile_.kiPermillePerCMinute) * error
                              * static_cast<int64_t>(dt);
        const int64_t tentative = std::clamp<int64_t>(integral_ + delta,
                                                     -1000 * integralScale, 1000 * integralScale);
        const int64_t combined = proportional * integralScale + tentative;
        // Do not wind up against either saturation boundary.
        if (!((combined > 1000 * integralScale && error > 0) || (combined < 0 && error < 0))) integral_ = tentative;
        const auto duty = static_cast<uint16_t>(std::clamp<int64_t>(proportional + integral_ / integralScale, 0, 1000));
        if (profile_.mode == ZoneControl::directPi) {
            demand_ = duty > 0;
            return {demand_, duty};
        }
        const uint64_t onMs = static_cast<uint64_t>(profile_.cycleMs) * duty / 1000;
        // Too short a pulse is suppressed, not rounded into an unrequested minimum.
        const bool wanted = onMs >= profile_.minimumOnMs
            && (duty == 1000 || profile_.cycleMs - onMs >= profile_.minimumOffMs)
            && now % profile_.cycleMs < onMs;
        const auto minimum = demand_ ? profile_.minimumOnMs : profile_.minimumOffMs;
        if (wanted != demand_ && now - switchedAt_ >= minimum) {
            demand_ = wanted; switchedAt_ = now;
        }
        return {demand_, duty};
    }
private:
    ZoneControlProfile profile_;
    int64_t integral_ = 0;
    uint64_t last_ = 0, switchedAt_ = 0;
    uint32_t generation_ = 0;
    bool haveTime_ = false, demand_ = false;
};
}
