#pragma once
#include "BoilerProfile.h"
#include "EmsEntityTable.h"
#include "EmsTelegram.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <ostream>
#include <string_view>

namespace heating::ems {
// Bounded store: one slot per (device address, catalog row), oldest replaced.
class EmsEntityObserver {
public:
    static constexpr size_t capacity=48;
    static constexpr uint8_t boilerAddress=0x08,serviceAddress=0x0b;
    void attachProfile(BoilerProfile* profile){profile_=profile;} // boiler profile, same owner and lock
    void observe(const EmsTelegram& t,uint64_t now) {
        if(!t.dataSize()||t.getOperationType()==EmsTelegram::READ||t.getOperationType()==EmsTelegram::READ_WITH_DATA)return;
        const uint8_t sender=t.getSenderId();
        if(!sender||sender==serviceAddress)return;
        for(size_t i=0;i<entityCatalog.size();++i) {
            const auto& spec=entityCatalog[i];
            if(spec.type!=t.getTypeId()||(spec.source==EntitySource::boiler)!=(sender==boilerAddress))continue;
            const auto value=decode(t,spec);
            if(!value.has_value()&&!present(t,spec))continue; // outside this (partial) frame
            if(profile_)profile_->observe(BoilerProfile::catalogSlot(entityRowFields[i]),
                value?FieldEvidence::value:FieldEvidence::absent,now);
            store(sender,i,value,now);
        }
    }
    void writeJSON(std::ostream& out,uint64_t now) const {
        out<<"{\"schema\":1,\"reference\":\"emsesp_offsets\",\"verified_on_hardware\":false,\"devices\":[";
        bool firstDevice=true;
        for(size_t d=0;d<used_;++d) {
            const auto address=slots_[d].address;
            bool seen=false;for(size_t e=0;e<d;++e)seen|=slots_[e].address==address;
            if(seen)continue;
            out<<(firstDevice?"":",")<<"{\"address\":"<<unsigned(address)<<",\"entities\":[";firstDevice=false;
            bool first=true;
            for(size_t s=d;s<used_;++s) {
                const auto& slot=slots_[s];
                if(slot.address!=address)continue;
                const auto& spec=entityCatalog[slot.spec];
                if(now<slot.observedMs||now-slot.observedMs>=spec.ttlMs)continue;
                out<<(first?"":",")<<"{\"id\":\""<<spec.id<<"\",\"value\":";first=false;
                if(!slot.valid)out<<"null";
                else if(spec.kind==EntityKind::bit)out<<(slot.raw?"true":"false");
                else if(spec.kind==EntityKind::text){out<<'"';for(char c:{char(slot.raw>>8),char(slot.raw&255)}){if(c=='"'||c=='\\')out<<'\\';out<<c;}out<<'"';}
                else out<<static_cast<double>(slot.raw)/spec.divisor;
                out<<",\"unit\":\""<<spec.unit<<"\",\"source_type\":"<<spec.type<<",\"age_ms\":"<<now-slot.observedMs
                   <<(spec.verified?",\"verified\":true}":"}"); // table-wide flag stays false
            }
            out<<"]}";
        }
        out<<"],\"dropped\":"<<dropped_<<'}';
    }
    // Test and UI helper: current value for one device/entity id, if fresh.
    std::optional<double> value(uint8_t address,const char* id,uint64_t now) const {
        for(size_t s=0;s<used_;++s) {
            const auto& slot=slots_[s];const auto& spec=entityCatalog[slot.spec];
            if(slot.address==address&&std::string_view(spec.id)==id&&slot.valid&&now>=slot.observedMs&&now-slot.observedMs<spec.ttlMs)
                return static_cast<double>(slot.raw)/spec.divisor;
        }
        return {};
    }
    // The freshest report of one field from any device, for the boiler fields route.
    struct FieldSample { int32_t raw; uint64_t observedMs; uint16_t type; bool valid; };
    std::optional<FieldSample> field(size_t field, uint64_t now) const {
        if (field >= entityFieldCount) return {};
        const Slot* best = nullptr;
        for (size_t s = 0; s < used_; ++s) {
            const auto& slot = slots_[s];
            if (!sameEntity(slot.spec, entityFieldRows[field])) continue;
            if (now < slot.observedMs || now - slot.observedMs >= entityCatalog[slot.spec].ttlMs) continue;
            if (!best || slot.observedMs > best->observedMs) best = &slot;
        }
        if (!best) return {};
        return FieldSample{best->raw, best->observedMs, entityCatalog[best->spec].type, best->valid};
    }
private:
    static bool printable(int c){return c>=32&&c<=126;}
    struct Slot{uint64_t observedMs=0;int32_t raw=0;uint8_t address=0,spec=0;bool valid=false;};
    static bool present(const EmsTelegram& t,const EntitySpec& spec) {
        const size_t width=spec.kind==EntityKind::u16||spec.kind==EntityKind::s16||spec.kind==EntityKind::text?2:spec.kind==EntityKind::u24?3:1;
        return t.getOffset()<=spec.offset&&size_t(spec.offset-t.getOffset())+width<=t.dataSize();
    }
    static std::optional<int32_t> decode(const EmsTelegram& t,const EntitySpec& spec) {
        std::optional<int32_t> raw;
        switch(spec.kind) {
            case EntityKind::u8: if(auto b=t.byteAt(spec.offset);b&&*b!=0xFF)raw=*b;break;
            case EntityKind::bit: if(auto b=t.byteAt(spec.offset))raw=(*b>>spec.bit)&1;break;
            case EntityKind::u16: if(auto w=t.wordAt(spec.offset);w&&*w!=0x8000&&*w!=0x7FFF&&*w!=0xFFFF)raw=*w;break;
            case EntityKind::s16: if(auto w=t.wordAt(spec.offset);w&&*w!=0x8000&&*w!=0x7FFF&&*w!=0x7D00)raw=static_cast<int16_t>(*w);break;
            case EntityKind::u24: if(auto c=t.counterAt(spec.offset);c&&*c!=0xFFFFFF)raw=static_cast<int32_t>(*c);break;
            case EntityKind::text: if(auto w=t.wordAt(spec.offset);w&&printable(*w>>8)&&printable(*w&255))raw=*w;break;
        }
        if(raw&&(*raw<spec.minimum||*raw>spec.maximum))raw.reset();
        return raw;
    }
    void store(uint8_t address,size_t spec,std::optional<int32_t> value,uint64_t now) {
        Slot* slot=nullptr;
        for(size_t s=0;s<used_;++s)if(slots_[s].address==address&&slots_[s].spec==spec){slot=&slots_[s];break;}
        if(slot&&now<slot->observedMs)return; // reordered older report cannot replace a newer one
        if(!slot) {
            if(used_<capacity)slot=&slots_[used_++];
            else {
                slot=&slots_[0];for(size_t s=1;s<used_;++s)if(slots_[s].observedMs<slot->observedMs)slot=&slots_[s];
                if(dropped_!=UINT32_MAX)++dropped_;
            }
        }
        *slot={now,value.value_or(0),address,static_cast<uint8_t>(spec),value.has_value()};
    }
    std::array<Slot,capacity> slots_{};
    BoilerProfile* profile_=nullptr;
    size_t used_=0;uint32_t dropped_=0;
};
}
