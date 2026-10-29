#include "diagnostics/BlackBox.h"
#include "diagnostics/GatewayProbe.h"
#include "diagnostics/ReconnectBackoff.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <vector>

namespace {
using heating::diagnostics::BlackBox;
using heating::diagnostics::BlackBoxRecord;
using heating::diagnostics::SupervisorPolicy;
using Reason = SupervisorPolicy::Reason;
using heating::diagnostics::LoopPhase;
using heating::diagnostics::LoopPhaseRecord;
using heating::diagnostics::IcmpEcho;
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
// Wi-Fi "connected", the gateway answered earlier this boot, now nothing works.
SupervisorPolicy::Inputs silentNetwork(uint64_t now, uint64_t quietFor) {
    auto in = healthy(now);
    in.gatewayProbeArmed = true; in.gatewayProbeFailures = 6; in.networkQuietSince = now - quietFor;
    return in;
}
TEST(SupervisorPolicy, ConnectedWifiWithoutAnyIpTrafficRestartsAfterThreeMinutes) {
    EXPECT_EQ(SupervisorPolicy::decide(silentNetwork(100 * minute, 3 * minute - 1000)), Reason::none);
    EXPECT_EQ(SupervisorPolicy::decide(silentNetwork(100 * minute, 3 * minute)), Reason::networkDead);
    auto in = silentNetwork(100 * minute, 30 * minute);
    in.updateRunning = true;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.updateRunning = false; in.loopAt = in.now - 5 * minute; // a dead loop is reported as such
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::loopStall);
}
TEST(SupervisorPolicy, PositiveNetworkEvidenceRestartsTheQuietClock) {
    // A probe reply, routed HTTP request or MQTT session sets networkQuietSince.
    EXPECT_EQ(SupervisorPolicy::decide(silentNetwork(100 * minute, 10000)), Reason::none);
    auto in = silentNetwork(100 * minute, 10 * minute);
    in.networkQuietSince = 0; // not tracked
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}
TEST(SupervisorPolicy, NetworkDeadNeedsProbesThatRanAndAGatewayThatAnswersProbes) {
    auto in = silentNetwork(100 * minute, 10 * minute);
    in.gatewayProbeFailures = 2; // a slow loop that did not probe is no network evidence
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.gatewayProbeFailures = 3;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::networkDead);
    in.gatewayProbeArmed = false; // this gateway never answered ICMP echo this boot
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}
TEST(SupervisorPolicy, NetworkDeadOnlyWhileWifiReportsConnectedInStationMode) {
    auto in = silentNetwork(100 * minute, 10 * minute);
    in.wifiDownSince = in.now - minute; // disconnected: the wifiLost path applies
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.wifiDownSince = 0; in.wifiExpected = false; // setup access point or ethernet
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    EXPECT_EQ(static_cast<int>(Reason::networkDead), 4); // stored in RTC by earlier boots
    EXPECT_STREQ(SupervisorPolicy::name(Reason::networkDead), "network_dead");
}

TEST(GatewayProbe, EchoChecksumMatchesRfc1071) {
    const uint8_t sample[] = {0x00, 0x01, 0xf2, 0x03, 0xf4, 0xf5, 0xf6, 0xf7};
    EXPECT_EQ(IcmpEcho::checksum(sample, sizeof(sample)), 0x220d);
    uint8_t echo[IcmpEcho::size];
    IcmpEcho::request(echo, 0x4F54, 7);
    EXPECT_EQ(echo[0], 8);
    EXPECT_EQ(IcmpEcho::checksum(echo, sizeof(echo)), 0);
}
TEST(GatewayProbe, OnlyTheMatchingReplyFromTheGatewayCounts) {
    uint8_t packet[20 + IcmpEcho::size]{0x45, 0, 0, sizeof(packet), 0, 0, 0, 0, 64, 1, 0, 0, 192, 168, 1, 1, 192, 168, 1, 42};
    uint8_t echo[IcmpEcho::size];
    IcmpEcho::request(echo, 0x4F54, 7);
    echo[0] = 0; echo[2] = echo[3] = 0; // the gateway's echo reply
    const uint16_t sum = IcmpEcho::checksum(echo, sizeof(echo));
    echo[2] = sum >> 8; echo[3] = sum & 0xFF;
    std::memcpy(packet + 20, echo, sizeof(echo));
    uint32_t gateway, other;
    const uint8_t g[] = {192, 168, 1, 1}, o[] = {192, 168, 1, 2};
    std::memcpy(&gateway, g, 4); std::memcpy(&other, o, 4);
    EXPECT_TRUE(IcmpEcho::isReply(packet, sizeof(packet), gateway, 0x4F54, 7));
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet), other, 0x4F54, 7));
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet), gateway, 0x4F54, 8)); // an older probe
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet), gateway, 0x1234, 7)); // someone else's ping
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet) - 1, gateway, 0x4F54, 7)); // truncated
    packet[20] = 8; // an echo request to us, not a reply
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet), gateway, 0x4F54, 7));
    packet[20] = 0; packet[30] ^= 1; // corrupted payload
    EXPECT_FALSE(IcmpEcho::isReply(packet, sizeof(packet), gateway, 0x4F54, 7));
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
    EXPECT_EQ(static_cast<int>(LoopPhase::network_probe), 12);
    EXPECT_STREQ(BlackBox::phaseName(LoopPhase::network_probe), "network_probe");
}
TEST(BlackBox, RoutedRequestsAreCountedAsNetworkEvidence) {
    BlackBoxRecord rtc{};
    BlackBox box;
    box.request("/status"); // before begin(): counted, not recorded
    box.begin(rtc, phaseRtc, 1);
    box.request("/status");
    EXPECT_EQ(box.requests(), 2u);
    box.restartReason(Reason::networkDead);
    BlackBox next; next.begin(rtc, phaseRtc, 3);
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> j(next.json(), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "previous"), "supervisor_restart")), "network_dead");
}
}

namespace {
using heating::diagnostics::BlackBox;
using heating::diagnostics::BlackBoxRecord;
using heating::diagnostics::LoopPhaseRecord;
using heating::diagnostics::SupervisorPolicy;
using Reason = SupervisorPolicy::Reason;
constexpr uint64_t minute18 = 60000;
SupervisorPolicy::Inputs healthy18(uint64_t now) {
    SupervisorPolicy::Inputs in; in.now = now; in.loopAt = now; in.wifiExpected = true; return in;
}
TEST(SupervisorPolicy, UpdateExemptionEndsAfterTwentyMinutes) {
    auto in = healthy18(100 * minute18);
    in.loopAt = in.now - 10 * minute18; in.updateRunning = true; in.updateSince = in.now - 19 * minute18;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.updateSince = in.now - 20 * minute18; // a stalled TLS stream keeps busy() true forever
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::updateStuck);
    in.updateSince = 0; // start unknown: never restart an update
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    EXPECT_STREQ(SupervisorPolicy::name(Reason::updateStuck), "update_stuck");
}
TEST(SupervisorPolicy, WifiLostRestartsBackOffExponentially) {
    auto in = healthy18(1000 * minute18);
    const uint32_t expected[] = {15, 30, 60, 120, 240, 240, 240};
    for (uint8_t n = 0; n < 7; ++n) {
        in.wifiLostRestarts = n;
        in.wifiDownSince = in.now - (expected[n] * minute18 - 1000);
        EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none) << int(n);
        in.wifiDownSince = in.now - expected[n] * minute18;
        EXPECT_EQ(SupervisorPolicy::decide(in), Reason::wifiLost) << int(n);
    }
    // An 8-hour access point outage: 15+30+60+120+240 min = 5 restarts, not 32.
    uint32_t t = 0, restarts = 0;
    for (uint8_t n = 0; t + expected[n < 6 ? n : 6] <= 480; ++n) { t += expected[n < 6 ? n : 6]; ++restarts; }
    EXPECT_EQ(restarts, 5u);
}
TEST(SupervisorPolicy, NetworkDeadRestartsBackOffFromThreeMinutesToFourHours) {
    const uint32_t expected[] = {3, 6, 12, 24, 48, 96, 192, 240, 240, 240, 240, 240, 240, 240, 240, 240};
    for (uint8_t n = 0; n < 16; ++n) {
        auto in = healthy18(1000 * minute18);
        in.gatewayProbeArmed = true; in.gatewayProbeFailures = 6; in.networkDeadRestarts = n;
        in.networkQuietSince = in.now - (expected[n] * minute18 - 1000);
        EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none) << int(n);
        in.networkQuietSince = in.now - expected[n] * minute18;
        EXPECT_EQ(SupervisorPolicy::decide(in), Reason::networkDead) << int(n);
        EXPECT_EQ(SupervisorPolicy::networkDeadDelay(n), expected[n] * minute18) << int(n);
    }
    EXPECT_EQ(SupervisorPolicy::networkDeadDelay(255), 240 * minute18); // no shift overflow
}
TEST(BlackBox, NetworkDeadSeriesCountsAndEndsOnlyAfterTheNetworkLasted) {
    LoopPhaseRecord phase{}; BlackBoxRecord rtc{};
    BlackBox first; first.begin(rtc, phase, 1);
    first.restartReason(Reason::networkDead);
    BlackBox second; second.begin(rtc, phase, 3);
    EXPECT_EQ(second.networkDeadRestarts(), 1u);
    // Each networkDead restart needs a probe reply earlier in that boot: an
    // early reply must not undo the backoff.
    second.networkWorked(10000);
    second.networkWorked(29 * minute18);
    EXPECT_EQ(second.networkDeadRestarts(), 1u);
    second.restartReason(Reason::networkDead);
    BlackBox third; third.begin(rtc, phase, 3);
    EXPECT_EQ(third.networkDeadRestarts(), 2u);
    EXPECT_EQ(third.wifiLostRestarts(), 0u); // separate series
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> j(third.json(), cJSON_Delete);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(j.get(), "network_dead_restarts")), 2);
    third.networkWorked(30 * minute18); // the network lasted 30 min after boot
    EXPECT_EQ(third.networkDeadRestarts(), 0u);
    for (int i = 0; i < 40; ++i) third.restartReason(Reason::networkDead);
    BlackBox capped; capped.begin(rtc, phase, 3);
    EXPECT_EQ(capped.networkDeadRestarts(), BlackBox::maximumCount);
    std::memset(&phase, 0xA5, sizeof(phase)); // power cut: RTC memory undefined
    BlackBox cold; cold.begin(rtc, phase, 1);
    EXPECT_EQ(cold.networkDeadRestarts(), 0u);
}
TEST(SupervisorPolicy, SilentBluetoothRestartsRarelyAndNeverDuringATrial) {
    auto in = healthy18(1000 * minute18);
    in.bluetoothExpected = true; in.bluetoothQuietSince = in.now - 29 * minute18;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.bluetoothQuietSince = in.now - 30 * minute18;
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::bluetoothSilent);
    in.restartDeferred = true; EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.restartDeferred = false; in.bluetoothExpected = false; EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.bluetoothExpected = true; in.bluetoothRestarts = 1; EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
    in.bluetoothQuietSince = in.now - 60 * minute18; EXPECT_EQ(SupervisorPolicy::decide(in), Reason::bluetoothSilent);
    in.bluetoothRestarts = SupervisorPolicy::maximumBackoff; in.bluetoothQuietSince = 1; // gives up
    EXPECT_EQ(SupervisorPolicy::decide(in), Reason::none);
}
TEST(BlackBox, RestartReasonIsASeparateByteAndCountsBackoff) {
    LoopPhaseRecord phase{}; BlackBoxRecord rtc{};
    BlackBox first; first.begin(rtc, phase, 1);
    first.note(100, 2000, 300, 10, -50, false, false);
    const auto sealed = rtc.check;
    first.restartReason(Reason::wifiLost); // supervisor task: must not touch the loop's record
    EXPECT_EQ(rtc.check, sealed);
    BlackBox second; second.begin(rtc, phase, 3);
    EXPECT_EQ(second.previousRestart(), Reason::wifiLost);
    EXPECT_EQ(second.wifiLostRestarts(), 1u);
    second.restartReason(Reason::wifiLost);
    BlackBox third; third.begin(rtc, phase, 3);
    EXPECT_EQ(third.wifiLostRestarts(), 2u);
    third.wifiRecovered(); EXPECT_EQ(third.wifiLostRestarts(), 0u);
    third.restartReason(Reason::bluetoothSilent);
    BlackBox fourth; fourth.begin(rtc, phase, 3);
    EXPECT_EQ(fourth.bluetoothRestarts(), 1u); fourth.bluetoothHeard(); EXPECT_EQ(fourth.bluetoothRestarts(), 0u);
    std::memset(&phase, 0xA5, sizeof(phase)); // power cut: RTC memory undefined
    BlackBox cold; cold.begin(rtc, phase, 1);
    EXPECT_EQ(cold.wifiLostRestarts(), 0u); EXPECT_EQ(cold.previousRestart(), Reason::none);
}
TEST(BlackBox, ResourceMinimaKeepTheLowestValueAndReachTheNextBoot) {
    LoopPhaseRecord phase{}; BlackBoxRecord rtc{};
    BlackBox box; box.begin(rtc, phase, 1);
    box.noteResources(60000, 1200, 900, 0); box.noteResources(40000, 1500, 800, 2000); box.noteResources(50000, 0, 1000, 2500);
    BlackBox next; next.begin(rtc, phase, 3);
    ASSERT_TRUE(next.havePrevious());
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> j(next.json(), cJSON_Delete);
    const auto* p = cJSON_GetObjectItem(j.get(), "previous");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "minimum_largest_internal_block_bytes")), 40000);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "supervisor_stack_minimum_bytes")), 1200);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "ems_uart_stack_minimum_bytes")), 800);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(p, "bluetooth_host_stack_minimum_bytes")), 2000);
}
}

namespace {
TEST(ReconnectBackoff, WifiReconnectsAfterTenTwentyFortyThenEverySixtySeconds) {
    heating::diagnostics::ReconnectBackoff b;
    std::vector<uint64_t> attempts;
    for (uint64_t t = 0; t <= 300000; t += 10000) if (b.due(t, t < 20000)) attempts.push_back(t);
    // down first seen at 20 s
    EXPECT_EQ(attempts, (std::vector<uint64_t>{30000, 50000, 90000, 150000, 210000, 270000}));
    EXPECT_FALSE(b.due(310000, true)); // connected again: the next outage starts at 10 s
    EXPECT_FALSE(b.due(320000, false)); EXPECT_TRUE(b.due(330000, false));
}
}
