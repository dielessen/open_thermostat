#include "control/BleScanLifecycle.h"
#include <gtest/gtest.h>
#include <stdexcept>
using heating::control::BleScanLifecycle;

TEST(BleScanLifecycle, FailedStartReleasesButDoesNotSpinOrRequireEndCallback) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(0,0));
    EXPECT_TRUE(scan.pending());
    EXPECT_TRUE(scan.complete(0,[] {},true));
    EXPECT_FALSE(scan.pending());
    EXPECT_FALSE(scan.begin(999,0));
    EXPECT_TRUE(scan.begin(1000,0));
}
TEST(BleScanLifecycle, CleanupRetainsExclusiveOwnershipAndPublishesOriginalCooldown) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(10,60000));
    unsigned called=0;
    EXPECT_TRUE(scan.complete(20,[&] {
        ++called;
        EXPECT_TRUE(scan.pending());
        EXPECT_FALSE(scan.begin(100000,0));
        EXPECT_FALSE(scan.complete(20,[&] {++called;}));
    }));
    EXPECT_EQ(called,1u);
    EXPECT_FALSE(scan.complete(30,[&] {++called;}));
    EXPECT_FALSE(scan.begin(60019,60000));
    EXPECT_TRUE(scan.begin(60020,60000));
}
TEST(BleScanLifecycle, ZeroCompletionTimeAndMillisWrapPreserveInterval) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(UINT32_MAX-100,2000));
    ASSERT_TRUE(scan.complete(0,[] {}));
    EXPECT_FALSE(scan.begin(1999,2000));
    EXPECT_TRUE(scan.begin(2000,2000));
    ASSERT_TRUE(scan.complete(UINT32_MAX-100,[] {}));
    EXPECT_FALSE(scan.begin(1898,2000));
    EXPECT_TRUE(scan.begin(1899,2000));
}
TEST(BleScanLifecycle, ShutdownDuringCleanupCannotReopenOrRunDuplicateCleanup) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(0,0));
    EXPECT_FALSE(scan.complete(1,[&] {scan.close();}));
    EXPECT_FALSE(scan.pending());
    EXPECT_FALSE(scan.begin(2000,0));
    EXPECT_FALSE(scan.complete(2,[] {FAIL();}));
}
TEST(BleScanLifecycle, CleanupFailureAndClosedScannerStayClosed) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(0,0));
    EXPECT_FALSE(scan.complete(1,[] {throw std::runtime_error("cleanup");}));
    EXPECT_FALSE(scan.begin(2000,0));
    BleScanLifecycle closed;
    closed.close();
    EXPECT_FALSE(closed.begin(0,0));
}

TEST(BleScanLifecycle, ReportsAcceptedOnlyInsideOwnedScanNotCleanupOrShutdown) {
    BleScanLifecycle scan;
    EXPECT_FALSE(scan.acceptsReports());
    ASSERT_TRUE(scan.begin(0,0));
    EXPECT_TRUE(scan.acceptsReports());
    EXPECT_TRUE(scan.complete(1,[&] {EXPECT_FALSE(scan.acceptsReports());}));
    EXPECT_FALSE(scan.acceptsReports());
    ASSERT_TRUE(scan.begin(2,0));
    scan.close();
    EXPECT_FALSE(scan.acceptsReports());
}
TEST(BleScanLifecycle, OnlyARequestedDiscoveryFillsTheListAndItSkipsTheAutomaticCooldown) {
    BleScanLifecycle scan;
    ASSERT_TRUE(scan.begin(0,60000));
    EXPECT_TRUE(scan.acceptsReports());EXPECT_FALSE(scan.discovering()); // automatic scan
    ASSERT_TRUE(scan.complete(60000,[] {}));
    EXPECT_FALSE(scan.begin(60500,60000,true)); // no spin: 1 s minimum
    ASSERT_TRUE(scan.begin(61000,60000,true));   // user Search does not wait 60 s
    EXPECT_TRUE(scan.discovering());
    EXPECT_TRUE(scan.complete(91000,[&] {EXPECT_FALSE(scan.discovering());}));
    EXPECT_FALSE(scan.discovering());
    EXPECT_FALSE(scan.begin(150999,60000));      // automatic scans keep their cooldown
    ASSERT_TRUE(scan.begin(151000,60000));
    EXPECT_FALSE(scan.discovering());
}
