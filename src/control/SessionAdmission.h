#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace heating::control {

enum class Direction { ha_to_fw, fw_to_ha };
enum class StreamKind { heartbeat, observation, user_command, actuator_command, actuator_result, configuration };
enum class AdmissionCode {
    accepted, duplicate, not_configured, wrong_version, wrong_identity,
    wrong_revision, unknown_binding, expired_grant, lease_expired,
    old_sequence, changed_duplicate, invalid_sequence, invalid_clock
};
struct Admission { AdmissionCode code; uint64_t originalResult = 0; };
struct SessionIdentity {
    std::string controller, boot, adapter, session;
    uint32_t epoch = 0, revision = 0;
};
struct Envelope {
    uint16_t major = 1;
    StreamKind kind = StreamKind::observation;
    Direction direction = Direction::ha_to_fw;
    std::string_view controller, boot, adapter, session, grant, binding;
    uint32_t epoch = 0, revision = 0, sequence = 0, grantSequence = 0;
    std::array<uint8_t,32> payloadDigest{};
};

// Pure admission primitive. It does NOT authenticate a broker client, persist
// config or apply a device action. Only the authenticated local handshake may
// begin a session; the transport must validate message shape/value before admit.
// Exactly one firmware/adapter runtime owns this object (or supplies its lock).
class SessionAdmission {
public:
    static constexpr std::size_t maximumStreams = 48;
    static constexpr uint32_t maximumGrantMs = 15000;
    explicit SessionAdmission(std::string_view expectedAdapter,
                              Direction direction = Direction::ha_to_fw)
        : expectedAdapter_(validId(expectedAdapter) ? expectedAdapter : ""), direction_(direction) {}

    bool begin(const SessionIdentity &identity, uint32_t leaseMs = 15000) {
        if (expectedAdapter_.empty() || identity.adapter != expectedAdapter_ ||
            !validId(identity.controller) || !validId(identity.boot) || !validId(identity.session) ||
            identity.epoch == 0 || leaseMs == 0 || leaseMs > 60000) return false;
        // Replayed/repeated local admission cannot erase sequence watermarks.
        if (configured_ && identity.boot == identity_.boot && identity.epoch == identity_.epoch &&
            identity.session == identity_.session) return false;
        if (configured_ && identity.boot == identity_.boot && identity.epoch <= identity_.epoch) return false;
        identity_ = identity; leaseMs_ = leaseMs; configured_ = true; transportValid_ = true; grantSequence_ = 0;
        streams_ = {}; grant_.clear(); grantValid_ = false; leaseUntil_ = 0; leaseFrom_ = 0;
        return true;
    }
    bool bind(std::size_t index, std::string_view binding, StreamKind kind) {
        if (!configured_ || !transportValid_ || index >= streams_.size() || !validId(binding)) return false;
        if (streams_[index].bound) return streams_[index].binding == binding && streams_[index].kind == kind;
        for (const auto &s : streams_) if (s.bound && s.binding == binding && s.kind == kind) return false;
        streams_[index].binding = binding; streams_[index].kind = kind; streams_[index].bound = true;
        return true;
    }
    bool issueGrant(std::string_view token, uint32_t grantSequence, uint64_t now, uint32_t durationMs) {
        if (!configured_ || !transportValid_ || !validId(token) || !grantSequence ||
            grantSequence <= grantSequence_ || durationMs == 0 ||
            durationMs > maximumGrantMs || now > UINT64_MAX - durationMs) return false;
        grant_ = token; grantSequence_ = grantSequence; grantFrom_ = now; grantUntil_ = now + durationMs; grantValid_ = true;
        // Rotation deliberately preserves every stream's high-water sequence.
        return true;
    }
    void invalidateTransport() { transportValid_ = false; grantValid_ = false; leaseUntil_ = 0; }
    bool alive(uint64_t now) const {
        return configured_ && transportValid_ && now >= leaseFrom_ && now < leaseUntil_;
    }
    Admission admit(std::size_t streamIndex, const Envelope &e, uint64_t now, uint64_t immutableResult = 0) {
        if (!configured_ || !transportValid_) return {AdmissionCode::not_configured};
        if (e.major != 1) return {AdmissionCode::wrong_version};
        if (e.direction != direction_ || e.controller != identity_.controller || e.boot != identity_.boot ||
            e.adapter != identity_.adapter || e.session != identity_.session || e.epoch != identity_.epoch)
            return {AdmissionCode::wrong_identity};
        if (e.revision != identity_.revision) return {AdmissionCode::wrong_revision};
        if (streamIndex >= streams_.size() || !streams_[streamIndex].bound ||
            streams_[streamIndex].binding != e.binding || streams_[streamIndex].kind != e.kind) return {AdmissionCode::unknown_binding};
        if (!identity_.revision && streams_[streamIndex].kind != StreamKind::heartbeat &&
            streams_[streamIndex].kind != StreamKind::configuration) return {AdmissionCode::wrong_revision};
        if (!grantValid_ || e.grant != grant_ || e.grantSequence != grantSequence_ || now < grantFrom_ || now >= grantUntil_)
            return {AdmissionCode::expired_grant};
        auto &s = streams_[streamIndex];
        if (s.kind != StreamKind::heartbeat && !alive(now)) return {AdmissionCode::lease_expired};
        if (!e.sequence) return {AdmissionCode::invalid_sequence};
        if (e.sequence < s.highWater) return {AdmissionCode::old_sequence};
        if (e.sequence == s.highWater) {
            if (e.payloadDigest != s.digest) return {AdmissionCode::changed_duplicate};
            return {AdmissionCode::duplicate, s.result};
        }
        if (s.kind == StreamKind::heartbeat && now > UINT64_MAX - leaseMs_)
            return {AdmissionCode::invalid_clock};
        s.highWater = e.sequence; s.digest = e.payloadDigest; s.result = immutableResult;
        if (s.kind == StreamKind::heartbeat) { leaseFrom_ = now; leaseUntil_ = now + leaseMs_; }
        return {AdmissionCode::accepted, immutableResult};
    }
    // Source-age normalization can add this conservative delay bound after admission.
    uint64_t grantElapsed(uint64_t now) const {
        return transportValid_ && grantValid_ && now >= grantFrom_ && now < grantUntil_ ? now - grantFrom_ : UINT64_MAX;
    }
    uint64_t grantDeadline(uint64_t now) const {
        return grantElapsed(now) != UINT64_MAX ? grantUntil_ : 0;
    }
    static bool validId(std::string_view s) {
        if (s.empty() || s.size() > 32) return false;
        for (unsigned char c : s)
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '-' || c == '_')) return false;
        return true;
    }
private:
    struct Stream {
        std::string binding;
        StreamKind kind = StreamKind::observation;
        bool bound = false;
        uint32_t highWater = 0;
        std::array<uint8_t,32> digest{};
        uint64_t result = 0;
    };
    std::string expectedAdapter_, grant_;
    Direction direction_;
    SessionIdentity identity_;
    std::array<Stream,maximumStreams> streams_{};
    bool configured_ = false, grantValid_ = false, transportValid_ = false;
    uint32_t grantSequence_ = 0;
    uint32_t leaseMs_ = 15000;
    uint64_t grantFrom_ = 0, grantUntil_ = 0, leaseFrom_ = 0, leaseUntil_ = 0;
};
}
