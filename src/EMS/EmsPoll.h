#pragma once
#include <cstdint>

namespace heating::ems {
// EMS-bus: polls invert the source-address MSB convention. Callers must
// establish that convention from a CRC-validated boiler broadcast first.
// Recognition grants no permission to transmit.
struct EmsPoll {
    static constexpr uint8_t unknown = 0xff;
    static constexpr bool addressed(uint8_t wire, uint8_t address, uint8_t sourceMask) {
        return address > 0 && address < 0x80
            && (sourceMask == 0 || sourceMask == 0x80)
            && wire == static_cast<uint8_t>(address | (sourceMask ^ 0x80));
    }
};
}
