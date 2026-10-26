// Production SDK adapter; all SDK boundaries below are explicit host fakes.
#include "EmsUartWriter.h"
#include <gtest/gtest.h>
#include <vector>
namespace {
struct State {std::vector<uint8_t> bytes;bool pending=false,corrupt=false;int readResult=1;unsigned calls=0,breaks=0;uint8_t last=0;unsigned maps=0,resets=0,inputs=0,floats=0;bool mapOk=true,resetOk=true,inputOk=true,floatOk=true,bufferOk=true,txIdle=true,dataAfterMap=false;unsigned inversions=0,failInversion=0;int writeResult=1;} state;
struct EchoAdapter:testing::Test {void SetUp()override{state={};}};
}
int uart_write_bytes(int slot,const void* data,size_t length){EXPECT_EQ(slot,2);EXPECT_EQ(length,1u);++state.calls;if(state.writeResult!=1)return state.writeResult;state.last=*static_cast<const uint8_t*>(data);state.bytes.push_back(state.last);state.pending=true;return 1;}
int uart_read_bytes(int slot,void* data,size_t length,uint32_t wait){EXPECT_EQ(slot,2);EXPECT_EQ(length,1u);EXPECT_EQ(wait,0u);++state.calls;if(state.readResult!=1)return state.readResult;*static_cast<uint8_t*>(data)=state.last^(state.corrupt?1:0);state.pending=false;return 1;}
int uart_get_buffered_data_len(int slot,size_t* size){EXPECT_EQ(slot,2);++state.calls;*size=state.pending?1:0;return state.bufferOk?ESP_OK:-1;}
int uart_wait_tx_done(int slot,uint32_t wait){EXPECT_EQ(slot,2);EXPECT_EQ(wait,0u);++state.calls;return state.txIdle?ESP_OK:-1;}
int uart_set_line_inverse(int slot,int mask){EXPECT_EQ(slot,2);++state.calls;++state.inversions;if(mask)++state.breaks;return state.failInversion==state.inversions?-1:ESP_OK;}
void delayMicroseconds(uint32_t){++state.calls;}
TEST_F(EchoAdapter, DisabledRouteTouchesNoSdkEvenWithOutstandingEvents){heating::ems::EmsEchoRxDebt debt;ASSERT_TRUE(debt.consumedByte());const uint8_t frame[]={1,2};EXPECT_FALSE((heating::uart_detail::writeClassic<2,false>(frame,2,debt)));EXPECT_EQ(state.calls,0u);}
TEST_F(EchoAdapter, MatchingEchoAccountsForConsumedBytesAndPreservesNextFrame){heating::ems::EmsEchoRxDebt debt;const uint8_t frame[]={1,2};ASSERT_TRUE((heating::uart_detail::writeClassic<2,true>(frame,2,debt)));EXPECT_EQ(state.bytes,(std::vector<uint8_t>{1,2}));EXPECT_EQ(state.breaks,1u);EXPECT_EQ(debt.dataEvent(3),1u);EXPECT_TRUE(debt.atBreak());debt.reset();EXPECT_EQ(debt.dataEvent(6),6u);}
TEST_F(EchoAdapter, MismatchStopsSuffixAndRetiresOnlyActuallyConsumedByte){heating::ems::EmsEchoRxDebt debt;state.corrupt=true;const uint8_t frame[]={1,2};EXPECT_FALSE((heating::uart_detail::writeClassic<2,true>(frame,2,debt)));EXPECT_EQ(state.bytes.size(),1u);EXPECT_EQ(state.breaks,0u);EXPECT_EQ(debt.dataEvent(1),0u);EXPECT_TRUE(debt.atBreak());}
TEST_F(EchoAdapter, OutstandingEchoEventsRefuseNextWriteWithoutSdkAccess){heating::ems::EmsEchoRxDebt debt;ASSERT_TRUE(debt.consumedByte());const uint8_t frame[]={1,2};EXPECT_FALSE((heating::uart_detail::writeClassic<2,true>(frame,2,debt)));EXPECT_EQ(state.calls,0u);}
TEST_F(EchoAdapter, FailedReadDoesNotInventConsumedEventOrSendBreak){heating::ems::EmsEchoRxDebt debt;state.readResult=0;const uint8_t frame[]={1,2};EXPECT_FALSE((heating::uart_detail::writeClassic<2,true>(frame,2,debt)));EXPECT_TRUE(debt.atBreak());EXPECT_EQ(debt.dataEvent(1),1u);EXPECT_EQ(state.bytes.size(),1u);EXPECT_EQ(state.breaks,0u);}

int uart_set_pin(int slot,int tx,int rx,int rts,int cts){EXPECT_EQ(slot,2);EXPECT_EQ(tx,5);EXPECT_EQ(rx,UART_PIN_NO_CHANGE);EXPECT_EQ(rts,UART_PIN_NO_CHANGE);EXPECT_EQ(cts,UART_PIN_NO_CHANGE);++state.calls;++state.maps;if(state.dataAfterMap)state.pending=true;return state.mapOk?ESP_OK:-1;}
int gpio_reset_pin(gpio_num_t pin){EXPECT_EQ(pin,5);++state.calls;++state.resets;return state.resetOk?ESP_OK:-1;}
int gpio_set_direction(gpio_num_t pin,int direction){EXPECT_EQ(pin,5);EXPECT_EQ(direction,GPIO_MODE_INPUT);++state.calls;++state.inputs;return state.inputOk?ESP_OK:-1;}
int gpio_set_pull_mode(gpio_num_t pin,int pull){EXPECT_EQ(pin,5);EXPECT_EQ(pull,GPIO_FLOATING);++state.calls;++state.floats;return state.floatOk?ESP_OK:-1;}
TEST_F(EchoAdapter, ManualDisabledCannotMapPinOrUseSdk){heating::ems::EmsEchoRxDebt debt;const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};const auto r=heating::uart_detail::writeManualClassic<2,5,false>(frame,6,debt);EXPECT_FALSE(r.succeeded());EXPECT_EQ(state.calls,0u);}
TEST_F(EchoAdapter, ManualFrameAttachesAndDisconnectsFixedTxWithoutChangingRx){heating::ems::EmsEchoRxDebt debt;const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);EXPECT_TRUE(r.succeeded());EXPECT_EQ(state.maps,1u);EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);EXPECT_EQ(state.bytes.size(),6u);}
TEST_F(EchoAdapter, ManualMapFailureStillAttemptsAllCleanupAndWritesNothing){heating::ems::EmsEchoRxDebt debt;state.mapOk=false;const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);EXPECT_TRUE(state.bytes.empty());EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);}
TEST_F(EchoAdapter, ManualReleaseFailureIsVisibleAndDoesNotSkipRemainingCleanup){for(int failed=0;failed<3;++failed){state={};heating::ems::EmsEchoRxDebt debt;if(failed==0)state.resetOk=false;if(failed==1)state.inputOk=false;if(failed==2)state.floatOk=false;const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);EXPECT_FALSE(r.succeeded());EXPECT_FALSE(r.detached);EXPECT_TRUE(r.writeCompleted);EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);}}
TEST_F(EchoAdapter, ManualEchoMismatchDetachesAndPendingEventsCannotRemap){heating::ems::EmsEchoRxDebt debt;state.corrupt=true;const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);EXPECT_EQ(state.bytes.size(),1u);const auto calls=state.calls;r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);EXPECT_FALSE(r.touched);EXPECT_EQ(state.calls,calls);}

TEST_F(EchoAdapter, InvalidManualChecksumNeverTouchesSdkOrEchoDebt){
    heating::ems::EmsEchoRxDebt debt;
    const uint8_t frame[]={0x19,8,0x1a,0,0,0x55};
    const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);
    EXPECT_FALSE(r.touched);EXPECT_FALSE(r.succeeded());EXPECT_EQ(state.calls,0u);
    EXPECT_EQ(state.maps,0u);EXPECT_EQ(state.resets,0u);EXPECT_EQ(state.inputs,0u);EXPECT_EQ(state.floats,0u);
}

TEST_F(EchoAdapter, KnownBusyOrUnknownUartNeverMapsInvertsOrReleasesPin){
    for(int mode=0;mode<3;++mode){state={};heating::ems::EmsEchoRxDebt debt;
        if(mode==0)state.pending=true;
        if(mode==1)state.bufferOk=false;
        if(mode==2)state.txIdle=false;
        const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};
        const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);
        EXPECT_FALSE(r.touched);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);
        EXPECT_EQ(state.maps,0u);EXPECT_EQ(state.inversions,0u);EXPECT_TRUE(state.bytes.empty());
        EXPECT_EQ(state.resets,0u);EXPECT_EQ(state.inputs,0u);EXPECT_EQ(state.floats,0u);
        EXPECT_TRUE(debt.idle());
    }
}

TEST_F(EchoAdapter, DataArrivingAfterPreflightStillRefusesWriteAndReleasesAcquiredPin){
    state.dataAfterMap=true;heating::ems::EmsEchoRxDebt debt;
    const uint8_t frame[]={0x19,8,0x1a,0,0,0xa1};
    const auto r=heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt);
    EXPECT_TRUE(r.touched);EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);
    EXPECT_EQ(state.maps,1u);EXPECT_TRUE(state.bytes.empty());EXPECT_TRUE(state.pending);
    EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);EXPECT_TRUE(debt.idle());
}

TEST_F(EchoAdapter, FixedConfigurationReadUsesEchoAndPinReleaseWithoutOpeningSetpointWriter){
    heating::ems::EmsEchoRxDebt debt;uint8_t data[]={0x0b,0x88,0x16,0,2,0};uint8_t crc=0;
    for(int i=0;i<5;++i){crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^data[i]);}data[5]=crc;
    auto rejected=heating::uart_detail::writeManualClassic<2,5,true>(data,6,debt);
    EXPECT_FALSE(rejected.touched);EXPECT_EQ(state.calls,0u);
    auto result=heating::uart_detail::writeManualClassic<2,5,true,true>(data,6,debt);
    EXPECT_TRUE(result.succeeded());EXPECT_EQ(state.maps,1u);EXPECT_EQ(state.bytes.size(),6u);
    EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);
}
TEST_F(EchoAdapter, ConfigurationReadWithBusyRxCannotAcquirePin){
    heating::ems::EmsEchoRxDebt debt;uint8_t data[]={0x0b,0x88,0x16,0,2,0};uint8_t crc=0;
    for(int i=0;i<5;++i){crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^data[i]);}data[5]=crc;
    state.pending=true;const auto result=heating::uart_detail::writeManualClassic<2,5,true,true>(data,6,debt);
    EXPECT_FALSE(result.touched);EXPECT_EQ(state.maps,0u);EXPECT_EQ(state.resets,0u);EXPECT_TRUE(state.bytes.empty());
}

TEST_F(EchoAdapter, CompletionWritesOneExactEchoedByteAndReleasesPin){
    heating::ems::EmsEchoRxDebt debt;const uint8_t byte=0x0b;
    const auto r=heating::uart_detail::writeManualClassic<2,5,true,false,true>(&byte,1,debt);
    EXPECT_TRUE(r.succeeded());ASSERT_EQ(state.bytes.size(),1u);EXPECT_EQ(state.bytes[0],byte);
    EXPECT_EQ(state.maps,1u);EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);
}
TEST_F(EchoAdapter, CompletionDisabledWrongByteOrBusyRxNeverAcquiresPin){
    heating::ems::EmsEchoRxDebt debt;const uint8_t byte=0x0b,wrong=0x8b;
    EXPECT_FALSE((heating::uart_detail::writeManualClassic<2,5,false,false,true>(&byte,1,debt).touched));
    EXPECT_FALSE((heating::uart_detail::writeManualClassic<2,5,true,false,true>(&wrong,1,debt).touched));EXPECT_EQ(state.calls,0u);
    state.pending=true;EXPECT_FALSE((heating::uart_detail::writeManualClassic<2,5,true,false,true>(&byte,1,debt).touched));EXPECT_EQ(state.maps,0u);EXPECT_EQ(state.resets,0u);
}
TEST_F(EchoAdapter, CompletionEchoFailureIsNotSuccessfulBusClosure){
    heating::ems::EmsEchoRxDebt debt;const uint8_t byte=0x0b;state.corrupt=true;
    const auto r=heating::uart_detail::writeManualClassic<2,5,true,false,true>(&byte,1,debt);
    EXPECT_FALSE(r.succeeded());EXPECT_TRUE(r.detached);EXPECT_EQ(state.maps,1u);EXPECT_EQ(state.resets,1u);
}

// Exercise the actual SDK adapter for every admitted operation. These are
// software failure injections, not electrical or boiler-stop qualification.
TEST_F(EchoAdapter, EveryManualOperationReleasesPinAfterSdkFailure){
    for(int operation=0;operation<3;++operation){
        for(int failure=0;failure<5;++failure){
            SCOPED_TRACE(::testing::Message()<<"operation="<<operation<<" failure="<<failure);
            state={};heating::ems::EmsEchoRxDebt debt;
            uint8_t frame[]={0x0b,8,0x1a,0,0,0};
            if(operation==1){frame[1]=0x88;frame[2]=0x16;frame[4]=2;}
            uint8_t crc=0;for(int i=0;i<5;++i)crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^frame[i]);frame[5]=crc;
            // First inversion is attachment; second/third start/end BREAK.
            if(failure<3)state.failInversion=unsigned(failure+1);
            else state.writeResult=failure==3?0:-1;
            const auto result=operation==0
                ?heating::uart_detail::writeManualClassic<2,5,true>(frame,6,debt)
                :operation==1
                ?heating::uart_detail::writeManualClassic<2,5,true,true>(frame,6,debt)
                :heating::uart_detail::writeManualClassic<2,5,true,false,true>(frame,1,debt);
            EXPECT_TRUE(result.touched);EXPECT_FALSE(result.writeCompleted);EXPECT_FALSE(result.succeeded());EXPECT_TRUE(result.detached);
            EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);
            if(failure==0){EXPECT_EQ(state.maps,0u);EXPECT_TRUE(state.bytes.empty());}
            if(failure>=3){EXPECT_TRUE(state.bytes.empty());EXPECT_EQ(state.breaks,0u);EXPECT_TRUE(debt.idle());}
            if(failure==1){EXPECT_EQ(state.inversions,3u);} // restoration attempted after failed BREAK assertion
        }
    }
}

TEST_F(EchoAdapter, PersistentSettingBoundaryDisabledHasNoSdkCalls){
    heating::ems::EmsEchoRxDebt debt;const uint8_t bytes[]={11,8,22,1,45,0};
    const auto r=heating::uart_detail::writeClassicSetting<2,5,false>(bytes,6,
        heating::ems::ClassicBoilerSettingSpec::Setting::heatingTemperature,45,debt);
    EXPECT_FALSE(r.touched);EXPECT_EQ(state.calls,0u);
}
TEST_F(EchoAdapter, PersistentSettingExactWriteOrReadUsesEchoAndReleasesPin){
    using Setting=heating::ems::ClassicBoilerSettingSpec::Setting;
    for(bool read:{false,true}){state={};heating::ems::EmsEchoRxDebt debt;
        uint8_t bytes[]={11,uint8_t(read?0x88:8),22,1,uint8_t(read?1:45),0};uint8_t crc=0;
        for(int i=0;i<5;++i)crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^bytes[i]);
        bytes[5]=crc;
        const auto r=read?heating::uart_detail::writeClassicSetting<2,5,true,true>(bytes,6,Setting::heatingTemperature,45,debt)
                         :heating::uart_detail::writeClassicSetting<2,5,true>(bytes,6,Setting::heatingTemperature,45,debt);
        EXPECT_TRUE(r.succeeded());EXPECT_EQ(state.maps,1u);EXPECT_EQ(state.bytes.size(),6u);
        EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);
    }
}
TEST_F(EchoAdapter, PersistentSettingWrongIntentOrChecksumNeverUsesSdk){
    using Setting=heating::ems::ClassicBoilerSettingSpec::Setting;
    for(bool wrongChecksum:{false,true}){state={};heating::ems::EmsEchoRxDebt debt;
        uint8_t bytes[]={11,8,22,1,45,0};uint8_t crc=0;
        for(int i=0;i<5;++i)crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^bytes[i]);
        bytes[5]=wrongChecksum?uint8_t(crc^1):crc;
        const auto r=heating::uart_detail::writeClassicSetting<2,5,true>(bytes,6,Setting::heatingTemperature,wrongChecksum?45:46,debt);
        EXPECT_FALSE(r.touched);EXPECT_EQ(state.calls,0u);EXPECT_TRUE(debt.idle());
    }
}
TEST_F(EchoAdapter, PersistentSettingBusyUartEchoMismatchOrReleaseFailureCannotSucceed){
    using Setting=heating::ems::ClassicBoilerSettingSpec::Setting;
    for(int fault=0;fault<6;++fault){state={};heating::ems::EmsEchoRxDebt debt;
        if(fault==0)state.pending=true;
        if(fault==1)state.corrupt=true;
        if(fault==2)state.resetOk=false;
        if(fault==3)state.inputOk=false;
        if(fault==4)state.floatOk=false;
        if(fault==5)state.dataAfterMap=true;
        uint8_t bytes[]={11,8,22,1,45,0};uint8_t crc=0;
        for(int i=0;i<5;++i)crc=uint8_t((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^bytes[i]);
        bytes[5]=crc;
        const auto r=heating::uart_detail::writeClassicSetting<2,5,true>(bytes,6,Setting::heatingTemperature,45,debt);
        EXPECT_FALSE(r.succeeded());
        if(fault==0){EXPECT_FALSE(r.touched);EXPECT_EQ(state.maps,0u);EXPECT_EQ(state.resets,0u);}
        else{EXPECT_EQ(state.resets,1u);EXPECT_EQ(state.inputs,1u);EXPECT_EQ(state.floats,1u);}
        if(fault>=2&&fault<=4){EXPECT_FALSE(r.detached);}
    }
}
