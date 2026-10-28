#include "control/ActiveHeatGuard.h"
#include <gtest/gtest.h>
#include <memory>
#include <vector>

namespace {
using heating::control::ActiveHeatGuard;
using heating::control::FlowDemand;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using State = ActiveHeatGuard::State;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000;

// One living room with a fresh reading, the tado unplugged, E32 up for an hour.
struct Bench {
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    uint64_t now = 60 * minute;
    bool writesSucceed = true;
    struct Sent { uint64_t at; uint8_t flowC; };
    std::vector<Sent> sent;
    Bench() {
        in.mode = RoomPlan::Mode::active;
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 2040;
        in.uptimeMs = now; in.routeReady = true;
        heat(40);
    }
    void heat(uint8_t flowC) { in.request = {flowC > 0, flowC, flowC ? FlowDemand::Reason::heating : FlowDemand::Reason::idle}; }
    // Steps every 10 s like HeatingController::stepHeating, through `until`.
    void runFor(uint64_t duration) {
        const uint64_t end = now + duration;
        while (now < end) { now += 10 * second; tick(); }
    }
    ActiveHeatGuard::Command tick() {
        in.uptimeMs = now;
        const auto c = guard.step(now, in);
        if (c.send) {
            if (writesSucceed) sent.push_back({now, c.flowC});
            guard.transmitted(now, writesSucceed);
        }
        return c;
    }
    std::vector<Sent> since(uint64_t at) const {
        std::vector<Sent> out;
        for (const auto& s : sent) if (s.at > at) out.push_back(s);
        return out;
    }
};

TEST(ActiveHeatGuard, ShadowNeverSends) {
    Bench b; b.in.mode = RoomPlan::Mode::shadow;
    b.in.rooms.coldestCentiC = 300; // even a frost reading
    b.runFor(3 * 60 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::shadow);
    EXPECT_STREQ(b.guard.command().why, "shadow");
}

TEST(ActiveHeatGuard, ForeignRequestWithinQuietWindowBlocksArming) {
    Bench b;
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, 9 * minute}; // tado unplugged nine minutes ago
    b.tick();
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
    EXPECT_FALSE(b.guard.command().send);
    for (int i = 0; i < 5; ++i) { b.now += 10 * second; b.in.foreign->ageMs += 10 * second; b.tick(); }
    EXPECT_TRUE(b.sent.empty());
    b.now += 10 * second; b.in.foreign->ageMs = 10 * minute; // quiet window over
    b.tick();
    EXPECT_EQ(b.guard.state(), State::active);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0].flowC, 40);
    // Our own address and the boiler's never count as another master.
    Bench own; own.in.foreign = ActiveHeatGuard::Foreign{0x0b, 0};
    own.tick();
    EXPECT_EQ(own.guard.state(), State::active);
}

TEST(ActiveHeatGuard, ForeignRequestWhileActiveStopsWithZeroWindow) {
    Bench b; b.runFor(5 * minute);
    ASSERT_EQ(b.guard.state(), State::active);
    const auto at = b.now;
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, 0};
    b.runFor(3 * minute);
    const auto zeros = b.since(at);
    ASSERT_EQ(zeros.size(), 6u); // 0, 10..50 s; then silent
    for (const auto& z : zeros) EXPECT_EQ(z.flowC, 0);
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
}

TEST(ActiveHeatGuard, UnchangedRequestRefreshesEverySixtySeconds) {
    Bench b; b.runFor(4 * minute + 10 * second);
    ASSERT_EQ(b.sent.size(), 5u);
    for (size_t i = 1; i < b.sent.size(); ++i) EXPECT_EQ(b.sent[i].at - b.sent[i - 1].at, minute);
    // A flow change waits for the cadence; switching heat off does not.
    const auto last = b.sent.back().at;
    ASSERT_EQ(last, b.now);
    b.heat(45); b.now += 10 * second; b.tick();
    EXPECT_EQ(b.sent.back().at, last);
    b.heat(0); b.now += 10 * second; b.tick();
    EXPECT_EQ(b.sent.back().at, b.now);
    EXPECT_EQ(b.sent.back().flowC, 0);
    b.heat(45); b.now += 10 * second; b.tick();
    EXPECT_EQ(b.sent.back().flowC, 45); // and back on, at once
}

TEST(ActiveHeatGuard, StopSendsZeroForOneWindowThenGoesQuiet) {
    Bench b; b.runFor(3 * minute);
    ASSERT_EQ(b.sent.back().flowC, 40);
    const auto at = b.now;
    b.in.mode = RoomPlan::Mode::shadow; // hand back to tado
    b.now += 10 * second;
    const auto first = b.tick();
    EXPECT_EQ(b.guard.state(), State::stopping);
    EXPECT_TRUE(first.send); EXPECT_EQ(first.flowC, 0); EXPECT_STREQ(first.why, "stop_zero");
    b.runFor(60 * minute);
    const auto zeros = b.since(at);
    ASSERT_EQ(zeros.size(), 6u);
    for (const auto& z : zeros) EXPECT_EQ(z.flowC, 0);
    EXPECT_EQ(zeros.back().at - zeros.front().at, 50 * second);
    EXPECT_EQ(b.guard.state(), State::shadow);
}

TEST(ActiveHeatGuard, IdleActiveStillStopsWithZeroAndHeatOffRepeatsZero) {
    Bench b; b.runFor(3 * minute);
    const auto off = b.now;
    b.heat(0); b.runFor(2 * minute);
    auto zeros = b.since(off);
    // Zero at once and every 10 s for one window, then the 60 s refresh.
    ASSERT_EQ(zeros.size(), 7u);
    for (const auto& z : zeros) EXPECT_EQ(z.flowC, 0);
    EXPECT_EQ(zeros[6].at - zeros[5].at, minute);
    const auto stop = b.now;
    b.in.mode = RoomPlan::Mode::shadow;
    b.runFor(5 * minute);
    EXPECT_EQ(b.since(stop).size(), 6u); // leaving active always repeats zero
}

TEST(ActiveHeatGuard, MeasurementLostSendsZeroAfterThirtyMinutes) {
    // The real RoomDemand chain: tado reading at t0, then HA and Bluetooth gone.
    Bench b; b.runFor(minute); // armed on a fresh reading
    ASSERT_EQ(b.guard.state(), State::active);
    RoomDemand::Spec spec; spec.state = RoomDemand::State::active; spec.sources = 2;
    const RoomDemand::Reading last{2040, b.now};
    std::array<RoomDemand::Reading, RoomDemand::maxSources> readings{};
    readings[0] = last;
    const auto roomsAt = [&](uint64_t now) {
        ActiveHeatGuard::Rooms rooms;
        rooms.add(RoomDemand::evaluate(spec, readings, int16_t(2100), now, last));
        return rooms;
    };
    const auto t0 = b.now;
    readings[0] = {}; // no source reports any more
    while (b.now < t0 + 30 * minute - 10 * second) {
        b.in.rooms = roomsAt(b.now + 10 * second);
        b.now += 10 * second; b.tick();
    }
    EXPECT_EQ(b.guard.state(), State::active);
    ASSERT_FALSE(b.sent.empty());
    EXPECT_EQ(b.sent.back().flowC, 40);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::measurementLost));
    b.in.rooms = roomsAt(t0 + 30 * minute);
    b.now = t0 + 30 * minute;
    const auto c = b.tick(); // even if the engine still asked for heat
    EXPECT_EQ(b.guard.state(), State::stoppedMeasurementLost);
    EXPECT_TRUE(c.send); EXPECT_EQ(c.flowC, 0);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::measurementLost));
    b.runFor(10 * minute);
    for (const auto& s : b.since(t0 + 30 * minute - 1)) EXPECT_EQ(s.flowC, 0);
    // A reading returns: heat resumes without re-arming.
    b.in.rooms = {}; b.in.rooms.active = b.in.rooms.fresh = 1;
    b.runFor(10 * second);
    EXPECT_EQ(b.guard.state(), State::active);
    EXPECT_EQ(b.sent.back().flowC, 40);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::measurementLost));
}

TEST(ActiveHeatGuard, FrostReadingInAnyRoomAsksMinimumFlow) {
    Bench b; b.heat(0);
    b.in.rooms.measured(450); // inactive bathroom at 4.5 degC
    b.tick();
    EXPECT_TRUE(b.guard.command().send);
    EXPECT_EQ(b.guard.command().flowC, 30);
    EXPECT_STREQ(b.guard.command().why, "frost_minimum");
    b.in.rooms.coldestCentiC = 550; b.runFor(minute); // hysteresis holds
    EXPECT_EQ(b.sent.back().flowC, 30);
    b.in.rooms.coldestCentiC = 600; b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 0);
    // A higher engine request wins over the frost minimum.
    b.in.rooms.coldestCentiC = 400; b.heat(42); b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 42);
    EXPECT_STREQ(b.guard.command().why, "heat_request");
}

TEST(ActiveHeatGuard, RestartHoldsOffUntilListenedAndInputsFresh) {
    Bench b; b.now = 0; b.in.rooms.fresh = 0; // just rebooted, no reading yet
    b.runFor(9 * minute + 50 * second);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::arming);
    b.in.rooms.fresh = 1; b.runFor(10 * second); // listened 10 min, room fresh
    EXPECT_EQ(b.guard.state(), State::active);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0].at, 10 * minute);
    // The transmit route not ready: still nothing.
    Bench route; route.now = 0; route.in.routeReady = false;
    route.runFor(20 * minute);
    EXPECT_TRUE(route.sent.empty());
    EXPECT_EQ(route.guard.state(), State::arming);
}

TEST(ActiveHeatGuard, RestartWithoutMeasurementOwnsWithZeroAfterThirtyMinutes) {
    Bench b; b.now = 0; b.in.rooms.fresh = 0; b.in.rooms.lost = 1;
    b.runFor(29 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::measurementLost));
    b.runFor(2 * minute);
    EXPECT_EQ(b.guard.state(), State::stoppedMeasurementLost);
    ASSERT_FALSE(b.sent.empty());
    EXPECT_EQ(b.sent[0].flowC, 0);
}

TEST(ActiveHeatGuard, FlowNeverAboveSixty) {
    Bench b; b.heat(90);
    b.runFor(3 * minute);
    for (const auto& s : b.sent) EXPECT_EQ(s.flowC, 60);
    b.guard.setFlowLimits(30, 50); b.runFor(minute);
    EXPECT_EQ(b.sent.back().flowC, 50);
    // A limit above the hard cap is refused: the E32 leaves active with zero.
    b.guard.setFlowLimits(30, 75); b.runFor(2 * minute);
    for (const auto& s : b.sent) EXPECT_LE(s.flowC, 60);
    EXPECT_EQ(b.sent.back().flowC, 0);
    EXPECT_EQ(b.guard.state(), State::shadow);
}

TEST(ActiveHeatGuard, BoilerWithoutResponseWarnsButKeepsAsking) {
    Bench b; b.in.boiler = {false, 2500};
    b.runFor(15 * minute); // first request at +10 s
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::boilerNoResponse));
    b.runFor(10 * second);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::boilerNoResponse));
    EXPECT_EQ(b.guard.state(), State::active);
    EXPECT_EQ(b.sent.back().flowC, 40);
    b.in.boiler.flowCentiC = 2800; b.runFor(10 * second); // 3 degC rise
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::boilerNoResponse));
    // No feedback at all is no response either; burner on clears it.
    Bench quiet; quiet.runFor(16 * minute);
    EXPECT_TRUE(quiet.guard.warning(ActiveHeatGuard::boilerNoResponse));
    quiet.in.boiler.burnerOn = true; quiet.runFor(10 * second);
    EXPECT_FALSE(quiet.guard.warning(ActiveHeatGuard::boilerNoResponse));
}

TEST(ActiveHeatGuard, FailedWriteIsRetriedAndWarned) {
    Bench b; b.writesSucceed = false;
    b.runFor(30 * second);
    EXPECT_TRUE(b.guard.command().send); // retried every step
    b.runFor(3 * minute);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    b.writesSucceed = true; b.runFor(10 * second);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
}

TEST(ActiveHeatGuard, StatusJson) {
    Bench b; b.in.foreign = ActiveHeatGuard::Foreign{0x17, minute};
    b.tick();
    Json j(b.guard.json(b.now), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(j.get(), "state")), "blocked_foreign_controller");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "last_sent")));
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "foreign_controller"), "address")->valueint, 0x17);
    const auto* warnings = cJSON_GetObjectItem(j.get(), "warnings");
    ASSERT_EQ(cJSON_GetArraySize(warnings), 1);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(warnings, 0)), "foreign_controller");
    b.in.foreign.reset(); b.in.foreign = ActiveHeatGuard::Foreign{0x17, 11 * minute};
    b.tick();
    Json k(b.guard.json(b.now + 5 * second), cJSON_Delete);
    const auto* command = cJSON_GetObjectItem(k.get(), "command");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(command, "send")));
    EXPECT_EQ(cJSON_GetObjectItem(command, "flow_c")->valueint, 40);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(command, "why")), "heat_request");
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(k.get(), "last_sent"), "age_ms")->valueint, 5000);
}
}
