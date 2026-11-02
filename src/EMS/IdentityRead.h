#pragma once
#include "ClassicConfigurationRead.h"
#include <array>
#include <cstdint>
#include <optional>

namespace heating::ems {
// Who is on the bus (owner, 1 Nov 2026: "identiteit automatisch"): the E32 asks
// each device it has heard for its version telegram 0x02 once, instead of
// waiting for "Read device identity". Read-only: the reviewed identity read
// frame of the attended configuration read, at a poll of 0x0B only and after
// the 0x16 limit read, so never beside the trial, a configuration read, a
// settings write or an active-heat command. Not before 2 min after boot, one
// request a minute at most, three tries per device (5 min apart); the answer
// fills EmsDeviceInventory passively. Callers serialize all calls (telemetry mutex).
class IdentityRead {
public:
    static constexpr uint32_t bootDelayMs = 120000, spacingMs = 60000, retryMs = 300000;
    static constexpr uint8_t triesPerDevice = 3;
    explicit IdentityRead(bool compiled) : compiled_(compiled) {}
    // target: a heard device without a version yet (EmsDeviceInventory::withoutVersion).
    bool due(uint64_t now, std::optional<uint8_t> target) const {
        if (!compiled_ || !target || *target == 0x0b || !*target || now < bootDelayMs) return false;
        if (lastAt_ && (now < lastAt_ || now - lastAt_ < spacingMs)) return false;
        return wants(now, *target);
    }
    // Not yet asked, or its retry is due; never after three tries.
    bool wants(uint64_t now, uint8_t address) const {
        const auto* t = find(address);
        return !t || (t->tries < triesPerDevice && (now < t->at || now - t->at >= retryMs));
    }
    // At a poll of 0x0B. ready: the reviewed route's gates. True: this poll was used (written or not).
    template<class Ready, class Write>
    bool poll(uint64_t now, std::optional<uint8_t> target, Ready ready, Write write) {
        if (!due(now, target) || !ready()) return false;
        Try* t = find(*target);
        if (!t) {
            if (used_ == tried_.size()) return false; // every slot used this boot
            t = &tried_[used_++]; t->address = *target;
        }
        EmsRawFrame frame;
        ClassicConfigurationRead::encodeIdentity(frame, *target);
        t->at = lastAt_ = now; ++t->tries; sent_ = sent_ < UINT32_MAX ? sent_ + 1 : sent_;
        try { if (!write(frame)) ++failed_; } catch (...) { ++failed_; }
        return true;
    }
    uint32_t sent() const { return sent_; }
    uint32_t failed() const { return failed_; }

private:
    struct Try { uint64_t at = 0; uint8_t address = 0, tries = 0; };
    const Try* find(uint8_t address) const { for (size_t i = 0; i < used_; ++i) if (tried_[i].address == address) return &tried_[i]; return nullptr; }
    Try* find(uint8_t address) { for (size_t i = 0; i < used_; ++i) if (tried_[i].address == address) return &tried_[i]; return nullptr; }
    bool compiled_;
    std::array<Try, 16> tried_{};
    size_t used_ = 0;
    uint64_t lastAt_ = 0;
    uint32_t sent_ = 0, failed_ = 0;
};
}
