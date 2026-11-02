#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::control {
// Necessary conservative preflight for the EXISTING E32 20KiB NVS partition.
// Not proof of contiguous pages, successful commit or heap/8zone viability.
// No key/namespace/partition creation, erase, migration or device IO here.
enum class ControlStorageProfile { legacy_api1, graph_shadow_v2 };
struct ControlPartitionStats {
    size_t partitionBytes=0,totalEntries=0,usedEntries=0,freeEntries=0;
    bool valid=false;
};
struct ControlModelReservation {
    size_t warmZones=0,coastZones=0,curveGroups=0;
};
class ControlPartitionBudget {
public:
    static constexpr size_t partitionBytes=20*1024,entriesPerPage=126;
    static constexpr size_t totalEntries=5*entriesPerPage;
    static constexpr size_t configBytes=4096,networkBytes=2048;
    // Bound includes per-chunk/index overhead conservatively. Public stats do
    // not expose contiguous page placement; nvs_set_blob may STILL fail.
    static constexpr size_t blobEntries(size_t bytes) {
        return bytes&&bytes<=configBytes
            ?4+(bytes+31)/32+2*((bytes+3999)/4000):0;
    }
    static constexpr size_t warmBytes=426,coastBytes=554,curveBytes=412;
    static constexpr bool validReservation(ControlModelReservation r) {
        return r.warmZones<=8&&r.coastZones<=8&&r.curveGroups<=8;
    }
    static constexpr size_t modelEntries(ControlModelReservation r) {
        return validReservation(r)?r.warmZones*blobEntries(warmBytes)
            +r.coastZones*blobEntries(coastBytes)+r.curveGroups*blobEntries(curveBytes):SIZE_MAX;
    }
    static constexpr bool staticLedgerPermits(ControlModelReservation r) {
        // Existing max config + network + model allocations, one max config
        // replacement and GC page. Namespace entries reserved explicitly.
        return validReservation(r)&&2+blobEntries(configBytes)*2
            +blobEntries(networkBytes)+modelEntries(r)+entriesPerPage<=totalEntries;
    }
    static constexpr bool permitsGraphWrite(ControlPartitionStats s,size_t bytes,
                                            ControlModelReservation future={}) {
        if(!validStats(s)||!blobEntries(bytes)||!staticLedgerPermits(future)) return false;
        // Old config/network/other keys are ALREADY charged in usedEntries.
        // Never pretend old bytes are available before the new commit.
        return s.freeEntries>=2+blobEntries(configBytes)+entriesPerPage+modelEntries(future);
    }
    static constexpr bool permitsBluetoothWrite(ControlPartitionStats s,size_t bytes,
                                                 ControlModelReservation future={}) {
        return permitsPrivateBlobWrite(s,bytes,2048,future);
    }
    static constexpr bool permitsHeatingPlanWrite(ControlPartitionStats s,size_t bytes,
                                                   ControlModelReservation future={}) {
        return permitsPrivateBlobWrite(s,bytes,configBytes,future);
    }
    // What a private blob write of `bytes` (a plan or Bluetooth save) needs free.
    static constexpr size_t planSaveEntries(size_t bytes,ControlModelReservation future={}) {
        return 3+blobEntries(bytes)+blobEntries(configBytes)+entriesPerPage+modelEntries(future);
    }

    // rc.2 optional records beside the plan ("ot_heating"): what was learned
    // ("learned", "learned0".."learned7", up to 1 KB each), the automatic knobs
    // ("autotune", ~1.4 KB with its log) and the takeover readiness ("readiness").
    // Control comes first: one is written only while what control needs stays
    // free after it (the new record charged, the old one not reclaimed):
    //  - the handover confirmation (a string < 64 bytes),
    //  - the flow record at its largest (an owner's save),
    //  - a plan save and a Bluetooth save of their stored size plus an edit
    //    (the hand-back, a small edit), with the control replacement
    //    and GC margins of permitsHeatingPlanWrite / permitsBluetoothWrite,
    //  - `priority`: room kept for more important optional records.
    // A refused write is skipped (logged by the caller; RAM keeps the state).
    // A larger plan or Bluetooth save makes room for itself: makeRoom() erases
    // optional records, the least useful first, until it is permitted.
    static constexpr size_t bluetoothBytes=2048,editBytes=64;
    static constexpr size_t handoverEntries=3;   // nvs_set_str of < 64 bytes: 1 + 2
    static constexpr size_t flowRecordBytes=640; // >= FlowSettings::maxBytes + 1 (asserted in the tests)
    static constexpr size_t controlReserveEntries(size_t planBytes,size_t bleBytes,ControlModelReservation future={}) {
        const size_t plan=planBytes+editBytes<configBytes?planBytes+editBytes:configBytes;
        const size_t ble=bleBytes+editBytes<bluetoothBytes?bleBytes+editBytes:bluetoothBytes;
        return handoverEntries+blobEntries(flowRecordBytes)+planSaveEntries(plan>ble?plan:ble,future);
    }
    static constexpr bool permitsOptionalWrite(ControlPartitionStats s,size_t bytes,size_t planBytes,size_t bleBytes,
                                               ControlModelReservation future={},size_t priority=0) {
        if(!validStats(s)||!blobEntries(bytes)||planBytes>configBytes||bleBytes>bluetoothBytes||priority>totalEntries
            ||!staticLedgerPermits(future)) return false;
        return s.freeEntries>=1+blobEntries(bytes)+priority+controlReserveEntries(planBytes,bleBytes,future);
    }
    // The optional keys, erased in this order to make room: the learned rooms
    // (last first), the learned globals, the readiness counters, the automatic
    // knobs (written again by the owner where they fit).
    static constexpr size_t optionalKeyCount=11;
    static constexpr const char* optionalKeys[optionalKeyCount]={"learned7","learned6","learned5","learned4","learned3",
        "learned2","learned1","learned0","learned","readiness","autotune"};
    // permits(stats): the write that needs room; stats(): fresh statistics;
    // bytes(key): a stored optional record's size (0: absent); erase(key):
    // removes it. Nothing is erased with unknown statistics, or when erasing
    // every optional record (each counted at its smallest: 1 + 1 per 32 bytes)
    // could not make the room. False: still no room.
    template<class Permits,class Stats,class Bytes,class Erase>
    static bool makeRoom(Permits&& permits,Stats&& stats,Bytes&& bytes,Erase&& erase) {
        ControlPartitionStats s=stats();
        if(!validStats(s)) return false;
        if(permits(s)) return true;
        size_t reclaim=0;
        for(const char* key:optionalKeys) if(const size_t b=bytes(key)) reclaim+=1+(b+31)/32;
        reclaim=reclaim<s.usedEntries?reclaim:s.usedEntries;
        ControlPartitionStats best=s;best.usedEntries-=reclaim;best.freeEntries+=reclaim;
        if(!permits(best)) return false;
        for(const char* key:optionalKeys) {
            if(!bytes(key)) continue;
            erase(key);
            s=stats();
            if(!validStats(s)) return false;
            if(permits(s)) return true;
        }
        return false;
    }
private:
    static constexpr bool validStats(ControlPartitionStats s) {
        return s.valid&&s.partitionBytes==partitionBytes&&s.totalEntries
            &&s.totalEntries<=totalEntries&&s.usedEntries<=s.totalEntries
            &&s.freeEntries<=s.totalEntries
            &&s.usedEntries==s.totalEntries-s.freeEntries;
    }
    static constexpr bool permitsPrivateBlobWrite(ControlPartitionStats s,size_t bytes,size_t maximum,
                                                   ControlModelReservation future) {
        if(bytes<3||bytes>maximum||!permitsGraphWrite(s,bytes,future))return false;
        // Charge the NEW private blob and its namespace without reclaiming old
        // bytes, then still leave the original control replacement + GC margin.
        // Fresh statistics are necessary, not proof of contiguous free pages.
        return s.freeEntries>=planSaveEntries(bytes,future);
    }

};
}
