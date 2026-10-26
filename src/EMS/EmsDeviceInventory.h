#pragma once
#include "EmsTelegram.h"
#include "DeviceVersion.h"
#include <array>
#include <cstdint>
#include <ostream>

namespace heating::ems {
// Passive metadata from validated reports, never a scanner or support database.
// Owned by EmsController's existing telemetry mutex; fixed storage, no packet payload retention.
class EmsDeviceInventory {
public:
    static constexpr size_t capacity = 16, typesPerDevice = 64;
    void observe(const EmsTelegram &t, uint64_t now) {
        if (!t.dataSize() || t.getOperationType()==EmsTelegram::READ ||
            t.getOperationType()==EmsTelegram::READ_WITH_DATA || !t.getSenderId()) return;
        Entry *e=nullptr;
        for(size_t i=0;i<used_;++i)if(entries_[i].address==t.getSenderId()){e=&entries_[i];break;}
        if(!e){
            if(used_==capacity){increment(untracked_);return;}
            e=&entries_[used_++];e->address=t.getSenderId();
        }
        // Reordered queued reports cannot make diagnostic age younger or replace identity.
        if(e->frames && now<e->seen)return;
        e->seen=now;increment(e->frames);
        bool found=false;for(size_t i=0;i<e->usedTypes;++i)found|=e->types[i]==t.getTypeId();
        if(!found){if(e->usedTypes<typesPerDevice)e->types[e->usedTypes++]=t.getTypeId();else increment(e->untrackedTypes);}
        if(const auto version=readDeviceVersion(t)){
            e->product=version->product;e->major=version->major;e->minor=version->minor;e->version=true;
            e->brand=version->brand?int16_t(*version->brand):-1;
        }
    }
    void writeJSON(std::ostream &out,uint64_t now) const {
        out<<"{\"schema\":1,\"capacity\":"<<capacity<<",\"types_per_device\":"<<typesPerDevice<<",\"untracked_frames\":"<<untracked_<<",\"devices\":[";
        for(size_t i=0;i<used_;++i){
            if(i)out<<',';const auto &e=entries_[i];
            out<<"{\"address\":"<<unsigned(e.address)<<",\"frames\":"<<e.frames<<",\"age_ms\":";
            if(now>=e.seen)out<<now-e.seen;else out<<"null";
            out<<",\"product_id\":";if(e.version)out<<unsigned(e.product);else out<<"null";
            out<<",\"version\":";if(e.version)out<<'"'<<unsigned(e.major)<<'.'<<unsigned(e.minor)<<'"';else out<<"null";
            out<<",\"brand_id\":";if(e.brand>=0)out<<e.brand;else out<<"null";
            out<<",\"untracked_types\":"<<e.untrackedTypes<<",\"telegram_types\":[";
            for(size_t j=0;j<e.usedTypes;++j){if(j)out<<',';out<<e.types[j];}out<<"]}";
        }
        out<<"]}";
    }
private:
    static void increment(uint64_t &v){if(v!=UINT64_MAX)++v;}
    struct Entry {
        uint64_t seen=0,frames=0,untrackedTypes=0;
        std::array<uint16_t,typesPerDevice> types{};
        size_t usedTypes=0;
        int16_t brand=-1;
        uint8_t address=0,product=0,major=0,minor=0;
        bool version=false;
    };
    std::array<Entry,capacity> entries_{};
    size_t used_=0;uint64_t untracked_=0;
};
}
