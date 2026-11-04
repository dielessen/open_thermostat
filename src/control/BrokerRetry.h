#pragma once
#include <cstdint>

namespace heating::control {
// MQTT broker reconnect pacing (review R2-09). Before rc.4 every failed DNS, TCP or MQTT CONNECT
// step tried again after a fixed 5 s, forever: about 17 000 attempts a day while the broker was
// down or refused the login, each with up to 1 s of CONNACK wait. Now each attempt waits 5 s,
// then 10, 20, 40 and from then on 60 s, each within +-20 % (so several devices do not retry in
// step); a session that lasted stableMs starts again at 5 s. A session that drops sooner (a
// broker that accepts and closes at once) keeps the longer wait.
class BrokerRetry {
public:
    static constexpr uint32_t firstMs = 5000, maximumMs = 60000, stableMs = 60000;
    // An attempt starts or fails at `now`: the earliest next attempt. random: any 32-bit value.
    uint64_t next(uint64_t now, uint32_t random) {
        const uint32_t wait = waitMs_, span = wait / 5; // +-20 %
        waitMs_ = wait >= maximumMs / 2 ? maximumMs : wait * 2;
        return now + (wait - span) + (span ? random % (2 * span + 1) : 0);
    }
    void connected(uint64_t now) { connectedAt_ = now; session_ = true; }
    void disconnected(uint64_t now) {
        if (session_ && now >= connectedAt_ && now - connectedAt_ >= stableMs) waitMs_ = firstMs;
        session_ = false;
    }
    uint32_t waitMs() const { return waitMs_; } // the wait the next attempt sets (before jitter)

private:
    uint32_t waitMs_ = firstMs;
    uint64_t connectedAt_ = 0;
    bool session_ = false;
};
}
