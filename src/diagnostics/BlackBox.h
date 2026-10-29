#pragma once
#include "diagnostics/SupervisorPolicy.h"
#include <cJSON.h>
#include <cstdint>
#include <cstring>
namespace heating::diagnostics {
// Last-known state in RTC memory: survives a software/watchdog/panic restart,
// not a power cut. Written every 10 s and before a supervisor restart, so the
// next boot can show what the device was doing when it stopped.
struct BlackBoxRecord {
    uint32_t magic, uptimeS, minFreeHeap, loopStackMin, loopAgeMs, check;
    int8_t rssi;
    uint8_t wifiConnected, brokerConnected, reason;
    char lastRequest[40];
    // Appended in beta.18: the smallest largest-free internal block and the
    // stack high-water marks (bytes) of the other long-lived tasks.
    uint32_t minLargestInternal;
    uint16_t supervisorStackMin, emsStackMin, bleHostStackMin, reserved;
};
// Which part of the main loop runs, written several times per iteration, so it
// is kept outside the checksummed record: one byte behind its own magic.
// Append only: a stored value from the previous boot keeps its meaning.
// The supervisor's restart reason and the restart backoff counters live here
// too: single bytes, so the supervisor task never rewrites the checksummed
// record that the loop writes at the same time.
enum class LoopPhase : uint8_t { idle, update, network, controller, ems, http, telemetry,
    operate, health, wifi_reconnect, bluetooth, mqtt, network_probe };
struct LoopPhaseRecord { uint32_t magic; volatile uint8_t phase, reason, wifiLostRestarts, bluetoothRestarts; };

class BlackBox {
public:
    static constexpr uint32_t magic = 0x4F54424Bu; // "OTBK"
    static constexpr uint32_t phaseMagic = 0x4F545032u; // "OTP2": phase + reason + backoff
    static constexpr uint8_t maximumCount = 15;
    // At boot: keep a valid record as the previous boot, then start a new one.
    void begin(BlackBoxRecord& current, LoopPhaseRecord& phase, int resetReason) {
        current_ = &current; phase_ = &phase;
        resetReason_ = resetReason;
        havePrevious_ = current.magic == magic && current.check == checksum(current);
        if (havePrevious_) previous_ = current;
        const bool phaseValid = phase.magic == phaseMagic;
        previousPhase_ = phaseValid ? static_cast<LoopPhase>(phase.phase) : LoopPhase::idle;
        previousReason_ = phaseValid ? phase.reason : 0;
        const uint8_t wifi = phaseValid ? phase.wifiLostRestarts : 0, bluetooth = phaseValid ? phase.bluetoothRestarts : 0;
        std::memset(&current, 0, sizeof(current));
        seal();
        phase.magic = phaseMagic; phase.phase = 0; phase.reason = 0;
        phase.wifiLostRestarts = wifi > maximumCount ? maximumCount : wifi;
        phase.bluetoothRestarts = bluetooth > maximumCount ? maximumCount : bluetooth;
    }
    void loopPhase(LoopPhase phase) { if (phase_) phase_->phase = static_cast<uint8_t>(phase); }
    void note(uint32_t uptimeS, uint32_t minFreeHeap, uint32_t loopStackMin, uint32_t loopAgeMs,
              int8_t rssi, bool wifiConnected, bool brokerConnected) {
        if (!current_) return;
        auto& r = *current_;
        r.uptimeS = uptimeS; r.minFreeHeap = minFreeHeap; r.loopStackMin = loopStackMin; r.loopAgeMs = loopAgeMs;
        r.rssi = rssi; r.wifiConnected = wifiConnected; r.brokerConnected = brokerConnected;
        seal();
    }
    void request(const char* path) {
        ++requests_; // any routed request proves the IP path (supervisor evidence)
        if (!current_ || !path) return;
        std::strncpy(current_->lastRequest, path, sizeof(current_->lastRequest) - 1);
        current_->lastRequest[sizeof(current_->lastRequest) - 1] = 0;
        seal();
    }
    // Lowest values seen this boot; written by the loop with note().
    void noteResources(uint32_t largestInternal, uint32_t supervisorStack, uint32_t emsStack, uint32_t bleHostStack) {
        if (!current_) return;
        auto& r = *current_;
        const auto low16 = [](uint16_t& field, uint32_t value) {
            if (!value) return; // task not running (yet)
            const auto v = static_cast<uint16_t>(value > 0xFFFF ? 0xFFFF : value);
            if (!field || v < field) field = v;
        };
        if (largestInternal && (!r.minLargestInternal || largestInternal < r.minLargestInternal)) r.minLargestInternal = largestInternal;
        low16(r.supervisorStackMin, supervisorStack); low16(r.emsStackMin, emsStack); low16(r.bleHostStackMin, bleHostStack);
        seal();
    }
    // Any task: one byte, no checksum to race with the loop's note()/request().
    void restartReason(SupervisorPolicy::Reason reason) {
        if (!phase_) return;
        phase_->reason = static_cast<uint8_t>(reason);
        if (reason == SupervisorPolicy::Reason::wifiLost && phase_->wifiLostRestarts < maximumCount) ++phase_->wifiLostRestarts;
        if (reason == SupervisorPolicy::Reason::bluetoothSilent && phase_->bluetoothRestarts < maximumCount) ++phase_->bluetoothRestarts;
    }
    // Recovery ends a restart series: the next outage starts at the base delay.
    void wifiRecovered() { if (phase_) phase_->wifiLostRestarts = 0; }
    void bluetoothHeard() { if (phase_ && phase_->bluetoothRestarts) phase_->bluetoothRestarts = 0; }
    uint8_t wifiLostRestarts() const { return phase_ ? phase_->wifiLostRestarts : 0; }
    uint8_t bluetoothRestarts() const { return phase_ ? phase_->bluetoothRestarts : 0; }
    // {"reset_reason":n,"previous":{...}|null}
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON_AddNumberToObject(root, "reset_reason", resetReason_);
        cJSON_AddNumberToObject(root, "wifi_lost_restarts", wifiLostRestarts());
        cJSON_AddNumberToObject(root, "bluetooth_silent_restarts", bluetoothRestarts());
        if (!havePrevious_) { cJSON_AddNullToObject(root, "previous"); return root; }
        cJSON* p = cJSON_AddObjectToObject(root, "previous");
        if (!p) { cJSON_Delete(root); return nullptr; }
        const auto& r = previous_;
        cJSON_AddNumberToObject(p, "uptime_s", r.uptimeS);
        cJSON_AddNumberToObject(p, "minimum_free_heap_bytes", r.minFreeHeap);
        cJSON_AddNumberToObject(p, "loop_stack_minimum_bytes", r.loopStackMin);
        cJSON_AddNumberToObject(p, "loop_age_ms", r.loopAgeMs);
        cJSON_AddNumberToObject(p, "wifi_rssi", r.rssi);
        cJSON_AddBoolToObject(p, "wifi_connected", r.wifiConnected);
        cJSON_AddBoolToObject(p, "broker_connected", r.brokerConnected);
        cJSON_AddStringToObject(p, "supervisor_restart",
            SupervisorPolicy::name(static_cast<SupervisorPolicy::Reason>(previousReason_)));
        cJSON_AddNumberToObject(p, "minimum_largest_internal_block_bytes", r.minLargestInternal);
        cJSON_AddNumberToObject(p, "supervisor_stack_minimum_bytes", r.supervisorStackMin);
        cJSON_AddNumberToObject(p, "ems_uart_stack_minimum_bytes", r.emsStackMin);
        cJSON_AddNumberToObject(p, "bluetooth_host_stack_minimum_bytes", r.bleHostStackMin);
        char path[sizeof(r.lastRequest)];
        std::memcpy(path, r.lastRequest, sizeof(path));
        path[sizeof(path) - 1] = 0;
        cJSON_AddStringToObject(p, "last_request", path);
        cJSON_AddStringToObject(p, "loop_phase", phaseName(previousPhase_));
        return root;
    }
    uint32_t requests() const { return requests_; }
    bool havePrevious() const { return havePrevious_; }
    LoopPhase previousPhase() const { return previousPhase_; }
    static const char* phaseName(LoopPhase p) {
        switch (p) {
            case LoopPhase::update: return "update";
            case LoopPhase::network: return "network";
            case LoopPhase::controller: return "controller";
            case LoopPhase::ems: return "ems";
            case LoopPhase::http: return "http";
            case LoopPhase::telemetry: return "telemetry";
            case LoopPhase::operate: return "operate";
            case LoopPhase::health: return "health_and_log";
            case LoopPhase::wifi_reconnect: return "wifi_reconnect";
            case LoopPhase::bluetooth: return "bluetooth";
            case LoopPhase::mqtt: return "mqtt";
            case LoopPhase::network_probe: return "network_probe";
            default: return "idle";
        }
    }
    const BlackBoxRecord& previous() const { return previous_; }
    SupervisorPolicy::Reason previousRestart() const { return static_cast<SupervisorPolicy::Reason>(previousReason_); }
private:
    static uint32_t checksum(const BlackBoxRecord& r) {
        BlackBoxRecord copy = r;
        copy.check = 0;
        uint32_t sum = 2166136261u; // FNV-1a over the record without its check
        const auto* bytes = reinterpret_cast<const uint8_t*>(&copy);
        for (size_t i = 0; i < sizeof(copy); ++i) sum = (sum ^ bytes[i]) * 16777619u;
        return sum;
    }
    void seal() { current_->magic = magic; current_->check = checksum(*current_); }
    BlackBoxRecord* current_ = nullptr;
    LoopPhaseRecord* phase_ = nullptr;
    LoopPhase previousPhase_ = LoopPhase::idle;
    BlackBoxRecord previous_{};
    int resetReason_ = 0;
    uint8_t previousReason_ = 0;
    uint32_t requests_ = 0;
    bool havePrevious_ = false;
};
inline BlackBox blackBox;
}
