#pragma once
#include <cstdint>
namespace heating::diagnostics {
// Wi-Fi station reconnect pacing for the loop's 10 s health pass. The SDK
// already reconnects on its own after a disconnect; an extra WiFi.reconnect()
// every 10 s aborted connects in progress. After the link is first seen down:
// reconnect after 10 s, then 20 s, 40 s and from then on every 60 s.
class ReconnectBackoff {
public:
    static constexpr uint32_t firstMs = 10000, maximumMs = 60000;
    // connected: true while linked (or not in station mode). True = reconnect now.
    bool due(uint64_t now, bool connected) {
        if (connected) { down_ = false; waitMs_ = firstMs; return false; }
        if (!down_) { down_ = true; waitMs_ = firstMs; nextAt_ = now + firstMs; return false; }
        if (now < nextAt_) return false;
        waitMs_ = waitMs_ * 2 > maximumMs ? maximumMs : waitMs_ * 2;
        nextAt_ = now + waitMs_;
        return true;
    }
private:
    uint64_t nextAt_ = 0;
    uint32_t waitMs_ = firstMs;
    bool down_ = false;
};
}
