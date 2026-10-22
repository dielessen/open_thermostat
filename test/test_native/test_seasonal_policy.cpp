#include "control/HydraulicSupervisor.h"
#include "control/GroupWaterPolicy.h"
#include <gtest/gtest.h>
#include <cstdlib>
#include <fstream>

namespace {
using namespace heating::control;
SeasonalProfile seasonal() {return {true,true,true,120000,300000,700};}
SeasonalInputs sample(uint64_t now=0) {
    SeasonalInputs i;i.ownerAdmitted=i.sourceQualified=i.limitsKnownSafe=i.dhwStateKnown=true;
    i.ownerGeneration=1;i.sensorAt=now;i.temperature=1900;i.target=2100;return i;
}
HydraulicProfile hydraulic() {
    HydraulicProfile p{true,true,true,10000,1000,200,500,300,2000,3500};p.flowWaitDeadlineMs=1000;
    p.withdrawalPolicies.fill(WithdrawalPolicy::withdrawHeatOnly);
    for(auto c:{WithdrawalCause::normalStop,WithdrawalCause::sourceLost,WithdrawalCause::dhwPriority,WithdrawalCause::adapterLost})
        p.withdrawalPolicies[static_cast<size_t>(c)]=WithdrawalPolicy::retainExistingPathAndPump;
    return p;
}
HydraulicInputs water() {
    HydraulicInputs i;i.adapterAlive=i.sourceValid=i.heatDemand=i.limitsKnownSafe=i.faultStateKnown=i.dhwStateKnown=true;
    i.waterTarget=3000;return i;
}
void record(const char* name,const ZoneRegulator::Result& z,const HydraulicSupervisor::Result& h) {
    EXPECT_FALSE(z.physicalOutputsEnabled);EXPECT_FALSE(z.frostProtectionAvailable);EXPECT_FALSE(h.physicalOutputsEnabled);
    const auto path=std::getenv("OPENTHERMOSTAT_SEASONAL_EVIDENCE");
        if(!path)return;
    std::ofstream out(path,std::ios::app);
    out<<"{\"scenario\":\""<<name<<"\",\"zone_reason\":\""<<z.reason<<"\",\"zone_demand\":"<<(z.demand?"true":"false")
       <<",\"restriction_mask\":"<<z.seasonalRestrictions<<",\"duty_permille\":"<<z.dutyPermille<<",\"frost_advice\":"<<(z.frostAdvice?"true":"false")
       <<",\"hydraulic_phase\":\""<<hydraulicPhaseName(h.phase)<<"\",\"hydraulic_reason\":\""<<h.reason
       <<"\",\"heat_intent\":"<<(h.heatIntent?"true":"false")<<",\"retain_existing_path\":"<<(h.pathIntent==HydraulicPathIntent::retainExistingPath?"true":"false")
       <<",\"pump_intent\":"<<(h.pumpIntent?"true":"false")<<",\"physical_outputs_enabled\":false,\"frost_protection_available\":false}\n";
}
struct Rig {
    ZoneRegulator zone{ZoneControlProfile{},seasonal()};HydraulicSupervisor supervisor;
    explicit Rig(HydraulicProfile p=hydraulic()):supervisor(p){}
    SeasonalInputs i=sample();HydraulicInputs h=water();ZoneRegulator::Result z;
    HydraulicSupervisor::Result tick(uint64_t now) {z=zone.stepSeasonal(now,i);return supervisor.stepSeasonal(now,h,z);}
    void heat() {
        auto r=tick(0);h.readinessConfirmed=true;h.feedbackCommand=r.openingCommand;h.feedbackAt=100;i.sensorAt=100;tick(100);
        i.sensorAt=300;h.feedbackAt=h.flowAt=300;h.independentFlowConfirmed=true;ASSERT_TRUE(tick(300).heatIntent);
    }
};
TEST(SeasonalPolicy, DisabledUnqualifiedMalformedProfilesCannotAdvertiseFrostOrDemand) {
    for(int k=0;k<6;++k) {
        auto p=seasonal();
        if(k==0)p.enabled=false;
        if(k==1)p.installationQualified=false;
        if(k==2)p.maximumSensorAgeMs=0;
        if(k==3)p.maximumStepGapMs=300001;
        if(k==4)p.frostTargetCentiC=499;
        if(k==5)p.frostTargetCentiC=1501;
        ZoneRegulator z({},p);auto i=sample();i.frostSelected=true;i.temperature=400;
        auto a=z.stepSeasonal(0,i);EXPECT_FALSE(a.demand);EXPECT_FALSE(a.seasonalQualified);
        HydraulicSupervisor h(hydraulic());record("invalid_profile",a,h.stepSeasonal(0,water(),a));
    }
    EXPECT_FALSE(ZoneRegulator{}.stepSeasonal(0,sample()).demand);
}
TEST(SeasonalPolicy, ExplicitFrostBeatsSummerButNeverHardStopOrAllOff) {
    ZoneRegulator z({},seasonal());auto i=sample();HydraulicSupervisor h;
    i.summer=true;auto a=z.stepSeasonal(0,i);EXPECT_FALSE(a.demand);record("summer_no_phantom_demand",a,h.stepSeasonal(0,water(),a));
    i.frostSelected=true;i.temperature=500;i.sensorAt=1;a=z.stepSeasonal(1,i);EXPECT_TRUE(a.demand&&a.frostAdvice);
    record("chosen_frost_in_summer_advice_only",a,h.stepSeasonal(1,water(),a));
    i.stop=true;a=z.stepSeasonal(2,i);EXPECT_FALSE(a.demand);record("stop_beats_frost",a,h.stepSeasonal(2,water(),a));
    i.stop=false;i.allOff=true;a=z.stepSeasonal(3,i);EXPECT_FALSE(a.demand);record("all_off_beats_frost",a,h.stepSeasonal(3,water(),a));
}
TEST(SeasonalPolicy, UnreviewedFrostIsNotGenericProtectionAndNoAutomaticColdWeatherDemand) {
    auto p=seasonal();p.frostAdviceReviewed=false;ZoneRegulator z({},p);auto i=sample();i.frostSelected=true;i.temperature=400;
    EXPECT_FALSE(z.stepSeasonal(0,i).demand);
    i.frostSelected=false;i.summer=true;EXPECT_FALSE(z.stepSeasonal(1,i).demand);
    i.summer=false;i.target.reset();EXPECT_FALSE(z.stepSeasonal(2,i).demand);
}
TEST(SeasonalPolicy, CachedOldUnknownFutureOrInvalidSensorNeverGetsFrostFallback) {
    for(int k=0;k<5;++k) {
        ZoneRegulator z({},seasonal());auto i=sample();i.frostSelected=true;i.temperature=400;
        if(k==0)i.temperature.reset();
        if(k==1)i.sourceQualified=false;
        if(k==2)i.sensorAt=120001;
        if(k==3)i.temperature=-4001;
        if(k==4)i.sensorAt=0;
        const auto a=z.stepSeasonal(120000,i);EXPECT_FALSE(a.demand);HydraulicSupervisor h(hydraulic());record("sensor_unavailable_no_frost_fallback",a,h.stepSeasonal(120000,water(),a));
    }
    ZoneRegulator z({},seasonal());auto i=sample();ASSERT_TRUE(z.stepSeasonal(0,i).demand);
    EXPECT_FALSE(z.stepSeasonal(120000,i).demand);i.target=2200;EXPECT_FALSE(z.stepSeasonal(120001,i).demand);
}
TEST(SeasonalPolicy, SmallRequestedPulseIsSuppressedNotRoundedIntoMinimumOnOrPermanentDemand) {
    ZoneControlProfile p{ZoneControl::slowBinaryPi,20,100,0,900000,180000,120000};ZoneRegulator z(p,seasonal());auto i=sample();i.temperature=2090;
    for(uint64_t t=0;t<=1800000;t+=60000) {i.sensorAt=t;auto a=z.stepSeasonal(t,i);EXPECT_EQ(a.dutyPermille,10);EXPECT_FALSE(a.demand);}
}
TEST(SeasonalPolicy, SummerStopDhwAndLimitPreemptMinimumOnWithNoBacklog) {
    for(int reason=0;reason<5;++reason) {
        ZoneControlProfile p{ZoneControl::slowBinaryPi,20,500,0,900000,180000,120000};ZoneRegulator z(p,seasonal());auto i=sample();
        EXPECT_FALSE(z.stepSeasonal(0,i).demand);i.sensorAt=120000;ASSERT_TRUE(z.stepSeasonal(120000,i).demand);
        if(reason==0)i.summer=true;
        if(reason==1)i.stop=true;
        if(reason==2)i.dhwActive=true;
        if(reason==3)i.limitsKnownSafe=false;
        if(reason==4)i.dhwStateKnown=false;
        const auto a=z.stepSeasonal(120001,i);EXPECT_FALSE(a.demand);EXPECT_EQ(a.dutyPermille,0);
        HydraulicSupervisor h(hydraulic());record("inhibit_beats_minimum_on",a,h.stepSeasonal(120001,water(),a));
        i=sample(120002);EXPECT_FALSE(z.stepSeasonal(120002,i).demand);
    }
}
TEST(SeasonalPolicy, LeaseLossPreemptionAndGapRequireStrictlyNewOwnerWithoutOldStateResurrection) {
    for(int reason=0;reason<3;++reason) {
        ZoneRegulator z({},seasonal());auto i=sample();ASSERT_TRUE(z.stepSeasonal(0,i).demand);
        uint64_t t=1;
        if(reason==0)i.ownerAdmitted=false;
        if(reason==1)i.preempted=true;
        if(reason==2)t=300001;
        auto a=z.stepSeasonal(t,i);EXPECT_FALSE(a.demand);HydraulicSupervisor h(hydraulic());record("lease_preemption_or_gap",a,h.stepSeasonal(t,water(),a));
        i=sample(t+1);EXPECT_FALSE(z.stepSeasonal(t+1,i).demand);
        i.ownerGeneration=2;i.sensorAt=t+2;EXPECT_FALSE(z.stepSeasonal(t+2,i).demand);
        i.sensorAt=t+3;EXPECT_TRUE(z.stepSeasonal(t+3,i).demand);
        i.ownerGeneration=1;i.sensorAt=t+4;EXPECT_FALSE(z.stepSeasonal(t+4,i).demand);
    }
}
TEST(SeasonalPolicy, ReversedClockCannotBeClearedByMerelyChangingOwnerGeneration) {
    ZoneRegulator z({},seasonal());auto i=sample(100);ASSERT_TRUE(z.stepSeasonal(100,i).demand);
    i.ownerGeneration=2;i.sensorAt=50;auto a=z.stepSeasonal(50,i);EXPECT_FALSE(a.demand);EXPECT_EQ(a.seasonalStop,SeasonalStop::timing);
    i.sensorAt=150;EXPECT_FALSE(z.stepSeasonal(150,i).demand);
    i.ownerGeneration=3;i.sensorAt=151;EXPECT_FALSE(z.stepSeasonal(151,i).demand);
    i.sensorAt=152;EXPECT_TRUE(z.stepSeasonal(152,i).demand);
}
TEST(SeasonalPolicy, SummerWithdrawalRetainsOnlyExistingExplicitlyValidatedBoundedPostrun) {
    Rig r;r.heat();r.i.summer=true;auto h=r.tick(301);
    EXPECT_FALSE(h.heatIntent);EXPECT_TRUE(h.pumpIntent);EXPECT_EQ(h.pathIntent,HydraulicPathIntent::retainExistingPath);
    record("summer_preserves_reviewed_postrun",r.z,h);
    h=r.tick(801);EXPECT_FALSE(h.pumpIntent);EXPECT_FALSE(h.openPathIntent);record("summer_postrun_expired",r.z,h);
    Rig cold;cold.i.summer=true;h=cold.tick(0);EXPECT_FALSE(h.pumpIntent);EXPECT_FALSE(h.openPathIntent);
}
TEST(SeasonalPolicy, StopCannotBeDelayedByExistingWaterWriteBudget) {
    // A stop has no water target; existing slew/write cadence cannot postpone it.
    Rig r;r.heat();WaterWriteBudget budget({10000,10,600});ASSERT_TRUE(budget.step(300,3000).publishIntent);
    r.i.stop=true;auto h=r.tick(301);EXPECT_FALSE(h.heatIntent);EXPECT_FALSE(h.waterTarget);
    const auto stopped=budget.step(301,h.waterTarget);EXPECT_TRUE(stopped.publishIntent);EXPECT_FALSE(stopped.waterTarget);
    record("stop_no_water_target_no_budget_delay",r.z,h);
}
TEST(SeasonalPolicy, DhwAndFreshFrostStillRequireHydraulicFlowAndIndependentSafety) {
    Rig r;r.i.frostSelected=true;r.i.summer=true;r.i.temperature=500;
    auto h=r.tick(0);EXPECT_TRUE(r.z.frostAdvice);EXPECT_EQ(h.phase,HydraulicPhase::opening);EXPECT_FALSE(h.heatIntent);
    r.h.readinessConfirmed=true;r.h.feedbackCommand=h.openingCommand;r.h.feedbackAt=100;r.i.sensorAt=100;h=r.tick(100);EXPECT_FALSE(h.heatIntent);
    r.h.independentFlowConfirmed=true;r.h.flowAt=r.h.feedbackAt=300;r.i.sensorAt=300;h=r.tick(300);EXPECT_TRUE(h.heatIntent);
    r.i.dhwActive=true;h=r.tick(301);EXPECT_FALSE(h.heatIntent);record("dhw_beats_frost",r.z,h);
    r.i.dhwActive=false;r.i.limitsKnownSafe=false;h=r.tick(302);EXPECT_FALSE(h.heatIntent);EXPECT_FALSE(h.pumpIntent);
    record("unknown_limit_beats_frost_and_postrun",r.z,h);
}
TEST(SeasonalPolicy, LeaseOrPreemptionWithdrawsAndCannotResumeBeforeVerifiedHydraulicClear) {
    for(bool preempt:{false,true}) {
        Rig r;r.heat();
        if(preempt)r.i.preempted=true;else r.i.ownerAdmitted=false;
        auto h=r.tick(301);EXPECT_FALSE(h.heatIntent);EXPECT_EQ(h.phase,HydraulicPhase::fault);record("lease_or_preemption_latched",r.z,h);
        r.i=sample(400);r.i.ownerGeneration=2;r.h.flowAt=r.h.feedbackAt=400;h=r.tick(400);EXPECT_FALSE(h.heatIntent);
        EXPECT_FALSE(r.supervisor.clearFault(false));EXPECT_TRUE(r.supervisor.clearFault(true));
        r.i.sensorAt=500;h=r.tick(500);EXPECT_EQ(h.phase,HydraulicPhase::postrun);EXPECT_FALSE(h.heatIntent);
        r.i.sensorAt=801;r.h.flowAt=r.h.feedbackAt=801;h=r.tick(801);EXPECT_EQ(h.phase,HydraulicPhase::opening);EXPECT_FALSE(h.heatIntent);
    }
}
TEST(SeasonalPolicy, SensorLossUsesSourceLossPolicyNotAnInventedPhysicalSafePosition) {
    Rig r;r.heat();r.i.temperature.reset();auto h=r.tick(301);EXPECT_FALSE(h.heatIntent);EXPECT_TRUE(h.pumpIntent);
    record("sensor_loss_reviewed_prior_path",r.z,h);
    r.i=sample(802);r.h.flowAt=r.h.feedbackAt=802;h=r.tick(802);EXPECT_EQ(h.phase,HydraulicPhase::opening);EXPECT_FALSE(h.heatIntent);
}
TEST(SeasonalPolicy, GapDuringHeatLatchesTimingFaultWithoutStartingLatePostrun) {
    auto p=hydraulic();p.withdrawalPolicies[static_cast<size_t>(WithdrawalCause::timingFault)]=WithdrawalPolicy::retainExistingPathAndPump;
    Rig r(p);r.heat();r.i.sensorAt=3600000;r.h.flowAt=r.h.feedbackAt=3600000;auto h=r.tick(3600000);
    EXPECT_FALSE(h.heatIntent);EXPECT_FALSE(h.pumpIntent);EXPECT_EQ(h.phase,HydraulicPhase::fault);record("hour_gap_no_late_postrun",r.z,h);
}
TEST(SeasonalPolicy, NewOwnerAndFreshBootRestartLowLoadMinimumOffRatherThanRememberingPriorHeat) {
    ZoneControlProfile p{ZoneControl::slowBinaryPi,20,500,0,900000,180000,120000};
    ZoneRegulator z(p,seasonal());auto i=sample();EXPECT_FALSE(z.stepSeasonal(0,i).demand);
    i.sensorAt=120000;ASSERT_TRUE(z.stepSeasonal(120000,i).demand);
    i.ownerAdmitted=false;EXPECT_FALSE(z.stepSeasonal(120001,i).demand);
    i=sample(120002);i.ownerGeneration=2;EXPECT_FALSE(z.stepSeasonal(120002,i).demand);
    i.sensorAt=240002;EXPECT_TRUE(z.stepSeasonal(240002,i).demand);
    ZoneRegulator reboot(p,seasonal());i.sensorAt=240003;EXPECT_FALSE(reboot.stepSeasonal(240003,i).demand);
}

TEST(SeasonalPolicy, OwnerChangeCannotReuseOldHydraulicCommandEvenWithFreshLookingFeedback) {
    Rig r;r.heat();r.i.ownerGeneration=2;r.i.sensorAt=301;r.h.feedbackAt=r.h.flowAt=301;
    auto h=r.tick(301);EXPECT_FALSE(h.heatIntent);EXPECT_EQ(h.phase,HydraulicPhase::fault);
    EXPECT_EQ(r.z.seasonalStop,SeasonalStop::ownerChanged);record("owner_change_old_command_rejected",r.z,h);
    r.i.sensorAt=302;r.h.feedbackAt=r.h.flowAt=302;h=r.tick(302);EXPECT_FALSE(h.heatIntent);
    EXPECT_TRUE(r.supervisor.clearFault(true));r.i.sensorAt=801;r.h.feedbackAt=r.h.flowAt=801;h=r.tick(801);
    EXPECT_EQ(h.phase,HydraulicPhase::opening);EXPECT_FALSE(h.heatIntent);
}

TEST(SeasonalPolicy, ExactParentStopAndUnknownLimitCannotHideUnknownSafetyRestriction) {
    auto p=hydraulic();p.withdrawalPolicies.fill(WithdrawalPolicy::withdrawHeatOnly);
    p.withdrawalPolicies[static_cast<size_t>(WithdrawalCause::normalStop)]=WithdrawalPolicy::retainExistingPathAndPump;
    Rig r(p);r.heat();r.i.stop=true;r.i.limitsKnownSafe=false;r.i.sensorAt=301;
    const auto h=r.tick(301);EXPECT_FALSE(h.heatIntent);EXPECT_FALSE(h.pumpIntent);EXPECT_FALSE(h.openPathIntent);
    EXPECT_EQ(r.z.seasonalStop,SeasonalStop::stop);
    EXPECT_TRUE(r.z.seasonalRestrictions&seasonalRestriction(SeasonalRestriction::limitsUnknown));
    record("parent_stop_unknown_limit",r.z,h);
}
TEST(SeasonalPolicy, AllSevenConcurrentInputLossesSurviveEveryPrimaryReasonAndReviewedCausePolicy) {
    for(auto cause:{WithdrawalCause::normalStop,WithdrawalCause::sourceLost,WithdrawalCause::adapterLost,
                   WithdrawalCause::unknownSafety,WithdrawalCause::dhwPriority}) {
        auto p=hydraulic();p.withdrawalPolicies.fill(WithdrawalPolicy::retainExistingPathAndPump);
        p.withdrawalPolicies[static_cast<size_t>(cause)]=WithdrawalPolicy::withdrawHeatOnly;
        for(unsigned mask=1;mask<128;++mask) {
            Rig r(p);r.heat();r.i.sensorAt=301;r.h.feedbackAt=r.h.flowAt=301;
            r.i.stop=mask&1;r.i.sourceQualified=!(mask&2);r.i.limitsKnownSafe=!(mask&4);
            r.i.dhwStateKnown=!(mask&8);r.i.dhwActive=mask&16;
            r.i.ownerAdmitted=!(mask&32);r.i.preempted=mask&64;
            const auto h=r.tick(301);
            const bool restricted=(cause==WithdrawalCause::normalStop&&(mask&1))
                ||(cause==WithdrawalCause::sourceLost&&(mask&2))
                ||(cause==WithdrawalCause::unknownSafety&&(mask&12))
                ||(cause==WithdrawalCause::dhwPriority&&(mask&16))
                ||(cause==WithdrawalCause::adapterLost&&(mask&96));
            EXPECT_FALSE(r.z.demand);EXPECT_FALSE(h.heatIntent);EXPECT_FALSE(h.physicalOutputsEnabled);
            EXPECT_EQ(h.pumpIntent,!restricted)<<"mask="<<mask<<" cause="<<static_cast<unsigned>(cause);
            EXPECT_EQ(h.openPathIntent,!restricted)<<"mask="<<mask<<" cause="<<static_cast<unsigned>(cause);
            if(const auto path=std::getenv("OPENTHERMOSTAT_SEASONAL_COMBINED_EVIDENCE")) {
                std::ofstream out(path,std::ios::app);
                out<<"{\"input_mask\":"<<mask<<",\"restrictive_cause\":"<<static_cast<unsigned>(cause)
                    <<",\"projected_restrictions\":"<<r.z.seasonalRestrictions
                    <<",\"retention_expected\":"<<(!restricted?"true":"false")
                    <<",\"pump_intent\":"<<(h.pumpIntent?"true":"false")
                    <<",\"path_intent\":"<<(h.openPathIntent?"true":"false")
                    <<",\"heat_intent\":"<<(h.heatIntent?"true":"false")
                    <<",\"physical_output\":false}\n";
            }
        }
    }
}
TEST(SeasonalPolicy, ConcurrentEscalationClearingLossesCannotRestoreRetentionOrRenewDeadline) {
    auto p=hydraulic();p.withdrawalPolicies[static_cast<size_t>(WithdrawalCause::sourceLost)]=WithdrawalPolicy::retainExistingPath;
    Rig r(p);r.heat();r.i.stop=true;auto h=r.tick(301);ASSERT_TRUE(h.pumpIntent);
    r.i.sourceQualified=false;h=r.tick(350);EXPECT_FALSE(h.pumpIntent);EXPECT_TRUE(h.openPathIntent);
    record("combined_source_escalation",r.z,h);
    r.i.limitsKnownSafe=false;h=r.tick(400);EXPECT_FALSE(h.pumpIntent);EXPECT_FALSE(h.openPathIntent);
    record("combined_limit_escalation",r.z,h);
    r.i.sourceQualified=true;r.i.limitsKnownSafe=true;r.i.sensorAt=450;h=r.tick(450);
    EXPECT_FALSE(h.pumpIntent);EXPECT_FALSE(h.openPathIntent);EXPECT_EQ(h.phase,HydraulicPhase::postrun);
    r.i.sensorAt=801;h=r.tick(801);EXPECT_EQ(h.phase,HydraulicPhase::idle);EXPECT_FALSE(h.pumpIntent);
    record("combined_deadline_not_renewed",r.z,h);
    r.i.stop=false;r.i.sensorAt=802;h=r.tick(802);EXPECT_EQ(h.phase,HydraulicPhase::opening);EXPECT_FALSE(h.heatIntent);
    EXPECT_EQ(h.openingCommand,2u);
}
TEST(SeasonalPolicy, SeasonalSnapshotNeverUpgradesExternalHydraulicUnknownsOrUnknownRestrictionBits) {
    for(int reason=0;reason<8;++reason) {
        ZoneRegulator z({},seasonal());auto i=sample();auto zr=z.stepSeasonal(0,i);ASSERT_TRUE(zr.demand);
        HydraulicSupervisor h(hydraulic());auto in=water();
        if(reason==0)in.sourceValid=false;
        if(reason==1)in.adapterAlive=false;
        if(reason==2)in.limitsKnownSafe=false;
        if(reason==3)in.dhwStateKnown=false;
        if(reason==4)in.dhwActive=true;
        if(reason==5)in.faultStateKnown=false;
        if(reason==6)in.limitTripped=true;
        if(reason==7)zr.seasonalRestrictions|=0x8000;
        const auto a=h.stepSeasonal(0,in,zr);EXPECT_FALSE(a.heatIntent);EXPECT_FALSE(a.pumpIntent);EXPECT_FALSE(a.physicalOutputsEnabled);
    }
}

}
