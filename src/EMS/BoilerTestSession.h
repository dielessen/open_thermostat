#pragma once

#include "ClassicBoilerMonitor.h"
#include <cstdint>
#include <limits>
#include <optional>

namespace heating::ems {

// Pure commissioning policy. No UART/HTTP/HA callbacks and no physical authority.
// The eventual bus owner must serialize all calls including the final send check.
// In particular, selecting this policy cannot unlock Board::emsTransmitAllowed.
class BoilerTestSession {
public:
    static constexpr uint32_t maximumTrialMs = 600000;
    enum class Phase { idle, baseline, ready, heating, stopping, completed, fault, closed };
    enum class Command { none, zero, positive };
    enum class Reply { accepted, duplicate, refused };
    struct TransmittedRequest { uint8_t flowC; uint64_t completedAtMs; uint32_t sequence; };
    const std::optional<TransmittedRequest>& lastTransmittedRequest() const { return lastTransmittedRequest_; }

    enum class StopCause { explicitStop, heatDeadline, provingConditionsLost, operatorLeaseExpired };
    struct Profile {
        bool reviewed = false;
        uint8_t minimumFlowC = 0, maximumFlowC = 0;
        uint32_t maximumHeatMs = 0, stopTimeoutMs = 0, reportTtlMs = 0;
        uint32_t operatorLeaseMs = 0, writeIntervalMs = 0;
        // Reviewed SOFTWARE policy for the first supervised zero-only trial.
        // These are observation/lease/cadence limits, not a physical stop-time
        // guarantee or permission to transmit. Positive demand stays invalid.
        static Profile supervisedZeroOnly() {
            // Classic 0x18 broadcasts normally arrive every 10 seconds.
            return {true, 0, 0, 0, 30000, 15000, 5000, 1000};
        }
        bool validForZero() const {
            return reviewed && stopTimeoutMs >= 1000 && stopTimeoutMs <= 60000
                && reportTtlMs >= 100 && reportTtlMs <= 30000
                && operatorLeaseMs >= 1000 && operatorLeaseMs <= 10000
                && writeIntervalMs >= 100 && writeIntervalMs <= 10000;
        }
        bool valid() const {
            return validForZero() && minimumFlowC >= 5 && maximumFlowC > minimumFlowC && maximumFlowC <= 90
                && maximumHeatMs >= 1000 && maximumHeatMs <= maximumTrialMs;
        }
    };
    struct Gates {
        bool transmitterReviewed = false, exclusiveOwner = false;
        bool pathReady = false, limitsSafe = false, independentStopAvailable = false;
        bool allowsZero() const { return transmitterReviewed && exclusiveOwner; }
        bool allowsHeat() const { return allowsZero() && pathReady && limitsSafe && independentStopAvailable; }
    };
    struct Intent {
        Command command = Command::none;
        uint8_t flowC = 0;
        uint64_t boot = 0, session = 0, epoch = 0, expiresAt = 0;
    };

    explicit BoilerTestSession(uint64_t boot, Profile profile) : boot_(boot), profile_(profile) {}
    Phase phase() const { return phase_; }
    const char* reason() const { return reason_; }
    bool reportedStopConfirmed() const { return stopConfirmed_; }
    uint64_t heatDeadline() const { return heatUntil_; }
    uint64_t operatorDeadline() const { return operatorUntil_; }
    uint64_t sessionId() const { return session_; }
    bool transmissionInFlight() const { return inFlight_; }
    bool zeroOnly() const { return zeroOnly_; }
    // Historical observations for this one session. They never admit a command.
    bool requestedTemperatureReported() const { return selectedReported_; }
    bool heatingOperationReported() const { return heatingReported_; }
    bool durationCompleted() const { return durationCompleted_; }
    uint32_t requestedDurationSeconds() const { return heatMs_ / 1000; }
    const char* endReason() const { return endReason_; }
    // First matching completed zero for CURRENT stop proof, not a bus ACK.
    std::optional<uint64_t> stopReferenceMs() const {
        return zeroSent_ ? std::optional<uint64_t>(zeroSentAt_) : std::nullopt;
    }
    bool canPrepare(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor, bool zeroOnly = false) const {
        return !inFlight_ && (!haveTime_ || now >= lastNow_) && boot_ && (zeroOnly ? profile_.validForZero() : profile_.valid())
            && (phase_ == Phase::idle || phase_ == Phase::completed)
            && (zeroOnly ? gates.allowsZero() && gates.independentStopAvailable : gates.allowsHeat()) && feedbackValid(monitor, now)
            && canAdd(now, profile_.stopTimeoutMs) && canAdd(now, profile_.operatorLeaseMs);
    }
    bool canStart(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) const {
        return !inFlight_ && (!haveTime_ || now >= lastNow_) && phase_ == Phase::ready && !started_ && !zeroOnly_
            && now < operatorUntil_ && gates.allowsHeat() && feedbackValid(monitor, now)
            && reportedOff(monitor, now, zeroSentAt_) && canAdd(now, heatMs_);
    }
    bool active() const { return inFlight_ || (phase_ != Phase::idle && phase_ != Phase::completed && phase_ != Phase::closed); }
    bool canCloseFault(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) const {
        return phase_ == Phase::fault && !inFlight_ && (!haveTime_ || now >= lastNow_)
            && gates.allowsZero() && gates.independentStopAvailable && zeroSent_ && stopConfirmed_
            && reportedOff(monitor, now, zeroSentAt_);
    }
    bool closeFault(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        step(now, gates, monitor);
        if (!canCloseFault(now, gates, monitor)) return false;
        // Explicit terminal retirement, NOT successful commissioning or a reset
        // of the failure. Preserve its reason and stop history; no new prepare
        // is admitted in this boot. All old transmission tickets are retired.
        phase_ = Phase::closed; ++epoch_; sent_ = false;
        return true;
    }
    void transportFault(uint64_t now) {
        if (observeTime(now) && active()) fail("test_transport_unavailable");
    }

    Reply prepare(uint64_t boot, uint64_t session, uint8_t flowC, uint32_t heatMs,
                  uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor, bool zeroOnly = false) {
        if (!observeTime(now)) return Reply::refused;
        if (boot == boot_ && session && session == session_)
            return zeroOnly == zeroOnly_ && flowC == flowC_ && heatMs == heatMs_ ? Reply::duplicate : Reply::refused;
        if (inFlight_ || !boot_ || boot != boot_ || !session || session <= session_
            || (phase_ != Phase::idle && phase_ != Phase::completed)
            || !(zeroOnly ? profile_.validForZero() && gates.allowsZero() && gates.independentStopAvailable
                          : profile_.valid() && gates.allowsHeat()) || !feedbackValid(monitor, now)
            || (zeroOnly ? flowC != 0 || heatMs != 0 : flowC < profile_.minimumFlowC || flowC > profile_.maximumFlowC
                || heatMs < 1000 || heatMs > profile_.maximumHeatMs)
            || !canAdd(now, profile_.stopTimeoutMs) || !canAdd(now, profile_.operatorLeaseMs))
            return Reply::refused;
        firstPositiveAt_.reset(); selectedReported_ = heatingReported_ = durationCompleted_ = false;
        endReason_ = "";
        session_ = session; flowC_ = flowC; heatMs_ = heatMs; zeroOnly_ = zeroOnly;
        operatorUntil_ = now + profile_.operatorLeaseMs;
        enter(Phase::baseline, "checking_reported_stop", now);
        return Reply::accepted;
    }

    Reply start(uint64_t boot, uint64_t session, uint64_t now,
                const Gates& gates, const ClassicBoilerMonitor& monitor) {
        step(now, gates, monitor);
        if (boot != boot_ || session != session_ || !session) return Reply::refused;
        if (started_) return Reply::duplicate; // never extend or revive, even after completion
        if (zeroOnly_ || inFlight_ || phase_ != Phase::ready || !gates.allowsHeat() || !feedbackValid(monitor, now)
            || !reportedOff(monitor, now, zeroSentAt_) || !canAdd(now, heatMs_)) return Reply::refused;
        heatUntil_ = now + heatMs_; started_ = true;
        enter(Phase::heating, "bounded_heat_request", now);
        return Reply::accepted;
    }

    bool keepAlive(uint64_t boot, uint64_t session, uint64_t now) {
        if (!observeTime(now) || boot != boot_ || session != session_ || !session
            || !active() || phase_ == Phase::fault) return false;
        if (now >= operatorUntil_ || !canAdd(now, profile_.operatorLeaseMs)) {
            stop(now, StopCause::operatorLeaseExpired); return false;
        }
        operatorUntil_ = now + profile_.operatorLeaseMs;
        return true;
    }

    void stop(uint64_t now, StopCause cause = StopCause::explicitStop) {
        if (!observeTime(now)) return;
        if (phase_ == Phase::idle || phase_ == Phase::completed || phase_ == Phase::closed || phase_ == Phase::fault
            || phase_ == Phase::stopping) return;
        const char* reason = cause == StopCause::explicitStop ? "explicit_stop"
            : cause == StopCause::heatDeadline ? "heat_deadline"
            : cause == StopCause::operatorLeaseExpired ? "operator_lease_expired" : "proving_conditions_lost";
        durationCompleted_ = cause == StopCause::heatDeadline;
        endReason_ = reason;
        // Expiry is an event at its fixed deadline, not at the later owner tick.
        const uint64_t at = cause == StopCause::heatDeadline && heatUntil_ <= now ? heatUntil_
            : cause == StopCause::operatorLeaseExpired && operatorUntil_ <= now ? operatorUntil_ : now;
        enter(Phase::stopping, reason, at);
    }

    void step(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        if (!observeTime(now) || phase_ == Phase::idle || phase_ == Phase::completed || phase_ == Phase::closed) return;
        if (phase_ == Phase::fault) {
            const bool confirmed = zeroSent_ && reportedOff(monitor, now, zeroSentAt_);
            if (stopConfirmed_ && !confirmed) {
                // Lost/stale stop proof needs a NEW zero and subsequent report.
                // Old tickets and their write cooldown cannot postpone it.
                ++epoch_; zeroSent_ = false; sent_ = false;
            }
            stopConfirmed_ = confirmed;
            return; // no automatic recovery or new session after a fault
        }
        if (!gates.allowsZero()) { fail("transmitter_or_owner_lost"); return; }
        // Preserve a baseline/stop timeout before lease loss can change phase
        // and accidentally create a new proving window.
        if ((phase_ == Phase::baseline || phase_ == Phase::stopping)
            && now - phaseAt_ >= profile_.stopTimeoutMs) {
            fail("reported_stop_timeout"); return;
        }
        if (phase_ == Phase::heating) observeHeating(monitor, now);
        if (phase_ == Phase::heating && (now >= heatUntil_ || now >= operatorUntil_
            || !gates.allowsHeat() || !feedbackValid(monitor, now))) {
            stop(now, now >= operatorUntil_ && (operatorUntil_ <= heatUntil_ || now < heatUntil_)
                ? StopCause::operatorLeaseExpired
                : now >= heatUntil_ ? StopCause::heatDeadline : StopCause::provingConditionsLost);
        } else if ((phase_ == Phase::baseline || phase_ == Phase::ready)
            && (now >= operatorUntil_ || (!zeroOnly_ && !gates.allowsHeat()) || !feedbackValid(monitor, now))) {
            stop(now, now >= operatorUntil_ ? StopCause::operatorLeaseExpired : StopCause::provingConditionsLost);
        }
        // The fixed proving deadline wins over a late callback/report. Otherwise
        // a stalled owner could admit heat after its baseline timeout, or mark
        // an expired stop successful. Recovery still requires a new fault-zero.
        if ((phase_ == Phase::baseline || phase_ == Phase::stopping)
            && now - phaseAt_ >= profile_.stopTimeoutMs) {
            fail("reported_stop_timeout"); return;
        }
        if ((phase_ == Phase::baseline || phase_ == Phase::stopping) && zeroSent_
            && reportedOff(monitor, now, zeroSentAt_)) {
            stopConfirmed_ = true;
            if (phase_ == Phase::baseline && !zeroOnly_) {
                phase_ = Phase::ready; reason_ = "reported_stop_baseline_confirmed"; ++epoch_;
            } else { phase_ = Phase::completed; reason_ = "reported_stop_confirmed"; ++epoch_; }
        }
    }

    Intent next(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        step(now, gates, monitor);
        if (inFlight_ || !gates.allowsZero() || !session_
            || (phase_ == Phase::fault && stopConfirmed_)) return {};
        const Command command = phase_ == Phase::heating ? Command::positive
            : phase_ == Phase::baseline || phase_ == Phase::stopping || phase_ == Phase::fault ? Command::zero : Command::none;
        if (command == Command::none || (sent_ && now >= sentAt_ && now - sentAt_ < profile_.writeIntervalMs)) return {};
        return {command, static_cast<uint8_t>(command == Command::positive ? flowC_ : 0),
                boot_, session_, epoch_, command == Command::positive ? heatUntil_ : 0};
    }

    // Invoke at the last serialized boundary before transmission, not just when
    // queueing. Old positive intents are invalidated immediately by stop/expiry.
    bool mayTransmit(const Intent& intent, uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto current = next(now, gates, monitor);
        return current.command != Command::none && intent.command == current.command
            && intent.flowC == current.flowC && intent.boot == current.boot && intent.session == current.session
            && intent.epoch == current.epoch && intent.expiresAt == current.expiresAt;
    }
    bool beginTransmit(const Intent& intent, uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        if (!mayTransmit(intent, now, gates, monitor)) return false;
        inFlight_ = true; pending_ = intent; beganAt_ = now;
        return true;
    }
    // A completed IO is a historical fact even if stop/deadline intervened.
    // Its old positive budget MUST NOT delay a newer required zero. Only a
    // matching current zero can establish post-completion reported stop proof.
    bool finishTransmit(const Intent& intent, uint64_t now, bool success,
                        const Gates& gates, const ClassicBoilerMonitor& monitor) {
        if (!inFlight_ || intent.command != pending_.command || intent.flowC != pending_.flowC
            || intent.boot != pending_.boot || intent.session != pending_.session
            || intent.epoch != pending_.epoch || intent.expiresAt != pending_.expiresAt) return false;
        inFlight_ = false;
        const bool validTime = observeTime(now) && now >= beganAt_;
        step(now, gates, monitor);
        if (!success) { fail("transmission_failed"); return false; }
        // Historical completed UART IO, never a proposal or boiler readback.
        if (validTime && transmittedSequence_ != UINT32_MAX) {
            lastTransmittedRequest_ = TransmittedRequest{intent.flowC, now, ++transmittedSequence_};
        } else lastTransmittedRequest_.reset();
        if (!validTime || intent.epoch != epoch_) return true;
        sent_ = true; sentAt_ = now;
        if (intent.command == Command::positive && !firstPositiveAt_) firstPositiveAt_ = now;
        if (intent.command == Command::zero && !zeroSent_) { zeroSent_ = true; zeroSentAt_ = now; }
        return true;
    }

private:
    std::optional<TransmittedRequest> lastTransmittedRequest_;
    uint32_t transmittedSequence_ = 0;
    static bool canAdd(uint64_t now, uint64_t duration) {
        return now <= std::numeric_limits<uint64_t>::max() - duration;
    }
    bool observeTime(uint64_t now) {
        if (haveTime_ && now < lastNow_) {
            if (active()) {
                fail("monotonic_clock_reversed");
                // A previously faulted session must also retire stop proof.
                // Returning to an older clock cannot retain its confirmation.
                if (stopConfirmed_ || zeroSent_ || sent_) ++epoch_;
                stopConfirmed_=false;zeroSent_=false;sent_=false;
            }
            return false;
        }
        haveTime_ = true; lastNow_ = now; return true;
    }
    bool fresh(const BoilerSample& sample, uint64_t now) const {
        return sample.raw && sample.fresh(now, profile_.reportTtlMs);
    }
    bool feedbackValid(const ClassicBoilerMonitor& monitor, uint64_t now) const {
        const auto& cv = monitor.sample(BoilerField::heatingActive);
        const auto& power = monitor.sample(BoilerField::modulation);
        const auto& dhw = monitor.sample(BoilerField::dhwActive);
        return monitor.capabilities().profile() == BoilerProtocol::classic
            && fresh(cv, now) && fresh(power, now) && fresh(dhw, now) && *dhw.raw == 0;
    }
    void observeHeating(const ClassicBoilerMonitor& monitor, uint64_t now) {
        if ((selectedReported_ && heatingReported_) || !firstPositiveAt_ || now > heatUntil_
            || !feedbackValid(monitor, now)) return;
        const auto& selected = monitor.sample(BoilerField::selectedFlow);
        const auto& cv = monitor.sample(BoilerField::heatingActive);
        const auto& dhw = monitor.sample(BoilerField::dhwActive);
        const auto afterCommand = [&](const BoilerSample& sample, BoilerQuality quality) {
            return fresh(sample, now) && sample.quality == quality && sample.sourceType == 0x18
                && sample.observedMs > *firstPositiveAt_ && sample.observedMs <= now
                && sample.observedMs <= heatUntil_;
        };
        if (afterCommand(selected, BoilerQuality::reported) && *selected.raw == flowC_ * 100)
            selectedReported_ = true;
        // Adapter-derived CV status; not independent flame or radiator proof.
        if (afterCommand(cv, BoilerQuality::inferred) && afterCommand(dhw, BoilerQuality::inferred)
            && cv.observedMs == dhw.observedMs && *cv.raw == 1 && *dhw.raw == 0) heatingReported_ = true;
    }
    bool reportedOff(const ClassicBoilerMonitor& monitor, uint64_t now, uint64_t after) const {
        const auto& cv = monitor.sample(BoilerField::heatingActive);
        const auto& power = monitor.sample(BoilerField::modulation);
        const auto& selected = monitor.sample(BoilerField::selectedFlow);
        // A burner pause can coexist with a pending positive demand. Baseline,
        // completion and fault recovery require explicit zero selection too.
        return feedbackValid(monitor, now) && cv.observedMs > after && power.observedMs > after
            && *cv.raw == 0 && *power.raw == 0 && fresh(selected, now)
            && selected.quality == BoilerQuality::reported && selected.sourceType == 0x18
            && selected.observedMs > after && *selected.raw == 0;
    }
    void enter(Phase phase, const char* reason, uint64_t now) {
        phase_ = phase; reason_ = reason; phaseAt_ = now; ++epoch_;
        zeroSent_ = false; stopConfirmed_ = false; sent_ = false;
        if (phase == Phase::baseline) { started_ = false; heatUntil_ = 0; }
    }
    void fail(const char* reason) {
        if (phase_ != Phase::fault) {
            if (!*endReason_) endReason_ = reason; // retain an earlier operator/deadline stop
            phase_ = Phase::fault; reason_ = reason; ++epoch_;
            zeroSent_ = false; stopConfirmed_ = false; sent_ = false;
        }
    }
    uint64_t boot_ = 0, session_ = 0, epoch_ = 0, phaseAt_ = 0, lastNow_ = 0;
    uint64_t heatUntil_ = 0, operatorUntil_ = 0, sentAt_ = 0, zeroSentAt_ = 0;
    Profile profile_;
    Phase phase_ = Phase::idle;
    const char* reason_ = "not_prepared";
    uint8_t flowC_ = 0;
    uint32_t heatMs_ = 0;
    bool zeroOnly_ = false;
    bool haveTime_ = false, started_ = false, sent_ = false, zeroSent_ = false, stopConfirmed_ = false;
    std::optional<uint64_t> firstPositiveAt_;
    bool selectedReported_ = false, heatingReported_ = false, durationCompleted_ = false;
    const char* endReason_ = "";
    bool inFlight_ = false;
    Intent pending_;
    uint64_t beganAt_ = 0;
};

} // namespace heating::ems
