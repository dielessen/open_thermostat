#pragma once
#include <array>
#include <cstddef>
#include <algorithm>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class WithdrawalCause : size_t {
    normalStop, sourceLost, adapterLost, unknownSafety, dhwPriority,
    boilerFault, readinessLost, flowLost, limitTrip, timingFault, count
};
enum class WithdrawalPolicy : uint8_t {
    unspecified, withdrawHeatOnly, retainExistingPath, retainExistingPathAndPump
};
enum class HydraulicPathIntent { none, requestQualifiedPath, retainExistingPath };

struct HydraulicProfile {
    // Caller-owned reviewed installation policy, NEVER inferred from valve position.
    bool qualified = false, independentLimits = false, postrunPathValidated = false;
    uint32_t openingDeadlineMs = 0, feedbackTtlMs = 0, pumpStartDelayMs = 0;
    uint32_t postrunMs = 0, minimumOffMs = 0;
    int16_t minimumWaterCentiC = 0, maximumWaterCentiC = 0;
    uint32_t flowWaitDeadlineMs = 0;
    std::array<WithdrawalPolicy,static_cast<size_t>(WithdrawalCause::count)> withdrawalPolicies{};
    WithdrawalPolicy policy(WithdrawalCause cause) const { return withdrawalPolicies[static_cast<size_t>(cause)]; }
    bool valid() const {
        if (!(qualified && independentLimits && postrunPathValidated
            && openingDeadlineMs >= 1000 && openingDeadlineMs <= 600000
            && flowWaitDeadlineMs >= 1000 && flowWaitDeadlineMs <= 600000
            && feedbackTtlMs >= 100 && feedbackTtlMs <= 30000
            && pumpStartDelayMs <= 300000 && postrunMs <= 600000
            && minimumOffMs <= 600000 && minimumWaterCentiC >= 500
            && maximumWaterCentiC > minimumWaterCentiC && maximumWaterCentiC <= 9000)) return false;
        for (auto p:withdrawalPolicies)
            if (p < WithdrawalPolicy::withdrawHeatOnly || p > WithdrawalPolicy::retainExistingPathAndPump) return false;
        return true;
    }
};
struct HydraulicInputs {
    bool adapterAlive = false, sourceValid = false, heatDemand = false;
    bool limitsKnownSafe = false, limitTripped = false, faultStateKnown = false, boilerFault = false;
    bool dhwStateKnown = false, dhwActive = false, stop = false;
    bool actuatorFailure = false, readinessConfirmed = false, independentFlowConfirmed = false;
    uint64_t feedbackAt = 0, flowAt = 0;
    uint32_t feedbackCommand = 0;
    std::optional<int16_t> waterTarget;
};
enum class HydraulicPhase { inhibited, idle, opening, pumpWait, heating, postrun, fault };
inline const char* hydraulicPhaseName(HydraulicPhase phase) {
    switch (phase) {
        case HydraulicPhase::idle:return "idle";
        case HydraulicPhase::opening:return "opening";
        case HydraulicPhase::pumpWait:return "pump_wait";
        case HydraulicPhase::heating:return "heating";
        case HydraulicPhase::postrun:return "postrun";
        case HydraulicPhase::fault:return "fault";
        default:return "inhibited";
    }
}

// SHADOW intents only. No hardware callbacks or physical enable. false/none is
// NOT a universal close/deenergize/pump-off command; owner needs reviewed mapping.
class HydraulicSupervisor {
public:
    struct Result {
        HydraulicPhase phase = HydraulicPhase::inhibited;
        const char* reason = "hydraulic_profile_unqualified";
        bool heatIntent = false, openPathIntent = false, pumpIntent = false;
        bool physicalOutputsEnabled = false;
        uint32_t openingCommand = 0;
        std::optional<int16_t> waterTarget;
        HydraulicPathIntent pathIntent = HydraulicPathIntent::none;
    };
    explicit HydraulicSupervisor(HydraulicProfile profile = {}) : profile_(profile) {}
    void invalidate() {
        if (profile_.valid() && haveTime_) {
            latch(last_,WithdrawalCause::adapterLost,"adapter_unavailable");
            finish(withdrawalResult(last_,faultReason_));
        } else { phase_=HydraulicPhase::inhibited; lastResult_={}; }
    }
    const Result& lastIntent() const { return lastResult_; }
    bool clearFault(bool causeVerifiedCleared) {
        if (!causeVerifiedCleared) return false;
        latched_=false;
        // Clearing a fault never cancels an already required bounded postrun.
        phase_=withdrawalActive_?HydraulicPhase::postrun:HydraulicPhase::inhibited;
        return true;
    }
    Result step(uint64_t now,const HydraulicInputs& in) {
        const bool reversed=haveTime_ && now<last_;
        if (!haveTime_) {stoppedAt_=now;haveTime_=true;}
        last_=now;
        if (!profile_.valid()) return finish({});
        if (reversed) latch(now,WithdrawalCause::timingFault,"clock_reversed");
        if (in.limitTripped) latch(now,WithdrawalCause::limitTrip,"limit_trip");
        if (in.actuatorFailure) latch(now,WithdrawalCause::readinessLost,"actuator_failure");
        if (in.faultStateKnown && in.boilerFault) latch(now,WithdrawalCause::boilerFault,"boiler_fault");
        if (!in.adapterAlive && (lastResult_.openPathIntent || lastResult_.pumpIntent || latched_))
            latch(now,WithdrawalCause::adapterLost,"adapter_unavailable");
        if (latched_) {
            restrictForCurrentLosses(in,now);
            phase_=HydraulicPhase::fault;
            return finish(withdrawalResult(now,faultReason_));
        }
        WithdrawalCause cause=WithdrawalCause::normalStop;
        const char* inhibit=nullptr;
        if (in.stop) inhibit="stop";
        else if (!in.adapterAlive) {inhibit="adapter_unavailable";cause=WithdrawalCause::adapterLost;}
        else if (!in.sourceValid) {inhibit="source_unavailable";cause=WithdrawalCause::sourceLost;}
        else if (!in.limitsKnownSafe) {inhibit="limits_unknown";cause=WithdrawalCause::unknownSafety;}
        else if (!in.faultStateKnown) {inhibit="fault_state_unknown";cause=WithdrawalCause::unknownSafety;}
        else if (!in.dhwStateKnown) {inhibit="dhw_state_unknown";cause=WithdrawalCause::unknownSafety;}
        else if (in.dhwActive) {inhibit="dhw_priority";cause=WithdrawalCause::dhwPriority;}
        if (inhibit || !in.heatDemand) {
            withdraw(now,cause,inhibit?inhibit:"no_demand");
            restrictForCurrentLosses(in,now);
            return finish(withdrawalResult(now,inhibit?inhibit:"no_demand"));
        }
        if (!in.waterTarget || *in.waterTarget<profile_.minimumWaterCentiC
            || *in.waterTarget>profile_.maximumWaterCentiC) {
            withdraw(now,WithdrawalCause::normalStop,"water_target_invalid");
            restrictForCurrentLosses(in,now);
            return finish(withdrawalResult(now,"water_target_invalid"));
        }
        if (withdrawalActive_) {
            restrictForCurrentLosses(in,now);
            if (!withdrawalExpired(now)) return finish(withdrawalResult(now,"postrun"));
            withdrawalActive_=false;phase_=HydraulicPhase::idle;
            lastResult_.pumpIntent=false;lastResult_.heatIntent=false;
            setPath(lastResult_,HydraulicPathIntent::none);
        }
        if (phase_==HydraulicPhase::inhibited || phase_==HydraulicPhase::idle) {
            if (command_==UINT32_MAX) {
                latch(now,WithdrawalCause::timingFault,"command_exhausted");
                return finish(withdrawalResult(now,faultReason_));
            }
            ++command_;openedAt_=now;phase_=HydraulicPhase::opening;
        }
        const auto fresh=[this,now](uint64_t at) {
            return now>=at && now-at<profile_.feedbackTtlMs;
        };
        const bool ready=in.readinessConfirmed && in.feedbackCommand==command_
            && in.feedbackAt>openedAt_ && fresh(in.feedbackAt);
        const bool flow=in.independentFlowConfirmed && in.flowAt>openedAt_ && fresh(in.flowAt);
        if (phase_==HydraulicPhase::opening) {
            if (now-openedAt_>=profile_.openingDeadlineMs) {
                latch(openedAt_+profile_.openingDeadlineMs,WithdrawalCause::readinessLost,"opening_timeout");
                restrictForCurrentLosses(in,now);
                return finish(withdrawalResult(now,faultReason_));
            }
            if (ready) {phase_=HydraulicPhase::pumpWait;pumpAt_=now;}
        } else if (!ready || (phase_==HydraulicPhase::heating && !flow)) {
            latch(now,!ready?WithdrawalCause::readinessLost:WithdrawalCause::flowLost,
                  !ready?"readiness_lost":"flow_lost");
            restrictForCurrentLosses(in,now);
            return finish(withdrawalResult(now,faultReason_));
        }
        if (phase_==HydraulicPhase::pumpWait) {
            const uint64_t wait=now-pumpAt_;
            const uint64_t maximumWait=static_cast<uint64_t>(profile_.flowWaitDeadlineMs)
                +profile_.pumpStartDelayMs+profile_.minimumOffMs;
            if ((!flow && wait>=profile_.flowWaitDeadlineMs) || wait>=maximumWait) {
                const uint64_t deadline=pumpAt_+(!flow?profile_.flowWaitDeadlineMs:maximumWait);
                latch(deadline,WithdrawalCause::flowLost,"flow_or_pump_wait_timeout");
                restrictForCurrentLosses(in,now);
                return finish(withdrawalResult(now,faultReason_));
            }
            if (ready && flow && wait>=profile_.pumpStartDelayMs
                && now-stoppedAt_>=profile_.minimumOffMs) phase_=HydraulicPhase::heating;
        }
        auto r=result(phase_==HydraulicPhase::heating?"shadow_heat_intent":
                      phase_==HydraulicPhase::pumpWait?(flow?"pump_delay_or_minimum_off":"flow_unconfirmed"):"opening");
        setPath(r,HydraulicPathIntent::requestQualifiedPath);
        r.pumpIntent=phase_==HydraulicPhase::pumpWait || phase_==HydraulicPhase::heating;
        r.heatIntent=phase_==HydraulicPhase::heating;
        if (r.heatIntent) r.waterTarget=in.waterTarget;
        return finish(r);
    }
private:
    static void setPath(Result& r,HydraulicPathIntent p) {
        r.pathIntent=p;r.openPathIntent=p!=HydraulicPathIntent::none;
    }
    Result finish(Result r) {r.physicalOutputsEnabled=false;lastResult_=r;return r;}
    void beginWithdrawal(uint64_t now,WithdrawalCause cause) {
        if (!withdrawalActive_) {
            heldPath_=lastResult_.openPathIntent;heldPump_=lastResult_.pumpIntent;
            withdrawalAt_=now;
            withdrawalActive_=heldPath_ || heldPump_ || lastResult_.heatIntent;
            retention_=profile_.policy(cause);
            if (withdrawalActive_) stoppedAt_=now;
        } else retention_=std::min(retention_,profile_.policy(cause));
    }
    void latch(uint64_t now,WithdrawalCause cause,const char* reason) {
        beginWithdrawal(now,cause);
        if (!latched_) {faultReason_=reason;latched_=true;}
        phase_=HydraulicPhase::fault;
    }
    bool withdrawalExpired(uint64_t now) const {
        return now>=withdrawalAt_ && now-withdrawalAt_>=profile_.postrunMs;
    }
    Result withdrawalResult(uint64_t now,const char* reason) const {
        auto r=result(reason);
        // Backwards time cannot re-enable a path/pump before the first deadline.
        if (!withdrawalActive_ || now<withdrawalAt_ || withdrawalExpired(now)) return r;
        if (heldPath_ && retention_>=WithdrawalPolicy::retainExistingPath)
            setPath(r,HydraulicPathIntent::retainExistingPath);
        r.pumpIntent=heldPump_ && retention_==WithdrawalPolicy::retainExistingPathAndPump;
        return r;
    }
    Result withdraw(uint64_t now,WithdrawalCause cause,const char* reason) {
        beginWithdrawal(now,cause);
        if (withdrawalActive_ && !withdrawalExpired(now)) phase_=HydraulicPhase::postrun;
        else {withdrawalActive_=false;phase_=HydraulicPhase::idle;}
        return withdrawalResult(now,reason);
    }
    void restrictForCurrentLosses(const HydraulicInputs& in,uint64_t now) {
        // Escalation may remove retention but can NEVER renew deadline or restore it.
        const auto restrict=[this](WithdrawalCause c){retention_=std::min(retention_,profile_.policy(c));};
        if (!in.adapterAlive) restrict(WithdrawalCause::adapterLost);
        if (!in.sourceValid) restrict(WithdrawalCause::sourceLost);
        if (!in.limitsKnownSafe || !in.faultStateKnown || !in.dhwStateKnown) restrict(WithdrawalCause::unknownSafety);
        if (in.dhwActive) restrict(WithdrawalCause::dhwPriority);
        if (!in.readinessConfirmed || in.feedbackCommand!=command_ || in.feedbackAt<=openedAt_ || now<in.feedbackAt
            || now-in.feedbackAt>=profile_.feedbackTtlMs) restrict(WithdrawalCause::readinessLost);
        if (!in.independentFlowConfirmed || in.flowAt<=openedAt_ || now<in.flowAt || now-in.flowAt>=profile_.feedbackTtlMs)
            restrict(WithdrawalCause::flowLost);
    }
    Result result(const char* reason) const {
        Result r;r.phase=phase_;r.reason=reason;r.openingCommand=command_;return r;
    }
    HydraulicProfile profile_;
    HydraulicPhase phase_=HydraulicPhase::inhibited;
    Result lastResult_;
    uint64_t last_=0,openedAt_=0,pumpAt_=0,stoppedAt_=0,withdrawalAt_=0;
    uint32_t command_=0;
    bool haveTime_=false,latched_=false,withdrawalActive_=false,heldPath_=false,heldPump_=false;
    WithdrawalPolicy retention_=WithdrawalPolicy::withdrawHeatOnly;
    const char* faultReason_="latched_fault";
};
}
