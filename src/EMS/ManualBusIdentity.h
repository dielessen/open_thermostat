#pragma once
#include "ClassicBoilerTestEncoder.h"

namespace heating::ems {
// Absence of a conflict is never proof that an address is free. The reviewed
// address still needs installation handover; this only removes authority.
struct ManualBusIdentity {
    static bool matches(const ClassicBoilerTestEncoder::Addressing& reviewed,
                        uint8_t controller, uint8_t observedMask, bool conflict) {
        return !conflict && reviewed.valid() && reviewed.source == controller
            && reviewed.sourceMask == observedMask;
    }
    // Includes CRC, excludes BREAK. Called by the RX owner before queueing:
    // delayed diagnostic decoding must not postpone a known address conflict.
    // Exact local transmit echoes are already consumed by the synchronous writer.
    static bool conflictingSource(const uint8_t* frame, size_t length, uint8_t controller) {
        if (!frame || length < 5 || length > 32
            || !controller || controller > 0x7f || (frame[0] & 0x7f) != controller) return false;
        return frame[length - 1] == EmsTelegram::calculateCRC(frame, static_cast<uint8_t>(length - 1));
    }
};
}
