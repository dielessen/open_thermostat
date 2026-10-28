#include "EMS/EmsEchoRxDebt.h"
#include <gtest/gtest.h>
using heating::ems::EmsEchoRxDebt;
TEST(EmsEchoRxDebt, IncomingFramesWithoutEchoAreUnchanged){EmsEchoRxDebt d;EXPECT_EQ(d.dataEvent(6),6u);EXPECT_TRUE(d.atBreak());}
TEST(EmsEchoRxDebt, IndividualEchoEventsAreRetiredBeforeBreakByte){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);EXPECT_EQ(d.dataEvent(1),1u);EXPECT_TRUE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(7),7u);}
TEST(EmsEchoRxDebt, CoalescedDataPreservesBreakAndFollowingBytes){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(4),0u);EXPECT_FALSE(d.atBreak());EXPECT_EQ(d.dataEvent(3),1u);EXPECT_TRUE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(7),7u);}
TEST(EmsEchoRxDebt, LostDataEventIsVisibleAtBreakAndResetPreservesNextFrame){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_FALSE(d.atBreak());d.reset();EXPECT_TRUE(d.atBreak());EXPECT_EQ(d.dataEvent(6),6u);}
TEST(EmsEchoRxDebt, DebtIsBoundedAndZeroSizedEventsCannotClearIt){EmsEchoRxDebt d;for(size_t i=0;i<d.capacity;++i)ASSERT_TRUE(d.consumedByte());EXPECT_FALSE(d.hasRoom());EXPECT_FALSE(d.consumedByte());EXPECT_EQ(d.dataEvent(0),0u);EXPECT_FALSE(d.atBreak());EXPECT_EQ(d.dataEvent(d.capacity),0u);EXPECT_TRUE(d.hasRoom());EXPECT_TRUE(d.atBreak());}

// Bytes after a complete echo without our BREAK event are only accepted when the
// first one is our 0x00 delimiter; a later device's frame never starts with 0x00.
TEST(EmsEchoRxDebt, LostEchoEventsCannotHideInsideLaterPayload){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(4),3u);EXPECT_TRUE(d.coalesced());EXPECT_FALSE(d.acceptDelimiter(0x08));EXPECT_FALSE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(6),6u);EXPECT_TRUE(d.atBreak());EXPECT_FALSE(d.coalesced());}
TEST(EmsEchoRxDebt, SplitExtraBytesRequireTheDelimiterAndCompleteEchoStillNeedsBreakBoundary){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(1),0u);EXPECT_TRUE(d.atBreak());EXPECT_FALSE(d.idle());EXPECT_EQ(d.dataEvent(1),1u);EXPECT_FALSE(d.coalesced());EXPECT_EQ(d.dataEvent(1),1u);EXPECT_TRUE(d.coalesced());EXPECT_TRUE(d.acceptDelimiter(0x00));EXPECT_TRUE(d.atBreak());d.reset();EXPECT_TRUE(d.idle());}
TEST(EmsEchoRxDebt, OrdinaryDelimiterBreakIsNotARecovery){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);EXPECT_EQ(d.dataEvent(1),1u);EXPECT_FALSE(d.coalesced());EXPECT_TRUE(d.acceptDelimiter(0x37));EXPECT_TRUE(d.atBreak());}
TEST(EmsEchoRxDebt, FrozenAttendedTrialTraceRecoversTheBoilerStatusReply){
    // 2026-10-27 beta12 trace: 6-byte zero write, six 1-byte echo events, then
    // one 3-byte event (00 delimiter, 01 status, 00 boiler BREAK) and a BREAK.
    EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());
    for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);
    EXPECT_EQ(d.dataEvent(3),3u);EXPECT_TRUE(d.coalesced());EXPECT_TRUE(d.atBreak());
    EXPECT_TRUE(d.acceptDelimiter(0x00));EXPECT_TRUE(d.atBreak()); // two bytes remain: the status reply frame
    d.reset();EXPECT_TRUE(d.idle());EXPECT_FALSE(d.coalesced());
}
TEST(EmsEchoRxDebt, MissingEchoDataAtBreakRemainsAFault){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());for(int i=0;i<5;++i)EXPECT_EQ(d.dataEvent(1),0u);EXPECT_FALSE(d.atBreak());EXPECT_FALSE(d.coalesced());}
