#pragma once
#include "ClassicConfigurationRead.h"
#include <cstdint>
#include <optional>

namespace heating::ems {
// Active heating's ceiling comes from the boiler itself (owner, 29 Oct): the
// E32 asks the Classic boiler for UBAParameters 0x16 (heating enabled and the
// heating temperature, 2 bytes) once after boot and again when no usable 0x16
// report was seen for 6 h, whoever asked. Read-only: the attended
// configuration read's reviewed frame and private transaction, at a poll of
// 0x0B only and never beside the trial, a configuration read, a settings write
// or an active-heat command. An unanswered read is retried after 5 min.
// Review: docs/modern-thermostat/BOILER-LIMIT-READ.en.md. Callers serialize
// all calls (telemetry mutex).
class BoilerLimitRead {
public:
    static constexpr uint32_t refreshMs = 6u * 3600000u, retryMs = 300000;
    explicit BoilerLimitRead(bool compiled) : compiled_(compiled) {}
    // reportedAtMs: the boiler's last usable 0x16 report this boot (ActiveHeatEnvelope).
    bool due(uint64_t now, std::optional<uint64_t> reportedAtMs) const {
        if (!compiled_ || (reportedAtMs && (now < *reportedAtMs || now - *reportedAtMs < refreshMs))) return false;
        return !sent_ || now < attemptAt_ || now - attemptAt_ >= retryMs;
    }
    // At a poll of 0x0B. ready: the reviewed route's gates. True: this poll
    // was used for the read (written or not).
    template<class Ready, class Write>
    bool poll(uint64_t now, std::optional<uint64_t> reportedAtMs, Ready ready, Write write) {
        if (!due(now, reportedAtMs) || !ready()) return false;
        EmsRawFrame frame;
        ClassicConfigurationRead::encode(frame);
        attemptAt_ = now; sent_ = sent_ < UINT32_MAX ? sent_ + 1 : sent_;
        try { if (!write(frame)) ++failed_; } catch (...) { ++failed_; }
        return true;
    }
    uint32_t sent() const { return sent_; }     // read requests attempted this boot
    uint32_t failed() const { return failed_; } // of which the write failed

private:
    bool compiled_;
    uint64_t attemptAt_ = 0;
    uint32_t sent_ = 0, failed_ = 0;
};
}
