#pragma once
#include "EmsTelegram.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <ostream>
#include <string_view>

namespace heating::ems {
// The one table of passive entities beyond the 69 verified Classic boiler
// fields: what another controller asks of the boiler (0x1A), the maintenance
// message, EMS+ boilers (0xE4-0xEA) and room thermostats (RC10/20/30/35, EMS+
// HC1 monitor). Offsets and scaling follow the EMS-ESP telegram reference
// (https://emsesp.org); independent table, no copied EMS-ESP code. Values are
// observations only and never admit control. Not yet verified on hardware.
enum class EntityKind : uint8_t { u8, s16, u16, u24, bit };
enum class EntitySource : uint8_t { boiler, controller }; // controller: any non-boiler, non-service sender

struct EntitySpec {
    uint16_t type; uint8_t offset; EntityKind kind; uint8_t bit;
    uint16_t divisor; int32_t minimum, maximum; // range in raw units after sign handling
    EntitySource source; const char* id; const char* unit; uint32_t ttlMs;
};

inline constexpr uint32_t monitorTtl=180000, settingTtl=600000;
inline constexpr std::array<EntitySpec,40> entityCatalog{{
    // UBASetPoints written to the boiler by another controller (our own
    // service-address trial is excluded by the observer).
    {0x1A,0,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_flow_temperature","degC",monitorTtl},
    {0x1A,1,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_burner_power","%",monitorTtl},
    {0x1A,2,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_pump_modulation","%",monitorTtl},
    // UBAMaintenanceStatus: message number, 0 = none, 3 = H03.
    {0x1C,5,EntityKind::u8,0,1,0,254,EntitySource::boiler,"maintenance_message","code",settingTtl},
    // Room thermostats: setpoint is half degrees, room temperature tenths.
    {0xB1,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC10
    {0xB1,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x91,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC20
    {0x91,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0xAE,2,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC20 (new)/RC25
    {0xAE,3,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x41,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC30
    {0x41,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x3E,2,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC35 HC1
    {0x3E,3,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x3E,14,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_target_flow_temperature","degC",monitorTtl},
    // EMS+ HC1 monitor: the setpoint offset differs per model; room and target flow agree.
    {0x02A5,0,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x02A5,4,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_target_flow_temperature","degC",monitorTtl},
    // EMS+ boiler monitors and parameters.
    {0xE4,6,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_selected_flow_temperature","degC",monitorTtl},
    {0xE4,7,EntityKind::u16,0,10,0,1300,EntitySource::boiler,"plus_flow_temperature","degC",monitorTtl},
    {0xE4,9,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_requested_burner_power","%",monitorTtl},
    {0xE4,10,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_burner_modulation","%",monitorTtl},
    {0xE4,11,EntityKind::bit,0,1,0,1,EntitySource::boiler,"plus_burner_on","bool",monitorTtl},
    {0xE4,11,EntityKind::bit,2,1,0,1,EntitySource::boiler,"plus_dhw_valve","bool",monitorTtl},
    {0xE4,17,EntityKind::u16,0,10,1,1300,EntitySource::boiler,"plus_return_temperature","degC",monitorTtl},  // 0 = no sensor
    {0xE4,19,EntityKind::u16,0,10,0,1000,EntitySource::boiler,"plus_flame_current","uA",monitorTtl},
    {0xE4,21,EntityKind::u8,0,10,1,40,EntitySource::boiler,"plus_pressure","bar",monitorTtl},                // 0 = no sensor
    {0xE4,31,EntityKind::u16,0,10,0,5000,EntitySource::boiler,"plus_exhaust_temperature","degC",monitorTtl},
    {0xE5,2,EntityKind::bit,5,1,0,1,EntitySource::boiler,"plus_heating_pump","bool",monitorTtl},
    {0xE5,10,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_burner_starts","starts",monitorTtl},
    {0xE5,13,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_burner_runtime","min",monitorTtl},
    {0xE5,19,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_heating_runtime","min",monitorTtl},
    {0xE5,25,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_heating_pump_modulation","%",monitorTtl},
    {0xE9,0,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_dhw_target","degC",monitorTtl},
    {0xE9,1,EntityKind::u16,0,10,0,1000,EntitySource::boiler,"plus_dhw_temperature","degC",monitorTtl},
    {0xE9,11,EntityKind::u8,0,10,0,250,EntitySource::boiler,"plus_dhw_flow","L/min",monitorTtl},
    {0xE9,14,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_dhw_runtime","min",monitorTtl},
    {0xE9,17,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_dhw_starts","starts",monitorTtl},
    {0xEA,6,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_dhw_selected_temperature","degC",settingTtl},
    {0xE6,1,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_heating_temperature","degC",settingTtl},
    {0xE6,4,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_maximum_burner_power","%",settingTtl},
}};

// Bounded store: one slot per (device address, catalog row), oldest replaced.
class EmsEntityObserver {
public:
    static constexpr size_t capacity=48;
    static constexpr uint8_t boilerAddress=0x08,serviceAddress=0x0b;
    void observe(const EmsTelegram& t,uint64_t now) {
        if(!t.dataSize()||t.getOperationType()==EmsTelegram::READ||t.getOperationType()==EmsTelegram::READ_WITH_DATA)return;
        const uint8_t sender=t.getSenderId();
        if(!sender||sender==serviceAddress)return;
        for(size_t i=0;i<entityCatalog.size();++i) {
            const auto& spec=entityCatalog[i];
            if(spec.type!=t.getTypeId()||(spec.source==EntitySource::boiler)!=(sender==boilerAddress))continue;
            const auto value=decode(t,spec);
            if(!value.has_value()&&!present(t,spec))continue; // outside this (partial) frame
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
                else out<<static_cast<double>(slot.raw)/spec.divisor;
                out<<",\"unit\":\""<<spec.unit<<"\",\"source_type\":"<<spec.type<<",\"age_ms\":"<<now-slot.observedMs<<'}';
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
private:
    struct Slot{uint64_t observedMs=0;int32_t raw=0;uint8_t address=0,spec=0;bool valid=false;};
    static bool present(const EmsTelegram& t,const EntitySpec& spec) {
        const size_t width=spec.kind==EntityKind::u16||spec.kind==EntityKind::s16?2:spec.kind==EntityKind::u24?3:1;
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
    size_t used_=0;uint32_t dropped_=0;
};
}
