#include "EMS/ManualClassicUartWrite.h"
#include "EMS/EmsTelegram.h"
#define OPENTHERMOSTAT_E32V2
#include "Board.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <stdexcept>
using heating::ems::ManualClassicUartWrite;
namespace {
// Valid fixed wire vector, independently checked against the shared encoder CRC.
const uint8_t frame[]={0x19,8,0x1a,0,40,0x89};
struct IO {
    unsigned attached=0,writes=0,detached=0,preflights=0;size_t expectedLength=6;bool attachOk=true,writeOk=true,detachOk=true,readyOk=true;
    int throwing=0;
    bool ready(){++preflights;if(throwing==4)throw std::runtime_error("ready");return readyOk;}
    bool attach(){++attached;if(throwing==1)throw std::runtime_error("attach");return attachOk;}
    bool write(const uint8_t*,size_t n){++writes;EXPECT_EQ(n,expectedLength);if(throwing==2)throw std::runtime_error("write");return writeOk;}
    bool detach(){++detached;if(throwing==3)throw std::runtime_error("detach");return detachOk;}
};
TEST(ManualClassicUart, DefaultsKeepManualAndLegacyPermissionsIndependentlyDisabled){EXPECT_FALSE(heating::board::emsTransmitAllowed);EXPECT_FALSE(heating::board::emsManualTestTransmitAllowed);EXPECT_FALSE(heating::board::auxiliaryGpioAllowed);}
TEST(ManualClassicUart, DisabledDoesNotInstantiateOrCallIo){struct Forbidden{}io;const auto r=ManualClassicUartWrite::write<false>(nullptr,999,io);EXPECT_FALSE(r.succeeded());EXPECT_FALSE(r.touched);}
TEST(ManualClassicUart, EncoderFrameMapsOnlyForOneWriteAndAlwaysDetaches){IO io;const auto r=ManualClassicUartWrite::write<true>(frame,6,io);EXPECT_TRUE(r.succeeded());EXPECT_TRUE(r.touched);EXPECT_EQ(io.attached,1u);EXPECT_EQ(io.writes,1u);EXPECT_EQ(io.detached,1u);}
TEST(ManualClassicUart, RejectsOtherFramesBeforeAnyMapping){
    for(int field:{0,1,2,3,4}){uint8_t data[6]={0x19,8,0x1a,0,40,0x89};data[field]=(field==3||field==4)?1:0;IO io;const auto r=ManualClassicUartWrite::write<true>(data,6,io);EXPECT_FALSE(r.touched);EXPECT_EQ(io.attached,0u);}
    for(size_t size:{size_t(0),size_t(1),size_t(7),size_t(32)}){IO io;EXPECT_FALSE(ManualClassicUartWrite::write<true>(frame,size,io).touched);}
    IO io;EXPECT_FALSE(ManualClassicUartWrite::write<true>(nullptr,6,io).touched);
}
TEST(ManualClassicUart, PartialAttachmentFailureStillAttemptsDetachWithoutWriting){IO io;io.attachOk=false;const auto r=ManualClassicUartWrite::write<true>(frame,6,io);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);EXPECT_EQ(io.writes,0u);EXPECT_EQ(io.detached,1u);}
TEST(ManualClassicUart, WriteFailureReleasesPinButReleaseFailureNeverClaimsSuccess){IO io;io.writeOk=false;auto r=ManualClassicUartWrite::write<true>(frame,6,io);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);IO broken;broken.detachOk=false;r=ManualClassicUartWrite::write<true>(frame,6,broken);EXPECT_TRUE(r.writeCompleted);EXPECT_FALSE(r.detached);EXPECT_FALSE(r.succeeded());}
TEST(ManualClassicUart, ExceptionsCannotSkipReleaseOrCreateSuccessfulResult){for(int at:{1,2,3}){IO io;io.throwing=at;const auto r=ManualClassicUartWrite::write<true>(frame,6,io);EXPECT_FALSE(r.succeeded());EXPECT_EQ(io.detached,1u);if(at==3){EXPECT_FALSE(r.detached);}}}
TEST(ManualClassicUart, CorruptedChecksumNeverMapsPin){
    for(unsigned crc=0;crc<256;++crc){if(crc==frame[5])continue;
        uint8_t bytes[6];std::copy(frame,frame+6,bytes);bytes[5]=static_cast<uint8_t>(crc);
        IO io;const auto r=ManualClassicUartWrite::write<true>(bytes,6,io);
        EXPECT_FALSE(r.touched);EXPECT_FALSE(r.succeeded());EXPECT_EQ(io.attached,0u);EXPECT_EQ(io.writes,0u);EXPECT_EQ(io.detached,0u);
    }
}
TEST(ManualClassicUart, PayloadBitCorruptionCannotReachAttachment){
    for(unsigned index=0;index<5;++index)for(unsigned bit=0;bit<8;++bit){
        uint8_t bytes[6];std::copy(frame,frame+6,bytes);bytes[index]^=uint8_t(1u<<bit);
        IO io;EXPECT_FALSE(ManualClassicUartWrite::write<true>(bytes,6,io).touched);EXPECT_EQ(io.attached,0u);
    }
}
TEST(ManualClassicUart, AllValidAddressMaskAndFlowChecksumsMatchExistingWireEncoder){
    for(unsigned source=1;source<128;++source){if(source==8)continue;
        for(unsigned mask:{0u,128u})for(unsigned flow=0;flow<=90;++flow){if(flow>0&&flow<5)continue;
            uint8_t bytes[]={uint8_t(source|mask),8,0x1a,0,uint8_t(flow),0};
            bytes[5]=heating::ems::EmsTelegram::calculateCRC(bytes,5);
            IO io;EXPECT_TRUE(ManualClassicUartWrite::write<true>(bytes,6,io).succeeded());
        }
    }
}

TEST(ManualClassicUart, ReadOnlyPreflightRefusalOrExceptionCannotAcquireOrReleasePin){
    for(bool throwing:{false,true}){IO io;io.readyOk=false;io.throwing=throwing?4:0;
        const auto r=ManualClassicUartWrite::write<true>(frame,6,io);
        EXPECT_FALSE(r.touched);EXPECT_FALSE(r.succeeded());EXPECT_EQ(io.preflights,1u);
        EXPECT_EQ(io.attached,0u);EXPECT_EQ(io.writes,0u);EXPECT_EQ(io.detached,0u);
    }
}
TEST(ManualClassicUart, InvalidChecksumPrecedesEvenReadOnlyPreflight){
    uint8_t bytes[6];std::copy(frame,frame+6,bytes);bytes[5]^=1;IO io;
    EXPECT_FALSE(ManualClassicUartWrite::write<true>(bytes,6,io).touched);
    EXPECT_EQ(io.preflights,0u);EXPECT_EQ(io.attached,0u);EXPECT_EQ(io.detached,0u);
}

}

TEST(ManualClassicUart, FixedConfigurationReadHasSeparateAllowlistAndDisabledBuildDoesNothing){
    uint8_t data[]={0x0b,0x88,0x16,0,2,0};data[5]=heating::ems::EmsTelegram::calculateCRC(data,5);
    IO io;EXPECT_TRUE(ManualClassicUartWrite::readConfiguration<true>(data,6,io).succeeded());
    IO other;EXPECT_FALSE(ManualClassicUartWrite::write<true>(data,6,other).touched);EXPECT_EQ(other.preflights,0u);
    struct Forbidden{}forbidden;EXPECT_FALSE(ManualClassicUartWrite::readConfiguration<false>(nullptr,999,forbidden).touched);
    for(int field=0;field<5;++field){auto old=data[field];data[field]^=1;
        data[5]=heating::ems::EmsTelegram::calculateCRC(data,5);IO rejected;
        EXPECT_FALSE(ManualClassicUartWrite::readConfiguration<true>(data,6,rejected).touched);
        EXPECT_EQ(rejected.preflights,0u);data[field]=old;
    }
}
TEST(ManualClassicUart, ConfigurationReadRetainsPreflightAndCleanupFailureRules){
    uint8_t data[]={0x0b,0x88,0x16,0,2,0};data[5]=heating::ems::EmsTelegram::calculateCRC(data,5);
    IO busy;busy.readyOk=false;EXPECT_FALSE(ManualClassicUartWrite::readConfiguration<true>(data,6,busy).touched);
    EXPECT_EQ(busy.attached,0u);EXPECT_EQ(busy.detached,0u);
    IO cleanup;cleanup.detachOk=false;auto result=ManualClassicUartWrite::readConfiguration<true>(data,6,cleanup);
    EXPECT_TRUE(result.writeCompleted);EXPECT_FALSE(result.succeeded());EXPECT_FALSE(result.detached);
}

TEST(ManualClassicUart, CompletionIsOneFixedByteOnlyAndNotGeneralPong){
    const uint8_t completion=0x0b;IO io;io.expectedLength=1;
    EXPECT_TRUE(ManualClassicUartWrite::completeTransaction<true>(&completion,1,io).succeeded());
    EXPECT_EQ(io.attached,1u);EXPECT_EQ(io.detached,1u);
    IO old;EXPECT_FALSE(ManualClassicUartWrite::write<true>(&completion,1,old).touched);
    EXPECT_FALSE(ManualClassicUartWrite::readConfiguration<true>(&completion,1,old).touched);
    for(uint8_t wrong:{uint8_t(0),uint8_t(1),uint8_t(4),uint8_t(0x8b),uint8_t(0x19)})
        EXPECT_FALSE(ManualClassicUartWrite::completeTransaction<true>(&wrong,1,old).touched);
    EXPECT_FALSE(ManualClassicUartWrite::completeTransaction<true>(&completion,2,old).touched);EXPECT_EQ(old.preflights,0u);
    struct Forbidden{}none;EXPECT_FALSE(ManualClassicUartWrite::completeTransaction<false>(nullptr,99,none).touched);
}
