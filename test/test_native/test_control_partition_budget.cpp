#include <gtest/gtest.h>
#include "control/ControlPartitionBudget.h"
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
