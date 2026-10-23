#include "EMS/ClassicBoilerTestEncoder.h"
#include "EMS/BoilerTestPollDriver.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::ems;
using Command = BoilerTestSession::Command;
const ClassicBoilerTestEncoder::Addressing syntheticAddress{true,0x19,0x08,0};
BoilerTestSession::Intent positive() { return {Command::positive,40,42,1,2,1102}; }
BoilerTestSession::Intent zero() { return {Command::zero,0,42,1,1,0}; }

TEST(ClassicTestEncoder, ExactGoldenFramesKeepMaskExplicitAndWriteOnlyFlowByte) {
    for (const auto mask : {0,0x80}) {
        auto address=syntheticAddress;address.sourceMask=mask;
        EmsRawFrame frame;
        ASSERT_TRUE(ClassicBoilerTestEncoder::encode(address,positive(),frame));
        const std::array<uint8_t,6> expected{static_cast<uint8_t>(0x19|mask),8,0x1A,0,40,
                                           static_cast<uint8_t>(mask ? 0x41 : 0x89)};
        ASSERT_EQ(frame.length,expected.size());
        EXPECT_TRUE(std::equal(expected.begin(),expected.end(),frame.data.begin()));
        auto decoded=EmsTelegram::fromRawData(frame.data.data(),frame.length);
        EXPECT_EQ(decoded.getOperationType(),EmsTelegram::WRITE);
        EXPECT_EQ(decoded.getSenderId(),0x19);EXPECT_EQ(decoded.getDestinationId(),8);
        EXPECT_EQ(decoded.getTypeId(),0x1A);EXPECT_EQ(decoded.getOffset(),0);
        EXPECT_EQ(decoded.dataSize(),1);EXPECT_EQ(decoded.byteAt(0),40);
        EXPECT_FALSE(decoded.byteAt(1)); // no power/DHW or other setpoint bytes
        ASSERT_TRUE(ClassicBoilerTestEncoder::encode(address,zero(),frame));
        EXPECT_EQ(frame.length,6);EXPECT_EQ(frame.data[4],0);
        EXPECT_EQ(frame.data[5],mask ? 0x69 : 0xA1);
    }
}

TEST(ClassicTestEncoder, UnreviewedUnknownAndInvalidAddressesCannotProduceFrame) {
    for(const auto address : {ClassicBoilerTestEncoder::Addressing{},
         {false,0x19,8,0},{true,0,8,0},{true,8,8,0},{true,0x99,8,0},
         {true,0x19,0,0},{true,0x19,9,0},{true,0x19,0x88,0},
         {true,0x19,8,1},{true,0x19,8,0xFF}}) {
        EmsRawFrame frame;frame.length=6;frame.data.fill(0xFF);
        EXPECT_FALSE(ClassicBoilerTestEncoder::encode(address,positive(),frame));
        EXPECT_EQ(frame.length,0);
        EXPECT_TRUE(std::all_of(frame.data.begin(),frame.data.end(),[](auto b){return b==0;}));
    }
}

TEST(ClassicTestEncoder, MissingTicketFieldsOrUnknownCommandAreRejected) {
    for(int field=0;field<4;++field) {
        auto intent=positive();
        if(field==0)intent.boot=0;if(field==1)intent.session=0;
        if(field==2)intent.epoch=0;if(field==3)intent.command=Command::none;
        EmsRawFrame frame;
        EXPECT_FALSE(ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame));
    }
}

TEST(ClassicTestEncoder, ProtocolBoundsAndExplicitZeroCannotBeConfused) {
    for(int value=0;value<=255;++value) {
        auto intent=positive();intent.flowC=value;EmsRawFrame frame;
        EXPECT_EQ(ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame),value>=5&&value<=90);
    }
    EmsRawFrame frame;auto intent=positive();intent.expiresAt=0;
    EXPECT_FALSE(ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame));
    intent=zero();intent.flowC=40;
    EXPECT_FALSE(ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame));
    intent=zero();intent.expiresAt=100;
    EXPECT_FALSE(ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame));
}

TEST(ClassicTestEncoder, IndependentParserRejectsEverySingleBitCorruption) {
    EmsRawFrame frame;ASSERT_TRUE(ClassicBoilerTestEncoder::encode(syntheticAddress,positive(),frame));
    for(size_t byte=0;byte<frame.length;++byte)for(int bit=0;bit<8;++bit) {
        auto damaged=frame;damaged.data[byte]^=1<<bit;
        EXPECT_THROW(EmsTelegram::fromRawData(damaged.data.data(),damaged.length),std::exception);
    }
}

TEST(ClassicTestEncoder, RealPollPolicyChecksDeadlineAfterEncodingAndSelectsZeroNext) {
    const BoilerTestSession::Profile profile{true,20,60,10000,3000,2000,5000,100};
    const BoilerTestSession::Gates gates{true,true,true,true,true};
    ClassicBoilerMonitor monitor;BoilerTestService service{42,true,profile,true};
    uint64_t now=100;int writes=0;EmsRawFrame sent;
    const std::string owner(64,'a');
    auto report=[&]{monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{40,1,0x72,80,0,0}},now);};
    auto encode=+[](const BoilerTestSession::Intent& intent,EmsRawFrame& frame){return ClassicBoilerTestEncoder::encode(syntheticAddress,intent,frame);};
    auto poll=[&]{return BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{return gates;},encode,[&](const auto& frame){++writes;sent=frame;return true;});};
    now=90;report();now=100;
    ASSERT_EQ(service.action("prepare",R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})",owner,now,gates,monitor).http,202);
    ASSERT_EQ(poll(),BoilerTestPollDriver::Result::sent);EXPECT_EQ(sent.data[4],0);
    ++now;report();service.tick(now,gates,monitor);++now;
    ASSERT_EQ(service.action("start",R"({"schema":1,"boot_id":"000000000000002a","revision":1})",owner,now,gates,monitor).http,202);
    unsigned clocks=0;
    EXPECT_EQ(BoilerTestPollDriver::poll(service,monitor,[&]{return ++clocks==1?now:uint64_t(1102);},[&]{return gates;},encode,[&](const auto&){++writes;return true;}),BoilerTestPollDriver::Result::rejected);
    EXPECT_EQ(writes,1);now=1102;
    EXPECT_EQ(poll(),BoilerTestPollDriver::Result::sent);EXPECT_EQ(writes,2);
    EXPECT_EQ(sent.data[2],0x1A);EXPECT_EQ(sent.data[4],0);
}
} // namespace
