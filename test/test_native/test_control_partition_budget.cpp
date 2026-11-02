#include <gtest/gtest.h>
#include "control/ControlPartitionBudget.h"
#include "control/AutoTuner.h"
#include "control/FlowPolicy.h"
#include "control/LearnedState.h"
#include "control/OptionalRecordPriority.h"
#include "control/TakeoverReadiness.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>
using namespace heating::control;
namespace {
ControlPartitionStats healthy(size_t free=630) {return {20480,630,630-free,free,true};}
TEST(ControlPartitionBudget, ExactExistingPartitionKnownSlotsAndBlobBound) {
    EXPECT_EQ(ControlPartitionBudget::blobEntries(4096),136u);
    EXPECT_EQ(ControlPartitionBudget::blobEntries(2048),70u);
    EXPECT_EQ(ControlPartitionBudget::blobEntries(426),20u);
    EXPECT_EQ(ControlPartitionBudget::blobEntries(554),24u);
    EXPECT_EQ(ControlPartitionBudget::blobEntries(412),19u);
    EXPECT_TRUE(ControlPartitionBudget::staticLedgerPermits({}));
    EXPECT_TRUE(ControlPartitionBudget::permitsGraphWrite(healthy(),4096));
}
TEST(ControlPartitionBudget, ActualFreeAlreadyChargesOldConfigAndNetworkNoReclaimBeforeCommit) {
    // 2namespaces+136maxnewblob+126GC page =264 free entries. Old config and
    // network remain ALREADY charged to usedEntries, never added to free.
    EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(263),4096));
    EXPECT_TRUE(ControlPartitionBudget::permitsGraphWrite(healthy(264),4096));
    EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(263),1));
}
TEST(ControlPartitionBudget, UnknownPartitionUnreadableInconsistentOrOverflowStatsRejected) {
    auto s=healthy();s.valid=false;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.partitionBytes=40960;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.partitionBytes=0;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.usedEntries=1;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.totalEntries=0;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.totalEntries=631;s.freeEntries=631;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
    s=healthy();s.freeEntries=SIZE_MAX;s.usedEntries=SIZE_MAX;EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(s,4096));
}
TEST(ControlPartitionBudget, EmptyOversizedOrIntegerOverflowBlobRejected) {
    for(size_t bytes:{size_t(0),size_t(4097),SIZE_MAX}) {
        EXPECT_EQ(ControlPartitionBudget::blobEntries(bytes),0u);
        EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(),bytes));
    }
}
TEST(ControlPartitionBudget, AllEightPersistentModelsAreNotAdvertisedUnderConservative20KiBLedger) {
    const ControlModelReservation full{8,8,8};
    EXPECT_EQ(ControlPartitionBudget::modelEntries(full),504u);
    EXPECT_FALSE(ControlPartitionBudget::staticLedgerPermits(full));
    EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(),4096,full));
    // One group's checkpoint reservation is separately bounded, not an8zoneGO.
    const ControlModelReservation one{1,1,1};
    EXPECT_EQ(ControlPartitionBudget::modelEntries(one),63u);
    EXPECT_TRUE(ControlPartitionBudget::staticLedgerPermits(one));
    EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(326),4096,one));
    EXPECT_TRUE(ControlPartitionBudget::permitsGraphWrite(healthy(327),4096,one));
}
TEST(ControlPartitionBudget, UnknownModelCountsCannotWrapOrSilentlyDropReservation) {
    for(ControlModelReservation bad: {ControlModelReservation{9,0,0},
        ControlModelReservation{0,9,0},ControlModelReservation{0,0,9},
        ControlModelReservation{SIZE_MAX,SIZE_MAX,SIZE_MAX}}) {
        EXPECT_FALSE(ControlPartitionBudget::validReservation(bad));
        EXPECT_EQ(ControlPartitionBudget::modelEntries(bad),SIZE_MAX);
        EXPECT_FALSE(ControlPartitionBudget::staticLedgerPermits(bad));
        EXPECT_FALSE(ControlPartitionBudget::permitsGraphWrite(healthy(),4096,bad));
    }
}
}
TEST(ControlPartitionBudget, BluetoothLeavesTheOriginalControlAndGcMarginAfterItsNewBlob) {
    EXPECT_FALSE(ControlPartitionBudget::permitsBluetoothWrite(healthy(334),2048));
    EXPECT_TRUE(ControlPartitionBudget::permitsBluetoothWrite(healthy(335),2048));
    // New private blob70 + own namespace1 have NOT been reclaimed from old data.
    EXPECT_TRUE(ControlPartitionBudget::permitsGraphWrite(healthy(335-70-1),4096));
    const ControlModelReservation models{1,1,1};
    EXPECT_FALSE(ControlPartitionBudget::permitsBluetoothWrite(healthy(397),2048,models));
    EXPECT_TRUE(ControlPartitionBudget::permitsBluetoothWrite(healthy(398),2048,models));
}
TEST(ControlPartitionBudget, BluetoothRejectsUnknownBudgetInvalidSizesAndOverflowReservations) {
    auto bad=healthy();bad.valid=false;EXPECT_FALSE(ControlPartitionBudget::permitsBluetoothWrite(bad,100));
    for(auto bytes:{size_t(0),size_t(2),size_t(2049),SIZE_MAX})EXPECT_FALSE(ControlPartitionBudget::permitsBluetoothWrite(healthy(),bytes));
    EXPECT_FALSE(ControlPartitionBudget::permitsBluetoothWrite(healthy(),100,{SIZE_MAX,0,0}));
}

// Review of rc.2 (finding 3): the optional records beside the plan (learned,
// autotune, readiness) and the larger flow record were not in the budget. From
// the beta.19 baseline (198 of 630 used, e32-beta19-20261030-postinstall-capture.json)
// 4 rooms x 5 bins left ~303 free where a 2 KB plan save needs 334 (507 storage_full);
// 8 rooms x 20 bins filled the partition. Now an optional record is written only
// while control keeps its room, and a larger plan makes room by erasing them.
namespace {
using B = ControlPartitionBudget;
constexpr size_t baselineUsed = 198;
ControlPartitionStats used(size_t n) { return {20480, 630, n, 630 - n, true}; }
static_assert(FlowSettings::maxBytes + 1 <= B::flowRecordBytes, "the flow record's reserve");
static_assert(sizeof(TakeoverReadiness::Stored) <= 1024);
TEST(ControlPartitionBudget, TheKnobsWithoutTheirLogFitTheirPriorityReserve) {
    AutoTuner t;
    ControlTuning widest; size_t kn; const auto* kk = ControlTuning::knobs(kn);
    for (size_t i = 0; i < kn; ++i) widest.*kk[i].field = kk[i].high;
    ASSERT_TRUE(t.restore(("{\"values\":" + widest.json() + ",\"log\":[[1,\"min_on_s\",300,360,\"short_burns\",3,\"\"]]}").c_str()));
    EXPECT_EQ(t.stored(0).find("\"log\":[]"), t.stored(0).size() - 9);
    EXPECT_LE(t.stored(0).size() + 1, OptionalRecordPriority::knobsBytes);
    EXPECT_GT(t.stored().size(), t.stored(0).size());
}
// The worst case: the readiness counters, the knobs with a full log, the learned globals
// and 8 rooms with all 20 bins (every frame at most LearnedState::maxFrame).
struct Record { const char* key; size_t bytes; };
// The reviewer's case: 4 rooms with 5 bins (0.1 KB + 41 B a bin), the globals ~0.25 KB, a log of 10 typical entries.
std::vector<Record> typical() {
    return {{"readiness", sizeof(TakeoverReadiness::Stored)}, {"autotune", 950}, {"learned", 250},
            {"learned0", 335}, {"learned1", 335}, {"learned2", 335}, {"learned3", 335}};
}
std::vector<Record> worstCase() {
    std::vector<Record> r{{"readiness", sizeof(TakeoverReadiness::Stored)}, {"autotune", AutoTuner::storedMaxBytes + 1},
                          {"learned", LearnedState::maxFrame}};
    static const char* rooms[] = {"learned0", "learned1", "learned2", "learned3", "learned4", "learned5", "learned6", "learned7"};
    for (const char* k : rooms) r.push_back({k, LearnedState::maxFrame});
    return r;
}
}
TEST(ControlPartitionBudget, OptionalRecordsAlwaysLeaveRoomForThePlanHandoverAndBluetooth) {
    const size_t flowGrowth = B::blobEntries(B::flowRecordBytes) - B::blobEntries(96); // beta.19 flow record: <= 95 bytes
    size_t ungated = baselineUsed + flowGrowth;
    for (const auto& r : worstCase()) ungated += B::blobEntries(r.bytes);
    std::printf("[ nvs ] baseline %zu used + flow growth %zu + optional worst case %zu = %zu of 630 (GC page 126)\n",
                baselineUsed, flowGrowth, ungated - baselineUsed - flowGrowth, ungated);
    // Before: written without a budget, no plan save fits (and the partition is over full).
    EXPECT_GT(ungated, 630u - B::entriesPerPage);
    EXPECT_FALSE(B::permitsHeatingPlanWrite(used(std::min<size_t>(ungated, 630)), 600));
    // Stored plan and Bluetooth sizes (the baseline holds them); the worst case written through the gate.
    const std::pair<size_t, size_t> sizes[] = {{600, 300}, {1200, 600}, {2000, 2047}, {3000, 900}, {4096, 2048}};
    for (const auto& records : {worstCase(), typical()})
    for (const auto& [plan, ble] : sizes) {
        size_t n = baselineUsed + flowGrowth;
        std::string kept;
        for (const auto& r : records) {
            // As LearnedNvs and AutoTunerNvs: the learned frames after the knobs and the readiness,
            // the knobs' log after one learned frame (else the values only).
            const bool knobs = !std::strcmp(r.key, "autotune");
            size_t bytes = r.bytes, priority = r.key[0] == 'l' ? OptionalRecordPriority::learned : knobs ? OptionalRecordPriority::tuningLog : 0;
            if (knobs && !B::permitsOptionalWrite(used(n), bytes, plan, ble, {}, priority)) { bytes = OptionalRecordPriority::knobsBytes; priority = 0; }
            if (!B::permitsOptionalWrite(used(n), bytes, plan, ble, {}, priority)) continue;
            n += B::blobEntries(bytes); kept += std::string(r.key) + (bytes < r.bytes ? "(values) " : " ");
        }
        std::printf("[ nvs ] %s plan %4zu B, Bluetooth %4zu B: reserve %zu; written: %s-> %zu used, %zu free\n",
                    records.size() > 7 ? "worst case:" : "typical:   ", plan, ble,
                    B::controlReserveEntries(plan, ble), kept.c_str(), n, 630 - n);
        // The invariant: a plan save and a Bluetooth save of the stored size plus an edit (the
        // hand-back, a small edit), the handover confirmation and the largest flow record fit.
        EXPECT_TRUE(B::permitsHeatingPlanWrite(used(n), std::min(plan + B::editBytes, B::configBytes))) << plan;
        EXPECT_TRUE(B::permitsBluetoothWrite(used(n), std::min(ble + B::editBytes, B::bluetoothBytes))) << ble;
        EXPECT_GE(630 - n, B::handoverEntries + B::blobEntries(B::flowRecordBytes) + B::entriesPerPage) << plan;
        EXPECT_LE(n, 630u - B::entriesPerPage) << "never physically full";
    }
    // The gate itself: the edge, invalid stats, sizes and reservations.
    const size_t edge = 1 + B::blobEntries(1000) + B::controlReserveEntries(0, 0);
    EXPECT_EQ(B::controlReserveEntries(0, 0), 3u + 26u + (3u + 8u + 136u + 126u)); // handover, flow, a 64-byte plan save
    EXPECT_EQ(B::controlReserveEntries(0, 2048), 3u + 26u + (3u + 70u + 136u + 126u));
    EXPECT_EQ(B::controlReserveEntries(4096, 0), 3u + 26u + (3u + 136u + 136u + 126u));
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - edge + 1), 1000, 0, 0));
    EXPECT_TRUE(B::permitsOptionalWrite(used(630 - edge), 1000, 0, 0));
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - edge), 1000, 0, 0, {}, 1)) << "the priority reserve";
    auto bad = used(100); bad.valid = false;
    EXPECT_FALSE(B::permitsOptionalWrite(bad, 100, 0, 0));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 0, 0, 0));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 5000, 0, 0));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 5000, 0));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, 3000));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, 0, {SIZE_MAX, 0, 0}));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, 0, {}, SIZE_MAX));
}
TEST(ControlPartitionBudget, ALargerPlanOrBluetoothSaveErasesTheOptionalRecordsLeastUsefulFirst) {
    // An NVS filled by rc.2 before this fix (every optional record, no budget): a larger plan
    // makes room by erasing the learned rooms first, then what else it needs.
    std::map<std::string, size_t> nvs;
    for (const auto& r : worstCase()) nvs[r.key] = B::blobEntries(r.bytes);
    const size_t fixed = baselineUsed + B::blobEntries(B::flowRecordBytes) - B::blobEntries(96);
    const auto stats = [&] { size_t n = fixed; for (const auto& [k, e] : nvs) n += e; return used(std::min<size_t>(n, 630)); };
    std::vector<std::string> erased;
    const auto erase = [&](const char* key) { if (nvs.erase(key)) erased.push_back(key); };
    const auto bytes = [&](const char* key) -> size_t { for (const auto& r : worstCase()) if (nvs.count(key) && r.key == std::string(key)) return r.bytes; return 0; };
    const auto plan = [](size_t bytes) { return [=](ControlPartitionStats s) { return B::permitsHeatingPlanWrite(s, bytes); }; };
    EXPECT_FALSE(plan(2000)(stats()));
    ASSERT_TRUE(B::makeRoom(plan(2000), stats, bytes, erase));
    EXPECT_TRUE(plan(2000)(stats()));
    ASSERT_FALSE(erased.empty());
    EXPECT_EQ(erased.front(), "learned7");
    EXPECT_TRUE(nvs.count("autotune")) << "the knobs stay while the rooms make room";
    ASSERT_TRUE(B::makeRoom([](ControlPartitionStats s) { return B::permitsBluetoothWrite(s, 2048); }, stats, bytes, erase));
    ASSERT_TRUE(B::makeRoom(plan(4096), stats, bytes, erase));
    EXPECT_TRUE(plan(4096)(stats()));
    std::printf("[ nvs ] a 4 KB plan erased %zu record(s), %zu free\n", erased.size(), stats().freeEntries);
    // Nothing left to erase and still too full (another owner of the partition): refused.
    nvs.clear(); erased.clear();
    EXPECT_FALSE(B::makeRoom(plan(4096), [] { return used(630 - 300); }, bytes, erase));
    EXPECT_EQ(erased.size(), 0u);
    // Records that could not make the room even all together are kept; unknown statistics erase nothing.
    for (const auto& r : worstCase()) nvs[r.key] = B::blobEntries(r.bytes);
    EXPECT_FALSE(B::makeRoom(plan(4096), [] { return used(629); }, bytes, erase));
    EXPECT_FALSE(B::makeRoom(plan(600), [] { ControlPartitionStats s = used(600); s.valid = false; return s; }, bytes, erase));
    EXPECT_EQ(erased.size(), 0u);
    EXPECT_EQ(nvs.size(), worstCase().size());
}
