#pragma once

#include "BoilerCapabilities.h"
#include <array>
#include <cstdint>
#include <cstddef>
#include <ostream>

namespace heating::ems {

// Metadata only: never retain payloads, allocate per packet, or infer support
// from silence. Filled by the monitor after its boiler-source/read filter.
class BoilerTelegramInventory {
public:
    static constexpr size_t capacity = 24;
    void observe(uint16_t type, uint8_t offset, size_t size, uint64_t now) {
        Entry *entry = nullptr;
        for (size_t i = 0; i < used_; ++i)
            if (entries_[i].type == type) { entry = &entries_[i]; break; }
        if (!entry) {
            if (used_ == capacity) { increment(untracked_); return; }
            entry = &entries_[used_++];
            entry->type = type;
        }
        increment(entry->frames);
        entry->offset = offset;
        entry->size = static_cast<uint16_t>(size);
        entry->observedMs = now;
    }
    void writeJSON(std::ostream &ss, uint64_t now) const {
        ss << "{\"capacity\":" << capacity << ",\"untracked_frames\":" << untracked_ << ",\"types\":[";
        for (size_t i = 0; i < used_; ++i) {
            if (i) ss << ',';
            const auto &e = entries_[i];
            const auto family = BoilerCapabilities::family(e.type);
            const char *decoder = family == BoilerProtocol::classic ? "classic_fields"
                : family == BoilerProtocol::plus ? "plus_legacy_fields" : "unmapped";
            ss << "{\"type\":" << e.type << ",\"frames\":" << e.frames
               << ",\"last_offset\":" << unsigned(e.offset) << ",\"last_payload_bytes\":" << e.size
               << ",\"decoder\":\"" << decoder << "\",\"age_ms\":";
            if (now >= e.observedMs) ss << now - e.observedMs; else ss << "null";
            ss << '}';
        }
        ss << "]}";
    }
private:
    struct Entry {
        uint16_t type = 0, size = 0;
        uint8_t offset = 0;
        uint64_t frames = 0, observedMs = 0;
    };
    static void increment(uint64_t &value) { if (value != UINT64_MAX) ++value; }
    std::array<Entry, capacity> entries_{};
    size_t used_ = 0;
    uint64_t untracked_ = 0;
};
}
