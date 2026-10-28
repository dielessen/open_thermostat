#pragma once
#include <cstdint>
namespace heating::diagnostics {
// Pure restart decision for the supervisor task. On 2026-10-28 the E32 stayed
// "WiFi connected" for 10+ minutes while ping and HTTP were dead, and nothing
// restarted it. Times are monotonic milliseconds; 0 means "never/not tracked".
struct SupervisorPolicy {
    enum class Reason : uint8_t { none = 0, loopStall = 1, wifiLost = 2, brokerLost = 3 };
    static constexpr uint32_t loopStallMs = 300000;   // a firmware upload blocks the loop for minutes
    static constexpr uint32_t wifiLostMs = 900000;    // loop already calls WiFi.reconnect() every 10 s
    static constexpr uint32_t brokerLostMs = 900000;  // link "up" but the MQTT broker unreachable

    struct Inputs {
        uint64_t now = 0, loopAt = 0;
        bool updateRunning = false;   // OTA upload/flash: never restart
        bool wifiExpected = false;    // STA mode, not AP/setup/ethernet
        uint64_t wifiDownSince = 0;   // 0 while connected
        bool brokerExpected = false;  // MQTT configured and was connected this boot
        uint64_t brokerDownSince = 0; // 0 while connected
    };
    static Reason decide(const Inputs& in) {
        if (in.updateRunning) return Reason::none;
        if (elapsed(in.now, in.loopAt, loopStallMs)) return Reason::loopStall;
        if (in.wifiExpected && in.wifiDownSince && elapsed(in.now, in.wifiDownSince, wifiLostMs)) return Reason::wifiLost;
        if (in.brokerExpected && in.brokerDownSince && (!in.wifiExpected || !in.wifiDownSince)
            && elapsed(in.now, in.brokerDownSince, brokerLostMs)) return Reason::brokerLost;
        return Reason::none;
    }
    static const char* name(Reason r) {
        switch (r) {
            case Reason::loopStall: return "loop_stall";
            case Reason::wifiLost: return "wifi_lost";
            case Reason::brokerLost: return "broker_lost";
            default: return "none";
        }
    }
private:
    static bool elapsed(uint64_t now, uint64_t since, uint32_t limit) { return since && now >= since && now - since >= limit; }
};
}
