#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
namespace heating::ems {
// UART task only. Reads the bytes counted up to one BREAK, like EMS-ESP, and
// never flushes on a bad frame, so the DATA counts stay matched to the buffer.
// A flush racing a byte's DATA event leaves one uncounted byte: every later
// frame then starts with the previous BREAK's 0x00 and loses its own (beta.12,
// 2026-10-28 04:45 UTC, until reboot). No valid EMS frame starts with 0x00, so
// drop it and take this frame's own 0x00 from the buffer, which realigns.
struct BreakFrameReader {
    enum class Result { frame, realigned, empty, shortRead, oversized, misaligned };
    static bool deliverable(Result r) { return r == Result::frame || r == Result::realigned; }

    // io.read(dst,n) returns the bytes available now (never waits).
    template<class IO>
    static Result read(IO& io, uint8_t* buffer, size_t capacity, size_t counted, size_t& size) {
        size = 0;
        if (counted == 0) return Result::empty;
        if (counted > capacity) {
            uint8_t sink[16];
            for (size_t left = counted; left > 0;) {
                const size_t chunk = left < sizeof(sink) ? left : sizeof(sink);
                const size_t got = io.read(sink, chunk);
                if (got != chunk) return Result::shortRead;
                left -= chunk;
            }
            return Result::oversized;
        }
        size = io.read(buffer, counted);
        if (size != counted) return Result::shortRead;
        if (size < 2 || buffer[0] != 0x00) return Result::frame;
        uint8_t own = 0xFF;
        if (io.read(&own, 1) != 1 || own != 0x00) return Result::misaligned;
        std::memmove(buffer, buffer + 1, size - 1);
        buffer[size - 1] = 0x00;
        return Result::realigned;
    }
};
}
