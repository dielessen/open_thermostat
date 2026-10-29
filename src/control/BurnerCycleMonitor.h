#pragma once
#include "EMS/ClassicBoilerMonitor.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <optional>
#include <ostream>

namespace heating::control {
// Short-cycling detector over observed burner reports (pure, boot-local,
// observation only, never a control input). Starts are off->on edges, runs
// on->off. Space heating short-cycles when, in the last hour, it started
// >= 6 times, or >= 3 of its measured runs had a median below 5 min. DHW runs
// are counted but never flag: a tap draw is short by nature (the EcomLine
// logs show ~1 min DHW burns every 10-20 min). A report gap > 60 s (0x18
// comes every ~10 s) makes the current run length unknown: it still counts as
// a start, never as a short run. Older (reordered) reports are ignored.
class BurnerCycleMonitor {
public:
    static constexpr uint64_t windowMs=3600000,gapMs=60000,shortRunMs=300000;
    static constexpr size_t shortCycleStarts=6,medianRuns=3,capacity=24; // starts saturate at capacity
    struct Summary {
        size_t starts=0,heatingStarts=0;
        std::optional<uint64_t> medianHeatingRunMs;
        uint64_t observedMs=0; // part of the window covered by reports
        bool shortCycling=false,known=false;
    };
    void observe(bool on,bool dhw,uint64_t now) {
        if(have_&&now<last_)return;
        const bool gap=have_&&now-last_>gapMs;
        if(!have_)first_=now;
        else if(on&&!on_) {
            runs_[next_]={now,0,dhw,false};next_=(next_+1)%capacity;used_=std::min(used_+1,capacity);
            measured_=!gap;if(starts_!=UINT32_MAX)++starts_;
        } else if(on_&&used_) {
            auto& run=runs_[(next_+capacity-1)%capacity];
            if(on)run.dhw|=dhw;
            else if(measured_&&!gap){run.runMs=now-run.startMs;run.closed=true;}
        }
        if(gap){measured_=false;first_=now;}
        have_=true;on_=on;last_=now;
    }
    // Classic: the boiler-reported state of UBAMonitorFast (0x18 offset 5:
    // bit 3 flame, bit 1 DHW), only when this report carried it.
    void observe(const ems::ClassicBoilerMonitor& monitor,uint64_t now) {
        const auto& s=monitor.sample(ems::BoilerField::rawState);
        if(s.observed&&s.observedMs==now&&s.sourceType==0x18&&s.raw)observe(*s.raw&0x08,*s.raw&0x02,now);
    }
    Summary summary(uint64_t now) const {
        Summary r;
        if(!have_||now<last_||now-last_>gapMs)return r; // stale: unknown, never "not cycling"
        r.known=true;r.observedMs=std::min(windowMs,now-first_);
        std::array<uint64_t,capacity> lengths{};size_t n=0;
        for(size_t i=0;i<used_;++i) {
            const auto& run=runs_[i];
            if(now-run.startMs>=windowMs)continue;
            ++r.starts;
            if(run.dhw)continue;
            ++r.heatingStarts;
            if(run.closed)lengths[n++]=run.runMs;
        }
        if(n>=medianRuns) {
            std::nth_element(lengths.begin(),lengths.begin()+n/2,lengths.begin()+n);
            r.medianHeatingRunMs=lengths[n/2];
        }
        r.shortCycling=r.heatingStarts>=shortCycleStarts||(r.medianHeatingRunMs&&*r.medianHeatingRunMs<shortRunMs);
        return r;
    }
    uint32_t observedStarts() const { return starts_; } // boot-local lifetime count
    void writeJSON(std::ostream& out,uint64_t now) const {
        const auto s=summary(now);
        out<<"{\"known\":"<<(s.known?"true":"false")<<",\"short_cycling\":"<<(s.shortCycling?"true":"false")
           <<",\"starts_last_hour\":"<<s.starts<<",\"heating_starts_last_hour\":"<<s.heatingStarts
           <<",\"median_heating_run_s\":";
        if(s.medianHeatingRunMs)out<<*s.medianHeatingRunMs/1000;else out<<"null";
        out<<",\"observed_window_s\":"<<s.observedMs/1000<<",\"observed_starts\":"<<starts_<<'}';
    }
private:
    struct Run { uint64_t startMs; uint64_t runMs; bool dhw,closed; };
    std::array<Run,capacity> runs_{};
    size_t next_=0,used_=0;
    uint64_t first_=0,last_=0;
    uint32_t starts_=0;
    bool have_=false,on_=false,measured_=false;
};
}
