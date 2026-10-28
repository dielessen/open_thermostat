#pragma once
#include <cstdint>

namespace heating::update {
// Volatile cache only: no periodic flash writes. All intervals are shorter
// than half the millis() range; unsigned subtraction tolerates rollover.
class ReleaseCheckSchedule {
public:
    static constexpr uint32_t initialDelayMs=5u*60*1000;
    static constexpr uint32_t intervalMs=12u*60*60*1000;
    static constexpr uint32_t failureRetryMs=30u*60*1000;
    static constexpr uint32_t cacheMs=5u*60*1000;
    // Consecutive failures back off (30 min, 1 h, 2 h ... at most 12 h): each
    // failed native TLS attempt costs internal heap, and a lasting fault
    // should not repeat every half hour. A success restores the normal cadence.
    uint32_t retryMs() const {
        uint32_t retry=failureRetryMs;
        for(uint32_t i=1;i<failures_&&retry<intervalMs;++i)retry*=2;
        return retry<intervalMs?retry:intervalMs;
    }
    bool due(uint32_t now,bool allowed) const {
        return allowed&&(attempted_?uint32_t(now-attempt_)>=(lastSucceeded_?intervalMs:retryMs()):now>=initialDelayMs);
    }
    void attempted(uint32_t now){attempted_=true;attempt_=now;lastSucceeded_=false;}
    void completed(uint32_t now,bool success){
        lastSucceeded_=success;
        if(success){cached_=true;success_=now;failures_=0;}
        else if(failures_<32)++failures_;
    }
    bool cached(uint32_t now) const{return cached_&&lastSucceeded_&&uint32_t(now-success_)<cacheMs;}
    bool known() const{return cached_;}
    uint32_t age(uint32_t now) const{return uint32_t(now-success_);}
private:
    bool attempted_=false,cached_=false,lastSucceeded_=false;
    uint32_t attempt_=0,success_=0,failures_=0;
};
}
