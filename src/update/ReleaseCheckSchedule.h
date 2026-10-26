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
    bool due(uint32_t now,bool allowed) const {
        return allowed&&(attempted_?uint32_t(now-attempt_)>=(lastSucceeded_?intervalMs:failureRetryMs):now>=initialDelayMs);
    }
    void attempted(uint32_t now){attempted_=true;attempt_=now;lastSucceeded_=false;}
    void completed(uint32_t now,bool success){lastSucceeded_=success;if(success){cached_=true;success_=now;}}
    bool cached(uint32_t now) const{return cached_&&lastSucceeded_&&uint32_t(now-success_)<cacheMs;}
    bool known() const{return cached_;}
    uint32_t age(uint32_t now) const{return uint32_t(now-success_);}
private:
    bool attempted_=false,cached_=false,lastSucceeded_=false;
    uint32_t attempt_=0,success_=0;
};
}
