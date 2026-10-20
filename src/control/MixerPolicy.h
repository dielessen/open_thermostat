#pragma once
#include <algorithm>
#include <cstdint>
#include <optional>

namespace heating::control {
enum class MixerKind { threePoint, analog0to10 };
struct MixerProfile {
    bool qualified=false, coldDirectionVerified=false, independentLimitsValidated=false;
    bool timedReferenceValidated=false;
    MixerKind kind=MixerKind::threePoint;
    uint32_t travelMs=0, feedbackTtlMs=0, reversalDeadMs=0, minimumWriteMs=0;
    int16_t minimumWaterCentiC=0, maximumWaterCentiC=0, deadbandCentiC=0;
    uint16_t coldMillivolts=0,warmMillivolts=0,analogStepPermillePerMinute=0,positionTolerancePermille=0;
    bool valid() const {
        if (!qualified || !coldDirectionVerified || !independentLimitsValidated
            || travelMs<1000 || travelMs>3600000 || feedbackTtlMs<100 || feedbackTtlMs>30000
            || reversalDeadMs<100 || reversalDeadMs>10000 || minimumWriteMs<1000
            || minimumWriteMs>60000 || minimumWaterCentiC<500
            || maximumWaterCentiC<=minimumWaterCentiC || maximumWaterCentiC>9000
            || deadbandCentiC<1 || deadbandCentiC>500) return false;
        return kind==MixerKind::threePoint || (kind==MixerKind::analog0to10
            && coldMillivolts<=10000 && warmMillivolts<=10000 && coldMillivolts!=warmMillivolts
            && analogStepPermillePerMinute>=1 && analogStepPermillePerMinute<=1000
            && positionTolerancePermille>=1 && positionTolerancePermille<=100);
    }
};
struct MixerInput {
    bool adapterAlive=false, independentLimitsHealthy=false, limitTripped=false;
    bool supplyFresh=false, requestReference=false, referenceSafeConfirmed=false;
    bool coldEndSwitch=false, positionFresh=false;
    std::optional<int16_t> supplyCentiC,targetCentiC;
    std::optional<uint16_t> positionPermille;
    uint64_t supplyAt=0,feedbackAt=0;
    uint32_t feedbackCommand=0;
};
class MixerPolicy {
public:
    struct Result {
        bool warmerIntent=false,colderIntent=false,referenceKnown=false,fault=false;
        std::optional<uint16_t> analogMillivolts;
        uint32_t command=0;
        const char* reason="mixer_profile_unqualified";
        // No boiler enable or implied hydraulic/physical readiness.
    };
    explicit MixerPolicy(MixerProfile profile):profile_(profile) {}
    void invalidate() { referenced_=homing_=false; motor_=0; haveTime_=false; lastAnalog_.reset();pendingAnalog_.reset(); }
    bool clearFault(bool verifiedCleared) {
        if (!verifiedCleared) return false;
        fault_=false;invalidate();return true;
    }
    Result step(uint64_t now,const MixerInput& in) {
        if (haveTime_ && now<clock_) fault_=true;
        if (!haveTime_) { idleAt_=now; writeAt_=now; }
        haveTime_=true;clock_=now;
        if (!profile_.valid()) return result("mixer_profile_unqualified");
        if (in.limitTripped) fault_=true;
        if (fault_) return result("mixer_fault");
        if (!in.adapterAlive || !in.independentLimitsHealthy) {
            referenced_=homing_=false;motor_=0;idleAt_=now;
            pendingAnalog_.reset();lastAnalog_.reset();
            return result("mixer_source_or_limits_unavailable");
        }
        const auto fresh=[this,now](uint64_t at) {return now>=at && now-at<profile_.feedbackTtlMs;};
        if (!in.supplyFresh || !in.supplyCentiC || !fresh(in.supplyAt)
            || *in.supplyCentiC < -4000 || *in.supplyCentiC > 13000) {
            motor_=0;homing_=false;idleAt_=now;return result("mixer_supply_unavailable");
        }
        if (*in.supplyCentiC>=profile_.maximumWaterCentiC) {
            fault_=true;motor_=0;return result("mixer_water_limit");
        }
        if (profile_.kind==MixerKind::analog0to10) {
            if (!in.positionFresh || !in.positionPermille || *in.positionPermille>1000
                || !fresh(in.feedbackAt)) {
                referenced_=false;return result("mixer_position_unavailable");
            }
            referenced_=true;
        } else if (!referenced_) {
            if (!in.referenceSafeConfirmed) {
                homing_=false;motor_=0;return result("mixer_reference_not_safe");
            }
            if (!homing_) {
                if (!in.requestReference) return result("mixer_reference_required");
                if (!nextCommand()) return result("mixer_command_exhausted");
                homing_=true;homingAt_=now;motor_=0;
            }
            if (in.coldEndSwitch && in.feedbackCommand==command_ && in.feedbackAt>homingAt_
                && fresh(in.feedbackAt)) {
                referenced_=true;homing_=false;idleAt_=now;
                return result("mixer_end_switch_reference");
            }
            if (now-homingAt_>=profile_.travelMs) {
                homing_=false;
                if (!profile_.timedReferenceValidated) {fault_=true;return result("mixer_reference_timeout");}
                referenced_=true;idleAt_=now;return result("mixer_timed_reference");
            }
            auto r=result("mixer_referencing_cold");r.colderIntent=true;return r;
        }
        if (!in.targetCentiC || *in.targetCentiC<profile_.minimumWaterCentiC
            || *in.targetCentiC>profile_.maximumWaterCentiC) {
            motor_=0;idleAt_=now;return result("mixer_target_invalid");
        }
        if (pendingAnalog_) {
            if (now-writeAt_>=profile_.travelMs) {fault_=true;return result("mixer_position_timeout");}
            const int32_t positionError=*in.positionPermille-*pendingAnalog_;
            if (in.feedbackAt<=writeAt_ || in.feedbackCommand!=command_
                || positionError < -profile_.positionTolerancePermille
                || positionError > profile_.positionTolerancePermille)
                return result("mixer_wait_feedback");
            pendingAnalog_.reset();
        }
        const int32_t error=*in.targetCentiC-*in.supplyCentiC;
        const int wanted=error>profile_.deadbandCentiC?1:error<-profile_.deadbandCentiC?-1:0;
        if (profile_.kind==MixerKind::analog0to10) {
            if (!wanted || now-writeAt_<profile_.minimumWriteMs) return result("mixer_hold");
            const auto dt=std::min<uint64_t>(now-writeAt_,60000);
            const auto step=static_cast<uint16_t>(profile_.analogStepPermillePerMinute*dt/60000);
            if (!step) return result("mixer_write_budget");
            const int32_t position=std::clamp<int32_t>(*in.positionPermille+wanted*step,0,1000);
            const auto millivolts=static_cast<uint16_t>(profile_.coldMillivolts+
                (static_cast<int32_t>(profile_.warmMillivolts)-profile_.coldMillivolts)*position/1000);
            if (lastAnalog_==millivolts) return result("mixer_wait_feedback");
            if (!nextCommand()) return result("mixer_command_exhausted");
            lastAnalog_=millivolts;pendingAnalog_=static_cast<uint16_t>(position);writeAt_=now;
            auto r=result("mixer_analog_intent");r.analogMillivolts=millivolts;return r;
        }
        if (wanted!=motor_) {
            if (motor_) {motor_=0;idleAt_=now;return result("mixer_reversal_deadtime");}
            if (!wanted) return result("mixer_hold");
            if (now-idleAt_<profile_.reversalDeadMs) return result("mixer_reversal_deadtime");
            if (!nextCommand()) return result("mixer_command_exhausted");
            motor_=wanted;driveAt_=now;
        }
        if (motor_ && now-driveAt_>=profile_.travelMs) {
            fault_=true;motor_=0;return result("mixer_travel_limit");
        }
        auto r=result(motor_?"mixer_motor_intent":"mixer_hold");
        r.warmerIntent=motor_>0;r.colderIntent=motor_<0;return r;
    }
private:
    bool nextCommand() {
        if (command_==UINT32_MAX) {fault_=true;motor_=0;return false;}
        ++command_;return true;
    }
    Result result(const char* reason) const {
        Result r;r.referenceKnown=referenced_;r.fault=fault_;r.command=command_;r.reason=reason;return r;
    }
    MixerProfile profile_;
    uint64_t clock_=0,homingAt_=0,idleAt_=0,driveAt_=0,writeAt_=0;
    uint32_t command_=0;
    int motor_=0;
    bool referenced_=false,homing_=false,fault_=false,haveTime_=false;
    std::optional<uint16_t> lastAnalog_,pendingAnalog_;
};
}
