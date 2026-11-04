#include <gtest/gtest.h>
#include "control/ControlPartitionBudget.h"
#include "control/AutoTuner.h"
#include "control/DhwEpisodes.h"
#include "control/FlowPolicy.h"
#include "control/LearnedState.h"
#include "control/OptionalRecordPriority.h"
#include "control/Scoreboard.h"
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
// The optional records (rc.2 learned-room review): the readiness counters, the knobs with a
// full log and what was learned as one packed record (LearnedStore: the global frame and the
// rooms' version 2 frames, at most 4000 bytes a part). rc.4 (review S3): the hot water days
// ("dhw", DhwNvs, at most DhwEpisodes::recordBytes) and the daily scoreboard ("scoreboard",
// ScoreboardNvs, at most Scoreboard::storedMaxBytes with its NUL), both written hourly with
// priority 0 like the readiness and the knobs, before the 6-hourly learned record.
struct Record { const char* key; size_t bytes; };
constexpr size_t globalBytes = 300;                                   // measured 240 (test_learned_state)
constexpr size_t typicalRoom = LearnedState::compactRoomBytes(10, 6);  // 6 bins with the outdoor: 190 B
constexpr size_t worstRoom = LearnedState::compactRoomBytes(32, 0, FlowLearner::binCount); // 558 B
std::vector<Record> typical() {
    return {{"readiness", sizeof(TakeoverReadiness::Stored)}, {"autotune", AutoTuner::storedMaxBytes + 1},
            {"dhw", DhwEpisodes::recordBytes}, {"scoreboard", Scoreboard::storedMaxBytes + 1},
            {"learned_a", globalBytes + 8 * typicalRoom}};
}
std::vector<Record> worstCase() {
    // Whole frames per part: the globals and 6 rooms, then 2 rooms.
    static_assert(globalBytes + 6 * worstRoom <= LearnedStore::partBytes && globalBytes + 7 * worstRoom > LearnedStore::partBytes);
    return {{"readiness", sizeof(TakeoverReadiness::Stored)}, {"autotune", AutoTuner::storedMaxBytes + 1},
            {"dhw", DhwEpisodes::recordBytes}, {"scoreboard", Scoreboard::storedMaxBytes + 1},
            {"learned_a", globalBytes + 6 * worstRoom}, {"learned_b", 2 * worstRoom}};
}
}
// rc.4 (review S3): the scoreboard holds only today and yesterday, the least valuable record on the
// device, so a save that needs room erases it first; the hot water days are an optional record too.
TEST(ControlPartitionBudget, TheScoreboardIsTheFirstOptionalRecordToGoAndTheHotWaterDaysAreOne) {
    ASSERT_GE(B::optionalKeyCount, 2u);
    EXPECT_STREQ(B::optionalKeys[0], "scoreboard");
    bool dhw = false, learned = false, knobs = false;
    for (const char* key : B::optionalKeys) { dhw = dhw || !std::strcmp(key, "dhw"); learned = learned || !std::strcmp(key, "learned_a"); knobs = knobs || !std::strcmp(key, "autotune"); }
    EXPECT_TRUE(dhw); EXPECT_TRUE(learned); EXPECT_TRUE(knobs);
    EXPECT_STREQ(B::optionalKeys[B::optionalKeyCount - 1], "autotune") << "the knobs go last";
    for (const auto& r : worstCase()) {  // every record in the budget is an optional key, and the sizes are their bounds
        bool listed = false;
        for (const char* key : B::optionalKeys) listed = listed || !std::strcmp(key, r.key);
        EXPECT_TRUE(listed) << r.key;
    }
    // rc.5 (P2): 287 B with the Insights' baselines (rc.4: 240 B, 14 entries): the widest record is 213 B of days
    // and 65 B of baselines (test_scoreboard.cpp); 16 entries would cost the owner's unit its learned record.
    EXPECT_EQ(B::blobEntries(Scoreboard::storedMaxBytes + 1), 15u);
    EXPECT_EQ(B::blobEntries(DhwEpisodes::recordBytes), 22u);
}
TEST(ControlPartitionBudget, OptionalRecordsAlwaysLeaveRoomForThePlanHandoverAndBluetooth) {
    const size_t flowGrowth = B::blobEntries(B::flowRecordBytes) - B::blobEntries(96); // beta.19 flow record: <= 95 bytes
    size_t ungated = baselineUsed + flowGrowth;
    for (const auto& r : worstCase()) ungated += B::blobEntries(r.bytes);
    std::printf("[ nvs ] baseline %zu used + flow growth %zu + optional worst case %zu = %zu of 630 (GC page 126)\n",
                baselineUsed, flowGrowth, ungated - baselineUsed - flowGrowth, ungated);
    // Stored plan and control record sizes; the Bluetooth save is always charged at 2 KB.
    // Control record: 0 none, ~0.2 KB the Home Assistant session without rooms (E32 room-plan
    // mode), larger with Home Assistant rooms; `graph`: a graph/native profile (full 4 KB).
    struct Case { size_t plan, control; bool graph; };
    const Case cases[] = {{600, 200, false}, {930, 200, false}, {930, 0, false}, {2000, 1200, false}, {3000, 4000, false},
                          {4096, 200, false}, {930, 1200, true}};
    for (const bool worst : {true, false})
    for (const auto& c : cases) {
        const auto records = worst ? worstCase() : typical();
        const size_t control = B::controlReplacementEntries(c.control, c.graph);
        const size_t reserve = B::controlReserveEntries(c.plan, control);
        size_t n = baselineUsed + flowGrowth;
        std::string kept;
        for (const auto& r : records) {
            // As LearnedNvs and AutoTunerNvs: what was learned after the knobs and the readiness,
            // the knobs' log after what was learned (else the values only). rc.4: the hot water
            // days and the scoreboard (DhwNvs, ScoreboardNvs) with priority 0, hourly, before the learned record.
            const bool knobs = !std::strcmp(r.key, "autotune");
            size_t bytes = r.bytes, priority = r.key[0] == 'l' ? OptionalRecordPriority::learned(kept.find("autotune") != std::string::npos, kept.find("readiness") != std::string::npos) : 0;
            if (knobs && !B::permitsOptionalWrite(used(n), bytes, 0, reserve, priority)) { bytes = OptionalRecordPriority::knobsBytes; priority = 0; }
            if (!std::strcmp(r.key, "learned_b") && kept.find("learned_a") == std::string::npos) continue; // whole frames in order
            if (!B::permitsOptionalWrite(used(n), bytes, 0, reserve, priority)) continue;
            n += B::blobEntries(bytes); kept += std::string(r.key) + (bytes < r.bytes ? "(values) " : " ");
        }
        std::printf("[ nvs ] %s plan %4zu B, control %4zu B%s: reserve %zu; written: %s-> %zu used, %zu free\n",
                    worst ? "worst case:" : "typical:   ", c.plan, c.control, c.graph ? " (graph)" : "", reserve, kept.c_str(), n, 630 - n);
        // The invariant: a plan save of the stored size plus an edit, a 2 KB Bluetooth save, the
        // handover confirmation, the largest flow record and the control record's replacement fit.
        EXPECT_TRUE(B::permitsHeatingPlanWrite(used(n), std::min(c.plan + B::editBytes, B::configBytes), {}, control)) << c.plan;
        EXPECT_TRUE(B::permitsBluetoothWrite(used(n), B::bluetoothBytes, {}, control)) << c.plan;
        EXPECT_GE(630 - n, B::handoverEntries + B::blobEntries(B::flowRecordBytes) + B::entriesPerPage) << c.plan;
        if (c.graph) { EXPECT_TRUE(B::permitsGraphWrite(used(n), B::configBytes)); }
        else { EXPECT_GE(630 - n, 2 + B::blobEntries(std::min(c.control + B::editBytes, B::configBytes)) + B::entriesPerPage); }
        EXPECT_LE(n, 630u - B::entriesPerPage) << "never physically full";
        // The owner's unit (plan ~0.93 KB, a session without rooms): everything is kept, the
        // learned rooms beside the hourly records (rc.4: the hot water days and the scoreboard;
        // rc.5: the scoreboard with the Insights' baselines, 15 entries), and at least 200 entries stay free.
        if (c.plan == 930 && c.control <= 200 && !c.graph && !worst) {
            EXPECT_EQ(kept, "readiness autotune dhw scoreboard learned_a ")
                << "the owner's unit: " << 630 - n << " free after the records written, the learned record (" << typical().back().bytes
                << " B) needs 1 + " << B::blobEntries(typical().back().bytes) << " entries beside the reserve of " << reserve;
            EXPECT_GE(630 - n, 200u) << "the owner's unit keeps at least 200 free entries";
        }
    }
    // The gate itself: the edge, the record it replaces, invalid stats, sizes and reservations.
    EXPECT_EQ(B::controlReplacementEntries(0, false), 8u);
    EXPECT_EQ(B::controlReplacementEntries(200, false), 15u);
    EXPECT_EQ(B::controlReplacementEntries(200, true), 136u);
    EXPECT_EQ(B::controlReplacementEntries(4090, false), 136u);
    EXPECT_EQ(B::controlReserveEntries(0, 8), 3u + 26u + (3u + 70u + 8u + 126u));    // handover, flow, a 2 KB Bluetooth save
    EXPECT_EQ(B::controlReserveEntries(4096, 136), 3u + 26u + (3u + 136u + 136u + 126u));
    EXPECT_EQ(B::previousFirmwareReserveEntries(0, 0), 3u + 26u + (3u + 8u + 136u + 126u)); // rc2-fw-review2's ledger
    EXPECT_EQ(B::previousFirmwareReserveEntries(0, 2048), 3u + 26u + (3u + 70u + 136u + 126u));
    EXPECT_EQ(B::previousFirmwareReserveEntries(4096, 0), 3u + 26u + (3u + 136u + 136u + 126u));
    const size_t reserve = B::controlReserveEntries(930, 13);
    const size_t edge = 1 + B::blobEntries(1000) + reserve;
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - edge + 1), 1000, 0, reserve));
    EXPECT_TRUE(B::permitsOptionalWrite(used(630 - edge), 1000, 0, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - edge), 1000, 0, reserve, 1)) << "the priority reserve";
    // Replacing a record: its old entries come back (counted at their smallest, 1 + 1 per 32 bytes).
    EXPECT_TRUE(B::permitsOptionalWrite(used(630 - edge + 33), 1000, 1000, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - edge + 34), 1000, 1000, reserve));
    // ...but the new record must still be written beside it, with the GC page.
    EXPECT_FALSE(B::permitsOptionalWrite(used(630 - (1 + B::blobEntries(4000) + B::entriesPerPage) + 1), 4000, 4000, 0));
    EXPECT_TRUE(B::permitsOptionalWrite(used(630 - (1 + B::blobEntries(4000) + B::entriesPerPage)), 4000, 4000, 0));
    auto bad = used(100); bad.valid = false;
    EXPECT_FALSE(B::permitsOptionalWrite(bad, 100, 0, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 0, 0, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 5000, 0, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 5000, reserve));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, B::controlReserveEntries(930, 13, {SIZE_MAX, 0, 0})));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, B::controlReserveEntries(930, 137)));
    EXPECT_FALSE(B::permitsOptionalWrite(used(100), 100, 0, reserve, SIZE_MAX));
    // This firmware's plan and Bluetooth gates with the stored control record's replacement;
    // the default (a full 4 KB one) is the gate of every firmware before rc.2.
    EXPECT_EQ(B::planSaveEntries(2048, {}, 13), 3u + 70u + 13u + 126u);
    EXPECT_TRUE(B::permitsBluetoothWrite(used(630 - 212), 2048, {}, 13));
    EXPECT_FALSE(B::permitsBluetoothWrite(used(630 - 211), 2048, {}, 13));
    EXPECT_FALSE(B::permitsBluetoothWrite(used(630 - 212), 2048));
    EXPECT_FALSE(B::permitsBluetoothWrite(used(100), 2048, {}, 137));
}
// rc.4: the owner's holiday planner ("holidays", at most 224 bytes with its NUL) is written while
// control keeps its room after it, and like a plan save it makes room for itself: on an NVS that
// what was learned filled up to control's reserve, the learned rooms give way (never the knobs or
// the record itself); without anything to erase it is refused and nothing changes.
TEST(ControlPartitionBudget, TheHolidaysRecordMakesRoomForItselfLikeAPlanSave) {
    const size_t reserve = B::controlReserveEntries(930, B::controlReplacementEntries(200, false));
    EXPECT_FALSE(B::permitsHolidayWrite(used(630 - reserve), 224, 0, reserve)) << "no room left beside control's";
    EXPECT_TRUE(B::permitsHolidayWrite(used(630 - reserve - 1 - B::blobEntries(224)), 224, 0, reserve));
    EXPECT_FALSE(B::permitsHolidayWrite(used(100), 225, 0, reserve)) << "never larger than its bound";
    // Its replacement needs only its growth (the old one comes back).
    EXPECT_TRUE(B::permitsHolidayWrite(used(630 - reserve - 1 - B::blobEntries(224) + B::reclaimEntries(224)), 224, 224, reserve));
    std::map<std::string, size_t> nvs;
    for (const auto& r : worstCase()) nvs[r.key] = B::blobEntries(r.bytes);
    const size_t fill = 630 - reserve - [&] { size_t n = 0; for (const auto& [k, e] : nvs) n += e; return n; }();
    const auto stats = [&] { size_t n = fill; for (const auto& [k, e] : nvs) n += e; return used(std::min<size_t>(n, 630)); };
    std::vector<std::string> erased;
    const auto erase = [&](const char* key) { if (nvs.erase(key)) erased.push_back(key); };
    const auto bytes = [&](const char* key) -> size_t { for (const auto& r : worstCase()) if (nvs.count(key) && r.key == std::string(key)) return r.bytes; return 0; };
    const auto holidays = [&](ControlPartitionStats s) { return B::permitsHolidayWrite(s, 215, 0, reserve); };
    EXPECT_FALSE(holidays(stats()));
    ASSERT_TRUE(B::makeRoom(holidays, stats, bytes, erase));
    EXPECT_TRUE(holidays(stats()));
    // rc.4 (S3): the scoreboard (today and yesterday only) goes first; the learned rooms stay.
    ASSERT_EQ(erased, std::vector<std::string>{"scoreboard"});
    EXPECT_TRUE(nvs.count("autotune") && nvs.count("readiness") && nvs.count("learned_a") && nvs.count("learned_b") && nvs.count("dhw"));
    nvs.clear(); erased.clear();
    EXPECT_FALSE(B::makeRoom(holidays, [&] { return used(630 - reserve); }, bytes, erase));
    EXPECT_TRUE(erased.empty());
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
    // rc.4 (S3): the scoreboard and the hot water days (today and yesterday, counts) before the learned rooms.
    ASSERT_GE(erased.size(), 3u);
    EXPECT_EQ(erased[0], "scoreboard"); EXPECT_EQ(erased[1], "dhw"); EXPECT_EQ(erased[2], "learned_b");
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
// Review R1-06: the owner's records beside the plan ("comfort": overrides and away, at most 768
// bytes; "trv": the radiator valves, at most 2 KB) and the "owned" note were written without the
// ledger, so a plan or Bluetooth save could end in storage_full with nothing optional left to
// erase. rc.4 gates them like an optional record (NvsOptionalRecords.h userHeatingRecordFits:
// control's reserve stays free after them), but before what was learned: optional records are
// erased first when that makes their room. The notes ("owned", "takeover_test") are gated without
// erasing anything (HeatingNoteNvs::writeGated).
TEST(ControlPartitionBudget, TheOwnersRecordsKeepThePlanSaveAndMakeRoomFromWhatWasLearned) {
    constexpr size_t comfortBytes = 768 + 1, trvBytes = 2048 + 1, noteBytes = 64;
    // The finding at its edge: nothing optional left to erase, exactly control's reserve free.
    {
        const size_t control = B::controlReplacementEntries(200, false), reserve = B::controlReserveEntries(930, control);
        const size_t full = 630 - reserve, comfort = B::blobEntries(comfortBytes);
        const auto ble = [&](size_t n) { return B::permitsBluetoothWrite(used(n), B::bluetoothBytes, {}, control); };
        ASSERT_TRUE(ble(full));
        EXPECT_FALSE(ble(full + 1 + comfort)) << "written without the ledger, comfort takes the private save's room";
        EXPECT_FALSE(B::permitsOptionalWrite(used(full), comfortBytes, 0, reserve)) << "the gate refuses it instead";
        EXPECT_TRUE(B::permitsOptionalWrite(used(full - 1 - comfort), comfortBytes, 0, reserve));
        EXPECT_TRUE(ble(full - 1 - comfort + 1 + comfort));
    }
    // The worst case: every optional record its gate lets in, then comfort, the valves and both notes at their largest.
    struct Case { size_t plan, control; bool graph; };
    const Case cases[] = {{600, 200, false}, {930, 200, false}, {930, 0, false}, {2000, 1200, false}, {3000, 4000, false},
                          {4096, 200, false}, {930, 1200, true}};
    const size_t fixed = baselineUsed + B::blobEntries(B::flowRecordBytes) - B::blobEntries(96);
    for (const auto& c : cases) {
        const size_t control = B::controlReplacementEntries(c.control, c.graph), reserve = B::controlReserveEntries(c.plan, control);
        std::map<std::string, size_t> nvs; // key -> stored bytes
        const auto stats = [&] { size_t n = fixed; for (const auto& [k, b] : nvs) n += B::blobEntries(b); return used(std::min<size_t>(n, 630)); };
        const auto bytes = [&](const char* key) -> size_t { const auto it = nvs.find(key); return it == nvs.end() ? 0 : it->second; };
        std::vector<std::string> erased;
        const auto erase = [&](const char* key) { if (nvs.erase(key)) erased.push_back(key); };
        for (const auto& r : worstCase())
            if ((std::strcmp(r.key, "learned_b") || nvs.count("learned_a")) && B::permitsOptionalWrite(stats(), r.bytes, 0, reserve)) nvs[r.key] = r.bytes;
        const auto user = [&](const char* key, size_t size) { // userHeatingRecordFits, then the write
            const auto kept = nvs; const size_t old = bytes(key);
            if (!B::makeRoom([&](ControlPartitionStats s) { return B::permitsOptionalWrite(s, size, old, reserve); }, stats, bytes, erase)) {
                EXPECT_EQ(nvs, kept) << key << ": refused, nothing erased";
                return false;
            }
            nvs[key] = size;
            return true;
        };
        const auto note = [&](const char* key) { // HeatingNoteNvs::writeGated
            if (!B::permitsOptionalWrite(stats(), noteBytes, bytes(key), reserve)) return false;
            nvs[key] = noteBytes;
            return true;
        };
        const bool comfort = user("comfort", comfortBytes), valves = user("trv", trvBytes);
        const bool owned = note("owned"), test = note("takeover_test");
        std::string kept;
        for (const auto& [k, b] : nvs) kept += k + " ";
        std::printf("[ nvs ] plan %4zu B, control %4zu B%s: reserve %zu; comfort %d, valves %d, owned %d, test %d; erased %zu; kept: %s-> %zu free\n",
                    c.plan, c.control, c.graph ? " (graph)" : "", reserve, comfort, valves, owned, test, erased.size(), kept.c_str(), stats().freeEntries);
        for (const auto& k : erased) // optional records only (rc.4: the scoreboard and the hot water days are two)
            EXPECT_TRUE(k.rfind("learned", 0) == 0 || k == "readiness" || k == "autotune" || k == "scoreboard" || k == "dhw") << k;
        EXPECT_EQ(nvs.count("comfort"), size_t(comfort));
        // The invariant: the plan saved again at its size plus an edit, a 2 KB Bluetooth save,
        // the handover and the largest flow record still fit, with the GC page.
        EXPECT_TRUE(B::permitsHeatingPlanWrite(stats(), std::min(c.plan + B::editBytes, B::configBytes), {}, control)) << c.plan;
        EXPECT_TRUE(B::permitsBluetoothWrite(stats(), B::bluetoothBytes, {}, control)) << c.plan;
        EXPECT_GE(stats().freeEntries, B::handoverEntries + B::blobEntries(B::flowRecordBytes) + B::entriesPerPage) << c.plan;
        // The owner's unit (plan ~0.93 KB, a session without rooms): the overrides and the valves are kept.
        if (c.plan == 930 && c.control <= 200 && !c.graph) { EXPECT_TRUE(comfort); EXPECT_TRUE(valves); }
    }
}
