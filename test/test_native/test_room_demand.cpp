#include "control/FlowDemand.h"
#include "control/RoomDemand.h"
#include <gtest/gtest.h>

namespace {
using heating::control::FlowDemand;
using heating::control::RoomDemand;
using Status = RoomDemand::Status;
constexpr uint64_t minute = 60000;

RoomDemand::Spec livingRoom() {
    RoomDemand::Spec s; s.state = RoomDemand::State::active; s.sources = 2; // tado via HA, then Bluetooth
    return s;
}
std::array<RoomDemand::Reading, RoomDemand::maxSources> readings(std::optional<int16_t> tado, uint64_t tadoAt,
                                                                 std::optional<int16_t> ble, uint64_t bleAt) {
    return {{{tado, tadoAt}, {ble, bleAt}, {}, {}}};
}

TEST(RoomDemand, PrimarySourceLeadsWhenFresh) {
    const auto r = RoomDemand::evaluate(livingRoom(), readings(2050, 100 * minute, 2120, 100 * minute), 2100, 101 * minute, {});
    EXPECT_EQ(r.status, Status::ok); EXPECT_EQ(r.source, 0);
    EXPECT_EQ(*r.temperature, 2050); EXPECT_EQ(r.errorCentiC, 50); EXPECT_TRUE(r.usable);
}
TEST(RoomDemand, BluetoothTakesOverWhenTheTadoReadingIsOld) {
    const auto r = RoomDemand::evaluate(livingRoom(), readings(2050, 80 * minute, 2120, 100 * minute), 2100, 101 * minute, {});
    EXPECT_EQ(r.status, Status::fallback); EXPECT_EQ(r.source, 1); EXPECT_EQ(*r.temperature, 2120);
}
TEST(RoomDemand, OnlyBluetoothConfiguredIsPrimary) {
    auto spec = livingRoom(); spec.sources = 1;
    const auto r = RoomDemand::evaluate(spec, {{{1900, 100 * minute}, {}, {}, {}}}, 2000, 101 * minute, {});
    EXPECT_EQ(r.status, Status::ok); EXPECT_EQ(r.source, 0); EXPECT_EQ(r.errorCentiC, 100);
}
TEST(RoomDemand, WithoutAnySourceTheLastValueHoldsForThirtyMinutesThenTheRoomStops) {
    const RoomDemand::Reading last{2000, 100 * minute};
    const auto none = readings(std::nullopt, 0, std::nullopt, 0);
    auto held = RoomDemand::evaluate(livingRoom(), none, 2100, 129 * minute, last);
    EXPECT_EQ(held.status, Status::stale); EXPECT_TRUE(held.usable); EXPECT_EQ(held.errorCentiC, 100);
    auto lost = RoomDemand::evaluate(livingRoom(), none, 2100, 130 * minute, last);
    EXPECT_EQ(lost.status, Status::lost); EXPECT_FALSE(lost.usable);
}
TEST(RoomDemand, InactiveRoomNeverAsksForHeat) {
    auto bath = livingRoom(); bath.state = RoomDemand::State::inactive;
    const auto cold = readings(1500, 100 * minute, std::nullopt, 0);
    const auto r = RoomDemand::evaluate(bath, cold, 2200, 101 * minute, {});
    EXPECT_EQ(r.status, Status::inactive); EXPECT_FALSE(r.usable);
}
TEST(RoomDemand, SetpointIsClampedAndMissingSetpointGivesNoDemand) {
    auto r = RoomDemand::evaluate(livingRoom(), readings(2000, minute, std::nullopt, 0), 4000, minute, {});
    EXPECT_EQ(*r.setpoint, 3000);
    r = RoomDemand::evaluate(livingRoom(), readings(2000, minute, std::nullopt, 0), std::nullopt, minute, {});
    EXPECT_FALSE(r.usable); EXPECT_EQ(r.status, Status::ok);
}
TEST(RoomDemand, FutureTimestampsAreNotTrusted) {
    const auto r = RoomDemand::evaluate(livingRoom(), readings(2000, 5 * minute, std::nullopt, 0), 2100, minute, {});
    EXPECT_EQ(r.status, Status::lost);
}

TEST(FlowDemand, StartsOnRoomDemandAndModulatesWithTheShortfall) {
    FlowDemand f;
    EXPECT_FALSE(f.update(0, false, 10).heat);
    auto r = f.update(minute, true, 50); // 0.5 degC too cold
    EXPECT_TRUE(r.heat); EXPECT_EQ(r.flowC, 35);
    r = f.update(2 * minute, true, 150);
    EXPECT_EQ(r.flowC, 45);
}
TEST(FlowDemand, NeverExceedsThePlanMaximum) {
    FlowDemand f;
    auto r = f.update(0, true, 1000);
    for (uint64_t t = minute; t < 600 * minute; t += minute) r = f.update(t, true, 1000);
    EXPECT_EQ(r.flowC, 60);
    FlowDemand::Params radiators; radiators.maximumFlowC = 80;
    EXPECT_TRUE(radiators.valid());
    FlowDemand hot(radiators);
    r = hot.update(0, true, 1000);
    for (uint64_t t = minute; t < 600 * minute; t += minute) r = hot.update(t, true, 1000);
    EXPECT_EQ(r.flowC, 80);
    FlowDemand::Params tooHot; tooHot.maximumFlowC = 81;
    EXPECT_FALSE(tooHot.valid());
    EXPECT_FALSE(FlowDemand(tooHot).update(0, true, 500).heat);
}
// The boiler's own limit (0x16) caps the rule too, flagged as capped; unknown:
// the plan's ceiling. The integral does not wind up above the limit.
TEST(FlowDemand, TheBoilersOwnLimitCapsTheRequestAndSaysSo) {
    FlowDemand f;
    f.setBoilerLimit(45);
    auto r = f.update(0, true, 100); // 1 degC short: 40, below the limit
    EXPECT_EQ(r.flowC, 40); EXPECT_FALSE(r.capped);
    for (uint64_t t = minute; t < 600 * minute; t += minute) r = f.update(t, true, 1000);
    EXPECT_EQ(r.flowC, 45); EXPECT_TRUE(r.capped); EXPECT_EQ(r.reason, FlowDemand::Reason::heating);
    f.setBoilerLimit(std::nullopt); // unknown: back to the plan maximum
    r = f.update(601 * minute, true, 1000);
    EXPECT_EQ(r.flowC, 60); EXPECT_FALSE(r.capped);
    f.setBoilerLimit(70); // above the plan maximum: the plan limits, not capped
    EXPECT_FALSE(f.update(602 * minute, true, 1000).capped);
    f.setBoilerLimit(25); // below the plan minimum: the boiler's limit wins
    r = f.update(603 * minute, true, 100);
    EXPECT_EQ(r.flowC, 25); EXPECT_TRUE(r.capped);
    // No wind-up while capped: a limit of 35 for an hour at 0.5 degC short, then lifted.
    FlowDemand g; g.setBoilerLimit(35);
    for (uint64_t t = 0; t <= 60 * minute; t += minute) r = g.update(t, true, 50);
    EXPECT_EQ(r.flowC, 35); EXPECT_TRUE(r.capped);
    g.setBoilerLimit(std::nullopt);
    EXPECT_EQ(g.update(61 * minute, true, 50).flowC, 35); // the integral stayed at the cap
    EXPECT_FALSE(g.update(62 * minute, false, -50).capped); // satisfied: off, nothing capped
}
TEST(FlowDemand, PersistentSmallShortfallSlowlyRaisesTheFlow) {
    FlowDemand f;
    const auto first = f.update(0, true, 50).flowC;
    uint8_t later = first;
    for (uint64_t t = minute; t <= 30 * minute; t += minute) later = f.update(t, true, 50).flowC;
    EXPECT_EQ(first, 35); EXPECT_EQ(later, 40); // +0.5 degC x 30 min adds 5 degC
}
TEST(FlowDemand, MinimumOnAndOffTimesProtectTheBurner) {
    FlowDemand f;
    ASSERT_TRUE(f.update(0, true, 100).heat);
    auto r = f.update(2 * minute, false, -20); // satisfied, but only 2 minutes on
    EXPECT_TRUE(r.heat); EXPECT_EQ(r.reason, FlowDemand::Reason::holdOn);
    r = f.update(5 * minute, false, -20);
    EXPECT_FALSE(r.heat); EXPECT_EQ(r.reason, FlowDemand::Reason::satisfied);
    r = f.update(7 * minute, true, 100); // demand again after 2 minutes off
    EXPECT_FALSE(r.heat); EXPECT_EQ(r.reason, FlowDemand::Reason::holdOff);
    EXPECT_TRUE(f.update(10 * minute, true, 100).heat);
}
TEST(FlowDemand, LostOrInactiveRoomsStopImmediatelyDespiteMinimumOn) {
    FlowDemand f;
    ASSERT_TRUE(f.update(0, true, 100).heat);
    const auto r = f.update(minute, true, std::nullopt);
    EXPECT_FALSE(r.heat); EXPECT_EQ(r.reason, FlowDemand::Reason::noDemand);
}
}
