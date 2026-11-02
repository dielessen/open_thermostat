#pragma once
#include "ControlPartitionBudget.h"
#include <atomic>
namespace heating::control {
// Loop-owned resource reservation only. No source/sample/actuation authority,
// allocation, namespace creation, IO or refund while a failed owner still lives.
class ControlModelStorageReservation {
public:
    ControlModelStorageReservation()=default;
    ControlModelStorageReservation(const ControlModelStorageReservation&)=delete;
    ControlModelStorageReservation& operator=(const ControlModelStorageReservation&)=delete;
    bool claim(const void* owner,ControlModelReservation models) {
        if(owner_||!owner||!ControlPartitionBudget::validReservation(models)
                ||!ControlPartitionBudget::modelEntries(models)
                ||!ControlPartitionBudget::staticLedgerPermits(models))return false;
        owner_=owner;models_=models;return true;
    }
    void release(const void* owner) {if(owner_==owner){owner_=nullptr;models_={};}}
    bool matches(const void* owner,ControlModelReservation models) const {
        return owner&&owner_==owner&&models.warmZones==models_.warmZones
            &&models.coastZones==models_.coastZones&&models.curveGroups==models_.curveGroups;
    }
    ControlModelReservation current() const {return models_;}
private:
    const void* owner_=nullptr;
    ControlModelReservation models_{};
};
inline ControlModelStorageReservation controlModelStorageReservation;
// A graph or native control profile is configured (an NvsControlStore of
// graph_shadow_v2 exists this boot): its control record saves are gated by
// permitsGraphWrite, so the optional NVS records keep a full control
// replacement free (ControlPartitionBudget::controlReplacementEntries).
inline std::atomic<bool> graphControlStorage{false};
}
