#include <gtest/gtest.h>
#include "control/CoastModelStore.h"
#include "ModelResourceTest.h"
#include "ControlTestHash.h"
using namespace heating::control;
namespace {
constexpr int64_t epoch=1790812800;
auto binding(){std::array<uint8_t,32>b{};b[0]=42;return b;}
CoastProfile profile() {
    CoastProfile p;p.reviewed=true;p.maximumGapMs=60000;p.minimumHeatSec=900;p.maximumHeatSec=7200;
    p.heatDurationRadiusSec=300;p.observationWindowSec=1800;p.maximumCoastSec=1800;
    p.minimumCycles=6;p.minimumDays=6;p.minimumComparable=3;p.minimumSpanDays=14;p.maximumAgeDays=60;
    p.minimumOutdoorSpanCentiC=200;p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;
    p.waterRadiusCentiC=100;p.roomRadiusCentiC=25;p.maximumFallCentiC=100;p.maximumResidualRiseCentiC=100;
    p.maximumRateCentiCPerHour=600;p.comfortBandCentiC=50;p.uncertaintyCentiC=10;p.maximumOvershootCentiC=50;
    return p;
}
struct Rig {
    ThermalCoastModel model{profile(),binding()};ThermalObservation in{};
    Rig(){model.setMode(LearningMode::shadow);in.profileQualified=in.sourceVerified=in.conditionsKnown=true;
        in.deliveryKnown=in.clockTrusted=in.normalControl=true;in.admissionEpoch=1;in.targetGeneration=1;
        in.utc=epoch;in.temperatureCentiC=2100;in.outdoorCentiC=500;in.waterCentiC=4500;}
    bool sample(uint32_t seconds=60){in.monotonicMs+=seconds*1000;in.utc+=seconds;++in.reportSequence;return model.observe(in);}
    void heat(unsigned minutes=30){in.deliveredHeat=true;in.temperatureCentiC=2100;sample();for(unsigned i=0;i<minutes;++i)sample();}
    bool cool(){in.deliveredHeat=false;in.temperatureCentiC=2100;sample();bool result=false;
        for(int i=1;i<=30;++i){in.temperatureCentiC=i<=10?2100+i:2120-i;result=sample();}return result;}
    void train(){for(unsigned i=0;i<6;++i){in.admissionEpoch=i+1;in.utc=epoch+i*3*86400;in.monotonicMs=i*3*86400000ULL;
        in.outdoorCentiC=i<3?500:700;heat();ASSERT_TRUE(cool());}}
    void fresh(unsigned minutes=30){++in.admissionEpoch;in.utc=epoch+16*86400;in.monotonicMs=16ULL*86400000;
        in.outdoorCentiC=500;heat(minutes);}
    ScheduleTarget schedule(int64_t lead=900,int16_t next=1900){return {ScheduleState::active,2100,ScheduleTransition{in.utc+lead,next}};}
    CoastAdvisory advise(bool qualified=true){return model.propose(in.monotonicMs,in.utc,schedule(),qualified);}
};
struct Store:ControlStore {
    std::string bytes;bool readOk=true,writeOk=true,commitOnError=false,corrupt=false;unsigned writes=0;
    bool load(std::string& out)override {out=bytes;return readOk;}
    bool loadBounded(std::string& out,size_t max)override{if(bytes.size()>max)return false;return load(out);}
    bool saveBounded(std::string_view value,size_t max)override{return value.size()<=max&&save(value);}
    bool save(std::string_view value)override {++writes;if(writeOk||commitOnError)bytes=value;if(corrupt&&!bytes.empty())bytes[0]='X';return writeOk;}
};
TEST(ThermalCoast, DisabledUnreviewedAndUnboundCannotLearnOrPropose) {
    Rig r;r.heat();ThermalCoastModel disabled(profile(),binding());EXPECT_FALSE(disabled.observe(r.in));EXPECT_FALSE(disabled.propose(r.in.monotonicMs,r.in.utc,r.schedule(),true).coastNow);
    auto p=profile();p.reviewed=false;ThermalCoastModel unreviewed(p,binding());unreviewed.setMode(LearningMode::shadow);
    EXPECT_FALSE(unreviewed.observe(r.in));ThermalCoastModel unbound(profile(),{});unbound.setMode(LearningMode::shadow);EXPECT_FALSE(unbound.observe(r.in));
    r.model.setMode(static_cast<LearningMode>(42));EXPECT_EQ(r.model.mode(),LearningMode::disabled);
}
TEST(ThermalCoast, SixCompleteIndependentWindowsAcrossFifteenDaysExposeConservativeBoundsOnly) {
    Rig r;r.train();r.fresh();auto a=r.advise();ASSERT_TRUE(a.coastNow);
    EXPECT_EQ(a.eligibleCycles,6);EXPECT_EQ(a.distinctDays,6);EXPECT_EQ(a.comparableCycles,3);EXPECT_EQ(a.coveredDays,15);
    EXPECT_EQ(a.horizonSec,900u);EXPECT_EQ(a.observedCoolingCentiCPerHour,20u);
    EXPECT_EQ(a.samplingUncertaintyCentiC,20);EXPECT_EQ(a.worstLowerCentiC,2060);EXPECT_EQ(a.worstUpperCentiC,2140);
    EXPECT_STREQ(a.reason,"shadow_coast_advisory");
}
TEST(ThermalCoast, PriorQualifiedStartModelAndCurrentComparableHeatPeriodAreRequired) {
    Rig r;r.train();r.fresh(0);EXPECT_FALSE(r.advise().coastNow);
    for(int i=0;i<30;++i){r.sample();}
    EXPECT_TRUE(r.advise().coastNow);EXPECT_FALSE(r.advise(false).coastNow);
    EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,r.schedule()).coastNow); // Default false gate.
    r.in.deliveredHeat=false;r.sample();EXPECT_FALSE(r.advise().coastNow);
}
TEST(ThermalCoast, TimeAloneSameDayOrIncompleteHeatOffIsNotLearningCoverage) {
    Rig one;one.heat();ASSERT_TRUE(one.cool());one.fresh();EXPECT_FALSE(one.advise().coastNow);
    Rig same;for(int i=0;i<6;++i){same.heat();ASSERT_TRUE(same.cool());}same.heat();EXPECT_FALSE(same.advise().coastNow);
    Rig shortHeat;shortHeat.heat(10);EXPECT_FALSE(shortHeat.cool());EXPECT_EQ(shortHeat.model.snapshot().count,0);
    Rig shortOff;shortOff.heat();shortOff.in.deliveredHeat=false;shortOff.sample();for(int i=0;i<10;++i)shortOff.sample();
    shortOff.heat();EXPECT_EQ(shortOff.model.snapshot().count,0);
}
TEST(ThermalCoast, NoWeatherWaterRoomDurationOrHorizonExtrapolation) {
    Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().coastNow);
    r.in.waterCentiC=6000;r.sample();EXPECT_FALSE(r.advise().coastNow);
    r.in.waterCentiC=4500;r.in.outdoorCentiC=-500;r.sample();EXPECT_FALSE(r.advise().coastNow);
    r.in.outdoorCentiC=500;r.in.temperatureCentiC=2140;r.sample();EXPECT_FALSE(r.advise().coastNow);
    r.fresh(15);EXPECT_FALSE(r.advise().coastNow);r.fresh(35);EXPECT_TRUE(r.advise().coastNow);r.sample();EXPECT_FALSE(r.advise().coastNow);
    r.fresh();EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,r.schedule(1801),true).coastNow);
}
TEST(ThermalCoast, OnlyValidImminentLowerUtcScheduleWithoutEarlyOccupiedTargetLoss) {
    Rig r;r.train();r.fresh();
    for(auto lead:{-1,0,1801})EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,r.schedule(lead),true).coastNow);
    for(int16_t next:{2100,2200})EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,r.schedule(900,next),true).coastNow);
    auto s=r.schedule();s.state=ScheduleState::expired;EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,s,true).coastNow);
    s=r.schedule();s.temperatureCentiC.reset();EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc,s,true).coastNow);
    EXPECT_FALSE(r.model.propose(r.in.monotonicMs,INT64_MAX,r.schedule(),true).coastNow);
    EXPECT_FALSE(r.model.propose(r.in.monotonicMs+60000,r.in.utc+60,r.schedule(),true).coastNow);
}
TEST(ThermalCoast, WorstComparableFallAndResidualPeakNotAnOptimisticMedian) {
    Rig r;r.train();auto data=r.model.snapshot();data.runs[0].minimumRelativeCentiC=-60;data.runs[0].endRelativeCentiC=-60;
    ASSERT_TRUE(r.model.restore(data));r.model.setMode(LearningMode::shadow);r.fresh();
    auto a=r.advise();EXPECT_FALSE(a.coastNow);EXPECT_EQ(a.worstLowerCentiC,2010);
    data.runs[0].minimumRelativeCentiC=-10;data.runs[0].endRelativeCentiC=-10;data.runs[0].maximumRelativeCentiC=80;
    ASSERT_TRUE(r.model.restore(data));r.model.setMode(LearningMode::shadow);r.fresh();
    a=r.advise();EXPECT_FALSE(a.coastNow);EXPECT_EQ(a.worstUpperCentiC,2210);
}
TEST(ThermalCoast, CoarserReportAllowanceCanOnlyRestrictComfortAdvice) {
    Rig r;r.train();auto p=profile();p.maximumGapMs=120000;
    ThermalCoastModel coarse(p,binding());ASSERT_TRUE(coarse.restore(r.model.snapshot()));coarse.setMode(LearningMode::frozen);
    r.fresh();auto in=r.in;in.admissionEpoch++;++in.reportSequence;coarse.observe(in);
    for(int i=0;i<30;++i){in.monotonicMs+=60000;in.utc+=60;++in.reportSequence;coarse.observe(in);}
    auto a=coarse.propose(in.monotonicMs,in.utc,{ScheduleState::active,2100,ScheduleTransition{in.utc+900,1900}},true);
    EXPECT_EQ(a.samplingUncertaintyCentiC,40);EXPECT_FALSE(a.coastNow);
}
TEST(ThermalCoast, ConditionsDhwWindowFaultManualGainOrMissingProvenanceAbortWindow) {
    for(int reason=0;reason<12;++reason) {
        Rig r;r.heat();r.in.deliveredHeat=false;r.sample();
        switch(reason){case 0:r.in.dhw=true;break;case 1:r.in.windowOpen=true;break;case 2:r.in.fault=true;break;
        case 3:r.in.manualTest=true;break;case 4:r.in.unexplainedGain=true;break;case 5:r.in.sourceVerified=false;break;
        case 6:r.in.deliveryKnown=false;break;case 7:r.in.conditionsKnown=false;break;case 8:r.in.profileQualified=false;break;
        case 9:r.in.clockTrusted=false;break;case 10:r.in.normalControl=false;break;case 11:r.in.outdoorCentiC.reset();break;}
        for(int i=0;i<31;++i){EXPECT_FALSE(r.sample());}
        EXPECT_EQ(r.model.snapshot().count,0);
    }
}
TEST(ThermalCoast, CachedReportsOldEpochAndModeResetNeverEraseReplayFence) {
    Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().coastNow);
    EXPECT_FALSE(r.model.observe(r.in));EXPECT_FALSE(r.advise().coastNow);
    r.model.setMode(LearningMode::shadow);EXPECT_FALSE(r.model.observe(r.in));
    r.model.reset();EXPECT_FALSE(r.model.observe(r.in));--r.in.admissionEpoch;r.in.reportSequence+=1000;
    EXPECT_FALSE(r.model.observe(r.in));EXPECT_EQ(r.model.snapshot().count,0);
}
TEST(ThermalCoast, GapBackwardClockAndTargetGenerationInvalidateImmediateAdvice) {
    for(int reason=0;reason<5;++reason){Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().coastNow);
        switch(reason){case 0:r.in.utc+=3600;break;case 1:r.in.monotonicMs=0;break;case 2:r.in.targetGeneration++;break;
        case 3:r.in.utc+=60;r.in.monotonicMs+=60000;break;case 4:r.in.temperatureCentiC=2300;break;}
        r.sample();EXPECT_FALSE(r.advise().coastNow);}
}
TEST(ThermalCoast, FrozenUsesFreshComparableHeatWithoutLearningResetKeepsMode) {
    Rig r;r.train();r.model.setMode(LearningMode::frozen);r.fresh();EXPECT_TRUE(r.advise().coastNow);
    EXPECT_FALSE(r.cool());EXPECT_EQ(r.model.snapshot().count,6);
    r.model.reset();EXPECT_EQ(r.model.mode(),LearningMode::frozen);EXPECT_EQ(r.model.snapshot().count,0);
}
TEST(ThermalCoast, ExpiredHistoryInvalidBindingVersionOrIncompleteRecordCannotQualify) {
    Rig r;r.train();auto data=r.model.snapshot();
    for(int reason=0;reason<7;++reason){auto d=data;switch(reason){case 0:d.bindingDigest[1]++;break;case 1:d.algorithmVersion=2;break;
        case 2:d.runs[0].durationSec=1;break;case 3:d.runs[0].heatedDurationSec=10;break;
        case 4:d.runs[0].minimumRelativeCentiC=1;break;case 5:d.runs[0].endRelativeCentiC=-500;break;case 6:d.runs[1]=d.runs[0];break;}
        EXPECT_FALSE(r.model.restore(d));}
    r.in.admissionEpoch++;r.in.utc=epoch+80*86400;r.in.monotonicMs=80ULL*86400000;r.heat();EXPECT_FALSE(r.advise().coastNow);
}
TEST(ThermalCoast, NegativeWeatherAndBoundedHistoryAreNotFabricatedHeatingCommands) {
    Rig r;
    for(int i=0;i<20;++i){r.in.admissionEpoch=i+1;r.in.utc=epoch+i*86400;r.in.monotonicMs=i*86400000ULL;
        r.in.outdoorCentiC=-500;r.heat();ASSERT_TRUE(r.cool());}
    const auto d=r.model.snapshot();EXPECT_EQ(d.count,16);EXPECT_EQ(d.runs[0].outdoorCentiC,-500);
    EXPECT_EQ(d.runs[0].minimumRelativeCentiC,-10);EXPECT_EQ(d.runs[0].heatedDurationSec,1800u);
}
TEST(CoastStore, RealShaKnownAnswerRoundtripDisabledRestoreAndNoPerReportWrites) {
    EXPECT_EQ(controlTestHash("abc"),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    Rig r;r.train();Store s;ModelResourceGate storageResources{testModelResourcePlan()};CoastModelStore storage(s,testBoundedModelHash,storageResources,0);ASSERT_TRUE(storage.load(r.model));
    ASSERT_TRUE(storage.checkpoint(r.model,100));EXPECT_EQ(s.writes,1u);EXPECT_EQ(s.bytes.size(),274u);
    ASSERT_TRUE(storage.checkpoint(r.model,101));EXPECT_EQ(s.writes,1u);
    ThermalCoastModel recovered(profile(),binding());ModelResourceGate restoredResources{testModelResourcePlan()};CoastModelStore restored(s,testBoundedModelHash,restoredResources,0);ASSERT_TRUE(restored.load(recovered));
    EXPECT_EQ(recovered.mode(),LearningMode::disabled);EXPECT_EQ(recovered.snapshot().count,6);EXPECT_EQ(recovered.snapshot().runs[0].minimumRelativeCentiC,-10);
    EXPECT_FALSE(recovered.propose(r.in.monotonicMs,r.in.utc,r.schedule(),true).coastNow);
}
TEST(CoastStore, MaximumBytesResetRateLimitExternalDriftAndNoAutomaticNvsAllocation) {
    Rig r;for(int i=0;i<16;++i){r.in.admissionEpoch=i+1;r.in.utc=epoch+i*86400;r.in.monotonicMs=i*86400000ULL;r.heat();ASSERT_TRUE(r.cool());}
    Store s;ModelResourceGate storeResources{testModelResourcePlan()};CoastModelStore store(s,testBoundedModelHash,storeResources,0);ASSERT_TRUE(store.load(r.model));ASSERT_TRUE(store.checkpoint(r.model,100));
    EXPECT_EQ(s.bytes.size(),CoastModelStore::maximumBytes);r.model.reset();EXPECT_FALSE(store.checkpoint(r.model,101));
    ASSERT_TRUE(store.checkpoint(r.model,1800100));EXPECT_EQ(s.writes,2u);r.model.setMode(LearningMode::shadow);r.in.admissionEpoch++;r.heat();ASSERT_TRUE(r.cool());
    s.bytes="external change";EXPECT_FALSE(store.checkpoint(r.model,3600100));EXPECT_FALSE(store.healthy());EXPECT_EQ(s.writes,2u);
}
TEST(CoastStore, AmbiguousCommitCorruptReadbackAndBackwardsClockLatchDisabledWithoutRetry) {
    for(int reason=0;reason<3;++reason){Rig r;r.train();Store s;ModelResourceGate storageResources{testModelResourcePlan()};CoastModelStore storage(s,testBoundedModelHash,storageResources,0);ASSERT_TRUE(storage.load(r.model));
        if(reason==2){ASSERT_TRUE(storage.checkpoint(r.model,100));r.model.reset();EXPECT_FALSE(storage.checkpoint(r.model,1));}
        else{if(reason==0){s.writeOk=false;s.commitOnError=true;}else s.corrupt=true;EXPECT_FALSE(storage.checkpoint(r.model,100));}
        EXPECT_FALSE(storage.healthy());EXPECT_EQ(r.model.mode(),LearningMode::disabled);auto writes=s.writes;
        EXPECT_FALSE(storage.checkpoint(r.model,9999999));EXPECT_EQ(s.writes,writes);}
}
TEST(CoastStore, TruncatedSchemaDigestBindingAndProviderFailureAreRejectedWithoutWrites) {
    Rig r;r.train();Store origin;ModelResourceGate originalResources{testModelResourcePlan()};CoastModelStore original(origin,testBoundedModelHash,originalResources,0);ASSERT_TRUE(original.load(r.model));ASSERT_TRUE(original.checkpoint(r.model,1));
    for(int reason=0;reason<6;++reason){Store s;s.bytes=origin.bytes;
        if(reason==0){s.bytes.resize(50);}
        if(reason==1){s.bytes[7]='2';}
        if(reason==2){s.bytes[70]^=1;}
        if(reason==3){s.bytes="{\"zones\":[]}";}
        if(reason==4){s.bytes[10]^=1;s.bytes=s.bytes.substr(0,s.bytes.size()-64)+controlTestHash(s.bytes.substr(0,s.bytes.size()-64));}
        ThermalCoastModel m(profile(),binding());ModelResourceGate stResources{testModelResourcePlan()};CoastModelStore st(s,reason==5?CoastModelStore::Hash([](std::string_view,ModelDigest&){return false;}):testBoundedModelHash,stResources,0);
        EXPECT_FALSE(st.load(m));EXPECT_EQ(m.mode(),LearningMode::disabled);EXPECT_EQ(s.writes,0u);}
}
TEST(ThermalCoast, ExtremeMonotonicGapAndReturnFromClockDiscontinuityFailClosed) {
    Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().coastNow);
    auto in=r.in;in.monotonicMs+=UINT64_C(1)<<63;++in.reportSequence;
    EXPECT_FALSE(r.model.observe(in));EXPECT_FALSE(r.model.propose(in.monotonicMs,in.utc,r.schedule(),true).coastNow);
    ++r.in.reportSequence;EXPECT_FALSE(r.model.observe(r.in));EXPECT_FALSE(r.advise().coastNow);
}
TEST(ThermalCoast, PlausibleRisingOutdoorHeatRestartAndUnobservedLongHeatCannotCompleteCooling) {
    for(int reason=0;reason<3;++reason) {
        Rig r;r.heat();r.in.deliveredHeat=false;r.sample();
        if(reason==0){r.in.outdoorCentiC=560;r.sample();}
        if(reason==1){r.in.deliveredHeat=true;r.sample();r.in.deliveredHeat=false;}
        if(reason==2){r.in.temperatureCentiC=2300;r.sample();}
        for(int i=0;i<31;++i){EXPECT_FALSE(r.sample());}
        EXPECT_EQ(r.model.snapshot().count,0);
    }
    Rig longHeat;longHeat.heat(121);EXPECT_FALSE(longHeat.cool());EXPECT_EQ(longHeat.model.snapshot().count,0);
}
TEST(ThermalCoast, LiveUnqualifiedReportsNeverReusePreviouslyQualifiedAdvice) {
    for(int reason=0;reason<6;++reason) {
        Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().coastNow);
        switch(reason){case 0:r.in.dhw=true;break;case 1:r.in.windowOpen=true;break;case 2:r.in.fault=true;break;
            case 3:r.in.manualTest=true;break;case 4:r.in.unexplainedGain=true;break;case 5:r.in.deliveryKnown=false;break;}
        r.sample();EXPECT_FALSE(r.advise().coastNow);
    }
}

}
