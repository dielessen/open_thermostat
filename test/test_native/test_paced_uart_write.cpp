#include "EMS/PacedUartWrite.h"
#include <gtest/gtest.h>
#include <vector>
#include <string>

namespace {
using heating::ems::PacedUartWrite;
struct IO {
    std::vector<std::string> events;
    int failByte=-1, byteResult=-1, byteCount=0;
    bool ready=true, enter=true, exit=true;
    int writeByte(uint8_t byte) {
        events.push_back("byte:"+std::to_string(byte));
        return byteCount++==failByte?byteResult:1;
    }
    bool idle() { events.push_back("idle"); return ready; }
    bool invert(bool active) { events.push_back(active?"break":"normal");return active?enter:exit; }
    void delayUs(uint32_t us) { events.push_back("delay:"+std::to_string(us)); }
};
TEST(PacedUart, PreservesLegacyBytePacingAndChecksIdleBeforeBreak) {
    IO io;const uint8_t frame[]={0x19,0x08};
    ASSERT_TRUE(PacedUartWrite::write<true>(frame,2,io));
    EXPECT_EQ(io.events,(std::vector<std::string>{"byte:25","delay:1768","byte:8","delay:1768","idle","break","delay:1144","normal"}));
}
TEST(PacedUart, DisabledBoardInstantiatesNoSDKCalls) {
    struct Forbidden {};Forbidden io;
    EXPECT_FALSE(PacedUartWrite::write<false>(nullptr,1000,io));
}
TEST(PacedUart, RejectsNullEmptyOversizedAndLengthsThatWouldWrapToValidByte) {
    std::vector<uint8_t> data(513,0x19);
    for(size_t size:{0,34,255,256,257,289,512,513}) {
        IO io;EXPECT_FALSE(PacedUartWrite::write<true>(data.data(),size,io));EXPECT_TRUE(io.events.empty());
    }
    IO io;EXPECT_FALSE(PacedUartWrite::write<true>(nullptr,1,io));EXPECT_TRUE(io.events.empty());
}
TEST(PacedUart, EveryPartialOrFailedByteStopsWithoutSendingSuffixOrBreak) {
    const uint8_t frame[]={1,2,3,4,5,6};
    for(int position=0;position<6;++position)for(int result:{-1,0,2}) {
        IO io;io.failByte=position;io.byteResult=result;
        EXPECT_FALSE(PacedUartWrite::write<true>(frame,6,io));
        EXPECT_EQ(io.byteCount,position+1);EXPECT_EQ(io.events.size(),size_t(position*2+1));
        EXPECT_EQ(io.events.back(),"byte:"+std::to_string(position+1));
    }
}
TEST(PacedUart, NonIdleTransmitterNeverStartsBreakAndDoesNotRetry) {
    const uint8_t byte=1;IO io;io.ready=false;
    EXPECT_FALSE(PacedUartWrite::write<true>(&byte,1,io));
    EXPECT_EQ(io.events,(std::vector<std::string>{"byte:1","delay:1768","idle"}));
}
TEST(PacedUart, BreakEntryFailureAttemptsNormalRestorationButNeverReportsSuccess) {
    const uint8_t byte=1;
    for(bool restore:{false,true}) {
        IO io;io.enter=false;io.exit=restore;
        EXPECT_FALSE(PacedUartWrite::write<true>(&byte,1,io));
        EXPECT_EQ(io.events,(std::vector<std::string>{"byte:1","delay:1768","idle","break","normal"}));
    }
}
TEST(PacedUart, NormalRestorationFailureIsNotSuccessfulFrame) {
    const uint8_t byte=1;IO io;io.exit=false;
    EXPECT_FALSE(PacedUartWrite::write<true>(&byte,1,io));
    EXPECT_EQ(io.events.back(),"normal");EXPECT_EQ(io.events.size(),6u);
}
TEST(PacedUart, ExactMaximumAndSingleByteKeepAllBytesWithoutAllocationInWriter) {
    for(size_t length:{1,33}) {
        std::vector<uint8_t> frame(length,0x55);IO io;
        EXPECT_TRUE(PacedUartWrite::write<true>(frame.data(),length,io));
        EXPECT_EQ(io.byteCount,int(length));EXPECT_EQ(io.events.size(),length*2+4);
    }
}
}
