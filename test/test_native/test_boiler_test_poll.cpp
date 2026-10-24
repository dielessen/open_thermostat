#include "EMS/BoilerTestPollDriver.h"
#include <gtest/gtest.h>
#include <functional>
#include <sstream>

namespace {
using namespace heating::ems;
using Result = BoilerTestPollDriver::Result;
struct BoilerPoll : testing::Test {
    // Synthetic envelope and byte encoder: not an installed Classic command.
    BoilerTestSession::Profile profile{true,20,60,10000,3000,2000,5000,100};
    BoilerTestSession::Gates gates{true,true,true,true,true};
    ClassicBoilerMonitor monitor;
    BoilerTestService service{42,true,profile,true};
    uint64_t now=100;
    int writes=0;
    bool succeeds=true;
    std::function<void()> duringWrite;
    const std::string owner=std::string(64,'a');
    const std::string action=R"({"schema":1,"boot_id":"000000000000002a","revision":1})";
    static bool encode(const BoilerTestSession::Intent& intent,EmsRawFrame& frame) {
        frame.length=1;frame.data[0]=intent.flowC;return true;
    }
    void report(uint64_t time) {
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{40,1,0x72,80,0,0}},time);
    }
    void prepare() {
        report(90);
        ASSERT_EQ(service.action("prepare",R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":1})",owner,now,gates,monitor).http,202);
    }
    Result poll(BoilerTestPollDriver::Encoder encoder=encode) {
        return BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{return gates;},encoder,
            [&](const EmsRawFrame& frame) {
                EXPECT_EQ(frame.length,1);++writes;
                if(duringWrite)duringWrite();return succeeds;
            });
    }
    void heating() {
        prepare();ASSERT_EQ(poll(),Result::sent);
        report(++now);service.tick(now,gates,monitor);
        ++now;ASSERT_EQ(service.action("start",action,owner,now,gates,monitor).http,202);
    }
    std::string status() {
        std::ostringstream out;service.writeJSON(out,now,owner,gates,monitor);return out.str();
    }
};

TEST_F(BoilerPoll, IdleDoesNotOwnPollButBaselineAndReadyNeverFallBackToLegacy) {
    EXPECT_EQ(poll(),Result::unowned);EXPECT_EQ(writes,0);
    prepare();EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(poll(),Result::waiting);
    report(++now);service.tick(now,gates,monitor);
    EXPECT_EQ(poll(),Result::waiting);EXPECT_EQ(writes,1);
}

TEST_F(BoilerPoll, MissingOrMalformedEncoderFaultsWithoutCallingWriter) {
    prepare();EXPECT_EQ(poll(nullptr),Result::rejected);EXPECT_EQ(writes,0);
    EXPECT_NE(status().find("test_transport_unavailable"),std::string::npos);
    EXPECT_EQ(poll([](const auto&,auto& frame){frame.length=34;return true;}),Result::rejected);
    EXPECT_EQ(poll([](const auto&,auto&){return true;}),Result::rejected);
    EXPECT_EQ(poll([](const auto&,auto&){return false;}),Result::rejected);
    EXPECT_EQ(writes,0);
    // Fault retains ownership. A later legitimate encoder may send zero only.
    EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(writes,1);
    EXPECT_NE(status().find("\"positive_frames\":0"),std::string::npos);
}

TEST_F(BoilerPoll, DeadlinePassingDuringEncodingPreventsPositiveWriteAndNextPollSendsZero) {
    heating();
    // Stateless encoder's test hook advances the supplied clock at final check.
    unsigned reads=0;
    auto result=BoilerTestPollDriver::poll(service,monitor,
        [&]{return ++reads==1 ? now : uint64_t(1102);},[&]{return gates;},encode,
        [&](const auto&){++writes;return true;});
    EXPECT_EQ(result,Result::rejected);EXPECT_EQ(writes,1);
    now=1102;EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(writes,2);
    EXPECT_NE(status().find("\"positive_frames\":0"),std::string::npos);
}

TEST_F(BoilerPoll, StopBetweenSelectionAndDispatchInvalidatesSelectedPositive) {
    heating();unsigned reads=0;
    auto result=BoilerTestPollDriver::poll(service,monitor,[&]{
        if(++reads==2)EXPECT_EQ(service.action("stop",action,owner,now,gates,monitor).http,202);
        return now;
    },[&]{return gates;},encode,[&](const auto&){++writes;return true;});
    EXPECT_EQ(result,Result::rejected);EXPECT_EQ(writes,1);
    EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(writes,2);
}

TEST_F(BoilerPoll, LosingExclusiveOwnerAtFinalAdmissionNeverWrites) {
    heating();unsigned checks=0;
    auto result=BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{
        if(++checks==2)gates.exclusiveOwner=false;return gates;
    },encode,[&](const auto&){++writes;return true;});
    EXPECT_EQ(result,Result::rejected);EXPECT_EQ(writes,1);
    EXPECT_EQ(poll(),Result::waiting);EXPECT_EQ(writes,1);
}

TEST_F(BoilerPoll, FailedWriteStaysUnconfirmedAndFaultRetainsPollOwnership) {
    prepare();succeeds=false;
    EXPECT_EQ(poll(),Result::failed);EXPECT_EQ(writes,1);
    EXPECT_NE(status().find("transmission_failed"),std::string::npos);
    EXPECT_NE(status().find("\"zero_frames\":0"),std::string::npos);
    succeeds=true;EXPECT_EQ(poll(),Result::sent);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":false"),std::string::npos);
}

TEST_F(BoilerPoll, StopDuringSuccessfulWriteCountsHistoryButZeroBypassesPositiveBudget) {
    heating();duringWrite=[&]{
        EXPECT_EQ(service.action("stop",action,owner,++now,gates,monitor).http,202);
    };
    EXPECT_EQ(poll(),Result::sent);
    EXPECT_NE(status().find("\"positive_frames\":1"),std::string::npos);
    duringWrite={};EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(writes,3);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":false"),std::string::npos);
    report(++now);service.tick(now,gates,monitor);
    EXPECT_EQ(poll(),Result::unowned);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":true"),std::string::npos);
}

TEST_F(BoilerPoll, DeadlineDuringWriteRecordsPositiveThenImmediatelyWithdraws) {
    heating();duringWrite=[&]{now=1102;};
    EXPECT_EQ(poll(),Result::sent);
    duringWrite={};EXPECT_EQ(poll(),Result::sent);EXPECT_EQ(writes,3);
    EXPECT_NE(status().find("\"positive_frames\":1"),std::string::npos);
    EXPECT_NE(status().find("\"zero_frames\":2"),std::string::npos);
}

TEST_F(BoilerPoll, TransportFaultInvalidatesOldPositiveAndNeverAutomaticallyRearms) {
    heating();auto old=service.next(now,gates,monitor);
    service.transportFault(now);
    EXPECT_FALSE(service.mayTransmit(old,now,gates,monitor));
    EXPECT_EQ(poll(),Result::sent);
    report(++now);service.tick(now,gates,monitor);
    EXPECT_NE(status().find("\"phase\":\"fault\""),std::string::npos);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":true"),std::string::npos);
    EXPECT_TRUE(service.action("start",action,owner,now,gates,monitor).duplicate);
    EXPECT_NE(status().find("\"phase\":\"fault\""),std::string::npos);
    EXPECT_NE(status().find("\"positive_frames\":0"),std::string::npos);
}
TEST_F(BoilerPoll, FreshFaultStopRetainsOwnershipWithoutRedundantWritesOrRestart) {
    prepare();succeeds=false;ASSERT_EQ(poll(),Result::failed);
    succeeds=true;++now;ASSERT_EQ(poll(),Result::sent);
    report(++now);service.tick(now,gates,monitor);
    ASSERT_NE(status().find("\"reported_stop_confirmed\":true"),std::string::npos);
    now+=100;EXPECT_EQ(poll(),Result::waiting);EXPECT_EQ(writes,2);
    EXPECT_TRUE(service.active());
    EXPECT_NE(status().find("\"phase\":\"fault\""),std::string::npos);
    EXPECT_EQ(service.action("start",action,owner,now,gates,monitor).http,409);
    EXPECT_EQ(poll(),Result::waiting);EXPECT_EQ(writes,2);
}
TEST_F(BoilerPoll, ExpiredFaultStopRequiresFreshZeroAndLaterReportWithoutLegacyFallback) {
    prepare();succeeds=false;ASSERT_EQ(poll(),Result::failed);
    succeeds=true;++now;ASSERT_EQ(poll(),Result::sent);
    report(++now);service.tick(now,gates,monitor);
    ASSERT_NE(status().find("\"reported_stop_confirmed\":true"),std::string::npos);
    now+=profile.reportTtlMs;service.tick(now,gates,monitor);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":false"),std::string::npos);
    ASSERT_EQ(poll(),Result::sent);EXPECT_EQ(writes,3);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":false"),std::string::npos);
    report(++now);service.tick(now,gates,monitor);
    EXPECT_NE(status().find("\"reported_stop_confirmed\":true"),std::string::npos);
    EXPECT_EQ(poll(),Result::waiting);EXPECT_EQ(writes,3);
    EXPECT_NE(status().find("\"positive_frames\":0"),std::string::npos);
    EXPECT_NE(status().find("\"phase\":\"fault\""),std::string::npos);
}

} // namespace
