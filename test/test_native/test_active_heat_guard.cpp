#include "control/ActiveHeatGuard.h"
#include "update/RestartTimer.h"
#include <array>
#include <string>
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

// One living room with a fresh reading, the tado unplugged and confirmed so
// by the owner, E32 up for an hour, the boiler reporting a 60 degC limit.
struct Bench {
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    uint64_t now = 60 * minute;
    bool writesSucceed = true;
    struct Sent { uint64_t at; uint8_t flowC; };
    std::vector<Sent> sent;
    explicit Bench(bool confirmed = true) {
        in.mode = RoomPlan::Mode::active;
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 2040;
        in.uptimeMs = now; in.routeReady = true; in.boilerLimitC = 60;
        heat(40);
        if (confirmed) guard.confirm(now, true);
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

TEST(ActiveHeatGuard, ShadowNeverSendsAndForgetsTheConfirmation) {
    Bench b; b.in.mode = RoomPlan::Mode::shadow;
    b.in.rooms.coldestCentiC = 300; // even a frost reading
    b.runFor(3 * 60 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::shadow);
    EXPECT_STREQ(b.guard.command().why, "shadow");
    EXPECT_FALSE(b.guard.confirmed());
    b.in.mode = RoomPlan::Mode::active; b.runFor(minute); // active again: confirm again
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
}

TEST(ActiveHeatGuard, TakesOverOnlyAfterTheOwnerConfirms) {
    Bench b(false);
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now - 5 * second}; // the tado's last request, just before
    b.runFor(30 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
    EXPECT_STREQ(b.guard.command().why, "awaiting_confirmation");
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::foreignController));
    b.guard.confirm(b.now, true); // no quiet window: the next step takes over
    b.runFor(10 * second);
    EXPECT_EQ(b.guard.state(), State::active);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0].flowC, 40);
    // Withdrawing the confirmation ends with the zero window.
    b.guard.confirm(b.now, false);
    b.runFor(3 * minute);
    EXPECT_EQ(b.since(b.sent[0].at).size(), 6u);
    EXPECT_EQ(b.sent.back().flowC, 0);
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
}

TEST(ActiveHeatGuard, ForeignRequestAfterConfirmationBlocksBeforeSending) {
    Bench b; b.in.routeReady = false; // still arming
    b.runFor(minute);
    ASSERT_EQ(b.guard.state(), State::arming);
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 5 * second}; // the tado is still connected
    b.in.routeReady = true; b.runFor(10 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
    EXPECT_FALSE(b.guard.confirmed()); // must be given again
    b.guard.confirm(b.now, true); b.runFor(10 * second);
    EXPECT_EQ(b.guard.state(), State::active);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::foreignController));
    // Our own address and the boiler's never count as another master.
    for (uint8_t address : {uint8_t(0x0b), uint8_t(0x08)}) {
        Bench own; own.in.foreign = ActiveHeatGuard::Foreign{address, own.now + minute};
        own.runFor(2 * minute);
        EXPECT_EQ(own.guard.state(), State::active);
    }
}

TEST(ActiveHeatGuard, ForeignRequestWhileActiveStopsWithZeroWindow) {
    Bench b; b.runFor(5 * minute);
    ASSERT_EQ(b.guard.state(), State::active);
    const auto at = b.now;
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, at + 1};
    b.runFor(3 * minute);
    const auto zeros = b.since(at);
    ASSERT_EQ(zeros.size(), 6u); // 0, 10..50 s; then silent
    for (const auto& z : zeros) EXPECT_EQ(z.flowC, 0);
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
    EXPECT_FALSE(b.guard.confirmed());
    b.runFor(60 * minute); // stays blocked: no automatic retry
    EXPECT_EQ(b.since(at).size(), 6u);
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
    EXPECT_FALSE(b.guard.confirmed());
    b.runFor(60 * minute);
    const auto zeros = b.since(at);
    ASSERT_EQ(zeros.size(), 6u);
    for (const auto& z : zeros) EXPECT_EQ(z.flowC, 0);
    EXPECT_EQ(zeros.back().at - zeros.front().at, 50 * second);
    EXPECT_EQ(b.guard.state(), State::shadow);
}

TEST(ActiveHeatGuard, StopKeepsRepeatingZeroUntilOneIsDelivered) {
    Bench b; b.runFor(3 * minute);
    ASSERT_EQ(b.sent.back().flowC, 40);
    b.writesSucceed = false; // bus busy, or the boiler stops polling 0x0B
    b.in.mode = RoomPlan::Mode::shadow;
    b.runFor(2 * minute);
    EXPECT_EQ(b.guard.state(), State::stopping);
    EXPECT_TRUE(b.guard.claimsBoiler());
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    b.in.routeReady = false; b.runFor(6 * 60 * minute); // the route stays down for hours
    EXPECT_EQ(b.guard.state(), State::stopping);
    EXPECT_FALSE(b.guard.command().send);
    EXPECT_STREQ(b.guard.command().why, "route_not_ready");
    const auto at = b.now;
    b.in.routeReady = true; b.writesSucceed = true;
    b.now += 10 * second; b.tick();
    ASSERT_EQ(b.since(at).size(), 1u);
    EXPECT_EQ(b.since(at)[0].flowC, 0);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    b.now += 10 * second; b.tick();
    EXPECT_EQ(b.guard.state(), State::shadow); // the window is over and the zero arrived
    EXPECT_FALSE(b.guard.claimsBoiler());
    // A guard whose last delivered request was already zero ends after one window.
    Bench idle; idle.heat(0); idle.runFor(3 * minute);
    ASSERT_EQ(idle.sent.back().flowC, 0);
    idle.writesSucceed = false; idle.in.mode = RoomPlan::Mode::shadow;
    idle.runFor(2 * minute);
    EXPECT_EQ(idle.guard.state(), State::shadow);
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
    b.in.rooms.measured(790); // inactive bathroom at 7.9 degC
    b.tick();
    EXPECT_TRUE(b.guard.command().send);
    EXPECT_EQ(b.guard.command().flowC, 30);
    EXPECT_STREQ(b.guard.command().why, "frost_minimum");
    b.in.rooms.coldestCentiC = 899; b.runFor(minute); // hysteresis holds
    EXPECT_EQ(b.sent.back().flowC, 30);
    b.in.rooms.coldestCentiC = 900; b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 0);
    b.in.rooms.coldestCentiC = 800; b.runFor(minute); // 8.00 degC itself is no frost
    EXPECT_EQ(b.sent.back().flowC, 0);
    // A higher engine request wins over the frost minimum.
    b.in.rooms.coldestCentiC = 400; b.heat(42); b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 42);
    EXPECT_STREQ(b.guard.command().why, "heat_request");
}

TEST(ActiveHeatGuard, RestartHoldsOffUntilListenedAndInputsFresh) {
    Bench b(false); b.now = 0; b.in.rooms.fresh = 0; // just rebooted, no reading yet
    b.guard.confirm(0, true);
    b.runFor(110 * second);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::arming);
    b.in.rooms.fresh = 1; b.runFor(10 * second); // room fresh: the next step heats
    EXPECT_EQ(b.guard.state(), State::active);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0].at, 2 * minute);
    // Fresh at once (stored confirmation, owner 29 Oct): heat within 1 min, not before.
    Bench quick(false); quick.now = 0; quick.guard.confirm(0, true);
    quick.runFor(50 * second);
    EXPECT_TRUE(quick.sent.empty());
    quick.runFor(10 * second);
    ASSERT_EQ(quick.sent.size(), 1u);
    EXPECT_EQ(quick.sent[0].at, minute);
    // The transmit route not ready: still nothing.
    Bench route(false); route.now = 0; route.in.routeReady = false; route.guard.confirm(0, true);
    route.runFor(20 * minute);
    EXPECT_TRUE(route.sent.empty());
    EXPECT_EQ(route.guard.state(), State::arming);
}

TEST(ActiveHeatGuard, RestartWithoutMeasurementOwnsWithZeroAfterThirtyMinutes) {
    Bench b(false); b.now = 0; b.in.rooms.fresh = 0; b.in.rooms.lost = 1;
    b.guard.confirm(0, true);
    b.runFor(29 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::measurementLost));
    b.runFor(2 * minute);
    EXPECT_EQ(b.guard.state(), State::stoppedMeasurementLost);
    ASSERT_FALSE(b.sent.empty());
    EXPECT_EQ(b.sent[0].flowC, 0);
}

TEST(ActiveHeatGuard, FlowNeverAboveThePlanMaximum) {
    Bench b; b.heat(90);
    b.runFor(3 * minute);
    for (const auto& s : b.sent) EXPECT_EQ(s.flowC, 60);
    b.guard.setFlowLimits(30, 50); b.runFor(minute);
    EXPECT_EQ(b.sent.back().flowC, 50);
    // A radiator home may allow up to 80 degC.
    b.in.boilerLimitC = 90; b.heat(90);
    b.guard.setFlowLimits(30, 80); b.runFor(minute);
    EXPECT_EQ(b.sent.back().flowC, 80);
    // A limit above the absolute ceiling is refused: the E32 leaves active with zero.
    b.guard.setFlowLimits(30, 81); b.runFor(2 * minute);
    for (const auto& s : b.sent) EXPECT_LE(s.flowC, 80);
    EXPECT_EQ(b.sent.back().flowC, 0);
    EXPECT_EQ(b.guard.state(), State::shadow);
}

TEST(ActiveHeatGuard, CeilingIsTheLowerOfPlanMaximumAndBoilerLimit) {
    {   // plan 75, boiler set to 55: the boiler's own setting wins
        Bench b; b.guard.setFlowLimits(30, 75); b.in.boilerLimitC = 55; b.heat(90);
        b.runFor(2 * minute);
        ASSERT_FALSE(b.sent.empty());
        for (const auto& s : b.sent) EXPECT_EQ(s.flowC, 55);
    }
    {   // plan 45, boiler set to 70: the plan's maximum wins
        Bench b; b.guard.setFlowLimits(30, 45); b.in.boilerLimitC = 70; b.heat(90);
        b.runFor(2 * minute);
        ASSERT_FALSE(b.sent.empty());
        for (const auto& s : b.sent) EXPECT_EQ(s.flowC, 45);
    }
}

TEST(ActiveHeatGuard, NeverAboveTheBoilersReportedHeatingLimit) {
    Bench b; b.heat(58); b.in.boilerLimitC = 55; // the boiler's own knob
    b.runFor(minute);
    for (const auto& s : b.sent) EXPECT_EQ(s.flowC, 55);
    // Also below the plan minimum the boiler's limit wins.
    b.in.boilerLimitC = 25; b.runFor(minute);
    EXPECT_EQ(b.sent.back().flowC, 25);
    // Unknown limit: the E32 keeps the boiler but asks no heat, and says why.
    b.in.boilerLimitC.reset(); b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 0);
    b.runFor(2 * minute); // after the stop window
    EXPECT_STREQ(b.guard.command().why, "boiler_limit_unknown");
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::boilerLimitUnknown));
    EXPECT_EQ(b.guard.state(), State::active);
    b.in.boilerLimitC = 55; b.runFor(10 * second);
    EXPECT_EQ(b.sent.back().flowC, 55);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::boilerLimitUnknown));
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
    Bench b(false); b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now - minute};
    b.tick();
    Json j(b.guard.json(b.now), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(j.get(), "state")), "awaiting_confirmation");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(j.get(), "awaiting_confirmation")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "last_sent")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "confirmation")));
    const auto* foreign = cJSON_GetObjectItem(j.get(), "foreign_controller");
    EXPECT_EQ(cJSON_GetObjectItem(foreign, "address")->valueint, 0x17);
    EXPECT_EQ(cJSON_GetObjectItem(foreign, "age_s")->valueint, 60);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j.get(), "warnings")), 0);
    b.guard.confirm(b.now, true);
    b.now += 10 * second; b.tick();
    Json k(b.guard.json(b.now + 5 * second), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(k.get(), "state")), "active");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(k.get(), "awaiting_confirmation")));
    const auto* command = cJSON_GetObjectItem(k.get(), "command");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(command, "send")));
    EXPECT_EQ(cJSON_GetObjectItem(command, "flow_c")->valueint, 40);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(command, "why")), "heat_request");
    const auto* sent = cJSON_GetObjectItem(k.get(), "last_sent");
    EXPECT_EQ(cJSON_GetObjectItem(sent, "age_s")->valueint, 5);
    EXPECT_EQ(cJSON_GetObjectItem(sent, "flow_c")->valueint, 40);
    EXPECT_EQ(cJSON_GetObjectItem(cJSON_GetObjectItem(k.get(), "confirmation"), "age_s")->valueint, 15);
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 1};
    b.now += 10 * second; b.tick();
    Json l(b.guard.json(b.now), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(l.get(), "state")), "stopping");
    const auto* warnings = cJSON_GetObjectItem(l.get(), "warnings");
    ASSERT_EQ(cJSON_GetArraySize(warnings), 1);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(warnings, 0)), "foreign_controller");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(l.get(), "confirmation")));
}

// A planned restart (update, settings, controlled restart) while the E32 heats:
// zero first, released once delivered, and no new takeover before the restart.
TEST(ActiveHeatGuard, PlannedRestartWithdrawsWithZeroAndReleases) {
    Bench b; b.runFor(minute);
    ASSERT_EQ(b.guard.state(), State::active);
    ASSERT_EQ(b.sent.back().flowC, 40);
    EXPECT_FALSE(b.guard.released());
    const auto t0 = b.now;
    b.guard.withdraw(b.now);
    EXPECT_EQ(b.guard.state(), State::stopping);
    b.runFor(10 * second);
    ASSERT_FALSE(b.since(t0).empty());
    EXPECT_EQ(b.since(t0).front().flowC, 0);
    EXPECT_TRUE(b.guard.released());
    EXPECT_TRUE(b.guard.confirmed()); // the next boot resumes after its restore listening
    b.runFor(30 * minute); // the restart is late: still no positive request
    for (const auto& s : b.since(t0)) EXPECT_EQ(s.flowC, 0);
    EXPECT_EQ(b.guard.state(), State::stopping);
    EXPECT_TRUE(b.guard.claimsBoiler());
}

TEST(ActiveHeatGuard, PlannedRestartWithFailingWritesIsNotReleased) {
    Bench b; b.runFor(minute);
    b.writesSucceed = false;
    b.guard.withdraw(b.now);
    b.runFor(2 * minute);
    EXPECT_FALSE(b.guard.released()); // the boiler may still hold 40 degC
    // The restart is bounded: BoilerReleaseHold lets it go after 90 s.
    heating::update::BoilerReleaseHold hold;
    EXPECT_FALSE(hold.ready(1000, b.guard.released()));
    EXPECT_FALSE(hold.ready(1000 + 89999, b.guard.released()));
    EXPECT_TRUE(hold.ready(1000 + 90000, b.guard.released()));
    b.writesSucceed = true; b.runFor(10 * second);
    EXPECT_TRUE(b.guard.released());
}

TEST(ActiveHeatGuard, WithdrawWithoutAClaimNeverSendsOrTakesOver) {
    Bench shadow(false); shadow.in.mode = RoomPlan::Mode::shadow;
    shadow.guard.withdraw(shadow.now);
    shadow.runFor(10 * minute);
    EXPECT_TRUE(shadow.sent.empty());
    EXPECT_TRUE(shadow.guard.released());
    EXPECT_FALSE(shadow.guard.claimsBoiler());
    // Arming after a restart (stored confirmation) when the next restart comes: no takeover.
    Bench arming(false); arming.now = 0; arming.guard.restore(0);
    arming.guard.withdraw(0);
    arming.in.boilerHeardAtMs = 0;
    for (int i = 0; i < 60; ++i) { arming.in.boilerHeardAtMs = arming.now; arming.runFor(10 * second); }
    EXPECT_TRUE(arming.sent.empty());
    EXPECT_EQ(arming.guard.state(), State::arming);
    EXPECT_TRUE(arming.guard.released());
}

// Shadow mode (the firmware gate is false): the new restart hook changes nothing.
TEST(ActiveHeatGuard, ShadowStaysSilentWithEveryInputAndTheRestartHook) {
    for (bool withdrawn : {false, true}) {
        Bench b(false); b.in.mode = RoomPlan::Mode::shadow;
        if (withdrawn) b.guard.withdraw(b.now);
        std::vector<std::string> states;
        for (int i = 0; i < 2000; ++i) {
            b.heat(uint8_t(i % 7 ? 30 + i % 25 : 0));
            b.in.rooms.coldestCentiC = int16_t(i % 50 == 0 ? 700 : 2000);
            b.in.foreign = i % 9 ? std::optional<ActiveHeatGuard::Foreign>{} : ActiveHeatGuard::Foreign{0x17, b.now};
            b.in.boiler = {i % 3 == 0, int16_t(3000 + i % 40 * 50)};
            b.in.routeReady = i % 5 != 0;
            if (i == 700) b.guard.confirm(b.now, true); // a confirmation in shadow mode is forgotten
            const auto c = b.tick(); b.now += 10 * second;
            EXPECT_FALSE(c.send);
            states.push_back(ActiveHeatGuard::name(b.guard.state()));
        }
        EXPECT_TRUE(b.sent.empty());
        for (const auto& s : states) EXPECT_EQ(s, "shadow");
        EXPECT_FALSE(b.guard.confirmed());
        EXPECT_TRUE(b.guard.released());
    }
}

// A hot water tap while heating: the boiler serves DHW first; the E32 keeps
// its request unchanged (refreshed every 60 s) and raises no warning.
TEST(ActiveHeatGuard, HotWaterTapDuringHeatingKeepsTheRequest) {
    Bench b; b.runFor(minute);
    b.in.boiler = {true, int16_t(5500)}; // burner on for the tap, flow hot
    const auto t0 = b.now;
    b.runFor(10 * minute);
    b.in.boiler = {false, int16_t(4200)}; b.runFor(5 * minute);
    const auto sent = b.since(t0);
    ASSERT_GE(sent.size(), 14u);
    for (size_t i = 0; i < sent.size(); ++i) {
        EXPECT_EQ(sent[i].flowC, 40);
        if (i) { EXPECT_LE(sent[i].at - sent[i - 1].at, minute); }
    }
    EXPECT_EQ(b.guard.state(), State::active);
    for (auto w : {ActiveHeatGuard::boilerNoResponse, ActiveHeatGuard::transmitFailed, ActiveHeatGuard::measurementLost})
        EXPECT_FALSE(b.guard.warning(w));
}

// A slow loop (MQTT storm, slow Wi-Fi): steps up to 25 s apart. The request is
// still refreshed at the first step after 60 s, no false transmit warning, and
// a stop still sends its zero.
TEST(ActiveHeatGuard, SlowLoopKeepsTheRefreshAndTheStop) {
    Bench b; b.runFor(minute);
    const auto t0 = b.now;
    const uint64_t gaps[] = {25, 7, 18, 25, 3, 25, 25, 11, 25, 9};
    for (int round = 0; round < 20; ++round)
        for (auto g : gaps) { b.now += g * second; b.tick(); }
    const auto sent = b.since(t0);
    ASSERT_GT(sent.size(), 20u);
    for (size_t i = 1; i < sent.size(); ++i) EXPECT_LE(sent[i].at - sent[i - 1].at, minute + 25 * second);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    b.heat(0);
    b.now += 25 * second; const auto c = b.tick();
    EXPECT_TRUE(c.send); EXPECT_EQ(c.flowC, 0);
}

// Wi-Fi or HA gone but the Bluetooth fallback still measures: heating goes on.
TEST(ActiveHeatGuard, FallbackSourceKeepsHeating) {
    Bench b; b.runFor(minute);
    RoomDemand::Spec spec; spec.state = RoomDemand::State::active; spec.sources = 2;
    std::array<RoomDemand::Reading, RoomDemand::maxSources> readings{};
    readings[1] = {2010, b.now}; // HA source gone, Bluetooth reading fresh
    const auto r = RoomDemand::evaluate(spec, readings, int16_t(2100), b.now, RoomDemand::Reading{2010, b.now});
    ASSERT_EQ(r.status, RoomDemand::Status::fallback);
    b.in.rooms = {}; b.in.rooms.add(r);
    const auto t0 = b.now;
    b.runFor(10 * minute);
    EXPECT_EQ(b.guard.state(), State::active);
    for (const auto& s : b.since(t0)) EXPECT_EQ(s.flowC, 40);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::measurementLost));
}

// Power loss with the tado plugged back in meanwhile: the stored confirmation
// listens first; the tado's 0x1A in that window blocks before any heat.
TEST(ActiveHeatGuard, PowerLossThenForeignControllerNeverHeats) {
    Bench b(false); b.now = 0; b.guard.restore(0);
    for (int i = 0; i < 9; ++i) { b.in.boilerHeardAtMs = b.now; b.runFor(10 * second); }
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now};
    for (int i = 0; i < 60; ++i) { b.in.boilerHeardAtMs = b.now; b.runFor(10 * second); }
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_FALSE(b.guard.confirmed());
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
}
}
