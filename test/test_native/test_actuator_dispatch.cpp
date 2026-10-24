#include "control/ActuatorDispatch.h"
#include <gtest/gtest.h>
#include <cstdlib>
using heating::control::ActuatorDispatch;
namespace {
using Outcome=ActuatorDispatch::Outcome;
ActuatorDispatch::Scope dispatchScope(){return {"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};}
std::string dispatchGrant(int sequence=1,std::string nonce="receiver1") {
    return "{\"adapter_id\":\"ha\",\"adapter_session_id\":\"session\",\"api\":1,\"binding_id\":\"valve\","
        "\"boot_id\":\"boot\",\"command_kind\":\"room_target\",\"config_digest\":\""+std::string(64,'a')+
        "\",\"config_revision\":4,\"controller_id\":\"ctrl\",\"epoch\":1,\"grant_id\":\""+nonce+
        "\",\"grant_ms\":5000,\"grant_sequence\":"+std::to_string(sequence)+"}";
}
struct DispatchFixture {
    uint64_t now=1000,deadline=0;
    int reads=0,sends=0;
    ActuatorDispatch::Facts facts{dispatchScope(),16000,true};
    std::function<void()> onSource,onSend;
    bool sendResult=true;
    std::string sent;
    ActuatorDispatch owner{dispatchScope(),[&]{++reads;if(onSource)onSource();return facts;},[&]{return now;},
        [&](std::string_view raw,uint64_t budget){++sends;sent=raw;deadline=budget;if(onSend)onSend();return sendResult;}};
    void admit(){ASSERT_TRUE(owner.accept(dispatchGrant(),1000));}
};
TEST(ActuatorDispatch, MissingLocalProducersAndTransportDefaultClosed) {
    ActuatorDispatch a(dispatchScope());EXPECT_TRUE(a.retired());EXPECT_FALSE(a.accept(dispatchGrant(),1000));
    EXPECT_EQ(a.dispatch(2100),Outcome::refused);
}
TEST(ActuatorDispatch, OneOriginalBudgetAndSingleSynchronousTransportHandoff) {
    DispatchFixture f;f.admit();EXPECT_EQ(f.reads,2);
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);
    EXPECT_EQ(f.sends,1);EXPECT_EQ(f.deadline,6000u);EXPECT_EQ(f.reads,5);
    EXPECT_EQ(f.owner.dispatch(2200),Outcome::refused);EXPECT_EQ(f.sends,1);
    EXPECT_FALSE(f.owner.accept(dispatchGrant(),1001));
    ASSERT_TRUE(f.owner.accept(dispatchGrant(2,"receiver2"),1000));
    EXPECT_EQ(f.owner.dispatch(2200),Outcome::transport_accepted);EXPECT_EQ(f.sends,2);
}
TEST(ActuatorDispatch, OriginalLeaseAndNewShorterLeaseBoundActualHandoff) {
    for(bool shrink:{false,true}) {
        DispatchFixture f;f.facts.leaseUntil=4000;f.admit();
        if(shrink)f.onSource=[&]{if(f.reads==4)f.facts.leaseUntil=2000;};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);
        EXPECT_EQ(f.deadline,shrink?2000u:4000u);
    }
}
TEST(ActuatorDispatch, LeaseExpiryInSourceCallbackCannotUseEarlierClockSnapshot) {
    DispatchFixture f;f.admit();f.onSource=[&]{f.now=16000;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sends,0);
}
TEST(ActuatorDispatch, GrantExpiryDuringSourceValidationNeverCallsTransport) {
    DispatchFixture f;f.admit();f.onSource=[&]{f.now=6000;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorDispatch, ExpiryAfterEncodingCannotUseOldSourceOrLease) {
    for(bool lease:{false,true}) {
        DispatchFixture f;f.admit();f.onSource=[&]{if(f.reads==4){f.now=6000;if(lease)f.facts.leaseUntil=6000;}};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,0);
        if(lease){EXPECT_TRUE(f.owner.retired());}
    }
}
TEST(ActuatorDispatch, DelayedSecondGrantValidationCannotRenewOriginalWindow) {
    DispatchFixture f;f.onSource=[&]{if(f.reads==2)f.now=6000;};
    EXPECT_FALSE(f.owner.accept(dispatchGrant(),1000));EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);
    EXPECT_EQ(f.sends,0);
}
TEST(ActuatorDispatch, AllScopeChangesAndLostAuthorityBeforeSendPermanentlyRetire) {
    for(int kind=0;kind<9;++kind) {
        DispatchFixture f;f.admit();
        f.onSource=[&]{if(f.reads!=4)return;switch(kind){
            case 0:f.facts.scope.controller="new";break;case 1:f.facts.scope.boot="new";break;
            case 2:f.facts.scope.adapter="new";break;case 3:f.facts.scope.session="new";break;
            case 4:f.facts.scope.digest=std::string(64,'b');break;case 5:f.facts.scope.binding="new";break;
            case 6:++f.facts.scope.epoch;break;case 7:++f.facts.scope.revision;break;
            case 8:f.facts.authorized=false;break;}};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,0);EXPECT_TRUE(f.owner.retired());
        f.facts={dispatchScope(),30000,true};f.onSource={};
        EXPECT_FALSE(f.owner.accept(dispatchGrant(2,"new"),1000));
    }
}
TEST(ActuatorDispatch, PostSendSourceLossOrExpiryCannotBecomeAcceptanceOrRetry) {
    for(int kind=0;kind<4;++kind) {
        DispatchFixture f;f.admit();f.onSend=[&]{switch(kind){
            case 0:f.facts.authorized=false;break;case 1:f.facts.scope.session="new";break;
            case 2:f.now=6000;break;case 3:f.facts.leaseUntil=f.now;break;}};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::outcome_unknown);EXPECT_EQ(f.sends,1);EXPECT_TRUE(f.owner.retired());
        f.onSend={};f.facts={dispatchScope(),30000,true};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_FALSE(f.owner.accept(dispatchGrant(2,"new"),f.now));
        EXPECT_EQ(f.sends,1);
    }
}
TEST(ActuatorDispatch, FalseOrThrowingTransportIsUnknownNotSafeToRetry) {
    for(bool throws:{false,true}) {
        DispatchFixture f;f.admit();f.sendResult=false;if(throws)f.onSend=[]{throw std::runtime_error("partial IO");};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::outcome_unknown);EXPECT_EQ(f.sends,1);EXPECT_TRUE(f.owner.retired());
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,1);
    }
}
TEST(ActuatorDispatch, ClockReversalBeforeAndAfterHandoffIsSticky) {
    for(bool after:{false,true}) {
        DispatchFixture f;f.admit();if(after)f.onSend=[&]{f.now=999;};else f.onSource=[&]{f.now=999;};
        EXPECT_EQ(f.owner.dispatch(2100),after?Outcome::outcome_unknown:Outcome::refused);
        EXPECT_EQ(f.sends,after?1:0);EXPECT_TRUE(f.owner.retired());f.now=1001;
        EXPECT_FALSE(f.owner.accept(dispatchGrant(2,"new"),1001));
    }
}
TEST(ActuatorDispatch, ReentrantSourceAndTransportCannotDispatchSecondAction) {
    for(bool atSend:{false,true}) {
        DispatchFixture f;f.admit();auto nested=[&]{EXPECT_EQ(f.owner.dispatch(2200),Outcome::refused);};
        if(atSend)f.onSend=nested;else f.onSource=nested;
        EXPECT_EQ(f.owner.dispatch(2100),atSend?Outcome::outcome_unknown:Outcome::refused);
        EXPECT_EQ(f.sends,atSend?1:0);EXPECT_TRUE(f.owner.retired());
    }
}
TEST(ActuatorDispatch, ExplicitRetirementOrThrowingSourceStopsBeforeTransport) {
    for(bool throws:{false,true}) {
        DispatchFixture f;f.admit();f.onSource=[&]{if(throws)throw std::runtime_error("lost source");f.owner.retire();};
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sends,0);
    }
}
TEST(ActuatorDispatch, InvalidTargetAndRetainedGrantCannotCreateOrConsumeAction) {
    DispatchFixture f;EXPECT_FALSE(f.owner.accept(dispatchGrant(),1000,true));EXPECT_EQ(f.reads,0);
    f.admit();EXPECT_EQ(f.owner.dispatch(499),Outcome::refused);EXPECT_EQ(f.owner.dispatch(3501),Outcome::refused);
    EXPECT_EQ(f.sends,0);EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);EXPECT_EQ(f.sends,1);
}
}
namespace {
TEST(ActuatorDispatch, ShortenedLeaseDuringGrantValidationCannotLaterRegrow) {
    DispatchFixture f;f.facts.leaseUntil=4000;
    f.onSource=[&]{if(f.reads==2)f.facts.leaseUntil=2000;};f.admit();
    f.onSource={};f.facts.leaseUntil=16000;f.now=2500;
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorDispatch, ShortenedLeaseBeforeEncodingCannotRegrowAfterEncoding) {
    DispatchFixture f;f.admit();f.onSource=[&]{
        if(f.reads==3)f.facts.leaseUntil=2000;
        if(f.reads==4){f.facts.leaseUntil=16000;f.now=2500;}};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorDispatch, LateHandoffCannotBecomeAcceptedWhenPostSendSourceExtendsLease) {
    DispatchFixture f;f.admit();f.onSource=[&]{
        if(f.reads==4)f.facts.leaseUntil=2000;
        if(f.reads==5)f.facts.leaseUntil=16000;};f.onSend=[&]{f.now=2500;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::outcome_unknown);EXPECT_TRUE(f.owner.retired());
    EXPECT_EQ(f.deadline,2000u);EXPECT_EQ(f.sends,1);
}
}
namespace {
TEST(ActuatorDispatch, EncodingAllocationFailureIsVisibleAsPermanentOwnerRetirement) {
    DispatchFixture f;f.admit();ActuatorDispatch::Outcome outcome;
    struct RejectJsonAllocation {
        RejectJsonAllocation(){cJSON_Hooks hooks{[](size_t)->void*{return nullptr;},std::free};cJSON_InitHooks(&hooks);}
        ~RejectJsonAllocation(){cJSON_InitHooks(nullptr);}
    };
    {RejectJsonAllocation reject;outcome=f.owner.dispatch(2100);}
    EXPECT_EQ(outcome,Outcome::refused);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sends,0);
    EXPECT_FALSE(f.owner.accept(dispatchGrant(2,"new"),1000));EXPECT_EQ(f.sends,0);
}
}
