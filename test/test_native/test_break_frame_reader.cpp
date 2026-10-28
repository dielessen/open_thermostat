#include "EMS/BreakFrameReader.h"
#include <gtest/gtest.h>
#include <array>
#include <deque>
#include <vector>

namespace {
using heating::ems::BreakFrameReader;
using Result = BreakFrameReader::Result;
// Ring buffer stand-in: read() returns only what is buffered, like a 0-tick read.
struct Fifo {
    std::deque<uint8_t> bytes;
    void push(const std::vector<uint8_t>& frame) { bytes.insert(bytes.end(), frame.begin(), frame.end()); }
    size_t read(uint8_t* dst, size_t n) {
        size_t got = 0;
        for (; got < n && !bytes.empty(); ++got) { dst[got] = bytes.front(); bytes.pop_front(); }
        return got;
    }
};
// Boiler frames as logged on 2026-10-28, each ending in the BREAK's 0x00.
const std::vector<uint8_t> ww{0x08, 0x00, 0x34, 0x00, 0x3C, 0x02, 0x4E, 0x80, 0x00, 0x20, 0x00, 0x00,
                              0x01, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46, 0x00};
const std::vector<uint8_t> request{0x17, 0x08, 0x1A, 0x00, 0x20, 0x64, 0x64, 0x00, 0x62, 0x00};

std::vector<uint8_t> next(Fifo& fifo, size_t counted, Result expected) {
    std::array<uint8_t, 32> buffer{};
    size_t size = 0;
    EXPECT_EQ(BreakFrameReader::read(fifo, buffer.data(), buffer.size(), counted, size), expected);
    return {buffer.begin(), buffer.begin() + size};
}

TEST(BreakFrameReader, CountedFrameIsDeliveredWithItsBreakByte) {
    Fifo fifo; fifo.push(ww);
    EXPECT_EQ(next(fifo, ww.size(), Result::frame), ww);
    EXPECT_TRUE(fifo.bytes.empty());
}

TEST(BreakFrameReader, OneUncountedByteNoLongerShiftsEveryLaterFrame) {
    // The reset race left the previous BREAK's 0x00 without a DATA event.
    Fifo fifo; fifo.bytes.push_back(0x00); fifo.push(ww); fifo.push(request); fifo.push(ww);
    EXPECT_EQ(next(fifo, ww.size(), Result::realigned), ww);
    EXPECT_EQ(next(fifo, request.size(), Result::frame), request);
    EXPECT_EQ(next(fifo, ww.size(), Result::frame), ww);
    EXPECT_TRUE(fifo.bytes.empty());
}

TEST(BreakFrameReader, CountWithoutBytesDropsOneFrameAndDoesNotNeedAFlush) {
    // The opposite race: a DATA event for a flushed byte. Only that frame is lost.
    Fifo fifo; fifo.push(request);
    EXPECT_EQ(next(fifo, request.size() + 1, Result::shortRead).size(), request.size());
    fifo.push(ww);
    EXPECT_EQ(next(fifo, ww.size(), Result::frame), ww);
}

TEST(BreakFrameReader, MisalignedPollIsRealignedToo) {
    Fifo fifo; fifo.bytes.push_back(0x00); fifo.push({0x8B, 0x00});
    EXPECT_EQ(next(fifo, 2, Result::realigned), (std::vector<uint8_t>{0x8B, 0x00}));
}

TEST(BreakFrameReader, LeadingZeroWithoutOwnBreakByteIsDropped) {
    Fifo fifo; fifo.push({0x00, 0x08, 0x02}); fifo.push({0x17});
    EXPECT_TRUE(next(fifo, 3, Result::misaligned).size() == 3);
    EXPECT_FALSE(BreakFrameReader::deliverable(Result::misaligned));
}

TEST(BreakFrameReader, OversizedFrameIsDrainedNotDelivered) {
    Fifo fifo; fifo.push(std::vector<uint8_t>(40, 0x55)); fifo.push(request);
    EXPECT_TRUE(next(fifo, 40, Result::oversized).empty());
    EXPECT_EQ(next(fifo, request.size(), Result::frame), request);
}

TEST(BreakFrameReader, BareBreakAndEmptyCountsAreNotFrames) {
    Fifo fifo; fifo.push({0x00});
    EXPECT_EQ(next(fifo, 1, Result::frame).size(), 1u); // single BREAK byte: caller ignores size 1
    EXPECT_TRUE(next(fifo, 0, Result::empty).empty());
}
}
