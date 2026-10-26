#include "BoilerTestIoFixture.h"
#include "EMS/BoilerTestSession.h"
#include "EMS/EmsFrameQueue.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::ems;
using Phase = BoilerTestSession::Phase;
using Command = BoilerTestSession::Command;
using Reply = BoilerTestSession::Reply;

struct BoilerTest : testing::Test {
    // Synthetic reviewed envelope, not a profile for the installed boiler.
    BoilerTestSession::Profile profile{true, 20, 60, 10000, 3000, 2000, 5000, 100};
    BoilerTestSession::Gates gates{true, true, true, true, true};
    ClassicBoilerMonitor monitor;
    BoilerTestSession session{11, profile};
    void report(uint64_t now, bool cv = false, uint8_t power = 0, bool dhw = false) {
        monitor.receive({EmsTelegram::BROADCAST, 8, 0, 0, 0x18,
            {0, 1, 0x72, 80, power, static_cast<uint8_t>(cv ? 9 : dhw ? 10 : 0)}}, now);
    }
    void prepare() {
        report(90);
        ASSERT_EQ(session.prepare(11, 1, 40, 1000, 100, gates, monitor), Reply::accepted);
    }
    void baseline() {
        prepare();
        auto zero = session.next(100, gates, monitor);
        ASSERT_EQ(zero.command, Command::zero);
        ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 100, true, gates, monitor));
        report(101); session.step(101, gates, monitor);
        ASSERT_EQ(session.phase(), Phase::ready);
    }
    void heating() {
        baseline();
        ASSERT_EQ(session.start(11, 1, 102, gates, monitor), Reply::accepted);
        ASSERT_EQ(session.phase(), Phase::heating);
    }
};

TEST_F(BoilerTest, RequiresTransmittedZeroAndStrictlyLaterReportedOffBeforeHeat) {
    prepare();
    EXPECT_EQ(session.start(11, 1, 100, gates, monitor), Reply::refused);
    report(101); session.step(101, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::baseline); // receipt alone is not an executed zero
    const auto zero = session.next(101, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 101, true, gates, monitor));
    session.step(101, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::baseline); // same tick does not prove post-command feedback
    report(102, true, 10); session.step(102, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::baseline);
    report(103); session.step(103, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::ready);
    EXPECT_EQ(session.start(11, 1, 104, gates, monitor), Reply::accepted);
}

TEST_F(BoilerTest, BurnerPauseWithPositiveSelectionIsNotBaselineOrCompletedStop) {
    prepare();const auto zero=session.next(100,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,zero,100,true,gates,monitor));
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{40,1,0x72,80,0,0}},101);
    session.step(101,gates,monitor);EXPECT_EQ(session.phase(),Phase::baseline);
    EXPECT_FALSE(session.reportedStopConfirmed());EXPECT_EQ(session.start(11,1,101,gates,monitor),Reply::refused);
    report(102);session.step(102,gates,monitor);ASSERT_EQ(session.phase(),Phase::ready);
    ASSERT_EQ(session.start(11,1,103,gates,monitor),Reply::accepted);
    session.stop(104);const auto stop=session.next(104,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,stop,104,true,gates,monitor));
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{40,1,0x72,80,0,0}},105);
    session.step(105,gates,monitor);EXPECT_EQ(session.phase(),Phase::stopping);EXPECT_FALSE(session.reportedStopConfirmed());
    report(106);session.step(106,gates,monitor);EXPECT_EQ(session.phase(),Phase::completed);
}

TEST_F(BoilerTest, DuplicateStartAndPrepareNeverExtendDeadlineOrRearm) {
    heating();
    const auto deadline = session.heatDeadline();
    EXPECT_EQ(deadline, 1102u);
    EXPECT_EQ(session.prepare(11, 1, 40, 1000, 200, gates, monitor), Reply::duplicate);
    EXPECT_EQ(session.prepare(11, 1, 41, 1000, 200, gates, monitor), Reply::refused);
    EXPECT_EQ(session.start(11, 1, 200, gates, monitor), Reply::duplicate);
    EXPECT_EQ(session.heatDeadline(), deadline);
    const auto old = session.next(201, gates, monitor);
    ASSERT_EQ(old.command, Command::positive);
    EXPECT_FALSE(session.mayTransmit(old, deadline, gates, monitor));
    EXPECT_EQ(session.phase(), Phase::stopping);
    EXPECT_EQ(session.next(deadline, gates, monitor).command, Command::zero);
    EXPECT_EQ(session.start(11, 1, deadline, gates, monitor), Reply::duplicate);
    EXPECT_EQ(session.phase(), Phase::stopping);
}

TEST_F(BoilerTest, ExplicitStopInvalidatesAlreadyQueuedPositiveAndHasNoWriteDelay) {
    heating();
    const auto positive = session.next(102, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, positive, 102, true, gates, monitor));
    const auto pending = session.next(202, gates, monitor);
    ASSERT_EQ(pending.command, Command::positive);
    session.stop(202);
    EXPECT_FALSE(session.mayTransmit(pending, 202, gates, monitor));
    auto zero = session.next(202, gates, monitor);
    ASSERT_EQ(zero.command, Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 202, true, gates, monitor));
    EXPECT_FALSE(session.reportedStopConfirmed()); // baseline off is too old
    report(203); session.step(203, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::completed);
    EXPECT_TRUE(session.reportedStopConfirmed());
    EXPECT_EQ(session.next(1000, gates, monitor).command, Command::none);
}

TEST_F(BoilerTest, InvalidParametersIdentityAndUnreviewedDefaultsNeverCreateIntent) {
    report(90);
    for (auto target : {0, 19, 61, 255})
        EXPECT_EQ(session.prepare(11, 1, target, 1000, 100, gates, monitor), Reply::refused);
    for (auto duration : {0u, 999u, 10001u, UINT32_MAX})
        EXPECT_EQ(session.prepare(11, 1, 40, duration, 100, gates, monitor), Reply::refused);
    EXPECT_EQ(session.prepare(12, 1, 40, 1000, 100, gates, monitor), Reply::refused);
    EXPECT_EQ(session.prepare(11, 0, 40, 1000, 100, gates, monitor), Reply::refused);
    BoilerTestSession locked{11, {}};
    EXPECT_EQ(locked.prepare(11, 1, 40, 1000, 100, gates, monitor), Reply::refused);
    EXPECT_EQ(locked.next(100, gates, monitor).command, Command::none);
    EXPECT_EQ(session.phase(), Phase::idle);
}

TEST_F(BoilerTest, EveryIndependentGateRestrictsHeatAndCannotBeInferredFromReceipt) {
    report(90);
    for (int index = 0; index < 5; ++index) {
        auto denied = gates;
        switch (index) {
            case 0: denied.transmitterReviewed = false; break;
            case 1: denied.exclusiveOwner = false; break;
            case 2: denied.pathReady = false; break;
            case 3: denied.limitsSafe = false; break;
            case 4: denied.independentStopAvailable = false; break;
        }
        EXPECT_EQ(session.prepare(11, 1, 40, 1000, 100, denied, monitor), Reply::refused);
    }
    EXPECT_EQ(session.phase(), Phase::idle);
}

TEST_F(BoilerTest, FaultNeverClaimsStopOrAutomaticallyResumes) {
    heating();
    const auto positive = session.next(102, gates, monitor);
    EXPECT_FALSE(testing_detail::instantTransmission(session, positive, 102, false, gates, monitor));
    EXPECT_EQ(session.phase(), Phase::fault);
    EXPECT_FALSE(session.reportedStopConfirmed());
    auto zero = session.next(103, gates, monitor);
    ASSERT_EQ(zero.command, Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 103, true, gates, monitor));
    report(104); session.step(104, gates, monitor);
    EXPECT_TRUE(session.reportedStopConfirmed());
    EXPECT_EQ(session.phase(), Phase::fault); // reported stop does not clear the failed test
    EXPECT_EQ(session.prepare(11, 2, 40, 1000, 105, gates, monitor), Reply::refused);
}

TEST_F(BoilerTest, LeaseExpiryCannotBeResurrectedByLateKeepAlive) {
    baseline();
    ASSERT_TRUE(session.keepAlive(11, 1, 200));
    EXPECT_FALSE(session.keepAlive(11, 1, 5200));
    EXPECT_EQ(session.phase(), Phase::stopping);
    EXPECT_FALSE(session.keepAlive(12, 1, 5200));
    EXPECT_EQ(session.next(5200, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, TimeoutWithoutPostCommandFeedbackLatchesUncertainStop) {
    prepare();
    auto zero = session.next(100, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 100, true, gates, monitor));
    report(3099, true, 20);
    session.step(3100, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::fault);
    EXPECT_STREQ(session.reason(), "reported_stop_timeout");
    EXPECT_FALSE(session.reportedStopConfirmed());
}

TEST_F(BoilerTest, DhwStaleAndConflictingFamiliesWithdrawPositiveDemand) {
    heating();
    auto pending = session.next(102, gates, monitor);
    report(103, false, 10, true);
    EXPECT_FALSE(session.mayTransmit(pending, 103, gates, monitor));
    EXPECT_EQ(session.phase(), Phase::stopping);
    monitor.receive({EmsTelegram::BROADCAST, 8, 0, 0, 0xE4, {1}}, 104);
    report(105);
    auto zero = session.next(105, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 105, true, gates, monitor));
    report(106); session.step(106, gates, monitor);
    EXPECT_FALSE(session.reportedStopConfirmed()); // fresh Classic cannot clear latched family conflict
}

TEST_F(BoilerTest, RebootHasNoSessionAndRejectsOldIntents) {
    heating();
    auto positive = session.next(102, gates, monitor);
    BoilerTestSession rebooted{12, profile};
    EXPECT_EQ(rebooted.phase(), Phase::idle);
    EXPECT_FALSE(rebooted.mayTransmit(positive, 103, gates, monitor));
    EXPECT_EQ(rebooted.start(11, 1, 104, gates, monitor), Reply::refused);
}

TEST_F(BoilerTest, BackwardsTimeAndLostOwnershipNeverAllowQueuedHeat) {
    heating();
    auto positive = session.next(200, gates, monitor);
    EXPECT_FALSE(session.mayTransmit(positive, 199, gates, monitor));
    EXPECT_EQ(session.phase(), Phase::fault);
    gates.exclusiveOwner = false;
    EXPECT_EQ(session.next(201, gates, monitor).command, Command::none);
    EXPECT_FALSE(session.reportedStopConfirmed());
}

TEST_F(BoilerTest, Monotonic64BitClockDoesNotWrapIntoFreshLease) {
    const uint64_t base = uint64_t{1} << 32;
    report(base + 90);
    ASSERT_EQ(session.prepare(11, 1, 40, 1000, base + 100, gates, monitor), Reply::accepted);
    auto zero = session.next(base + 100, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, base + 100, true, gates, monitor));
    report(base + 101); session.step(base + 101, gates, monitor);
    ASSERT_EQ(session.start(11, 1, base + 102, gates, monitor), Reply::accepted);
    EXPECT_EQ(session.heatDeadline(), base + 1102);
    EXPECT_EQ(session.next(base + 1102, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, PreCommandQueuedTelegramDecodedLaterCannotConfirmStop) {
    prepare();
    EmsFrameQueue<1> queue;
    EmsTelegram telegram{EmsTelegram::BROADCAST, 8, 0, 0, 0x18, {0, 1, 0x72, 80, 0, 0}};
    const auto bytes = telegram.encodeToRawDataWithCRC();
    ASSERT_TRUE(queue.push(bytes.data(), bytes.size(), 99)); // UART before zero
    auto zero = session.next(100, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 100, true, gates, monitor));
    EmsRawFrame pending;
    uint64_t receivedAt;
    ASSERT_TRUE(queue.pop(pending, &receivedAt));
    monitor.receive(EmsTelegram::fromRawData(pending.data.data(), pending.length), receivedAt);
    session.step(200, gates, monitor); // decode is late; arrival age stays original
    EXPECT_EQ(session.phase(), Phase::baseline);
    EXPECT_FALSE(session.reportedStopConfirmed());
    report(201); session.step(201, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::ready);
}

TEST_F(BoilerTest, FeedbackExpiryWithdrawsBeforeHeatAndOperatorDeadlines) {
    report(90);
    ASSERT_EQ(session.prepare(11, 1, 40, 5000, 100, gates, monitor), Reply::accepted);
    auto zero = session.next(100, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 100, true, gates, monitor));
    report(101); session.step(101, gates, monitor);
    ASSERT_EQ(session.start(11, 1, 102, gates, monitor), Reply::accepted);
    const auto positive = session.next(102, gates, monitor);
    EXPECT_FALSE(session.mayTransmit(positive, 2101, gates, monitor));
    EXPECT_EQ(session.phase(), Phase::stopping);
    EXPECT_EQ(session.next(2101, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, EveryLostGateInvalidatesPendingPositiveAtFinalSendBoundary) {
    for (int index = 0; index < 5; ++index) {
        monitor=ClassicBoilerMonitor{}; // Each independent case has its own RX lifetime.
        BoilerTestSession candidate{11, profile};
        report(90);
        ASSERT_EQ(candidate.prepare(11, 1, 40, 1000, 100, gates, monitor), Reply::accepted);
        auto zero = candidate.next(100, gates, monitor);
        ASSERT_TRUE(testing_detail::instantTransmission(candidate, zero, 100, true, gates, monitor));
        report(101); candidate.step(101, gates, monitor);
        ASSERT_EQ(candidate.start(11, 1, 102, gates, monitor), Reply::accepted);
        auto positive = candidate.next(102, gates, monitor);
        auto lost = gates;
        switch (index) {
            case 0: lost.transmitterReviewed = false; break;
            case 1: lost.exclusiveOwner = false; break;
            case 2: lost.pathReady = false; break;
            case 3: lost.limitsSafe = false; break;
            case 4: lost.independentStopAvailable = false; break;
        }
        EXPECT_FALSE(candidate.mayTransmit(positive, 103, lost, monitor));
        EXPECT_NE(candidate.next(103, lost, monitor).command, Command::positive);
        EXPECT_FALSE(candidate.reportedStopConfirmed());
    }
}

TEST_F(BoilerTest, WriteBudgetNeverDelaysAnExplicitStop) {
    heating();
    auto positive = session.next(102, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, positive, 102, true, gates, monitor));
    EXPECT_EQ(session.next(103, gates, monitor).command, Command::none);
    session.stop(103);
    EXPECT_EQ(session.next(103, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, DeadlineAdditionOverflowCannotArmSession) {
    const uint64_t end = std::numeric_limits<uint64_t>::max();
    report(end - 150);
    EXPECT_EQ(session.prepare(11, 1, 40, 1000, end - 100, gates, monitor), Reply::refused);
    EXPECT_EQ(session.phase(), Phase::idle);
    EXPECT_EQ(session.next(end - 100, gates, monitor).command, Command::none);
}

TEST_F(BoilerTest, InFlightPositiveCompletionAfterStopCannotDelayZeroOrDisappear) {
    heating();
    const auto positive=session.next(102,gates,monitor);
    ASSERT_TRUE(session.beginTransmit(positive,102,gates,monitor));
    session.stop(103);
    EXPECT_EQ(session.next(103,gates,monitor).command,Command::none); // one in-flight IO owner
    ASSERT_TRUE(session.finishTransmit(positive,110,true,gates,monitor)); // it really completed
    EXPECT_EQ(session.next(110,gates,monitor).command,Command::zero); // no positive write cooldown
    EXPECT_FALSE(session.reportedStopConfirmed());
    EXPECT_FALSE(session.finishTransmit(positive,111,true,gates,monitor)); // no double accounting
}

TEST_F(BoilerTest, DeadlineCanExpireDuringAnAlreadyStartedTransmission) {
    heating();
    const auto positive=session.next(1101,gates,monitor);
    ASSERT_TRUE(session.beginTransmit(positive,1101,gates,monitor));
    ASSERT_TRUE(session.finishTransmit(positive,1103,true,gates,monitor));
    EXPECT_EQ(session.phase(),Phase::stopping);
    EXPECT_EQ(session.next(1103,gates,monitor).command,Command::zero);
    EXPECT_FALSE(session.beginTransmit(positive,1103,gates,monitor));
}

TEST_F(BoilerTest, StopFeedbackMustFollowActualCompletionNotJustBegin) {
    prepare();
    const auto zero=session.next(100,gates,monitor);
    ASSERT_TRUE(session.beginTransmit(zero,100,gates,monitor));
    report(105);
    ASSERT_TRUE(session.finishTransmit(zero,110,true,gates,monitor));
    session.step(111,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::baseline);
    report(112);session.step(112,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::ready);
}

// A delayed owner callback must not turn an expired baseline into permission
// to start, even when the newest telegram reports off.
TEST_F(BoilerTest, BaselineDeadlineWinsOverFreshOffAtOrAfterDeadline) {
    for (const uint64_t at : {3100u, 3101u, 6000u, 9000u}) {
        monitor=ClassicBoilerMonitor{}; // Each independent case has its own RX lifetime.
        BoilerTestSession candidate{11, profile};
        report(90);
        ASSERT_EQ(candidate.prepare(11, 1, 40, 1000, 100, gates, monitor), Reply::accepted);
        const auto zero = candidate.next(100, gates, monitor);
        ASSERT_TRUE(testing_detail::instantTransmission(candidate, zero, 100, true, gates, monitor));
        report(at);
        candidate.step(at, gates, monitor);
        EXPECT_EQ(candidate.phase(), Phase::fault);
        EXPECT_STREQ(candidate.reason(), "reported_stop_timeout");
        EXPECT_FALSE(candidate.reportedStopConfirmed());
        EXPECT_FALSE(candidate.canStart(at, gates, monitor));
    }
}

TEST_F(BoilerTest, StopDeadlineWinsOverFreshOffButDoesNotPreventRecoveryZero) {
    heating();
    session.stop(200);
    auto zero = session.next(200, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 200, true, gates, monitor));
    report(3200);
    session.step(3200, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::fault);
    EXPECT_FALSE(session.reportedStopConfirmed());
    zero = session.next(3200, gates, monitor);
    ASSERT_EQ(zero.command, Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 3200, true, gates, monitor));
    report(3201); session.step(3201, gates, monitor);
    EXPECT_TRUE(session.reportedStopConfirmed());
    EXPECT_EQ(session.phase(), Phase::fault);
}

TEST_F(BoilerTest, OffJustBeforeStopDeadlineStillCompletes) {
    heating(); session.stop(200);
    const auto zero = session.next(200, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session, zero, 200, true, gates, monitor));
    report(3199); session.step(3199, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::completed);
    EXPECT_TRUE(session.reportedStopConfirmed());
}


TEST_F(BoilerTest, DelayedHeatDeadlineDoesNotRenewStopBudget) {
    heating();
    report(4102);
    session.step(4102, gates, monitor); // heat deadline 1102 + stop budget 3000
    EXPECT_EQ(session.phase(), Phase::fault);
    EXPECT_STREQ(session.reason(), "reported_stop_timeout");
    EXPECT_EQ(session.next(4102, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, ExpiredReadyLeaseDoesNotRenewStopBudgetOnLateTick) {
    baseline();
    report(8100); // operator deadline 5100 + stop budget 3000
    session.step(8100, gates, monitor);
    EXPECT_EQ(session.phase(), Phase::fault);
    EXPECT_EQ(session.next(8100, gates, monitor).command, Command::zero);
}

TEST_F(BoilerTest, EarlierOperatorDeadlineWinsWhenBothDeadlinesHavePassed) {
    profile.maximumHeatMs = 10000;
    BoilerTestSession candidate{11, profile};
    report(90);
    ASSERT_EQ(candidate.prepare(11, 1, 40, 10000, 100, gates, monitor), Reply::accepted);
    auto zero = candidate.next(100, gates, monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(candidate, zero, 100, true, gates, monitor));
    report(101); candidate.step(101, gates, monitor);
    ASSERT_EQ(candidate.start(11, 1, 102, gates, monitor), Reply::accepted);
    report(11000); candidate.step(11000, gates, monitor);
    EXPECT_EQ(candidate.phase(), Phase::fault); // lease 5100 expired before heat 10102
    EXPECT_STREQ(candidate.reason(), "reported_stop_timeout");
}

TEST_F(BoilerTest, FaultKeepsItsLatchButDoesNotResendZeroWhileStopEvidenceIsFresh) {
    heating();const auto positive=session.next(102,gates,monitor);
    ASSERT_FALSE(testing_detail::instantTransmission(session,positive,102,false,gates,monitor));
    const auto zero=session.next(103,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,zero,103,true,gates,monitor));
    report(104);session.step(104,gates,monitor);
    ASSERT_TRUE(session.reportedStopConfirmed());
    EXPECT_EQ(session.next(203,gates,monitor).command,Command::none);
    EXPECT_FALSE(session.mayTransmit(zero,203,gates,monitor));
    EXPECT_EQ(session.phase(),Phase::fault);
    EXPECT_EQ(session.prepare(11,2,40,1000,203,gates,monitor),Reply::refused);
}
TEST_F(BoilerTest, LossOfFaultStopEvidenceRequiresANewZeroAndPostCommandReport) {
    // Long write spacing must not postpone a newly necessary stop.
    profile.writeIntervalMs=10000;BoilerTestSession candidate{11,profile};
    report(90);ASSERT_EQ(candidate.prepare(11,1,40,1000,100,gates,monitor),Reply::accepted);
    const auto initial=candidate.next(100,gates,monitor);
    ASSERT_FALSE(testing_detail::instantTransmission(candidate,initial,100,false,gates,monitor));
    const auto zero=candidate.next(101,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(candidate,zero,101,true,gates,monitor));
    report(102);candidate.step(102,gates,monitor);ASSERT_TRUE(candidate.reportedStopConfirmed());
    EXPECT_EQ(candidate.next(103,gates,monitor).command,Command::none);
    report(104,true,20);candidate.step(104,gates,monitor);
    EXPECT_FALSE(candidate.reportedStopConfirmed());
    const auto renewed=candidate.next(104,gates,monitor);
    ASSERT_EQ(renewed.command,Command::zero);
    EXPECT_NE(renewed.epoch,zero.epoch);
    EXPECT_FALSE(candidate.mayTransmit(zero,104,gates,monitor));
    ASSERT_TRUE(testing_detail::instantTransmission(candidate,renewed,104,true,gates,monitor));
    candidate.step(104,gates,monitor);EXPECT_FALSE(candidate.reportedStopConfirmed());
    report(105);candidate.step(105,gates,monitor);EXPECT_TRUE(candidate.reportedStopConfirmed());
    EXPECT_EQ(candidate.phase(),Phase::fault);
}
TEST_F(BoilerTest, ExpiredFaultStopEvidenceCannotRemainConfirmedOrWaitForOldCooldown) {
    profile.writeIntervalMs=10000;BoilerTestSession candidate{11,profile};
    report(90);ASSERT_EQ(candidate.prepare(11,1,40,1000,100,gates,monitor),Reply::accepted);
    const auto failed=candidate.next(100,gates,monitor);
    ASSERT_FALSE(testing_detail::instantTransmission(candidate,failed,100,false,gates,monitor));
    const auto zero=candidate.next(101,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(candidate,zero,101,true,gates,monitor));
    report(102);candidate.step(102,gates,monitor);ASSERT_TRUE(candidate.reportedStopConfirmed());
    candidate.step(2102,gates,monitor);
    EXPECT_FALSE(candidate.reportedStopConfirmed());
    EXPECT_EQ(candidate.next(2102,gates,monitor).command,Command::zero);
}

TEST_F(BoilerTest, ReversedClockRetiresFaultStopProofAndOldZeroTicket) {
    heating();const auto positive=session.next(102,gates,monitor);
    ASSERT_FALSE(testing_detail::instantTransmission(session,positive,102,false,gates,monitor));
    const auto zero=session.next(103,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,zero,103,true,gates,monitor));
    report(104);session.step(104,gates,monitor);ASSERT_TRUE(session.reportedStopConfirmed());
    session.step(103,gates,monitor);
    EXPECT_FALSE(session.reportedStopConfirmed());
    EXPECT_EQ(session.phase(),Phase::fault);
    EXPECT_FALSE(session.mayTransmit(zero,105,gates,monitor));
    EXPECT_EQ(session.next(105,gates,monitor).command,Command::zero);
}

TEST_F(BoilerTest, OlderOffCannotHideNewerRunningStateAndConfirmBaseline) {
    prepare();const auto zero=session.next(100,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,zero,100,true,gates,monitor));
    report(110,true,30);report(105,false,0);
    session.step(111,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::baseline);
    EXPECT_FALSE(session.reportedStopConfirmed());
    report(112,false,0);session.step(112,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::ready);
}
TEST_F(BoilerTest, OlderOffCannotHideNewerRunningStateAndConfirmExplicitStop) {
    heating();session.stop(103);
    const auto zero=session.next(103,gates,monitor);
    ASSERT_TRUE(testing_detail::instantTransmission(session,zero,103,true,gates,monitor));
    report(110,true,30);report(105,false,0);session.step(111,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::stopping);
    EXPECT_FALSE(session.reportedStopConfirmed());
    report(112,false,0);session.step(112,gates,monitor);
    EXPECT_EQ(session.phase(),Phase::completed);
}


TEST_F(BoilerTest, ZeroOnlyNeedsNoHeatLimitsAndNeverBecomesReadyToHeat) {
    profile.minimumFlowC=profile.maximumFlowC=0;profile.maximumHeatMs=0;
    ASSERT_TRUE(profile.validForZero());ASSERT_FALSE(profile.valid());
    BoilerTestSession zero{11,profile};gates.pathReady=gates.limitsSafe=false;report(90);
    ASSERT_TRUE(zero.canPrepare(100,gates,monitor,true));
    ASSERT_EQ(zero.prepare(11,1,0,0,100,gates,monitor,true),Reply::accepted);
    EXPECT_EQ(zero.start(11,1,100,gates,monitor),Reply::refused);
    const auto intent=zero.next(100,gates,monitor);ASSERT_EQ(intent.command,Command::zero);
    ASSERT_TRUE(testing_detail::instantTransmission(zero,intent,100,true,gates,monitor));
    report(100);zero.step(100,gates,monitor);EXPECT_EQ(zero.phase(),Phase::baseline);
    report(101);zero.step(101,gates,monitor);EXPECT_EQ(zero.phase(),Phase::completed);
    EXPECT_TRUE(zero.reportedStopConfirmed());EXPECT_FALSE(zero.active());
    gates.pathReady=gates.limitsSafe=true;
    EXPECT_FALSE(zero.canStart(102,gates,monitor));EXPECT_EQ(zero.start(11,1,102,gates,monitor),Reply::refused);
    EXPECT_EQ(zero.next(102,gates,monitor).command,Command::none);
}
TEST_F(BoilerTest, ZeroOnlyStillRequiresReviewedTimingOwnerTransmitterStopAndFreshReports) {
    report(90);
    for(int missing=0;missing<3;++missing){auto g=gates;if(missing==0)g.transmitterReviewed=false;if(missing==1)g.exclusiveOwner=false;if(missing==2)g.independentStopAvailable=false;
        EXPECT_EQ(session.prepare(11,1,0,0,100,g,monitor,true),Reply::refused);}
    EXPECT_EQ(session.prepare(11,1,1,0,100,gates,monitor,true),Reply::refused);
    EXPECT_EQ(session.prepare(11,1,0,1,100,gates,monitor,true),Reply::refused);
    EXPECT_EQ(session.prepare(11,1,0,0,2100,gates,monitor,true),Reply::refused);
    profile.reviewed=false;BoilerTestSession unreviewed{11,profile};
    EXPECT_EQ(unreviewed.prepare(11,1,0,0,100,gates,monitor,true),Reply::refused);
}
TEST_F(BoilerTest, ZeroOnlyCannotChangeModeUnderSameRevisionOrReviveAfterLeaseLoss) {
    report(90);ASSERT_EQ(session.prepare(11,1,0,0,100,gates,monitor,true),Reply::accepted);
    EXPECT_EQ(session.prepare(11,1,40,1000,100,gates,monitor),Reply::refused);
    EXPECT_EQ(session.prepare(11,1,0,0,100,gates,monitor,true),Reply::duplicate);
    session.step(5100,gates,monitor);EXPECT_EQ(session.phase(),Phase::fault);
    EXPECT_EQ(session.next(5100,gates,monitor).command,Command::zero);
    EXPECT_EQ(session.start(11,1,5100,gates,monitor),Reply::refused);
}
TEST_F(BoilerTest, CompletedZeroOnlyNeedsNewPreparationBeforeAnyHeat) {
    report(90);ASSERT_EQ(session.prepare(11,1,0,0,100,gates,monitor,true),Reply::accepted);
    auto intent=session.next(100,gates,monitor);ASSERT_TRUE(testing_detail::instantTransmission(session,intent,100,true,gates,monitor));
    report(101);session.step(101,gates,monitor);ASSERT_EQ(session.phase(),Phase::completed);
    ASSERT_EQ(session.prepare(11,2,40,1000,102,gates,monitor),Reply::accepted);
    EXPECT_FALSE(session.zeroOnly());EXPECT_EQ(session.phase(),Phase::baseline);
    EXPECT_EQ(session.start(11,2,102,gates,monitor),Reply::refused);
}

} // namespace
