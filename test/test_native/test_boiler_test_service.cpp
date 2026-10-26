#include "BoilerTestIoFixture.h"
#include "EMS/BoilerTestService.h"
#include "control/HttpAccessPolicy.h"
#include "control/CaptivePortalPolicy.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <sstream>

namespace {
using namespace heating::ems;
using namespace heating::control;
using namespace std::string_literals;
using Command = BoilerTestSession::Command;
struct BoilerService : testing::Test {
    BoilerTestSession::Profile profile{true,20,60,10000,3000,2000,5000,100};
    BoilerTestSession::Gates gates{true,true,true,true,true};
    ClassicBoilerMonitor monitor;
    BoilerTestService service{42,true,profile,true}; // finite fake driver, not installed hardware
    std::string owner = std::string(64,'a'), other = std::string(64,'b');
    const std::string prepare = R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})";
    const std::string action = R"({"schema":1,"boot_id":"000000000000002a","revision":1})";
    void report(uint64_t now) {
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,1,0x72,80,0,0}},now);
    }
    ControlJson status(uint64_t now, std::string_view who = {}) {
        std::ostringstream out;service.writeJSON(out,now,who,gates,monitor);
        return ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    }
    void ready() {
        report(90);
        ASSERT_EQ(service.action("prepare",prepare,owner,100,gates,monitor).http,202);
        auto zero=service.next(100,gates,monitor);
        ASSERT_EQ(zero.command,Command::zero);
        ASSERT_TRUE(testing_detail::instantTransmission(service, zero,100,true,gates,monitor));
        report(101);service.tick(101,gates,monitor);
    }
};

TEST_F(BoilerService, DefaultInstalledBoundaryRefusesActionsAndDoesNotManufactureProfile) {
    report(90);
    BoilerTestService installed{42,false};
    const auto result=installed.action("prepare",prepare,owner,100,gates,monitor);
    EXPECT_EQ(result.http,409);EXPECT_STREQ(result.error,"transmit_blocked");
    EXPECT_EQ(installed.next(100,gates,monitor).command,Command::none);
    std::ostringstream out;installed.writeJSON(out,100,owner,gates,monitor);
    auto json=ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(json.get(),"available")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(json.get(),"limits")));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"revision")),0);
}

TEST_F(BoilerService, MissingReviewedProfileOrDriverCannotBeFilledByHttp) {
    report(90);
    BoilerTestService noDriver{42,true,profile};
    EXPECT_STREQ(noDriver.action("prepare",prepare,owner,100,gates,monitor).error,"test_transport_missing");
    BoilerTestService noProfile{42,true,{},true};
    EXPECT_STREQ(noProfile.action("prepare",prepare,owner,100,gates,monitor).error,"profile_missing");
    auto forged=prepare;forged.insert(forged.size()-1,",\"reviewed\":true");
    EXPECT_EQ(noProfile.action("prepare",forged,owner,100,gates,monitor).http,400);
}

TEST_F(BoilerService, RealPolicyLifecycleKeepsHttpAcceptanceSeparateFromTransmitAndReport) {
    ready();
    auto before=status(101,owner);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(before.get(),"can_start")));
    ASSERT_EQ(service.action("start",action,owner,102,gates,monitor).http,202);
    auto requested=status(102,owner);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(requested.get(),"positive_frames")),0);
    const auto positive=service.next(102,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(service, positive,102,true,gates,monitor));
    ASSERT_EQ(service.action("stop",action,other,103,gates,monitor).http,202);
    EXPECT_FALSE(service.mayTransmit(positive,103,gates,monitor));
    auto zero=service.next(103,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(service, zero,103,true,gates,monitor));
    auto waiting=status(103,owner);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(waiting.get(),"reported_stop_confirmed")));
    report(104);service.tick(104,gates,monitor);
    auto stopped=status(104,owner);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(stopped.get(),"phase")),"completed");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(stopped.get(),"reported_stop_confirmed")));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(stopped.get(),"positive_frames")),1);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(stopped.get(),"zero_frames")),2);
}

TEST_F(BoilerService, OperatorBindingBlocksOtherStartAndRenewalButAllowsCurrentStop) {
    ready();
    EXPECT_EQ(service.action("start",action,other,102,gates,monitor).http,403);
    EXPECT_EQ(service.action("keepalive",action,other,102,gates,monitor).http,403);
    auto own=status(102,owner), foreign=status(102,other);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(own.get(),"owned")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(foreign.get(),"owned")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(foreign.get(),"can_start")));
    EXPECT_EQ(service.action("stop",action,other,103,gates,monitor).http,202);
}

TEST_F(BoilerService, RepeatedPrepareAndStartNeverRenewLeaseOrHeatDuration) {
    ready();
    ASSERT_EQ(service.action("start",action,owner,102,gates,monitor).http,202);
    const auto duplicate=service.action("prepare",prepare,owner,200,gates,monitor);
    EXPECT_EQ(duplicate.http,200);EXPECT_TRUE(duplicate.duplicate);
    EXPECT_TRUE(service.action("start",action,owner,200,gates,monitor).duplicate);
    auto json=status(200,owner);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"heat_remaining_ms")),902);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"operator_remaining_ms")),4900);
}

TEST_F(BoilerService, ReadOnlyStatusCannotRenewOrResurrectLease) {
    ready();
    for(auto now:{1000u,2000u,5000u,5200u}) {auto json=status(now,owner);ASSERT_NE(json,nullptr);}
    service.tick(5200,gates,monitor);
    EXPECT_EQ(service.action("keepalive",action,owner,5200,gates,monitor).http,409);
    auto json=status(5200,owner);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"stopping");
}

TEST_F(BoilerService, RejectsAmbiguousUnboundedAndCoercedRequestsWithoutConsumingRevision) {
    report(90);
    for(const auto& bytes:{std::string(257,'x'),std::string("[]"),std::string("{}"),
        R"({"schema":1,"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})"s,
        R"({"schema":true,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})"s,
        R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40.5,"duration_s":1})"s,
        R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1e999})"s,
        R"({"schema":1,"boot_id":"000000000000002a","revision":9007199254740993,"flow_c":40,"duration_s":1})"s}) {
        EXPECT_EQ(service.action("prepare",bytes,owner,100,gates,monitor).http,400);
    }
    auto json=status(100,owner);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"revision")),0);
    EXPECT_EQ(service.action("prepare",prepare,owner,100,gates,monitor).http,202);
}

TEST_F(BoilerService, StaleBootScopeAndWrongRevisionCannotAffectCurrentSession) {
    ready();
    auto wrongBoot=action;wrongBoot.replace(wrongBoot.find("002a"),4,"002b");
    EXPECT_EQ(service.action("stop",wrongBoot,owner,102,gates,monitor).http,409);
    auto wrongRevision=action;wrongRevision.replace(wrongRevision.find("revision\":1"),11,"revision\":2");
    EXPECT_EQ(service.action("stop",wrongRevision,owner,102,gates,monitor).http,409);
    EXPECT_EQ(service.action("start",action,"",102,gates,monitor).http,401);
    auto json=status(102,owner);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"ready");
}

TEST_F(BoilerService, CookieAndCredentialsNeverAppearInStatus) {
    ready();std::ostringstream out;service.writeJSON(out,102,owner,gates,monitor);
    EXPECT_EQ(out.str().find(owner),std::string::npos);
    EXPECT_EQ(out.str().find("csrf"),std::string::npos);
    EXPECT_EQ(out.str().find("password"),std::string::npos);
    EXPECT_EQ(service.action("unknown",action,owner,102,gates,monitor).http,404);
}

TEST_F(BoilerService, ReadbackOrderTracksActionsWithoutMakingGetAMutation) {
    ready();
    auto before=status(101,owner),later=status(200,owner);
    const auto sequence=cJSON_GetNumberValue(cJSON_GetObjectItem(before.get(),"state_sequence"));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(later.get(),"state_sequence")),sequence);
    ASSERT_EQ(service.action("start",action,owner,201,gates,monitor).http,202);
    auto started=status(201,owner);
    EXPECT_GT(cJSON_GetNumberValue(cJSON_GetObjectItem(started.get(),"state_sequence")),sequence);
    ASSERT_EQ(service.action("stop",action,owner,202,gates,monitor).http,202);
    auto stopped=status(202,owner);
    EXPECT_GT(cJSON_GetNumberValue(cJSON_GetObjectItem(stopped.get(),"state_sequence")),
              cJSON_GetNumberValue(cJSON_GetObjectItem(started.get(),"state_sequence")));
}

TEST_F(BoilerService, OldPrepareCannotReopenAfterANewerExplicitSession) {
    ready();
    ASSERT_EQ(service.action("stop",action,owner,102,gates,monitor).http,202);
    auto zero=service.next(102,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(service, zero,102,true,gates,monitor));
    report(103);service.tick(103,gates,monitor);
    auto next=prepare;next.replace(next.find("revision\":1"),11,"revision\":2");
    ASSERT_EQ(service.action("prepare",next,owner,104,gates,monitor).http,202);
    EXPECT_EQ(service.action("prepare",prepare,owner,105,gates,monitor).http,409);
    EXPECT_EQ(service.action("prepare",next,other,105,gates,monitor).http,403);
    auto json=status(105,owner);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"revision")),2);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"baseline");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(json.get(),"can_start")));
}

TEST_F(BoilerService, CompletedPositiveFrameRemainsVisibleWhenStopIntervenes) {
    ready();
    ASSERT_EQ(service.action("start",action,owner,102,gates,monitor).http,202);
    const auto positive=service.next(102,gates,monitor);
    ASSERT_TRUE(service.beginTransmit(positive,102,gates,monitor));
    ASSERT_EQ(service.action("stop",action,other,103,gates,monitor).http,202);
    ASSERT_TRUE(service.finishTransmit(positive,110,true,gates,monitor));
    auto json=status(110,owner);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"positive_frames")),1);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(json.get(),"reported_stop_confirmed")));
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(json.get(),"phase")),"stopping");
    EXPECT_EQ(service.next(110,gates,monitor).command,Command::zero);
}

TEST(BoilerServiceHttp, ExactPostMethodsCsrfAndPortalRulesAreRequired) {
    WebAuthSession sessions;
    const std::string token(64,'a'),csrf(64,'b');ASSERT_NE(sessions.issue(token,csrf,100),nullptr);
    for(auto path:{"/boiler/test/prepare","/boiler/test/start","/boiler/test/keepalive","/boiler/test/stop"}) {
        EXPECT_TRUE(allowedHttpMethod(path,"POST"));EXPECT_FALSE(allowedHttpMethod(path,"GET"));
        EXPECT_FALSE(allowedHttpMethod(path,"DELETE"));EXPECT_FALSE(publicAuthResource(path));
        EXPECT_NE(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,"POST"),PortalAccess::Setup);
        EXPECT_EQ(webAuthDecision(sessions,path,"POST",token,"",101,false),WebAuthDecision::csrf_required);
        EXPECT_EQ(webAuthDecision(sessions,path,"POST",token,csrf,101,false),WebAuthDecision::allow);
        EXPECT_EQ(webAuthDecision(sessions,path,"POST","",csrf,101,false),WebAuthDecision::authentication_required);
    }
    EXPECT_FALSE(allowedHttpMethod("/boiler/test/enable","POST"));
}

TEST(BoilerServiceHttp, ActiveTestInterlocksOtherWritersAndUpdatesNeverBlockStop) {
    for(auto path:{"/updates/install","/updates/check","/updates/reboot","/ota","/otafs","/config/device","/config/boiler","/setup/network"}) {
        EXPECT_TRUE(boilerTestMutationBlocked(path,true));EXPECT_FALSE(boilerTestMutationBlocked(path,false));
    }
    for(auto path:{"/auth/logout","/boiler/test/prepare","/boiler/test/start","/boiler/test/keepalive","/boiler/test/stop"})
        EXPECT_FALSE(boilerTestMutationBlocked(path,true));
    for(auto path:{"/boiler/test/prepare","/boiler/test/start","/boiler/test/keepalive"})
        for(auto bits:{1,2,4,7}) EXPECT_TRUE(heating::update::mutationBlocked(path,bits&1,bits&2,bits&4));
    EXPECT_FALSE(heating::update::mutationBlocked("/boiler/test/stop",true,true,true));
}

TEST_F(BoilerService, ZeroOnlyHttpUsesScopedExactRequestWithoutHeatConditions) {
    gates.pathReady=gates.limitsSafe=false;report(90);
    EXPECT_EQ(service.action("prepare_zero",action,owner,100,gates,monitor).http,202);
    auto s=status(100,owner);EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(s.get(),"zero_only")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(s.get(),"available")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(s.get(),"zero_test_available")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(s.get(),"requested_flow_c")));
    EXPECT_TRUE(service.action("prepare_zero",action,owner,100,gates,monitor).duplicate);
    EXPECT_EQ(service.action("prepare_zero",action,other,100,gates,monitor).http,403);
    EXPECT_EQ(service.action("prepare",prepare,owner,100,gates,monitor).http,409);
    EXPECT_EQ(service.action("start",action,owner,100,gates,monitor).http,409);
    auto intent=service.next(100,gates,monitor);ASSERT_EQ(intent.command,Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(service,intent,100,true,gates,monitor));
    report(101);service.tick(101,gates,monitor);
    s=status(101,owner);EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(s.get(),"phase")),"completed");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(s.get(),"can_start")));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(s.get(),"positive_frames")),0);
}
TEST_F(BoilerService, ZeroOnlyDoesNotAcceptHiddenHeatParametersOrBypassBoardLock) {
    report(90);EXPECT_EQ(service.action("prepare_zero",prepare,owner,100,gates,monitor).http,400);
    BoilerTestService locked{42,false,profile,true};
    EXPECT_STREQ(locked.action("prepare_zero",action,owner,100,gates,monitor).error,"transmit_blocked");
    gates.independentStopAvailable=false;
    EXPECT_STREQ(service.action("prepare_zero",action,owner,100,gates,monitor).error,"proving_conditions_missing");
}
TEST_F(BoilerService, ZeroOnlyProfileCanExposeZeroCapabilityWithoutHeatCapability) {
    profile.minimumFlowC=profile.maximumFlowC=0;profile.maximumHeatMs=0;
    BoilerTestService zero{42,true,profile,true};gates.pathReady=gates.limitsSafe=false;report(90);
    std::ostringstream out;zero.writeJSON(out,100,owner,gates,monitor);
    auto s=ControlJson(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(s.get(),"can_prepare_zero")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(s.get(),"can_prepare")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(s.get(),"limits")));
    ASSERT_EQ(zero.action("prepare_zero",action,owner,100,gates,monitor).http,202);
    EXPECT_EQ(zero.action("keepalive",action,owner,101,gates,monitor).http,202);
    EXPECT_EQ(zero.action("stop",action,other,102,gates,monitor).http,202);
}
TEST(ZeroOnlyHttp, IsProtectedPostAndIsNotASettingsWrite) {
    EXPECT_TRUE(allowedHttpMethod("/boiler/test/prepare_zero","POST"));
    EXPECT_FALSE(allowedHttpMethod("/boiler/test/prepare_zero","GET"));
    EXPECT_FALSE(allowedHttpMethod("/boiler/test/prepare_zero","DELETE"));
    EXPECT_FALSE(boilerTestMutationBlocked("/boiler/test/prepare_zero",true));
    EXPECT_TRUE(boilerTestMutationBlocked("/config/network",true));
}

TEST_F(BoilerService, StopReferenceIsNullUntilMatchingCompletedZeroAndStableAcrossRepeats) {
    report(90);ASSERT_EQ(service.action("prepare",prepare,owner,100,gates,monitor).http,202);
    auto read=[&](uint64_t now) { auto j=status(now,owner);auto v=cJSON_GetObjectItem(j.get(),"stop_reference_emitted_at_ms");return cJSON_IsNumber(v)?v->valuedouble:-1.; };
    EXPECT_EQ(read(100),-1);
    auto zero=service.next(100,gates,monitor);ASSERT_TRUE(service.beginTransmit(zero,100,gates,monitor));
    EXPECT_EQ(read(100),-1);
    ASSERT_TRUE(service.finishTransmit(zero,101,true,gates,monitor));EXPECT_EQ(read(101),101);
    zero=service.next(201,gates,monitor);ASSERT_EQ(zero.command,Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(service,zero,201,true,gates,monitor));
    EXPECT_EQ(read(201),101);
    report(202);service.tick(202,gates,monitor);EXPECT_EQ(read(202),101);
    ASSERT_EQ(service.action("start",action,owner,203,gates,monitor).http,202);
    EXPECT_EQ(read(203),-1); // baseline zero is not a stop reference for heating
}
TEST_F(BoilerService, FailedZeroCannotBecomeDiagnosticStopEvidence) {
    report(90);ASSERT_EQ(service.action("prepare",prepare,owner,100,gates,monitor).http,202);
    auto zero=service.next(100,gates,monitor);
    ASSERT_FALSE(testing_detail::instantTransmission(service,zero,100,false,gates,monitor));
    auto j=status(101,owner);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(),"stop_reference_emitted_at_ms")));
    EXPECT_STREQ(cJSON_GetObjectItem(j.get(),"clock")->valuestring,"boot_monotonic_ms");
}
TEST_F(BoilerService, ClockReversalRetiresDiagnosticStopReference) {
    ready();auto j=status(101,owner);ASSERT_TRUE(cJSON_IsNumber(cJSON_GetObjectItem(j.get(),"stop_reference_emitted_at_ms")));
    service.tick(99,gates,monitor);j=status(102,owner);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(),"stop_reference_emitted_at_ms")));
}
TEST_F(BoilerService, TimestampZeroIsPresentRatherThanNull) {
    report(0);ASSERT_EQ(service.action("prepare",prepare,owner,0,gates,monitor).http,202);
    auto zero=service.next(0,gates,monitor);ASSERT_TRUE(testing_detail::instantTransmission(service,zero,0,true,gates,monitor));
    auto j=status(0,owner);auto v=cJSON_GetObjectItem(j.get(),"stop_reference_emitted_at_ms");
    ASSERT_TRUE(cJSON_IsNumber(v));EXPECT_EQ(v->valuedouble,0);
}

} // namespace
