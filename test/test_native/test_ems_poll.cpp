#include "EMS/EmsPoll.h"
#include <gtest/gtest.h>
using heating::ems::EmsPoll;
TEST(EmsPoll, ClassicRecognizesPollAndRejectsAcknowledgement) {
    EXPECT_TRUE(EmsPoll::addressed(0x99, 0x19, 0));
    EXPECT_FALSE(EmsPoll::addressed(0x19, 0x19, 0));
    EXPECT_TRUE(EmsPoll::addressed(0x8b, 0x0b, 0));
}
TEST(EmsPoll, JunkersUsesOppositePolarity) {
    EXPECT_TRUE(EmsPoll::addressed(0x19, 0x19, 0x80));
    EXPECT_FALSE(EmsPoll::addressed(0x99, 0x19, 0x80));
}
TEST(EmsPoll, UnknownMaskAndOtherAddressesAreRejected) {
    for (unsigned byte = 0; byte < 256; ++byte) {
        EXPECT_FALSE(EmsPoll::addressed(byte, 0x19, EmsPoll::unknown));
        EXPECT_FALSE(EmsPoll::addressed(byte, 0x19, 1));
        EXPECT_FALSE(EmsPoll::addressed(byte, 0, 0));
        EXPECT_FALSE(EmsPoll::addressed(byte, 0x99, 0));
    }
    EXPECT_FALSE(EmsPoll::addressed(0x97, 0x19, 0));
}
