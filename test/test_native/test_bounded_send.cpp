// Review R2-02: BoundedSend, the end of one HTTP response write. The fake clock moves only in
// wait() (the 1 ms pause between attempts), so the time a write holds the loop is exact.
#include "control/BoundedSend.h"
#include <gtest/gtest.h>
#include <cstdint>
#include <string>
using heating::control::BoundedSend;
namespace {
struct Peer {
    uint32_t now = 1000;
    size_t chunk = SIZE_MAX;   // bytes taken per send
    uint32_t everyMs = 0;      // at most one send taken per this many ms (0: every attempt)
    uint32_t lastTake = 0;
    bool taken = false;
    int failAfter = -1;        // sends that work before the connection fails (-1: never)
    unsigned sends = 0, waits = 0;
    std::string got;
    BoundedSend::Result write(const std::string& data, uint32_t start) {
        return BoundedSend::write(reinterpret_cast<const uint8_t*>(data.data()), data.size(), start,
            [this](const uint8_t* d, size_t n) -> int {
                ++sends;
                if (failAfter >= 0 && int(sends) > failAfter) return -1;
                if (everyMs && taken && now - lastTake < everyMs) return 0;
                const size_t k = n < chunk ? n : chunk;
                if (!k) return 0;
                taken = true; lastTake = now;
                got.append(reinterpret_cast<const char*>(d), k);
                return int(k);
            },
            [this] { return now; }, [this] { ++waits; ++now; });
    }
};
const std::string page(100000, 'x');
}

TEST(BoundedSend, FullSpeedSendsEverythingWithoutWaiting) {
    Peer p;
    const auto r = p.write(page, p.now);
    EXPECT_TRUE(r.complete); EXPECT_EQ(r.sent, page.size()); EXPECT_EQ(p.got, page);
    EXPECT_EQ(p.waits, 0u); EXPECT_EQ(p.sends, 1u);
}
TEST(BoundedSend, AClientThatTakesNothingIsGivenUpAfterTheStallBound) {
    Peer p; p.chunk = 0;
    const uint32_t start = p.now;
    const auto r = p.write(page, start);
    EXPECT_FALSE(r.complete); EXPECT_EQ(r.sent, 0u);
    EXPECT_EQ(p.now - start, BoundedSend::stallMs);
}
TEST(BoundedSend, ADrippingClientIsGivenUpAtTheTotalBound) {
    Peer p; p.chunk = 1; p.everyMs = 1000; // one byte a second: never a 2 s stall
    const uint32_t start = p.now;
    const auto r = p.write(page, start);
    EXPECT_FALSE(r.complete);
    EXPECT_EQ(p.now - start, BoundedSend::totalMs);
    EXPECT_EQ(r.sent, 10u); EXPECT_EQ(p.got.size(), r.sent);
}
TEST(BoundedSend, ASlowButSteadyClientCompletes) {
    Peer p; p.chunk = 512; p.everyMs = 5; // about 100 KB/s, a phone on weak Wi-Fi
    const uint32_t start = p.now;
    const auto r = p.write(page, start);
    EXPECT_TRUE(r.complete); EXPECT_EQ(p.got, page);
    EXPECT_LT(p.now - start, 1500u);
}
TEST(BoundedSend, ASocketErrorEndsTheWriteAtOnce) {
    Peer p; p.chunk = 1000; p.failAfter = 3;
    const auto r = p.write(page, p.now);
    EXPECT_FALSE(r.complete); EXPECT_EQ(r.sent, 3000u); EXPECT_EQ(p.waits, 0u);
}
TEST(BoundedSend, TheWritesOfOneResponseShareTheTotalBound) {
    Peer p; p.chunk = 1; p.everyMs = 500;
    const uint32_t start = p.now - 9000; // the head took 9 s already
    const auto r = p.write(page, start);
    EXPECT_FALSE(r.complete);
    EXPECT_EQ(p.now - start, BoundedSend::totalMs);
    const auto late = p.write(page, start); // a later write of the same response: no time left, nothing sent
    EXPECT_FALSE(late.complete); EXPECT_EQ(late.sent, 0u);
}
TEST(BoundedSend, EmptyAndNullWritesAndAClockWrap) {
    Peer p;
    EXPECT_TRUE(BoundedSend::write(nullptr, 0, 0, [](const uint8_t*, size_t) { return 1; }, [] { return 0u; }, [] {}).complete);
    EXPECT_FALSE(BoundedSend::write(nullptr, 5, 0, [](const uint8_t*, size_t) { return 5; }, [] { return 0u; }, [] {}).complete);
    p.now = UINT32_MAX - 500; p.chunk = 0;
    const uint32_t start = p.now;
    EXPECT_FALSE(p.write(page, start).complete);
    EXPECT_EQ(uint32_t(p.now - start), BoundedSend::stallMs); // across the 32-bit wrap
}
