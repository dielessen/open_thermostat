#include "BoilerTestIoFixture.h"
#include "EMS/BoilerTestService.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <sstream>
namespace {
using namespace heating::ems;
using heating::control::ControlJson;
struct SiteConfirmation:testing::Test {
    BoilerTestSession::Profile profile{true,20,60,10000,3000,2000,5000,100};
    BoilerTestSession::Gates gates{true,false,true,true,false};
    ClassicBoilerMonitor monitor;
    BoilerTestService service{42,true,profile,true,true};
    std::string owner=std::string(64,'a'),other=std::string(64,'b');
    std::string scope=R"({"schema":1,"boot_id":"000000000000002a","revision":1})";
    std::string zero=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"exclusive_owner_confirmed":true,"independent_stop_confirmed":true})";
    std::string heat=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1,"exclusive_owner_confirmed":true,"independent_stop_confirmed":true,"heat_path_confirmed":true})";
    void SetUp()override{report(90);}
    void report(uint64_t now){monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,1,0x72,80,0,0}},now);}
    ControlJson status(uint64_t now){std::ostringstream out;service.writeJSON(out,now,owner,gates,monitor);return ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);}
};
TEST_F(SiteConfirmation, MissingFalseNumericAndStringDeclarationsCannotPrepare){
    EXPECT_EQ(service.action("prepare_zero",scope,owner,100,gates,monitor).http,400);
    for(const auto* field:{"exclusive_owner_confirmed","independent_stop_confirmed"})for(const auto* replacement:{"false","1","\"true\"","null"}){
        auto body=zero;const auto at=body.find(std::string("\"")+field+"\":true")+std::string(field).size()+3;
        body.replace(at,4,replacement);
        EXPECT_EQ(service.action("prepare_zero",body,owner,100,gates,monitor).http,400)<<body;
    }
    EXPECT_FALSE(service.active());
}
TEST_F(SiteConfirmation, PreviewDoesNotGrantTransmissionOrManufacturePhysicalProof){
    auto json=status(100);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"site_confirmation_required")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_prepare_zero")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"physical_validation")));
    EXPECT_EQ(service.next(100,gates,monitor).command,BoilerTestSession::Command::none);
}
TEST_F(SiteConfirmation, AcceptedZeroBindsDeclarationsToFiniteSessionWithoutHeatGrant){
    ASSERT_EQ(service.action("prepare_zero",zero,owner,100,gates,monitor).http,202);
    auto intent=service.next(100,gates,monitor);ASSERT_EQ(intent.command,BoilerTestSession::Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(service,intent,100,true,gates,monitor));
    EXPECT_EQ(service.action("keepalive",scope,other,101,gates,monitor).http,403);
    report(101);service.tick(101,gates,monitor);
    auto json=status(101);EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"completed");
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"can_start")));
    auto next=scope;next.replace(next.find("revision\":1")+10,1,"2");
    EXPECT_EQ(service.action("prepare_zero",next,owner,102,gates,monitor).http,400);
    EXPECT_EQ(service.next(102,gates,monitor).command,BoilerTestSession::Command::none);
}
TEST_F(SiteConfirmation, HeatNeedsExplicitPathAndStillRequiresReviewedPathAndLimits){
    auto missing=heat;const auto at=missing.find(",\"heat_path_confirmed\"");missing.erase(at,missing.size()-at-1);
    EXPECT_EQ(service.action("prepare",missing,owner,100,gates,monitor).http,400);
    auto unconfirmed=heat;unconfirmed.replace(unconfirmed.find("heat_path_confirmed\":true")+21,4,"false");
    EXPECT_EQ(service.action("prepare",unconfirmed,owner,100,gates,monitor).http,400);
    gates.pathReady=false;EXPECT_EQ(service.action("prepare",heat,owner,100,gates,monitor).http,409);
    gates.pathReady=true;gates.limitsSafe=false;EXPECT_EQ(service.action("prepare",heat,owner,100,gates,monitor).http,409);
    gates.limitsSafe=true;ASSERT_EQ(service.action("prepare",heat,owner,100,gates,monitor).http,202);
}
TEST_F(SiteConfirmation, DeclarationsCannotBypassBootProfileAddressOrCompileBoundaries){
    auto wrong=zero;wrong.replace(wrong.find("000000000000002a"),16,"000000000000002b");
    EXPECT_EQ(service.action("prepare_zero",wrong,owner,100,gates,monitor).http,409);
    gates.transmitterReviewed=false;EXPECT_EQ(service.action("prepare_zero",zero,owner,100,gates,monitor).http,409);
    gates.transmitterReviewed=true;
    BoilerTestService locked{42,false,profile,true,true};EXPECT_STREQ(locked.action("prepare_zero",zero,owner,100,gates,monitor).error,"transmit_blocked");
    BoilerTestService noProfile{42,true,{},true,true};EXPECT_STREQ(noProfile.action("prepare_zero",zero,owner,100,gates,monitor).error,"profile_missing");
    BoilerTestService rebooted{43,true,profile,true,true};EXPECT_EQ(rebooted.action("prepare_zero",zero,owner,100,gates,monitor).http,409);
}
TEST_F(SiteConfirmation, DuplicateCannotRenewLeaseAndControlRequestsCannotCarryDeclarations){
    ASSERT_EQ(service.action("prepare_zero",zero,owner,100,gates,monitor).http,202);
    EXPECT_TRUE(service.action("prepare_zero",zero,owner,200,gates,monitor).duplicate);
    auto json=status(200);EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"operator_remaining_ms")),4900);
    EXPECT_EQ(service.action("keepalive",zero,owner,200,gates,monitor).http,400);
    EXPECT_EQ(service.action("stop",scope,other,201,gates,monitor).http,202);
}
TEST_F(SiteConfirmation, SensorlessHeatRequiresTruePressureDeclarationEveryPreparation) {
    BoilerTestService separate{42,true,profile,true,true,true};
    auto confirmed = heat;
    confirmed.insert(confirmed.size()-1,",\"pressure_check_confirmed\":true");
    ASSERT_LE(confirmed.size(),256u);
    EXPECT_EQ(separate.action("prepare",heat,owner,100,gates,monitor).http,400);
    for (const auto* value : {"false","1","\"true\"","null"}) {
        auto invalid = confirmed;
        invalid.replace(invalid.find("pressure_check_confirmed\":true")+26,4,value);
        EXPECT_EQ(separate.action("prepare",invalid,owner,100,gates,monitor).http,400)<<invalid;
    }
    gates.pathReady=false;
    EXPECT_EQ(separate.action("prepare",confirmed,owner,100,gates,monitor).http,409);
    gates.pathReady=true;gates.limitsSafe=false;
    EXPECT_EQ(separate.action("prepare",confirmed,owner,100,gates,monitor).http,409);
    gates.limitsSafe=true;
    ASSERT_EQ(separate.action("prepare",confirmed,owner,100,gates,monitor).http,202);
    std::ostringstream out;separate.writeJSON(out,100,owner,gates,monitor);
    auto json=ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"pressure_check_required")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"pressure_check_confirmed")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"physical_validation")));
    EXPECT_FALSE(monitor.sample(BoilerField::pressure).raw);
    EXPECT_EQ(separate.action("keepalive",confirmed,owner,101,gates,monitor).http,400);
    EXPECT_EQ(separate.action("start",scope,other,101,gates,monitor).http,403);
    EXPECT_EQ(separate.action("prepare",heat,owner,101,gates,monitor).http,400);
}
TEST_F(SiteConfirmation, SeparatePressureConfirmationCannotBlockZeroOrIndependentStop) {
    BoilerTestService separate{42,true,profile,true,false,true};
    gates.pathReady=false;gates.limitsSafe=false;
    ASSERT_EQ(separate.action("prepare_zero",zero,owner,100,gates,monitor).http,202);
    EXPECT_EQ(separate.next(100,gates,monitor).command,BoilerTestSession::Command::zero);
    EXPECT_EQ(separate.action("stop",scope,other,101,gates,monitor).http,202);
    std::ostringstream out;separate.writeJSON(out,101,owner,gates,monitor);
    auto json=ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"pressure_check_confirmed")));
}
TEST_F(SiteConfirmation, ZeroOnlyTimingProfileCannotCreateHeatAuthorityOrSurviveLostSupervision){
    const auto zeroProfile=BoilerTestSession::Profile::supervisedZeroOnly();
    ASSERT_TRUE(zeroProfile.validForZero());ASSERT_FALSE(zeroProfile.valid());
    BoilerTestService zeroService{42,true,zeroProfile,true,true};
    EXPECT_STREQ(zeroService.action("prepare",heat,owner,100,gates,monitor).error,"profile_missing");
    ASSERT_EQ(zeroService.action("prepare_zero",zero,owner,100,gates,monitor).http,202);
    auto intent=zeroService.next(100,gates,monitor);ASSERT_EQ(intent.command,BoilerTestSession::Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(zeroService,intent,100,true,gates,monitor));
    EXPECT_EQ(zeroService.next(101,gates,monitor).command,BoilerTestSession::Command::none);
    // No fresh feedback or supervision: no positive command can be selected.
    zeroService.tick(5100,gates,monitor);
    intent=zeroService.next(5100,gates,monitor);EXPECT_NE(intent.command,BoilerTestSession::Command::positive);
    zeroService.tick(35100,gates,monitor);
    EXPECT_NE(zeroService.next(35100,gates,monitor).command,BoilerTestSession::Command::positive);
    EXPECT_EQ(zeroService.action("keepalive",scope,owner,35101,gates,monitor).http,409);
}
TEST(BoilerZeroUpdateExclusion, ZeroPreparationCannotOverlapAnyUpdateStateButStopRemainsAllowed){
    for(int bits=0;bits<8;++bits){
        EXPECT_EQ(heating::update::mutationBlocked("/boiler/test/prepare_zero",bits&1,bits&2,bits&4),bits!=0);
        EXPECT_FALSE(heating::update::mutationBlocked("/boiler/test/stop",bits&1,bits&2,bits&4));
    }
}
}
