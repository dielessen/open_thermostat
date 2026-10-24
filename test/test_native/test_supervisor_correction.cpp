#include "control/HydraulicSupervisor.h"
#include <gtest/gtest.h>
namespace {
using namespace heating::control;
using C=WithdrawalCause;
using P=WithdrawalPolicy;
HydraulicProfile policy() {
    HydraulicProfile p{true,true,true,10000,1000,200,500,300,2000,3500};
    p.flowWaitDeadlineMs=1000;
    p.withdrawalPolicies.fill(P::withdrawHeatOnly);
    for(auto cause:{C::normalStop,C::sourceLost,C::dhwPriority,C::boilerFault,C::adapterLost})
        p.withdrawalPolicies[static_cast<size_t>(cause)]=P::retainExistingPathAndPump;
    for(auto cause:{C::readinessLost,C::flowLost,C::limitTrip})
        p.withdrawalPolicies[static_cast<size_t>(cause)]=P::retainExistingPath;
    return p;
}
HydraulicInputs input() {
    HydraulicInputs i;
    i.adapterAlive=i.sourceValid=i.heatDemand=i.limitsKnownSafe=i.faultStateKnown=i.dhwStateKnown=true;
    i.waterTarget=3000;return i;
}
void heating(HydraulicSupervisor& h,HydraulicInputs& i) {
    auto r=h.step(0,i);
    i.readinessConfirmed=true;i.feedbackCommand=r.openingCommand;i.feedbackAt=100;
    h.step(100,i);i.independentFlowConfirmed=true;i.flowAt=i.feedbackAt=300;
    ASSERT_TRUE(h.step(300,i).heatIntent);
}
TEST(SupervisorCorrection, ExactParentNeverFlowProbeHasBoundedDeadlineEvenWithContinuouslyFreshReady) {
    HydraulicSupervisor h(policy());auto i=input();
    auto r=h.step(0,i);
    i.readinessConfirmed=true;i.feedbackCommand=r.openingCommand;i.feedbackAt=100;
    ASSERT_TRUE(h.step(100,i).pumpIntent);
    for(uint64_t t=200;t<1100;t+=100) {
        i.feedbackAt=t;r=h.step(t,i);
        EXPECT_FALSE(r.heatIntent);EXPECT_TRUE(r.pumpIntent);EXPECT_FALSE(r.physicalOutputsEnabled);
    }
    i.feedbackAt=1100;r=h.step(1100,i);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.heatIntent);
    EXPECT_STREQ(r.reason,"flow_or_pump_wait_timeout");
    i.feedbackAt=3600000;r=h.step(3600000,i);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
}
TEST(SupervisorCorrection, ParentOneHourJumpCannotStartLatePostrunAfterExpiredDeadline) {
    auto p=policy();p.withdrawalPolicies[static_cast<size_t>(C::flowLost)]=P::retainExistingPathAndPump;
    HydraulicSupervisor h(p);auto i=input();
    auto r=h.step(0,i);i.readinessConfirmed=true;i.feedbackCommand=r.openingCommand;i.feedbackAt=100;
    h.step(100,i);i.feedbackAt=3600000;r=h.step(3600000,i);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
}
TEST(SupervisorCorrection, ExactBoilerFaultWithdrawsHeatAndKeepsOnlyQualifiedBoundedPriorPostrun) {
    HydraulicSupervisor h(policy());auto i=input();heating(h,i);
    i.boilerFault=true;auto r=h.step(301,i);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.heatIntent);
    EXPECT_TRUE(r.openPathIntent);EXPECT_TRUE(r.pumpIntent);
    EXPECT_EQ(r.pathIntent,HydraulicPathIntent::retainExistingPath);
    EXPECT_FALSE(r.waterTarget);EXPECT_FALSE(r.physicalOutputsEnabled);
    for(uint64_t t:{400,600,800}) {
        i.feedbackAt=i.flowAt=t;r=h.step(t,i);
        EXPECT_TRUE(r.pumpIntent);EXPECT_FALSE(r.heatIntent);
    }
    i.feedbackAt=i.flowAt=801;r=h.step(801,i);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);EXPECT_FALSE(r.heatIntent);
}
TEST(SupervisorCorrection, FaultCannotStartPumpOrOpenPathThatWasNotAlreadyRequested) {
    HydraulicSupervisor h(policy());auto i=input();
    i.boilerFault=true;auto r=h.step(0,i);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
    EXPECT_FALSE(r.heatIntent);EXPECT_EQ(r.phase,HydraulicPhase::fault);
}
TEST(SupervisorCorrection, MissingCausePolicyOrUnboundedFlowWaitMakesProfileUnqualified) {
    auto p=policy();p.withdrawalPolicies[static_cast<size_t>(C::limitTrip)]=P::unspecified;
    EXPECT_FALSE(p.valid());HydraulicSupervisor h(p);auto i=input();
    EXPECT_STREQ(h.step(0,i).reason,"hydraulic_profile_unqualified");
    p=policy();p.flowWaitDeadlineMs=0;EXPECT_FALSE(p.valid());
    p=policy();p.flowWaitDeadlineMs=600001;EXPECT_FALSE(p.valid());
}
TEST(SupervisorCorrection, DifferentReviewedFaultPoliciesNotUniversalPumpOrSafePositionDefaults) {
    for(auto chosen:{P::withdrawHeatOnly,P::retainExistingPath,P::retainExistingPathAndPump}) {
        auto p=policy();p.withdrawalPolicies[static_cast<size_t>(C::boilerFault)]=chosen;
        HydraulicSupervisor h(p);auto i=input();heating(h,i);
        i.boilerFault=true;auto r=h.step(301,i);
        EXPECT_FALSE(r.heatIntent);
        EXPECT_EQ(r.openPathIntent,chosen>=P::retainExistingPath);
        EXPECT_EQ(r.pumpIntent,chosen==P::retainExistingPathAndPump);
        EXPECT_FALSE(r.physicalOutputsEnabled);
    }
}
TEST(SupervisorCorrection, ReadinessLossFlowLossLimitTripAndAdapterLossHaveExplicitBoundedPolicies) {
    for(int failure=0;failure<4;++failure) {
        HydraulicSupervisor h(policy());auto i=input();heating(h,i);
        if(failure==0)i.readinessConfirmed=false;
        if(failure==1)i.independentFlowConfirmed=false;
        if(failure==2)i.limitTripped=true;
        if(failure==3)i.adapterAlive=false;
        auto r=h.step(301,i);
        EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.heatIntent);
        EXPECT_TRUE(r.openPathIntent);EXPECT_EQ(r.pumpIntent,failure==3);
        i=input();i.readinessConfirmed=i.independentFlowConfirmed=true;
        i.feedbackCommand=r.openingCommand;i.flowAt=i.feedbackAt=400;
        r=h.step(400,i);EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.heatIntent);
        EXPECT_FALSE(h.clearFault(false));EXPECT_TRUE(h.clearFault(true));
        r=h.step(401,i);EXPECT_EQ(r.phase,HydraulicPhase::postrun);EXPECT_FALSE(r.heatIntent);
        i.flowAt=i.feedbackAt=801;r=h.step(801,i);
        EXPECT_EQ(r.phase,HydraulicPhase::opening);EXPECT_FALSE(r.heatIntent);
        EXPECT_FALSE(r.physicalOutputsEnabled);
    }
}
TEST(SupervisorCorrection, EscalationNeverRenewsDeadlineOrResurrectsRestrictedPump) {
    HydraulicSupervisor h(policy());auto i=input();heating(h,i);
    i.boilerFault=true;ASSERT_TRUE(h.step(301,i).pumpIntent);
    i.limitTripped=true;auto r=h.step(400,i);
    EXPECT_FALSE(r.pumpIntent);EXPECT_TRUE(r.openPathIntent);
    i.limitTripped=false;i.flowAt=i.feedbackAt=500;
    EXPECT_FALSE(h.step(500,i).pumpIntent);
    i.flowAt=i.feedbackAt=801;r=h.step(801,i);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
}
TEST(SupervisorCorrection, TransportInvalidationWithdrawsAndLatchesWithoutDiscardingReviewedRetention) {
    HydraulicSupervisor h(policy());auto i=input();heating(h,i);
    h.invalidate();auto r=h.lastIntent();
    EXPECT_FALSE(r.heatIntent);EXPECT_TRUE(r.pumpIntent);EXPECT_TRUE(r.openPathIntent);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);
    i.flowAt=i.feedbackAt=801;r=h.step(801,i);
    EXPECT_FALSE(r.heatIntent);EXPECT_FALSE(r.pumpIntent);EXPECT_EQ(r.phase,HydraulicPhase::fault);
}

TEST(SupervisorCorrection, DisconnectedLocalTicksExpireReviewedPostrunWithoutExtendingIt) {
    HydraulicSupervisor h(policy());auto i=input();heating(h,i);
    h.invalidate();
    auto r=h.advanceWithoutOwner(301);
    EXPECT_FALSE(r.heatIntent);EXPECT_TRUE(r.pumpIntent);EXPECT_TRUE(r.openPathIntent);
    for(uint64_t t:{400,600,799}) {
        r=h.advanceWithoutOwner(t);
        EXPECT_TRUE(r.pumpIntent);EXPECT_FALSE(r.heatIntent);
    }
    r=h.advanceWithoutOwner(800); // Last qualified state300 + original postrun500.
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
    EXPECT_FALSE(r.heatIntent);EXPECT_EQ(r.phase,HydraulicPhase::fault);
    r=h.advanceWithoutOwner(900);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
    EXPECT_FALSE(r.physicalOutputsEnabled);
}

TEST(SupervisorCorrection, OfflineTickCannotStartAnyPathPumpOrHeatBeforeFirstOwner) {
    HydraulicSupervisor h(policy());
    for(uint64_t t:{0,1,1000,10000}) {
        const auto r=h.advanceWithoutOwner(t);
        EXPECT_FALSE(r.heatIntent);EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
        EXPECT_FALSE(r.physicalOutputsEnabled);
    }
}

TEST(SupervisorCorrection, ClockReversalCannotResurrectExpiredWithdrawalEvenWithRetainingTimingPolicy) {
    for(bool offline:{false,true}) {
        auto p=policy();p.withdrawalPolicies[static_cast<size_t>(C::timingFault)]=P::retainExistingPathAndPump;
        HydraulicSupervisor h(p);auto i=input();heating(h,i);
        i.boilerFault=true;ASSERT_TRUE(h.step(301,i).pumpIntent);
        EXPECT_FALSE(h.step(801,i).pumpIntent);
        auto r=offline?h.advanceWithoutOwner(800):h.step(800,i);
        EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);EXPECT_FALSE(r.heatIntent);
        r=offline?h.advanceWithoutOwner(801):h.step(801,i);
        EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
    }
}

TEST(SupervisorCorrection, ClockReversalCannotHideSimultaneousMoreRestrictiveLimitTrip) {
    auto p=policy();p.withdrawalPolicies[static_cast<size_t>(C::timingFault)]=P::retainExistingPathAndPump;
    p.withdrawalPolicies[static_cast<size_t>(C::limitTrip)]=P::withdrawHeatOnly;
    HydraulicSupervisor h(p);auto i=input();heating(h,i);
    i.boilerFault=true;ASSERT_TRUE(h.step(301,i).pumpIntent);
    ASSERT_TRUE(h.step(500,i).pumpIntent);
    i.limitTripped=true;const auto r=h.step(400,i);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);EXPECT_FALSE(r.heatIntent);
}

TEST(SupervisorCorrection, SimultaneousReadinessAndFlowLossUsesMostRestrictiveReviewedPolicyImmediately) {
    auto p=policy();
    p.withdrawalPolicies[static_cast<size_t>(C::readinessLost)]=P::retainExistingPathAndPump;
    p.withdrawalPolicies[static_cast<size_t>(C::flowLost)]=P::withdrawHeatOnly;
    HydraulicSupervisor h(p);auto i=input();heating(h,i);
    i.readinessConfirmed=i.independentFlowConfirmed=false;
    auto r=h.step(301,i);
    EXPECT_EQ(r.phase,HydraulicPhase::fault);EXPECT_FALSE(r.heatIntent);
    EXPECT_FALSE(r.pumpIntent);EXPECT_FALSE(r.openPathIntent);
    EXPECT_FALSE(r.physicalOutputsEnabled);
}


TEST(SupervisorCorrection, PredatingEvidenceCannotPreservePumpOnFaultOrUnknownSafetyWithdrawal) {
    for(bool boilerFault:{false,true}) {
        HydraulicSupervisor h(policy());auto i=input();heating(h,i);
        if (boilerFault) i.boilerFault=true;
        else {i.sourceValid=false;i.limitsKnownSafe=false;}
        i.flowAt=i.feedbackAt=0;
        auto r=h.step(301,i);
        EXPECT_FALSE(r.heatIntent);EXPECT_FALSE(r.pumpIntent);
        EXPECT_FALSE(r.physicalOutputsEnabled);
    }
}

}
