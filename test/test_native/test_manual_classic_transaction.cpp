#include "EMS/ManualClassicTransaction.h"
#include "EMS/ClassicConfigurationRead.h"
#include <gtest/gtest.h>
#include <stdexcept>
namespace {
using namespace heating::ems;
struct ManualTransaction:testing::Test {
    ManualClassicTransaction transaction;uint64_t now=100;int closures=0;bool gate=true,closeOk=true;
    EmsRawFrame request(bool read=false){
        EmsRawFrame frame;ClassicConfigurationRead::encode(frame);
        if(!read){frame.data[1]=8;frame.data[2]=0x1a;frame.data[4]=40;frame.data[5]=EmsTelegram::calculateCRC(frame.data.data(),5);}
        return frame;
    }
    void emit(bool read=false){auto frame=request(read);ASSERT_TRUE(transaction.begin(frame.data.data(),frame.length,now));transaction.finish(true,now);++now;}
    auto receive(const uint8_t* data,size_t length){return transaction.receive(data,length,[&]{return now;},[&]{return gate;},[&]{++closures;return closeOk;});}
};
TEST_F(ManualTransaction, NoIdlePongOrUnsolicitedReplyCanCloseBus){
    const uint8_t status=1;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,0);
}
TEST_F(ManualTransaction, WriteSuccessClosesExactlyOnceAndNeverResendsFrame){
    emit();const uint8_t status=1;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::closed);
    EXPECT_EQ(closures,1);++now;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,1);
}
TEST_F(ManualTransaction, WriteRejectionStillClosesButIsReportedAsRejected){
    emit();const uint8_t status=4;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::rejected);EXPECT_EQ(closures,1);
}
TEST_F(ManualTransaction, ReadRequiresMatchingCrcValidFullAddressedResponse){
    emit(true);uint8_t bytes[]={8,0x0b,0x16,0,255,55,0};bytes[6]=EmsTelegram::calculateCRC(bytes,6);
    for(int field:{0,1,2,3}){const auto old=bytes[field];bytes[field]^=1;bytes[6]=EmsTelegram::calculateCRC(bytes,6);
        EXPECT_EQ(receive(bytes,7),ManualClassicTransaction::Result::none);bytes[field]=old;}
    bytes[6]=EmsTelegram::calculateCRC(bytes,6);bytes[6]^=1;EXPECT_EQ(receive(bytes,7),ManualClassicTransaction::Result::none);
    bytes[6]^=1;EXPECT_EQ(receive(bytes,6),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,0);
    EXPECT_EQ(receive(bytes,7),ManualClassicTransaction::Result::closed);EXPECT_EQ(closures,1);
}
TEST_F(ManualTransaction, ReadRequestOrWriteStatusCannotCompleteReadTransaction){
    emit(true);auto frame=request(true);const uint8_t status=1;
    EXPECT_EQ(receive(frame.data.data(),frame.length),ManualClassicTransaction::Result::none);
    EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,0);
}
TEST_F(ManualTransaction, ReservedOrFailedEmissionNeverPermitsCompletion){
    auto frame=request();ASSERT_TRUE(transaction.begin(frame.data.data(),frame.length,now));const uint8_t status=1;
    ++now;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);
    transaction.finish(false,now);++now;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,0);
}
TEST_F(ManualTransaction, ExactEmissionTimestampIsNotLaterReply){
    emit();--now;const uint8_t status=1;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);
    ++now;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::closed);
}
TEST_F(ManualTransaction, DeadlineExpiresWithoutAnyClosureAndNeverReplays){
    emit();now=100+ManualClassicTransaction::replyWindowUs;const uint8_t status=1;
    EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::failed);EXPECT_EQ(closures,0);
    EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);
}
TEST_F(ManualTransaction, TimeOrTransportLossDuringFinalAdmissionSuppressesClosure){
    emit();const uint8_t status=1;
    auto result=transaction.receive(&status,1,[&]{return now;},[&]{now+=ManualClassicTransaction::replyWindowUs;return true;},[&]{++closures;return true;});
    EXPECT_EQ(result,ManualClassicTransaction::Result::failed);EXPECT_EQ(closures,0);
    emit();gate=false;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::failed);EXPECT_EQ(closures,0);
}
TEST_F(ManualTransaction, FailedOrThrowingClosureIsNeverRetried){
    emit();const uint8_t status=1;closeOk=false;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::failed);
    EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,1);
    emit();EXPECT_EQ(transaction.receive(&status,1,[&]{return now;},[]{return true;},[]()->bool{throw std::runtime_error("close");}),ManualClassicTransaction::Result::failed);
    EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);EXPECT_EQ(closures,1);
}
TEST_F(ManualTransaction, ClockRollbackRetiresTransactionWithoutIo){
    emit();now=99;const uint8_t status=1;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::failed);EXPECT_EQ(closures,0);
}
TEST_F(ManualTransaction, OverlappingOrInvalidFrameCannotCreateNewReplyAuthority){
    auto frame=request();ASSERT_TRUE(transaction.begin(frame.data.data(),frame.length,now));
    EXPECT_FALSE(transaction.begin(frame.data.data(),frame.length,now));transaction.finish(true,now);
    ++now;const uint8_t status=1;EXPECT_EQ(receive(&status,1),ManualClassicTransaction::Result::none);
    for(int i=0;i<5;++i){auto bad=frame;bad.data[i]^=1;bad.data[5]=EmsTelegram::calculateCRC(bad.data.data(),5);
        // Different valid flow bytes are still valid setpoints; policy/SDK
        // matching, not this reply parser, checks the admitted exact target.
        if(i==4)continue;
        EXPECT_FALSE(transaction.begin(bad.data.data(),bad.length,now));}
    EXPECT_EQ(closures,0);
}
}
