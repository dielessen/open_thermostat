#include "EMS/ClassicSettingBusExchange.h"
#include "EMS/ClassicBoilerSettingTransaction.h"
#include "EMS/ManualClassicTransaction.h"
#include <gtest/gtest.h>
#include <stdexcept>
using namespace heating::ems;
namespace {
using Bus=ClassicSettingBusExchange;
using Result=Bus::Result;
using Setting=Bus::Setting;
struct Exchange {
    Bus bus; uint64_t now=100; int closures=0; bool permitted=true,closeOk=true;
    EmsRawFrame frame(bool read=false,Setting setting=Setting::heatingTemperature,int value=45) {
        EmsRawFrame f;
        EXPECT_TRUE(ClassicBoilerSettingsEncoder::encode(ClassicBoilerTestEncoder::Addressing::classicService(),true,setting,value,f));
        if(read){f.data[1]=0x88;f.data[4]=1;f.data[5]=EmsTelegram::calculateCRC(f.data.data(),5);}
        return f;
    }
    void emit(bool read=false,Setting setting=Setting::heatingTemperature,int value=45){
        ASSERT_TRUE(bus.begin(frame(read,setting,value),setting,value,7,read,now));
        bus.finish(true,now);++now;
    }
    Bus::Event receive(const uint8_t* bytes,size_t size,uint64_t acquired=101){
        return bus.receive(bytes,size,acquired,[&]{return now;},[&]{return permitted;},[&]{++closures;return closeOk;});
    }
};
TEST(ClassicSettingBus, CommissioningWhitelistStillRejectsEverySettingsWriteAndRead){
    Exchange f;
    for(auto setting:{Setting::heatingActivated,Setting::heatingTemperature,Setting::burnerMinimumPeriod,Setting::pumpDelay}){
        for(bool read:{false,true}){
            auto frame=f.frame(read,setting,1);ManualClassicTransaction legacy;
            EXPECT_FALSE(legacy.begin(frame.data.data(),frame.length,100));
        }
    }
}
TEST(ClassicSettingBus, ExactIntentRequiredEvenWhenMutatedFrameHasValidChecksum){
    Exchange f;
    for(int index=0;index<5;++index){
        auto candidate=f.frame();candidate.data[index]^=1;
        candidate.data[5]=EmsTelegram::calculateCRC(candidate.data.data(),5);
        EXPECT_FALSE(f.bus.begin(candidate,Setting::heatingTemperature,45,7,false,100));
    }
    auto candidate=f.frame();candidate.data[5]^=1;
    EXPECT_FALSE(f.bus.begin(candidate,Setting::heatingTemperature,45,7,false,100));
    EXPECT_FALSE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,0,false,100));
    EXPECT_FALSE(f.bus.begin(f.frame(),Setting::heatingTemperature,46,7,false,100));
}
TEST(ClassicSettingBus, PositiveAndNegativeStatusCloseOnceAndCarryOriginalRevision){
    for(uint8_t status:{1,4}){
        Exchange f;f.emit();auto event=f.receive(&status,1);
        EXPECT_EQ(event.result,status==1?Result::writeClosed:Result::rejected);EXPECT_EQ(event.revision,7u);
        EXPECT_EQ(f.closures,1);EXPECT_FALSE(f.bus.active());
        EXPECT_EQ(f.receive(&status,1).result,Result::none);EXPECT_EQ(f.closures,1);
    }
}
TEST(ClassicSettingBus, RepliesMustBeOriginallyAcquiredStrictlyAfterEmissionAndNotInFuture){
    Exchange f;f.emit();uint8_t status=1;
    for(uint64_t acquired:{99,100,102})EXPECT_EQ(f.receive(&status,1,acquired).result,Result::none);
    EXPECT_EQ(f.closures,0);EXPECT_EQ(f.receive(&status,1,101).result,Result::writeClosed);
}
TEST(ClassicSettingBus, ReadsRequireCorrectCompleteAddressedFragmentAndChecksum){
    for(auto setting:{Setting::heatingActivated,Setting::heatingTemperature,Setting::burnerMinimumPeriod,Setting::pumpDelay}){
        Exchange f;f.emit(true,setting,1);ClassicBoilerSettingsEncoder::Definition spec;
        ASSERT_TRUE(ClassicBoilerSettingsEncoder::definition(setting,spec));
        uint8_t bytes[]={8,11,0x16,spec.offset,1,0};bytes[5]=EmsTelegram::calculateCRC(bytes,5);
        for(int field=0;field<4;++field){
            auto old=bytes[field];bytes[field]^=1;bytes[5]=EmsTelegram::calculateCRC(bytes,5);
            EXPECT_EQ(f.receive(bytes,6).result,Result::none);bytes[field]=old;
        }
        bytes[5]=EmsTelegram::calculateCRC(bytes,5);bytes[5]^=1;
        EXPECT_EQ(f.receive(bytes,6).result,Result::none);bytes[5]^=1;
        EXPECT_EQ(f.receive(bytes,5).result,Result::none);
        uint8_t status=1;EXPECT_EQ(f.receive(&status,1).result,Result::none);
        EXPECT_EQ(f.closures,0);EXPECT_EQ(f.receive(bytes,6).result,Result::readClosed);EXPECT_EQ(f.closures,1);
    }
}
TEST(ClassicSettingBus, ReadValueMismatchClosesBusButDoesNotConfirmSetting){
    Exchange f;f.emit(true);uint8_t bytes[]={8,11,0x16,1,44,0};bytes[5]=EmsTelegram::calculateCRC(bytes,5);
    EXPECT_EQ(f.receive(bytes,6).result,Result::readClosed);
    EXPECT_FALSE(ClassicBoilerSettingsEncoder::readbackMatches(ClassicBoilerTestEncoder::Addressing::classicService(),true,
                 Setting::heatingTemperature,45,EmsTelegram::fromRawData(bytes,6)));
}
TEST(ClassicSettingBus, FailedOrReservedEmissionHasNoReplyAuthority){
    Exchange f;ASSERT_TRUE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,7,false,100));
    ++f.now;uint8_t status=1;EXPECT_EQ(f.receive(&status,1).result,Result::none);
    f.bus.finish(false,f.now);EXPECT_EQ(f.receive(&status,1).result,Result::none);EXPECT_EQ(f.closures,0);
}
TEST(ClassicSettingBus, TimeoutAndLostPermissionRetireEvenWithSilentBus){
    for(int fault=0;fault<3;++fault){
        Exchange f;f.emit();
        if(fault==0)f.now=200100;
        if(fault==1)f.now=99;
        if(fault==2)f.permitted=false;
        auto event=f.bus.tick(f.now,f.permitted);EXPECT_EQ(event.result,Result::failed);EXPECT_EQ(event.revision,7u);
        EXPECT_FALSE(f.bus.active());EXPECT_EQ(f.closures,0);
    }
}
TEST(ClassicSettingBus, SlowAdmissionAndFailedOrThrowingClosureCannotReportSuccess){
    for(int fault=0;fault<5;++fault){
        Exchange f;f.emit();uint8_t status=1;
        auto event=f.bus.receive(&status,1,101,[&]{return f.now;},[&]{if(fault==0)f.now+=200000;return fault!=1;},[&]()->bool{
            ++f.closures;if(fault==2)return false;if(fault==3)throw std::runtime_error("close");
            if(fault==4)f.now+=200000;
            return true;
        });
        EXPECT_EQ(event.result,Result::failed);EXPECT_FALSE(f.bus.active());
        EXPECT_EQ(f.receive(&status,1).result,Result::none);
    }
}
TEST(ClassicSettingBus, ClosureCannotReenterAndAcquireNewExchange){
    Exchange f;f.emit();uint8_t status=1;
    auto event=f.bus.receive(&status,1,101,[&]{return f.now;},[]{return true;},[&]{
        ++f.closures;EXPECT_FALSE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,8,false,f.now));
        EXPECT_EQ(f.receive(&status,1).result,Result::none);return true;
    });
    EXPECT_EQ(event.result,Result::writeClosed);EXPECT_EQ(event.revision,7u);EXPECT_EQ(f.closures,1);
}
TEST(ClassicSettingBus, ClockGateAndClosureCallbacksCannotTakeOverOrDuplicateCompletion){
    for(int kind=0;kind<3;++kind)for(int reenterAt=0;reenterAt<6;++reenterAt){
        SCOPED_TRACE(::testing::Message()<<"kind="<<kind<<" callback="<<reenterAt);
        Exchange f;f.emit(kind==2);const uint8_t status=kind==1?4:1;
        uint8_t reply[]={8,11,0x16,1,45,0};reply[5]=EmsTelegram::calculateCRC(reply,5);
        const uint8_t* bytes=kind==2?reply:&status;const size_t length=kind==2?6:1;
        int callbacks=0,nestedClosures=0;
        const auto reenter=[&]{
            if(callbacks++!=reenterAt)return;
            const auto nested=f.bus.receive(bytes,length,f.now,[&]{return f.now;},[]{return true;},[&]{
                ++nestedClosures;return true;
            });
            EXPECT_EQ(nested.result,Result::none);EXPECT_EQ(nested.revision,0u);EXPECT_EQ(nestedClosures,0);
            EXPECT_FALSE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,8,false,f.now));
            EXPECT_TRUE(f.bus.active());
        };
        const auto event=f.bus.receive(bytes,length,f.now,[&]{reenter();return f.now;},
            [&]{reenter();return true;},[&]{++f.closures;reenter();return true;});
        EXPECT_EQ(event.result,kind==1?Result::rejected:kind==2?Result::readClosed:Result::writeClosed);
        EXPECT_EQ(event.revision,7u);EXPECT_EQ(callbacks,6);EXPECT_EQ(nestedClosures,0);EXPECT_EQ(f.closures,1);
        EXPECT_FALSE(f.bus.active());EXPECT_EQ(f.receive(bytes,length).result,Result::none);EXPECT_EQ(f.closures,1);
        EXPECT_TRUE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,8,false,f.now));
    }
}
TEST(ClassicSettingBus, EveryCallbackExceptionReleasesReceiveGuardWithoutRetry){
    for(int throwAt=0;throwAt<6;++throwAt){
        SCOPED_TRACE(throwAt);
        Exchange f;f.emit();const uint8_t status=1;int callbacks=0;
        const auto fault=[&]{if(callbacks++==throwAt)throw std::runtime_error("callback");};
        const auto event=f.bus.receive(&status,1,f.now,[&]{fault();return f.now;},[&]{fault();return true;},
            [&]{++f.closures;fault();return true;});
        EXPECT_EQ(event.result,Result::failed);EXPECT_EQ(event.revision,7u);EXPECT_FALSE(f.bus.active());
        EXPECT_EQ(f.closures,throwAt<3?0:1);
        EXPECT_EQ(f.receive(&status,1).result,Result::none);EXPECT_EQ(f.closures,throwAt<3?0:1);
        EXPECT_TRUE(f.bus.begin(f.frame(),Setting::heatingTemperature,45,8,false,f.now));
    }
}
TEST(ClassicSettingBus, WriteStatusClosureThenReadClosureThenReadbackCompletesTransaction){
    using Transaction=ClassicBoilerSettingTransaction;
    Transaction t{42,true};Exchange f;uint64_t ms=100;
    ASSERT_EQ(t.request({42,7,1,Setting::heatingTemperature,45,true,true},ms,true),Transaction::Admission::accepted);
    auto poll=[&](bool read){t.poll([&]{return ms;},[]{return true;},[&](const EmsRawFrame& frame){
        EXPECT_TRUE(f.bus.begin(frame,Setting::heatingTemperature,45,t.revision(),read,f.now));
        f.bus.finish(true,f.now);return true;
    });};
    poll(false);EXPECT_EQ(t.phase(),Transaction::Phase::waitingWriteStatus);
    ++f.now;uint8_t status=1;auto write=f.receive(&status,1,f.now);
    ASSERT_EQ(write.result,Result::writeClosed);t.writeClosed(write.revision,ms,true,true);
    ++ms;++f.now;poll(true);EXPECT_EQ(t.phase(),Transaction::Phase::waitingResponse);
    ++ms;++f.now;uint8_t bytes[]={8,11,0x16,1,45,0};bytes[5]=EmsTelegram::calculateCRC(bytes,5);
    auto read=f.receive(bytes,6,f.now);ASSERT_EQ(read.result,Result::readClosed);
    t.receive(EmsTelegram::fromRawData(bytes,6),ms,ms,true);
    EXPECT_EQ(t.phase(),Transaction::Phase::completed);EXPECT_EQ(f.closures,2);
}
}
