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
    EXPECT_FALSE(s.due(300000+s.failureRetryMs-1,true));
    EXPECT_FALSE(s.due(300000+s.failureRetryMs,false));
    EXPECT_TRUE(s.due(300000+s.failureRetryMs,true));
}
TEST(ReleaseCheckSchedule, CacheExpiresAtFiveMinutesAndManualAttemptPostponesAutomaticCheck) {
    ReleaseCheckSchedule s;s.attempted(300000);s.completed(310000,true);
    EXPECT_TRUE(s.known());EXPECT_TRUE(s.cached(310000));
    EXPECT_TRUE(s.cached(310000+s.cacheMs-1));EXPECT_FALSE(s.cached(310000+s.cacheMs));
    s.attempted(900000);s.completed(910000,false);
    EXPECT_TRUE(s.known());EXPECT_EQ(s.age(920000),610000u);
    EXPECT_FALSE(s.due(900000+s.failureRetryMs-1,true));EXPECT_TRUE(s.due(900000+s.failureRetryMs,true));
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
TEST(ReleaseCheckSchedule, FailedRefreshCannotReuseEarlierFreshSuccess) {
    ReleaseCheckSchedule s;s.attempted(300000);s.completed(301000,true);
    ASSERT_TRUE(s.cached(301001));
    s.attempted(302000);s.completed(303000,false);
    EXPECT_FALSE(s.cached(303001));
    EXPECT_TRUE(s.known());EXPECT_EQ(s.age(303001),2001u);
}
TEST(ReleaseCheckSchedule, NewAttemptCannotAdvertisePreviousCacheAsCurrentResult) {
    ReleaseCheckSchedule s;s.attempted(300000);s.completed(301000,true);
    s.attempted(302000);EXPECT_FALSE(s.cached(302001));
    s.completed(303000,true);EXPECT_TRUE(s.cached(303001));
}
TEST(ReleaseCheckSchedule, TransientFailureRetriesAtHalfHourWithoutBusyLoop) {
    ReleaseCheckSchedule s;constexpr uint32_t retry=30u*60*1000;
    s.attempted(300000);s.completed(301000,false);
    EXPECT_FALSE(s.due(300000+retry-1,true));
    EXPECT_TRUE(s.due(300000+retry,true));
    EXPECT_FALSE(s.due(300000+retry,false));
    s.attempted(300000+retry);s.completed(301000+retry,true);
    EXPECT_FALSE(s.due(300000+retry+s.intervalMs-1,true));
    EXPECT_TRUE(s.due(300000+retry+s.intervalMs,true));
}
TEST(ReleaseCheckSchedule, FailedRetryCooldownSurvivesRolloverAndEveryRepeatedFailure) {
    ReleaseCheckSchedule s;uint32_t at=UINT32_MAX-1000;
    for(unsigned i=0;i<32;++i) {
        s.attempted(at);s.completed(at+1,false);
        EXPECT_FALSE(s.cached(at+2));EXPECT_FALSE(s.known());
        const auto retry=s.retryMs(); // backs off, capped at the normal interval
        EXPECT_GE(retry,s.failureRetryMs);EXPECT_LE(retry,s.intervalMs);
        EXPECT_FALSE(s.due(at+retry-1,true));
        EXPECT_FALSE(s.due(at+retry,false));
        EXPECT_TRUE(s.due(at+retry,true));
        at+=retry;
    }
}

TEST(ReleaseCheckSchedule, ConsecutiveFailuresBackOffToTheNormalIntervalAndSuccessResets){
    heating::update::ReleaseCheckSchedule s;
    uint32_t now=s.initialDelayMs;
    for(uint32_t expected:{s.failureRetryMs,2*s.failureRetryMs,4*s.failureRetryMs,8*s.failureRetryMs,16*s.failureRetryMs,s.intervalMs,s.intervalMs}){
        ASSERT_TRUE(s.due(now,true));s.attempted(now);s.completed(now,false);
        EXPECT_EQ(s.retryMs(),expected);EXPECT_FALSE(s.due(now+expected-1,true));now+=expected;
    }
    ASSERT_TRUE(s.due(now,true));s.attempted(now);s.completed(now,true);EXPECT_EQ(s.retryMs(),s.failureRetryMs);
}
