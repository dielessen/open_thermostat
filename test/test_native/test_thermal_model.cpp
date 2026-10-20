#include <gtest/gtest.h>
#include "control/ThermalModelStore.h"
#include "ControlTestHash.h"
using namespace heating::control;
namespace {
constexpr int64_t epoch=1790812800; // 2026-10-01 UTC; synthetic clock only.
auto binding() {std::array<uint8_t,32>b{};b[0]=42;return b;}
ThermalModelProfile profile() {
    ThermalModelProfile p;p.reviewed=true;p.maximumGapMs=120000;p.minimumOffSec=1800;
    p.minimumRunSec=900;p.maximumRunSec=7200;p.minimumRiseCentiC=50;p.maximumRiseCentiC=500;
    p.minimumRateCentiCPerHour=10;p.maximumRateCentiCPerHour=3000;
    p.outdoorDriftCentiC=50;p.waterDriftCentiC=100;p.minimumStarts=6;p.minimumDistinctDays=6;
    p.minimumSpanDays=14;p.maximumAgeDays=60;p.minimumComparableStarts=3;
    p.comparableOutdoorRadiusCentiC=100;p.comparableWaterRadiusCentiC=100;p.comparableRoomRadiusCentiC=50;
    p.minimumOutdoorSpanCentiC=200;p.maximumLeadSec=7200;return p;
}
struct Rig {
    ThermalResponseModel m{profile(),binding()};ThermalObservation in{};
    Rig() {m.setMode(LearningMode::shadow);in.profileQualified=in.sourceVerified=in.conditionsKnown=true;
        in.deliveryKnown=in.clockTrusted=in.normalControl=true;in.admissionEpoch=1;in.targetGeneration=1;
        in.utc=epoch;in.temperatureCentiC=1900;in.outdoorCentiC=500;in.waterCentiC=4500;}
    bool sample(uint32_t seconds=60) {in.monotonicMs+=seconds*1000;in.utc+=seconds;++in.reportSequence;return m.observe(in);}
    void off() {in.deliveredHeat=false;in.temperatureCentiC=1900;for(int i=0;i<31;++i)sample();}
    bool run() {off();in.deliveredHeat=true;sample();
        for(int i=1;i<20;++i){in.temperatureCentiC=1900+i*10;sample();}
        in.deliveredHeat=false;in.temperatureCentiC=2100;return sample();}
    void train() {
        for(int i=0;i<6;++i) {in.utc=epoch+i*3*86400;in.monotonicMs=i*uint64_t(3)*86400000;
            in.outdoorCentiC=i<3?500:700;in.admissionEpoch=i+1;ASSERT_TRUE(run());}
    }
    void fresh() {in.admissionEpoch+=1;in.deliveredHeat=false;in.temperatureCentiC=1900;in.outdoorCentiC=500;
        in.utc=epoch+16*86400;in.monotonicMs=16ULL*86400000;sample();}
    ScheduleTarget schedule(int64_t lead=3600,int16_t target=2100) {return {ScheduleState::active,1900,ScheduleTransition{in.utc+lead,target}};}
    StartAdvisory advise(int16_t water=4500) {return m.propose(in.monotonicMs,in.utc,schedule(),water);}
};
std::string sha(std::string_view bytes) {return controlTestHash(bytes);}
struct Store:ControlStore {
    std::string data;bool readOk=true,writeOk=true,commitOnFailure=false,corrupt=false;int writes=0;
    bool load(std::string& out)override {out=data;return readOk;}
    bool save(std::string_view bytes)override {++writes;if(writeOk||commitOnFailure)data=bytes;if(corrupt&&!data.empty())data[0]='X';return writeOk;}
};
TEST(ThermalModel, DefaultsAndUnreviewedProfileCannotTrain) {
    ThermalResponseModel m(profile(),binding());Rig r;r.sample();EXPECT_FALSE(m.observe(r.in));EXPECT_EQ(m.snapshot().count,0);
    auto p=profile();p.reviewed=false;ThermalResponseModel invalid(p,binding());invalid.setMode(LearningMode::shadow);
    EXPECT_FALSE(invalid.observe(r.in));EXPECT_FALSE(invalid.propose(r.in.monotonicMs,r.in.utc,r.schedule(),4500).plannedStartUtc);
    m.setMode(static_cast<LearningMode>(99));EXPECT_EQ(m.mode(),LearningMode::disabled);
}
TEST(ThermalModel, SixMeasuredStartsAcrossFifteenDaysGiveIndependentTwentyMinuteLead) {
    Rig r;r.train();r.fresh();const auto a=r.advise();ASSERT_TRUE(a.plannedStartUtc);
    EXPECT_EQ(a.leadSec,1200u);EXPECT_EQ(*a.plannedStartUtc,r.in.utc+2400);EXPECT_EQ(a.eligibleStarts,6);
    EXPECT_EQ(a.comparableStarts,3);EXPECT_EQ(a.distinctDays,6);EXPECT_EQ(a.coveredDays,15);EXPECT_FALSE(a.startNow);
}
TEST(ThermalModel, TimeAloneOrManyStartsSameDayIsNotEnough) {
    Rig r;r.run();r.in.utc+=16*86400;r.in.admissionEpoch++;r.sample();EXPECT_FALSE(r.advise().plannedStartUtc);
    Rig same;for(int i=0;i<6;++i)ASSERT_TRUE(same.run());EXPECT_FALSE(same.advise().plannedStartUtc);
}
TEST(ThermalModel, NoExtrapolationBeyondWeatherWaterRoomOrObservedRise) {
    Rig r;r.train();r.fresh();EXPECT_FALSE(r.advise(6000).plannedStartUtc);
    r.in.outdoorCentiC=-1000;r.sample();EXPECT_FALSE(r.advise().plannedStartUtc);
    r.in.outdoorCentiC=500;r.in.temperatureCentiC=1800;r.in.admissionEpoch++;r.sample();EXPECT_FALSE(r.advise().plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs,r.in.utc,r.schedule(3600,2300),4500).plannedStartUtc);
}
TEST(ThermalModel, CachedAndOlderEpochStayRejectedAfterRepeatedReadsAndModeChanges) {
    Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().plannedStartUtc);
    EXPECT_FALSE(r.m.observe(r.in));EXPECT_FALSE(r.m.observe(r.in));EXPECT_FALSE(r.advise().plannedStartUtc);
    r.m.setMode(LearningMode::shadow);EXPECT_FALSE(r.m.observe(r.in));EXPECT_FALSE(r.advise().plannedStartUtc);
    --r.in.admissionEpoch;r.in.reportSequence+=100;EXPECT_FALSE(r.m.observe(r.in));EXPECT_FALSE(r.advise().plannedStartUtc);
}
TEST(ThermalModel, SourceLossAndInvalidSampleAbortWithoutTraining) {
    for(int failure=0;failure<10;++failure) {
        Rig r;r.off();r.in.deliveredHeat=true;r.sample();r.in.temperatureCentiC=2000;r.sample();
        switch(failure) {case 0:r.in.dhw=true;break;case 1:r.in.windowOpen=true;break;case 2:r.in.fault=true;break;
        case 3:r.in.manualTest=true;break;case 4:r.in.unexplainedGain=true;break;case 5:r.in.sourceVerified=false;break;
        case 6:r.in.normalControl=false;break;case 7:r.in.deliveryKnown=false;break;case 8:r.in.waterCentiC.reset();break;
        case 9:r.in.clockTrusted=false;break;}
        EXPECT_FALSE(r.sample());EXPECT_EQ(r.m.snapshot().count,0);
    }
}
TEST(ThermalModel, GapClockJumpAndTargetChangeAbortRunAndBlockImmediateAdvisory) {
    for(int reason=0;reason<4;++reason) {
        Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().plannedStartUtc);
        switch(reason) {case 0:r.in.utc+=3600;break;case 1:r.in.targetGeneration++;break;
            case 2:r.in.monotonicMs+=300000;r.in.utc+=300;break;case 3:r.in.monotonicMs=0;break;}
        r.sample();EXPECT_FALSE(r.advise().plannedStartUtc);
    }
}
TEST(ThermalModel, FrozenAcceptsFreshEvidenceButNeverTrainsAndResetKeepsModeAndFence) {
    Rig r;r.train();r.m.setMode(LearningMode::frozen);r.fresh();EXPECT_TRUE(r.advise().plannedStartUtc);
    r.in.utc+=10000;r.in.monotonicMs+=10000000;r.in.admissionEpoch++;r.run();EXPECT_EQ(r.m.snapshot().count,6);
    r.m.reset();EXPECT_EQ(r.m.snapshot().count,0);EXPECT_EQ(r.m.mode(),LearningMode::frozen);
    EXPECT_FALSE(r.m.observe(r.in));EXPECT_FALSE(r.advise().plannedStartUtc);
}
TEST(ThermalModel, FreshUtcScheduleOnlyNoExpiredOrPastTransitionOrStaleSourceReplay) {
    Rig r;r.train();r.fresh();UtcSchedule s;ScheduleTransition t[]={{r.in.utc,1900},{r.in.utc+3600,2100}};
    ASSERT_TRUE(s.configure(r.in.utc,r.in.utc+7200,1900,t,2));
    EXPECT_TRUE(r.m.propose(r.in.monotonicMs,r.in.utc,s.target(r.in.utc,true),4500).plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs,r.in.utc,s.target(r.in.utc,false),4500).plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs,r.in.utc,s.target(r.in.utc+7200,true),4500).plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs,r.in.utc,r.schedule(-1),4500).plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs+120000,r.in.utc+120,r.schedule(),4500).plannedStartUtc);
    EXPECT_FALSE(r.m.propose(r.in.monotonicMs,INT64_MAX,r.schedule(),4500).plannedStartUtc);
}
TEST(ThermalModel, NoIndependentOffOrChangingWaterNeverAddsRecord) {
    Rig r;r.in.deliveredHeat=true;for(int i=0;i<21;++i){r.in.temperatureCentiC=1900+i*10;r.sample();}
    r.in.deliveredHeat=false;r.sample();EXPECT_EQ(r.m.snapshot().count,0);
    Rig drift;drift.off();drift.in.deliveredHeat=true;drift.sample();drift.in.waterCentiC=5000;drift.sample();
    drift.in.deliveredHeat=false;drift.sample();EXPECT_EQ(drift.m.snapshot().count,0);
}
TEST(ThermalModel, RestoredDataRequiresExactBindingValidRecordsAndNewAdmission) {
    Rig r;r.train();auto d=r.m.snapshot();ThermalResponseModel m(profile(),binding());ASSERT_TRUE(m.restore(d));
    EXPECT_EQ(m.mode(),LearningMode::disabled);EXPECT_FALSE(m.propose(r.in.monotonicMs,r.in.utc,r.schedule(),4500).plannedStartUtc);
    d.bindingDigest[1]++;EXPECT_FALSE(m.restore(d));d=r.m.snapshot();d.algorithmVersion=2;EXPECT_FALSE(m.restore(d));
    d=r.m.snapshot();d.runs[0].riseCentiC=1;EXPECT_FALSE(m.restore(d));d=r.m.snapshot();d.runs[1]=d.runs[0];EXPECT_FALSE(m.restore(d));
}
TEST(ThermalModel, RobustMedianSuppressesOneSlowOutlierAndRejectsExpiredHistory) {
    Rig r;r.train();auto data=r.m.snapshot();
    // Three comparable observed starts: 20min,20min,60min for 2C.
    data.runs[2].durationSec=3600;data.runs[2].endUtc=data.runs[2].startUtc+3600;
    ASSERT_TRUE(r.m.restore(data));r.m.setMode(LearningMode::shadow);r.fresh();
    EXPECT_EQ(r.advise().leadSec,1200u);
    r.in.admissionEpoch++;r.in.utc=epoch+80*86400;r.in.monotonicMs=80ULL*86400000;r.sample();
    EXPECT_FALSE(r.advise().plannedStartUtc);
}
TEST(ThermalModel, BoundedEmitterLeadRefusesClippingAndStartNowRemainsOnlyAdvice) {
    Rig r;r.train();auto data=r.m.snapshot();
    for(size_t i=0;i<data.count;++i) {data.runs[i].durationSec=7200;data.runs[i].endUtc=data.runs[i].startUtc+7200;}
    auto p=profile();p.maximumLeadSec=1800;ThermalResponseModel shortEmitter(p,binding());
    ASSERT_TRUE(shortEmitter.restore(data));shortEmitter.setMode(LearningMode::shadow);r.fresh();
    shortEmitter.observe(r.in);
    EXPECT_FALSE(shortEmitter.propose(r.in.monotonicMs,r.in.utc,r.schedule(1800),4500).plannedStartUtc);
    auto a=r.m.propose(r.in.monotonicMs,r.in.utc,r.schedule(600),4500);
    EXPECT_TRUE(a.startNow);EXPECT_TRUE(a.lateForTarget);EXPECT_EQ(a.leadSec,1200u);
}
TEST(ThermalModel, NegativeOutdoorAndBoundedHistoryRoundTripAreRealValues) {
    Rig r;
    for(int i=0;i<20;++i) {r.in.admissionEpoch=i+1;r.in.utc=epoch+i*86400;r.in.monotonicMs=i*86400000ULL;
        r.in.outdoorCentiC=-500;ASSERT_TRUE(r.run());}
    EXPECT_EQ(r.m.snapshot().count,16);EXPECT_EQ(r.m.snapshot().runs[0].outdoorCentiC,-500);
    Store s;ThermalModelStore storage(s,sha);ASSERT_TRUE(storage.load(r.m));ASSERT_TRUE(storage.checkpoint(r.m,1));
    EXPECT_EQ(s.data.size(),ThermalModelStore::maximumBytes);
    ThermalResponseModel recovered(profile(),binding());ThermalModelStore restore(s,sha);
    ASSERT_TRUE(restore.load(recovered));EXPECT_EQ(recovered.snapshot().runs[0].outdoorCentiC,-500);
}
TEST(ThermalStore, ProviderIsRealSha256KnownAnswer) {
    EXPECT_EQ(sha("abc"),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}
TEST(ThermalStore, RealShaRoundTripNoPerSampleWritesAndBootAdmissionNotRestored) {
    Rig r;r.train();Store s;ThermalModelStore storage(s,sha);ASSERT_TRUE(storage.load(r.m));ASSERT_TRUE(storage.checkpoint(r.m,100));
    EXPECT_EQ(s.writes,1);EXPECT_EQ(s.data.size(),226u); // 42 header + 6*20 records + 64 realSHA hex.
    ASSERT_TRUE(storage.checkpoint(r.m,101));EXPECT_EQ(s.writes,1);
    ThermalResponseModel fresh(profile(),binding());ThermalModelStore reload(s,sha);ASSERT_TRUE(reload.load(fresh));
    EXPECT_EQ(fresh.snapshot().count,6);EXPECT_EQ(fresh.mode(),LearningMode::disabled);
    EXPECT_EQ(fresh.snapshot().runs[0].outdoorCentiC,500);
}
TEST(ThermalStore, RateLimitedResetPersistsLaterAndExternalDriftNeverOverwritten) {
    Rig r;r.train();Store s;ThermalModelStore storage(s,sha);ASSERT_TRUE(storage.load(r.m));ASSERT_TRUE(storage.checkpoint(r.m,100));
    r.m.reset();EXPECT_FALSE(storage.checkpoint(r.m,101));EXPECT_EQ(s.writes,1);
    ASSERT_TRUE(storage.checkpoint(r.m,1800100));EXPECT_EQ(s.writes,2);
    r.in.admissionEpoch++;r.in.utc=epoch+18*86400;r.in.monotonicMs=18ULL*86400000;ASSERT_TRUE(r.run());
    s.data="external new content";EXPECT_FALSE(storage.checkpoint(r.m,3600100));EXPECT_EQ(s.writes,2);EXPECT_FALSE(storage.healthy());
}
TEST(ThermalStore, AmbiguousCommitAndCorruptReadbackLatchDisabledNoRetry) {
    for(bool ambiguous:{false,true}) {Rig r;r.train();Store s;ThermalModelStore storage(s,sha);ASSERT_TRUE(storage.load(r.m));
        if(ambiguous){s.writeOk=false;s.commitOnFailure=true;}else s.corrupt=true;
        EXPECT_FALSE(storage.checkpoint(r.m,1));EXPECT_EQ(r.m.mode(),LearningMode::disabled);EXPECT_FALSE(storage.healthy());
        EXPECT_FALSE(storage.checkpoint(r.m,9999999));EXPECT_EQ(s.writes,1);}
}
TEST(ThermalStore, TruncatedUnknownSchemaDigestBindingAndProviderFailureReject) {
    Rig r;r.train();Store source;ThermalModelStore original(source,sha);ASSERT_TRUE(original.load(r.m));ASSERT_TRUE(original.checkpoint(r.m,1));
    for(int variant=0;variant<6;++variant) {Store s;s.data=source.data;
        if(variant==0)s.data.resize(50);
        if(variant==1)s.data[7]='2';
        if(variant==2)s.data[70]^=1;
        if(variant==3)s.data="{\"zones\":[]}";
        if(variant==4){s.data[10]^=1;s.data=s.data.substr(0,s.data.size()-64)+sha(s.data.substr(0,s.data.size()-64));}
        ThermalResponseModel model(profile(),binding());ThermalModelStore storage(s,variant==5?ThermalModelStore::Hash([](auto){return std::string();}):sha);
        EXPECT_FALSE(storage.load(model));EXPECT_EQ(model.mode(),LearningMode::disabled);EXPECT_EQ(s.writes,0);}
}
}
