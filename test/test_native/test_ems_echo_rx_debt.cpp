#include "EMS/EmsEchoRxDebt.h"
#include <gtest/gtest.h>
using heating::ems::EmsEchoRxDebt;
TEST(EmsEchoRxDebt, IncomingFramesWithoutEchoAreUnchanged){EmsEchoRxDebt d;EXPECT_EQ(d.dataEvent(6),6u);EXPECT_TRUE(d.atBreak());}
TEST(EmsEchoRxDebt, IndividualEchoEventsAreRetiredBeforeBreakByte){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);EXPECT_EQ(d.dataEvent(1),1u);EXPECT_TRUE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(7),7u);}
TEST(EmsEchoRxDebt, CoalescedDataPreservesBreakAndFollowingBytes){EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(4),0u);EXPECT_FALSE(d.atBreak());EXPECT_EQ(d.dataEvent(3),1u);EXPECT_TRUE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(7),7u);}
TEST(EmsEchoRxDebt, LostDataEventIsVisibleAtBreakAndResetPreservesNextFrame){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_FALSE(d.atBreak());d.reset();EXPECT_TRUE(d.atBreak());EXPECT_EQ(d.dataEvent(6),6u);}
TEST(EmsEchoRxDebt, DebtIsBoundedAndZeroSizedEventsCannotClearIt){EmsEchoRxDebt d;for(size_t i=0;i<d.capacity;++i)ASSERT_TRUE(d.consumedByte());EXPECT_FALSE(d.hasRoom());EXPECT_FALSE(d.consumedByte());EXPECT_EQ(d.dataEvent(0),0u);EXPECT_FALSE(d.atBreak());EXPECT_EQ(d.dataEvent(d.capacity),0u);EXPECT_TRUE(d.hasRoom());EXPECT_TRUE(d.atBreak());}

TEST(EmsEchoRxDebt, LostEchoEventsCannotHideInsideLaterPayload){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(4),3u);EXPECT_FALSE(d.atBreak());d.reset();EXPECT_EQ(d.dataEvent(6),6u);EXPECT_TRUE(d.atBreak());}
TEST(EmsEchoRxDebt, SplitExtraBytesRequireResyncAndCompleteEchoStillNeedsBreakBoundary){EmsEchoRxDebt d;ASSERT_TRUE(d.consumedByte());EXPECT_EQ(d.dataEvent(1),0u);EXPECT_TRUE(d.atBreak());EXPECT_FALSE(d.idle());EXPECT_EQ(d.dataEvent(1),1u);EXPECT_EQ(d.dataEvent(1),1u);EXPECT_FALSE(d.atBreak());d.reset();EXPECT_TRUE(d.idle());}
