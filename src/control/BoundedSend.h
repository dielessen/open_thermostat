#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::control {
// One HTTP response write with an end (review R2-02). The pinned WiFiClient::write waits up to
// 1 s in select() per attempt, 10 attempts, and starts counting again after any progress: a
// client that stops reading (a phone at the edge of Wi-Fi, a host that never reads) held the
// loop task, and with it the heating step, MQTT and the EMS decode, for as long as it liked.
// write() offers the bytes to a non-blocking send and gives up once the client took nothing for
// stallMs, or once the response (all its writes, counted from `start`) took totalMs.
//   send(data, size): bytes taken (> 0), 0 = the send buffer is full (try again), < 0 = failed;
//   now(): monotonic ms (32-bit, may wrap); wait(): a short pause that lets the network stack run.
struct BoundedSend {
    static constexpr uint32_t stallMs = 2000, totalMs = 10000;
    struct Result { size_t sent = 0; bool complete = false; };
    template<class Send, class Now, class Wait>
    static Result write(const uint8_t *data, size_t size, uint32_t start, Send &&send, Now &&now, Wait &&wait) {
        Result r;
        if (!size) { r.complete = true; return r; }
        if (!data) return r;
        uint32_t progress = now();
        while (r.sent < size) {
            const uint32_t t = now();
            if (uint32_t(t - start) >= totalMs || uint32_t(t - progress) >= stallMs) return r;
            const auto n = send(data + r.sent, size - r.sent);
            if (n < 0) return r;
            if (n == 0) { wait(); continue; }
            const size_t left = size - r.sent;
            r.sent += size_t(n) < left ? size_t(n) : left;
            progress = now();
        }
        r.complete = true;
        return r;
    }
};
}
