#include "EMS/ClassicBoilerSettingsService.h"
#include "EMS/ClassicSettingUartWrite.h"
#include <gtest/gtest.h>
#include <sstream>
#include <stdexcept>
namespace {
using namespace heating::ems;
struct Pipeline {
    ClassicBoilerSettingsService service{42,true};heating::control::WebAuthSession sessions;
    std::string owner=std::string(64,'a');uint64_t now=100000;bool permitted=true,releaseOk=true;
    int writes=0,closures=0;EmsRawFrame sent;
    std::string body(){return "{\"schema\":1,\"boot_id\":\"000000000000002a\",\"revision\":1,\"entity\":\"heatingtemp\",\"value\":45,\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true}";}
    auto gate(){return [&](std::string_view token){EXPECT_EQ(token,owner);return permitted;};}
    auto clock(){return [&]{return now;};}
    void start(){ASSERT_NE(sessions.issue(owner,std::string(64,'b'),now/1000),nullptr);ASSERT_EQ(service.request(body(),owner,now/1000,true).http,202);service.synchronizeSessions(sessions,now/1000);}
    void poll(){service.poll(clock(),gate(),[&](const EmsRawFrame& frame,ClassicBoilerSettingsEncoder::Setting setting,int value,bool read){
        struct IO{Pipeline& f;bool ready(){return true;}bool attach(){return true;}
            bool write(const uint8_t*,size_t){++f.writes;return true;}bool detach(){return f.releaseOk;}}io{*this};
        sent=frame;
        return read?ClassicSettingUartWrite::write<true,true>(frame.data.data(),frame.length,setting,value,io)
                   :ClassicSettingUartWrite::write<true>(frame.data.data(),frame.length,setting,value,io);
    });}
    void receive(const uint8_t* bytes,size_t length){service.receive(bytes,length,now,clock(),gate(),[&]{
        ++closures;return ManualClassicUartWrite::Result{true,releaseOk,true};
    });}
    void ack(){++now;const uint8_t status=1;receive(&status,1);}
    void read(){now+=1000;poll();}
    void reply(uint8_t value=45){now+=1000;uint8_t bytes[]={8,11,22,1,value,0};bytes[5]=EmsTelegram::calculateCRC(bytes,5);receive(bytes,6);}
    std::string status(){std::ostringstream out;service.writeJSON(out,now/1000,true);return out.str();}
};
TEST(ClassicSettingsPipeline, FullRequestWriteStatusClosureReadAndReadbackCompletes){
    Pipeline f;f.start();f.poll();EXPECT_EQ(f.writes,1);EXPECT_TRUE(f.service.active());
    f.poll();EXPECT_EQ(f.writes,1);f.ack();f.read();EXPECT_EQ(f.writes,2);f.reply();
    EXPECT_FALSE(f.service.active());EXPECT_EQ(f.closures,2);
    EXPECT_NE(f.status().find("setting_read_back"),std::string::npos);
}
TEST(ClassicSettingsPipeline, LateReplyOrMismatchCannotConfirmSetting){
    for(bool mismatch:{false,true}){
        Pipeline f;f.start();f.poll();f.ack();f.read();
        if(!mismatch)f.now+=200000;
        f.reply(mismatch?44:45);
        EXPECT_FALSE(f.service.active());EXPECT_EQ(f.status().find("setting_read_back"),std::string::npos);
    }
}
TEST(ClassicSettingsPipeline, LostSessionPreventsEveryFurtherIo){
    for(int phase=0;phase<4;++phase){
        Pipeline f;f.start();if(phase>0)f.poll();if(phase>1)f.ack();if(phase>2)f.read();
        const auto writes=f.writes,closures=f.closures;f.permitted=false;
        f.service.tick(f.clock(),f.gate());f.poll();f.reply();
        EXPECT_FALSE(f.service.active());EXPECT_EQ(f.writes,writes);EXPECT_EQ(f.closures,closures);
    }
}
TEST(ClassicSettingsPipeline, ExplicitRevocationOnlyCancelsMatchingOperator){
    Pipeline f;f.start();f.service.revokeOwner(std::string(64,'b'));EXPECT_TRUE(f.service.active());
    f.poll();f.service.revokeOwner(f.owner);f.ack();f.poll();
    EXPECT_FALSE(f.service.active());EXPECT_EQ(f.writes,1);EXPECT_EQ(f.closures,0);
}
TEST(ClassicSettingsPipeline, FailedPinReleaseLatchesFaultAndRejectsNextRevision){
    for(bool duringClose:{false,true}){
        Pipeline f;f.start();if(duringClose)f.poll();f.releaseOk=false;
        if(duringClose)f.ack();else f.poll();
        EXPECT_TRUE(f.service.transportFault());EXPECT_FALSE(f.service.active());
        auto next=f.body();next.replace(next.find("\"revision\":1"),12,"\"revision\":2");
        EXPECT_EQ(f.service.request(next,f.owner,30100,true).http,409);f.poll();
        EXPECT_EQ(f.writes,1);
    }
}
TEST(ClassicSettingsPipeline, UncertainSendAndClockExceptionsNeverLeaveBusOwnershipOrRetry){
    for(bool badClock:{false,true}){
        Pipeline f;f.start();
        if(badClock)f.service.tick([]()->uint64_t{throw std::runtime_error("clock");},f.gate());
        else f.service.poll(f.clock(),f.gate(),[](const auto&,auto,int,bool)->ManualClassicUartWrite::Result{throw std::runtime_error("send");});
        EXPECT_FALSE(f.service.active());EXPECT_TRUE(f.service.transportFault());
        f.ack();f.poll();EXPECT_EQ(f.writes,0);EXPECT_EQ(f.closures,0);
    }
}
TEST(ClassicSettingsPipeline, ReentrantRequestDuringIoCannotReplaceOriginalIntent){
    Pipeline f;f.start();
    f.service.poll(f.clock(),f.gate(),[&](const auto&,auto,int,bool){
        EXPECT_EQ(f.service.request(f.body(),f.owner,f.now/1000,true).http,409);
        f.poll();return ManualClassicUartWrite::Result{true,true,true};
    });
    f.ack();f.read();f.reply();EXPECT_FALSE(f.service.active());
    EXPECT_NE(f.status().find("setting_read_back"),std::string::npos);
}
TEST(ClassicSettingsPipeline, OperatorRevokedInsideIoCannotResumeAfterSend){
    Pipeline f;f.start();
    f.service.poll(f.clock(),f.gate(),[&](const auto&,auto,int,bool){f.service.revokeOwner(f.owner);return ManualClassicUartWrite::Result{true,true,true};});
    f.ack();f.poll();EXPECT_FALSE(f.service.active());EXPECT_EQ(f.closures,0);
}
TEST(ClassicSettingsPipeline, DuplicateWhileWaitingForStatusNeverRepeatsWrite){
    Pipeline f;f.start();f.poll();const auto result=f.service.request(f.body(),f.owner,f.now/1000,true);
    EXPECT_EQ(result.http,200);EXPECT_TRUE(result.duplicate);f.poll();EXPECT_EQ(f.writes,1);
}
TEST(ClassicSettingsPipeline, ClosureCannotRewriteOriginalReadbackEvidence){
    for(uint8_t original:{44,45}){
        Pipeline f;f.start();f.poll();f.ack();f.read();f.now+=1000;
        uint8_t bytes[]={8,11,22,1,original,0};bytes[5]=EmsTelegram::calculateCRC(bytes,5);
        f.service.receive(bytes,6,f.now,f.clock(),f.gate(),[&]{
            bytes[4]=original==44?45:44;bytes[5]=EmsTelegram::calculateCRC(bytes,5);
            return ManualClassicUartWrite::Result{true,true,true};
        });
        EXPECT_EQ(f.status().find("setting_read_back")!=std::string::npos,original==45);
    }
}
TEST(ClassicSettingsPipeline, AmbiguousClosureIsPermanentFaultAndCannotBeRetried){
    Pipeline f;f.start();f.poll();++f.now;const uint8_t status=1;
    f.service.receive(&status,1,f.now,f.clock(),f.gate(),[]()->ManualClassicUartWrite::Result{throw std::runtime_error("close");});
    EXPECT_FALSE(f.service.active());EXPECT_TRUE(f.service.transportFault());
    f.ack();f.poll();EXPECT_EQ(f.writes,1);EXPECT_EQ(f.closures,0);
}

TEST(ClassicSettingsPipeline, UnprovenSessionCannotExecuteEvenWhenOtherGatesPermit){
    Pipeline f;ASSERT_EQ(f.service.request(f.body(),f.owner,f.now/1000,true).http,202);
    f.poll();EXPECT_EQ(f.writes,0);EXPECT_FALSE(f.service.active());
}
TEST(ClassicSettingsPipeline, ActualLogoutRevocationCancelsWithoutClosingOrResending){
    Pipeline f;f.start();f.poll();f.sessions.revoke(f.owner);
    f.service.synchronizeSessions(f.sessions,f.now/1000);f.ack();f.poll();
    EXPECT_FALSE(f.service.active());EXPECT_EQ(f.writes,1);EXPECT_EQ(f.closures,0);
}
TEST(ClassicSettingsPipeline, SessionRecoveryInvalidatesOldOwnerWithoutAdoptingNewLogin){
    Pipeline f;f.start();f.poll();
    ASSERT_NE(f.sessions.issue(std::string(64,'c'),std::string(64,'d'),f.now/1000,{},true),nullptr);
    f.service.synchronizeSessions(f.sessions,f.now/1000);f.ack();f.poll();
    EXPECT_FALSE(f.service.active());EXPECT_EQ(f.writes,1);EXPECT_EQ(f.closures,0);
}
TEST(ClassicSettingsPipeline, CachedSessionProofExpiresAtIdleAndHardDeadlineWithoutHttpPolling){
    using Sessions=heating::control::WebAuthSession;
    for(bool hard:{false,true}){
        Pipeline f;const auto expiry=100+(hard?Sessions::lifetimeMs:Sessions::idleTimeoutMs);
        const auto nowMs=expiry-1;f.now=nowMs*1000;
        ASSERT_NE(f.sessions.issue(f.owner,std::string(64,'b'),100),nullptr);
        if(hard){for(uint64_t at=100+Sessions::idleTimeoutMs/2;at<nowMs;at+=Sessions::idleTimeoutMs/2){
            ASSERT_TRUE(f.sessions.touch(f.owner,at));
        }}
        ASSERT_EQ(f.service.request(f.body(),f.owner,nowMs,true).http,202);
        f.service.synchronizeSessions(f.sessions,nowMs);f.poll();ASSERT_EQ(f.writes,1);
        f.now+=1000;f.poll();f.ack();
        EXPECT_FALSE(f.service.active());EXPECT_EQ(f.writes,1);EXPECT_EQ(f.closures,0);
        EXPECT_FALSE(f.sessions.touch(f.owner,expiry));
    }
}
TEST(ClassicSettingsPipeline, SessionSynchronizationNeverRenewsIdleDeadline){
    Pipeline f;f.start();const auto remaining=f.sessions.remainingMs(f.owner,100);
    f.service.synchronizeSessions(f.sessions,200);f.service.synchronizeSessions(f.sessions,600);
    EXPECT_EQ(f.sessions.remainingMs(f.owner,600),remaining-500);
}
TEST(ClassicSettingsPipeline, SessionProofClockRollbackRetiresAttempt){
    Pipeline f;f.start();f.poll();f.service.synchronizeSessions(f.sessions,99);f.ack();
    EXPECT_FALSE(f.service.active());EXPECT_EQ(f.closures,0);
}

TEST(ClassicSettingsPipeline, IdleStartupFaultDoesNotPermanentlyDisableWriterButActiveFaultDoes){
    Pipeline f;f.service.failTransport();EXPECT_FALSE(f.service.transportFault());
    f.start();f.service.failTransport();EXPECT_TRUE(f.service.transportFault());
    f.poll();EXPECT_EQ(f.writes,0);EXPECT_FALSE(f.service.active());
}

}
