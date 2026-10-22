#pragma once
#include "EmsTelegram.h"
#include <algorithm>
#include <cstdint>
#include <ostream>
#include <string>

namespace heating::ems {
// Reporting only: boiler bits / supply temperature are not proof of room heat,
// real water flow, actuator position or physical commissioning.
class RoomHeatObservation {
public:
    static constexpr uint64_t ttlMs = 30000;
    explicit RoomHeatObservation(std::string boot = {}) : boot_(std::move(boot)) {}
    void receive(uint64_t now, const EmsTelegram& t) {
        if (t.getTypeId()!=0xE4 || t.getSenderId()!=8 ||
            t.getOperationType()==EmsTelegram::READ || t.getOperationType()==EmsTelegram::READ_WITH_DATA) return;
        const auto target=t.byteAt(6), power=t.byteAt(10), flags=t.byteAt(11);
        const auto supply=t.wordAt(7);
        // Partial frames cannot renew a full coherent observation.
        if (!target || !power || !flags || !supply) return;
        if (sequence_==UINT64_MAX || (sequence_ && now<observed_)) {
            valid_=false; return; // fail closed on clock rollback / exhausted epoch
        }
        ++sequence_; observed_=now;
        valid_=*target<=110 && *supply<=1100 && *power<=100;
        target_=*target; supply_=*supply; power_=*power; flags_=*flags;
    }
    void context(std::ostream& out, uint64_t now) const {
        out<<"{\"schema\":2,\"boot_id\":\""<<(validBoot()?boot_:"")<<"\",\"source_ms\":"<<now<<"}";
    }
    void write(std::ostream& out, uint64_t now) const {
        const bool fresh=validBoot() && valid_ && now>=observed_ && now-observed_<ttlMs;
        out<<"{\"schema\":2,\"boot_id\":\""<<(validBoot()?boot_:"")<<"\",\"source_ms\":"<<now
           <<",\"observed_ms\":"<<observed_<<",\"sequence\":"<<sequence_
           <<",\"ttl_ms\":"<<ttlMs<<",\"quality\":\"reported_plus_not_delivery_proof\",\"valid\":"<<(fresh?"true":"false");
        out<<",\"selected_flow_c\":"; number(out,fresh,target_);
        out<<",\"supply_c\":"; number(out,fresh,supply_/10.0);
        out<<",\"modulation_pct\":"; number(out,fresh,power_);
        out<<",\"ch\":"; boolean(out,fresh,(flags_&4)==0&&(flags_&2)!=0);
        out<<",\"dhw\":"; boolean(out,fresh,(flags_&1)!=0&&(flags_&4)!=0);
        out<<",\"flame\":"; boolean(out,fresh,(flags_&1)!=0);
        out<<",\"pump\":"; boolean(out,fresh,(flags_&2)!=0);
        out<<"}";
    }
private:
    bool validBoot() const {
        return boot_.size()==32 && std::all_of(boot_.begin(),boot_.end(),[](char c){
            return (c>='0'&&c<='9')||(c>='a'&&c<='f');
        });
    }
    static void number(std::ostream& out,bool valid,double value) { if(valid)out<<value;else out<<"null"; }
    static void boolean(std::ostream& out,bool valid,bool value) { out<<(valid?(value?"true":"false"):"null"); }
    std::string boot_;
    uint64_t observed_=0,sequence_=0;
    unsigned target_=0,supply_=0,power_=0,flags_=0;
    bool valid_=false;
};
}
