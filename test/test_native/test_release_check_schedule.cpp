#include "update/ReleaseCheckSchedule.h"
#include <gtest/gtest.h>
using namespace heating::update;
TEST(ReleaseCheckSchedule, DelaysFirstAttemptUntilStartupAndReadiness) {
    ReleaseCheckSchedule s;
    EXPECT_FALSE(s.due(0,true));EXPECT_FALSE(s.due(s.initialDelayMs-1,true));
    EXPECT_FALSE(s.due(s.initialDelayMs,false));EXPECT_TRUE(s.due(s.initialDelayMs,true));
    EXPECT_FALSE(s.known());EXPECT_FALSE(s.cached(0));
}
TEST(ReleaseCheckSchedule, FailedAttemptsDoNotRetryEveryLoopOrCreateCache) {
    ReleaseCheckSchedule s;s.attempted(300000);s.completed(400000,false);
    EXPECT_FALSE(s.known());EXPECT_FALSE(s.cached(400000));
    EXPECT_FALSE(s.due(300000+s.intervalMs-1,true));
    EXPECT_FALSE(s.due(300000+s.intervalMs,false));
    EXPECT_TRUE(s.due(300000+s.intervalMs,true));
}
TEST(ReleaseCheckSchedule, CacheExpiresAtFiveMinutesAndManualAttemptPostponesAutomaticCheck) {
    ReleaseCheckSchedule s;s.attempted(300000);s.completed(310000,true);
    EXPECT_TRUE(s.known());EXPECT_TRUE(s.cached(310000));
    EXPECT_TRUE(s.cached(310000+s.cacheMs-1));EXPECT_FALSE(s.cached(310000+s.cacheMs));
    s.attempted(900000);s.completed(910000,false);
    EXPECT_TRUE(s.known());EXPECT_EQ(s.age(920000),610000u);
    EXPECT_FALSE(s.due(900000+s.intervalMs-1,true));EXPECT_TRUE(s.due(900000+s.intervalMs,true));
}
TEST(ReleaseCheckSchedule, CacheAndRetryIntervalsSurviveMillisRollover) {
    ReleaseCheckSchedule s;const uint32_t t=UINT32_MAX-1000;
    s.attempted(t);s.completed(t,true);
    EXPECT_TRUE(s.cached(t+2000));EXPECT_EQ(s.age(t+2000),2000u);
    EXPECT_FALSE(s.cached(t+s.cacheMs));
    EXPECT_FALSE(s.due(t+s.intervalMs-1,true));EXPECT_TRUE(s.due(t+s.intervalMs,true));
}
TEST(ReleaseCheckSchedule, ActiveTestInhibitsWithoutConsumingTheNextAttempt) {
    ReleaseCheckSchedule s;
    EXPECT_FALSE(s.due(s.initialDelayMs,false));
    EXPECT_FALSE(s.due(s.initialDelayMs+60000,false));
    EXPECT_TRUE(s.due(s.initialDelayMs+60000,true));
    s.attempted(s.initialDelayMs+60000);
    EXPECT_FALSE(s.due(s.initialDelayMs+60000+s.intervalMs,false));
    EXPECT_TRUE(s.due(s.initialDelayMs+60000+s.intervalMs,true));
}
