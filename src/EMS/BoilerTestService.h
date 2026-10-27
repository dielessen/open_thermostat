#pragma once
#include "BoilerTestSession.h"
#include "ClassicHeatTrialEnvelope.h"
#include "control/BoundedJson.h"
#include "control/WebAuthSession.h"
#include <array>
#include <algorithm>
#include <cstring>
#include <initializer_list>
#include <ostream>
#include <string_view>

namespace heating::ems {

// Existing authenticated HTTP owner -> the SAME finite session policy. No
// profile selection, GPIO, UART callback, persistence or implicit TX unlock.
// All methods must be serialized by its owner. A future reviewed poll driver
// must also use that owner when selecting/checking/recording real transmission.
class BoilerTestService {
public:
    static constexpr uint32_t maximumRevision = 2147483647;
    struct Result { int http; const char* error; bool duplicate = false; };
    BoilerTestService(uint64_t boot, bool transmitCompiled,
                      BoilerTestSession::Profile profile = {}, bool driverAttached = false,
                      bool requireSiteConfirmation = false, bool requirePressureConfirmation = false,
                      bool requirePressureReading = false)
        : boot_(boot), transmitCompiled_(transmitCompiled), profile_(profile),
          driverAttached_(driverAttached), requireSiteConfirmation_(requireSiteConfirmation || requirePressureConfirmation || requirePressureReading),
          requirePressureConfirmation_(requirePressureConfirmation || requirePressureReading),
          requirePressureReading_(requirePressureReading), session_(boot, profile) {}
    static constexpr uint32_t minimumManualPressureDecibar = ClassicHeatTrialEnvelope::minimumPressureDecibar + 1;
    static constexpr uint32_t maximumManualPressureDecibar = ClassicHeatTrialEnvelope::maximumPressureDecibar;
    static constexpr uint64_t manualPressureLifetimeMs = 120000;
    uint64_t bootId() const { return boot_; }
    bool active() const { return session_.active(); }
    bool heating() const { return session_.phase() == BoilerTestSession::Phase::heating; }
    void transportFault(uint64_t now) {
        const auto before = marker();
        session_.transportFault(now);
        if (marker() != before) ++stateSequence_;
    }

    void tick(uint64_t now, const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        session_.step(now, effective(gates, now), monitor);
        if (marker() != before) ++stateSequence_;
    }
    Result action(std::string_view action, std::string_view body, std::string_view owner,
                  uint64_t now, const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        // Only a previously authenticated, CSRF-checked boot-local HTTP session
        // may call this API. The cookie is bound privately and NEVER published.
        if (!control::WebAuthSession::hexToken(owner)) return {401, "authentication_required"};
        if (body.size() > (requirePressureReading_ ? 384u : 256u)) return {400, "invalid_request"};
        const auto document = control::parseControlJson(body);
        const auto* json = document.get();
        const bool zeroOnly = action == "prepare_zero";
        const bool preparingHeat = action == "prepare";
        const bool preparing = preparingHeat || zeroOnly;
        const bool closing = action == "close_fault";
        if (!preparing && !closing && action != "start" && action != "keepalive" && action != "stop") return {404, "unknown_action"};
        const bool validKeys = closing ? exactKeys(json, {"schema", "boot_id", "revision", "local_stop_confirmed"})
            : preparing && requireSiteConfirmation_
            ? (preparingHeat ? (requirePressureReading_
                               ? exactKeys(json, {"schema", "boot_id", "revision", "flow_c", "duration_s", "exclusive_owner_confirmed", "independent_stop_confirmed", "heat_path_confirmed", "pressure_check_confirmed", "pressure_decibar"})
                               : requirePressureConfirmation_
                               ? exactKeys(json, {"schema", "boot_id", "revision", "flow_c", "duration_s", "exclusive_owner_confirmed", "independent_stop_confirmed", "heat_path_confirmed", "pressure_check_confirmed"})
                               : exactKeys(json, {"schema", "boot_id", "revision", "flow_c", "duration_s", "exclusive_owner_confirmed", "independent_stop_confirmed", "heat_path_confirmed"}))
                             : exactKeys(json, {"schema", "boot_id", "revision", "exclusive_owner_confirmed", "independent_stop_confirmed"}))
            : (preparingHeat ? exactKeys(json, {"schema", "boot_id", "revision", "flow_c", "duration_s"})
                             : exactKeys(json, {"schema", "boot_id", "revision"}));
        if (!validKeys
            || !integer(json, "schema", 1, 1) || !integer(json, "revision", 1, maximumRevision)) return {400, "invalid_request"};
        if (closing && !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "local_stop_confirmed"))) return {400, "invalid_request"};
        if (preparing && requireSiteConfirmation_
            && (!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "exclusive_owner_confirmed"))
                || !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "independent_stop_confirmed"))
                || (preparingHeat && !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "heat_path_confirmed")))))
            return {400, "site_confirmation_required"};
        if (preparingHeat && requirePressureConfirmation_
            && !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "pressure_check_confirmed")))
            return {400, "pressure_confirmation_required"};
        if (preparingHeat && requirePressureReading_
            && !integer(json, "pressure_decibar", minimumManualPressureDecibar, maximumManualPressureDecibar))
            return {400, "pressure_outside_trial_limits"};
        const auto* boot = cJSON_GetObjectItemCaseSensitive(json, "boot_id");
        if (!cJSON_IsString(boot) || std::string_view(boot->valuestring) != bootText()) return {409, "boot_changed"};
        const auto revision = static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "revision")->valuedouble);
        uint8_t flow = 0; uint32_t durationMs = 0;
        if (preparingHeat) {
            if (!integer(json, "flow_c", 5, 90) || !integer(json, "duration_s", 1, BoilerTestSession::maximumTrialMs / 1000)) return {400, "invalid_request"};
            flow = static_cast<uint8_t>(cJSON_GetObjectItemCaseSensitive(json, "flow_c")->valuedouble);
            durationMs = static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "duration_s")->valuedouble) * 1000;
        }
        if (preparing) {
            if (revision == revision_) {
                if (!owned(owner)) return {403, "different_operator"};
                const bool samePressure = zeroOnly || !requirePressureReading_
                    || (pressureDecibar_ && *pressureDecibar_ == static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "pressure_decibar")->valuedouble));
                return zeroOnly == session_.zeroOnly() && flow == flow_ && durationMs == durationMs_ && samePressure
                    ? Result{200, "", true} : Result{409, "request_changed"};
            }
            if (revision_ == maximumRevision || revision != revision_ + 1) return {409, "revision_changed"};
        } else {
            if (revision != revision_ || !revision_) return {409, "revision_changed"};
            // An authenticated operator can always request withdrawal of the
            // CURRENT session, but cannot start or renew somebody else's test.
            if (action != "stop" && !closing && !owned(owner)) return {403, "different_operator"};
        }
        auto admitted = effective(gates, now, preparing);
        if (closing) {
            if (session_.phase() == BoilerTestSession::Phase::closed) return {200, "", true};
            const auto before = marker();
            const bool closed = session_.closeFault(now, admitted, monitor);
            if (marker() != before) ++stateSequence_;
            if (!closed) return {409, "reported_stop_required"};
            siteConfirmed_ = heatPathConfirmed_ = pressureConfirmed_ = false;
            return {202, ""};
        }
        if (action == "stop") {
            if (!session_.active()) return {409, "test_not_active"};
            session_.stop(now);
            ++stateSequence_;
            return {202, ""}; // request accepted, NEVER a reported stop proof
        }
        if (const auto* blocked = blockedReason(gates, now, zeroOnly || (!preparing && session_.zeroOnly()), preparing)) return {409, blocked};
        if (preparing) {
            const auto reply = session_.prepare(boot_, revision, flow, durationMs, now, admitted, monitor, zeroOnly);
            if (reply == BoilerTestSession::Reply::refused) return {409, "proving_conditions_missing"};
            revision_ = revision; flow_ = flow; durationMs_ = durationMs;
            // Store only after successful preparation, privately in this boot
            // and session. A new preparation must submit its declarations again.
            siteConfirmed_ = requireSiteConfirmation_;
            heatPathConfirmed_ = requireSiteConfirmation_ && preparingHeat;
            pressureConfirmed_ = requirePressureConfirmation_ && preparingHeat;
            pressureDecibar_ = preparingHeat && requirePressureReading_
                ? std::optional<uint32_t>(static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "pressure_decibar")->valuedouble))
                : std::nullopt;
            pressureDeclaredAt_ = now;
            std::copy(owner.begin(), owner.end(), owner_.begin()); owner_[64] = 0;
            positiveFrames_ = zeroFrames_ = 0;
            ++stateSequence_;
            return {202, ""};
        }
        if (action == "start") {
            ++stateSequence_;
            const auto reply = session_.start(boot_, revision, now, admitted, monitor);
            if (reply == BoilerTestSession::Reply::refused) return {409, "proving_conditions_missing"};
            return {reply == BoilerTestSession::Reply::duplicate ? 200 : 202, "", reply == BoilerTestSession::Reply::duplicate};
        }
        ++stateSequence_;
        session_.step(now, admitted, monitor);
        return session_.keepAlive(boot_, revision, now) ? Result{202, ""} : Result{409, "operator_lease_expired"};
    }

    BoilerTestSession::Intent next(uint64_t now, const BoilerTestSession::Gates& gates,
                                  const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const auto intent = session_.next(now, effective(gates, now), monitor);
        if (marker() != before) ++stateSequence_;
        return intent;
    }
    bool mayTransmit(const BoilerTestSession::Intent& intent, uint64_t now,
                     const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool allowed = session_.mayTransmit(intent, now, effective(gates, now), monitor);
        if (marker() != before) ++stateSequence_;
        return allowed;
    }
    bool beginTransmit(const BoilerTestSession::Intent& intent, uint64_t now,
                       const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool began = session_.beginTransmit(intent, now, effective(gates, now), monitor);
        if (began || marker() != before) ++stateSequence_;
        return began;
    }
    bool finishTransmit(const BoilerTestSession::Intent& intent, uint64_t now, bool success,
                        const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool wasInFlight = session_.transmissionInFlight();
        if (!session_.finishTransmit(intent, now, success, effective(gates, now), monitor)) {
            if (marker() != before || wasInFlight != session_.transmissionInFlight()) ++stateSequence_;
            return false;
        }
        ++stateSequence_;
        if (intent.command == BoilerTestSession::Command::positive) ++positiveFrames_; else ++zeroFrames_;
        return true;
    }
    void writeCommandJSON(std::ostream& out, uint64_t now) const {
        const auto& value = session_.lastTransmittedRequest();
        const bool known = value && value->completedAtMs <= now;
        out << "{\"schema\":1,\"profile_id\":\"ecomline-classic-separate-pressure-v1\",\"source\":\"controller_uart_transmit\",\"boot_id\":\"";
        static constexpr char hex[]="0123456789abcdef";
        for (int shift=60;shift>=0;shift-=4) out << hex[(boot_>>shift)&15];
        out << "\",\"observed_at_ms\":" << now << ",\"known\":" << (known?"true":"false")
            << ",\"boiler_readback\":false,\"value_c\":";
        if (known) out << static_cast<unsigned>(value->flowC); else out << "null";
        out << ",\"emitted_at_ms\":";
        if (known) out << value->completedAtMs; else out << "null";
        out << ",\"sequence\":" << (known?value->sequence:0) << '}';
    }
    void writeJSON(std::ostream& out, uint64_t now, std::string_view owner,
                   const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) const {
        const auto* blocked = blockedReason(gates, now, false, true); const auto admitted = effective(gates, now);
        const auto preparationGates = effective(gates, now, true);
        const bool isOwner = owned(owner);
        const bool zeroAvailable = !blockedReason(gates, now, true, true);
        out << "{\"schema\":1,\"boot_id\":\"" << bootText() << "\",\"revision\":" << revision_
            << ",\"state_sequence\":" << stateSequence_ << ",\"observed_at_ms\":" << now
            << ",\"available\":" << (blocked ? "false" : "true")
            << ",\"site_confirmation_required\":" << (requireSiteConfirmation_ ? "true" : "false")
            << ",\"pressure_check_required\":" << (requirePressureConfirmation_ ? "true" : "false")
            << ",\"pressure_check_confirmed\":" << (pressureConfirmed_ ? "true" : "false")
            << ",\"can_close_fault\":" << (session_.canCloseFault(now, admitted, monitor) ? "true" : "false")
            << ",\"restart_required\":" << (session_.phase() == BoilerTestSession::Phase::closed ? "true" : "false")
            << ",\"zero_test_available\":" << (zeroAvailable ? "true" : "false")
            << ",\"can_prepare_zero\":" << (zeroAvailable && revision_ < maximumRevision && session_.canPrepare(now, preparationGates, monitor, true) ? "true" : "false")
            << ",\"zero_only\":" << (session_.zeroOnly() ? "true" : "false")
            << ",\"operator_lease_ms\":" << (profile_.validForZero() ? profile_.operatorLeaseMs : 0)
            << ",\"blocked_reason\":\"" << (blocked ? blocked : "")
            << "\",\"phase\":\"" << phaseName(session_.phase()) << "\",\"reason\":\"" << session_.reason()
            << "\",\"owned\":" << (isOwner ? "true" : "false")
            << ",\"can_prepare\":" << (!blocked && revision_ < maximumRevision && session_.canPrepare(now, preparationGates, monitor) ? "true" : "false")
            << ",\"can_start\":" << (!blocked && isOwner && session_.canStart(now, admitted, monitor) ? "true" : "false")
            << ",\"can_stop\":" << (revision_ && session_.active() && session_.phase() != BoilerTestSession::Phase::completed ? "true" : "false")
            << ",\"transmission_in_flight\":" << (session_.transmissionInFlight() ? "true" : "false")
            << ",\"clock\":\"boot_monotonic_ms\",\"stop_reference_emitted_at_ms\":";
        if (const auto reference = session_.stopReferenceMs()) out << *reference; else out << "null";
        out << ",\"reported_stop_confirmed\":" << (session_.reportedStopConfirmed() ? "true" : "false")
            << ",\"progress\":{\"schema\":1,\"requested_temperature_reported\":" << (session_.requestedTemperatureReported() ? "true" : "false")
            << ",\"heating_operation_reported\":" << (session_.heatingOperationReported() ? "true" : "false")
            << ",\"duration_completed\":" << (session_.durationCompleted() ? "true" : "false")
            << ",\"requested_duration_s\":" << session_.requestedDurationSeconds()
            << ",\"end_reason\":\"" << session_.endReason() << "\"}"
            << ",\"positive_frames\":" << positiveFrames_ << ",\"zero_frames\":" << zeroFrames_
            << ",\"operator_remaining_ms\":" << remaining(session_.operatorDeadline(), now)
            << ",\"heat_remaining_ms\":" << (session_.phase() == BoilerTestSession::Phase::heating ? remaining(session_.heatDeadline(), now) : 0)
            << ",\"requested_flow_c\":";
        if (revision_ && !session_.zeroOnly()) out << static_cast<unsigned>(flow_); else out << "null";
        out << ",\"limits\":";
        if (!profile_.valid()) out << "null";
        else out << "{\"minimum_flow_c\":" << static_cast<unsigned>(profile_.minimumFlowC)
                 << ",\"maximum_flow_c\":" << static_cast<unsigned>(profile_.maximumFlowC)
                 << ",\"maximum_duration_s\":" << profile_.maximumHeatMs / 1000
                 << ",\"operator_lease_ms\":" << profile_.operatorLeaseMs << '}';
        out << ",\"pressure_reading_required\":" << (requirePressureReading_ ? "true" : "false")
            << ",\"pressure_reading_limits\":";
        if (requirePressureReading_) out << "{\"minimum_decibar\":" << minimumManualPressureDecibar
            << ",\"maximum_decibar\":" << maximumManualPressureDecibar << '}';
        else out << "null";
        out << ",\"operator_pressure_observation\":";
        if (pressureDecibar_) out << "{\"source\":\"operator_boiler_gauge\",\"value_decibar\":" << *pressureDecibar_
            << ",\"declared_at_ms\":" << pressureDeclaredAt_ << ",\"maximum_age_ms\":" << pressureLifetimeMs()
            << ",\"physical_validation\":false}";
        else out << "null";
        out << ",\"physical_validation\":false}";
    }

private:
    uint64_t pressureLifetimeMs() const {
        // A fresh declaration is mandatory for every preparation/start. Keep
        // that declaration for the finite attended run; keepalives cannot renew
        // it or extend the independent heat deadline.
        return manualPressureLifetimeMs + (heating() ? durationMs_ : 0);
    }
    unsigned marker() const {
        return static_cast<unsigned>(session_.phase()) * 16 + session_.reportedStopConfirmed()
            + session_.requestedTemperatureReported() * 2 + session_.heatingOperationReported() * 4
            + session_.durationCompleted() * 8;
    }
    static uint64_t remaining(uint64_t until, uint64_t now) { return until > now ? until - now : 0; }
    std::string bootText() const {
        std::string result(16, '0'); auto value = boot_;
        for (int i = 15; i >= 0; --i) { result[i] = "0123456789abcdef"[value & 15]; value >>= 4; }
        return result;
    }
    bool owned(std::string_view owner) const {
        return revision_ && control::WebAuthSession::hexToken(owner)
            && control::WebAuthSession::equal(owner, std::string_view(owner_.data(), 64));
    }
    BoilerTestSession::Gates effective(BoilerTestSession::Gates gates, uint64_t now, bool preparation = false) const {
        gates.transmitterReviewed = gates.transmitterReviewed && transmitCompiled_ && driverAttached_;
        if (requireSiteConfirmation_) {
            // These are operator declarations for this finite manual trial,
            // never automatic sensor proof or an installation qualification.
            gates.exclusiveOwner = preparation || siteConfirmed_;
            gates.independentStopAvailable = preparation || siteConfirmed_;
            gates.pathReady = gates.pathReady && (preparation || heatPathConfirmed_);
        }
        if (requirePressureConfirmation_)
            gates.limitsSafe = gates.limitsSafe && (preparation || pressureConfirmed_);
        if (requirePressureReading_)
            gates.limitsSafe = gates.limitsSafe && (preparation || (pressureDecibar_ && now >= pressureDeclaredAt_
                && now - pressureDeclaredAt_ < pressureLifetimeMs()));
        return gates;
    }
    const char* blockedReason(const BoilerTestSession::Gates& gates, uint64_t now, bool zeroOnly = false, bool preparation = false) const {
        if (!boot_) return "boot_unavailable";
        if (session_.phase() == BoilerTestSession::Phase::closed) return "restart_required";
        if (!transmitCompiled_) return "transmit_blocked";
        if (!(zeroOnly ? profile_.validForZero() : profile_.valid())) return "profile_missing";
        if (!driverAttached_) return "test_transport_missing";
        const auto admitted = effective(gates, now, preparation);
        if (!(zeroOnly ? admitted.allowsZero() && admitted.independentStopAvailable : admitted.allowsHeat())) return "proving_conditions_missing";
        return nullptr;
    }
    static bool exactKeys(const cJSON* object, std::initializer_list<const char*> keys) {
        if (!cJSON_IsObject(object) || cJSON_GetArraySize(object) != static_cast<int>(keys.size())) return false;
        for (auto key : keys) if (!cJSON_GetObjectItemCaseSensitive(object, key)) return false;
        return true;
    }
    static bool integer(const cJSON* object, const char* key, uint32_t minimum, uint32_t maximum) {
        const auto* value = cJSON_GetObjectItemCaseSensitive(object, key);
        return cJSON_IsNumber(value) && value->valuedouble >= minimum && value->valuedouble <= maximum
            && std::floor(value->valuedouble) == value->valuedouble;
    }
    static const char* phaseName(BoilerTestSession::Phase phase) {
        switch (phase) {
            case BoilerTestSession::Phase::baseline: return "baseline";
            case BoilerTestSession::Phase::ready: return "ready";
            case BoilerTestSession::Phase::heating: return "heating";
            case BoilerTestSession::Phase::stopping: return "stopping";
            case BoilerTestSession::Phase::completed: return "completed";
            case BoilerTestSession::Phase::fault: return "fault";
            case BoilerTestSession::Phase::closed: return "closed";
            default: return "idle";
        }
    }
    uint64_t boot_;
    bool transmitCompiled_;
    BoilerTestSession::Profile profile_;
    bool driverAttached_;
    bool requireSiteConfirmation_, siteConfirmed_ = false, heatPathConfirmed_ = false;
    bool requirePressureConfirmation_, pressureConfirmed_ = false;
    bool requirePressureReading_ = false;
    std::optional<uint32_t> pressureDecibar_;
    uint64_t pressureDeclaredAt_ = 0;
    BoilerTestSession session_;
    uint32_t revision_ = 0, durationMs_ = 0;
    uint64_t positiveFrames_ = 0, zeroFrames_ = 0;
    uint64_t stateSequence_ = 0;
    uint8_t flow_ = 0;
    std::array<char, 65> owner_{};
};
} // namespace heating::ems
