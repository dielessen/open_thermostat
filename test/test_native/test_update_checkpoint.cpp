#include <gtest/gtest.h>
#include "update/UpdateCheckpoint.h"
#include <limits>
using namespace heating::update;
namespace {
struct Storage {
    UpdateCheckpoint bytes{};
    bool present=false,writeOk=true;
    unsigned reads=0,writes=0;
    bool read(UpdateCheckpoint &out){++reads;out=bytes;return present;}
    bool write(const UpdateCheckpoint &value){++writes;if(!writeOk)return false;bytes=value;present=true;return true;}
};
constexpr auto from="v0.1.0-e32v2-alpha.26",target="v0.1.0-e32v2-alpha.27";
const std::string source(40,'a');
}
TEST(UpdateCheckpoint, SavedAttemptSurvivesReconstructionWithoutInventingBootSuccess) {
    Storage storage;
    {UpdateCheckpointJournal journal(storage);EXPECT_EQ(journal.saved(),nullptr);
     ASSERT_TRUE(journal.begin(from,source,target));
     ASSERT_TRUE(journal.advance(UpdateStage::Download,0,1024,200));
     ASSERT_TRUE(journal.advance(UpdateStage::Verify,1024,1024,200));
     ASSERT_TRUE(journal.advance(UpdateStage::Selected,1024,1024,200));}
    UpdateCheckpointJournal rebooted(storage);ASSERT_NE(rebooted.saved(),nullptr);
    EXPECT_EQ(rebooted.saved()->attempt,1u);
    EXPECT_STREQ(rebooted.saved()->targetVersion,target);
    EXPECT_STREQ(updateStageName(rebooted.saved()->stage),"boot_slot_selected");
    EXPECT_EQ(storage.writes,4u); // No write on boot or status.
    for(int i=0;i<100;++i)ASSERT_NE(rebooted.saved(),nullptr);
    EXPECT_EQ(storage.writes,4u);EXPECT_EQ(storage.reads,2u);
}
TEST(UpdateCheckpoint, FailureRemainsVisibleAfterRebootAndCheckOnlyDoesNotEraseIt) {
    Storage storage;UpdateCheckpointJournal journal(storage);
    ASSERT_TRUE(journal.begin(from,source,target));
    ASSERT_TRUE(journal.advance(UpdateStage::Error,512,1024,-11));
    UpdateCheckpointJournal rebooted(storage);auto saved=rebooted.saved();ASSERT_NE(saved,nullptr);
    EXPECT_EQ(saved->stage,UpdateStage::Error);EXPECT_EQ(saved->received,512u);
    EXPECT_EQ(saved->httpStatus,-11);EXPECT_EQ(storage.writes,2u);
}
TEST(UpdateCheckpoint, FailedWritePreservesPreviousSavedStageAndDoesNotAttributeNewAttempt) {
    Storage storage;UpdateCheckpointJournal journal(storage);
    ASSERT_TRUE(journal.begin(from,source,target));
    ASSERT_TRUE(journal.advance(UpdateStage::Selected,1024,1024,200));
    storage.writeOk=false;
    EXPECT_FALSE(journal.begin(target,source,"v0.1.0-e32v2-alpha.28"));
    EXPECT_TRUE(journal.saveFailed());
    EXPECT_FALSE(journal.advance(UpdateStage::Error,0,0,-1));
    EXPECT_EQ(journal.saved()->attempt,1u);
    EXPECT_EQ(journal.saved()->stage,UpdateStage::Selected);
    EXPECT_STREQ(journal.saved()->targetVersion,target);
    EXPECT_EQ(storage.writes,3u);
    storage.writeOk=true;ASSERT_TRUE(journal.begin(target,source,"v0.1.0-e32v2-alpha.28"));
    EXPECT_FALSE(journal.saveFailed());EXPECT_EQ(journal.saved()->attempt,2u);
}
TEST(UpdateCheckpoint, CorruptIncompatibleOrUnterminatedStorageBecomesUnknown) {
    Storage good;{UpdateCheckpointJournal journal(good);ASSERT_TRUE(journal.begin(from,source,target));}
    for(int fault=0;fault<12;++fault){Storage bad=good;
        switch(fault){
        case 0:bad.bytes.schema=2;break;
        case 1:bad.bytes.attempt=0;break;
        case 2:bad.bytes.stage=static_cast<UpdateStage>(99);break;
        case 3:bad.bytes.total=maxImageBytes+1;break;
        case 4:bad.bytes.received=1;break;
        case 5:bad.bytes.httpStatus=600;break;
        case 6:std::memset(bad.bytes.targetVersion,'v',sizeof(bad.bytes.targetVersion));break;
        case 7:std::memset(bad.bytes.fromSource,'a',sizeof(bad.bytes.fromSource));break;
        case 8:bad.bytes.fromSource[0]='z';break;
        case 9:bad.bytes.reserved[0]=1;break;
        case 10:bad.bytes.httpStatus=-32769;break;
        case 11:bad.bytes.fromVersion[0]='x';break;
        }
        UpdateCheckpointJournal journal(bad);EXPECT_EQ(journal.saved(),nullptr)<<fault;
        EXPECT_FALSE(journal.advance(UpdateStage::Selected,1024,1024,200));
        EXPECT_EQ(bad.writes,good.writes);
    }
}
TEST(UpdateCheckpoint, InvalidNewInputsCannotWriteOrTruncateIntoAValidIdentity) {
    for(const auto &bad:{std::string(48,'v'),std::string("v1/secret"),std::string("v1\n")}) {
        Storage storage;UpdateCheckpointJournal journal(storage);
        EXPECT_FALSE(journal.begin(from,source,bad));EXPECT_EQ(storage.writes,0u);
        EXPECT_EQ(journal.saved(),nullptr);
    }
    Storage storage;UpdateCheckpointJournal journal(storage);
    EXPECT_FALSE(journal.begin(from,std::string(41,'a'),target));EXPECT_EQ(storage.writes,0u);
}
TEST(UpdateCheckpoint, InvalidProgressCannotReplaceLastDurableReceipt) {
    Storage storage;UpdateCheckpointJournal journal(storage);
    ASSERT_TRUE(journal.begin(from,source,target));
    EXPECT_FALSE(journal.advance(UpdateStage::Verify,1025,1024,200));
    EXPECT_EQ(journal.saved()->stage,UpdateStage::Manifest);EXPECT_TRUE(journal.saveFailed());
    EXPECT_EQ(storage.writes,1u);
}
TEST(UpdateCheckpoint, AttemptCounterWrapIsBoundedAndNeverUsesUnknownSentinel) {
    Storage storage;{UpdateCheckpointJournal journal(storage);ASSERT_TRUE(journal.begin(from,source,target));}
    storage.bytes.attempt=std::numeric_limits<uint32_t>::max();
    UpdateCheckpointJournal journal(storage);ASSERT_TRUE(journal.begin(from,source,target));
    EXPECT_EQ(journal.saved()->attempt,1u);
}

TEST(UpdateCheckpoint, LegacyStageNumbersAndBlobLayoutRetainTheirMeaning) {
    EXPECT_EQ(sizeof(UpdateCheckpoint),164u);
    unsigned value=1;
    for(const auto stage:{UpdateStage::Manifest,UpdateStage::Download,UpdateStage::Verify,
            UpdateStage::Selected,UpdateStage::Error}) {
        EXPECT_EQ(static_cast<unsigned>(stage),value++);
        Storage storage;{UpdateCheckpointJournal journal(storage);ASSERT_TRUE(journal.begin(from,source,target));}
        storage.bytes.stage=stage;
        UpdateCheckpointJournal legacy(storage);ASSERT_NE(legacy.saved(),nullptr);
        EXPECT_EQ(legacy.saved()->stage,stage);EXPECT_EQ(storage.writes,1u);
    }
}
TEST(UpdateCheckpoint, PreOperationStageSurvivesRebootWithoutClaimingCompletion) {
    for(const auto &stage:std::vector<std::pair<UpdateStage,const char*>>{
        {UpdateStage::Hash,"before_hash_verification"},{UpdateStage::Image,"before_image_validation"},
        {UpdateStage::Readback,"before_flash_readback"},{UpdateStage::Selecting,"before_boot_slot_selection"}}) {
        Storage storage;
        {UpdateCheckpointJournal journal(storage);ASSERT_TRUE(journal.begin(from,source,target));
         ASSERT_TRUE(journal.advance(stage.first,1024,1024,200));}
        UpdateCheckpointJournal rebooted(storage);ASSERT_NE(rebooted.saved(),nullptr);
        EXPECT_EQ(rebooted.saved()->stage,stage.first);
        EXPECT_STREQ(updateStageName(rebooted.saved()->stage),stage.second);
        EXPECT_NE(rebooted.saved()->stage,UpdateStage::Selected);
        EXPECT_EQ(storage.writes,2u);
        for(unsigned i=0;i<20;++i)ASSERT_NE(rebooted.saved(),nullptr);
        EXPECT_EQ(storage.writes,2u);
    }
}
TEST(UpdateCheckpoint, FailedDetailedStageSaveDoesNotInventProgress) {
    Storage storage;UpdateCheckpointJournal journal(storage);
    ASSERT_TRUE(journal.begin(from,source,target));
    ASSERT_TRUE(journal.advance(UpdateStage::Hash,1024,1024,200));
    storage.writeOk=false;
    EXPECT_FALSE(journal.advance(UpdateStage::Image,1024,1024,200));
    EXPECT_FALSE(journal.advance(UpdateStage::Selecting,1024,1024,200));
    EXPECT_EQ(journal.saved()->stage,UpdateStage::Hash);EXPECT_TRUE(journal.saveFailed());
    EXPECT_EQ(storage.writes,3u);
    UpdateCheckpointJournal rebooted(storage);ASSERT_NE(rebooted.saved(),nullptr);
    EXPECT_EQ(rebooted.saved()->stage,UpdateStage::Hash);
}
