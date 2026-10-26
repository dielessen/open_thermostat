#include "EMS/ClassicEchoUartWrite.h"
#include <gtest/gtest.h>
#include <vector>
#include <stdexcept>
namespace {
using heating::ems::ClassicEchoUartWrite;
struct IO {
    std::vector<uint8_t> bytes;
    unsigned polls=0,perBytePolls=0,echoAfter=1,bufferCalls=0,failBuffer=0;
    int byteResult=1,echoResult=1;
    int mismatchAt=-1;unsigned reads=0;
    int readEcho(uint8_t& byte){byte=bytes.back();if(static_cast<int>(reads++)==mismatchAt)byte^=1;return echoResult;}
    size_t initial=0,extra=0;
    bool ready=true,enter=true,exit=true,throwBreak=false;
    unsigned breaks=0,restores=0,breakDelays=0;
    int writeByte(uint8_t b){bytes.push_back(b);perBytePolls=0;return byteResult;}
    bool buffered(size_t& count){
        if(++bufferCalls==failBuffer)return false;
        if(bytes.empty()){count=initial;return true;}
        ++perBytePolls;++polls;
        count=(perBytePolls>=echoAfter?1:0)+extra;return true;
    }
    void delayUs(uint32_t us){
        if(us==ClassicEchoUartWrite::breakUs){++breakDelays;if(throwBreak)throw std::runtime_error("delay");}
        else EXPECT_EQ(us,13u);
    }
    bool idle(){return ready;}
    bool invert(bool active){if(active){++breaks;return enter;}++restores;return exit;}
};
TEST(ClassicEchoUart, DisabledDoesNotInstantiateAnyIo) {
    struct Forbidden{}io;EXPECT_FALSE(ClassicEchoUartWrite::write<false>(nullptr,999,io));
}
TEST(ClassicEchoUart, CompleteFrameWaitsForEachEchoBeforeSingleBreak) {
    IO io;io.echoAfter=3;const uint8_t frame[]={0x19,8,0x1a,0,0,0x55};
    ASSERT_TRUE(ClassicEchoUartWrite::write<true>(frame,sizeof frame,io));
    EXPECT_EQ(io.bytes,(std::vector<uint8_t>(frame,frame+sizeof frame)));
    EXPECT_EQ(io.polls,18u);EXPECT_EQ(io.breaks,1u);EXPECT_EQ(io.restores,1u);EXPECT_EQ(io.breakDelays,1u);
}
TEST(ClassicEchoUart, InvalidLengthsOrExistingRxCannotWriteAnything) {
    const uint8_t frame[33]{};
    for(size_t size:{size_t(0),size_t(33),size_t(256)}){IO io;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,size,io));EXPECT_TRUE(io.bytes.empty());}
    IO io;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(nullptr,1,io));
    io.initial=1;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,1,io));EXPECT_TRUE(io.bytes.empty());
}
TEST(ClassicEchoUart, EchoTimeoutIsBoundedAndCannotWriteSuffixOrBreak) {
    IO io;io.echoAfter=161;const uint8_t frame[]={1,2,3};
    EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,3,io));
    EXPECT_EQ(io.polls,160u);EXPECT_EQ(io.bytes.size(),1u);EXPECT_EQ(io.breaks,0u);
}
TEST(ClassicEchoUart, LastPermittedEchoAndMaximumFrameAreAccepted) {
    IO io;io.echoAfter=160;const uint8_t frame[32]{};
    EXPECT_TRUE(ClassicEchoUartWrite::write<true>(frame,32,io));EXPECT_EQ(io.bytes.size(),32u);EXPECT_EQ(io.polls,5120u);
}
TEST(ClassicEchoUart, FailedWriteOrUnexpectedRxGrowthCannotSendSuffix) {
    const uint8_t frame[]={1,2,3};
    for(int result:{-1,0,2}){IO io;io.byteResult=result;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,3,io));EXPECT_EQ(io.bytes.size(),1u);EXPECT_EQ(io.breaks,0u);}
    IO io;io.extra=1;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,3,io));EXPECT_EQ(io.bytes.size(),1u);EXPECT_EQ(io.breaks,0u);
}
TEST(ClassicEchoUart, BufferErrorsBeforeOrDuringEchoAndBusyTxAreNotSuccess) {
    const uint8_t frame[]={1,2};
    for(unsigned at:{1u,2u}){IO io;io.failBuffer=at;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,2,io));EXPECT_EQ(io.breaks,0u);}
    IO io;io.ready=false;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,2,io));EXPECT_EQ(io.breaks,0u);
}
TEST(ClassicEchoUart, FailedBreakOrDelayRestoresNormalAndNeverReportsSuccess) {
    const uint8_t byte=1;
    for(bool throwing:{false,true}){IO io;io.enter=throwing;io.throwBreak=throwing;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(&byte,1,io));EXPECT_EQ(io.restores,1u);}
    IO io;io.exit=false;EXPECT_FALSE(ClassicEchoUartWrite::write<true>(&byte,1,io));EXPECT_EQ(io.restores,1u);
}

TEST(ClassicEchoUart, MismatchingEchoAbortsBeforeAnySuffixOrBreak) {
    const uint8_t frame[]={0x19,8,0x1a,0,0,0x55};
    for(int at=0;at<6;++at){IO io;io.mismatchAt=at;
        EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,sizeof frame,io));
        EXPECT_EQ(io.bytes.size(),static_cast<size_t>(at+1));EXPECT_EQ(io.reads,static_cast<unsigned>(at+1));EXPECT_EQ(io.breaks,0u);}
}
TEST(ClassicEchoUart, FailedOrShortEchoReadIsNotAConfirmedFrame) {
    const uint8_t frame[]={1,2,3};
    for(int result:{-1,0,2}){IO io;io.echoResult=result;
        EXPECT_FALSE(ClassicEchoUartWrite::write<true>(frame,3,io));EXPECT_EQ(io.bytes.size(),1u);EXPECT_EQ(io.breaks,0u);}
}
}
