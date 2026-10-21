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
        if(!s.valid||s.partitionBytes!=partitionBytes||!s.totalEntries
            ||s.totalEntries>totalEntries||s.usedEntries>s.totalEntries
            ||s.freeEntries>s.totalEntries
            ||s.usedEntries!=s.totalEntries-s.freeEntries
            ||!blobEntries(bytes)||!staticLedgerPermits(future)) return false;
        // Old config/network/other keys are ALREADY charged in usedEntries.
        // Never pretend old bytes are available before the new commit.
        return s.freeEntries>=2+blobEntries(configBytes)+entriesPerPage+modelEntries(future);
    }
};
}
