#include "EMS/ClassicSettingUartWrite.h"
#include "EMS/ClassicBoilerSettingsEncoder.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <stdexcept>
namespace {
using namespace heating::ems;
using Boundary=ClassicSettingUartWrite;using Setting=Boundary::Setting;
struct IO {
    int readyCalls=0,attachments=0,writes=0,releases=0,throwAt=0;
    bool readyOk=true,attachOk=true,writeOk=true,releaseOk=true;
    bool ready(){++readyCalls;if(throwAt==1)throw std::runtime_error("ready");return readyOk;}
    bool attach(){++attachments;if(throwAt==2)throw std::runtime_error("attach");return attachOk;}
    bool write(const uint8_t*,size_t length){++writes;EXPECT_EQ(length,6u);if(throwAt==3)throw std::runtime_error("write");return writeOk;}
    bool detach(){++releases;if(throwAt==4)throw std::runtime_error("release");return releaseOk;}
};
EmsRawFrame frame(Setting setting,int value,bool read=false){
    EmsRawFrame f;
    EXPECT_TRUE(ClassicBoilerSettingsEncoder::encode(ClassicBoilerTestEncoder::Addressing::classicService(),true,setting,value,f));
    if(read){f.data[1]=0x88;f.data[4]=1;f.data[5]=EmsTelegram::calculateCRC(f.data.data(),5);}
    return f;
}
TEST(ClassicSettingUart, DisabledPathDoesNotInstantiateIo){
    struct Forbidden{}io;
    EXPECT_FALSE(Boundary::write<false>(nullptr,999,static_cast<Setting>(255),-1,io).touched);
}
TEST(ClassicSettingUart, EverySettingUsesOneAttachmentAndOneReleaseForWriteOrRead){
    for(auto setting:{Setting::heatingActivated,Setting::heatingTemperature,Setting::burnerMinimumPeriod,Setting::pumpDelay}){
        for(bool read:{false,true}){
            auto f=frame(setting,1,read);IO io;
            const auto r=read?Boundary::write<true,true>(f.data.data(),f.length,setting,1,io)
                             :Boundary::write<true>(f.data.data(),f.length,setting,1,io);
            EXPECT_TRUE(r.succeeded());EXPECT_TRUE(r.touched);
            EXPECT_EQ(io.readyCalls,1);EXPECT_EQ(io.attachments,1);EXPECT_EQ(io.writes,1);EXPECT_EQ(io.releases,1);
        }
    }
}
TEST(ClassicSettingUart, IndependentBoundaryChecksAllIntentValuesAndRejectsInvalidOnesBeforeIo){
    for(auto setting:{Setting::heatingActivated,Setting::heatingTemperature,Setting::burnerMinimumPeriod,Setting::pumpDelay}){
        ClassicBoilerSettingsEncoder::Definition spec;ASSERT_TRUE(ClassicBoilerSettingsEncoder::definition(setting,spec));
        for(int value=-256;value<=512;++value){
            const bool valid=value>=spec.minimum&&value<=spec.maximum;
            auto f=frame(setting,valid?value:1);IO io;
            const auto result=Boundary::write<true>(f.data.data(),6,setting,value,io);
            EXPECT_EQ(result.succeeded(),valid);EXPECT_EQ(io.attachments,valid?1:0);
        }
    }
}
TEST(ClassicSettingUart, EveryChangedWireByteEvenWithCorrectChecksumIsRefusedBeforePreflight){
    for(bool read:{false,true}){
        const auto original=frame(Setting::heatingTemperature,45,read);
        for(size_t index=0;index<5;++index)for(unsigned byte=0;byte<256;++byte){
            if(byte==original.data[index])continue;
            auto f=original;f.data[index]=byte;f.data[5]=EmsTelegram::calculateCRC(f.data.data(),5);IO io;
            const auto r=read?Boundary::write<true,true>(f.data.data(),6,Setting::heatingTemperature,45,io)
                             :Boundary::write<true>(f.data.data(),6,Setting::heatingTemperature,45,io);
            EXPECT_FALSE(r.touched);EXPECT_EQ(io.readyCalls,0);EXPECT_EQ(io.releases,0);
        }
    }
}
TEST(ClassicSettingUart, InvalidChecksumLengthOrSettingHasNoIoSideEffects){
    const auto original=frame(Setting::heatingTemperature,45);
    for(unsigned checksum=0;checksum<256;++checksum){
        if(checksum==original.data[5])continue;
        auto f=original;f.data[5]=checksum;IO io;
        EXPECT_FALSE(Boundary::write<true>(f.data.data(),6,Setting::heatingTemperature,45,io).touched);
        EXPECT_EQ(io.readyCalls,0);EXPECT_EQ(io.releases,0);
    }
    for(size_t length:{0u,1u,5u,7u,32u}){IO io;EXPECT_FALSE(Boundary::write<true>(original.data.data(),length,Setting::heatingTemperature,45,io).touched);EXPECT_EQ(io.readyCalls,0);}
    IO io;
    EXPECT_FALSE(Boundary::write<true>(nullptr,6,Setting::heatingTemperature,45,io).touched);
    EXPECT_FALSE(Boundary::write<true>(original.data.data(),6,static_cast<Setting>(255),45,io).touched);
    EXPECT_EQ(io.readyCalls,0);
}
TEST(ClassicSettingUart, FailedOrThrowingPreflightNeverTouchesOrCleansPin){
    for(bool throws:{false,true}){
        auto f=frame(Setting::heatingTemperature,45);IO io;io.readyOk=false;io.throwAt=throws?1:0;
        auto r=Boundary::write<true>(f.data.data(),6,Setting::heatingTemperature,45,io);
        EXPECT_FALSE(r.touched);EXPECT_EQ(io.attachments,0);EXPECT_EQ(io.releases,0);
    }
}
TEST(ClassicSettingUart, FailedOrThrowingAcquisitionWriteAndReleaseAlwaysReportFailure){
    for(int fault=0;fault<6;++fault){
        auto f=frame(Setting::heatingTemperature,45);IO io;
        if(fault==0)io.attachOk=false;
        if(fault==1)io.writeOk=false;
        if(fault==2)io.releaseOk=false;
        if(fault>=3)io.throwAt=fault-1;
        const auto r=Boundary::write<true>(f.data.data(),6,Setting::heatingTemperature,45,io);
        EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.touched);EXPECT_EQ(io.releases,1);
        if(fault==0||fault==3){EXPECT_EQ(io.writes,0);}
        if(fault==2||fault==5){EXPECT_FALSE(r.detached);}
    }
}
}
