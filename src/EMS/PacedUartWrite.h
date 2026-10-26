#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::ems {

// Existing HT3 pacing only. This is not a reviewed Classic installation mode.
// Success means checked SDK submission, idle observation and BREAK restoration;
// it does not prove an electrical waveform, bus acknowledgement or boiler action.
struct PacedUartWrite {
    static constexpr size_t maximumFrameSize = 33;
    static constexpr uint32_t byteDelayUs = 104 * 17;
    static constexpr uint32_t breakDelayUs = 104 * 11;

    template<bool Enabled, class IO>
    static bool write(const uint8_t* data, size_t length, IO& io) {
        if constexpr (!Enabled) {
            return false;
        } else {
            if (!data || !length || length > maximumFrameSize) return false;
            for (size_t i = 0; i < length; ++i) {
                if (io.writeByte(data[i]) != 1) return false;
                io.delayUs(byteDelayUs);
            }
            // Zero-wait SDK probe, not a new unbounded completion wait.
            if (!io.idle()) return false;
            if (!io.invert(true)) {
                // The failed call's physical outcome is unknown. Attempt only
                // the existing normal polarity restoration, never another frame.
                io.invert(false);
                return false;
            }
            io.delayUs(breakDelayUs);
            return io.invert(false);
        }
    }
};

} // namespace heating::ems
