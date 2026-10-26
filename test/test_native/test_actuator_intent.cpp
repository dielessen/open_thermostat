#include "control/ActuatorIntent.h"
#include <gtest/gtest.h>
#include "control/BoundedJson.h"
#include "control/GraphShadowValidation.h"
using heating::control::ActuatorIntent;
namespace {
ActuatorIntent::Scope scope(){return {"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};}
std::string grant(int sequence=1,std::string nonce="receiver1") {
    return "{\"adapter_id\":\"ha\",\"adapter_session_id\":\"session\",\"api\":1,\"binding_id\":\"valve\","
        "\"boot_id\":\"boot\",\"command_kind\":\"room_target\",\"config_digest\":\""+std::string(64,'a')+
        "\",\"config_revision\":4,\"controller_id\":\"ctrl\",\"epoch\":1,\"grant_id\":\""+nonce+
        "\",\"grant_ms\":5000,\"grant_sequence\":"+std::to_string(sequence)+"}";
}
TEST(ActuatorIntent, DefaultClosedAndExplicitLocalAuthorityRequired) {
    ActuatorIntent a(scope());EXPECT_FALSE(a.accept(grant(),scope(),100,100,15100));EXPECT_TRUE(a.retired());
    EXPECT_TRUE(a.command(2100,scope(),101,15100).empty());
}
TEST(ActuatorIntent, ExactReceiverEnvelopeAndSingleEmissionPerGrant) {
    ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(),scope(),100,100,15100));
    auto raw=a.command(2100,scope(),101,15100);ASSERT_FALSE(raw.empty());
    auto root=heating::control::parseControlJson(raw);
    EXPECT_EQ(heating::graph_test::integer(heating::graph_test::get(root.get(),"sequence"),1,UINT32_MAX),1);
    EXPECT_FALSE(heating::graph_test::get(root.get(),"grant_ms"));
    EXPECT_TRUE(a.command(2200,scope(),102,15100).empty());
    EXPECT_FALSE(a.accept(grant(),scope(),103,103,15103));
    ASSERT_TRUE(a.accept(grant(2,"receiver2"),scope(),104,104,15104));
    root=heating::control::parseControlJson(a.command(2200,scope(),105,15104));
    EXPECT_EQ(heating::graph_test::integer(heating::graph_test::get(root.get(),"sequence"),1,UINT32_MAX),2);
}
TEST(ActuatorIntent, DuplicateGrantCannotExtendOriginalRequestBudget) {
    ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(),scope(),100,0,20000));
    EXPECT_TRUE(a.accept(grant(),scope(),4999,4999,30000));
    EXPECT_TRUE(a.command(2100,scope(),5000,30000).empty());
    EXPECT_FALSE(a.accept(grant(),scope(),5001,5001,30000));
}
TEST(ActuatorIntent, LocalLeaseBoundsGrantEvenWhenCallerLaterSuppliesLongerLease) {
    ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(),scope(),100,100,200));
    EXPECT_TRUE(a.command(2100,scope(),200,30000).empty());
}
TEST(ActuatorIntent, DelayedRetainedFutureAndExpiredRequestNeverAdmit) {
    for(int kind=0;kind<3;++kind) {
        ActuatorIntent a(scope(),[]{return true;});
        EXPECT_FALSE(a.accept(grant(),scope(),100,kind==0?101:100,kind==1?100:20000,kind==2));
        EXPECT_TRUE(a.command(2100,scope(),101,20000).empty());
    }
}
TEST(ActuatorIntent, ExpiredRequestAndByteBoundsRejectWithoutConsumingGrant) {
    ActuatorIntent a(scope(),[]{return true;});
    EXPECT_FALSE(a.accept(grant(),scope(),5000,0,20000));
    EXPECT_FALSE(a.accept(std::string(2049,' '),scope(),5001,5001,20000));
    ASSERT_TRUE(a.accept(grant(),scope(),5002,5002,20000));
    EXPECT_FALSE(a.command(2100,scope(),5003,20000).empty());
}
TEST(ActuatorIntent, ChangedOwnerClockReversalAndAuthorityLossAreSticky) {
    for(int kind=0;kind<4;++kind) {
        bool allowed=true;ActuatorIntent a(scope(),[&]{return allowed;});
        ASSERT_TRUE(a.accept(grant(),scope(),100,100,20000));auto changed=scope();
        if(kind==0)changed.boot="newboot";
        if(kind==1)changed.digest=std::string(64,'b');
        if(kind==3)allowed=false;
        EXPECT_TRUE(a.command(2100,changed,kind==2?99:101,20000).empty());
        EXPECT_TRUE(a.retired());allowed=true;
        EXPECT_FALSE(a.accept(grant(2,"receiver2"),scope(),102,102,20000));
    }
}
TEST(ActuatorIntent, InvalidWireDoesNotConsumeGrantOrCreateReadiness) {
    for(auto raw:{std::string("{}"),std::string("{\"api\":true}"),grant()+"x",grant()+"\n{}"}) {
        ActuatorIntent a(scope(),[]{return true;});EXPECT_FALSE(a.accept(raw,scope(),100,100,20000));
        EXPECT_TRUE(a.command(2100,scope(),101,20000).empty());
        EXPECT_TRUE(a.accept(grant(),scope(),102,102,20000));
    }
}
TEST(ActuatorIntent, OldGrantChangedNonceAndInvalidTargetCannotConsumeFreshIntent) {
    ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(2),scope(),100,100,20000));
    EXPECT_FALSE(a.accept(grant(1,"older"),scope(),101,101,20000));
    EXPECT_FALSE(a.accept(grant(2,"changed"),scope(),102,102,20000));
    EXPECT_FALSE(a.accept(grant(3),scope(),103,103,20000));
    EXPECT_TRUE(a.command(499,scope(),104,20000).empty());
    EXPECT_TRUE(a.command(3501,scope(),105,20000).empty());
    EXPECT_FALSE(a.command(3500,scope(),106,20000).empty());
}
TEST(ActuatorIntent, ReentrantRetirementAndThrowingAuthorityCannotEmit) {
    ActuatorIntent* ptr=nullptr;
    ActuatorIntent a(scope(),[&]{ptr->retire();return true;});ptr=&a;
    EXPECT_FALSE(a.accept(grant(),scope(),100,100,20000));EXPECT_TRUE(a.retired());
    ActuatorIntent b(scope(),[]{throw std::runtime_error("lost authority");return true;});
    EXPECT_FALSE(b.accept(grant(),scope(),100,100,20000));EXPECT_TRUE(b.retired());
}
}
namespace {
TEST(ActuatorIntent, AuthorityCannotChangeCurrentScopeDuringAdmission) {
    auto current=scope();
    ActuatorIntent a(scope(),[&]{current.session="replacement";return true;});
    EXPECT_FALSE(a.accept(grant(),current,100,100,20000));
    EXPECT_TRUE(a.retired());
}
TEST(ActuatorIntent, ReentrantAuthorityCannotRecursivelyUseOwner) {
    ActuatorIntent* ptr=nullptr;
    ActuatorIntent a(scope(),[&]{ptr->command(2100,scope(),100,20000);return true;});ptr=&a;
    EXPECT_FALSE(a.accept(grant(),scope(),100,100,20000));EXPECT_TRUE(a.retired());
}
TEST(ActuatorIntent, ObservedLeaseLossCannotBeUndoneByRenewal) {
    for(bool receive:{false,true}) {
        ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(),scope(),100,100,200));
        if(receive)EXPECT_FALSE(a.accept(grant(2,"next"),scope(),200,200,200));
        else EXPECT_TRUE(a.command(2100,scope(),200,200).empty());
        EXPECT_TRUE(a.retired());
        EXPECT_FALSE(a.accept(grant(3,"later"),scope(),201,201,20000));
    }
}
}
namespace {
TEST(ActuatorIntent, ShorterLeaseOnExactGrantReadCanNeverBeExtendedAgain) {
    ActuatorIntent a(scope(),[]{return true;});ASSERT_TRUE(a.accept(grant(),scope(),100,100,4000));
    ASSERT_TRUE(a.accept(grant(),scope(),150,100,200));
    EXPECT_TRUE(a.command(2100,scope(),201,30000).empty());
}
}
