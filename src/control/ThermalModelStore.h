#pragma once
#include "ControlStore.h"
#include "ModelResourceGate.h"
#include "ThermalResponseModel.h"
#include <functional>
#include <string>
#include <string_view>

namespace heating::control {
// SOURCE ONLY: caller must provide a separately budgeted, owner-bound atomic key,
// never the configuration key. No active factory/NVS allocation is added here.
// Hash is the existing production SHA256-hex contract, NOT a signature/MAC.
class ThermalModelStore {
public:
    using Hash=ModelHash;
    static constexpr size_t maximumBytes=426;
    static constexpr uint64_t minimumCheckpointMs=1800000;
    ThermalModelStore(ControlStore& store,Hash hash,ModelResourceGate& gate,uint8_t zone)
        :store_(store),hash_(hash),gate_(gate),zone_(zone) {}
    ~ThermalModelStore() {if(model_)model_->setMode(LearningMode::disabled);gate_.detach(zone_,ModelKind::warm,model_);}
    ThermalModelStore(const ThermalModelStore&)=delete;
    ThermalModelStore& operator=(const ThermalModelStore&)=delete;
    static_assert(maximumBytes==ModelResourceGate::warmCodecBytes,"codec budget drift");
    bool load(ThermalResponseModel& model) {
        if (loaded_ || fault_) return false;
        ModelResourceTransaction transaction(gate_,zone_,ModelKind::warm);
        if (!transaction || !gate_.attach(zone_,ModelKind::warm,&model,[](void* p){static_cast<ThermalResponseModel*>(p)->storageFault();})) return fail(model);
        model_=&model;
        model.setMode(LearningMode::disabled); // even empty restore never reinstates learning/admission
        if (!model.restore(model.snapshot())) return fail(model);
        ModelDigest digest{};
        if (!hash_ || !hash_("",digest) || !validHash({digest.data(),digest.size()}) || !gate_.healthy()) return fail(model);
        durable_.reserve(maximumBytes);
        if (!store_.loadBounded(durable_,maximumBytes) || !bounded(durable_) || !gate_.healthy()) return fail(model);
        if (!durable_.empty()) {
            ThermalModelSnapshot candidate;
            // Hash callbacks may fault the SHARED owner. NEVER restore over
            // that fault: restore intentionally clears model storage fault.
            if (!decode(durable_,candidate) || !gate_.healthy()) return fail(model);
            if (!model.restore(candidate) || !gate_.healthy()) return fail(model);
        } else model.invalidateAdmission();
        if (!gate_.healthy()) return fail(model);
        loaded_=true;return true;
    }
    // Called after complete runs or explicit user reset, NEVER on every sample.
    // A false write is durability-ambiguous: latch fault even if readback matches.
    bool checkpoint(ThermalResponseModel& model,uint64_t now) {
        if (!loaded_ || fault_) return false;
        if (model_!=&model || !gate_.healthy()) return fail(model);
        ModelResourceTransaction transaction(gate_,zone_,ModelKind::warm);
        if (!transaction || !gate_.checkClock(now)) return fail(model);
        if (haveAttempt_ && now<lastAttempt_) return fail(model);
        std::string bytes;bytes.reserve(maximumBytes);
        const auto snapshot=model.snapshot();
        if (!encode(snapshot,bytes) || !gate_.healthy()) return fail(model);
        if (bytes==durable_) return true;
        if (haveAttempt_ && now-lastAttempt_<minimumCheckpointMs) return false;
        std::string current;current.reserve(maximumBytes);
        if (!bounded(bytes) || !store_.loadBounded(current,maximumBytes) || !bounded(current) || current!=durable_ || !gate_.healthy()) return fail(model);
        const auto admitted=gate_.admitWrite(zone_,ModelKind::warm,now,bytes.size(),store_.modelPartitionStats());
        if (admitted==ModelResourceGate::Write::rejected) return fail(model);
        if (admitted==ModelResourceGate::Write::deferred) return false;
        haveAttempt_=true;lastAttempt_=now;
        if (!store_.saveBounded(bytes,maximumBytes) || !gate_.healthy()) return fail(model);
        if (!store_.loadBounded(current,maximumBytes) || !bounded(current) || current!=bytes || !gate_.healthy()) return fail(model);
        durable_=bytes;return true;
    }
    bool healthy() const {return loaded_ && !fault_ && gate_.healthy();}
private:
    static bool bounded(const std::string& s) {return s.size()<=maximumBytes && s.capacity()<=2*maximumBytes;}
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
    bool encode(const ThermalModelSnapshot& data,std::string& out) const {
        if (data.count>data.capacity || data.algorithmVersion!=1) return false;
        out="OTTM0001";out.push_back(static_cast<char>(data.algorithmVersion));out.push_back(static_cast<char>(data.count));
        for(auto b:data.bindingDigest)out.push_back(static_cast<char>(b));
        for(size_t i=0;i<data.count;++i) {
            const auto& r=data.runs[i];append(out,r.startUtc,4);append(out,r.endUtc,4);append(out,r.durationSec,4);
            append(out,static_cast<uint16_t>(r.riseCentiC),2);append(out,static_cast<uint16_t>(r.outdoorCentiC),2);
            append(out,static_cast<uint16_t>(r.waterCentiC),2);append(out,static_cast<uint16_t>(r.startTemperatureCentiC),2);
        }
        ModelDigest digest{};
        if (!hash_(out,digest) || !validHash({digest.data(),digest.size()})) return false;
        out.append(digest.data(),digest.size());return bounded(out);
    }
    bool decode(std::string_view bytes,ThermalModelSnapshot& data) const {
        if (bytes.size()<106 || bytes.size()>maximumBytes || bytes.substr(0,8)!="OTTM0001") return false;
        const auto body=bytes.substr(0,bytes.size()-64),expected=bytes.substr(bytes.size()-64);
        ModelDigest digest{};
        if (!hash_(body,digest) || !validHash({digest.data(),digest.size()}) || std::string_view(digest.data(),digest.size())!=expected) return false;
        size_t at=8;data.algorithmVersion=static_cast<uint8_t>(get(body,at,1));data.count=static_cast<uint8_t>(get(body,at,1));
        if (data.algorithmVersion!=1 || data.count>data.capacity || body.size()!=size_t(42)+20*data.count) return false;
        for(auto& b:data.bindingDigest)b=static_cast<uint8_t>(get(body,at,1));
        for(size_t i=0;i<data.count;++i) {
            auto& r=data.runs[i];r.startUtc=get(body,at,4);r.endUtc=get(body,at,4);r.durationSec=get(body,at,4);
            r.riseCentiC=signed16(get(body,at,2));r.outdoorCentiC=signed16(get(body,at,2));
            r.waterCentiC=signed16(get(body,at,2));r.startTemperatureCentiC=signed16(get(body,at,2));
        }
        return true;
    }
    bool fail(ThermalResponseModel& model) {fault_=true;model.storageFault();gate_.fail();return false;}
    ControlStore& store_;Hash hash_;ModelResourceGate& gate_;uint8_t zone_;ThermalResponseModel* model_=nullptr;std::string durable_;
    bool loaded_=false,fault_=false,haveAttempt_=false;uint64_t lastAttempt_=0;
};
}

static_assert(sizeof(heating::control::ThermalModelStore)<=heating::control::ModelResourceGate::storeResidentAllowance,"store resident budget drift");
