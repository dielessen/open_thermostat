#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "EMS/ForeignBoilerRequest.h"
#include "control/ActiveHeatGuard.h"
#include "control/HttpAccessPolicy.h"
#include "control/RoomEngine.h"
#include <gtest/gtest.h>
#include <stdexcept>
#include <vector>

namespace {
using namespace heating::ems;
using heating::control::ActiveHeatGuard;
using heating::control::FlowDemand;
using heating::control::RoomPlan;

// The installed identity and encoder, exactly as EmsController wires them.
bool encode(const BoilerTestSession::Intent& intent, EmsRawFrame& frame) {
    constexpr auto addressing = ClassicBoilerTestEncoder::Addressing::classicService();
    return ClassicBoilerTestEncoder::encode(addressing, intent, frame) && ClassicBoilerTestEncoder::matches(addressing, intent, frame);
}

struct ActivePoll : testing::Test {
    ClassicBoilerMonitor monitor;
    ActiveHeatPollDriver driver{0x2a, true};
    bool ready = true, succeeds = true;
    std::vector<std::vector<uint8_t>> frames;
    uint64_t now = 100000;
    void limit(uint8_t c, uint64_t at = 1000) { ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE, 8, 0x17, 1, 0x16, {c}}, at)); }
    bool poll(ActiveHeatPollDriver::Encoder encoder = encode) {
        return driver.poll(now, monitor, [&] { return ready; }, encoder, [&](const EmsRawFrame& f) {
            frames.emplace_back(f.data.begin(), f.data.begin() + f.length);
            return succeeds;
        });
    }
};

TEST_F(ActivePoll, SendsThePostedRequestOnceThroughTheReviewedEncoder) {
    limit(55);
    const auto seq = driver.post(now, uint8_t(45), true, true);
    EXPECT_FALSE(poll(nullptr)); // no encoder, no frame; the post is used up
    ASSERT_TRUE(driver.last()); EXPECT_EQ(driver.last()->seq, seq); EXPECT_FALSE(driver.last()->ok);
    const auto next = driver.post(now, uint8_t(45), true, true);
    EXPECT_NE(next, seq);
    now += 900; ASSERT_TRUE(poll());
    ASSERT_EQ(frames.size(), 1u);
    const std::vector<uint8_t> want{0x0b, 0x08, 0x1a, 0x00, 45, EmsTelegram::calculateCRC(frames[0].data(), 5)};
    EXPECT_EQ(frames[0], want);
    EXPECT_EQ(driver.last()->seq, next); EXPECT_TRUE(driver.last()->ok);
    EXPECT_FALSE(poll()); EXPECT_EQ(frames.size(), 1u); // one attempt per post
    // A zero request: frame 0B 08 1A 00 00, also without heat authority.
    driver.post(now, uint8_t(0), false, true);
    ASSERT_TRUE(poll()); EXPECT_EQ(frames[1][4], 0);
    // Nothing posted this step: the poll is left to the normal answer.
    driver.post(now, std::nullopt, true, true);
    EXPECT_FALSE(poll()); EXPECT_EQ(frames.size(), 2u);
}

TEST_F(ActivePoll, RefusesWithoutGateRouteHeatAuthorityOrInTime) {
    limit(55);
    const auto refused = [&](bool expected = false) {
        const auto seq = driver.last() ? driver.last()->seq : 0;
        EXPECT_EQ(poll(), expected);
        return driver.last() && driver.last()->seq > seq && !driver.last()->ok;
    };
    driver.post(now, uint8_t(45), false, true); EXPECT_TRUE(refused()); // positive needs plan active + confirmation
    ready = false; driver.post(now, uint8_t(0), true, true); EXPECT_TRUE(refused()); // trial, read, settings or transport
    ready = true; driver.post(now - 10000, uint8_t(45), true, true); EXPECT_TRUE(refused()); // older than its step
    driver.post(now + 1, uint8_t(45), true, true); EXPECT_TRUE(refused()); // clock reversed
    succeeds = false; driver.post(now, uint8_t(45), true, true); EXPECT_TRUE(refused(true)); // UART write failed
    EXPECT_EQ(frames.size(), 1u);
    // Compile gate closed: nothing is ever posted, sent or claimed.
    ActiveHeatPollDriver closed{0x2a, false};
    EXPECT_EQ(closed.post(now, uint8_t(45), true, true), 0u);
    EXPECT_FALSE(closed.claimed());
    EXPECT_FALSE(closed.poll(now, monitor, [] { return true; }, encode, [&](const EmsRawFrame&) { ADD_FAILURE(); return true; }));
    EXPECT_FALSE(closed.last());
    // A throwing writer is a failed write, never a crash.
    succeeds = true; driver.post(now, uint8_t(45), true, true);
    EXPECT_TRUE(driver.poll(now, monitor, [] { return true; }, encode, [](const EmsRawFrame&) -> bool { throw std::runtime_error("uart"); }));
    EXPECT_FALSE(driver.last()->ok);
}

TEST_F(ActivePoll, EnvelopeIsSixtyAndTheBoilersOwnLimit) {
    EXPECT_FALSE(ActiveHeatEnvelope::limitC(monitor));
    EXPECT_TRUE(ActiveHeatEnvelope::admits(monitor, 0)); // zero is always allowed
    EXPECT_FALSE(ActiveHeatEnvelope::admits(monitor, 30));
    driver.post(now, uint8_t(30), true, true); EXPECT_FALSE(poll());
    limit(55);
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 55);
    EXPECT_TRUE(ActiveHeatEnvelope::admits(monitor, 55));
    EXPECT_FALSE(ActiveHeatEnvelope::admits(monitor, 56));
    limit(80, 2000);
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 60);
    EXPECT_FALSE(ActiveHeatEnvelope::admits(monitor, 61));
    // The latest report this boot, whatever its age: the setting lives in the boiler.
    EXPECT_EQ(ActiveHeatEnvelope::limitC(monitor), 60);
    driver.post(now, uint8_t(60), true, true); EXPECT_TRUE(poll());
    ClassicBoilerMonitor plus;
    plus.receive({EmsTelegram::BROADCAST, 8, 0, 0, 0xE4, {0}}, 1000);
    EXPECT_FALSE(ActiveHeatEnvelope::limitC(plus));
}

TEST_F(ActivePoll, ClaimFollowsThePost) {
    EXPECT_FALSE(driver.claimed());
    driver.post(now, std::nullopt, false, true); EXPECT_TRUE(driver.claimed());
    driver.post(now, std::nullopt, false, false); EXPECT_FALSE(driver.claimed());
}

TEST(ForeignBoilerRequest, RecordsTheLastOtherMasterAskingTheBoiler) {
    ForeignBoilerRequest foreign;
    foreign.observe({EmsTelegram::WRITE, 0x0b, 0x08, 0, 0x1a, {45}}, 10);  // the E32 itself
    foreign.observe({EmsTelegram::WRITE, 0x08, 0x08, 0, 0x1a, {45}}, 11);  // never the boiler
    foreign.observe({EmsTelegram::READ, 0x17, 0x08, 0, 0x1a, {1}}, 12);    // a read asks nothing
    foreign.observe({EmsTelegram::WRITE, 0x17, 0x08, 0, 0x18, {45}}, 13);  // another type
    foreign.observe({EmsTelegram::WRITE, 0x17, 0x10, 0, 0x1a, {45}}, 14);  // another destination
    foreign.observe({EmsTelegram::BROADCAST, 0x17, 0x00, 0, 0x1a, {45}}, 15);
    EXPECT_FALSE(foreign.last);
    foreign.observe({EmsTelegram::WRITE, 0x97, 0x08, 0, 0x1a, {38}}, 20); // the tado, MSB-masked sender
    ASSERT_TRUE(foreign.last);
    EXPECT_EQ(foreign.last->address, 0x17); EXPECT_EQ(foreign.last->receivedAtMs, 20u);
    foreign.observe({EmsTelegram::WRITE, 0x18, 0x08, 0, 0x1a, {0}}, 19); // a reordered older frame
    EXPECT_EQ(foreign.last->address, 0x17);
    foreign.observe({EmsTelegram::WRITE, 0x18, 0x08, 0, 0x1a, {0}}, 400000); // no expiry, newest wins
    EXPECT_EQ(foreign.last->address, 0x18); EXPECT_EQ(foreign.last->receivedAtMs, 400000u);
}

TEST(ActiveHeatRoutes, HandoverIsPostOnly) {
    EXPECT_TRUE(heating::control::allowedHttpMethod("/config/heating/handover", "POST"));
    for (const char* method : {"GET", "DELETE", "PUT"}) EXPECT_FALSE(heating::control::allowedHttpMethod("/config/heating/handover", method));
    EXPECT_TRUE(heating::control::allowedHttpMethod("/config/heating", "GET"));
}

TEST(ActiveHeatRoutes, RoomEngineReportsFreshReadingsOfInactiveRoomsForFrost) {
    heating::control::RoomEngine engine;
    RoomPlan plan;
    RoomPlan::Room bath; bath.id = "badkamer"; bath.name = "Badkamer";
    bath.sources = {{RoomPlan::SourceType::ble, "a4c138a3e8db"}, {RoomPlan::SourceType::ha, "sensor.badkamer"}};
    plan.rooms = {bath};
    engine.setPlan(plan);
    engine.bleReading("a4c138a3e8db", 750, 1000);
    engine.step(2000, std::nullopt);
    EXPECT_EQ(engine.result(0).status, heating::control::RoomDemand::Status::inactive);
    EXPECT_EQ(engine.freshTemperature(0, 2000), 750);
    engine.haState("sensor.badkamer", 760, std::nullopt, 950000);
    EXPECT_EQ(engine.freshTemperature(0, 950000), 760); // the first source is too old now
    EXPECT_EQ(engine.fresh(0, 2000).source, 0);         // FlowLearner: which source leads
    EXPECT_EQ(engine.fresh(0, 950000).source, 1);
    EXPECT_FALSE(engine.freshTemperature(0, 2000000));
    EXPECT_EQ(engine.fresh(0, 2000000).source, -1);
}

// The HeatingController loop: guard step -> post -> the boiler's poll -> the
// result read back at the next step. The 60 s refresh holds over the route.
TEST(ActiveHeatRoutes, GuardAndRouteKeepTheRefreshCadence) {
    ClassicBoilerMonitor monitor;
    ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE, 8, 0x17, 1, 0x16, {55}}, 1000));
    ActiveHeatPollDriver driver{0x2a, true};
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    in.mode = RoomPlan::Mode::active; in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 2040;
    in.routeReady = true; in.request = {true, 58, FlowDemand::Reason::heating};
    std::vector<std::pair<uint64_t, uint8_t>> sent;
    uint64_t now = 3600000, postedAt = 0; uint32_t posted = 0;
    guard.confirm(now, true);
    for (int step = 0; step < 36; ++step) {
        now += 10000;
        if (driver.last() && driver.last()->seq == posted) guard.transmitted(postedAt, driver.last()->ok);
        in.uptimeMs = now; in.boilerLimitC = ActiveHeatEnvelope::limitC(monitor);
        const auto c = guard.step(now, in);
        posted = driver.post(now, c.send ? std::optional<uint8_t>(c.flowC) : std::nullopt, guard.confirmed(), guard.claimsBoiler());
        postedAt = now;
        driver.poll(now + 700, monitor, [] { return true; }, encode, [&](const EmsRawFrame& f) { sent.push_back({now + 700, f.data[4]}); return true; });
    }
    ASSERT_EQ(sent.size(), 6u);
    for (size_t i = 0; i < sent.size(); ++i) {
        EXPECT_EQ(sent[i].second, 55); // capped by the boiler's own limit
        if (i) { EXPECT_EQ(sent[i].first - sent[i - 1].first, 60000u); }
    }
    EXPECT_TRUE(driver.claimed());
}
}
