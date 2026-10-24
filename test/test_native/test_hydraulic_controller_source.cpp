#include "SeasonalControllerFixture.h"
namespace {
HydraulicControllerSource hydraulicSourceFor(const SeasonalControllerSource& policy) {
    HydraulicControllerSource source;source.controllerId="e32_lab";source.adapterId="ha1";
    source.profileDigest=policy.profileDigest;source.maximumFactAgeMs=1000;
    source.profile={true,true,true,3000,1000,0,100,0,2000,6000};
    source.profile.flowWaitDeadlineMs=1000;
    source.profile.withdrawalPolicies.fill(WithdrawalPolicy::withdrawHeatOnly);
    return source;
}
HydraulicFeedbackSnapshot freshFacts(const HydraulicOwnerContext& owner,uint64_t at) {
    HydraulicFeedbackSnapshot s;s.ownerGeneration=owner.generation;s.configRevision=owner.revision;
    std::copy(owner.bootId.begin(),owner.bootId.end(),s.bootId.begin());
    s.ownerStartedAt=owner.startedAt;s.limitsAt=s.faultAt=s.dhwAt=s.waterTargetAt=at;
    s.limitsKnownSafe=s.faultStateKnown=s.dhwStateKnown=true;s.waterTarget=4000;
    return s;
}
TEST(HydraulicSourceGate, EverySafetyFactRetainsItsOwnOriginalDeadline) {
    const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    for(unsigned field=0;field<6;++field) {
        HydraulicFeedbackGate gate;auto s=freshFacts(owner,900);
        s.readinessConfirmed=s.independentFlowConfirmed=true;s.feedbackCommand=1;s.feedbackAt=s.flowAt=900;
        const std::array<uint64_t*,6> times{&s.limitsAt,&s.faultAt,&s.dhwAt,&s.waterTargetAt,&s.feedbackAt,&s.flowAt};
        *times[field]=101;
        const auto before=gate.evaluate(1100,1000,owner,s).inputs;
        EXPECT_TRUE(before.limitsKnownSafe&&before.faultStateKnown&&before.dhwStateKnown
            &&before.waterTarget&&before.readinessConfirmed&&before.independentFlowConfirmed)<<field;
        const auto at=gate.evaluate(1101,1000,owner,s).inputs;
        EXPECT_EQ(at.limitsKnownSafe,field!=0);EXPECT_EQ(at.faultStateKnown,field!=1);
        EXPECT_EQ(at.dhwStateKnown,field!=2);EXPECT_EQ(bool(at.waterTarget),field!=3);
        EXPECT_EQ(at.readinessConfirmed,field!=4);EXPECT_EQ(at.independentFlowConfirmed,field!=5);
    }
}
TEST(HydraulicSourceGate, WrongOwnerRevisionStartFutureOrInvalidBudgetNeverQualifies) {
    const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    for(unsigned fault=0;fault<7;++fault) {
        HydraulicFeedbackGate gate;auto s=freshFacts(owner,101);unsigned budget=1000;
        if(fault==0)++s.ownerGeneration;if(fault==1)++s.configRevision;if(fault==2)--s.ownerStartedAt;
        if(fault==3)s.limitsAt=201;if(fault==4)s.limitsAt=100;
        if(fault==5)budget=0;if(fault==6)budget=30001;
        const auto in=gate.evaluate(200,budget,owner,s).inputs;
        EXPECT_FALSE(in.limitsKnownSafe)<<fault;
    }
}
TEST(HydraulicSourceGate, DuplicateDoesNotRenewAndReorderedOrConflictingFactCannotRestoreSafety) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    auto first=freshFacts(owner,101);ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    EXPECT_FALSE(gate.evaluate(1101,1000,owner,first).inputs.limitsKnownSafe);
    auto newer=freshFacts(owner,1200);newer.limitsKnownSafe=false;
    EXPECT_FALSE(gate.evaluate(1200,1000,owner,newer).inputs.limitsKnownSafe);
    EXPECT_STREQ(gate.evaluate(1201,1000,owner,first).reason,"hydraulic_feedback_reordered");
    newer.limitsKnownSafe=true;
    EXPECT_STREQ(gate.evaluate(1201,1000,owner,newer).reason,"hydraulic_feedback_reordered");
    newer=freshFacts(owner,1202);
    EXPECT_TRUE(gate.evaluate(1202,1000,owner,newer).inputs.limitsKnownSafe);
}
TEST(HydraulicSourceGate, UnknownFactRetiresCachedProofUntilStrictlyNewerFact) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    auto unknown=first;unknown.limitsAt=0;unknown.limitsKnownSafe=false;
    EXPECT_FALSE(gate.evaluate(103,1000,owner,unknown).inputs.limitsKnownSafe);
    EXPECT_STREQ(gate.evaluate(104,1000,owner,first).reason,"hydraulic_feedback_reordered");
    auto newer=first;newer.limitsAt=105;
    EXPECT_TRUE(gate.evaluate(105,1000,owner,newer).inputs.limitsKnownSafe);
}
TEST(HydraulicSourceGate, FailedSnapshotCannotPartiallyCommitReplayWatermarks) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    auto wrong=freshFacts(owner,104);wrong.flowAt=105;
    EXPECT_STREQ(gate.evaluate(104,1000,owner,wrong).reason,"hydraulic_feedback_future");
    auto next=freshFacts(owner,103);EXPECT_TRUE(gate.evaluate(104,1000,owner,next).inputs.limitsKnownSafe);
}
struct HydraulicRig {
    Fixture f;SeasonalControllerSource policy=sourceFor();SeasonalSafetySnapshot safety=safe();
    HydraulicControllerSource source;HydraulicFeedbackSnapshot feedback;
    bool live=false,ready=false,flow=false,throwFeedback=false;uint32_t command=0;HydraulicOwnerContext context;
    std::function<void(HydraulicFeedbackSnapshot&)> alter;
    std::function<void()> afterFeedback;
    HydraulicRig() {
        policy.profileDigest=std::string(64,'c');source=hydraulicSourceFor(policy);bind(f,policy,safety);
        f.hydraulicSource=&source;
        f.hydraulicFeedback=[this](const auto& owner) {
            context=owner;
            if(throwFeedback)throw std::runtime_error("observer");
            if(afterFeedback){auto callback=afterFeedback;afterFeedback={};callback();}
            auto result=live?freshFacts(owner,f.now):feedback;
            if(live&&ready) {result.readinessConfirmed=true;result.feedbackAt=f.now;result.feedbackCommand=command;}
            if(live&&flow) {result.independentFlowConfirmed=true;result.flowAt=f.now;}
            if(alter)alter(result);
            return result;
        };
    }
    const cJSON* supervisor(const ControlJson& s){return field(s.get(),"supervisor");}
    void start() {f.ready();live=true;f.now+=1;report(f);f.now+=1;report(f);}
    ControlJson update() {++f.now;return report(f);}
    ControlJson heat() {
        start();auto opening=update();EXPECT_STREQ(stringField(supervisor(opening),"phase").c_str(),"opening");
        command=uintField(supervisor(opening),"opening_command");ready=flow=true;
        auto result=update();EXPECT_TRUE(cJSON_IsTrue(field(supervisor(result),"heat_intent")));return result;
    }
};
TEST(HydraulicControllerSource, ActualControllerCombinesDemandProfileFeedbackAndNoPhysicalOutput) {
    HydraulicRig r;const auto state=r.heat();const auto h=r.supervisor(state);
    EXPECT_STREQ(stringField(h,"phase").c_str(),"heating");EXPECT_EQ(uintField(h,"water_target_centi_c"),4000u);
    EXPECT_TRUE(cJSON_IsFalse(field(h,"physical_outputs_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(state.get(),"boiler_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(state.get(),"actuator_output_enabled")));
    // Constructor copied SOURCE, no later external policy mutation.
    r.source.profile.maximumWaterCentiC=3000;
    EXPECT_TRUE(cJSON_IsTrue(field(r.supervisor(r.update()),"heat_intent")));
}
TEST(HydraulicControllerSource, SelectedProfileRequiresExactOwnerAndExistingSeasonalPolicy) {
    for(unsigned fault=0;fault<6;++fault) {
        HydraulicRig r;
        if(fault==0)r.source.controllerId="other";if(fault==1)r.source.adapterId="other";
        if(fault==2)r.source.profileDigest=std::string(64,'d');if(fault==3)r.source.maximumFactAgeMs=0;
        if(fault==4)r.f.hydraulicFeedback={};if(fault==5)r.f.seasonalSource=nullptr;
        r.f.start();EXPECT_TRUE(r.f.core->faulted())<<fault;EXPECT_EQ(r.f.store.writes,0u);
    }
}
TEST(HydraulicControllerSource, RoomDemandNeverInventsReadinessOrIndependentFlow) {
    HydraulicRig r;r.start();auto opening=r.update();r.command=uintField(r.supervisor(opening),"opening_command");
    r.ready=true;auto waiting=r.update();
    EXPECT_STREQ(stringField(r.supervisor(waiting),"phase").c_str(),"pump_wait");
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(waiting),"heat_intent")));
    r.flow=true;r.command+=1;auto wrong=r.update();
    EXPECT_STREQ(stringField(r.supervisor(wrong),"phase").c_str(),"fault");
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(wrong),"heat_intent")));
}
TEST(HydraulicControllerSource, CurrentSeasonalSafetyStillRestrictsIndependentlyReportedHydraulics) {
    for(unsigned fault=0;fault<4;++fault) {
        HydraulicRig r;r.heat();
        if(fault==0)r.safety.limitsKnownSafe=false;if(fault==1)r.safety.dhwStateKnown=false;
        if(fault==2)r.safety.dhwActive=true;if(fault==3)r.safety.allOff=true;
        auto stopped=r.update();EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")))<<fault;
    }
}
TEST(HydraulicControllerSource, DisconnectCannotRestoreHeatFromFreshLookingNewOwnerSnapshot) {
    HydraulicRig r;r.heat();r.f.core->disconnected();++r.f.now;r.f.core->connected(r.f.now);
    r.f.connect();r.f.heartbeat();auto stopped=r.update();
    EXPECT_STREQ(stringField(r.supervisor(stopped),"phase").c_str(),"fault");
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")));
}
TEST(HydraulicControllerSource, CallbackExceptionCannotDisableControllerOrKeepHeat) {
    HydraulicRig r;r.heat();r.throwFeedback=true;auto stopped=r.update();
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")));EXPECT_FALSE(r.f.core->faulted());
}
TEST(HydraulicControllerSource, EveryCurrentIndependentConditionCanWithdrawLogicalHeat) {
    for(unsigned fault=0;fault<12;++fault) {
        HydraulicRig r;r.heat();
        r.alter=[&,fault](auto& snapshot) {
            if(fault==0)snapshot.limitsKnownSafe=false;
            if(fault==1)snapshot.limitsAt=r.f.now-1000;
            if(fault==2)snapshot.faultStateKnown=false;
            if(fault==3)snapshot.boilerFault=true;
            if(fault==4)snapshot.dhwStateKnown=false;
            if(fault==5)snapshot.dhwActive=true;
            if(fault==6)snapshot.dhwAt=r.f.now-1000;
            if(fault==7)snapshot.waterTarget=7000;
            if(fault==8)snapshot.waterTargetAt=r.f.now-1000;
            if(fault==9)snapshot.readinessConfirmed=false;
            if(fault==10)snapshot.independentFlowConfirmed=false;
            if(fault==11)++snapshot.ownerGeneration;
        };
        auto stopped=r.update();EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")))<<fault;
    }
}
TEST(HydraulicControllerSource, ProviderOwnershipLossIsRecheckedAfterCallback) {
    HydraulicRig r;r.heat();r.afterFeedback=[&]{r.f.core->disconnected();};
    auto stopped=r.update();EXPECT_FALSE(cJSON_IsTrue(field(stopped.get(),"adapter_alive")));
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")));
}
TEST(HydraulicControllerSource, ReentrantProviderCannotLeavePositiveIntent) {
    HydraulicRig r;r.heat();r.afterFeedback=[&]{
        auto message=r.f.command("off");r.f.send("ha/user_command",message.get());
    };
    auto stopped=r.update();EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(stopped),"heat_intent")));
    EXPECT_FALSE(r.f.core->faulted());
    r.ready=r.flow=false;r.alter={};auto later=r.update();
    EXPECT_STREQ(stringField(r.supervisor(later),"feedback_status").c_str(),"hydraulic_feedback_unavailable");
}

TEST(HydraulicControllerSource, LocalFaultAcknowledgementRequiresFreshCurrentOwnerFactsAndNeverStartsHeat) {
    HydraulicRig r;r.heat();r.ready=false;auto fault=r.update();
    ASSERT_STREQ(stringField(r.supervisor(fault),"phase").c_str(),"fault");
    auto evidence=freshFacts(r.context,r.f.now);
    auto wrong=evidence;++wrong.ownerGeneration;
    EXPECT_FALSE(r.f.core->acknowledgeHydraulicFault(r.f.now,wrong));
    wrong=evidence;wrong.limitsKnownSafe=false;
    // Different content with the same timestamp is not new proof.
    EXPECT_FALSE(r.f.core->acknowledgeHydraulicFault(r.f.now,wrong));
    ++r.f.now;evidence=freshFacts(r.context,r.f.now);
    r.safety.dhwActive=true;
    EXPECT_FALSE(r.f.core->acknowledgeHydraulicFault(r.f.now,evidence));
    r.safety.dhwActive=false;
    ASSERT_TRUE(r.f.core->acknowledgeHydraulicFault(r.f.now,evidence));
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(r.f.state()),"heat_intent")));
    r.flow=false;r.f.now+=101;auto opening=r.update();
    EXPECT_STREQ(stringField(r.supervisor(opening),"phase").c_str(),"opening");
    EXPECT_NE(uintField(r.supervisor(opening),"opening_command"),r.command);
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(opening),"heat_intent")));
    r.command=uintField(r.supervisor(opening),"opening_command");r.ready=r.flow=true;
    EXPECT_TRUE(cJSON_IsTrue(field(r.supervisor(r.update()),"heat_intent")));
}
TEST(HydraulicControllerSource, FaultAcknowledgementCannotRecoverAReplacedOrDisconnectedOwner) {
    HydraulicRig r;r.heat();r.ready=false;r.update();
    const auto old=freshFacts(r.context,r.f.now);
    r.f.core->disconnected();
    EXPECT_FALSE(r.f.core->acknowledgeHydraulicFault(r.f.now,old));
    ++r.f.now;r.f.core->connected(r.f.now);r.f.connect();r.f.heartbeat();r.update();
    EXPECT_FALSE(r.f.core->acknowledgeHydraulicFault(r.f.now,old));
    EXPECT_FALSE(cJSON_IsTrue(field(r.supervisor(r.update()),"heat_intent")));
}

TEST(HydraulicControllerSource, DisconnectedControllerAgesLocalPostrunWithoutNetworkOrObservers) {
    HydraulicRig r;
    unsigned safetyReads=0;const auto observer=r.f.seasonalSafety;
    r.f.seasonalSafety=[&] {++safetyReads;return observer();};
    r.source.profile.withdrawalPolicies[static_cast<size_t>(WithdrawalCause::adapterLost)]=WithdrawalPolicy::retainExistingPathAndPump;
    r.heat();
    const auto stoppedAt=r.f.now;
    r.f.core->disconnected();
    ASSERT_TRUE(r.f.core->hydraulicIntent().pumpIntent);
    const auto output=r.f.output;
    const auto readsBefore=safetyReads;
    r.afterFeedback=[] {ADD_FAILURE()<<"offline hydraulic observer";};
    r.f.now=stoppedAt+99;r.f.tick();
    EXPECT_TRUE(r.f.core->hydraulicIntent().pumpIntent);
    EXPECT_FALSE(r.f.core->hydraulicIntent().heatIntent);
    r.f.now=stoppedAt+100;r.f.tick();
    EXPECT_FALSE(r.f.core->hydraulicIntent().pumpIntent);
    EXPECT_FALSE(r.f.core->hydraulicIntent().openPathIntent);
    EXPECT_EQ(r.f.output,output); // No publish, handshake or synthetic feedback.
    EXPECT_EQ(safetyReads,readsBefore);
    EXPECT_FALSE(r.f.core->hydraulicIntent().physicalOutputsEnabled);
}

TEST(HydraulicControllerSource, SilentHaExpiresOnLocalLeaseEvenWhenBrokerAndObserversRemainAlive) {
    HydraulicRig r;r.heat();
    r.f.syncSession();r.f.heartbeat(2);const auto lastHeartbeat=r.f.now;
    const auto ack=r.f.get("fw/heartbeat_result");ASSERT_EQ(stringField(ack.get(),"status"),"accepted");
    r.f.now=lastHeartbeat+ShadowController::leaseMs-1;r.f.tick();
    ASSERT_TRUE(r.f.core->hydraulicIntent().heatIntent);
    r.f.now=lastHeartbeat+ShadowController::leaseMs;r.f.tick();
    EXPECT_FALSE(r.f.core->hydraulicIntent().heatIntent);
    // An old packet is not a reconnect or fresh admission.
    r.f.heartbeat(2);++r.f.now;r.f.tick();
    EXPECT_FALSE(r.f.core->hydraulicIntent().heatIntent);
    EXPECT_FALSE(r.f.core->hydraulicIntent().physicalOutputsEnabled);
}

TEST(HydraulicControllerSource, SourceLockoutCannotFreezeLocalPostrunOrStartReconnect) {
    HydraulicRig r;
    r.source.profile.withdrawalPolicies[static_cast<size_t>(WithdrawalCause::adapterLost)]=WithdrawalPolicy::retainExistingPathAndPump;
    r.heat();const auto last=r.f.now;
    r.f.core->inhibitNativeSourceMutation();
    ASSERT_TRUE(r.f.core->faulted());
    ASSERT_TRUE(r.f.core->hydraulicIntent().pumpIntent);
    const auto output=r.f.output;
    r.f.now=last+100;r.f.tick();
    EXPECT_FALSE(r.f.core->hydraulicIntent().pumpIntent);
    EXPECT_FALSE(r.f.core->hydraulicIntent().openPathIntent);
    EXPECT_FALSE(r.f.core->hydraulicIntent().heatIntent);
    EXPECT_EQ(r.f.output,output);
}

TEST(HydraulicSourceGate, PreviousBootCannotMatchEvenWhenAllLocalCountersAndTimesRepeat) {
    HydraulicFeedbackGate gate;HydraulicOwnerContext first{1,2,1,100,"boot1"};
    const auto snapshot=freshFacts(first,101);
    auto reboot=first;reboot.bootId="boot2";
    EXPECT_STREQ(gate.evaluate(102,1000,reboot,snapshot).reason,"hydraulic_feedback_owner_mismatch");
    EXPECT_TRUE(gate.evaluate(102,1000,reboot,freshFacts(reboot,101)).inputs.limitsKnownSafe);
}

TEST(HydraulicSourceGate, InvalidCurrentSnapshotPreservesOnlyAssertedRestrictions) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    const auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    auto invalid=freshFacts(owner,103);invalid.waterTargetAt=104;
    invalid.limitTripped=invalid.boilerFault=invalid.dhwActive=invalid.stop=invalid.actuatorFailure=true;
    invalid.readinessConfirmed=invalid.independentFlowConfirmed=true;
    invalid.feedbackAt=invalid.flowAt=103;invalid.feedbackCommand=1;
    const auto checked=gate.evaluate(103,1000,owner,invalid);
    ASSERT_STREQ(checked.reason,"hydraulic_feedback_future");
    const auto& in=checked.inputs;
    EXPECT_TRUE(in.limitTripped&&in.boilerFault&&in.dhwActive&&in.stop&&in.actuatorFailure);
    EXPECT_FALSE(in.limitsKnownSafe||in.faultStateKnown||in.dhwStateKnown
        ||in.readinessConfirmed||in.independentFlowConfirmed||in.waterTarget);
    // The rejected aggregate cannot make the previously retired cache valid.
    EXPECT_STREQ(gate.evaluate(104,1000,owner,first).reason,"hydraulic_feedback_reordered");
    const auto recovered=freshFacts(owner,105);
    EXPECT_TRUE(gate.evaluate(105,1000,owner,recovered).inputs.limitsKnownSafe);
}
TEST(HydraulicSourceGate, WrongOwnerCannotSupplyEvenRestrictiveFacts) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    auto wrong=freshFacts(owner,101);++wrong.ownerGeneration;
    wrong.limitTripped=wrong.boilerFault=wrong.dhwActive=wrong.stop=wrong.actuatorFailure=true;
    const auto in=gate.evaluate(102,1000,owner,wrong).inputs;
    EXPECT_FALSE(in.limitTripped||in.boilerFault||in.dhwActive||in.stop||in.actuatorFailure);
}
TEST(HydraulicSourceGate, ClockRegressionCannotRestoreEvidenceEvenWithNewerFacts) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    const auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(200,1000,owner,first).inputs.limitsKnownSafe);
    EXPECT_STREQ(gate.evaluate(199,1000,owner,first).reason,"hydraulic_feedback_clock_invalid");
    EXPECT_FALSE(gate.evaluate(201,1000,owner,freshFacts(owner,201)).inputs.limitsKnownSafe);
    HydraulicFeedbackGate reconstructed;
    EXPECT_TRUE(reconstructed.evaluate(201,1000,owner,freshFacts(owner,201)).inputs.limitsKnownSafe);
}
TEST(HydraulicSourceGate, ExpiredFactsAreRetiredWithoutAdvancingAcquisitionTimes) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    const auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    EXPECT_FALSE(gate.evaluate(1101,1000,owner,first).inputs.limitsKnownSafe);
    EXPECT_STREQ(gate.evaluate(1102,1000,owner,first).reason,"hydraulic_feedback_reordered");
    EXPECT_TRUE(gate.evaluate(1103,1000,owner,freshFacts(owner,1103)).inputs.limitsKnownSafe);
}
TEST(HydraulicControllerSource, MalformedUnrelatedTimeCannotHideAnyCurrentWithdrawalCause) {
    for(unsigned loss=0;loss<4;++loss) {
        HydraulicRig r;
        r.source.profile.withdrawalPolicies.fill(WithdrawalPolicy::retainExistingPathAndPump);
        const auto cause=loss==0?WithdrawalCause::limitTrip:loss==1?WithdrawalCause::boilerFault:
            loss==2?WithdrawalCause::dhwPriority:WithdrawalCause::normalStop;
        r.source.profile.withdrawalPolicies[static_cast<size_t>(cause)]=WithdrawalPolicy::withdrawHeatOnly;
        r.heat();
        r.alter=[&,loss](auto& snapshot) {
            snapshot.waterTargetAt=r.f.now+1;
            if(loss==0)snapshot.limitTripped=true;
            if(loss==1)snapshot.boilerFault=true;
            if(loss==2)snapshot.dhwActive=true;
            if(loss==3)snapshot.stop=true;
        };
        const auto state=r.update();const auto h=r.supervisor(state);
        EXPECT_FALSE(cJSON_IsTrue(field(h,"heat_intent")))<<loss;
        EXPECT_FALSE(cJSON_IsTrue(field(h,"pump_intent")))<<loss;
        EXPECT_STREQ(stringField(h,"path_intent").c_str(),"none")<<loss;
        EXPECT_FALSE(r.f.core->hydraulicIntent().physicalOutputsEnabled);
    }
}

TEST(HydraulicSourceGate, RepairNeedsNewAffectedFactWithoutRenewingUnrelatedLifetimes) {
    HydraulicFeedbackGate gate;const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    const auto first=freshFacts(owner,101);
    ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
    auto invalid=first;invalid.waterTargetAt=104;
    EXPECT_STREQ(gate.evaluate(103,1000,owner,invalid).reason,"hydraulic_feedback_future");
    auto repaired=first;repaired.waterTargetAt=105;
    const auto in=gate.evaluate(105,1000,owner,repaired).inputs;
    EXPECT_TRUE(in.limitsKnownSafe&&in.faultStateKnown&&in.dhwStateKnown&&in.waterTarget);
    const auto expired=gate.evaluate(1101,1000,owner,repaired).inputs;
    EXPECT_FALSE(expired.limitsKnownSafe||expired.faultStateKnown||expired.dhwStateKnown);
    EXPECT_TRUE(expired.waterTarget);
}

TEST(HydraulicSourceGate, EverySimultaneouslyRejectedFactNeedsNewProof) {
    const HydraulicOwnerContext owner{1,2,1,100,"boot1"};
    for(unsigned unrepaired=0;unrepaired<3;++unrepaired) {
        HydraulicFeedbackGate gate;const auto first=freshFacts(owner,101);
        ASSERT_TRUE(gate.evaluate(102,1000,owner,first).inputs.limitsKnownSafe);
        auto invalid=first;invalid.limitsAt=104;invalid.faultAt=105;invalid.waterTargetAt=106;
        invalid.boilerFault=true;
        EXPECT_STREQ(gate.evaluate(103,1000,owner,invalid).reason,"hydraulic_feedback_future");
        auto partial=freshFacts(owner,107);
        if(unrepaired==0)partial.limitsAt=101;
        if(unrepaired==1)partial.faultAt=101;
        if(unrepaired==2)partial.waterTargetAt=101;
        const auto rejected=gate.evaluate(107,1000,owner,partial);
        EXPECT_STREQ(rejected.reason,"hydraulic_feedback_reordered")<<unrepaired;
        EXPECT_FALSE(rejected.inputs.limitsKnownSafe||rejected.inputs.faultStateKnown||rejected.inputs.waterTarget)<<unrepaired;
        EXPECT_TRUE(gate.evaluate(108,1000,owner,freshFacts(owner,108)).inputs.limitsKnownSafe);
    }
}

}
