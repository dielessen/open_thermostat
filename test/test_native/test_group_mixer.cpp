#include "control/GroupWaterPolicy.h"
#include "control/MixerPolicy.h"
#include "control/HydraulicSupervisor.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::control;
GroupWaterProfile radiator() {
    GroupWaterProfile p;
    p.qualified=p.independentHighLimit=true;
    p.curveCentiC={2500,3000,3500,4000,4500,5000,5500,6000,6500};
    p.minimumCentiC=2000;p.maximumCentiC=7000;p.correctionLimitCentiC=300;
    return p;
}
GroupWaterProfile floor() {
    auto p=radiator();p.emitter=EmitterType::floor;p.maximumCentiC=3500;
    p.independentFloorCutout=p.floorSensorRequired=true;
    p.floorMaximumCentiC=2900;p.curveCentiC={2000,2100,2200,2400,2600,2800,3000,3200,3500};
    return p;
}
GroupWaterInput warm() {
    GroupWaterInput i;
    i.demand=i.sourceValid=i.deliveryAvailable=i.independentLimitHealthy=i.outdoorFresh=true;
    i.outdoorCentiC=750;i.roomErrorCentiC=100;
    i.floorSensorFresh=true;i.floorCentiC=2200;return i;
}
TEST(GroupWater, FractionalCurveAndBoundedRoomCorrectionUseActualUnits) {
    auto p=radiator();auto in=warm();
    EXPECT_EQ(interpolateWaterCurve(750,p.curveCentiC),3750);
    EXPECT_EQ(groupWaterTarget(p,in).target,3850);
    in.roomErrorCentiC=1000;EXPECT_EQ(groupWaterTarget(p,in).target,4050);
    in.roomErrorCentiC=-1000;EXPECT_EQ(groupWaterTarget(p,in).target,3450);
    p.curveCentiC[3]=4011;EXPECT_EQ(interpolateWaterCurve(750,p.curveCentiC),3755);
}
TEST(GroupWater, NoDemandIsNotPermanentMinimumAndNoStaleOutdoorDefault) {
    auto p=radiator();auto in=warm();in.demand=false;
    EXPECT_FALSE(groupWaterTarget(p,in).target);
    in.demand=true;in.outdoorFresh=false;EXPECT_FALSE(groupWaterTarget(p,in).target);
    p.fixedOutdoorFallback=3000;
    auto r=groupWaterTarget(p,in);EXPECT_EQ(r.target,3100);
    EXPECT_STREQ(r.reason,"shadow_fixed_fallback_target");
    p.fixedOutdoorFallback=8000;EXPECT_FALSE(p.valid());
}
TEST(GroupWater, HighestActiveGroupIsNotAverageOrBurnerModulation) {
    std::array<GroupWaterProfile,2> p{radiator(),radiator()};
    std::array<GroupWaterInput,2> in{warm(),warm()};
    in[1].outdoorCentiC=-1000;
    EXPECT_EQ(aggregateWaterTargets(p.data(),in.data(),2,{true,2000,7000}).target,5600);
    in[1].demand=false;
    EXPECT_EQ(aggregateWaterTargets(p.data(),in.data(),2,{true,2000,7000}).target,3850);
    in[0].demand=false;
    EXPECT_FALSE(aggregateWaterTargets(p.data(),in.data(),2,{true,2000,7000}).target);
}
TEST(GroupWater, ShutInactiveFloorValveIsNotIndependentMixingBarrier) {
    std::array<GroupWaterProfile,2> p{radiator(),floor()};
    std::array<GroupWaterInput,2> in{warm(),warm()};in[1].demand=false;
    auto r=aggregateWaterTargets(p.data(),in.data(),2,{true,2000,7000});
    EXPECT_FALSE(r.target);EXPECT_STREQ(r.reason,"floor_requires_mixing_or_shared_safe_limit");
    p[1].qualifiedMixing=true;
    EXPECT_EQ(aggregateWaterTargets(p.data(),in.data(),2,{true,2000,7000}).target,3850);
    p[1].qualifiedMixing=false;p[0].maximumCentiC=3500;
    EXPECT_EQ(aggregateWaterTargets(p.data(),in.data(),2,{true,2000,3500}).target,3500);
}
TEST(GroupWater, FloorSensorTripOrUnknownPhysicalLimitBlocksNotAssumedSafe) {
    auto p=floor();auto in=warm();
    in.floorSensorFresh=false;EXPECT_TRUE(groupWaterTarget(p,in).safetyInhibit);
    in.floorSensorFresh=true;in.floorCentiC=2900;
    EXPECT_TRUE(groupWaterTarget(p,in).safetyInhibit);
    in.floorCentiC=2200;in.independentLimitHealthy=false;
    EXPECT_TRUE(groupWaterTarget(p,in).safetyInhibit);
    p.independentFloorCutout=false;EXPECT_FALSE(p.valid());
}
TEST(GroupWater, InvalidProfilesMissingRoomEvidenceAndBoilerBoundsFailClosed) {
    auto p=radiator();auto in=warm();
    in.roomErrorCentiC.reset();EXPECT_FALSE(groupWaterTarget(p,in).target);
    in=warm();EXPECT_FALSE(aggregateWaterTargets(&p,&in,1,{true,2000,3000}).target);
    p.curveCentiC[2]=1000;EXPECT_FALSE(p.valid());
    EXPECT_FALSE(aggregateWaterTargets(nullptr,nullptr,0,{}).target);
}
TEST(GroupWater, WriteBudgetSlewDeadbandStopAndClockResetAreSeparateFromBoilerEnable) {
    WaterWriteBudget w({10000,10,600});
    EXPECT_EQ(w.step(0,3000).waterTarget,3000);
    EXPECT_FALSE(w.step(1000,4000).publishIntent);
    EXPECT_EQ(w.step(10000,4000).waterTarget,3100);
    EXPECT_FALSE(w.step(20000,3105).publishIntent);
    auto stop=w.step(20001,std::nullopt);
    EXPECT_TRUE(stop.publishIntent);EXPECT_FALSE(stop.waterTarget);
    EXPECT_FALSE(w.step(20002,std::nullopt).publishIntent);
    EXPECT_EQ(w.step(20003,3000).waterTarget,3000);
    stop=w.step(1,4000);EXPECT_TRUE(stop.publishIntent);EXPECT_FALSE(stop.waterTarget);
}

MixerProfile threePoint() {
    MixerProfile p;
    p.qualified=p.coldDirectionVerified=p.independentLimitsValidated=true;
    p.travelMs=10000;p.feedbackTtlMs=1000;p.reversalDeadMs=200;p.minimumWriteMs=1000;
    p.minimumWaterCentiC=2000;p.maximumWaterCentiC=3500;p.deadbandCentiC=20;
    return p;
}
MixerInput mixerInput(uint64_t now) {
    MixerInput i;i.adapterAlive=i.independentLimitsHealthy=i.supplyFresh=true;
    i.supplyCentiC=2500;i.targetCentiC=3000;i.supplyAt=now;
    return i;
}
void reference(MixerPolicy& m,MixerInput& in) {
    in.requestReference=true;in.referenceSafeConfirmed=true;
    auto r=m.step(0,in);ASSERT_TRUE(r.colderIntent);
    in.coldEndSwitch=true;in.feedbackCommand=r.command;in.feedbackAt=100;
    EXPECT_TRUE(m.step(100,in).referenceKnown);
    in.requestReference=false;in.coldEndSwitch=false;
}
TEST(MixerPolicy, UnqualifiedNoReferenceOrOldSwitchNeverMovesByAssumption) {
    MixerPolicy bad({});auto i=mixerInput(0);
    EXPECT_FALSE(bad.step(0,i).colderIntent);
    MixerPolicy m(threePoint());EXPECT_STREQ(m.step(0,i).reason,"mixer_reference_not_safe");
    i.referenceSafeConfirmed=true;
    EXPECT_STREQ(m.step(0,i).reason,"mixer_reference_required");
    i.requestReference=true;i.coldEndSwitch=true;i.feedbackAt=0;i.feedbackCommand=1;
    auto r=m.step(0,i);EXPECT_FALSE(r.referenceKnown);EXPECT_TRUE(r.colderIntent);
}
TEST(MixerPolicy, ColdReferenceThenWarmColdReversalAlwaysHasDeadtimeNotBothDirections) {
    MixerPolicy m(threePoint());auto i=mixerInput(0);reference(m,i);
    i.supplyAt=299;EXPECT_FALSE(m.step(299,i).warmerIntent);
    i.supplyAt=300;auto r=m.step(300,i);EXPECT_TRUE(r.warmerIntent);EXPECT_FALSE(r.colderIntent);
    i.supplyCentiC=3200;i.supplyAt=301;r=m.step(301,i);
    EXPECT_FALSE(r.warmerIntent);EXPECT_FALSE(r.colderIntent);
    i.supplyAt=501;r=m.step(501,i);EXPECT_FALSE(r.warmerIntent);EXPECT_TRUE(r.colderIntent);
}
TEST(MixerPolicy, ReferenceTimeoutIsFaultNotInventedPositionUnlessExplicitTimedProfile) {
    for(bool timed:{false,true}) {
        auto p=threePoint();p.timedReferenceValidated=timed;
        MixerPolicy m(p);auto i=mixerInput(0);i.requestReference=i.referenceSafeConfirmed=true;
        m.step(0,i);i.supplyAt=10000;auto r=m.step(10000,i);
        EXPECT_EQ(r.referenceKnown,timed);EXPECT_EQ(r.fault,!timed);
        EXPECT_FALSE(r.warmerIntent);EXPECT_FALSE(r.colderIntent);
    }
}
TEST(MixerPolicy, StaleSupplyDisconnectAndOvertemperatureWithdrawMotorIntent) {
    MixerPolicy m(threePoint());auto i=mixerInput(0);reference(m,i);
    i.supplyAt=300;ASSERT_TRUE(m.step(300,i).warmerIntent);
    auto r=m.step(1300,i);EXPECT_FALSE(r.warmerIntent);EXPECT_FALSE(r.colderIntent);
    i.supplyAt=1301;i.supplyCentiC=3500;
    r=m.step(1301,i);EXPECT_TRUE(r.fault);EXPECT_FALSE(r.warmerIntent);
    EXPECT_FALSE(m.clearFault(false));EXPECT_TRUE(m.clearFault(true));
    i.adapterAlive=false;r=m.step(1302,i);EXPECT_FALSE(r.referenceKnown);
}
TEST(MixerPolicy, MaximumTravelAndReverseClockCannotKeepDriving) {
    MixerPolicy m(threePoint());auto i=mixerInput(0);reference(m,i);
    i.supplyAt=300;ASSERT_TRUE(m.step(300,i).warmerIntent);
    i.supplyAt=10300;auto r=m.step(10300,i);EXPECT_TRUE(r.fault);EXPECT_FALSE(r.warmerIntent);
    EXPECT_TRUE(m.clearFault(true));m.step(20000,i);
    EXPECT_TRUE(m.step(19999,i).fault);
}
TEST(MixerPolicy, AnalogNeedsAbsolutePositionAndMatchingFreshPostCommandFeedback) {
    auto p=threePoint();p.kind=MixerKind::analog0to10;
    p.coldMillivolts=1000;p.warmMillivolts=9000;
    p.analogStepPermillePerMinute=600;p.positionTolerancePermille=5;
    MixerPolicy m(p);auto i=mixerInput(0);
    EXPECT_STREQ(m.step(0,i).reason,"mixer_position_unavailable");
    i.positionFresh=true;i.positionPermille=0;i.feedbackAt=0;
    EXPECT_FALSE(m.step(0,i).analogMillivolts);
    i.supplyAt=i.feedbackAt=1000;
    auto r=m.step(1000,i);ASSERT_TRUE(r.analogMillivolts);EXPECT_EQ(r.analogMillivolts,1080);
    i.supplyAt=i.feedbackAt=2000;i.positionPermille=10;i.feedbackCommand=0;
    EXPECT_FALSE(m.step(2000,i).analogMillivolts); // no same-session stale ACK adoption
    i.feedbackCommand=r.command;r=m.step(2000,i);
    ASSERT_TRUE(r.analogMillivolts);EXPECT_EQ(r.analogMillivolts,1160);
    i.supplyAt=i.feedbackAt=12000;i.positionPermille=10;
    r=m.step(12000,i);EXPECT_TRUE(r.fault);EXPECT_FALSE(r.analogMillivolts);
}
TEST(HydraulicSupervisor, PredatingOrSameTickFlowAndReadinessCannotAuthorizeOpening) {
    HydraulicProfile p{true,true,true,10000,1000,0,0,0,2000,3500};
    p.flowWaitDeadlineMs=1000;
    p.withdrawalPolicies.fill(WithdrawalPolicy::withdrawHeatOnly);
    HydraulicSupervisor h(p);HydraulicInputs i;
    i.adapterAlive=i.sourceValid=i.heatDemand=i.limitsKnownSafe=i.faultStateKnown=i.dhwStateKnown=true;
    i.waterTarget=3000;
    auto r=h.step(0,i);
    i.readinessConfirmed=i.independentFlowConfirmed=true;
    i.feedbackCommand=r.openingCommand;i.feedbackAt=i.flowAt=0;
    EXPECT_FALSE(h.step(0,i).heatIntent);
    i.feedbackAt=i.flowAt=1;EXPECT_TRUE(h.step(1,i).heatIntent);
}

TEST(MixerPolicy, StaleSupplyDuringReferenceCancelsIntentWithoutAssumedEndpoint) {
    MixerPolicy m(threePoint());auto i=mixerInput(0);
    i.requestReference=i.referenceSafeConfirmed=true;
    ASSERT_TRUE(m.step(0,i).colderIntent);
    auto r=m.step(1000,i);
    EXPECT_FALSE(r.colderIntent);EXPECT_FALSE(r.referenceKnown);
    EXPECT_STREQ(r.reason,"mixer_supply_unavailable");
}

}
