#include "EMS/ClassicConfigurationRead.h"
#include "control/HttpAccessPolicy.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <sstream>
#include <stdexcept>
namespace {
using namespace heating::ems;
struct ConfigurationRead:testing::Test {
    ClassicConfigurationRead read{42,true};ClassicBoilerMonitor monitor;
    heating::control::WebAuthSession sessions;
    std::string owner=std::string(64,'a');uint64_t now=100;bool permitted=true;int writes=0;
    std::string body(unsigned revision=1){return "{\"schema\":1,\"boot_id\":\"000000000000002a\",\"revision\":"+std::to_string(revision)+",\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true}";}
    void SetUp()override{
        ASSERT_NE(sessions.issue(owner,std::string(64,'c'),now),nullptr);
        ASSERT_NE(sessions.issue(std::string(64,'b'),std::string(64,'d'),now),nullptr);
    }
    auto request(){return read.request(body(),owner,now,permitted,false,sessions);}
    bool poll(bool succeeds=true){return read.poll([&]{return now;},[&]{return permitted;},[&](const EmsRawFrame& frame){++writes;EXPECT_EQ(frame.length,6);return succeeds;});}
    void report(uint64_t at,uint8_t destination=0x0b,uint8_t offset=0,std::vector<uint8_t> bytes={255,55},EmsTelegram::operation_t operation=EmsTelegram::WRITE){
        EmsTelegram telegram{operation,8,destination,offset,0x16,std::move(bytes)};
        monitor.receive(telegram,at);read.observe(telegram,at,now,permitted,monitor);
    }
};
TEST_F(ConfigurationRead, ExactReadFrameCannotBeMistakenForSetpointOrSettingWrite){
    EmsRawFrame frame;ClassicConfigurationRead::encode(frame);
    ASSERT_EQ(frame.length,6);EXPECT_EQ(frame.data[0],0x0b);EXPECT_EQ(frame.data[1],0x88);
    EXPECT_EQ(frame.data[2],0x16);EXPECT_EQ(frame.data[3],0);EXPECT_EQ(frame.data[4],2);
    EXPECT_EQ(frame.data[5],EmsTelegram::calculateCRC(frame.data.data(),5));
    const auto telegram=EmsTelegram::fromRawData(frame.data.data(),frame.length);
    EXPECT_EQ(telegram.getOperationType(),EmsTelegram::READ);EXPECT_EQ(telegram.getDestinationId(),8);
}
TEST_F(ConfigurationRead, BootLocalAuthenticatedExplicitDeclarationsOnly){
    EXPECT_EQ(read.request(body(),"",now,true,false,sessions).http,401);
    auto changed=body();changed.replace(changed.find("002a"),4,"002b");EXPECT_EQ(read.request(changed,owner,now,true,false,sessions).http,409);
    changed=body();changed.replace(changed.find("true"),4,"false");EXPECT_EQ(read.request(changed,owner,now,true,false,sessions).http,400);
    changed=body();changed.insert(1,"\"offset\":1,");EXPECT_EQ(read.request(changed,owner,now,true,false,sessions).http,400);
    changed=body();changed.insert(1,"\"schema\":1,");EXPECT_EQ(read.request(changed,owner,now,true,false,sessions).http,400);
    EXPECT_EQ(read.request(body(2),owner,now,true,false,sessions).http,409);EXPECT_FALSE(read.active());
    EXPECT_EQ(request().http,202);EXPECT_TRUE(read.active());EXPECT_EQ(writes,0);
}
TEST_F(ConfigurationRead, DisabledOrConcurrentTrialCannotArm){
    ClassicConfigurationRead blocked{42,false};EXPECT_EQ(blocked.request(body(),owner,now,true,false,sessions).http,409);
    EXPECT_EQ(read.request(body(),owner,now,true,true,sessions).http,409);
    EXPECT_EQ(read.request(body(),owner,now,false,false,sessions).http,409);EXPECT_FALSE(read.active());
}
TEST_F(ConfigurationRead, DuplicateNeverRenewsDeadlineOrRearmsTerminalRead){
    ASSERT_EQ(request().http,202);now+=4999;EXPECT_TRUE(request().duplicate);poll();ASSERT_EQ(writes,1);
    ++now;report(now);ASSERT_EQ(read.phase(),ClassicConfigurationRead::Phase::completed);
    EXPECT_TRUE(request().duplicate);EXPECT_FALSE(poll());EXPECT_EQ(writes,1);
    EXPECT_EQ(read.request(body(),std::string(64,'b'),now,true,false,sessions).http,403);
}
TEST_F(ConfigurationRead, QueuedTimeoutCannotSendOrRetry){
    ASSERT_EQ(request().http,202);now+=5000;EXPECT_TRUE(poll());EXPECT_EQ(writes,0);
    EXPECT_STREQ(read.reason(),"poll_timeout");EXPECT_FALSE(poll());EXPECT_TRUE(request().duplicate);
}
TEST_F(ConfigurationRead, ResponseTimeoutCannotCompleteWithLateOrCachedReports){
    ASSERT_EQ(request().http,202);ASSERT_TRUE(poll());ASSERT_EQ(writes,1);
    report(now);EXPECT_TRUE(read.active()); // equality is not after emission
    now+=15000;report(now);EXPECT_STREQ(read.reason(),"response_timeout");EXPECT_FALSE(read.active());
    ++now;report(now);EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::failed);EXPECT_FALSE(poll());
}
TEST_F(ConfigurationRead, ResponseMustBeNewFullReplyAddressedToOurService){
    ASSERT_EQ(request().http,202);++now;report(now);EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::queued);
    ASSERT_TRUE(poll());++now;
    report(now,0);report(now,0x17);report(now,0x0b,1,{55});report(now,0x0b,0,{255});
    report(now,0x0b,0,{255,55},EmsTelegram::READ);
    EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::waiting);
    ++now;report(now);EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::completed);
    EXPECT_EQ(monitor.sample(BoilerField::heatingEnabled).observedMs,now);
}
TEST_F(ConfigurationRead, InvalidReportedValuesDoNotBecomeSuccessfulAcquisition){
    ASSERT_EQ(request().http,202);poll();++now;report(now,0x0b,0,{1,55});
    EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::failed);EXPECT_STREQ(read.reason(),"invalid_configuration_response");
}
TEST_F(ConfigurationRead, FinalGateLossBeforeWritePreventsEmission){
    ASSERT_EQ(request().http,202);int calls=0;
    EXPECT_TRUE(read.poll([&]{return now;},[&]{return ++calls==1;},[&](const EmsRawFrame&){++writes;return true;}));
    EXPECT_EQ(writes,0);EXPECT_FALSE(read.active());
}
TEST_F(ConfigurationRead, FailedWriteIsNeverRetriedOrCalledResponse){
    ASSERT_EQ(request().http,202);poll(false);EXPECT_STREQ(read.reason(),"transmit_failed");
    ++now;report(now);EXPECT_FALSE(poll());EXPECT_EQ(writes,1);EXPECT_FALSE(read.active());
}
TEST_F(ConfigurationRead, ExceptionsAndClockRollbackRetireAuthority){
    ASSERT_EQ(request().http,202);
    read.poll([&]{return now;},[]{return true;},[](const EmsRawFrame&)->bool{throw std::runtime_error("write");});
    EXPECT_STREQ(read.reason(),"transport_exception");EXPECT_FALSE(poll());
    ClassicConfigurationRead other{42,true};ASSERT_EQ(other.request(body(),owner,100,true,false,sessions).http,202);
    other.tick(99,true);EXPECT_STREQ(other.reason(),"clock_changed");EXPECT_FALSE(other.active());
}
TEST_F(ConfigurationRead, WaitingReadReservesPollAndLossOfTransportFails){
    ASSERT_EQ(request().http,202);poll();++now;EXPECT_TRUE(poll());EXPECT_EQ(writes,1);
    permitted=false;poll();EXPECT_STREQ(read.reason(),"transport_unavailable");EXPECT_EQ(writes,1);
}
TEST_F(ConfigurationRead, NewExplicitRevisionRequiresCooldownAndFreshDeclarations){
    ASSERT_EQ(request().http,202);poll(false);
    EXPECT_EQ(read.request(body(2),owner,now,true,false,sessions).http,409);
    now+=30000;EXPECT_EQ(read.request(body(2),owner,now,true,false,sessions).http,202);
    EXPECT_EQ(read.revision(),2u);poll();EXPECT_EQ(writes,2);
}
TEST_F(ConfigurationRead, StatusSeparatesEmissionFromReceivedConfiguration){
    ASSERT_EQ(request().http,202);poll();
    std::ostringstream out;read.writeJSON(out,now,true,false);
    auto* json=cJSON_Parse(out.str().c_str());ASSERT_NE(json,nullptr);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(json,"response_at_ms")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json,"available")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json,"physical_validation")));cJSON_Delete(json);
    ++now;report(now);out.str("");out.clear();read.writeJSON(out,now,true,false);
    json=cJSON_Parse(out.str().c_str());ASSERT_NE(json,nullptr);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(json,"response_at_ms")->valuedouble,now);cJSON_Delete(json);
}
TEST_F(ConfigurationRead, HttpRequiresPostAndUpdateInterlockIncludesRead){
    using namespace heating;
    EXPECT_TRUE(control::allowedHttpMethod("/boiler/test/read_configuration","POST"));
    EXPECT_FALSE(control::allowedHttpMethod("/boiler/test/read_configuration","GET"));
    EXPECT_TRUE(update::mutationBlocked("/boiler/test/read_configuration",true,false,false));
    EXPECT_TRUE(update::mutationBlocked("/boiler/test/read_configuration",false,true,false));
    EXPECT_TRUE(update::mutationBlocked("/boiler/test/read_configuration",false,false,true));
}
TEST_F(ConfigurationRead, HexShapedButUnissuedOrRevokedTokensCannotArm){
    EXPECT_EQ(read.request(body(),std::string(64,'e'),now,true,false,sessions).http,401);
    sessions.revoke(owner);
    EXPECT_EQ(request().http,401);EXPECT_FALSE(read.active());EXPECT_EQ(writes,0);
}
TEST_F(ConfigurationRead, LogoutWithdrawsQueuedAndWaitingReadsWithoutReplayOrLateConfirmation){
    for(bool emitted:{false,true}){
        read=ClassicConfigurationRead{42,true};writes=0;
        sessions={};ASSERT_NE(sessions.issue(owner,std::string(64,'c'),now),nullptr);
        ASSERT_EQ(request().http,202);if(emitted)poll();
        sessions.revoke(owner);read.synchronizeSessions(sessions,now);
        EXPECT_EQ(read.active(),emitted);EXPECT_STREQ(read.reason(),"operator_session_expired");
        ++now;report(now);EXPECT_FALSE(poll());EXPECT_EQ(writes,emitted?1:0);
        ASSERT_NE(sessions.issue(owner,std::string(64,'c'),now),nullptr);
        read.synchronizeSessions(sessions,now);
        EXPECT_TRUE(request().duplicate);EXPECT_FALSE(poll());EXPECT_EQ(writes,emitted?1:0);
    }
}
TEST_F(ConfigurationRead, SessionReplacementAndRecoveryCannotTransferQueuedOwnership){
    for(bool recovery:{false,true}){
        heating::control::WebAuthSession current;ClassicConfigurationRead pending{42,true};
        ASSERT_NE(current.issue(owner,std::string(64,'c'),now),nullptr);
        ASSERT_EQ(pending.request(body(),owner,now,true,false,current).http,202);
        const std::string replacement(64,'e');
        ASSERT_NE(current.issue(replacement,std::string(64,'f'),now+1,owner,recovery),nullptr);
        pending.synchronizeSessions(current,now+1);
        EXPECT_FALSE(pending.active());
        EXPECT_EQ(pending.request(body(),replacement,now+1,true,false,current).http,403);
        pending.poll([&]{return now+1;},[]{return true;},[&](const EmsRawFrame&){++writes;return true;});
        EXPECT_EQ(writes,0);
    }
}
TEST_F(ConfigurationRead, CachedIdleAndAbsoluteDeadlinesAreCheckedAtFinalPollWithoutSessionTableAccess){
    using Auth=heating::control::WebAuthSession;
    for(bool absolute:{false,true}){
        Auth current;ClassicConfigurationRead pending{42,true};
        ASSERT_NE(current.issue(owner,std::string(64,'c'),0),nullptr);
        const auto deadline=absolute?Auth::lifetimeMs:Auth::idleTimeoutMs;
        if(absolute){
            for(uint64_t t=Auth::idleTimeoutMs/2;t<deadline;t+=Auth::idleTimeoutMs/2){
                ASSERT_TRUE(current.touch(owner,t));
            }
        }
        uint64_t at=deadline-1;
        ASSERT_EQ(pending.request(body(),owner,at,true,false,current).http,202);
        unsigned gates=0;
        pending.poll([&]{return at;},[&]{if(++gates==2)++at;return true;},[&](const EmsRawFrame&){++writes;return true;});
        EXPECT_EQ(writes,0);EXPECT_FALSE(pending.active());EXPECT_STREQ(pending.reason(),"operator_session_expired");
    }
}
TEST_F(ConfigurationRead, DeadlineExpiryCannotTurnALateResponseIntoSuccessfulAcquisition){
    using Auth=heating::control::WebAuthSession;
    sessions={};ASSERT_NE(sessions.issue(owner,std::string(64,'c'),0),nullptr);
    now=Auth::idleTimeoutMs-2;ASSERT_EQ(request().http,202);ASSERT_TRUE(poll());
    now=Auth::idleTimeoutMs;report(now);
    EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::failed);
    EXPECT_STREQ(read.reason(),"operator_session_expired");EXPECT_FALSE(poll());EXPECT_EQ(writes,1);
}
TEST_F(ConfigurationRead, ProjectionNeverRenewsAuthAndClockRollbackCannotRestoreRead){
    ASSERT_EQ(request().http,202);
    const auto before=sessions.remainingMs(owner,now+50);
    read.synchronizeSessions(sessions,now+50);
    EXPECT_EQ(sessions.remainingMs(owner,now+50),before);
    read.synchronizeSessions(sessions,now+49);
    EXPECT_STREQ(read.reason(),"clock_changed");
    now+=51;read.synchronizeSessions(sessions,now);EXPECT_FALSE(poll());EXPECT_EQ(writes,0);
}
TEST_F(ConfigurationRead, WithdrawalDuringIoCannotBeReopenedBySuccessfulWriteCompletion){
    ASSERT_EQ(request().http,202);
    ASSERT_TRUE(read.poll([&]{return now;},[&]{return permitted;},[&](const EmsRawFrame&){
        ++writes;sessions.revoke(owner);read.synchronizeSessions(sessions,now);
        now+=ClassicConfigurationRead::cooldownMs;
        EXPECT_EQ(read.request(body(2),std::string(64,'b'),now,true,false,sessions).http,409);
        EXPECT_TRUE(read.poll([&]{return now;},[]{return true;},[&](const EmsRawFrame&){++writes;return true;}));
        return true;
    }));
    EXPECT_EQ(read.phase(),ClassicConfigurationRead::Phase::waiting);
    EXPECT_STREQ(read.reason(),"operator_session_expired");EXPECT_EQ(writes,1);
    ++now;report(now);EXPECT_FALSE(poll());EXPECT_EQ(writes,1);
}
TEST_F(ConfigurationRead, WithdrawnSentReadKeepsFiniteOwnershipAndCannotBecomeSuccessful){
    ASSERT_EQ(request().http,202);poll();
    sessions.revoke(owner);read.synchronizeSessions(sessions,now);
    EXPECT_TRUE(read.active());
    std::ostringstream out;read.writeJSON(out,now,true,false);
    auto* json=cJSON_Parse(out.str().c_str());ASSERT_NE(json,nullptr);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json,"withdrawn")));
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(json,"available")));cJSON_Delete(json);
    now+=ClassicConfigurationRead::responseTimeoutMs-1;read.tick(now,true);EXPECT_TRUE(read.active());
    ++now;read.tick(now,true);EXPECT_FALSE(read.active());EXPECT_EQ(writes,1);
    EXPECT_STREQ(read.reason(),"operator_session_expired");
}
}
