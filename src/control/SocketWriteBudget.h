#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::control {
// Ordinary MQTT IO on the existing socket. This is a latency bound, not an
// actuator deadline, freshness proof or retry queue. Send must be nonblocking.
struct SocketWriteBudget {
    static constexpr uint64_t maximumMs=100;
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
}
