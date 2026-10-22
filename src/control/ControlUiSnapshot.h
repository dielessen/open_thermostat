#pragma once
#include <array>
#include <algorithm>
#include <cstdint>
#include <mutex>
#include <ostream>
#include <string_view>

namespace heating::control {
// A view of the SAME owner's outbound state, never input/admission or storage.
// Fixed 4 KiB budget; missing/stale/oversize observations affect only the UI.
class ControlUiSnapshot {
public:
    static constexpr size_t maximumBytes=4096;
    static constexpr uint64_t maximumAgeMs=5000;

    bool capture(std::string_view suffix,std::string_view bytes,uint64_t now) {
        if(suffix!="fw/state/zones")return false;
        std::lock_guard<std::mutex> lock(mutex_);
        size_=0;
        if(bytes.size()>maximumBytes) {reason_="snapshot_too_large";return false;}
        if(bytes.size()<2||bytes.front()!='{'||bytes.back()!='}'||bytes.find('\0')!=std::string_view::npos) {
            reason_="invalid_snapshot";return false;
        }
        std::copy(bytes.begin(),bytes.end(),bytes_.begin());
        size_=bytes.size();at_=now;reason_="fresh";
        return true;
    }

    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        size_=0;reason_="no_snapshot";
    }

    void write(std::ostream& out,uint64_t now,bool connected) const {
        std::lock_guard<std::mutex> lock(mutex_);
        const bool ageKnown=size_&&now>=at_;
        const bool fresh=connected&&ageKnown&&now-at_<maximumAgeMs;
        const char* reason=!connected?"source_disconnected":!size_?reason_:
            !ageKnown?"clock_reset":!fresh?"stale":"fresh";
        out<<"{\"available\":"<<(size_?"true":"false")<<",\"fresh\":"<<(fresh?"true":"false")
           <<",\"reason\":\""<<reason<<"\",\"age_ms\":";
        if(ageKnown)out<<now-at_;else out<<"null";
        out<<",\"captured_at_ms\":";
        if(size_)out<<at_;else out<<"null";
        out<<",\"state\":";
        if(fresh)out.write(bytes_.data(),size_);else out<<"null";
        out<<'}';
    }
private:
    mutable std::mutex mutex_;
    std::array<char,maximumBytes> bytes_{};
    size_t size_=0;
    uint64_t at_=0;
    const char* reason_="no_snapshot";
};
static_assert(sizeof(ControlUiSnapshot)<=4200,"UI state must remain within its fixed budget");
}
