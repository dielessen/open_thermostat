#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace heating::control {
// Ordinary MQTT IO on the existing socket. This is a latency bound, not an
// actuator deadline, freshness proof or retry queue. Send must be nonblocking.
// 300 ms (was 100): a heating status of a few KB over a weak Wi-Fi link
// regularly needed longer, and every overrun disconnects the MQTT session.
struct SocketWriteBudget {
    static constexpr uint64_t maximumMs=300;
    static constexpr unsigned maximumCalls=256;
    struct Result {size_t written=0;bool complete=false;};

    template<class Clock,class Send,class Wait>
    static Result write(const uint8_t* bytes,size_t size,Clock&& clock,Send&& send,Wait&& wait) {
        Result result;
        if(!bytes||!size)return result;
        const uint64_t started=clock();uint64_t last=started;
        for(unsigned calls=0;calls<maximumCalls;++calls) {
            auto now=clock();
            if(now<last||now-started>=maximumMs)return result;
            last=now;
            const auto count=send(bytes+result.written,size-result.written);
            if(count<0||static_cast<size_t>(count)>size-result.written)return result;
            result.written+=static_cast<size_t>(count);
            now=clock();
            if(now<last||now-started>=maximumMs)return result;
            last=now;
            if(result.written==size){result.complete=true;return result;}
            if(count==0)wait(); // Yield once; keep the ORIGINAL total budget.
        }
        return result; // A stuck clock cannot turn backpressure into a busy loop.
    }
};
// MQTT sessions closed because an ordinary write overran the budget (/status/logs).
inline std::atomic<uint32_t> socketBudgetDisconnects{0};
}
