#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class EmitterType { radiator, floor };
struct GroupWaterProfile {
    bool qualified = false, independentHighLimit = false;
    EmitterType emitter = EmitterType::radiator;
    bool qualifiedMixing = false, independentFloorCutout = false, floorSensorRequired = false;
    std::array<int16_t,9> curveCentiC{};
    int16_t minimumCentiC = 0, maximumCentiC = 0, correctionLimitCentiC = 0, floorMaximumCentiC = 0;
    std::optional<int16_t> fixedOutdoorFallback;
    bool valid() const {
        if (!qualified || !independentHighLimit || minimumCentiC < 500
            || maximumCentiC <= minimumCentiC || maximumCentiC > 9000
            || correctionLimitCentiC < 0 || correctionLimitCentiC > 1000) return false;
        for (size_t i=0;i<curveCentiC.size();++i)
            if (curveCentiC[i]<500 || curveCentiC[i]>9000 || (i && curveCentiC[i]<curveCentiC[i-1])) return false;
        if (fixedOutdoorFallback && (*fixedOutdoorFallback<minimumCentiC || *fixedOutdoorFallback>maximumCentiC))
            return false;
        return emitter==EmitterType::radiator || (emitter==EmitterType::floor
            && independentFloorCutout && floorMaximumCentiC>=500 && floorMaximumCentiC<=3500);
    }
};
struct GroupWaterInput {
    bool demand = false, sourceValid = false, deliveryAvailable = false;
    bool independentLimitHealthy = false, floorSensorFresh = false, outdoorFresh = false;
    std::optional<int16_t> outdoorCentiC, roomErrorCentiC, floorCentiC;
};
struct GroupWaterResult {
    std::optional<int16_t> target;
    const char* reason = "no_demand";
    bool safetyInhibit = false;
};

// Centi-degree variant; no whole-degree truncation of graph curves.
inline int16_t interpolateWaterCurve(int16_t outdoor,const std::array<int16_t,9>& curve) {
    if (outdoor>=2000) return curve.front();
    if (outdoor<=-2000) return curve.back();
    const int32_t distance=2000-static_cast<int32_t>(outdoor);
    const size_t index=static_cast<size_t>(distance/500);
    const int32_t part=distance%500;
    return static_cast<int16_t>(curve[index]+(static_cast<int32_t>(curve[index+1])-curve[index])*part/500);
}

inline GroupWaterResult groupWaterTarget(const GroupWaterProfile& p,const GroupWaterInput& in) {
    if (!p.valid()) return {{},"group_profile_unqualified"};
    if (!in.independentLimitHealthy) return {{},"independent_limit_unknown_or_tripped",true};
    if (p.emitter==EmitterType::floor && p.floorSensorRequired
        && (!in.floorSensorFresh || !in.floorCentiC)) return {{},"floor_sensor_unavailable",true};
    if (p.emitter==EmitterType::floor && in.floorSensorFresh && in.floorCentiC
        && (*in.floorCentiC < -4000 || *in.floorCentiC >= p.floorMaximumCentiC))
        return {{},"floor_temperature_limit",true};
    if (!in.demand) return {};
    if (!in.sourceValid || !in.deliveryAvailable) return {{},"group_unavailable"};
    if (p.correctionLimitCentiC && !in.roomErrorCentiC) return {{},"room_correction_unavailable"};
    std::optional<int16_t> base;
    const bool outdoorUsable = in.outdoorFresh && in.outdoorCentiC
        && *in.outdoorCentiC>=-6000 && *in.outdoorCentiC<=6000;
    if (outdoorUsable && *in.outdoorCentiC>=-6000 && *in.outdoorCentiC<=6000)
        base=interpolateWaterCurve(*in.outdoorCentiC,p.curveCentiC);
    else base=p.fixedOutdoorFallback;
    if (!base) return {{},"outdoor_unavailable"};
    const auto error=in.roomErrorCentiC.value_or(0);
    if (error < -10000 || error > 10000) return {{},"room_correction_invalid"};
    const auto correction=std::clamp<int32_t>(error,-p.correctionLimitCentiC,p.correctionLimitCentiC);
    return {static_cast<int16_t>(std::clamp<int32_t>(*base+correction,p.minimumCentiC,p.maximumCentiC)),
            outdoorUsable?"shadow_curve_target":"shadow_fixed_fallback_target"};
}

struct CentralWaterLimits {
    bool qualified = false;
    int16_t minimumCentiC = 0, maximumCentiC = 0;
};
// Fixed bounded native calculation only, NOT an E32 capacity advertisement.
inline GroupWaterResult aggregateWaterTargets(const GroupWaterProfile* profiles,
        const GroupWaterInput* inputs,size_t count,CentralWaterLimits boiler) {
    if (!profiles || !inputs || count==0 || count>8 || !boiler.qualified
        || boiler.minimumCentiC<500 || boiler.maximumCentiC<=boiler.minimumCentiC
        || boiler.maximumCentiC>9000) return {{},"central_profile_unqualified"};
    std::optional<int16_t> highest;
    for(size_t i=0;i<count;++i) {
        const auto& p=profiles[i];
        if (!p.valid() || p.minimumCentiC<boiler.minimumCentiC)
            return {{},"group_profile_unqualified"};
        // Inspect every configured floor, not only presently demanding groups.
        // Closing a valve is not an independent high-temperature barrier.
        if (p.emitter==EmitterType::floor && !p.qualifiedMixing && boiler.maximumCentiC>p.maximumCentiC)
            return {{},"floor_requires_mixing_or_shared_safe_limit"};
        const auto result=groupWaterTarget(p,inputs[i]);
        if (result.safetyInhibit) return result;
        if (!result.target) continue;
        if (*result.target>boiler.maximumCentiC) return {{},"boiler_water_limit"};
        if (!highest || *result.target>*highest) highest=result.target;
    }
    return {highest,highest?"shadow_central_water_target":"no_valid_demand"};
}

struct WaterWriteProfile {
    uint32_t minimumIntervalMs = 0;
    int16_t deadbandCentiC = 0, maximumChangeCentiCPerMinute = 0;
    bool valid() const {
        return minimumIntervalMs>=1000 && minimumIntervalMs<=60000
            && deadbandCentiC>=0 && deadbandCentiC<=500
            && maximumChangeCentiCPerMinute>=1 && maximumChangeCentiCPerMinute<=3000;
    }
};
class WaterWriteBudget {
public:
    struct Result { bool publishIntent=false; std::optional<int16_t> waterTarget; };
    explicit WaterWriteBudget(WaterWriteProfile p):profile_(p) {}
    Result step(uint64_t now,std::optional<int16_t> desired) {
        if (!profile_.valid() || (desired && (*desired<500 || *desired>9000))) desired.reset();
        if (haveClock_ && now<clock_) {
            const bool had=last_.has_value(); last_.reset(); clock_=now;
            return {had,{}}; // stop, never turn a clock reversal into positive demand
        }
        haveClock_=true; clock_=now;
        if (!desired) { const bool had=last_.has_value(); last_.reset(); return {had,{}}; }
        if (!last_) { last_=desired; sentAt_=now; return {true,last_}; }
        const int32_t difference=*desired-*last_;
        if (difference>=-profile_.deadbandCentiC && difference<=profile_.deadbandCentiC) return {};
        const uint64_t elapsed=now-sentAt_;
        if (elapsed<profile_.minimumIntervalMs) return {};
        // Cap multiplication before it can overflow; a full 85C range suffices.
        const auto boundedElapsed=std::min<uint64_t>(elapsed,600000000);
        const auto permitted=std::min<int64_t>(8500,
            static_cast<int64_t>(profile_.maximumChangeCentiCPerMinute)*boundedElapsed/60000);
        if (!permitted) return {};
        last_=static_cast<int16_t>(*last_+std::clamp<int64_t>(difference,-permitted,permitted));
        sentAt_=now; return {true,last_};
    }
private:
    WaterWriteProfile profile_;
    uint64_t clock_=0,sentAt_=0;
    bool haveClock_=false;
    std::optional<int16_t> last_;
};
}
