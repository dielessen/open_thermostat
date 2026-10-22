#include "control/ZoneRegulator.h"
#include "control/HydraulicSupervisor.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::control;

TEST(ZoneRegulator, BaselineHysteresisAndLocalTrvRetainExistingBandNoSecondPiLoop) {
    for (auto mode : {ZoneControl::hysteresis, ZoneControl::localTrv}) {
        ZoneControlProfile p; p.mode=mode;
        ZoneRegulator z(p);
        EXPECT_FALSE(z.step(0,2100,2100,true).demand);
        EXPECT_TRUE(z.step(1,2080,2100,true).demand);
        EXPECT_TRUE(z.step(2,2100,2100,true).demand);
        EXPECT_FALSE(z.step(3,2120,2100,true).demand);
        EXPECT_FALSE(z.step(4,1900,2100,false).demand);
    }
}
TEST(ZoneRegulator, FractionalPiIntegralIsTickRateIndependent) {
    ZoneControlProfile p{ZoneControl::directPi,20,100,10};
    ZoneRegulator a(p),b(p);
    a.step(0,2000,2100,true); b.step(0,2000,2100,true);
    for(unsigned i=1;i<60;++i) a.step(i*1000,2000,2100,true);
    EXPECT_EQ(a.step(60000,2000,2100,true).dutyPermille,110);
    EXPECT_EQ(b.step(60000,2000,2100,true).dutyPermille,110);
}
TEST(ZoneRegulator, SaturationNoBacklogAfterSourceDeliveryDhwOrGenerationChange) {
    ZoneControlProfile p{ZoneControl::directPi,20,1000,1000};
    ZoneRegulator z(p);
    z.step(0,500,3500,true);
    for(unsigned i=1;i<20;++i) EXPECT_EQ(z.step(i*60000,500,3500,true).dutyPermille,1000);
    EXPECT_EQ(z.step(1200000,2100,2100,true).dutyPermille,0);
    EXPECT_EQ(z.step(1200001,1900,2100,true,false).dutyPermille,0);
    EXPECT_EQ(z.step(1200002,2100,2100,true,true,2).dutyPermille,0);
    EXPECT_EQ(z.step(1,2100,2100,true,true,2).dutyPermille,0);
}
TEST(ZoneRegulator, SlowBinaryMinimumTimesNeverDefeatUnusableOrOff) {
    ZoneControlProfile p{ZoneControl::slowBinaryPi,20,500,0,900000,180000,120000};
    ZoneRegulator z(p);
    EXPECT_FALSE(z.step(0,1900,2100,true).demand); // conservative initial min-off
    EXPECT_TRUE(z.step(120000,1900,2100,true).demand);
    EXPECT_FALSE(z.step(120001,1900,2100,false).demand); // stop beats min-on
    p.cycleMs=1000;
    EXPECT_FALSE(ZoneRegulator(p).step(0,1900,2100,true).demand);
}
TEST(ZoneRegulator, UnknownOutOfRangeAndInvalidProfileNeverDemand) {
    ZoneRegulator z;
    EXPECT_FALSE(z.step(0,std::nullopt,2100,true).demand);
    EXPECT_FALSE(z.step(1,1900,std::nullopt,true).demand);
    EXPECT_FALSE(z.step(2,1900,4000,true).demand);
    ZoneControlProfile bad; bad.hysteresisCentiC=0;
    EXPECT_FALSE(ZoneRegulator(bad).step(0,1900,2100,true).demand);
}

HydraulicProfile qualified() {
    // SYNTHETIC profile, no assertion about an installed actuator/flow path.
    HydraulicProfile p{true,true,true,10000,1000,200,500,300,2000,3500};
    p.flowWaitDeadlineMs=1000;
    p.withdrawalPolicies.fill(WithdrawalPolicy::withdrawHeatOnly);
    for(auto cause:{WithdrawalCause::normalStop,WithdrawalCause::sourceLost,
                   WithdrawalCause::dhwPriority,WithdrawalCause::boilerFault,
                   WithdrawalCause::adapterLost})
        p.withdrawalPolicies[static_cast<size_t>(cause)]=WithdrawalPolicy::retainExistingPathAndPump;
    for(auto cause:{WithdrawalCause::readinessLost,WithdrawalCause::flowLost,WithdrawalCause::limitTrip})
        p.withdrawalPolicies[static_cast<size_t>(cause)]=WithdrawalPolicy::retainExistingPath;
    return p;
}
HydraulicInputs demand() {
    HydraulicInputs in;
    in.adapterAlive=in.sourceValid=in.heatDemand=in.limitsKnownSafe=true;
    in.faultStateKnown=in.dhwStateKnown=true;
    in.waterTarget=3000; return in;
}
HydraulicSupervisor::Result heat(HydraulicSupervisor& s,HydraulicInputs& in) {
    auto r=s.step(0,in);
    in.readinessConfirmed=true; in.feedbackCommand=r.openingCommand;
    in.feedbackAt=100;
    s.step(100,in);
    in.independentFlowConfirmed=true; in.flowAt=in.feedbackAt=300;
    return s.step(300,in);
}
TEST(HydraulicSupervisor, UnknownProfileAndUnknownSafetyNeverImplyReadiness) {
    HydraulicSupervisor none;
    auto in=demand();
    auto r=none.step(0,in);
    EXPECT_STREQ(r.reason,"hydraulic_profile_unqualified");
    EXPECT_FALSE(r.heatIntent); EXPECT_FALSE(r.physicalOutputsEnabled);
    HydraulicSupervisor s(qualified()); in.limitsKnownSafe=false;
    EXPECT_STREQ(s.step(0,in).reason,"limits_unknown");
    in.limitsKnownSafe=true;
    EXPECT_EQ(s.step(1,in).phase,HydraulicPhase::opening);
}
TEST(HydraulicSupervisor, CorrectCommandFreshFeedbackIndependentFlowAndDelayRequired) {
    HydraulicSupervisor s(qualified()); auto in=demand();
    auto r=s.step(0,in); EXPECT_EQ(r.phase,HydraulicPhase::opening);
    in.readinessConfirmed=true; in.feedbackCommand=0; in.feedbackAt=100;
    EXPECT_EQ(s.step(100,in).phase,HydraulicPhase::opening); // old command
    in.feedbackCommand=r.openingCommand; in.feedbackAt=200;
    r=s.step(200,in); EXPECT_EQ(r.phase,HydraulicPhase::pumpWait);
    EXPECT_FALSE(r.heatIntent); EXPECT_TRUE(r.pumpIntent);
    in.feedbackAt=400;
    EXPECT_FALSE(s.step(400,in).heatIntent); // valve readiness is NOT flow
    in.independentFlowConfirmed=true; in.flowAt=in.feedbackAt=401;
    r=s.step(401,in);
    EXPECT_TRUE(r.heatIntent); EXPECT_EQ(r.waterTarget,3000);
    EXPECT_FALSE(r.physicalOutputsEnabled);
}
TEST(HydraulicSupervisor, StopStaleDhwAndInvalidTargetWithdrawImmediatelyWithBoundedPostrun) {
    for(int reason=0;reason<4;++reason) {
        HydraulicSupervisor s(qualified()); auto in=demand();
        ASSERT_TRUE(heat(s,in).heatIntent);
        if(reason==0) in.stop=true;
        if(reason==1) in.sourceValid=false;
        if(reason==2) in.dhwActive=true;
        if(reason==3) in.waterTarget=3600;
        auto r=s.step(301,in);
        EXPECT_FALSE(r.heatIntent); EXPECT_FALSE(r.waterTarget);
        EXPECT_EQ(r.phase,HydraulicPhase::postrun);
        EXPECT_TRUE(r.openPathIntent); EXPECT_TRUE(r.pumpIntent);
        r=s.step(801,in); EXPECT_FALSE(r.heatIntent); EXPECT_FALSE(r.pumpIntent);
    }
}
TEST(HydraulicSupervisor, ReadinessFlowLossAndOpeningTimeoutLatchUntilVerifiedRecovery) {
    for(int mode=0;mode<2;++mode) {
        HydraulicSupervisor s(qualified()); auto in=demand(); ASSERT_TRUE(heat(s,in).heatIntent);
        if(mode==0) in.readinessConfirmed=false; else in.independentFlowConfirmed=false;
        auto r=s.step(301,in); EXPECT_EQ(r.phase,HydraulicPhase::fault); EXPECT_FALSE(r.heatIntent);
        in.readinessConfirmed=in.independentFlowConfirmed=true; in.flowAt=in.feedbackAt=302;
        EXPECT_EQ(s.step(302,in).phase,HydraulicPhase::fault);
        EXPECT_FALSE(s.clearFault(false)); EXPECT_TRUE(s.clearFault(true));
        EXPECT_EQ(s.step(303,in).phase,HydraulicPhase::postrun);
        EXPECT_EQ(s.step(801,in).phase,HydraulicPhase::opening);
    }
    HydraulicSupervisor s(qualified()); auto in=demand();
    s.step(0,in); EXPECT_EQ(s.step(10000,in).phase,HydraulicPhase::fault);
}
TEST(HydraulicSupervisor, MinimumOffDoesNotTurnIdleIntoDemandAndLimitsAlwaysWin) {
    auto p=qualified(); p.minimumOffMs=5000;
    HydraulicSupervisor s(p); auto in=demand();
    EXPECT_FALSE(heat(s,in).heatIntent);
    in.feedbackAt=in.flowAt=900; EXPECT_FALSE(s.step(900,in).heatIntent);
    in.heatDemand=false; EXPECT_FALSE(s.step(901,in).heatIntent);
    in.heatDemand=true; in.limitTripped=true;
    EXPECT_EQ(s.step(902,in).phase,HydraulicPhase::fault);
    EXPECT_FALSE(s.step(903,in).heatIntent);
}
TEST(HydraulicSupervisor, BackwardClockReconnectAndBoilerFaultNeverCarryHeatReadiness) {
    HydraulicSupervisor s(qualified()); auto in=demand();
    ASSERT_TRUE(heat(s,in).heatIntent);
    EXPECT_EQ(s.step(299,in).phase,HydraulicPhase::fault);
    EXPECT_TRUE(s.clearFault(true));
    auto r=s.step(500,in); EXPECT_FALSE(r.heatIntent);
    s.invalidate(); EXPECT_FALSE(s.step(600,in).heatIntent);
    in.boilerFault=true; EXPECT_EQ(s.step(601,in).phase,HydraulicPhase::fault);
}
}
