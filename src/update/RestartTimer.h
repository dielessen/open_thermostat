#pragma once
#include <atomic>
#include <cstdint>
#include <mutex>

namespace heating::update {
inline bool manualRebootAllowed(bool busy,bool pendingBoot) {
    // Do not interrupt an OTA flash, scheduled restart or unconfirmed new boot.
    return !busy && !pendingBoot;
}
// A new image confirms itself (esp_ota_mark_app_valid_cancel_rollback) once
// it has run normally for healthyMs: the main loop calls this, the supervisor
// task (restart and RTC watchdog) is alive, and the network worked once since
// boot. A pending image always follows a network update, so an image whose
// network never comes up is not kept: proof is an IP address plus one of an
// accepted HTTP request, an MQTT session or a gateway probe reply (never Home
// Assistant in particular); without a configured MQTT broker also the IP and
// link held for linkProofMs (an Ethernet install nobody opens, behind a
// gateway that ignores ping). Without that proof by networkProofMs the device
// restarts, and the bootloader boots the previous image; so does a crash,
// watchdog or supervisor reset before confirmation, or a loop without a
// supervisor after supervisorMissingMs. A failed confirmation is retried every
// retryMs, not on every loop pass.
struct BootConfirmation {
    static constexpr uint32_t healthyMs = 60000, supervisorMissingMs = 180000, networkProofMs = 600000, retryMs = 60000;
    static constexpr uint32_t linkProofMs = 300000;
    // evidence: a gateway reply, an MQTT session or an HTTP request this boot;
    // linkUpMs: how long the network has held an IP without a break (0: none).
    // A network lost after the update never proves itself and still rolls back.
    static bool networkProven(bool evidence, bool brokerConfigured, uint32_t linkUpMs) {
        return evidence || (!brokerConfigured && linkUpMs >= linkProofMs);
    }
    enum class Action { wait, confirm, rollback };
    static Action decide(uint32_t uptimeMs, bool supervisorAlive, bool networkProven) {
        if (uptimeMs >= healthyMs && supervisorAlive && networkProven) return Action::confirm;
        if (uptimeMs >= supervisorMissingMs && !supervisorAlive) return Action::rollback;
        return uptimeMs >= networkProofMs ? Action::rollback : Action::wait;
    }
    // lastAttemptMs: uptime of the previous failed attempt, 0 = none yet.
    static bool attemptDue(uint32_t uptimeMs, uint32_t lastAttemptMs) {
        return !lastAttemptMs || uptimeMs - lastAttemptMs >= retryMs;
    }
};
// An optional restart (e.g. to apply saved Bluetooth settings) waits for: no
// update or other restart, a confirmed boot (a restart while the image is
// still pending would roll it back) and no boiler trial/settings session.
inline bool controlledRestartAllowed(bool busy, bool pendingBoot, bool sessionActive) {
    return !busy && !pendingBoot && !sessionActive;
}
// Shared by the OTA worker and HTTP/main loop. The EARLIEST requested deadline
// wins: polling, a duplicate completion or a slower request can never
// postpone a pending restart. Zero denotes an unarmed timer. Deadlines are
// millis(); "earlier" is rollover-safe within 24 days.
inline bool earlierDeadline(uint32_t target,uint32_t current) {return !current||int32_t(target-current)<0;}
class RestartTimer {
    std::atomic<uint32_t> deadline_{0};
public:
    void schedule(uint32_t now,uint32_t grace=3000) {
        uint32_t target=now+grace;if(!target)target=1;
        uint32_t current=deadline_.load();
        while(earlierDeadline(target,current)&&!deadline_.compare_exchange_weak(current,target)) {}
    }
    bool pending() const {return deadline_.load()!=0;}
    bool due(uint32_t now,bool writing) const {
        const auto deadline=deadline_.load();
        return deadline&&!writing&&int32_t(now-deadline)>=0;
    }
};
// The controlled (optional) restart: the earliest deadline together with the
// reason that asked for it, so a later request neither delays it nor puts its
// own reason in the black box.
class ReasonedRestartTimer {
    mutable std::mutex mutex_;
    uint32_t deadline_=0;
    uint8_t reason_=0;
public:
    void schedule(uint32_t now,uint32_t grace,uint8_t reason) {
        uint32_t target=now+grace;if(!target)target=1;
        std::lock_guard<std::mutex> lock(mutex_);
        if(earlierDeadline(target,deadline_)) {deadline_=target;reason_=reason;}
    }
    bool pending() const {std::lock_guard<std::mutex> lock(mutex_);return deadline_!=0;}
    bool due(uint32_t now,bool writing) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return deadline_&&!writing&&int32_t(now-deadline_)>=0;
    }
    uint8_t reason() const {std::lock_guard<std::mutex> lock(mutex_);return reason_;}
};
}
