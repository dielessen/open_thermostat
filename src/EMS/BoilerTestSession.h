#pragma once

#include "ClassicBoilerMonitor.h"
#include <cstdint>
#include <limits>

namespace heating::ems {

// Pure commissioning policy. No UART/HTTP/HA callbacks and no physical authority.
// The eventual bus owner must serialize all calls including the final send check.
// In particular, selecting this policy cannot unlock Board::emsTransmitAllowed.
class BoilerTestSession {
public:
    enum class Phase { idle, baseline, ready, heating, stopping, completed, fault };
    enum class Command { none, zero, positive };
    enum class Reply { accepted, duplicate, refused };
    enum class StopCause { explicitStop, heatDeadline, provingConditionsLost, operatorLeaseExpired };
    struct Profile {
        bool reviewed = false;
        uint8_t minimumFlowC = 0, maximumFlowC = 0;
        uint32_t maximumHeatMs = 0, stopTimeoutMs = 0, reportTtlMs = 0;
        uint32_t operatorLeaseMs = 0, writeIntervalMs = 0;
        bool valid() const {
            return reviewed && minimumFlowC >= 5 && maximumFlowC > minimumFlowC && maximumFlowC <= 90
                && maximumHeatMs >= 1000 && maximumHeatMs <= 120000
                && stopTimeoutMs >= 1000 && stopTimeoutMs <= 60000
                && reportTtlMs >= 100 && reportTtlMs <= 30000
                && operatorLeaseMs >= 1000 && operatorLeaseMs <= 10000
                && writeIntervalMs >= 100 && writeIntervalMs <= 10000;
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
    bool canPrepare(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) const {
        return !inFlight_ && (!haveTime_ || now >= lastNow_) && boot_ && profile_.valid()
            && (phase_ == Phase::idle || phase_ == Phase::completed)
            && gates.allowsHeat() && feedbackValid(monitor, now)
            && canAdd(now, profile_.stopTimeoutMs) && canAdd(now, profile_.operatorLeaseMs);
    }
    bool canStart(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) const {
        return !inFlight_ && (!haveTime_ || now >= lastNow_) && phase_ == Phase::ready && !started_
            && now < operatorUntil_ && gates.allowsHeat() && feedbackValid(monitor, now)
            && reportedOff(monitor, now, zeroSentAt_) && canAdd(now, heatMs_);
    }
    bool active() const { return inFlight_ || (phase_ != Phase::idle && phase_ != Phase::completed); }

    Reply prepare(uint64_t boot, uint64_t session, uint8_t flowC, uint32_t heatMs,
                  uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        if (!observeTime(now)) return Reply::refused;
        if (boot == boot_ && session && session == session_)
            return flowC == flowC_ && heatMs == heatMs_ ? Reply::duplicate : Reply::refused;
        if (inFlight_ || !boot_ || boot != boot_ || !session || session <= session_
            || (phase_ != Phase::idle && phase_ != Phase::completed)
            || !profile_.valid() || !gates.allowsHeat() || !feedbackValid(monitor, now)
            || flowC < profile_.minimumFlowC || flowC > profile_.maximumFlowC
            || heatMs < 1000 || heatMs > profile_.maximumHeatMs
            || !canAdd(now, profile_.stopTimeoutMs) || !canAdd(now, profile_.operatorLeaseMs))
            return Reply::refused;
        session_ = session; flowC_ = flowC; heatMs_ = heatMs;
        operatorUntil_ = now + profile_.operatorLeaseMs;
        enter(Phase::baseline, "checking_reported_stop", now);
        return Reply::accepted;
    }

    Reply start(uint64_t boot, uint64_t session, uint64_t now,
                const Gates& gates, const ClassicBoilerMonitor& monitor) {
        step(now, gates, monitor);
        if (boot != boot_ || session != session_ || !session) return Reply::refused;
        if (started_) return Reply::duplicate; // never extend or revive, even after completion
        if (inFlight_ || phase_ != Phase::ready || !gates.allowsHeat() || !feedbackValid(monitor, now)
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
        if (phase_ == Phase::idle || phase_ == Phase::completed || phase_ == Phase::fault
            || phase_ == Phase::stopping) return;
        const char* reason = cause == StopCause::explicitStop ? "explicit_stop"
            : cause == StopCause::heatDeadline ? "heat_deadline"
            : cause == StopCause::operatorLeaseExpired ? "operator_lease_expired" : "proving_conditions_lost";
        enter(Phase::stopping, reason, now);
    }

    void step(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        if (!observeTime(now) || phase_ == Phase::idle || phase_ == Phase::completed) return;
        if (phase_ == Phase::fault) {
            if (zeroSent_ && reportedOff(monitor, now, zeroSentAt_)) stopConfirmed_ = true;
            return; // no automatic recovery or new session after a fault
        }
        if (!gates.allowsZero()) { fail("transmitter_or_owner_lost"); return; }
        if (phase_ == Phase::heating && (now >= heatUntil_ || now >= operatorUntil_
            || !gates.allowsHeat() || !feedbackValid(monitor, now))) {
            stop(now, now >= heatUntil_ ? StopCause::heatDeadline : StopCause::provingConditionsLost);
        } else if ((phase_ == Phase::baseline || phase_ == Phase::ready)
            && (now >= operatorUntil_ || !gates.allowsHeat() || !feedbackValid(monitor, now))) {
            stop(now, StopCause::provingConditionsLost);
        }
        if ((phase_ == Phase::baseline || phase_ == Phase::stopping) && zeroSent_
            && reportedOff(monitor, now, zeroSentAt_)) {
            stopConfirmed_ = true;
            if (phase_ == Phase::baseline) {
                phase_ = Phase::ready; reason_ = "reported_stop_baseline_confirmed"; ++epoch_;
            } else { phase_ = Phase::completed; reason_ = "reported_stop_confirmed"; ++epoch_; }
        } else if ((phase_ == Phase::baseline || phase_ == Phase::stopping)
            && now - phaseAt_ >= profile_.stopTimeoutMs) fail("reported_stop_timeout");
    }

    Intent next(uint64_t now, const Gates& gates, const ClassicBoilerMonitor& monitor) {
        step(now, gates, monitor);
        if (inFlight_ || !gates.allowsZero() || !session_) return {};
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
        if (!validTime || intent.epoch != epoch_) return true;
        sent_ = true; sentAt_ = now;
        if (intent.command == Command::zero && !zeroSent_) { zeroSent_ = true; zeroSentAt_ = now; }
        return true;
    }

private:
    static bool canAdd(uint64_t now, uint64_t duration) {
        return now <= std::numeric_limits<uint64_t>::max() - duration;
    }
    bool observeTime(uint64_t now) {
        if (haveTime_ && now < lastNow_) { if (active()) fail("monotonic_clock_reversed"); return false; }
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
    bool reportedOff(const ClassicBoilerMonitor& monitor, uint64_t now, uint64_t after) const {
        const auto& cv = monitor.sample(BoilerField::heatingActive);
        const auto& power = monitor.sample(BoilerField::modulation);
        return feedbackValid(monitor, now) && cv.observedMs > after && power.observedMs > after
            && *cv.raw == 0 && *power.raw == 0;
    }
    void enter(Phase phase, const char* reason, uint64_t now) {
        phase_ = phase; reason_ = reason; phaseAt_ = now; ++epoch_;
        zeroSent_ = false; stopConfirmed_ = false; sent_ = false;
        if (phase == Phase::baseline) { started_ = false; heatUntil_ = 0; }
    }
    void fail(const char* reason) {
        if (phase_ != Phase::fault) {
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
    bool haveTime_ = false, started_ = false, sent_ = false, zeroSent_ = false, stopConfirmed_ = false;
    bool inFlight_ = false;
    Intent pending_;
    uint64_t beganAt_ = 0;
};

} // namespace heating::ems
