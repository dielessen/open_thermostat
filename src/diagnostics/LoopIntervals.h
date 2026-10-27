#pragma once
#include <algorithm>
#include <cstdint>
#include <limits>
#include <memory>
#include <cJSON.h>

namespace heating::diagnostics {
// Observation only, owned/read on the serialized product/HTTP loop. Reuses its
// existing millis() value: no new clock reads, tasks, locks, history or IO.
// Intervals include scheduler/network/HTTP delays, not just CPU execution time.
class LoopIntervals {
public:
    static constexpr uint32_t windowTargetMs=60000;
    struct Snapshot {
        uint32_t samples=0,lastMs=0,maximumMs=0,atMs=0;
        uint32_t ge100Ms=0,ge500Ms=0,ge1000Ms=0;
        uint32_t windowMs=0,windowSamples=0,windowMaximumMs=0;
    };
    void observe(uint32_t now) {
        if(!initialized_) {initialized_=true;previous_=windowAt_=now;return;}
        const uint32_t interval=now-previous_; // Same unsigned millis rollover.
        previous_=now;
        if(uint32_t(now-windowAt_)>=windowTargetMs) {
            windowAt_=now;snapshot_.windowSamples=0;snapshot_.windowMaximumMs=0;
        }
        increment(snapshot_.samples);increment(snapshot_.windowSamples);
        snapshot_.lastMs=interval;snapshot_.maximumMs=std::max(snapshot_.maximumMs,interval);
        snapshot_.windowMaximumMs=std::max(snapshot_.windowMaximumMs,interval);
        snapshot_.atMs=now;snapshot_.windowMs=now-windowAt_;
        if(interval>=100)increment(snapshot_.ge100Ms);
        if(interval>=500)increment(snapshot_.ge500Ms);
        if(interval>=1000)increment(snapshot_.ge1000Ms);
    }
    Snapshot snapshot()const{return snapshot_;}
    using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
    Json json()const {
        Json result(cJSON_CreateObject(),cJSON_Delete);
        if(!result)return result;
        const auto& s=snapshot_;
        const auto number=[&](const char* name,uint32_t value){return cJSON_AddNumberToObject(result.get(),name,value)!=nullptr;};
        const auto optional=[&](const char* name,uint32_t value){return s.samples?number(name,value):cJSON_AddNullToObject(result.get(),name)!=nullptr;};
        if(!number("schema",1)||!number("samples",s.samples)
           ||!optional("sampled_at_ms",s.atMs)||!optional("last_ms",s.lastMs)||!optional("maximum_ms",s.maximumMs)
           ||!number("intervals_ge_100_ms",s.ge100Ms)||!number("intervals_ge_500_ms",s.ge500Ms)||!number("intervals_ge_1000_ms",s.ge1000Ms)
           ||!number("window_ms",s.windowMs)||!number("window_samples",s.windowSamples)||!optional("window_maximum_ms",s.windowMaximumMs))
            return Json(nullptr,cJSON_Delete);
        return result;
    }
private:
    static void increment(uint32_t& value){if(value<std::numeric_limits<uint32_t>::max())++value;}
    Snapshot snapshot_{};
    uint32_t previous_=0,windowAt_=0;
    bool initialized_=false;
};
static_assert(sizeof(LoopIntervals)<=64,"Main-loop observation must remain bounded");
inline LoopIntervals loopIntervals;
}
