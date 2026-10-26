#include "BoilerTestIoFixture.h"
#include "EMS/BoilerTestService.h"
#include "control/HttpAccessPolicy.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <sstream>
namespace {
using namespace heating::ems;
using heating::control::ControlJson;
using Command=BoilerTestSession::Command;
struct FaultClosure:testing::Test {
    BoilerTestSession::Profile profile{true,20,60,10000,3000,2000,5000,100};
    BoilerTestSession::Gates gates{true,true,true,true,true};
    ClassicBoilerMonitor monitor;
    BoilerTestService service{42,true,profile,true};
    const std::string owner=std::string(64,'a'),other=std::string(64,'b');
    const std::string scope=R"({"schema":1,"boot_id":"000000000000002a","revision":1})";
    const std::string close=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"local_stop_confirmed":true})";
    void report(uint64_t at,bool cv=false,uint8_t power=0,bool dhw=false,uint8_t selected=0){monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{selected,1,0x72,80,power,static_cast<uint8_t>(cv?9:dhw?10:0)}},at);}
    void fault(){report(90);ASSERT_EQ(service.action("prepare_zero",scope,owner,100,gates,monitor).http,202);service.transportFault(101);ASSERT_TRUE(service.active());}
    void sentZero(){fault();const auto zero=service.next(102,gates,monitor);ASSERT_EQ(zero.command,Command::zero);ASSERT_TRUE(testing_detail::instantTransmission(service,zero,102,true,gates,monitor));}
    void confirmed(){sentZero();report(103);service.tick(103,gates,monitor);}
    ControlJson status(uint64_t now){std::ostringstream out;service.writeJSON(out,now,owner,gates,monitor);return ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);}
};
TEST_F(FaultClosure, FaultNeverClosesAutomaticallyEvenWithReportedStop){
    confirmed();auto json=status(104);
    EXPECT_TRUE(service.active());EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_close_fault")));
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"fault");
    EXPECT_TRUE(heating::control::boilerTestMutationBlocked("/ota",service.active()));
}
TEST_F(FaultClosure, ExplicitAcknowledgmentRetiresFaultAndKeepsNewTrialsBlockedUntilReboot){
    confirmed();ASSERT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,202);
    EXPECT_FALSE(service.active());EXPECT_EQ(service.next(104,gates,monitor).command,Command::none);
    EXPECT_FALSE(heating::control::boilerTestMutationBlocked("/ota",service.active()));
    auto json=status(104);EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"closed");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"reason")),"test_transport_unavailable");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"restart_required")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_prepare_zero")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_start")));
    auto next=scope;next.replace(next.find("revision\":1")+10,1,"2");
    EXPECT_STREQ(service.action("prepare_zero",next,owner,105,gates,monitor).error,"restart_required");
    EXPECT_STREQ(service.action("start",scope,owner,105,gates,monitor).error,"restart_required");
    EXPECT_EQ(service.next(10000,gates,monitor).command,Command::none);
    EXPECT_TRUE(service.action("close_fault",close,other,10001,gates,monitor).duplicate);
}
TEST_F(FaultClosure, ReportWithoutActuallyTransmittedZeroCannotClose){
    fault();report(103);service.tick(103,gates,monitor);
    EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);EXPECT_TRUE(service.active());
}
TEST_F(FaultClosure, SameTimestampActiveBurnerDhwOrStaleFeedbackCannotClose){
    sentZero();
    report(102);EXPECT_EQ(service.action("close_fault",close,owner,102,gates,monitor).http,409);
    report(103,true,10);EXPECT_EQ(service.action("close_fault",close,owner,103,gates,monitor).http,409);
    report(104,false,0,true);EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);
    report(105);service.tick(105,gates,monitor);
    EXPECT_EQ(service.action("close_fault",close,owner,2200,gates,monitor).http,409);EXPECT_TRUE(service.active());
    auto json=status(2200);EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_close_fault")));
}
TEST_F(FaultClosure, EveryRelevantLostGateDeniesClosureAndOtherOperatorCanOnlyAcknowledgeCurrentScope){
    confirmed();
    for(auto field:{&BoilerTestSession::Gates::transmitterReviewed,&BoilerTestSession::Gates::exclusiveOwner,&BoilerTestSession::Gates::independentStopAvailable}){
        gates.*field=false;EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);gates.*field=true;
    }
    EXPECT_EQ(service.action("close_fault",close,other,105,gates,monitor).http,202);
}
TEST_F(FaultClosure, ClosureRequiresAuthenticationExactScopeAndExplicitBoolean){
    confirmed();EXPECT_EQ(service.action("close_fault",close,"",104,gates,monitor).http,401);
    EXPECT_EQ(service.action("close_fault",scope,owner,104,gates,monitor).http,400);
    for(const char* value:{"false","1","\"true\"","null"}){auto body=close;body.replace(body.find("local_stop_confirmed\":true")+22,4,value);EXPECT_EQ(service.action("close_fault",body,owner,104,gates,monitor).http,400);}
    auto wrong=close;wrong.replace(wrong.find("000000000000002a"),16,"000000000000002b");EXPECT_EQ(service.action("close_fault",wrong,owner,104,gates,monitor).http,409);
    wrong=close;wrong.replace(wrong.find("revision\":1")+10,1,"2");EXPECT_EQ(service.action("close_fault",wrong,owner,104,gates,monitor).http,409);
    EXPECT_TRUE(service.active());
}
TEST_F(FaultClosure, InFlightZeroCannotBeRetiredOrUsedAsStopProof){
    fault();auto zero=service.next(102,gates,monitor);ASSERT_TRUE(service.beginTransmit(zero,102,gates,monitor));
    report(103);EXPECT_EQ(service.action("close_fault",close,owner,103,gates,monitor).http,409);
    ASSERT_TRUE(service.finishTransmit(zero,104,true,gates,monitor));
    EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);
    report(105);EXPECT_EQ(service.action("close_fault",close,owner,105,gates,monitor).http,202);
    EXPECT_FALSE(service.mayTransmit(zero,106,gates,monitor));
}
TEST_F(FaultClosure, BurnerPauseWithNonzeroSelectedFlowCannotRetireUpdateInterlock){
    sentZero();report(103,false,0,false,40);service.tick(103,gates,monitor);
    auto json=status(104);EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"reported_stop_confirmed")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_close_fault")));
    EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);
    EXPECT_TRUE(service.active());
    report(105);EXPECT_EQ(service.action("close_fault",close,owner,105,gates,monitor).http,202);
}
TEST_F(FaultClosure, MissingPrecommandOrInvalidSelectedFlowCannotCountAsZeroSelection){
    sentZero();
    monitor.receive({EmsTelegram::BROADCAST,8,0,4,0x18,{0,0}},103); // power and switches only
    EXPECT_EQ(service.action("close_fault",close,owner,103,gates,monitor).http,409);
    report(104,false,0,false,255);EXPECT_EQ(service.action("close_fault",close,owner,104,gates,monitor).http,409);
    EXPECT_TRUE(service.active());report(105);EXPECT_EQ(service.action("close_fault",close,owner,105,gates,monitor).http,202);
}
TEST_F(FaultClosure, OldPositiveTicketCannotSurviveClosingHeatTrialFault){
    report(90);
    const std::string heat=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})";
    ASSERT_EQ(service.action("prepare",heat,owner,100,gates,monitor).http,202);
    auto zero=service.next(100,gates,monitor);ASSERT_TRUE(testing_detail::instantTransmission(service,zero,100,true,gates,monitor));
    report(101);service.tick(101,gates,monitor);
    ASSERT_EQ(service.action("start",scope,owner,102,gates,monitor).http,202);
    const auto positive=service.next(102,gates,monitor);ASSERT_EQ(positive.command,Command::positive);
    ASSERT_TRUE(testing_detail::instantTransmission(service,positive,102,true,gates,monitor));
    service.transportFault(103);
    zero=service.next(104,gates,monitor);ASSERT_EQ(zero.command,Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(service,zero,104,true,gates,monitor));
    report(105);ASSERT_EQ(service.action("close_fault",close,owner,106,gates,monitor).http,202);
    EXPECT_FALSE(service.mayTransmit(positive,107,gates,monitor));EXPECT_FALSE(service.active());
    EXPECT_EQ(service.next(107,gates,monitor).command,Command::none);
}
TEST(BoilerFaultClosureHttp, PostOnlyScopeRemainsReachableDuringActiveTrialWithoutOpeningOtherWrites){
    using namespace heating::control;
    EXPECT_TRUE(allowedHttpMethod("/boiler/test/close_fault","POST"));
    for(const char* method:{"GET","PUT","DELETE"})EXPECT_FALSE(allowedHttpMethod("/boiler/test/close_fault",method));
    EXPECT_FALSE(boilerTestMutationBlocked("/boiler/test/close_fault",true));
    EXPECT_TRUE(boilerTestMutationBlocked("/ota",true));
    EXPECT_FALSE(heating::update::mutationBlocked("/boiler/test/close_fault",true,true,true));
}
}
