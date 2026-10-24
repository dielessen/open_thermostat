#pragma once
#include "HydraulicSupervisor.h"
#include <array>
#include <functional>
#include <string>
#include <string_view>

namespace heating::control {
// SOURCE-owned installation policy, never decoded from an HTTP/MQTT setting.
// This connects SHADOW intents only; selection cannot enable physical outputs.
struct HydraulicControllerSource {
    std::string controllerId, adapterId, profileDigest;
    HydraulicProfile profile;
    uint32_t maximumFactAgeMs=0;
    bool valid() const {
        if(controllerId.empty()||controllerId.size()>32||adapterId.empty()||adapterId.size()>32
            ||profileDigest.size()!=64||!profile.valid()||maximumFactAgeMs<100||maximumFactAgeMs>30000)return false;
        for(char c:profileDigest)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
        return true;
    }
};
struct HydraulicOwnerContext {
    uint32_t generation=0, revision=0, openingCommand=0;
    uint64_t startedAt=0;
    std::string_view bootId;
};
struct HydraulicFeedbackSnapshot {
    uint32_t ownerGeneration=0, configRevision=0;
    uint64_t ownerStartedAt=0;
    std::array<char,33> bootId{};
    // Preserve each producer's original time. Reading an aggregate MUST NOT
    // rejuvenate older DHW/limits/flow facts with the newest callback time.
    uint64_t limitsAt=0, faultAt=0, dhwAt=0, waterTargetAt=0;
    bool limitsKnownSafe=false, limitTripped=false, faultStateKnown=false, boilerFault=false;
    bool dhwStateKnown=false, dhwActive=false, stop=false, actuatorFailure=false;
    bool readinessConfirmed=false, independentFlowConfirmed=false;
    uint64_t feedbackAt=0, flowAt=0;
    uint32_t feedbackCommand=0;
    std::optional<int16_t> waterTarget;
};
using HydraulicFeedbackProvider=std::function<HydraulicFeedbackSnapshot(const HydraulicOwnerContext&)>;

// No IO, timers, allocations or inferred facts. Context is an ownership fence,
// not acquisition/command proof. Physical producer/profile qualification remains
// independently required; callers cannot turn matching context into readiness.
class HydraulicFeedbackGate {
public:
    struct Result {HydraulicInputs inputs;const char* reason="hydraulic_feedback_unavailable";};
    Result evaluate(uint64_t now,uint32_t maximumAge,const HydraulicOwnerContext& owner,
                    const HydraulicFeedbackSnapshot& s) {
        const auto bootEnd=std::find(s.bootId.begin(),s.bootId.end(),'\0');
        if(owner.bootId.empty()||owner.bootId.size()>32||std::string_view(s.bootId.data(),size_t(bootEnd-s.bootId.begin()))!=owner.bootId
            ||maximumAge<100||maximumAge>30000||!owner.generation||!owner.revision||owner.startedAt>now
            ||s.ownerGeneration!=owner.generation||s.configRevision!=owner.revision||s.ownerStartedAt!=owner.startedAt)
            return deny(nullptr,"hydraulic_feedback_owner_mismatch");
        if(clockInvalid_||(haveTime_&&now<lastNow_)) {
            clockInvalid_=true;return deny(&s,"hydraulic_feedback_clock_invalid");
        }
        haveTime_=true;lastNow_=now;
        const std::array<uint64_t,6> times{s.limitsAt,s.faultAt,s.dhwAt,s.waterTargetAt,s.feedbackAt,s.flowAt};
        const std::array<uint64_t,6> values{
            uint64_t(s.limitsKnownSafe)|(uint64_t(s.limitTripped)<<1),
            uint64_t(s.faultStateKnown)|(uint64_t(s.boilerFault)<<1),
            uint64_t(s.dhwStateKnown)|(uint64_t(s.dhwActive)<<1),
            s.waterTarget?(uint64_t(uint16_t(*s.waterTarget))|(uint64_t{1}<<16)):0,
            uint64_t(s.readinessConfirmed)|(uint64_t(s.feedbackCommand)<<1),uint64_t(s.independentFlowConfirmed)};
        // Validate the whole snapshot before committing any replay watermark.
        for(size_t i=0;i<times.size();++i) {
            if(times[i]>now)return deny(&s,"hydraulic_feedback_future",i);
            if(times[i]&&(times[i]<lastAt_[i]||(times[i]==lastAt_[i]&&(values[i]!=lastValue_[i]||revoked_[i]))))
                return deny(&s,"hydraulic_feedback_reordered",i);
        }
        const auto fresh=[&](uint64_t at){return at>owner.startedAt&&now>=at&&now-at<maximumAge;};
        for(size_t i=0;i<times.size();++i) {
            if(times[i]){lastAt_[i]=times[i];lastValue_[i]=values[i];revoked_[i]=!fresh(times[i]);}
            else if(lastAt_[i])revoked_[i]=true; // Missing/expired evidence retires that cached fact.
        }
        HydraulicInputs in;
        in.limitsKnownSafe=s.limitsKnownSafe&&fresh(s.limitsAt);in.limitTripped=s.limitTripped;
        in.faultStateKnown=s.faultStateKnown&&fresh(s.faultAt);in.boilerFault=s.boilerFault;
        in.dhwStateKnown=s.dhwStateKnown&&fresh(s.dhwAt);in.dhwActive=s.dhwActive;
        in.stop=s.stop;in.actuatorFailure=s.actuatorFailure;
        in.readinessConfirmed=s.readinessConfirmed&&fresh(s.feedbackAt);
        in.independentFlowConfirmed=s.independentFlowConfirmed&&fresh(s.flowAt);
        in.feedbackAt=s.feedbackAt;in.flowAt=s.flowAt;in.feedbackCommand=s.feedbackCommand;
        if(fresh(s.waterTargetAt))in.waterTarget=s.waterTarget;
        return {in,"hydraulic_feedback_received"};
    }
private:
    Result deny(const HydraulicFeedbackSnapshot* current,const char* reason,size_t fact=6) {
        // Retire the affected proof without advancing its acquisition watermark.
        // An unrelated fact retains its own original lifetime; fixing one bad
        // field must not require reacquiring or rejuvenating all other fields.
        for(size_t i=0;i<lastAt_.size();++i)if(lastAt_[i]&&(fact==6||fact==i))revoked_[i]=true;
        HydraulicInputs in;
        if(current) {
            // Only AFTER the owner fence: preserve asserted restrictions even
            // when an unrelated timestamp is invalid. Never preserve permission,
            // readiness, flow, target or source age from a rejected aggregate.
            in.limitTripped=current->limitTripped;in.boilerFault=current->boilerFault;
            in.dhwActive=current->dhwActive;in.stop=current->stop;
            in.actuatorFailure=current->actuatorFailure;
        }
        return {in,reason};
    }
    uint64_t lastNow_=0;
    bool haveTime_=false,clockInvalid_=false;
    std::array<uint64_t,6> lastAt_{},lastValue_{};
    std::array<bool,6> revoked_{};
};
}
