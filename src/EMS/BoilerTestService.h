#pragma once
#include "BoilerTestSession.h"
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
                      BoilerTestSession::Profile profile = {}, bool driverAttached = false)
        : boot_(boot), transmitCompiled_(transmitCompiled), profile_(profile),
          driverAttached_(driverAttached), session_(boot, profile) {}
    bool active() const { return session_.active(); }
    void transportFault(uint64_t now) {
        const auto before = marker();
        session_.transportFault(now);
        if (marker() != before) ++stateSequence_;
    }

    void tick(uint64_t now, const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        session_.step(now, effective(gates), monitor);
        if (marker() != before) ++stateSequence_;
    }
    Result action(std::string_view action, std::string_view body, std::string_view owner,
                  uint64_t now, const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        // Only a previously authenticated, CSRF-checked boot-local HTTP session
        // may call this API. The cookie is bound privately and NEVER published.
        if (!control::WebAuthSession::hexToken(owner)) return {401, "authentication_required"};
        if (body.size() > 256) return {400, "invalid_request"};
        const auto document = control::parseControlJson(body);
        const auto* json = document.get();
        const bool preparing = action == "prepare";
        if (!preparing && action != "start" && action != "keepalive" && action != "stop") return {404, "unknown_action"};
        if (!exactKeys(json, preparing ? std::initializer_list<const char*>{"schema", "boot_id", "revision", "flow_c", "duration_s"}
                                      : std::initializer_list<const char*>{"schema", "boot_id", "revision"})
            || !integer(json, "schema", 1, 1) || !integer(json, "revision", 1, maximumRevision)) return {400, "invalid_request"};
        const auto* boot = cJSON_GetObjectItemCaseSensitive(json, "boot_id");
        if (!cJSON_IsString(boot) || std::string_view(boot->valuestring) != bootText()) return {409, "boot_changed"};
        const auto revision = static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "revision")->valuedouble);
        uint8_t flow = 0; uint32_t durationMs = 0;
        if (preparing) {
            if (!integer(json, "flow_c", 5, 90) || !integer(json, "duration_s", 1, 120)) return {400, "invalid_request"};
            flow = static_cast<uint8_t>(cJSON_GetObjectItemCaseSensitive(json, "flow_c")->valuedouble);
            durationMs = static_cast<uint32_t>(cJSON_GetObjectItemCaseSensitive(json, "duration_s")->valuedouble) * 1000;
        }
        if (preparing) {
            if (revision == revision_) {
                if (!owned(owner)) return {403, "different_operator"};
                return flow == flow_ && durationMs == durationMs_ ? Result{200, "", true} : Result{409, "request_changed"};
            }
            if (revision_ == maximumRevision || revision != revision_ + 1) return {409, "revision_changed"};
        } else {
            if (revision != revision_ || !revision_) return {409, "revision_changed"};
            // An authenticated operator can always request withdrawal of the
            // CURRENT session, but cannot start or renew somebody else's test.
            if (action != "stop" && !owned(owner)) return {403, "different_operator"};
        }
        auto admitted = effective(gates);
        if (action == "stop") {
            if (!session_.active()) return {409, "test_not_active"};
            session_.stop(now);
            ++stateSequence_;
            return {202, ""}; // request accepted, NEVER a reported stop proof
        }
        if (const auto* blocked = blockedReason(gates)) return {409, blocked};
        if (preparing) {
            const auto reply = session_.prepare(boot_, revision, flow, durationMs, now, admitted, monitor);
            if (reply == BoilerTestSession::Reply::refused) return {409, "proving_conditions_missing"};
            revision_ = revision; flow_ = flow; durationMs_ = durationMs;
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
        const auto intent = session_.next(now, effective(gates), monitor);
        if (marker() != before) ++stateSequence_;
        return intent;
    }
    bool mayTransmit(const BoilerTestSession::Intent& intent, uint64_t now,
                     const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool allowed = session_.mayTransmit(intent, now, effective(gates), monitor);
        if (marker() != before) ++stateSequence_;
        return allowed;
    }
    bool beginTransmit(const BoilerTestSession::Intent& intent, uint64_t now,
                       const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool began = session_.beginTransmit(intent, now, effective(gates), monitor);
        if (began || marker() != before) ++stateSequence_;
        return began;
    }
    bool finishTransmit(const BoilerTestSession::Intent& intent, uint64_t now, bool success,
                        const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) {
        const auto before = marker();
        const bool wasInFlight = session_.transmissionInFlight();
        if (!session_.finishTransmit(intent, now, success, effective(gates), monitor)) {
            if (marker() != before || wasInFlight != session_.transmissionInFlight()) ++stateSequence_;
            return false;
        }
        ++stateSequence_;
        if (intent.command == BoilerTestSession::Command::positive) ++positiveFrames_; else ++zeroFrames_;
        return true;
    }
    void writeJSON(std::ostream& out, uint64_t now, std::string_view owner,
                   const BoilerTestSession::Gates& gates, const ClassicBoilerMonitor& monitor) const {
        const auto* blocked = blockedReason(gates); const auto admitted = effective(gates);
        const bool isOwner = owned(owner);
        out << "{\"schema\":1,\"boot_id\":\"" << bootText() << "\",\"revision\":" << revision_
            << ",\"state_sequence\":" << stateSequence_ << ",\"observed_at_ms\":" << now
            << ",\"available\":" << (blocked ? "false" : "true")
            << ",\"blocked_reason\":\"" << (blocked ? blocked : "")
            << "\",\"phase\":\"" << phaseName(session_.phase()) << "\",\"reason\":\"" << session_.reason()
            << "\",\"owned\":" << (isOwner ? "true" : "false")
            << ",\"can_prepare\":" << (!blocked && revision_ < maximumRevision && session_.canPrepare(now, admitted, monitor) ? "true" : "false")
            << ",\"can_start\":" << (!blocked && isOwner && session_.canStart(now, admitted, monitor) ? "true" : "false")
            << ",\"can_stop\":" << (revision_ && session_.active() && session_.phase() != BoilerTestSession::Phase::completed ? "true" : "false")
            << ",\"transmission_in_flight\":" << (session_.transmissionInFlight() ? "true" : "false")
            << ",\"reported_stop_confirmed\":" << (session_.reportedStopConfirmed() ? "true" : "false")
            << ",\"positive_frames\":" << positiveFrames_ << ",\"zero_frames\":" << zeroFrames_
            << ",\"operator_remaining_ms\":" << remaining(session_.operatorDeadline(), now)
            << ",\"heat_remaining_ms\":" << (session_.phase() == BoilerTestSession::Phase::heating ? remaining(session_.heatDeadline(), now) : 0)
            << ",\"requested_flow_c\":";
        if (revision_) out << static_cast<unsigned>(flow_); else out << "null";
        out << ",\"limits\":";
        if (!profile_.valid()) out << "null";
        else out << "{\"minimum_flow_c\":" << static_cast<unsigned>(profile_.minimumFlowC)
                 << ",\"maximum_flow_c\":" << static_cast<unsigned>(profile_.maximumFlowC)
                 << ",\"maximum_duration_s\":" << profile_.maximumHeatMs / 1000
                 << ",\"operator_lease_ms\":" << profile_.operatorLeaseMs << '}';
        out << ",\"physical_validation\":false}";
    }

private:
    unsigned marker() const { return static_cast<unsigned>(session_.phase()) * 2 + session_.reportedStopConfirmed(); }
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
    BoilerTestSession::Gates effective(BoilerTestSession::Gates gates) const {
        gates.transmitterReviewed = gates.transmitterReviewed && transmitCompiled_ && driverAttached_;
        return gates;
    }
    const char* blockedReason(const BoilerTestSession::Gates& gates) const {
        if (!boot_) return "boot_unavailable";
        if (!transmitCompiled_) return "transmit_blocked";
        if (!profile_.valid()) return "profile_missing";
        if (!driverAttached_) return "test_transport_missing";
        if (!effective(gates).allowsHeat()) return "proving_conditions_missing";
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
            default: return "idle";
        }
    }
    uint64_t boot_;
    bool transmitCompiled_;
    BoilerTestSession::Profile profile_;
    bool driverAttached_;
    BoilerTestSession session_;
    uint32_t revision_ = 0, durationMs_ = 0;
    uint64_t positiveFrames_ = 0, zeroFrames_ = 0;
    uint64_t stateSequence_ = 0;
    uint8_t flow_ = 0;
    std::array<char, 65> owner_{};
};
} // namespace heating::ems
