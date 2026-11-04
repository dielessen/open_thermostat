// Review R2-09: the MQTT broker reconnect pacing of ModernTransport (control/BrokerRetry.h).
#include "control/BrokerRetry.h"
#include <gtest/gtest.h>
#include <cstdint>
#include <vector>
using heating::control::BrokerRetry;
namespace {
constexpr uint64_t second = 1000;
// The wait from `now` with the jitter at its middle (random = 20 % of the wait: no shift).
uint64_t middle(BrokerRetry& r, uint64_t now) { return r.next(now, r.waitMs() / 5) - now; }
}

TEST(BrokerRetry, FailedAttemptsWaitFiveTenTwentyFortyThenSixtySeconds) {
    BrokerRetry r;
    std::vector<uint64_t> waits;
    uint64_t now = 100 * second;
    for (int i = 0; i < 7; ++i) { const auto w = middle(r, now); waits.push_back(w); now += w; }
    EXPECT_EQ(waits, (std::vector<uint64_t>{5 * second, 10 * second, 20 * second, 40 * second, 60 * second, 60 * second, 60 * second}));
    // A broker down for a day: about 1 440 attempts instead of 17 280.
    unsigned attempts = 0;
    for (uint64_t t = 0; t < 24 * 3600 * second; t += middle(r, t)) ++attempts;
    EXPECT_LE(attempts, 1450u);
}
TEST(BrokerRetry, TheJitterStaysWithinTwentyPercent) {
    for (uint32_t random : {0u, 1u, 999u, 1000u, 1001u, 2000u, 0x7fffffffu, 0xffffffffu}) {
        BrokerRetry r;
        uint64_t now = 0;
        for (const uint64_t wait : {5000u, 10000u, 20000u, 40000u, 60000u, 60000u}) {
            const uint64_t at = r.next(now, random);
            EXPECT_GE(at - now, wait * 4 / 5) << random;
            EXPECT_LE(at - now, wait * 6 / 5) << random;
            now = at;
        }
    }
}
TEST(BrokerRetry, ASessionOfAMinuteStartsOverAShortOneDoesNot) {
    BrokerRetry r;
    uint64_t now = 0;
    for (int i = 0; i < 4; ++i) now += middle(r, now); // 5 + 10 + 20 + 40 s of failures
    EXPECT_EQ(r.waitMs(), 60000u);
    r.connected(now); r.disconnected(now + 59 * second); // the broker drops it at once
    EXPECT_EQ(r.waitMs(), 60000u);
    r.connected(now + 70 * second); r.disconnected(now + 70 * second + BrokerRetry::stableMs);
    EXPECT_EQ(r.waitMs(), BrokerRetry::firstMs);
    EXPECT_EQ(middle(r, now), 5 * second);
    r.disconnected(now + 500 * second); // no session: nothing changes
    EXPECT_EQ(r.waitMs(), 10000u);
}
