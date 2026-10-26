#include "EMS/ManualBusIdentity.h"
#include <gtest/gtest.h>
namespace {
using namespace heating::ems;
const ClassicBoilerTestEncoder::Addressing syntheticAddress{true,0x19,8,0};
TEST(ManualBusIdentity, OnlyReviewedMatchingPollIdentityIsAdmitted) {
    for (uint8_t mask : {0, 0x80}) {
        auto reviewed = syntheticAddress; reviewed.sourceMask = mask;
        EXPECT_TRUE(ManualBusIdentity::matches(reviewed, 0x19, mask, false));
        EXPECT_FALSE(ManualBusIdentity::matches(reviewed, 0x19, mask, true));
        EXPECT_FALSE(ManualBusIdentity::matches(reviewed, 0x0b, mask, false));
        EXPECT_FALSE(ManualBusIdentity::matches(reviewed, 0x19, mask ^ 0x80, false));
        EXPECT_FALSE(ManualBusIdentity::matches(reviewed, 0x19, 0xff, false));
        reviewed.reviewed = false;
        EXPECT_FALSE(ManualBusIdentity::matches(reviewed, 0x19, mask, false));
    }
    EXPECT_FALSE(ManualBusIdentity::matches({}, 0x19, 0, false));
}

TEST(ManualBusIdentity, ValidSourceConflictIsIndependentOfMaskAndDestination) {
    for (uint8_t mask : {0, 0x80}) for (uint8_t destination : {0, 8, 0x88}) {
        uint8_t frame[] = {static_cast<uint8_t>(0x19 | mask), destination, 0x1a, 0, 0, 0};
        frame[5] = EmsTelegram::calculateCRC(frame, 5);
        EXPECT_TRUE(ManualBusIdentity::conflictingSource(frame, 6, 0x19));
        EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, 6, 0x0b));
        frame[5] ^= 1;
        EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, 6, 0x19));
    }
}

TEST(ManualBusIdentity, InvalidInputCannotInventConflictOrReadPastFrame) {
    const uint8_t frame[] = {0x19, 8, 0x1a, 0, 0, 0};
    for (size_t n : {size_t(0), size_t(1), size_t(4), size_t(33)})
        EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, n, 0x19));
    EXPECT_FALSE(ManualBusIdentity::conflictingSource(nullptr, 6, 0x19));
    EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, 6, 0));
    EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, 6, 0x99));
}

TEST(ManualBusIdentity, HeaderOnlyFrameStillIdentifiesConflictingSource) {
    uint8_t frame[] = {0x19, 8, 0x1a, 0, 0};
    frame[4] = EmsTelegram::calculateCRC(frame, 4);
    ASSERT_NO_THROW(EmsTelegram::fromRawData(frame, 5));
    EXPECT_TRUE(ManualBusIdentity::conflictingSource(frame, 5, 0x19));
    frame[4] ^= 1;
    EXPECT_FALSE(ManualBusIdentity::conflictingSource(frame, 5, 0x19));
}

TEST(ManualBusIdentity, ClassicServiceIdentityIsExplicitAndStillNeedsObservedMatch) {
    const auto service = ClassicBoilerTestEncoder::Addressing::classicService();
    EXPECT_TRUE(service.valid());EXPECT_EQ(service.source,0x0b);EXPECT_EQ(service.boiler,8);EXPECT_EQ(service.sourceMask,0);
    EXPECT_TRUE(ManualBusIdentity::matches(service,0x0b,0,false));
    EXPECT_FALSE(ManualBusIdentity::matches(service,0x19,0,false));
    EXPECT_FALSE(ManualBusIdentity::matches(service,0x0b,0xff,false));
    EXPECT_FALSE(ManualBusIdentity::matches(service,0x0b,0,true));
    EmsRawFrame frame;
    ASSERT_TRUE(ClassicBoilerTestEncoder::encode(service,{BoilerTestSession::Command::zero,0,42,1,1,0},frame));
    const auto parsed=EmsTelegram::fromRawData(frame.data.data(),frame.length);
    EXPECT_EQ(parsed.getSenderId(),0x0b);EXPECT_EQ(parsed.getDestinationId(),8);EXPECT_EQ(parsed.getTypeId(),0x1a);
    ASSERT_EQ(parsed.dataSize(),1u);EXPECT_EQ(parsed.byteAt(0),0);
}

}
