#include <gtest/gtest.h>
#include "control/CurveModelStore.h"
#include "ModelResourceTest.h"
#include "ControlTestHash.h"
using namespace heating::control;
namespace {
constexpr int64_t epoch=1790812800;
auto binding(){std::array<uint8_t,32>b{};b[0]=42;return b;}
GroupWaterProfile group(){
    GroupWaterProfile p;p.qualified=p.independentHighLimit=true;p.minimumCentiC=2000;p.maximumCentiC=6500;
    p.correctionLimitCentiC=100;p.curveCentiC={2000,2500,3000,3500,4000,4500,5000,5500,6000};return p;
}
CurveProfile profile(){
    CurveProfile p;p.reviewed=true;p.configGeneration=1;p.maximumGapMs=120000;p.windowSec=14400;p.maximumOutsideAgeMs=3600000;
    p.maximumRoomAgeMs=120000;p.zoneCount=2;p.zoneIds[0]=1;p.zoneIds[1]=2;p.sourceIds[0]=11;p.sourceIds[1]=12;p.minimumWindows=6;p.minimumDays=6;p.minimumComparable=3;
    p.minimumSpanDays=14;p.maximumAgeDays=60;p.minimumWeatherSpanCentiC=1000;
    p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;p.errorDeadbandCentiC=20;p.maximumErrorCentiC=100;
    p.maximumErrorSpreadCentiC=30;p.waterTrackingToleranceCentiC=50;p.stepCentiC=20;p.maximumRoomRateCentiCPerHour=600;return p;
}
struct Rig {
    CurveAdaptation model{profile(),group(),binding()};CurveObservation in{};
    bool automaticWater=true,newWeather=true;
    Rig(){
        model.setMode(LearningMode::shadow);in.profileQualified=in.clockTrusted=in.normalAutomatic=in.outsideQualified=true;
        in.independentLimitsHealthy=in.waterTrackingVerified=true;in.admissionEpoch=1;in.configGeneration=1;in.targetGeneration=1;
        in.utc=epoch;in.outdoorCentiC=500;in.zoneCount=2;
        for(unsigned i=0;i<2;++i){auto& z=in.zones[i];z.zoneId=i+1;z.sourceId=i+11;z.sourceVerified=z.deliveryVerified=z.actuatorReady=true;
            z.targetCentiC=2100;z.temperatureCentiC=2070-int(i)*5;}
    }
    bool sample(uint32_t sec=60){
        in.monotonicMs+=sec*1000;in.utc+=sec;++in.reportSequence;for(size_t i=0;i<in.zoneCount&&i<8;++i)++in.zones[i].reportSequence;
        if(newWeather){++in.outsideReportSequence;in.outsideAgeMs=0;}else in.outsideAgeMs+=sec*1000;
        if(automaticWater){
            const auto maximum=std::max(*in.zones[0].targetCentiC-*in.zones[0].temperatureCentiC,*in.zones[1].targetCentiC-*in.zones[1].temperatureCentiC);
            in.requestedWaterCentiC=static_cast<int16_t>(interpolateWaterCurve(*in.outdoorCentiC,group().curveCentiC)+std::clamp(maximum,-100,100));
            in.reportedWaterCentiC=in.requestedWaterCentiC;
        }
        return model.observe(in);
    }
    bool window(){sample();bool result=false;for(int i=0;i<240;++i)result=sample();return result;}
    void train(){
        const int16_t weather[]={0,1000,500,500,500,0};
        for(unsigned i=0;i<6;++i){in.admissionEpoch=i+1;in.utc=epoch+i*3*86400;in.monotonicMs=i*3*86400000ULL;
            in.outdoorCentiC=weather[i];ASSERT_TRUE(window());}
    }
    void fresh(bool frozen=true){
        model.setMode(frozen?LearningMode::frozen:LearningMode::shadow);++in.admissionEpoch;
        in.utc=epoch+16*86400;in.monotonicMs=16ULL*86400000;in.outdoorCentiC=500;
        EXPECT_EQ(window(),!frozen);
    }
    CurveAdvisory advise(bool qualified=true){return model.propose(in.monotonicMs,in.utc,qualified);}
};
struct Store:ControlStore{
    std::string bytes;bool readOk=true,writeOk=true,commitOnError=false,corrupt=false;unsigned writes=0;
    bool load(std::string& out)override{out=bytes;return readOk;}
    bool loadBounded(std::string& out,size_t max)override{if(bytes.size()>max)return false;return load(out);}
    bool saveBounded(std::string_view value,size_t max)override{return value.size()<=max&&save(value);}
    bool save(std::string_view value)override{++writes;if(writeOk||commitOnError)bytes=value;if(corrupt&&!bytes.empty())bytes[0]='X';return writeOk;}
};
TEST(CurveAdaptation, DefaultDisabledUnreviewedQuorumAndDuplicateZoneProfileFailClosed){
    Rig r;r.sample();CurveAdaptation disabled(profile(),group(),binding());EXPECT_FALSE(disabled.observe(r.in));
    auto p=profile();p.zoneCount=1;EXPECT_FALSE(p.valid());p=profile();p.zoneIds[1]=1;EXPECT_FALSE(p.valid());
    p=profile();p.reviewed=false;CurveAdaptation bad(p,group(),binding());bad.setMode(LearningMode::shadow);EXPECT_FALSE(bad.observe(r.in));
    auto g=group();g.qualified=false;CurveAdaptation unsafe(profile(),g,binding());unsafe.setMode(LearningMode::shadow);EXPECT_FALSE(unsafe.observe(r.in));
}
TEST(CurveAdaptation, SixFourHourWindowsAcrossFifteenDaysRecommendOneObservedInteriorKnotOnly){
    Rig r;r.train();r.fresh();auto p=r.advise();ASSERT_TRUE(p.proposed);
    EXPECT_EQ(p.eligibleWindows,6);EXPECT_EQ(p.distinctDays,6);EXPECT_EQ(p.comparableWindows,3);EXPECT_EQ(p.coveredDays,15);
    EXPECT_EQ(p.knot,3);EXPECT_EQ(p.oldKnotCentiC,3500);EXPECT_EQ(p.newKnotCentiC,3520);
    for(size_t i=0;i<9;++i)EXPECT_EQ(p.newCurve[i],group().curveCentiC[i]+(i==3?20:0));
    auto again=r.advise();EXPECT_EQ(again.newCurve,p.newCurve);EXPECT_EQ(r.model.snapshot().baseCurve,group().curveCentiC);
    EXPECT_FALSE(r.advise(false).proposed);EXPECT_FALSE(r.model.propose(r.in.monotonicMs,r.in.utc).proposed);
}
TEST(CurveAdaptation, PersistentCommonOverheatCanOnlyReduceSameBoundedObservedKnot){
    Rig r;for(auto& z:r.in.zones)z.temperatureCentiC=2130;
    r.train();r.fresh();auto p=r.advise();ASSERT_TRUE(p.proposed);EXPECT_EQ(p.newKnotCentiC,3480);
}
TEST(CurveAdaptation, OneStubbornRoomMixedErrorsAndBadReadinessCannotTuneWholeGroup){
    for(int reason=0;reason<5;++reason){Rig r;
        if(reason==0)r.in.zones[1].temperatureCentiC=2100; //30Centi spread accepted but no ALL-zone consensus.
        if(reason==1)r.in.zones[1].temperatureCentiC=2120; //Mixed signs/spread fails complete windows.
        if(reason==2)r.in.zones[1].temperatureCentiC=2000; //Outlier.
        if(reason==3)r.in.zones[1].actuatorReady=false;
        if(reason==4)r.in.zones[1].sourceVerified=false;
        for(int i=0;i<241;++i)r.sample();
        EXPECT_FALSE(r.advise().proposed);
        if(reason!=0){EXPECT_EQ(r.model.snapshot().count,0);}
    }
}
TEST(CurveAdaptation, PollsCannotMakeEitherZoneOrOutsideWeatherPhysicallyFresh){
    Rig r;r.sample();auto prior=r.in;prior.monotonicMs+=60000;prior.utc+=60;++prior.reportSequence;
    EXPECT_FALSE(r.model.observe(prior));EXPECT_STREQ(r.model.status(),"curve_cached_or_wrong_zone");
    r.in=prior;r.sample();r.newWeather=false;
    for(int i=0;i<60;++i){r.sample();}
    EXPECT_EQ(r.model.snapshot().count,0);
    EXPECT_FALSE(r.advise().proposed);
    Rig forged;forged.sample();auto in=forged.in;in.monotonicMs+=60000;in.utc+=60;++in.reportSequence;
    for(auto& z:in.zones)++z.reportSequence; //New rooms, SAME outside report but age was reset0.
    EXPECT_FALSE(forged.model.observe(in));EXPECT_STREQ(forged.model.status(),"curve_conditions_unverified");
}
TEST(CurveAdaptation, ActualRequestMustMatchExistingGroupCurveAndReportedTrackingNotOtherGroup){
    for(int reason=0;reason<4;++reason){Rig r;r.sample();r.automaticWater=false;
        if(reason==0)r.in.requestedWaterCentiC=*r.in.requestedWaterCentiC+500;
        if(reason==1)r.in.reportedWaterCentiC=*r.in.reportedWaterCentiC-100;
        if(reason==2)r.in.waterTrackingVerified=false;
        if(reason==3)r.in.independentLimitsHealthy=false;
        for(int i=0;i<241;++i){r.sample();}
        EXPECT_EQ(r.model.snapshot().count,0);EXPECT_FALSE(r.advise().proposed);}
}
TEST(CurveAdaptation, GapClockTargetConfigDhwFaultManualGainWindowInvalidateAdvice){
    for(int reason=0;reason<11;++reason){Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().proposed);
        switch(reason){case 0:r.in.monotonicMs+=300000;r.in.utc+=300;break;case 1:r.in.utc+=3600;break;
        case 2:r.in.targetGeneration++;break;case 3:r.in.configGeneration++;break;case 4:r.in.dhw=true;break;
        case 5:r.in.fault=true;break;case 6:r.in.manualTest=true;break;case 7:r.in.externalGain=true;break;
        case 8:r.in.zones[0].windowOpen=true;break;case 9:r.in.zones[0].targetCentiC=2101;break;
        case 10:r.in.monotonicMs+=UINT64_C(1)<<63;break;}
        r.sample();EXPECT_FALSE(r.advise().proposed);}
}
TEST(CurveAdaptation, CoverageWithoutNeighborsOrConsistentAffectedWeatherErrorDoesNotExtrapolate){
    Rig r;r.train();auto d=r.model.snapshot();
    for(int reason=0;reason<4;++reason){auto bad=d;
        if(reason==0)bad.windows[0].outdoorCentiC=500,bad.windows[5].outdoorCentiC=500;
        if(reason==1)bad.windows[1].outdoorCentiC=500;
        if(reason==2)bad.windows[1].minimumZoneErrorCentiC=0,bad.windows[1].maximumZoneErrorCentiC=0;
        if(reason==3)bad.windows[3].outdoorCentiC=700;
        ASSERT_TRUE(r.model.restore(bad));r.model.setMode(LearningMode::frozen);r.fresh();EXPECT_FALSE(r.advise().proposed);}
}
TEST(CurveAdaptation, MonotonicAndHardGroupLimitsRefuseRatherThanClipProposedKnot){
    Rig r;r.train();auto d=r.model.snapshot();auto g=group();g.curveCentiC[4]=3505;
    auto changed=d;changed.baseCurve=g.curveCentiC;CurveAdaptation limited(profile(),g,binding());
    ASSERT_TRUE(limited.restore(changed));limited.setMode(LearningMode::frozen);
    r.fresh();auto in=r.in;in.admissionEpoch++;++in.reportSequence;for(auto& z:in.zones)++z.reportSequence;
    auto update=[&]{in.requestedWaterCentiC=3535;in.reportedWaterCentiC=3535;return limited.observe(in);};
    update();for(int i=0;i<240;++i){in.monotonicMs+=60000;in.utc+=60;++in.reportSequence;++in.outsideReportSequence;for(auto& z:in.zones)++z.reportSequence;update();}
    EXPECT_FALSE(limited.propose(in.monotonicMs,in.utc,true).proposed);
}
TEST(CurveAdaptation, FreezeResetOldEpochAndReusedZoneReportsPreserveAdmissionFences){
    Rig r;r.train();r.fresh();ASSERT_TRUE(r.advise().proposed);EXPECT_EQ(r.model.snapshot().count,6);
    r.model.reset();EXPECT_EQ(r.model.mode(),LearningMode::frozen);EXPECT_EQ(r.model.snapshot().count,0);
    EXPECT_FALSE(r.model.observe(r.in));--r.in.admissionEpoch;r.in.reportSequence+=10000;
    EXPECT_FALSE(r.model.observe(r.in));EXPECT_FALSE(r.advise().proposed);
}
TEST(CurveAdaptation, RestoreBindsExactOldCurveVersionAndHistoryTimeOrdering){
    Rig r;r.train();const auto d=r.model.snapshot();
    for(int reason=0;reason<6;++reason){auto bad=d;
        if(reason==0){bad.bindingDigest[0]++;}
        if(reason==1){bad.algorithmVersion=2;}
        if(reason==2){bad.baseCurve[3]++;}
        if(reason==3){bad.windows[0].durationSec=1;}
        if(reason==4){bad.windows[1]=bad.windows[0];}
        if(reason==5){bad.windows[0].maximumZoneErrorCentiC=500;}
        EXPECT_FALSE(r.model.restore(bad));}
    ASSERT_TRUE(r.model.restore(d));EXPECT_EQ(r.model.mode(),LearningMode::disabled);EXPECT_FALSE(r.advise().proposed);
}
TEST(CurveStore, VersionBindingBaseCurveShaReadbackAndRateLimitedReset){
    EXPECT_EQ(controlTestHash("abc"),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    Rig r;r.train();Store s;ModelResourceGate storeResources{testModelResourcePlan()};CurveModelStore store(s,testBoundedModelHash,storeResources,0);ASSERT_TRUE(store.load(r.model));ASSERT_TRUE(store.checkpoint(r.model,1));
    EXPECT_EQ(s.bytes.size(),232u);EXPECT_EQ(s.writes,1u);EXPECT_TRUE(store.checkpoint(r.model,2));EXPECT_EQ(s.writes,1u);
    CurveAdaptation other(profile(),group(),binding());ModelResourceGate recoveredResources{testModelResourcePlan()};CurveModelStore recovered(s,testBoundedModelHash,recoveredResources,0);ASSERT_TRUE(recovered.load(other));
    EXPECT_EQ(other.mode(),LearningMode::disabled);EXPECT_EQ(other.snapshot().count,6);EXPECT_EQ(other.snapshot().baseCurve,group().curveCentiC);
    r.model.reset();EXPECT_FALSE(store.checkpoint(r.model,2));EXPECT_TRUE(store.checkpoint(r.model,1800001));EXPECT_EQ(s.writes,2u);
}
TEST(CurveStore, AmbiguousCommitCorruptExternalChangeAndNoAutomaticRetry){
    for(int reason=0;reason<3;++reason){Rig r;r.train();Store s;ModelResourceGate storeResources{testModelResourcePlan()};CurveModelStore store(s,testBoundedModelHash,storeResources,0);ASSERT_TRUE(store.load(r.model));
        if(reason==0){s.writeOk=false;s.commitOnError=true;}if(reason==1)s.corrupt=true;if(reason==2)s.bytes="external";
        EXPECT_FALSE(store.checkpoint(r.model,1));EXPECT_FALSE(store.healthy());EXPECT_EQ(r.model.mode(),LearningMode::disabled);
        const auto writes=s.writes;EXPECT_FALSE(store.checkpoint(r.model,3600000));EXPECT_EQ(s.writes,writes);}
}
TEST(CurveAdaptation, IndependentSourceIdsRoomAgeAndAllZoneReportsAreMandatory) {
    auto p=profile();p.sourceIds[1]=p.sourceIds[0];EXPECT_FALSE(p.valid());
    for(int reason=0;reason<3;++reason){Rig r;r.sample();
        if(reason==0)r.in.zones[1].sourceId=999;
        if(reason==1)r.in.zones[1].sourceAgeMs=profile().maximumRoomAgeMs;
        if(reason==2)r.in.zoneCount=1;
        EXPECT_FALSE(r.sample());EXPECT_EQ(r.model.snapshot().count,0);}
}
TEST(CurveAdaptation, FloorIndependentCutoutAndRequiredSensorAreTheExistingSafetyBoundary) {
    Rig r;r.sample();auto g=group();g.emitter=EmitterType::floor;g.independentFloorCutout=g.qualifiedMixing=g.floorSensorRequired=true;
    g.floorMaximumCentiC=3500;g.maximumCentiC=4500;
    CurveAdaptation floor(profile(),g,binding());floor.setMode(LearningMode::shadow);auto in=r.in;
    EXPECT_FALSE(floor.observe(in));EXPECT_STREQ(floor.status(),"curve_conditions_unverified");
    in.floorSensorFresh=true;in.floorCentiC=2500;
    for(int i=0;i<241;++i){in.monotonicMs+=60000;in.utc+=60;++in.reportSequence;++in.outsideReportSequence;for(auto& z:in.zones)++z.reportSequence;floor.observe(in);}
    EXPECT_EQ(floor.snapshot().count,1);
    in.floorCentiC=3500;in.monotonicMs+=60000;in.utc+=60;++in.reportSequence;++in.outsideReportSequence;for(auto& z:in.zones)++z.reportSequence;
    EXPECT_FALSE(floor.observe(in));EXPECT_STREQ(floor.status(),"curve_conditions_unverified");EXPECT_FALSE(floor.propose(in.monotonicMs,in.utc,true).proposed);
}
TEST(CurveStore, MaximumBoundedWindowsAndSignedErrorRoundtrip) {
    Rig r;for(auto& z:r.in.zones)z.temperatureCentiC=2130;
    for(int i=0;i<20;++i){r.in.admissionEpoch=i+1;r.in.utc=epoch+i*86400;r.in.monotonicMs=i*86400000ULL;ASSERT_TRUE(r.window());}
    EXPECT_EQ(r.model.snapshot().count,16);Store s;ModelResourceGate storeResources{testModelResourcePlan()};CurveModelStore store(s,testBoundedModelHash,storeResources,0);
    ASSERT_TRUE(store.load(r.model));ASSERT_TRUE(store.checkpoint(r.model,1));EXPECT_EQ(s.bytes.size(),CurveModelStore::maximumBytes);
    CurveAdaptation restored(profile(),group(),binding());ModelResourceGate loadResources{testModelResourcePlan()};CurveModelStore load(s,testBoundedModelHash,loadResources,0);ASSERT_TRUE(load.load(restored));
    EXPECT_EQ(restored.snapshot().windows[0].minimumZoneErrorCentiC,-30);EXPECT_EQ(restored.snapshot().baseCurve,group().curveCentiC);
}
TEST(CurveStore, TruncationVersionUnknownCountDigestBindingAndBaseCurveRejectWithoutWrites) {
    Rig r;r.train();Store origin;ModelResourceGate sourceResources{testModelResourcePlan()};CurveModelStore source(origin,testBoundedModelHash,sourceResources,0);ASSERT_TRUE(source.load(r.model));ASSERT_TRUE(source.checkpoint(r.model,1));
    for(int reason=0;reason<7;++reason){Store s;s.bytes=origin.bytes;
        if(reason==0){s.bytes.resize(30);}
        if(reason==1){s.bytes[7]='2';}
        if(reason==2){s.bytes[70]^=1;}
        if(reason>=3&&reason<=5){s.bytes[reason==3?9:reason==4?10:42]^=1;s.bytes=s.bytes.substr(0,s.bytes.size()-64)+controlTestHash(s.bytes.substr(0,s.bytes.size()-64));}
        CurveAdaptation m(profile(),group(),binding());ModelResourceGate stResources{testModelResourcePlan()};CurveModelStore st(s,reason==6?CurveModelStore::Hash([](std::string_view,ModelDigest&){return false;}):testBoundedModelHash,stResources,0);
        EXPECT_FALSE(st.load(m));EXPECT_EQ(m.mode(),LearningMode::disabled);EXPECT_EQ(s.writes,0u);}
}

}
