#pragma once
#include "EmsTelegram.h"
#include <cstdint>
#include <optional>

namespace heating::ems {
// The last UBASetPoints (0x1A) write to the boiler from a master other than
// the E32 (0x0B) or the boiler itself: two controllers must never both ask.
// No expiry; the active guard compares it with the owner's confirmation.
struct ForeignBoilerRequest {
    struct Record { uint8_t address = 0; uint64_t receivedAtMs = 0; };
    std::optional<Record> last;
    void observe(const EmsTelegram& t, uint64_t receivedAtMs) {
        const uint8_t sender = t.getSenderId();
        if (t.getTypeId() != 0x1A || t.getOperationType() != EmsTelegram::WRITE || t.getDestinationId() != 0x08
            || !sender || sender == 0x0B || sender == 0x08) return;
        if (!last || receivedAtMs >= last->receivedAtMs) last = Record{sender, receivedAtMs};
    }
};
}
