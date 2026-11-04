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
    // `control`: the entries kept for a replacement of the control record
    // (ot_control/config). Default: a full 4 KB one (blobEntries(configBytes)),
    // the ledger of every firmware before rc.2; rc.2 passes
    // controlReplacementEntries() of the record actually stored.
    static constexpr bool permitsBluetoothWrite(ControlPartitionStats s,size_t bytes,
                                                 ControlModelReservation future={},size_t control=blobEntries(configBytes)) {
        return permitsPrivateBlobWrite(s,bytes,2048,future,control);
    }
    static constexpr bool permitsHeatingPlanWrite(ControlPartitionStats s,size_t bytes,
                                                   ControlModelReservation future={},size_t control=blobEntries(configBytes)) {
        return permitsPrivateBlobWrite(s,bytes,configBytes,future,control);
    }
    // What a private blob write of `bytes` (a plan or Bluetooth save) needs free.
    static constexpr size_t planSaveEntries(size_t bytes,ControlModelReservation future={},size_t control=blobEntries(configBytes)) {
        return 3+blobEntries(bytes)+control+entriesPerPage+modelEntries(future);
    }

    // The control record's replacement (ot_control/config, written by the Home
    // Assistant session through ha/config). Before rc.2 always a full 4 KB one
    // (136 entries). The record is that large only with Home Assistant rooms or
    // a native room profile; in E32 room-plan mode the session's record holds no
    // rooms (~0.2 KB). So: a full one while a graph/native control profile is
    // configured (its saves are gated by permitsGraphWrite, which keeps
    // reserving it), else the stored record plus an edit. A larger record makes
    // room for itself (NvsControlStore, makeRoom below), like a larger plan.
    static constexpr size_t controlReplacementEntries(size_t storedBytes,bool graphProfile) {
        return graphProfile||storedBytes+editBytes>=configBytes?blobEntries(configBytes):blobEntries(storedBytes+editBytes);
    }

    // rc.2 optional records beside the plan ("ot_heating"): what was learned
    // ("learned_a", "learned_b": the packed frames of LearnedState.h), the
    // automatic knobs ("autotune", ~1.4 KB with its log) and the takeover
    // readiness ("readiness"). Control comes first: one is written only while
    // what control needs stays free after it (the new record charged, the
    // record it replaces reclaimed at its smallest: NVS counts an erased entry
    // as free):
    //  - the handover confirmation (a string < 64 bytes),
    //  - the flow record at its largest (an owner's save),
    //  - one private save: the plan at its stored size plus an edit or the
    //    Bluetooth settings at their largest (2 KB), whichever is larger,
    //  - the control record's replacement (controlReplacementEntries),
    //  - the GC page (and a model reservation, none in this product),
    //  - `priority`: room kept for more important optional records.
    // A refused write is skipped (logged by the caller; RAM keeps the state).
    // A larger plan, Bluetooth or control save makes room for itself:
    // makeRoom() erases optional records, the least useful first.
    static constexpr size_t bluetoothBytes=2048,editBytes=64;
    static constexpr size_t handoverEntries=3;   // nvs_set_str of < 64 bytes: 1 + 2
    static constexpr size_t flowRecordBytes=640; // >= FlowSettings::maxBytes + 1 (asserted in the tests)
    // rc.4: the owner's holiday planner ("holidays", RoomOverrides::holidaysStored(): 8 periods and
    // the holiday temperature, a string of at most holidayRecordBytes with its NUL). Written like an
    // optional record (permitsHolidayWrite: control keeps its room after it), but it is the owner's:
    // like a plan save it makes room for itself (makeRoom erases what was learned, the least useful
    // first, written again where it fits), and it is not in optionalKeys (never erased itself).
    static constexpr size_t holidayRecordBytes=224;
    static constexpr bool permitsHolidayWrite(ControlPartitionStats s,size_t bytes,size_t oldBytes,size_t reserve) {
        return bytes<=holidayRecordBytes&&permitsOptionalWrite(s,bytes,oldBytes,reserve);
    }
    static constexpr size_t privateSaveBytes(size_t planBytes,size_t bleBytes) {
        const size_t plan=planBytes+editBytes<configBytes?planBytes+editBytes:configBytes;
        return plan>bleBytes?plan:bleBytes;
    }
    // SIZE_MAX (never permitted) for a reservation the static ledger refuses or a `control` above a full replacement.
    static constexpr size_t controlReserveEntries(size_t planBytes,size_t control,ControlModelReservation future={}) {
        return !staticLedgerPermits(future)||control>blobEntries(configBytes)?SIZE_MAX
            :handoverEntries+blobEntries(flowRecordBytes)+planSaveEntries(privateSaveBytes(planBytes,bluetoothBytes),future,control);
    }
    // The ledger of the firmware a rollback returns to (beta.22 and rc.1 gate a
    // plan or Bluetooth save with a full control replacement), as rc.2 kept it
    // before the packed learned record: a plan or Bluetooth save of the stored
    // size plus an edit, the full control replacement, the handover and the
    // flow record. Used while this firmware's boot is unconfirmed (the
    // bootloader may still roll back) and to make room before a requested rollback.
    static constexpr size_t previousFirmwareReserveEntries(size_t planBytes,size_t bleBytes) {
        const size_t ble=bleBytes+editBytes<bluetoothBytes?bleBytes+editBytes:bluetoothBytes;
        return handoverEntries+blobEntries(flowRecordBytes)+planSaveEntries(privateSaveBytes(planBytes,ble));
    }
    // An erased record of `bytes` at its smallest (a string: 1 + 1 per 32 bytes; a blob has one more).
    static constexpr size_t reclaimEntries(size_t bytes) { return bytes?1+(bytes+31)/32:0; }
    // `oldBytes`: the record this write replaces (0: a new key); `reserve`:
    // controlReserveEntries() or previousFirmwareReserveEntries().
    static constexpr bool permitsOptionalWrite(ControlPartitionStats s,size_t bytes,size_t oldBytes,size_t reserve,size_t priority=0) {
        if(!validStats(s)||!blobEntries(bytes)||oldBytes>configBytes||reserve>totalEntries||priority>totalEntries) return false;
        const size_t need=1+blobEntries(bytes);
        const size_t reclaim=reclaimEntries(oldBytes)<s.usedEntries?reclaimEntries(oldBytes):s.usedEntries;
        // Written at all (the new record beside the old one, the GC page), then control's room after it.
        return s.freeEntries>=need+entriesPerPage&&s.freeEntries+reclaim>=need+reserve+priority;
    }
    // The optional keys, erased in this order to make room: the hot water days
    // (rc.4, F2: counts only), the per-room keys
    // of rc.2 builds before the packed record, the learned record's second and
    // first part (the later rooms first; the first part also holds the
    // globals), the readiness counters, the automatic knobs (written again by
    // their owner where they fit).
    static constexpr size_t optionalKeyCount=14;
    static constexpr const char* optionalKeys[optionalKeyCount]={"dhw","learned7","learned6","learned5","learned4","learned3",
        "learned2","learned1","learned0","learned","learned_b","learned_a","readiness","autotune"};
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
        for(const char* key:optionalKeys) if(const size_t b=bytes(key)) reclaim+=reclaimEntries(b);
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
                                                   ControlModelReservation future,size_t control) {
        if(bytes<3||bytes>maximum||!validStats(s)||!staticLedgerPermits(future)||control>blobEntries(configBytes)) return false;
        // Charge the NEW private blob and its namespace without reclaiming old
        // bytes, then still leave the control replacement + GC margin (with the
        // default `control` also permitsGraphWrite's margin).
        // Fresh statistics are necessary, not proof of contiguous free pages.
        return s.freeEntries>=planSaveEntries(bytes,future,control);
    }
};
}
