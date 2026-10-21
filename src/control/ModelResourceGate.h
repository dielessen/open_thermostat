#pragma once
#include "ControlPartitionBudget.h"
#include "ThermalResponseModel.h"
#include "ThermalCoastModel.h"
#include "CurveAdaptation.h"
#include <array>
#include <string_view>

namespace heating::control {
// Resource preflight ONLY, never provenance, learning or output admission.
// No allocation/key/partition creation, worker, sample hook or persistent clock.
enum class ModelResourceProfile { unreviewed, bounded_memory_shadow_v1, e32_nvs_shadow_v1 };
enum class ModelKind : uint8_t { warm=0, coast=1, curve=2 };
struct ModelResourcePlan {
    ModelResourceProfile profile=ModelResourceProfile::unreviewed;
    uint8_t schema=0,zones=0;
    ControlModelReservation models{};
    size_t residentBytes=0,scratchBytes=0,stackBytes=0,persistentBytes=0;
    uint32_t checkpointSpacingMs=0,checkpointsPerHour=0,checkpointBytesPerHour=0;
};
struct ModelResourceRequirements {
    size_t residentBytes=0,scratchBytes=0,stackBytes=0,persistentBytes=0;
    size_t codecBytes=0,slots=0,nvsEntries=0;
};
using ModelDigest=std::array<char,64>;
// Fixed-output, non-owning callback. Its INTERNAL callgraph/workspace is an
// explicit external review gate, not magically bounded by a callback signature.
using ModelHash=bool(*)(std::string_view,ModelDigest&);
class ModelResourceGate {
public:
    static constexpr size_t maximumZones=8,maximumSlots=24;
    static constexpr size_t warmCodecBytes=426,coastCodecBytes=554,curveCodecBytes=412;
    static constexpr size_t storeResidentAllowance=128,backendResidentAllowance=128,allocationOverhead=32;
    static constexpr size_t providerWorkspaceAllowance=4096;
    static constexpr size_t minimumStackBytes=4096;
    static constexpr uint64_t minimumCheckpointMs=1800000,hourMs=3600000;
    enum class Write { allowed, deferred, rejected };
    explicit ModelResourceGate(ModelResourcePlan plan):plan_(plan) {
        valid_=requirements(plan,required_)&&within(plan.residentBytes,required_.residentBytes,131072)
            &&within(plan.scratchBytes,required_.scratchBytes,16384)
            &&within(plan.stackBytes,required_.stackBytes,16384)
            &&within(plan.persistentBytes,required_.persistentBytes,65536)
            &&plan.checkpointSpacingMs>=60000&&plan.checkpointSpacingMs<=1800000
            &&plan.checkpointsPerHour>=1&&plan.checkpointsPerHour<=24
            &&plan.checkpointBytesPerHour>=required_.codecBytes
            &&plan.checkpointBytesPerHour<=24*coastCodecBytes;
    }
    ModelResourceGate(const ModelResourceGate&)=delete;
    ModelResourceGate& operator=(const ModelResourceGate&)=delete;
    static constexpr size_t codecBytes(ModelKind k) {
        return k==ModelKind::warm?warmCodecBytes:k==ModelKind::coast?coastCodecBytes:k==ModelKind::curve?curveCodecBytes:0;
    }
    static bool requirements(const ModelResourcePlan& p,ModelResourceRequirements& out) {
        out={};
        if(p.schema!=1||p.zones<1||p.zones>maximumZones
            ||(p.profile!=ModelResourceProfile::bounded_memory_shadow_v1&&p.profile!=ModelResourceProfile::e32_nvs_shadow_v1)
            ||p.models.warmZones>p.zones||p.models.coastZones>p.zones||p.models.curveGroups>p.zones)return false;
        const std::array<size_t,3> counts{{p.models.warmZones,p.models.coastZones,p.models.curveGroups}};
        const std::array<size_t,3> models{{sizeof(ThermalResponseModel),sizeof(ThermalCoastModel),sizeof(CurveAdaptation)}};
        size_t resident=sizeof(ModelResourceGate),durable=0,slots=0,largest=0,snapshot=0;
        const std::array<size_t,3> snapshots{{sizeof(ThermalModelSnapshot),sizeof(CoastSnapshot),sizeof(CurveSnapshot)}};
        for(size_t k=0;k<counts.size();++k) {
            const auto bytes=codecBytes(static_cast<ModelKind>(k));
            // Counts bounded before ANY multiplication; all operands are hard caps.
            resident+=counts[k]*(models[k]+storeResidentAllowance+backendResidentAllowance+2*bytes+allocationOverhead);
            durable+=counts[k]*bytes;slots+=counts[k];
            if(counts[k]) {largest=std::max(largest,bytes);snapshot=std::max(snapshot,snapshots[k]);}
        }
        if(!slots)return false;
        // Source memory backend also holds durable payloads in RAM, separately
        // from each codec's durable readback cache. NVS does not earn that RAM.
        if(p.profile==ModelResourceProfile::bounded_memory_shadow_v1)
            resident+=2*durable+slots*allocationOverhead;
        out={resident,2*(2*largest+allocationOverhead)+snapshot+sizeof(ModelDigest)+providerWorkspaceAllowance,
             minimumStackBytes,durable,largest,slots,0};
        if(p.profile==ModelResourceProfile::e32_nvs_shadow_v1) {
            // Reuse existing conservative20KiB ledger. ALSO reserve one model
            // replacement, not only its old durable blob/config replacement/GC.
            out.nvsEntries=2+2*ControlPartitionBudget::blobEntries(ControlPartitionBudget::configBytes)
                +ControlPartitionBudget::blobEntries(ControlPartitionBudget::networkBytes)
                +ControlPartitionBudget::entriesPerPage+ControlPartitionBudget::modelEntries(p.models)
                +ControlPartitionBudget::blobEntries(largest);
            if(!ControlPartitionBudget::staticLedgerPermits(p.models)
                ||out.nvsEntries>ControlPartitionBudget::totalEntries
                ||p.persistentBytes>ControlPartitionBudget::partitionBytes)return false;
        }
        return true;
    }
    bool healthy()const{return valid_&&!fault_;}
    const ModelResourceRequirements& required()const{return required_;}
    bool owns(uint8_t zone,ModelKind kind)const {
        const auto count=kind==ModelKind::warm?plan_.models.warmZones:
            kind==ModelKind::coast?plan_.models.coastZones:kind==ModelKind::curve?plan_.models.curveGroups:0;
        return healthy()&&zone<plan_.zones&&zone<count;
    }
    // Models/stores must outlive their registration and gate must outlive stores.
    bool attach(uint8_t zone,ModelKind kind,void* model,void(*disable)(void*)) {
        if(!owns(zone,kind)||!model||!disable)return fail();
        auto& slot=slots_[index(zone,kind)];
        if(slot.model)return fail(); // no two owners of the same model checkpoint
        slot.model=model;slot.disable=disable;return true;
    }
    void detach(uint8_t zone,ModelKind kind,void* model) {
        if(zone>=maximumZones||!codecBytes(kind))return;
        auto& slot=slots_[index(zone,kind)];
        if(slot.model==model){slot.model=nullptr;slot.disable=nullptr;}
        // Checkpoint quota/high-water deliberately survives store destruction.
    }
    bool begin(uint8_t zone,ModelKind kind) {
        if(!owns(zone,kind)||busy_)return fail();
        busy_=true;return true;
    }
    void end(){busy_=false;}
    bool checkClock(uint64_t now) {
        if(!healthy())return false;
        if(haveClock_&&now<lastClock_)return fail();
        haveClock_=true;lastClock_=now;return true;
    }
    Write admitWrite(uint8_t zone,ModelKind kind,uint64_t now,size_t bytes,ControlPartitionStats stats={}) {
        if(!busy_||!owns(zone,kind)||!bytes||bytes>codecBytes(kind)||!checkClock(now)){fail();return Write::rejected;}
        auto& slot=slots_[index(zone,kind)];
        if(plan_.profile==ModelResourceProfile::e32_nvs_shadow_v1) {
            // Actual current stats necessary at EVERY mutation. No configured
            // number or stale plan can substitute for backend's fresh quota.
            if(!ControlPartitionBudget::permitsGraphWrite(stats,bytes,plan_.models)
                ||stats.freeEntries<ControlPartitionBudget::blobEntries(bytes)+ControlPartitionBudget::entriesPerPage) {
                fail();return Write::rejected;
            }
        }
        if((slot.attempted&&now-slot.lastAttempt<minimumCheckpointMs)
            ||(haveWrite_&&now-lastWrite_<plan_.checkpointSpacingMs))return Write::deferred;
        if(!haveWindow_||now-windowAt_>=hourMs){windowAt_=now;writesInWindow_=bytesInWindow_=0;haveWindow_=true;}
        if(writesInWindow_>=plan_.checkpointsPerHour||bytes>plan_.checkpointBytesPerHour-bytesInWindow_)return Write::deferred;
        // Reserve attempt BEFORE IO. Ambiguous failure cannot refund quota.
        slot.attempted=true;slot.lastAttempt=now;haveWrite_=true;lastWrite_=now;
        ++writesInWindow_;bytesInWindow_+=static_cast<uint32_t>(bytes);return Write::allowed;
    }
    bool fail() {
        fault_=true;
        for(auto& slot:slots_)if(slot.model&&slot.disable)slot.disable(slot.model);
        return false;
    }
private:
    struct Slot {void* model=nullptr;void(*disable)(void*)=nullptr;uint64_t lastAttempt=0;bool attempted=false;};
    static constexpr size_t index(uint8_t zone,ModelKind k){return static_cast<size_t>(k)*maximumZones+zone;}
    static bool within(size_t declared,size_t required,size_t maximum){return declared>=required&&declared<=maximum;}
    ModelResourcePlan plan_;ModelResourceRequirements required_{};
    std::array<Slot,maximumSlots> slots_{};
    bool valid_=false,fault_=false,busy_=false,haveClock_=false,haveWrite_=false,haveWindow_=false;
    uint64_t lastClock_=0,lastWrite_=0,windowAt_=0;
    uint32_t writesInWindow_=0,bytesInWindow_=0;
};
// Scope serialized snapshot/codec/readback work; no copying eight model objects.
class ModelResourceTransaction {
public:
    ModelResourceTransaction(ModelResourceGate& gate,uint8_t zone,ModelKind kind):gate_(gate),ok_(gate.begin(zone,kind)){}
    ~ModelResourceTransaction(){if(ok_)gate_.end();}
    explicit operator bool()const{return ok_;}
    ModelResourceTransaction(const ModelResourceTransaction&)=delete;
    ModelResourceTransaction& operator=(const ModelResourceTransaction&)=delete;
private:ModelResourceGate& gate_;bool ok_;
};
}
