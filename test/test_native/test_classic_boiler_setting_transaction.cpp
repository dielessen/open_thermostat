#include "EMS/ClassicBoilerSettingTransaction.h"
#include <gtest/gtest.h>
#include <stdexcept>
using namespace heating::ems;
namespace {
using Transaction = ClassicBoilerSettingTransaction;
using Phase = Transaction::Phase;
using Admission = Transaction::Admission;
using Setting = Transaction::Setting;
Transaction::Request intent() { return {42, 7, 1, Setting::heatingTemperature, 45, true, true}; }
EmsTelegram reply(uint8_t value = 45) { return {EmsTelegram::WRITE,8,11,1,0x16,{value}}; }
struct Fixture {
    Transaction transaction{42,true};
    uint64_t now = 100;
    bool allowed = true;
    int sends = 0;
    EmsRawFrame last;
    void start() { ASSERT_EQ(transaction.request(intent(),now,allowed),Admission::accepted); }
    void poll() {
        transaction.poll([&]{return now;},[&]{return allowed;},[&](const EmsRawFrame& frame){
            ++sends; last=frame; return true;
        });
    }
    void ack() { transaction.writeClosed(transaction.revision(),now,true,allowed); }
    void wait() { start(); poll(); ++now; ack(); ++now; poll(); ASSERT_EQ(transaction.phase(),Phase::waitingResponse); }
};
TEST(ClassicSettingTransaction, WritesOnceThenReadsExactlyOneByteAndRequiresLaterResponse) {
    Fixture f; f.start(); f.poll();
    EXPECT_EQ(f.transaction.phase(),Phase::waitingWriteStatus);
    f.ack();
    EXPECT_TRUE(f.transaction.writeAttempted());
    const auto write=EmsTelegram::fromRawData(f.last.data.data(),f.last.length);
    EXPECT_EQ(write.getDestinationId(),8); EXPECT_EQ(write.getTypeId(),0x16);
    EXPECT_EQ(write.getOffset(),1); EXPECT_EQ(*write.byteAt(1),45);
    f.transaction.receive(reply(),101,101,true);
    EXPECT_EQ(f.transaction.phase(),Phase::queuedRead);
    f.now=102; f.poll();
    const auto read=EmsTelegram::fromRawData(f.last.data.data(),f.last.length);
    EXPECT_EQ(read.getOperationType(),EmsTelegram::READ);
    EXPECT_EQ(read.getDestinationId(),8); EXPECT_EQ(read.getTypeId(),0x16);
    EXPECT_EQ(read.getOffset(),1); EXPECT_EQ(read.getRequestedDataSize(),1);
    for (const auto acquired : {100u,102u,104u}) {
        f.transaction.receive(reply(),acquired,103,true);
        EXPECT_EQ(f.transaction.phase(),Phase::waitingResponse);
    }
    f.transaction.receive(reply(),103,103,true);
    EXPECT_EQ(f.transaction.phase(),Phase::completed); EXPECT_EQ(f.transaction.responseAt(),103u);
    f.now=104; f.poll(); EXPECT_EQ(f.sends,2);
}
TEST(ClassicSettingTransaction, DisabledBootOwnerConfirmationsAndInvalidIntentRejectBeforeIO) {
    Transaction disabled{42}; EXPECT_EQ(disabled.request(intent(),100,true),Admission::rejected);
    for (int change=0;change<8;++change) {
        Fixture f; auto r=intent();
        switch(change) {
            case 0:r.boot=43;break; case 1:r.owner=0;break; case 2:r.revision=0;break;
            case 3:r.exclusiveOwnerConfirmed=false;break; case 4:r.independentStopConfirmed=false;break;
            case 5:r.value=91;break; case 6:r.setting=static_cast<Setting>(255);break;
            case 7:f.allowed=false;break;
        }
        EXPECT_EQ(f.transaction.request(r,100,f.allowed),Admission::rejected);
        f.poll(); EXPECT_EQ(f.sends,0);
    }
}
TEST(ClassicSettingTransaction, DuplicatesNeverRenewDeadlinesOrReplaceOwnerAndValue) {
    Fixture f; f.start();
    EXPECT_EQ(f.transaction.request(intent(),5099,true),Admission::duplicate);
    auto other=intent(); other.value=46;
    EXPECT_EQ(f.transaction.request(other,5099,true),Admission::rejected);
    other=intent();other.owner=8;
    EXPECT_EQ(f.transaction.request(other,5099,true),Admission::rejected);
    f.now=5100; f.poll(); EXPECT_EQ(f.sends,0);
    EXPECT_EQ(f.transaction.phase(),Phase::failed); EXPECT_STREQ(f.transaction.reason(),"poll_timeout");
}
TEST(ClassicSettingTransaction, PermissionLossAndClockReversalAreTerminalInEveryActivePhase) {
    for(int phase=0;phase<4;++phase)for(bool reverse:{false,true}) {
        Fixture f;f.start(); if(phase>0)f.poll(); if(phase>1){++f.now;f.ack();} if(phase>2){++f.now;f.poll();}
        const int sent=f.sends;
        if(reverse)--f.now;else f.allowed=false;
        f.poll(); EXPECT_EQ(f.transaction.phase(),Phase::failed); EXPECT_EQ(f.sends,sent);
        f.allowed=true;f.now=1000;f.poll();EXPECT_EQ(f.sends,sent);
    }
}
TEST(ClassicSettingTransaction, EveryPhaseExpiresAtItsExactDeadline) {
    for(int phase=0;phase<4;++phase) {
        Fixture f;f.start();if(phase>0)f.poll();if(phase>1)f.ack();if(phase>2)f.poll();
        const int sent=f.sends;
        f.now+=phase==3?15000:phase==1?200:5000;f.poll();
        EXPECT_EQ(f.transaction.phase(),Phase::failed);EXPECT_EQ(f.sends,sent);
        f.transaction.receive(reply(),f.now,f.now,true);EXPECT_EQ(f.transaction.responseAt(),0u);
    }
}
TEST(ClassicSettingTransaction, ForeignEchoPartialOrMismatchingReportsNeverConfirm) {
    Fixture f; f.wait(); ++f.now;
    for (const auto& report : {
        EmsTelegram(EmsTelegram::WRITE,11,8,1,0x16,{45}),
        EmsTelegram(EmsTelegram::BROADCAST,8,0,1,0x16,{45}),
        EmsTelegram(EmsTelegram::WRITE,8,16,1,0x16,{45}),
        EmsTelegram(EmsTelegram::WRITE,8,11,1,0xE6,{45}),
        EmsTelegram(EmsTelegram::WRITE,8,11,2,0x16,{45}),reply(44)}) {
        f.transaction.receive(report,f.now,f.now,true);
        EXPECT_EQ(f.transaction.phase(),Phase::waitingResponse);
    }
    f.now+=15000;f.poll();EXPECT_EQ(f.transaction.phase(),Phase::failed);
}
TEST(ClassicSettingTransaction, UncertainSendExceptionAndLateCompletionNeverRetry) {
    for (int fault=0;fault<4;++fault) {
        Fixture f;f.start();
        f.transaction.poll([&]{return f.now;},[]{return true;},[&](const EmsRawFrame&){
            ++f.sends;
            if(fault==0)return false;
            if(fault==1)throw std::runtime_error("uncertain");
            if(fault==2)f.now+=5000;
            if(fault==3)--f.now;
            return true;
        });
        EXPECT_TRUE(f.transaction.writeAttempted());EXPECT_EQ(f.transaction.phase(),Phase::failed);
        f.now=6000;f.poll();EXPECT_EQ(f.sends,1);
    }
}
TEST(ClassicSettingTransaction, RechecksPermissionImmediatelyBeforeAndAfterExternalIO) {
    for(int failAt:{2,3}) {
        Fixture f;f.start();int checks=0;
        f.transaction.poll([&]{return f.now;},[&]{return ++checks!=failAt;},[&](const EmsRawFrame&){++f.sends;return true;});
        EXPECT_EQ(f.transaction.phase(),Phase::failed);EXPECT_EQ(f.sends,failAt==2?0:1);
    }
}
TEST(ClassicSettingTransaction, ReentrantIOCannotStartAnotherTransactionOrDuplicateSend) {
    Fixture f;f.start();
    f.transaction.poll([&]{return f.now;},[]{return true;},[&](const EmsRawFrame&){
        ++f.sends;auto r=intent();r.revision=2;
        EXPECT_EQ(f.transaction.request(r,30100,true),Admission::rejected);
        f.poll();return true;
    });
    EXPECT_EQ(f.sends,1);EXPECT_EQ(f.transaction.revision(),1u);
    EXPECT_EQ(f.transaction.phase(),Phase::waitingWriteStatus);
}
TEST(ClassicSettingTransaction, ReentrantClockAndGateCannotTakeOverOrRepeatWriteAndRead) {
    for(bool reading:{false,true})for(int reenterAt=0;reenterAt<6;++reenterAt) {
        SCOPED_TRACE(::testing::Message()<<"reading="<<reading<<" callback="<<reenterAt);
        Fixture f;f.start();if(reading){f.poll();++f.now;f.ack();}
        const int before=f.sends;int callbacks=0,nestedSends=0;
        const auto reenter=[&]{
            if(callbacks++!=reenterAt)return;
            EXPECT_TRUE(f.transaction.poll([&]{return f.now;},[]{return true;},[&](const EmsRawFrame&){
                ++nestedSends;return true;
            }));
            EXPECT_EQ(nestedSends,0);
        };
        EXPECT_TRUE(f.transaction.poll([&]{reenter();return f.now;},[&]{reenter();return true;},
            [&](const EmsRawFrame& frame){
                ++f.sends;
                EXPECT_EQ(EmsTelegram::fromRawData(frame.data.data(),frame.length).getOperationType(),
                          reading?EmsTelegram::READ:EmsTelegram::WRITE);
                return true;
            }));
        EXPECT_EQ(callbacks,6);EXPECT_EQ(nestedSends,0);EXPECT_EQ(f.sends,before+1);
        EXPECT_EQ(f.transaction.revision(),1u);
        EXPECT_EQ(f.transaction.phase(),reading?Phase::waitingResponse:Phase::waitingWriteStatus);
    }
}
TEST(ClassicSettingTransaction, ClockAndGateExceptionsReleaseThePollGuardWithoutRetry) {
    for(int throwAt=0;throwAt<6;++throwAt) {
        SCOPED_TRACE(throwAt);
        Fixture f;f.start();int callbacks=0;
        const auto fault=[&]{if(callbacks++==throwAt)throw std::runtime_error("callback");};
        EXPECT_TRUE(f.transaction.poll([&]{fault();return f.now;},[&]{fault();return true;},
            [&](const EmsRawFrame&){++f.sends;return true;}));
        EXPECT_EQ(f.transaction.phase(),Phase::failed);EXPECT_STREQ(f.transaction.reason(),"transport_exception");
        const int sent=throwAt<4?0:1;EXPECT_EQ(f.sends,sent);
        f.poll();EXPECT_EQ(f.sends,sent);
        auto next=intent();next.revision=2;f.now+=Transaction::cooldownMs;
        ASSERT_EQ(f.transaction.request(next,f.now,true),Admission::accepted);
        f.poll();EXPECT_EQ(f.sends,sent+1);
    }
}
TEST(ClassicSettingTransaction, NewAttemptNeedsNextRevisionAndCooldownAndFreshConfirmations) {
    Fixture f;f.wait();++f.now;f.transaction.receive(reply(),f.now,f.now,true);
    auto next=intent();next.revision=2;
    EXPECT_EQ(f.transaction.request(next,30099,true),Admission::rejected);
    next.independentStopConfirmed=false;
    EXPECT_EQ(f.transaction.request(next,30100,true),Admission::rejected);
    next.independentStopConfirmed=true;
    EXPECT_EQ(f.transaction.request(next,30100,true),Admission::accepted);
    EXPECT_EQ(f.transaction.phase(),Phase::queuedWrite);
    EXPECT_FALSE(f.transaction.writeAttempted());EXPECT_EQ(f.transaction.responseAt(),0u);
}
TEST(ClassicSettingTransaction, SlowAdmissionGateCannotLetAnExpiredWriteReachTransport) {
    for(int slowAt:{1,2}) {
        Fixture f;f.start();int checks=0;
        f.transaction.poll([&]{return f.now;},[&]{if(++checks==slowAt)f.now+=5000;return true;},
                           [&](const EmsRawFrame&){++f.sends;return true;});
        EXPECT_EQ(f.sends,0);EXPECT_EQ(f.transaction.phase(),Phase::failed);
        EXPECT_STREQ(f.transaction.reason(),"poll_timeout");
    }
}
TEST(ClassicSettingTransaction, PostSendGateCannotHideClockReversalOrElapsedDeadline) {
    for(bool reverse:{false,true}) {
        Fixture f;f.start();int checks=0;
        f.transaction.poll([&]{return f.now;},[&]{
            if(++checks==3){if(reverse)--f.now;else f.now+=5000;}return true;
        },[&](const EmsRawFrame&){++f.sends;return true;});
        EXPECT_EQ(f.sends,1);EXPECT_EQ(f.transaction.phase(),Phase::failed);
    }
}

TEST(ClassicSettingTransaction, EmissionDoesNotPermitReadUntilMatchingPositiveStatusAndClosure) {
    Fixture f;f.start();f.poll();
    EXPECT_EQ(f.transaction.phase(),Phase::waitingWriteStatus);
    for(int i=0;i<10;++i){f.poll();EXPECT_EQ(f.sends,1);}
    f.transaction.writeClosed(2,f.now,true,true);
    EXPECT_EQ(f.transaction.phase(),Phase::waitingWriteStatus);
    f.transaction.receive(reply(),f.now+1,f.now+1,true);
    EXPECT_EQ(f.transaction.phase(),Phase::waitingWriteStatus);
    ++f.now;f.ack();f.poll();EXPECT_EQ(f.sends,2);
}
TEST(ClassicSettingTransaction, NegativeMissingOrUnauthorizedStatusCannotStartReadback) {
    for(int fault=0;fault<4;++fault){
        Fixture f;f.start();f.poll();
        if(fault==0)f.transaction.writeClosed(1,f.now,false,true);
        if(fault==1)f.transaction.writeClosed(1,f.now,true,false);
        if(fault==2)f.transaction.writeClosed(1,f.now+200,true,true);
        if(fault==3)f.transaction.writeClosed(1,f.now-1,true,true);
        EXPECT_EQ(f.transaction.phase(),Phase::failed);
        f.poll();EXPECT_EQ(f.sends,1);
    }
}

}
