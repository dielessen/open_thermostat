#pragma once
#include "BoilerTestSession.h"
#include "EmsFrameQueue.h"

namespace heating::ems {

// UBASetPoints (0x1A), offset 0, ONE flow-temperature byte. No burner-power,
// DHW, persistent enable/maximum-temperature or generic EMS+ settings write.
// Protocol reference: EMS-ESP32 v3.8.4 boiler.cpp blob
// 1c40b9ff3556213cbde213ac9e7e8563ec75de7a, set_flow_temp.
// This fixed frame implementation uses our existing checksum, no copied sender.
class ClassicBoilerTestEncoder {
public:
    struct Addressing {
        bool reviewed = false;
        uint8_t source = 0, boiler = 0, sourceMask = 0xFF;
        // EMS-ESP's documented service-key identity for non-Junkers Classic.
        // Protocol choice only: does not prove a free address or grant TX.
        static constexpr Addressing classicService() { return {true, 0x0B, 0x08, 0}; }
        bool valid() const {
            return reviewed && source > 0 && source <= 0x7F && source != boiler
                && boiler == 0x08 && (sourceMask == 0 || sourceMask == 0x80);
        }
    };

    // Independent wire-to-intent comparison. A correct CRC is not evidence
    // that a different setpoint or destination was admitted by the policy.
    static bool matches(const Addressing& addressing, const BoilerTestSession::Intent& intent,
                        const EmsRawFrame& frame) {
        using Command = BoilerTestSession::Command;
        if (!addressing.valid() || !intent.boot || !intent.session || !intent.epoch || frame.length != 6)
            return false;
        if (intent.command == Command::zero) {
            if (intent.flowC != 0 || intent.expiresAt != 0) return false;
        } else if (intent.command == Command::positive) {
            if (intent.flowC < 5 || intent.flowC > 90 || !intent.expiresAt) return false;
        } else return false;
        return frame.data[0] == (addressing.source | addressing.sourceMask)
            && frame.data[1] == addressing.boiler && frame.data[2] == 0x1A
            && frame.data[3] == 0 && frame.data[4] == intent.flowC
            && frame.data[5] == EmsTelegram::calculateCRC(frame.data.data(), 5);
    }

    static bool encode(const Addressing& addressing, const BoilerTestSession::Intent& intent,
                       EmsRawFrame& frame) {
        frame = {}; // A refused encoding never leaves earlier bytes dispatchable.
        using Command = BoilerTestSession::Command;
        if (!addressing.valid() || !intent.boot || !intent.session || !intent.epoch) return false;
        if (intent.command == Command::zero) {
            if (intent.flowC != 0 || intent.expiresAt != 0) return false;
        } else if (intent.command == Command::positive) {
            if (intent.flowC < 5 || intent.flowC > 90 || !intent.expiresAt) return false;
        } else return false;
        // Source MSB comes ONLY from explicit reviewed addressing. Neither a
        // Classic report nor the legacy encoder's unconditional MSB selects it.
        frame.data[0] = addressing.source | addressing.sourceMask;
        frame.data[1] = addressing.boiler;
        frame.data[2] = 0x1A;
        frame.data[3] = 0;
        frame.data[4] = intent.flowC;
        frame.data[5] = EmsTelegram::calculateCRC(frame.data.data(), 5);
        frame.length = 6; // includes CRC, excludes electrical BREAK
        return true;
    }
};

} // namespace heating::ems
