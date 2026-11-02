#include "EMS/EmsDeviceInventory.h"
#include "EMS/IdentityRead.h"
#include "EMS/ManualClassicTransaction.h"
#include <gtest/gtest.h>
#include <stdexcept>
#include <vector>

namespace {
using namespace heating::ems;
constexpr uint64_t second = 1000, minute = 60000;

struct Identity : testing::Test {
    EmsDeviceInventory inventory;
    IdentityRead read{true};
    bool ready = true, succeeds = true;
    std::vector<std::vector<uint8_t>> frames;
    uint64_t now = 20 * second; // just booted
    void heard(uint8_t address) { inventory.observe({EmsTelegram::WRITE, address, 0, 0, 0x18, {1, 2, 3}}, now); }
    void answer(uint8_t address) { inventory.observe({EmsTelegram::WRITE, address, 0x0b, 0, 0x02, {211, 2, 3}}, now); }
    bool poll() {
        const auto target = inventory.withoutVersion([&](uint8_t a) { return !read.wants(now, a); });
        return read.poll(now, target, [&] { return ready; }, [&](const EmsRawFrame& f) {
            frames.emplace_back(f.data.begin(), f.data.begin() + f.length);
            return succeeds;
        });
    }
};

TEST_F(Identity, AsksEachHeardDeviceOnceAfterBootWithTheReviewedFrame) {
    heard(0x08); heard(0x17); heard(0x0b);
    EXPECT_FALSE(poll()) << "not in the first two minutes";
    now = 2 * minute;
    ASSERT_TRUE(poll());
    // 0B 88 02 00 0A CRC: the E32 (0x0B) reads 10 bytes of the version telegram 0x02 from the boiler.
    const std::vector<uint8_t> want{0x0b, 0x88, 0x02, 0x00, 0x0a, EmsTelegram::calculateCRC(frames[0].data(), 5)};
    EXPECT_EQ(frames[0], want);
    ManualClassicTransaction transaction;
    EXPECT_TRUE(transaction.begin(frames[0].data(), frames[0].size(), 1)) << "the private read transaction admits it";
    answer(0x08);
    now += 30 * second; EXPECT_FALSE(poll()) << "one request a minute at most";
    now += 30 * second; ASSERT_TRUE(poll());
    EXPECT_EQ(frames[1][1], 0x80 | 0x17) << "then the thermostat; never 0x0B itself";
    answer(0x17);
    for (int i = 0; i < 20; ++i) { now += minute; EXPECT_FALSE(poll()); }
    EXPECT_EQ(read.sent(), 2u);
}

TEST_F(Identity, ASilentDeviceIsTriedThreeTimesWithoutBlockingOthers) {
    heard(0x08); now = 2 * minute;
    ASSERT_TRUE(poll()); // 0x08 does not answer
    heard(0x17);
    now += minute; ASSERT_TRUE(poll());
    EXPECT_EQ(frames.back()[1], 0x80 | 0x17) << "a device waiting for its retry does not hold others back";
    answer(0x17);
    now += 4 * minute; ASSERT_TRUE(poll()); EXPECT_EQ(frames.back()[1], 0x88);
    now += 5 * minute; ASSERT_TRUE(poll()); EXPECT_EQ(frames.back()[1], 0x88);
    for (int i = 0; i < 30; ++i) { now += minute; EXPECT_FALSE(poll()) << "three tries, then left alone this boot"; }
    EXPECT_EQ(read.sent(), 4u);
}

TEST_F(Identity, OnlyThroughTheReadyRouteAndNeverWhenNotCompiled) {
    heard(0x08); now = 2 * minute;
    ready = false; EXPECT_FALSE(poll()) << "the route's gates (trial, active heat, transport) come first";
    ready = true; succeeds = false; EXPECT_TRUE(poll()); EXPECT_EQ(read.failed(), 1u);
    now += 5 * minute;
    EXPECT_TRUE(read.poll(now, std::optional<uint8_t>{0x08}, [] { return true; }, [](const EmsRawFrame&) -> bool { throw std::runtime_error("uart"); }));
    EXPECT_EQ(read.failed(), 2u);
    IdentityRead off{false};
    EXPECT_FALSE(off.due(10 * minute, std::optional<uint8_t>{0x08}));
    EXPECT_FALSE(read.due(20 * minute, std::optional<uint8_t>{0x0b}));
    EXPECT_FALSE(read.due(20 * minute, std::nullopt));
}
}
