#pragma once
#include <cstdint>
namespace heating::diagnostics {
// Pure restart decision for the supervisor task. On 2026-10-28 the E32 stayed
// "WiFi connected" for 10+ minutes while ping and HTTP were dead, and nothing
// restarted it. Times are monotonic milliseconds; 0 means "never/not tracked".
struct SupervisorPolicy {
    enum class Reason : uint8_t { none = 0, loopStall = 1, wifiLost = 2, brokerLost = 3, networkDead = 4,
        updateStuck = 5, bluetoothApply = 6, bluetoothSilent = 7 }; // append only
    static constexpr uint32_t loopStallMs = 300000;   // a firmware upload blocks the loop for minutes
    static constexpr uint32_t wifiLostMs = 900000;    // loop already calls WiFi.reconnect() every 10 s
    static constexpr uint32_t brokerLostMs = 900000;  // link "up" but the MQTT broker unreachable
    static constexpr uint32_t networkDeadMs = 180000; // Wi-Fi "connected", no IP traffic proven
    static constexpr uint32_t networkDeadProbes = 3;  // failed gateway probes in a row (probe really ran)
    // Consecutive networkDead restarts double the patience, 3 min .. 4 h: a
    // gateway that answers after boot and then dies again must not restart
    // the device every few minutes all night.
    static constexpr uint32_t networkDeadMaxMs = 14400000;
    // A networkDead series ends only when the network still works this long
    // after boot: every networkDead restart needs a probe reply earlier in
    // that boot, so a reset on the first reply would undo the backoff.
    static constexpr uint32_t networkStableMs = 1800000;
    // A stalled TLS stream or upload once kept update::busy() true for good,
    // and with it this supervisor switched off. An update takes minutes.
    static constexpr uint32_t updateMaxMs = 1200000;
    // Consecutive restarts of the same kind (RTC memory) double the patience:
    // an 8-hour access point outage means 5 restarts, not 32.
    static constexpr uint8_t maximumBackoff = 4;
    // Bound Bluetooth sensors, scanning wanted, but no advert for 30 min: the
    // NimBLE host or its start failed. After maximumBackoff restarts in a row
    // (30 min .. 4 h) it gives up until a frame arrives or power is cycled.
    static constexpr uint32_t bluetoothSilentMs = 1800000;

    struct Inputs {
        uint64_t now = 0, loopAt = 0;
        bool updateRunning = false;   // OTA upload/flash: never restart
        bool wifiExpected = false;    // STA mode, not AP/setup/ethernet
        uint64_t wifiDownSince = 0;   // 0 while connected
        bool brokerExpected = false;  // MQTT configured and was connected this boot
        uint64_t brokerDownSince = 0; // 0 while connected
        bool gatewayProbeArmed = false; // the gateway answered a probe this boot
        uint32_t gatewayProbeFailures = 0;
        uint64_t networkQuietSince = 0; // last probe reply, HTTP request, MQTT session or Wi-Fi (re)connect
        uint64_t updateSince = 0;       // first seen updateRunning (0 = unknown: no limit)
        uint8_t wifiLostRestarts = 0;   // consecutive wifiLost restarts before this boot
        uint8_t networkDeadRestarts = 0; // consecutive networkDead restarts before this boot
        bool bluetoothExpected = false; // bound sensors and automatic scanning
        uint64_t bluetoothQuietSince = 0; // boot or the last advert of a bound sensor
        uint8_t bluetoothRestarts = 0;  // consecutive bluetoothSilent restarts before this boot
        bool restartDeferred = false;   // a boiler trial/settings session: no optional restart
    };
    static Reason decide(const Inputs& in) {
        if (in.updateRunning) return elapsed(in.now, in.updateSince, updateMaxMs) ? Reason::updateStuck : Reason::none;
        if (elapsed(in.now, in.loopAt, loopStallMs)) return Reason::loopStall;
        if (in.wifiExpected && in.wifiDownSince && elapsed(in.now, in.wifiDownSince, backoff(wifiLostMs, in.wifiLostRestarts)))
            return Reason::wifiLost;
        if (in.wifiExpected && !in.wifiDownSince && in.gatewayProbeArmed && in.gatewayProbeFailures >= networkDeadProbes
            && elapsed(in.now, in.networkQuietSince, networkDeadDelay(in.networkDeadRestarts))) return Reason::networkDead;
        if (in.brokerExpected && in.brokerDownSince && (!in.wifiExpected || !in.wifiDownSince)
            && elapsed(in.now, in.brokerDownSince, brokerLostMs)) return Reason::brokerLost;
        if (in.bluetoothExpected && !in.restartDeferred && in.bluetoothRestarts < maximumBackoff
            && elapsed(in.now, in.bluetoothQuietSince, backoff(bluetoothSilentMs, in.bluetoothRestarts))) return Reason::bluetoothSilent;
        return Reason::none;
    }
    static const char* name(Reason r) {
        switch (r) {
            case Reason::loopStall: return "loop_stall";
            case Reason::wifiLost: return "wifi_lost";
            case Reason::brokerLost: return "broker_lost";
            case Reason::networkDead: return "network_dead";
            case Reason::updateStuck: return "update_stuck";
            case Reason::bluetoothApply: return "bluetooth_settings";
            case Reason::bluetoothSilent: return "bluetooth_silent";
            default: return "none";
        }
    }
    static uint32_t backoff(uint32_t base, uint8_t restarts) {
        return base << (restarts < maximumBackoff ? restarts : maximumBackoff);
    }
    // 3, 6, 12, 24, 48, 96, 192, then 240 min.
    static uint32_t networkDeadDelay(uint8_t restarts) {
        const uint32_t delay = networkDeadMs << (restarts < 7 ? restarts : 7);
        return delay < networkDeadMaxMs ? delay : networkDeadMaxMs;
    }
    // Positive network evidence at this uptime ends a networkDead series.
    static bool networkSeriesEnded(uint64_t uptimeMs) { return uptimeMs >= networkStableMs; }
private:
    static bool elapsed(uint64_t now, uint64_t since, uint32_t limit) { return since && now >= since && now - since >= limit; }
};
}
