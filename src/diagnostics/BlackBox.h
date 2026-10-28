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
};
// Which part of the main loop runs, written several times per iteration, so it
// is kept outside the checksummed record: one byte behind its own magic.
enum class LoopPhase : uint8_t { idle, update, network, controller, ems, http, telemetry };
struct LoopPhaseRecord { uint32_t magic; volatile uint8_t phase; };

class BlackBox {
public:
    static constexpr uint32_t magic = 0x4F54424Bu; // "OTBK"
    // At boot: keep a valid record as the previous boot, then start a new one.
    void begin(BlackBoxRecord& current, LoopPhaseRecord& phase, int resetReason) {
        current_ = &current; phase_ = &phase;
        resetReason_ = resetReason;
        havePrevious_ = current.magic == magic && current.check == checksum(current);
        if (havePrevious_) previous_ = current;
        previousPhase_ = phase.magic == magic ? static_cast<LoopPhase>(phase.phase) : LoopPhase::idle;
        std::memset(&current, 0, sizeof(current));
        seal();
        phase.magic = magic; phase.phase = 0;
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
        if (!current_ || !path) return;
        std::strncpy(current_->lastRequest, path, sizeof(current_->lastRequest) - 1);
        current_->lastRequest[sizeof(current_->lastRequest) - 1] = 0;
        seal();
    }
    void restartReason(SupervisorPolicy::Reason reason) {
        if (!current_) return;
        current_->reason = static_cast<uint8_t>(reason);
        seal();
    }
    // {"reset_reason":n,"previous":{...}|null}
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON_AddNumberToObject(root, "reset_reason", resetReason_);
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
            SupervisorPolicy::name(static_cast<SupervisorPolicy::Reason>(r.reason)));
        char path[sizeof(r.lastRequest)];
        std::memcpy(path, r.lastRequest, sizeof(path));
        path[sizeof(path) - 1] = 0;
        cJSON_AddStringToObject(p, "last_request", path);
        cJSON_AddStringToObject(p, "loop_phase", phaseName(previousPhase_));
        return root;
    }
    bool havePrevious() const { return havePrevious_; }
    LoopPhase previousPhase() const { return previousPhase_; }
    static const char* phaseName(LoopPhase p) {
        switch (p) {
            case LoopPhase::update: return "update";
            case LoopPhase::network: return "network";
            case LoopPhase::controller: return "controller";
            case LoopPhase::ems: return "ems_and_bluetooth";
            case LoopPhase::http: return "http";
            case LoopPhase::telemetry: return "telemetry";
            default: return "idle";
        }
    }
    const BlackBoxRecord& previous() const { return previous_; }
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
    bool havePrevious_ = false;
};
inline BlackBox blackBox;
}
