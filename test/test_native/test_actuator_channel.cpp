#include "control/ActuatorChannel.h"
#include <gtest/gtest.h>
using heating::control::ActuatorChannel;
namespace {
using Outcome=ActuatorChannel::Outcome;
struct ChannelFixture {
    uint64_t now=1000;
    ActuatorChannel::Scope scope{"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};
    ActuatorChannel::Facts facts{scope,16000,true};
    struct Frame{std::string topic,raw;uint64_t deadline;};
    std::vector<Frame> sent;
    std::function<void()> onSource,onSend;
    bool accepted=true;
    ActuatorChannel owner{scope,[&]{if(onSource)onSource();return facts;},[&]{return now;},
        [&](std::string_view topic,std::string_view raw,uint64_t deadline){sent.push_back({std::string(topic),std::string(raw),deadline});if(onSend)onSend();return accepted;}};
    std::string grant(int request=1,int sequence=1) {
        return "{\"adapter_id\":\"ha\",\"adapter_session_id\":\"session\",\"api\":1,\"binding_id\":\"valve\","
            "\"boot_id\":\"boot\",\"command_kind\":\"room_target\",\"config_digest\":\""+std::string(64,'a')+
            "\",\"config_revision\":4,\"controller_id\":\"ctrl\",\"epoch\":1,\"grant_id\":\"receiver"+std::to_string(sequence)+
            "\",\"grant_ms\":5000,\"grant_sequence\":"+std::to_string(sequence)+",\"request_sequence\":"+std::to_string(request)+"}";
    }
    void admit(){ASSERT_EQ(owner.request(),Outcome::transport_accepted);ASSERT_TRUE(owner.receive("ha/actuator_grant/valve",grant()));}
};
TEST(ActuatorChannel, MissingProducersDefaultClosed) {
    ChannelFixture f;ActuatorChannel owner(f.scope);EXPECT_TRUE(owner.retired());EXPECT_EQ(owner.request(),Outcome::refused);
}
TEST(ActuatorChannel, CanonicalRequestAndCorrelatedGrantSendOnceOnSameTransport) {
    ChannelFixture f;f.admit();ASSERT_EQ(f.sent.size(),1u);
    EXPECT_EQ(f.sent[0].topic,"fw/actuator_grant_request/valve");EXPECT_EQ(f.sent[0].deadline,6000u);
    const auto root=heating::control::parseControlJson(f.sent[0].raw);ASSERT_TRUE(root);
    EXPECT_EQ(cJSON_GetArraySize(root.get()),11);EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(root.get(),"request_sequence")->valueint,1);
    EXPECT_EQ(f.owner.request(),Outcome::refused);
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);ASSERT_EQ(f.sent.size(),2u);
    EXPECT_EQ(f.sent[1].topic,"fw/actuator_command/valve");EXPECT_EQ(f.sent[1].deadline,6000u);
    EXPECT_EQ(f.owner.dispatch(2200),Outcome::refused);EXPECT_EQ(f.sent.size(),2u);
    EXPECT_EQ(f.owner.request(),Outcome::transport_accepted);
    EXPECT_TRUE(f.owner.receive("ha/actuator_grant/valve",f.grant(1,2)));
    EXPECT_EQ(f.owner.dispatch(2200),Outcome::refused);
    EXPECT_TRUE(f.owner.receive("ha/actuator_grant/valve",f.grant(2,2)));
    EXPECT_EQ(f.owner.dispatch(2200),Outcome::transport_accepted);EXPECT_EQ(f.sent.size(),4u);
}
TEST(ActuatorChannel, UnsolicitedRetainedWrongBindingAndOldRepliesCannotSend) {
    for(int kind=0;kind<5;++kind){ChannelFixture f;
        if(kind){ASSERT_EQ(f.owner.request(),Outcome::transport_accepted);}
        const auto topic=kind==2?"ha/actuator_grant/other":"ha/actuator_grant/valve";
        f.owner.receive(topic,kind==3?f.grant(2):kind==4?"{}":f.grant(),kind==1);
        EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sent.size(),kind?1u:0u);
    }
}
TEST(ActuatorChannel, OriginalBudgetExpiresAndLateReplyCannotBorrowNextRequest) {
    ChannelFixture f;ASSERT_EQ(f.owner.request(),Outcome::transport_accepted);f.now=6000;f.owner.checkCurrent();
    ASSERT_EQ(f.owner.request(),Outcome::transport_accepted);
    f.owner.receive("ha/actuator_grant/valve",f.grant(1,1));EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);
    f.owner.receive("ha/actuator_grant/valve",f.grant(2,2));EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);
    ASSERT_EQ(f.sent.size(),3u);EXPECT_EQ(f.sent.back().deadline,11000u);
}
TEST(ActuatorChannel, DuplicateGrantCannotRenewOriginalDeadline) {
    ChannelFixture f;f.admit();f.now=5999;f.owner.receive("ha/actuator_grant/valve",f.grant());
    f.now=6000;EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sent.size(),1u);
}
TEST(ActuatorChannel, LeaseShrinksAndCannotRegrowBeforeCommand) {
    ChannelFixture f;f.admit();f.facts.leaseUntil=2000;f.owner.checkCurrent();f.facts.leaseUntil=16000;f.now=2000;
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sent.size(),1u);
}
TEST(ActuatorChannel, SourceLossClockReversalAndDisconnectRetirePermanently) {
    for(int kind=0;kind<4;++kind){ChannelFixture f;f.admit();
        if(kind==0)f.facts.authorized=false;else if(kind==1)f.facts.scope.session="new";
        else if(kind==2)f.now=999;else f.owner.retire();
        f.owner.checkCurrent();EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);
        f.now=1000;f.facts={f.scope,16000,true};EXPECT_EQ(f.owner.request(),Outcome::refused);EXPECT_EQ(f.sent.size(),1u);
    }
}
TEST(ActuatorChannel, FailedThrowingOrLateRequestHandoffNeverRetries) {
    for(int kind=0;kind<3;++kind){ChannelFixture f;
        if(kind==0)f.accepted=false;else if(kind==1)f.onSend=[]{throw std::runtime_error("IO");};else f.onSend=[&]{f.now=6000;};
        EXPECT_EQ(f.owner.request(),Outcome::outcome_unknown);EXPECT_TRUE(f.owner.retired());
        EXPECT_EQ(f.owner.request(),Outcome::refused);EXPECT_EQ(f.sent.size(),1u);
    }
}
TEST(ActuatorChannel, ReentryCannotIssueOrDispatchAnotherRequest) {
    ChannelFixture f;f.onSend=[&]{EXPECT_EQ(f.owner.request(),Outcome::refused);};
    EXPECT_EQ(f.owner.request(),Outcome::outcome_unknown);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sent.size(),1u);
}
TEST(ActuatorChannel, InvalidTargetDoesNotConsumeCorrelatedGrant) {
    ChannelFixture f;f.admit();EXPECT_EQ(f.owner.dispatch(499),Outcome::refused);
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);EXPECT_EQ(f.sent.size(),2u);
}
TEST(ActuatorChannel, ShrinkingLeaseWhileEncodingBoundsRequestHandoff) {
    ChannelFixture f;int reads=0;f.onSource=[&]{if(++reads==2)f.facts.leaseUntil=2000;};
    ASSERT_EQ(f.owner.request(),Outcome::transport_accepted);ASSERT_EQ(f.sent.size(),1u);EXPECT_EQ(f.sent[0].deadline,2000u);
}
}
namespace {
TEST(ActuatorChannel, DispatcherClockObservationsAlsoFenceNextRequest) {
    ChannelFixture f;f.admit();int reads=0;
    f.onSource=[&]{if(++reads==2)f.now=2000;};
    ASSERT_EQ(f.owner.dispatch(2100),Outcome::transport_accepted);
    f.onSource={};f.now=1500;
    EXPECT_EQ(f.owner.request(),Outcome::refused);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sent.size(),2u);
}
TEST(ActuatorChannel, RememberedShortLeaseStillAppliesWhenDispatcherSamplesLaterTime) {
    ChannelFixture f;f.admit();f.facts.leaseUntil=2000;f.owner.checkCurrent();f.facts.leaseUntil=16000;
    int reads=0;f.onSource=[&]{if(++reads==2)f.now=2500;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_EQ(f.sent.size(),1u);
}
}
namespace {
TEST(ActuatorChannel, LateReturnUsesShortenedChannelDeadlineNotOldInnerDeadline) {
    ChannelFixture f;f.admit();f.facts.leaseUntil=2000;f.owner.checkCurrent();f.facts.leaseUntil=16000;f.now=1999;
    f.onSend=[&]{f.now=2500;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::outcome_unknown);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sent.size(),2u);
    f.now=2501;EXPECT_EQ(f.owner.request(),Outcome::refused);
}
}

namespace {
TEST(ActuatorChannel, OuterClockObservationAlsoFencesInnerDispatchReads) {
    ChannelFixture f;f.admit();f.now=2000;f.owner.checkCurrent();int reads=0;
    f.onSource=[&]{if(++reads==2)f.now=1500;};
    EXPECT_EQ(f.owner.dispatch(2100),Outcome::refused);EXPECT_TRUE(f.owner.retired());EXPECT_EQ(f.sent.size(),1u);
}
}
