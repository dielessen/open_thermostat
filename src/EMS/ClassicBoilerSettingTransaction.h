#pragma once
#include "ClassicBoilerSettingsEncoder.h"
#include <cstdint>
#include <limits>

namespace heating::ems {
// Boot-local, one-shot persistent setting transaction. No UART/HTTP registration.
// The caller owns authentication, reviewed model capabilities and exclusive bus
// ownership. Its gate must remain true throughout the transaction. No retries.
class ClassicBoilerSettingTransaction {
public:
    using Setting = ClassicBoilerSettingsEncoder::Setting;
    enum class Phase { idle, queuedWrite, waitingWriteStatus, queuedRead, waitingResponse, completed, failed };
    enum class Admission { accepted, duplicate, rejected };
    struct Request {
        uint64_t boot, owner;
        uint32_t revision;
        Setting setting;
        int value;
        bool exclusiveOwnerConfirmed, independentStopConfirmed;
    };
    static constexpr uint64_t pollTimeoutMs = 5000, responseTimeoutMs = 15000;
    static constexpr uint64_t writeStatusTimeoutMs = 200;
    static constexpr uint64_t cooldownMs = 30000;
    explicit ClassicBoilerSettingTransaction(uint64_t boot, bool compiled = false)
        : boot_(boot), compiled_(compiled) {}
    Phase phase() const { return phase_; }
    uint32_t revision() const { return request_.revision; }
    const char* reason() const { return reason_; }
    bool writeAttempted() const { return writeAttempted_; }
    uint64_t responseAt() const { return responseAt_; }
    bool active() const {
        return phase_ == Phase::queuedWrite || phase_ == Phase::waitingWriteStatus || phase_ == Phase::queuedRead || phase_ == Phase::waitingResponse;
    }
    bool available(uint64_t now, bool permitted) const {
        return compiled_ && boot_ && permitted && !inFlight_ && !active()
            && request_.revision < std::numeric_limits<uint32_t>::max()
            && (!request_.revision || (now >= lastNow_ && now >= armedAt_ && now - armedAt_ >= cooldownMs));
    }
    Admission request(const Request& next, uint64_t now, bool permitted) {
        // Owner is an internal authenticated session identity, never a raw HTTP
        // parameter. Duplicate requests cannot alter intent or renew deadlines.
        if (inFlight_ || !compiled_ || !boot_ || next.boot != boot_ || !next.owner
            || !next.exclusiveOwnerConfirmed || !next.independentStopConfirmed)
            return Admission::rejected;
        if (next.revision && next.revision == request_.revision) {
            return next.owner == request_.owner && next.setting == request_.setting
                && next.value == request_.value ? Admission::duplicate : Admission::rejected;
        }
        EmsRawFrame checked;
        if (!permitted || active() || request_.revision == std::numeric_limits<uint32_t>::max()
            || next.revision != request_.revision + 1
            || (request_.revision && (now < lastNow_ || now < armedAt_ || now - armedAt_ < cooldownMs))
            || !ClassicBoilerSettingsEncoder::encode(address(), true, next.setting, next.value, checked))
            return Admission::rejected;
        request_ = next; armedAt_ = lastNow_ = phaseAt_ = now;
        readEmittedAt_ = responseAt_ = 0; writeAttempted_ = false;
        phase_ = Phase::queuedWrite; reason_ = "awaiting_write_poll";
        return Admission::accepted;
    }
    void fail(const char* reason) {
        if (active()) { phase_ = Phase::failed; reason_ = reason; }
    }
    void tick(uint64_t now, bool permitted) {
        if (!active()) return;
        if (now < lastNow_) { fail("clock_changed"); return; }
        lastNow_ = now;
        if (!permitted) { fail("permission_lost"); return; }
        const auto timeout = phase_ == Phase::waitingResponse ? responseTimeoutMs
            : phase_ == Phase::waitingWriteStatus ? writeStatusTimeoutMs : pollTimeoutMs;
        if (now - phaseAt_ >= timeout)
            fail(phase_ == Phase::waitingResponse ? "response_timeout"
                 : phase_ == Phase::waitingWriteStatus ? "write_status_timeout" : "poll_timeout");
    }
    // Called only for an admitted service-address poll. send() returns after
    // emission/echo, never waits for an incoming status on the same UART task.
    // A later verified bus closure calls writeClosed(); a read reply is supplied
    // separately to receive(). Neither echo nor write status proves readback.
    // Even an uncertain/throwing callback is never invoked a second time.
    template<class Clock, class Gate, class Send>
    bool poll(Clock clock, Gate gate, Send send) {
        if (inFlight_) return true;
        if (!active()) return false;
        // Clock and permission callbacks are external code too. Reserve the
        // entire dispatch before invoking them, including the final gate.
        inFlight_ = true;
        struct Release { bool& value; ~Release() { value = false; } } release{inFlight_};
        try {
            const bool initiallyPermitted = gate();
            auto now = clock(); tick(now, initiallyPermitted);
            if (!active() || (phase_ == Phase::waitingResponse || phase_ == Phase::waitingWriteStatus)) return true;
            const bool writing = phase_ == Phase::queuedWrite;
            EmsRawFrame frame;
            if (!ClassicBoilerSettingsEncoder::encode(address(), true, request_.setting, request_.value, frame)) {
                fail("invalid_intent"); return true;
            }
            if (!writing) {
                frame.data[1] = 0x88; frame.data[4] = 1;
                frame.data[5] = EmsTelegram::calculateCRC(frame.data.data(), 5);
            }
            const bool finallyPermitted = gate();
            now = clock(); tick(now, finallyPermitted);
            if (!active()) return true;
            if (writing) writeAttempted_ = true;
            // Retire before external IO so re-entry cannot repeat a command.
            phase_ = Phase::failed; reason_ = "transport_uncertain";
            if (!send(frame)) { reason_ = "transport_failed"; return true; }
            const bool stillPermitted = gate();
            const auto finished = clock();
            if (finished < now) { reason_ = "clock_changed"; return true; }
            if (finished - phaseAt_ >= pollTimeoutMs) { reason_ = "poll_timeout"; return true; }
            if (!stillPermitted) { reason_ = "permission_lost"; return true; }
            lastNow_ = phaseAt_ = finished;
            if (writing) { phase_ = Phase::waitingWriteStatus; reason_ = "awaiting_write_status"; }
            else { readEmittedAt_ = finished; phase_ = Phase::waitingResponse; reason_ = "awaiting_readback"; }
        } catch (...) {
            if (active()) fail("transport_exception");
            else if (phase_ == Phase::failed) reason_ = "transport_exception";
        }
        return true;
    }
    // Only the UART exchange owner may call this after checking the original
    // microsecond RX order, write status and successful completion-byte IO.
    // The revision binds late callbacks to their original request. An accepted
    // status confirms transport only, never that the setting was retained.
    void writeClosed(uint32_t revision, uint64_t now, bool accepted, bool permitted) {
        tick(now, permitted);
        if (phase_ != Phase::waitingWriteStatus || revision != request_.revision) return;
        if (!accepted) { fail("write_rejected"); return; }
        lastNow_ = phaseAt_ = now; phase_ = Phase::queuedRead; reason_ = "awaiting_read_poll";
    }
    void receive(const EmsTelegram& report, uint64_t acquiredAt, uint64_t now, bool permitted) {
        tick(now, permitted);
        if (phase_ != Phase::waitingResponse || acquiredAt <= readEmittedAt_ || acquiredAt > now) return;
        if (!ClassicBoilerSettingsEncoder::readbackMatches(address(), true, request_.setting, request_.value, report))
            return;
        responseAt_ = acquiredAt; phase_ = Phase::completed; reason_ = "setting_read_back";
    }
private:
    static constexpr ClassicBoilerTestEncoder::Addressing address() { return ClassicBoilerTestEncoder::Addressing::classicService(); }
    uint64_t boot_, armedAt_ = 0, lastNow_ = 0, phaseAt_ = 0, readEmittedAt_ = 0, responseAt_ = 0;
    bool compiled_, writeAttempted_ = false, inFlight_ = false;
    Request request_{};
    Phase phase_ = Phase::idle;
    const char* reason_ = "not_requested";
};
} // namespace heating::ems
