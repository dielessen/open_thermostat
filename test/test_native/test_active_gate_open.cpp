// Beta.22 opens board::emsActiveHeatAllowed. These tests drive the whole loop
// as HeatingController::stepActiveHeat wires it (guard step -> post -> the
// boiler's poll of 0x0B -> result read back) with the route compiled OPEN, and
// check the bytes that reach the bus. Opening the gate alone must send nothing:
// the owner still has to set the plan to active and confirm the handover.
#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "control/ActiveHeatGuard.h"
#include <gtest/gtest.h>
#include <optional>
#include <string>
#include <vector>

namespace {
using namespace heating::ems;
using heating::control::ActiveHeatGuard;
using heating::control::FlowDemand;
using heating::control::RoomPlan;
constexpr uint64_t second = 1000, minute = 60000, hour = 60 * minute;

bool encode(const BoilerTestSession::Intent& intent, EmsRawFrame& frame) {
    constexpr auto addressing = ClassicBoilerTestEncoder::Addressing::classicService();
    return ClassicBoilerTestEncoder::encode(addressing, intent, frame) && ClassicBoilerTestEncoder::matches(addressing, intent, frame);
}

// One living room, the boiler reporting a 55 degC limit, the E32 up for an hour.
struct Loop {
    bool gate;                       // board::emsActiveHeatAllowed of the build
    RoomPlan::Mode plan = RoomPlan::Mode::shadow;
    ClassicBoilerMonitor monitor;
    ActiveHeatPollDriver driver;
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    uint64_t now = hour, postedAt = 0;
    uint32_t posted = 0;
    struct Frame { uint64_t at; std::vector<uint8_t> bytes; };
    std::vector<Frame> frames;
    std::vector<std::string> commands; // the guard's decision per step

    explicit Loop(bool gateOpen) : gate(gateOpen), driver(0x2a, gateOpen) {
        EXPECT_TRUE(monitor.receive({EmsTelegram::WRITE, 8, 0x17, 1, 0x16, {55}}, 1000));
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 2040;
        in.routeReady = true; in.boilerHeardAtMs = now;
        heat(45);
    }
    void heat(uint8_t flowC) { in.request = {flowC > 0, flowC, flowC ? FlowDemand::Reason::heating : FlowDemand::Reason::idle}; }
    // setHeatingHandover: refused unless the gate is open and the plan is active.
    bool handover(bool tadoDisconnected) {
        if (tadoDisconnected && (!gate || plan != RoomPlan::Mode::active)) return false;
        guard.confirm(now, tadoDisconnected);
        return true;
    }
    void step() {
        now += 10 * second;
        if (driver.last() && driver.last()->seq == posted) guard.transmitted(postedAt, driver.last()->ok);
        in.mode = gate ? plan : RoomPlan::Mode::shadow;
        in.uptimeMs = now; in.boilerLimitC = ActiveHeatEnvelope::limitC(monitor); in.boilerHeardAtMs = now;
        const auto c = guard.step(now, in);
        commands.push_back(std::string(c.send ? "send " : "hold ") + std::to_string(c.flowC) + " " + c.why);
        posted = driver.post(now, c.send ? std::optional<uint8_t>(c.flowC) : std::nullopt,
                             in.mode == RoomPlan::Mode::active && guard.confirmed(), guard.claimsBoiler());
        postedAt = now;
        driver.poll(now + 700, monitor, [] { return true; }, encode, [&](const EmsRawFrame& f) {
            frames.push_back({now + 700, std::vector<uint8_t>(f.data.begin(), f.data.begin() + f.length)});
            return true;
        });
    }
    void runFor(uint64_t duration) { const uint64_t end = now + duration; while (now < end) step(); }
    std::vector<uint8_t> flows(uint64_t after = 0) const {
        std::vector<uint8_t> out;
        for (const auto& f : frames) if (f.at > after) out.push_back(f.bytes[4]);
        return out;
    }
};

// Every input the guard reads, varied over a day: heat demand, frost, a foreign
// 0x1A, lost measurements and a planned-restart withdrawal.
void stir(Loop& l) {
    for (int i = 0; i < 24 * 6; ++i) {
        const int k = i % 12;
        l.heat(k < 4 ? 50 : k < 6 ? 0 : 38);
        l.in.rooms.coldestCentiC = k == 7 ? 600 : 2040;               // frost reading
        l.in.rooms.lost = k == 9 ? 1 : 0; l.in.rooms.fresh = k == 9 ? 0 : 1;
        if (k == 10) l.in.foreign = ActiveHeatGuard::Foreign{0x17, l.now};
        if (i == 100) l.guard.withdraw(l.now);
        l.runFor(10 * minute);
    }
}

TEST(ActiveGateOpen, ShadowPlanSendsNothingAndDecidesExactlyLikeTheClosedBuild) {
    Loop open(true), closed(false);
    stir(open); stir(closed);
    EXPECT_TRUE(open.frames.empty());   // not one byte on the bus
    EXPECT_TRUE(closed.frames.empty());
    EXPECT_EQ(open.commands, closed.commands); // the same decision at every step
    EXPECT_FALSE(open.driver.claimed());
    EXPECT_EQ(open.guard.state(), ActiveHeatGuard::State::shadow);
    EXPECT_FALSE(open.handover(true));  // "the tado is disconnected" is refused while the plan is in shadow mode
}

TEST(ActiveGateOpen, ActivePlanWithoutTheOwnersConfirmationSendsNothing) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    stir(l);
    EXPECT_TRUE(l.frames.empty());
    EXPECT_FALSE(l.driver.claimed());
    EXPECT_FALSE(l.guard.confirmed());
    EXPECT_EQ(l.guard.state(), ActiveHeatGuard::State::awaitingConfirmation);
}

TEST(ActiveGateOpen, ClosedBuildRefusesTheHandoverEvenWithAnActivePlan) {
    Loop l(false);
    l.plan = RoomPlan::Mode::active;
    EXPECT_FALSE(l.handover(true));
    l.guard.confirm(l.now, true); // even a stored confirmation cannot send through a closed build
    l.runFor(2 * hour);
    EXPECT_TRUE(l.frames.empty());
    EXPECT_FALSE(l.driver.claimed());
}

TEST(ActiveGateOpen, AfterConfirmationTheGuardedRequestReachesTheBusCappedByTheBoiler) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    l.runFor(5 * minute);
    EXPECT_TRUE(l.frames.empty());
    ASSERT_TRUE(l.handover(true));
    l.heat(58);
    l.runFor(10 * minute);
    ASSERT_FALSE(l.frames.empty());
    const std::vector<uint8_t> first{0x0b, 0x08, 0x1a, 0x00, 55, EmsTelegram::calculateCRC(l.frames[0].bytes.data(), 5)};
    EXPECT_EQ(l.frames[0].bytes, first);  // UBASetPoints to the boiler, capped at its own 55 degC
    for (auto f : l.flows()) EXPECT_EQ(f, 55);
    EXPECT_TRUE(l.driver.claimed());
    EXPECT_EQ(l.guard.state(), ActiveHeatGuard::State::active);
}

TEST(ActiveGateOpen, HandBackToTheThermostatEndsWithZeroThenSilence) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    ASSERT_TRUE(l.handover(true));
    l.runFor(10 * minute);
    ASSERT_FALSE(l.flows().empty());
    const auto at = l.now;
    l.handover(false); // "back to the thermostat"
    l.runFor(30 * minute);
    const auto after = l.flows(at);
    ASSERT_FALSE(after.empty());
    for (auto f : after) EXPECT_EQ(f, 0);  // only zero requests after the hand-back
    const auto quietFrom = l.now;
    l.runFor(2 * hour);
    EXPECT_TRUE(l.flows(quietFrom).empty()); // and then nothing at all
    EXPECT_FALSE(l.driver.claimed());
}

TEST(ActiveGateOpen, ForeignRequestAfterTakeoverStopsWithZeroAndNeedsANewConfirmation) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    ASSERT_TRUE(l.handover(true));
    l.runFor(10 * minute);
    ASSERT_FALSE(l.flows().empty());
    const auto at = l.now;
    l.in.foreign = ActiveHeatGuard::Foreign{0x17, l.now}; // the tado asks the boiler again
    l.runFor(hour);
    for (auto f : l.flows(at)) EXPECT_EQ(f, 0);
    EXPECT_FALSE(l.guard.confirmed());
    EXPECT_EQ(l.guard.state(), ActiveHeatGuard::State::blockedForeignController); // the owner must confirm again
}

TEST(ActiveGateOpen, LostMeasurementSendsZeroAfterThirtyMinutesAndResumes) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    ASSERT_TRUE(l.handover(true));
    l.runFor(10 * minute);
    // RoomDemand counts a room as "lost" only after 30 minutes without a reading;
    // until then the reading is merely stale and the request stays.
    const auto staleAt = l.now;
    l.in.rooms.fresh = 0;
    l.runFor(29 * minute);
    for (auto f : l.flows(staleAt)) EXPECT_GT(f, 0); // still heating within the 30 minutes
    const auto zeroFrom = l.now;
    l.in.rooms.lost = 1;                              // 30 minutes without a reading
    l.runFor(10 * minute);
    const auto zeros = l.flows(zeroFrom);
    ASSERT_FALSE(zeros.empty());
    EXPECT_EQ(zeros.back(), 0);
    EXPECT_EQ(l.guard.state(), ActiveHeatGuard::State::stoppedMeasurementLost);
    const auto back = l.now;
    l.in.rooms.lost = 0; l.in.rooms.fresh = 1; // the reading returns
    l.runFor(5 * minute);
    const auto resumed = l.flows(back);
    ASSERT_FALSE(resumed.empty());
    EXPECT_GT(resumed.back(), 0);
}

TEST(ActiveGateOpen, PlannedRestartWithdrawsWithZeroAndReleasesTheBoiler) {
    Loop l(true);
    l.plan = RoomPlan::Mode::active;
    ASSERT_TRUE(l.handover(true));
    l.runFor(10 * minute);
    EXPECT_FALSE(l.guard.released()); // a positive request is held by the boiler
    const auto at = l.now;
    l.guard.withdraw(l.now);
    l.runFor(3 * minute);
    const auto after = l.flows(at);
    ASSERT_FALSE(after.empty());
    for (auto f : after) EXPECT_EQ(f, 0);
    EXPECT_TRUE(l.guard.released()); // the restart may go ahead
    const auto quiet = l.now;
    l.runFor(hour);
    for (auto f : l.flows(quiet)) EXPECT_EQ(f, 0); // never a new takeover before the restart
}
}
