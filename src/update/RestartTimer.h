#pragma once
#include <atomic>
#include <cstdint>

namespace heating::update {
inline bool manualRebootAllowed(bool busy,bool pendingBoot) {
    // Do not interrupt an OTA flash, scheduled restart or unconfirmed new boot.
    return !busy && !pendingBoot;
}
// A new image confirms itself (esp_ota_mark_app_valid_cancel_rollback) once
// it has run normally for healthyMs: the main loop calls this, and the
// supervisor task (restart and RTC watchdog) is alive. Deliberately NOT tied
// to Wi-Fi, MQTT, Home Assistant or the filesystem: a healthy device in a
// network outage is never rolled back. A crash, watchdog or supervisor reset
// before then boots the previous image (bootloader rollback); so does a loop
// without a supervisor after supervisorMissingMs.
struct BootConfirmation {
    static constexpr uint32_t healthyMs = 60000, supervisorMissingMs = 180000;
    enum class Action { wait, confirm, rollback };
    static Action decide(uint32_t uptimeMs, bool supervisorAlive) {
        if (uptimeMs >= healthyMs && supervisorAlive) return Action::confirm;
        return uptimeMs >= supervisorMissingMs ? Action::rollback : Action::wait;
    }
};
// An optional restart (e.g. to apply saved Bluetooth settings) waits for: no
// update or other restart, a confirmed boot (a restart while the image is
// still pending would roll it back) and no boiler trial/settings session.
inline bool controlledRestartAllowed(bool busy, bool pendingBoot, bool sessionActive) {
    return !busy && !pendingBoot && !sessionActive;
}
// Shared by the OTA worker and HTTP/main loop. First request wins: polling or
// duplicate completion cannot postpone a restart. Zero denotes an unarmed timer.
class RestartTimer {
    std::atomic<uint32_t> deadline_{0};
public:
    void schedule(uint32_t now,uint32_t grace=3000) {
        uint32_t empty=0,target=now+grace;
        deadline_.compare_exchange_strong(empty,target?target:1);
    }
    bool pending() const {return deadline_.load()!=0;}
    bool due(uint32_t now,bool writing) const {
        const auto deadline=deadline_.load();
        return deadline&&!writing&&int32_t(now-deadline)>=0;
    }
};
}
