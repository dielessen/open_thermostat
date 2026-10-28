#include "diagnostics/BlackBox.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>

namespace {
using heating::diagnostics::BlackBox;
using heating::diagnostics::BlackBoxRecord;
using heating::diagnostics::SupervisorPolicy;
using Reason = SupervisorPolicy::Reason;
using heating::diagnostics::LoopPhase;
using heating::diagnostics::LoopPhaseRecord;
LoopPhaseRecord phaseRtc{};
constexpr uint64_t minute = 60000;

SupervisorPolicy::Inputs healthy(uint64_t now) {
    SupervisorPolicy::Inputs in;
    in.now = now; in.loopAt = now; in.wifiExpected = true; in.brokerExpected = true;
    return in;
}

TEST(SupervisorPolicy, HealthyDeviceIsNeverRestarted) {
    EXPECT_EQ(SupervisorPolicy::decide(healthy(100 * minute)), Reason::none);
}
TEST(SupervisorPolicy, LoopStallRestartsButNeverDuringAnUpdate) {
    auto in = healthy(100 * minute);
    in.loopAt = in.now - 4 * minute;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.loopAt = in.now - 5 * minute;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::loopStall);
    in.updateRunning = true;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}
TEST(SupervisorPolicy, WifiDownAfterReconnectAttemptsRestarts) {
    auto in = healthy(100 * minute);
    in.wifiDownSince = in.now - 14 * minute;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.wifiDownSince = in.now - 15 * minute;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::wifiLost);
    in.wifiExpected = false; // setup access point or ethernet
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}
TEST(SupervisorPolicy, LinkUpButBrokerUnreachableRestarts) {
    // 2026-10-28: "WiFi connected" for 10+ minutes while ping and HTTP were dead.
    auto in = healthy(100 * minute);
    in.brokerDownSince = in.now - 15 * minute;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::brokerLost);
    in.brokerExpected = false; // no broker configured or never connected this boot
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}

TEST(BlackBox, ColdBootHasNoPreviousRecord) {
    BlackBoxRecord rtc;
    std::memset(&rtc, 0xA5, sizeof(rtc)); // RTC memory after power-on is undefined
    BlackBox box; box.begin(rtc, phaseRtc, 1);
    EXPECT_FALSE(box.havePrevious());
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> j(box.json(), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "previous")));
}
TEST(BlackBox, SupervisorRestartKeepsTheLastStateForTheNextBoot) {
    BlackBoxRecord rtc{};
    BlackBox first; first.begin(rtc, phaseRtc, 1);
    first.note(44387, 9796, 284, 120, -61, true, false);
    first.request("/config/programs/default");
    first.restartReason(Reason::brokerLost);
    first.loopPhase(LoopPhase::http); // stuck serving the request
    BlackBox second; second.begin(rtc, phaseRtc, 3); // same RTC memory after esp_restart()
    ASSERT_TRUE(second.havePrevious());
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> j(second.json(), cJSON_Delete);
    const auto* p = cJSON_GetObjectItem(j.get(), "previous");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "uptime_s")), 44387);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "loop_stack_minimum_bytes")), 284);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(p, "last_request")), "/config/programs/default");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(p, "supervisor_restart")), "broker_lost");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(p, "broker_connected")));
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(p, "loop_phase")), "http");
    BlackBox third; third.begin(rtc, phaseRtc, 3); // the new boot's record replaced it
    EXPECT_EQ(third.previous().uptimeS, 0u);
}
TEST(BlackBox, CorruptedRecordIsNotReported) {
    BlackBoxRecord rtc{};
    BlackBox first; first.begin(rtc, phaseRtc, 1); first.note(10, 1, 1, 1, 0, true, true);
    rtc.uptimeS ^= 1;
    BlackBox second; second.begin(rtc, phaseRtc, 4);
    EXPECT_FALSE(second.havePrevious());
}
TEST(BlackBox, LongRequestPathIsTruncatedSafely) {
    BlackBoxRecord rtc{};
    BlackBox box; box.begin(rtc, phaseRtc, 1);
    box.request(std::string(100, 'x').c_str());
    EXPECT_EQ(std::strlen(rtc.lastRequest), sizeof(rtc.lastRequest) - 1);
}
TEST(BlackBox, LoopPhasesAppendedLaterKeepStoredValuesAndHaveNames) {
    EXPECT_EQ(static_cast<int>(LoopPhase::telemetry), 6);
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::ems), "ems");
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::operate), "operate");
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::health), "health_and_log");
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::wifi_reconnect), "wifi_reconnect");
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::bluetooth), "bluetooth");
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::mqtt), "mqtt");
}
}
