#include "control/ActuatorChannels.h"
#include <gtest/gtest.h>
using heating::control::ActuatorChannels;
using heating::control::ActuatorChannel;
namespace {
using Outcome=ActuatorChannel::Outcome;
struct ChannelsFixture {
    uint64_t now=1000;bool network=true,tcp=true,authority=true;
    int factories=0,sends=0,availabilityReads=0,contextReads=0;bool sendResult=true;std::function<void()> onFactory,onSource,onSend,onAvailable,onContext,onClock;
    ActuatorChannels* pointer=nullptr;
    heating::control::ActuatorScope scope(std::string_view binding){return {"ctrl","boot","ha","session",std::string(64,'a'),std::string(binding),1,4};}
    ActuatorChannels channels{
        [&](const heating::control::ActuatorSessionContext& context)->ActuatorChannel::Source{
            ++factories;if(onFactory)onFactory();const auto original=context.scope;
            return [&,original]{if(onSource)onSource();return ActuatorChannel::Facts{original,16000,authority};};
        },
        [&](std::string_view binding,uint64_t)->std::optional<heating::control::ActuatorSessionContext>{++contextReads;if(onContext)onContext();return heating::control::ActuatorSessionContext{scope(binding),16000,16000};},
        [&]{++availabilityReads;if(onAvailable)onAvailable();return network&&tcp;},[&]{if(onClock)onClock();return now;},
        [&](std::string_view,std::string_view,uint64_t){++sends;if(onSend)onSend();return sendResult;}};
    ChannelsFixture(){pointer=&channels;}
    std::string grant(){return "{\"adapter_id\":\"ha\",\"adapter_session_id\":\"session\",\"api\":1,\"binding_id\":\"valve\",\"boot_id\":\"boot\",\"command_kind\":\"room_target\",\"config_digest\":\""+std::string(64,'a')+"\",\"config_revision\":4,\"controller_id\":\"ctrl\",\"epoch\":1,\"grant_id\":\"receiver1\",\"grant_ms\":5000,\"grant_sequence\":1,\"request_sequence\":1}";}
};
TEST(ActuatorChannels, SameBindingHasExactlyOneLifetimeOwner) {
    ChannelsFixture f;auto* first=f.channels.get("valve");ASSERT_NE(first,nullptr);
    EXPECT_EQ(first,f.channels.get("valve"));EXPECT_EQ(f.factories,1);EXPECT_EQ(f.channels.size(),1u);
    ASSERT_EQ(first->request(),Outcome::transport_accepted);
    ASSERT_TRUE(f.channels.receive("ha/actuator_grant/valve",f.grant()));
    EXPECT_EQ(first->dispatch(2100),Outcome::transport_accepted);EXPECT_EQ(f.sends,2);
}
TEST(ActuatorChannels, InventoryNeverExceedsEightIndependentlyQualifiedBindings) {
    ChannelsFixture f;for(int i=0;i<8;++i)ASSERT_NE(f.channels.get("v"+std::to_string(i)),nullptr);
    EXPECT_EQ(f.channels.get("ninth"),nullptr);EXPECT_EQ(f.factories,8);EXPECT_EQ(f.channels.size(),8u);
}
TEST(ActuatorChannels, SameOrOtherBindingFactoryReentryCannotCreateDuplicatesOrExceedLimit) {
    for(bool same:{false,true}){ChannelsFixture f;f.onFactory=[&]{if(f.factories==1){EXPECT_EQ(f.channels.get(same?"valve":"other"),nullptr);}};
        EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_TRUE(f.channels.retired());
        EXPECT_EQ(f.factories,1);EXPECT_EQ(f.channels.size(),0u);EXPECT_EQ(f.sends,0);
    }
}
TEST(ActuatorChannels, SourceReentryDuringIterationCannotMutateContainer) {
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    f.onSource=[&]{EXPECT_EQ(f.channels.get("other"),nullptr);};
    f.channels.checkCurrent();EXPECT_TRUE(f.channels.retired());EXPECT_TRUE(channel->retired());
    EXPECT_EQ(f.factories,1);EXPECT_EQ(f.channels.size(),1u);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorChannels, SourceReentryDuringGrantDeliveryCannotInvalidateIterators) {
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    ASSERT_EQ(channel->request(),Outcome::transport_accepted);
    f.onSource=[&]{EXPECT_EQ(f.channels.get("other"),nullptr);};
    EXPECT_TRUE(f.channels.receive("ha/actuator_grant/valve",f.grant()));
    EXPECT_TRUE(f.channels.retired());EXPECT_TRUE(channel->retired());EXPECT_EQ(f.channels.size(),1u);
    EXPECT_EQ(channel->dispatch(2100),Outcome::refused);EXPECT_EQ(f.sends,1);
}
TEST(ActuatorChannels, SourceReentryOutsideIterationIsAlsoClosed) {
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    f.onSource=[&]{EXPECT_EQ(f.channels.get("other"),nullptr);};
    EXPECT_EQ(channel->request(),Outcome::refused);EXPECT_TRUE(f.channels.retired());EXPECT_EQ(f.sends,0);
}
TEST(ActuatorChannels, KnownNetworkLossWithTcpStillConnectedStopsBeforeIOAndCannotRevive) {
    for(bool beforeOwner:{false,true}){ChannelsFixture f;auto* channel=beforeOwner?nullptr:f.channels.get("valve");f.network=false;
        EXPECT_TRUE(f.tcp);
        if(channel)EXPECT_EQ(channel->request(),Outcome::refused);else EXPECT_EQ(f.channels.get("valve"),nullptr);
        EXPECT_TRUE(f.channels.retired());f.network=true;EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_EQ(f.sends,0);
    }
}
TEST(ActuatorChannels, NetworkLossInsideFactoryPreventsOwnerCreation) {
    ChannelsFixture f;f.onFactory=[&]{f.network=false;};
    EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_TRUE(f.channels.retired());EXPECT_EQ(f.channels.size(),0u);
}
TEST(ActuatorChannels, NetworkLossInsideQualificationStopsBeforeIOAndCannotRevive) {
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    f.onSource=[&]{f.network=false;};EXPECT_EQ(channel->request(),Outcome::refused);EXPECT_EQ(f.sends,0);
    EXPECT_TRUE(f.channels.retired());f.onSource={};f.network=true;
    EXPECT_EQ(channel->request(),Outcome::refused);EXPECT_EQ(f.channels.get("valve"),nullptr);
}
TEST(ActuatorChannels, RetiredInventoryCannotRecreateOwnerAfterReconnect) {
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    f.channels.retire();f.network=false;f.channels.checkCurrent();f.network=true;
    EXPECT_EQ(f.channels.get("other"),nullptr);EXPECT_EQ(channel->request(),Outcome::refused);EXPECT_EQ(f.sends,0);
}
}

namespace {
TEST(ActuatorChannels, FailedOrOfflineSharedHandoffRetiresAllOwners) {
    for(int kind=0;kind<3;++kind){ChannelsFixture f;auto* a=f.channels.get("valve");auto* b=f.channels.get("other");
        ASSERT_NE(a,nullptr);ASSERT_NE(b,nullptr);
        if(kind==0)f.sendResult=false;else if(kind==1)f.onSend=[&]{f.network=false;};else f.onSend=[]{throw std::runtime_error("IO");};
        EXPECT_EQ(a->request(),Outcome::outcome_unknown);EXPECT_TRUE(f.channels.retired());EXPECT_TRUE(b->retired());
        f.network=true;f.sendResult=true;f.onSend={};EXPECT_EQ(b->request(),Outcome::refused);EXPECT_EQ(f.sends,1);
    }
}
}

namespace {
TEST(ActuatorChannels, SharedHandoffClockObservationCannotBeLostAfterIO) {
    ChannelsFixture baseline;auto* b=baseline.channels.get("valve");ASSERT_NE(b,nullptr);int handoffRead=0;
    baseline.onSend=[&]{handoffRead=baseline.availabilityReads;};ASSERT_EQ(b->request(),Outcome::transport_accepted);
    ASSERT_GT(handoffRead,0);
    ChannelsFixture f;auto* channel=f.channels.get("valve");ASSERT_NE(channel,nullptr);
    f.onAvailable=[&]{if(f.availabilityReads==handoffRead)f.now=2000;};f.onSend=[&]{f.now=1500;};
    EXPECT_EQ(channel->request(),Outcome::outcome_unknown);EXPECT_TRUE(f.channels.retired());EXPECT_EQ(f.sends,1);
}
TEST(ActuatorChannels, ClockObservedByAnotherChannelFencesBeforeNextIO) {
    ChannelsFixture f;auto* a=f.channels.get("valve");auto* b=f.channels.get("other");ASSERT_NE(a,nullptr);ASSERT_NE(b,nullptr);
    f.now=2000;ASSERT_EQ(a->request(),Outcome::transport_accepted);f.now=1500;
    EXPECT_EQ(b->request(),Outcome::refused);EXPECT_TRUE(f.channels.retired());EXPECT_EQ(f.sends,1);
}
TEST(ActuatorChannels, ContextRetirementReentryOrOutageNeverCommitsNewOwner) {
    for(int lookup:{1,2})for(int kind=0;kind<3;++kind){ChannelsFixture f;
        f.onContext=[&]{if(f.contextReads!=lookup)return;if(kind==0)f.channels.retire();else if(kind==1){EXPECT_EQ(f.channels.get("other"),nullptr);}else f.network=false;};
        EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_TRUE(f.channels.retired());EXPECT_EQ(f.channels.size(),0u);
        EXPECT_EQ(f.factories,lookup==1?0:1);f.network=true;f.onContext={};EXPECT_EQ(f.channels.get("valve"),nullptr);
    }
}
TEST(ActuatorChannels, ContextRetirementKeepsExistingPointersStableAndRetired) {
    ChannelsFixture f;auto* existing=f.channels.get("first");ASSERT_NE(existing,nullptr);
    f.onContext=[&]{if(f.contextReads==4)f.channels.retire();};
    EXPECT_EQ(f.channels.get("second"),nullptr);EXPECT_EQ(f.channels.size(),1u);EXPECT_TRUE(existing->retired());
    EXPECT_EQ(existing->request(),Outcome::refused);EXPECT_EQ(f.sends,0);
}
}

namespace {
TEST(ActuatorChannels, RecursiveFinalHandoffAvailabilityRetiresEveryOwnerBeforeIO) {
    ChannelsFixture f;auto* a=f.channels.get("valve");auto* b=f.channels.get("other");
    ASSERT_NE(a,nullptr);ASSERT_NE(b,nullptr);
    int nested=0;
    // Bounded even on the defective implementation: this test must not overflow.
    f.onAvailable=[&]{if(++nested==1){EXPECT_FALSE(f.channels.beforeHandoff(5000));}};
    EXPECT_FALSE(f.channels.beforeHandoff(5000));
    EXPECT_TRUE(f.channels.retired());EXPECT_TRUE(a->retired());EXPECT_TRUE(b->retired());
    EXPECT_EQ(nested,1);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorChannels, FinalHandoffAvailabilityCannotAdmitAnotherOwner) {
    ChannelsFixture f;auto* a=f.channels.get("valve");ASSERT_NE(a,nullptr);
    int reads=0;
    f.onAvailable=[&]{if(++reads==1){EXPECT_EQ(f.channels.get("other"),nullptr);}};
    EXPECT_FALSE(f.channels.beforeHandoff(5000));
    EXPECT_TRUE(f.channels.retired());EXPECT_TRUE(a->retired());
    EXPECT_EQ(f.channels.size(),1u);EXPECT_EQ(f.factories,1);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorChannels, RecursiveFinalHandoffClockRetiresBeforeIO) {
    int reads=0;ActuatorChannels* owner=nullptr;
    ActuatorChannels channels{[](const auto&)->ActuatorChannel::Source{return {};},
        [](std::string_view,uint64_t)->std::optional<heating::control::ActuatorSessionContext>{return {};},
        []{return true;},[&]()->uint64_t{if(++reads==1){EXPECT_FALSE(owner->beforeHandoff(5000));}return 1000;},
        [](std::string_view,std::string_view,uint64_t){ADD_FAILURE();return true;}};
    owner=&channels;
    EXPECT_FALSE(channels.beforeHandoff(5000));EXPECT_TRUE(channels.retired());EXPECT_EQ(reads,1);
}
TEST(ActuatorChannels, OrdinaryFinalHandoffAndExpiredDeadlineRemainBounded) {
    ChannelsFixture f;auto* a=f.channels.get("valve");ASSERT_NE(a,nullptr);
    f.onSend=[&]{EXPECT_TRUE(f.channels.beforeHandoff(5000));};
    EXPECT_EQ(a->request(),Outcome::transport_accepted);EXPECT_FALSE(f.channels.retired());EXPECT_EQ(f.sends,1);
    EXPECT_FALSE(f.channels.beforeHandoff(f.now));EXPECT_FALSE(f.channels.retired());
}
}

namespace {
TEST(ActuatorChannels, AvailabilityCannotReenterHandoffFromNormalAdmission) {
    ChannelsFixture f;int calls=0;
    f.onAvailable=[&]{if(++calls==1){EXPECT_FALSE(f.channels.beforeHandoff(5000));}};
    EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_TRUE(f.channels.retired());
    EXPECT_EQ(calls,1);EXPECT_EQ(f.factories,0);EXPECT_EQ(f.sends,0);
}
TEST(ActuatorChannels, ClockCannotReenterHandoffFromNormalAdmission) {
    ChannelsFixture f;int calls=0;
    f.onClock=[&]{if(++calls==1){EXPECT_FALSE(f.channels.beforeHandoff(5000));}};
    EXPECT_EQ(f.channels.get("valve"),nullptr);EXPECT_TRUE(f.channels.retired());
    EXPECT_EQ(calls,1);EXPECT_EQ(f.factories,0);EXPECT_EQ(f.sends,0);
}
}
