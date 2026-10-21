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

// Optional SOURCE-owned seasonal policy. Never decoded from a GUI/telemetry flag.
// This qualifies SHADOW advice only; it cannot establish real frost protection.
struct SeasonalProfile {
    bool enabled=false,installationQualified=false,frostAdviceReviewed=false;
    uint32_t maximumSensorAgeMs=0,maximumStepGapMs=0;
    int16_t frostTargetCentiC=500;
    bool valid() const {
        return enabled&&installationQualified&&maximumSensorAgeMs>=1000&&maximumSensorAgeMs<=120000
            &&maximumStepGapMs>=1000&&maximumStepGapMs<=300000
            &&frostTargetCentiC>=500&&frostTargetCentiC<=1500;
    }
};
enum class SeasonalStop { none,disabled,stop,preempted,leaseLost,sensorLost,limits,dhw,unknownSafety,timing,ownerFence,ownerChanged };
// Independent loss facts survive ALL early returns. SeasonalStop is display only.
enum class SeasonalRestriction : uint16_t {
    sourceUnavailable=1,adapterUnavailable=2,stop=4,limitsUnknown=8,
    dhwUnknown=16,dhwPriority=32,timingFault=64
};
inline constexpr uint16_t seasonalRestriction(SeasonalRestriction r) {return static_cast<uint16_t>(r);}
inline constexpr uint16_t seasonalRestrictionMask=127;
struct SeasonalInputs {
    bool ownerAdmitted=false,sourceQualified=false,limitsKnownSafe=false;
    bool dhwStateKnown=false,dhwActive=false,stop=false,preempted=false;
    bool summer=false,allOff=false,frostSelected=false;
    uint32_t ownerGeneration=0;
    uint64_t sensorAt=0;
    std::optional<int16_t> temperature,target;
};

// Pure logical demand, not an actuator/boiler write or readiness proof.
class ZoneRegulator {
public:
    struct Result {
        bool demand=false;uint16_t dutyPermille=0;
        bool seasonalEvaluated=false,seasonalQualified=false,frostAdvice=false;
        bool physicalOutputsEnabled=false,frostProtectionAvailable=false;
        uint16_t seasonalRestrictions=0;
        SeasonalStop seasonalStop=SeasonalStop::none;
        const char* reason="logical_demand";
    };
    explicit ZoneRegulator(ZoneControlProfile profile = {},SeasonalProfile seasonal = {})
        : profile_(profile),seasonal_(seasonal) {}
    // Explicit opt-in integration. Ordinary legacy step remains byte-for-byte logic.
    Result stepSeasonal(uint64_t now,const SeasonalInputs& in) {
        uint16_t restrictions=0;
        const auto restrict=[&](bool active,SeasonalRestriction loss) {
            if(active) restrictions|=seasonalRestriction(loss);
        };
        // Facts are captured BEFORE choosing the primary diagnostic reason.
        restrict(!seasonal_.valid()||!in.sourceQualified||!in.temperature
            ||(in.temperature&&(*in.temperature < -4000||*in.temperature>8500))
            ||now<in.sensorAt||now-in.sensorAt>=seasonal_.maximumSensorAgeMs,
            SeasonalRestriction::sourceUnavailable);
        restrict(!in.ownerAdmitted||in.preempted,SeasonalRestriction::adapterUnavailable);
        restrict(in.stop||in.allOff||(in.summer&&!in.frostSelected),SeasonalRestriction::stop);
        restrict(!in.limitsKnownSafe,SeasonalRestriction::limitsUnknown);
        restrict(!in.dhwStateKnown,SeasonalRestriction::dhwUnknown);
        restrict(in.dhwActive,SeasonalRestriction::dhwPriority);
        const auto deny=[&](SeasonalStop cause,const char* reason) {
            auto r=step(now,std::nullopt,std::nullopt,false,false,in.ownerGeneration);
            switch(cause) {
            case SeasonalStop::disabled:case SeasonalStop::sensorLost:
                restrict(true,SeasonalRestriction::sourceUnavailable);break;
            case SeasonalStop::leaseLost:case SeasonalStop::preempted:case SeasonalStop::ownerFence:case SeasonalStop::ownerChanged:
                restrict(true,SeasonalRestriction::adapterUnavailable);break;
            case SeasonalStop::timing:
                restrict(true,SeasonalRestriction::sourceUnavailable);
                restrict(true,SeasonalRestriction::timingFault);break;
            default:break;
            }
            r.seasonalEvaluated=true;r.seasonalRestrictions=restrictions;
            r.seasonalStop=cause;r.reason=reason;return r;
        };
        const auto fence=[&]() {fencedOwner_=std::max(fencedOwner_,highestOwner_);};
        if(!seasonal_.valid()) return deny(SeasonalStop::disabled,"seasonal_profile_disabled_or_unqualified");
        // Record continuity even on denied samples, so an outage cannot silently
        // rejuvenate an old owner. Discontinuity fences even a new owner; a fresh
        // greater generation and subsequent independent hydraulics recovery are required.
        const bool reversed=seasonalTime_&&now<seasonalAt_;
        const bool discontinuity=seasonalTime_&&(reversed||now-seasonalAt_>seasonal_.maximumStepGapMs);
        seasonalTime_=true;seasonalAt_=now;
        const bool newOwner=in.ownerGeneration>highestOwner_;
        const bool replacedOwner=highestOwner_&&newOwner;
        if(newOwner) highestOwner_=in.ownerGeneration;
        if(discontinuity) {fence();return deny(SeasonalStop::timing,"seasonal_clock_discontinuity");}
        if(!in.ownerAdmitted) {fence();return deny(SeasonalStop::leaseLost,"seasonal_owner_unavailable");}
        if(in.preempted) {fence();return deny(SeasonalStop::preempted,"seasonal_preempted");}
        if(!in.ownerGeneration||in.ownerGeneration<highestOwner_||in.ownerGeneration<=fencedOwner_)
            return deny(SeasonalStop::ownerFence,"seasonal_new_owner_required");
        if(replacedOwner) return deny(SeasonalStop::ownerChanged,"seasonal_owner_changed");
        // Hard stop/unknown safety wins over chosen frost/summer and all pulse
        // minimums. No minimum pulse is manufactured to satisfy a budget.
        if(in.stop||in.allOff) return deny(SeasonalStop::stop,"seasonal_stop");
        if(!in.limitsKnownSafe) return deny(SeasonalStop::limits,"seasonal_limits_unavailable");
        if(!in.dhwStateKnown) return deny(SeasonalStop::unknownSafety,"seasonal_dhw_unknown");
        if(in.dhwActive) return deny(SeasonalStop::dhw,"seasonal_dhw_priority");
        if(!in.sourceQualified||!in.temperature||now<in.sensorAt||now-in.sensorAt>=seasonal_.maximumSensorAgeMs)
            return deny(SeasonalStop::sensorLost,"seasonal_sensor_unavailable");
        if(in.frostSelected&&!seasonal_.frostAdviceReviewed)
            return deny(SeasonalStop::disabled,"seasonal_frost_unqualified");
        if(in.summer&&!in.frostSelected) return deny(SeasonalStop::stop,"seasonal_summer");
        const auto target=in.frostSelected?std::optional<int16_t>(seasonal_.frostTargetCentiC):in.target;
        auto r=step(now,in.temperature,target,true,true,in.ownerGeneration);
        r.seasonalEvaluated=true;r.seasonalQualified=profile_.valid()&&target.has_value()
            &&*target>=500&&*target<=3500&&*in.temperature>=-4000&&*in.temperature<=8500;
        if(!r.seasonalQualified) {restrictions|=seasonalRestriction(SeasonalRestriction::sourceUnavailable);r.seasonalRestrictions=restrictions;r.seasonalStop=SeasonalStop::sensorLost;r.reason="seasonal_target_or_sensor_invalid";return r;}
        r.seasonalRestrictions=restrictions;
        r.frostAdvice=in.frostSelected;
        r.reason=in.frostSelected?"shadow_frost_advice":r.demand?"shadow_seasonal_demand":"shadow_low_load_or_satisfied";
        return r;
    }
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
    SeasonalProfile seasonal_;
    uint32_t highestOwner_=0,fencedOwner_=0;
    uint64_t seasonalAt_=0;bool seasonalTime_=false;
    int64_t integral_ = 0;
    uint64_t last_ = 0, switchedAt_ = 0;
    uint32_t generation_ = 0;
    bool haveTime_ = false, demand_ = false;
};
}
