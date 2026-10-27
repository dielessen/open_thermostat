#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <string_view>

namespace heating::diagnostics {
struct Settings {
    bool enabled = false;
    bool syslogEsp = true, syslogEms = false;
    std::array<char,16> server{};
    uint16_t port = 514;
    uint8_t syslogLevel = 3, webLevel = 3;
    uint32_t markSeconds = 0;
};
inline bool ipv4(std::string_view text) {
    unsigned parts[4]{}, index=0, digits=0;
    for (char c:text) {
        if (c=='.') { if(!digits || index==3) return false; ++index; digits=0; }
        else if(c>='0'&&c<='9') { if(digits==1&&parts[index]==0)return false; if(++digits>3) return false; parts[index]=parts[index]*10+unsigned(c-'0'); if(parts[index]>255)return false; }
        else return false;
    }
    return index==3 && digits && parts[0]>0 && parts[0]<224;
}
inline bool valid(const Settings& s) {
    const auto end=std::find(s.server.begin(),s.server.end(),'\0');
    if(end==s.server.end() || !s.port || s.webLevel>5 || s.syslogLevel>5 || s.markSeconds>86400) return false;
    const std::string_view host(s.server.data(),size_t(end-s.server.begin()));
    return (host.empty() ? !s.enabled : ipv4(host));
}
enum class Source : uint8_t { esp, ems };
inline const char* sourceName(Source source) { return source == Source::ems ? "ems" : "esp"; }
inline Source sourceForFeature(std::string_view feature) {
    return feature.substr(0,3)=="EMS" || feature.substr(0,3)=="Ems" ? Source::ems : Source::esp;
}
struct Record {
    Source source=Source::esp;
    uint64_t sequence=0, uptimeMs=0;
    uint8_t level=0;
    std::array<char,17> feature{};
    std::array<char,193> text{};
};
struct Stats {
    uint64_t latest=0, oldest=0, overwritten=0, truncated=0, redacted=0;
    uint64_t syslogDropped=0, sent=0, contention=0;
    size_t retained=0, pending=0;
};
// One normalization for redaction and both output sinks. Inspect the complete
// input before the visible record is shortened; never allocate in the log hook.
template<class Sink>
inline void visibleLogCharacters(std::string_view text, Sink sink) {
    bool escaped=false;
    for(char c:text) {
        if(c==27){escaped=true;continue;}
        if(escaped){if(c>='@'&&c<='~'&&c!='[')escaped=false;continue;}
        if(!sink((c>=32&&c<=126)?c:' '))return;
    }
}
inline bool sensitive(std::string_view text) {
    // Whole-message suppression: include labels separated by terminal formatting.
    constexpr std::string_view keys[]={"password","passwd","authorization","cookie","csrf","token","secret","ssid","username","payload","credential","bearer","api_key","apikey","body","://","{", "networkconfig", "mqttconfig"};
    const auto lower=[](char c){return c>='A'&&c<='Z'?char(c+32):c;};
    for(auto key:keys) {
        if(key.size()>text.size())continue;
        for(size_t i=0;i+key.size()<=text.size();++i)
            if(std::equal(key.begin(),key.end(),text.begin()+i,[&](char a,char b){return a==lower(b);}))return true;
    }
    std::array<char,16> tail{};size_t used=0;bool found=false;
    visibleLogCharacters(text,[&](char c){
        if(used==tail.size()) {std::move(tail.begin()+1,tail.end(),tail.begin());--used;}
        tail[used++]=lower(c);
        for(auto key:keys) {
            if(key.size()<=used&&std::equal(key.begin(),key.end(),tail.begin()+used-key.size())) {
                found=true;return false;
            }
        }
        return true;
    });
    return found;
}

class SystemLog {
public:
    static constexpr size_t Capacity=32, QueueCapacity=8, PageSize=8;
    void configure(const Settings& settings) {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_=settings;
        stats_.syslogDropped+=queued_;
        queued_=0; head_=0;
        // Read-only preflight for lazy message formatting. append() still owns
        // admission, redaction, contention accounting and the actual queues.
        uint32_t mask=settings.enabled?syslogEnabledMask:0;
        for(unsigned level=1;level<=5;++level) {
            if(level<=settings.webLevel)mask|=(1u<<level)|(1u<<(level+8));
            if(settings.enabled&&level<=settings.syslogLevel) {
                if(settings.syslogEsp)mask|=1u<<level;
                if(settings.syslogEms)mask|=1u<<(level+8);
            }
        }
        captureMask_.store(mask,std::memory_order_release);
    }
    // Diagnostic preflight only. Queue admission/destination still use the
    // original locked settings; this flag never grants a physical command.
    bool syslogEnabled() const {return captureMask_.load(std::memory_order_acquire)&syslogEnabledMask;}
    bool wantsLevel(uint8_t level) const {
        return level>=1&&level<=5&&
            (captureMask_.load(std::memory_order_acquire)&((1u<<level)|(1u<<(level+8))));
    }
    bool wants(uint8_t level,std::string_view feature) const {
        return level>=1&&level<=5&&
            (captureMask_.load(std::memory_order_acquire)&(1u<<(level+(sourceForFeature(feature)==Source::ems?8:0))));
    }
    Settings settings() const { std::lock_guard<std::mutex> lock(mutex_); return settings_; }
    void append(uint8_t level,std::string_view feature,std::string_view text,uint64_t uptime,bool truncated=false) {
        if(!level || level>5) return;
        std::unique_lock<std::mutex> lock(mutex_,std::try_to_lock);
        if(!lock.owns_lock()) { ++contention_; return; }
        const auto source=sourceForFeature(feature);
        const bool web=level<=settings_.webLevel;
        const bool remote=settings_.enabled&&level<=settings_.syslogLevel
            &&(source==Source::ems?settings_.syslogEms:settings_.syslogEsp);
        if(!web&&!remote) return;
        Record record; record.source=source;record.sequence=++stats_.latest;record.uptimeMs=uptime;record.level=level;
        const bool redact=truncated||sensitive(text)||sensitive(feature);
        if(redact) { text="[sensitive log content omitted]";feature="Log";++stats_.redacted; }
        auto copy=[](auto& dest,std::string_view source) {
            size_t n=0;
            visibleLogCharacters(source,[&](char c){
                if(n+1==dest.size())return false;
                dest[n++]=c;return true;
            });
            while(n&&dest[n-1]==' ')--n;
            dest[n]='\0';
        };
        if(truncated || text.size()>=record.text.size()) ++stats_.truncated;
        copy(record.feature,feature);copy(record.text,text);
        if(web) {
            if(count_==Capacity) { start_=(start_+1)%Capacity;--count_;++stats_.overwritten; }
            records_[(start_+count_++)%Capacity]=record;
        }
        if(remote) {
            if(!connected_)++stats_.syslogDropped;
            else if(queued_==QueueCapacity)++stats_.syslogDropped;
            else queue_[(head_+queued_++)%QueueCapacity]=record;
        }
    }
    bool next(uint64_t after,Record& out) const {
        std::lock_guard<std::mutex> lock(mutex_);
        for(size_t i=0;i<count_;++i) {const auto& r=records_[(start_+i)%Capacity];if(r.sequence>after){out=r;return true;}}
        return false;
    }
    bool pop(Record& out,Settings& settings) {
        std::lock_guard<std::mutex> lock(mutex_);
        if(!queued_)return false;
        out=queue_[head_];head_=(head_+1)%QueueCapacity;--queued_;settings=settings_;return true;
    }
    void online() {std::lock_guard<std::mutex> lock(mutex_);connected_=true;}
    void offline() {std::lock_guard<std::mutex> lock(mutex_);connected_=false;stats_.syslogDropped+=queued_;queued_=0;head_=0;}
    void noteContention(){++contention_;}
    void sent(bool success) {std::lock_guard<std::mutex> lock(mutex_);if(success)++stats_.sent;else ++stats_.syslogDropped;}
    void clear() {std::lock_guard<std::mutex> lock(mutex_);start_=count_=0;}
    Stats stats() const {
        std::lock_guard<std::mutex> lock(mutex_);auto s=stats_;s.retained=count_;s.pending=queued_;
        s.oldest=count_?records_[start_].sequence:0;s.contention=contention_.load();return s;
    }
private:
    static constexpr uint32_t syslogEnabledMask=1u<<16;
    // Defaults match Settings{} even before configure().
    std::atomic<uint32_t> captureMask_{0x0e0e};
    mutable std::mutex mutex_;
    Settings settings_;
    bool connected_=true; // Standalone core tests inject availability; firmware begins offline.
    std::array<Record,Capacity> records_{};
    std::array<Record,QueueCapacity> queue_{};
    size_t start_=0,count_=0,head_=0,queued_=0;
    Stats stats_;
    std::atomic<uint32_t> contention_{0};
};
inline std::string rfc5424(const Record& record,std::string_view hostname) {
    char host[65]{};size_t n=0;
    for(char c:hostname) {if(n==64)break;host[n++]=(c>32&&c<127)?c:'_';}
    if(!n)std::strcpy(host,"openthermostat");
    const unsigned severity=record.level==1?3:record.level==2?4:record.level==3?6:7;
    char message[512]{};
    std::snprintf(message,sizeof(message),"<%u>1 - %s openthermostat - - - uptime_ms=%llu seq=%llu source=%s [%s] %s",
        16*8+severity,host,(unsigned long long)record.uptimeMs,(unsigned long long)record.sequence,sourceName(record.source),record.feature.data(),record.text.data());
    return message;
}
} // namespace heating::diagnostics
