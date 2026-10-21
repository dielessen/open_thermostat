#pragma once
#include "ControlStore.h"
#include "ThermalCoastModel.h"
#include <functional>
#include <string>
#include <string_view>

namespace heating::control {
// SOURCE ONLY: caller must provide a separately budgeted, owner-bound atomic key,
// never the configuration key. No active factory/NVS allocation is added here.
// Hash is the existing production SHA256-hex contract, NOT a signature/MAC.
class CoastModelStore {
public:
    using Hash=std::function<std::string(std::string_view)>;
    static constexpr size_t maximumBytes=554;
    static constexpr uint64_t minimumCheckpointMs=1800000;
    CoastModelStore(ControlStore& store,Hash hash):store_(store),hash_(std::move(hash)) {}
    bool load(ThermalCoastModel& model) {
        if (loaded_ || fault_) return false;
        if (!hash_ || !validHash(hash_("")) || !store_.load(durable_)) return fail(model);
        if (!durable_.empty()) {
            CoastSnapshot candidate;
            if (!decode(durable_,candidate) || !model.restore(candidate)) return fail(model);
        } else model.invalidateAdmission();
        loaded_=true;return true;
    }
    // Called after complete runs or explicit user reset, NEVER on every sample.
    // A false write is durability-ambiguous: latch fault even if readback matches.
    bool checkpoint(ThermalCoastModel& model,uint64_t now) {
        if (!loaded_ || fault_) return false;
        if (haveAttempt_ && now<lastAttempt_) return fail(model);
        std::string bytes;
        const auto snapshot=model.snapshot();
        if (!encode(snapshot,bytes)) return fail(model);
        if (bytes==durable_) return true;
        if (haveAttempt_ && now-lastAttempt_<minimumCheckpointMs) return false;
        std::string current;
        if (!store_.load(current) || current!=durable_) return fail(model);
        haveAttempt_=true;lastAttempt_=now;
        if (!store_.save(bytes)) return fail(model);
        if (!store_.load(current) || current!=bytes) return fail(model);
        durable_=bytes;return true;
    }
    bool healthy() const {return loaded_ && !fault_;}
private:
    static bool validHash(std::string_view h) {
        return h.size()==64 && std::all_of(h.begin(),h.end(),[](char c){
            return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
    }
    static void append(std::string& s,uint32_t v,size_t n) {
        for(size_t i=0;i<n;++i)s.push_back(static_cast<char>((v>>(i*8))&255));
    }
    static uint32_t get(std::string_view s,size_t& at,size_t n) {
        uint32_t v=0;for(size_t i=0;i<n;++i)v|=uint32_t(static_cast<uint8_t>(s[at++]))<<(i*8);return v;
    }
    // Avoid implementation-defined unsigned->negative signed conversion.
    static int16_t signed16(uint32_t v) {
        const int32_t value=v<32768?static_cast<int32_t>(v):static_cast<int32_t>(v)-65536;
        return static_cast<int16_t>(value);
    }
    bool encode(const CoastSnapshot& data,std::string& out) const {
        if (data.count>data.capacity || data.algorithmVersion!=1) return false;
        out="OTCM0001";out.push_back(static_cast<char>(data.algorithmVersion));out.push_back(static_cast<char>(data.count));
        for(auto b:data.bindingDigest)out.push_back(static_cast<char>(b));
        for(size_t i=0;i<data.count;++i) {
            const auto& r=data.runs[i];append(out,r.startUtc,4);append(out,r.endUtc,4);append(out,r.durationSec,4);
            append(out,r.heatedDurationSec,4);
            append(out,static_cast<uint16_t>(r.stopTemperatureCentiC),2);append(out,static_cast<uint16_t>(r.outdoorCentiC),2);
            append(out,static_cast<uint16_t>(r.waterCentiC),2);append(out,static_cast<uint16_t>(r.minimumRelativeCentiC),2);
            append(out,static_cast<uint16_t>(r.maximumRelativeCentiC),2);append(out,static_cast<uint16_t>(r.endRelativeCentiC),2);
        }
        const auto digest=hash_(out);if (!validHash(digest)) return false;out+=digest;return out.size()<=maximumBytes;
    }
    bool decode(std::string_view bytes,CoastSnapshot& data) const {
        if (bytes.size()<106 || bytes.size()>maximumBytes || bytes.substr(0,8)!="OTCM0001") return false;
        const auto body=bytes.substr(0,bytes.size()-64),expected=bytes.substr(bytes.size()-64);
        const auto digest=hash_(body);if (!validHash(digest) || digest!=expected) return false;
        size_t at=8;data.algorithmVersion=static_cast<uint8_t>(get(body,at,1));data.count=static_cast<uint8_t>(get(body,at,1));
        if (data.algorithmVersion!=1 || data.count>data.capacity || body.size()!=size_t(42)+28*data.count) return false;
        for(auto& b:data.bindingDigest)b=static_cast<uint8_t>(get(body,at,1));
        for(size_t i=0;i<data.count;++i) {
            auto& r=data.runs[i];r.startUtc=get(body,at,4);r.endUtc=get(body,at,4);r.durationSec=get(body,at,4);
            r.heatedDurationSec=get(body,at,4);r.stopTemperatureCentiC=signed16(get(body,at,2));
            r.outdoorCentiC=signed16(get(body,at,2));r.waterCentiC=signed16(get(body,at,2));
            r.minimumRelativeCentiC=signed16(get(body,at,2));r.maximumRelativeCentiC=signed16(get(body,at,2));
            r.endRelativeCentiC=signed16(get(body,at,2));
        }
        return true;
    }
    bool fail(ThermalCoastModel& model) {fault_=true;model.storageFault();return false;}
    ControlStore& store_;Hash hash_;std::string durable_;
    bool loaded_=false,fault_=false,haveAttempt_=false;uint64_t lastAttempt_=0;
};
}
