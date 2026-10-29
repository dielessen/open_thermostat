#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/BoilerLimitRead.h"
#include "EMS/ManualClassicTransaction.h"
#include <gtest/gtest.h>
#include <stdexcept>
#include <vector>

namespace {
using namespace heating::ems;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;

struct LimitRead : testing::Test {
    ClassicBoilerMonitor monitor;
    BoilerLimitRead read{true};
    bool ready = true, succeeds = true;
    std::vector<std::vector<uint8_t>> frames;
    uint64_t now = 20 * second; // just booted
    bool poll() {
        return read.poll(now, ActiveHeatEnvelope::reportedAtMs(monitor), [&] { return ready; }, [&](const EmsRawFrame& f) {
            frames.emplace_back(f.data.begin(), f.data.begin() + f.length);
            return succeeds;
        });
    }
    // The boiler's answer to a 0x16 read: heating on, limit c degC.
    void reply(uint8_t c, uint8_t to = 0x0b) { ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE, 8, to, 0, 0x16, {0xFF, c}}, now)); }
};

TEST_F(LimitRead, ReadsOnceAfterBootThroughTheReviewedReadFrame) {
    EXPECT_FALSE(ActiveHeatEnvelope::limitC(monitor));
    ASSERT_TRUE(poll());
    ASSERT_EQ(frames.size(), 1u);
    // 0B 88 16 00 02 CRC: E32 (0x0B) reads 2 bytes of 0x16 from the boiler (0x08 | 0x80).
    const std::vector<uint8_t> want{0x0b, 0x88, 0x16, 0x00, 0x02, EmsTelegram::calculateCRC(frames[0].data(), 5)};
    EXPECT_EQ(frames[0], want);
    // The private transaction admits exactly this read (and its 7-byte reply).
    ManualClassicTransaction transaction;
    EXPECT_TRUE(transaction.begin(frames[0].data(), frames[0].size(), 1));
    EXPECT_EQ(read.sent(), 1u);
    reply(62);
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 62);
    EXPECT_EQ(ActiveHeatEnvelope::reportedAtMs(monitor), now);
    // Fresh for 6 h: no traffic, then exactly one new read.
    for (now += second; now < 20 * second + 6 * hour; now += 30 * second) EXPECT_FALSE(poll());
    now = 20 * second + 6 * hour;
    EXPECT_TRUE(poll());
    EXPECT_EQ(frames.size(), 2u);
}

TEST_F(LimitRead, UnansweredReadIsRetriedAfterFiveMinutes) {
    ASSERT_TRUE(poll());
    now += 4 * minute + 59 * second; EXPECT_FALSE(poll());
    now += second; EXPECT_TRUE(poll());
    succeeds = false; now += 5 * minute; EXPECT_TRUE(poll()); // a failed write still uses the poll
    EXPECT_EQ(read.sent(), 3u); EXPECT_EQ(read.failed(), 1u);
    EXPECT_FALSE(poll());
    // A write that throws is a failed attempt, not a crash.
    now += 5 * minute;
    EXPECT_TRUE(read.poll(now, std::nullopt, [] { return true; }, [](const EmsRawFrame&) -> bool { throw std::runtime_error("uart"); }));
    EXPECT_EQ(read.failed(), 2u);
}

TEST_F(LimitRead, AReportForAnotherMasterAlsoCounts) {
    reply(55, 0x17); // the tado asked; the boiler's answer is the same setting
    EXPECT_FALSE(poll());
    EXPECT_TRUE(frames.empty());
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 55);
    now += 6 * hour; EXPECT_TRUE(poll());
}

TEST_F(LimitRead, NeverWithoutTheRouteOrTheBuildPermission) {
    ready = false;
    EXPECT_FALSE(poll());
    EXPECT_EQ(read.sent(), 0u);
    ready = true;
    BoilerLimitRead closed{false};
    EXPECT_FALSE(closed.due(now, std::nullopt));
    EXPECT_FALSE(closed.poll(now, std::nullopt, [] { return true; }, [&](const EmsRawFrame&) { ADD_FAILURE(); return true; }));
    // A report time in the future (clock oddity) counts as fresh.
    EXPECT_FALSE(read.due(now, now + minute));
}

TEST_F(LimitRead, OnlyAReported0x16LimitIsTheActiveCeiling) {
    // Offset 1 of another type, or an out-of-range byte, is no limit.
    ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE, 8, 0x0b, 0, 0x16, {0xFF, 200}}, now));
    EXPECT_FALSE(ActiveHeatEnvelope::limitC(monitor));
    EXPECT_FALSE(ActiveHeatEnvelope::reportedAtMs(monitor));
    EXPECT_TRUE(read.due(now, ActiveHeatEnvelope::reportedAtMs(monitor)));
    now += second; reply(90); // above the hard 80 degC: clamped
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 80);
}
}
