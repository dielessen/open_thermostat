#pragma once
#include <atomic>
#include <cstdint>

namespace heating::update {
inline bool manualRebootAllowed(bool busy,bool pendingBoot) {
    // Do not interrupt an OTA flash, scheduled restart or unconfirmed new boot.
    return !busy && !pendingBoot;
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
