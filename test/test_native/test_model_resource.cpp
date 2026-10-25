#include <gtest/gtest.h>
#include "control/ThermalModelStore.h"
#include "control/CoastModelStore.h"
#include "control/CurveModelStore.h"
#include "ModelResourceTest.h"
#include <memory>
#include <fstream>
#include <cstdlib>
#include <stdexcept>
#include <tuple>
using namespace heating::control;
namespace {
constexpr uint32_t epoch=1790812800;
ThermalModelProfile warmProfile() {
    ThermalModelProfile p;p.reviewed=true;p.maximumGapMs=120000;p.minimumOffSec=1800;
    p.minimumRunSec=900;p.maximumRunSec=7200;p.minimumRiseCentiC=50;p.maximumRiseCentiC=500;
    p.minimumRateCentiCPerHour=10;p.maximumRateCentiCPerHour=3000;
    p.outdoorDriftCentiC=50;p.waterDriftCentiC=100;p.minimumStarts=6;p.minimumDistinctDays=6;
    p.minimumSpanDays=14;p.maximumAgeDays=60;p.minimumComparableStarts=3;
    p.comparableOutdoorRadiusCentiC=100;p.comparableWaterRadiusCentiC=100;p.comparableRoomRadiusCentiC=50;
    p.minimumOutdoorSpanCentiC=200;p.maximumLeadSec=7200;return p;
}
CoastProfile coastProfile() {
    CoastProfile p;p.reviewed=true;p.maximumGapMs=60000;p.minimumHeatSec=900;p.maximumHeatSec=7200;
    p.heatDurationRadiusSec=300;p.observationWindowSec=1800;p.maximumCoastSec=1800;
    p.minimumCycles=6;p.minimumDays=6;p.minimumComparable=3;p.minimumSpanDays=14;p.maximumAgeDays=60;
    p.minimumOutdoorSpanCentiC=200;p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;
    p.waterRadiusCentiC=100;p.roomRadiusCentiC=25;p.maximumFallCentiC=100;p.maximumResidualRiseCentiC=100;
    p.maximumRateCentiCPerHour=600;p.comfortBandCentiC=50;p.uncertaintyCentiC=10;p.maximumOvershootCentiC=50;
    return p;
}
GroupWaterProfile group(){
    GroupWaterProfile p;p.qualified=p.independentHighLimit=true;p.minimumCentiC=2000;p.maximumCentiC=6500;
    p.correctionLimitCentiC=100;p.curveCentiC={2000,2500,3000,3500,4000,4500,5000,5500,6000};return p;
}
CurveProfile curveProfile(){
    CurveProfile p;p.reviewed=true;p.configGeneration=1;p.maximumGapMs=120000;p.windowSec=14400;p.maximumOutsideAgeMs=3600000;
    p.maximumRoomAgeMs=120000;p.zoneCount=2;p.zoneIds[0]=1;p.zoneIds[1]=2;p.sourceIds[0]=11;p.sourceIds[1]=12;p.minimumWindows=6;p.minimumDays=6;p.minimumComparable=3;
    p.minimumSpanDays=14;p.maximumAgeDays=60;p.minimumWeatherSpanCentiC=1000;
    p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;p.errorDeadbandCentiC=20;p.maximumErrorCentiC=100;
    p.maximumErrorSpreadCentiC=30;p.waterTrackingToleranceCentiC=50;p.stepCentiC=20;p.maximumRoomRateCentiCPerHour=600;return p;
}
auto binding(uint8_t zone=0){std::array<uint8_t,32> b{};b[0]=42+zone;return b;}
struct Backend:ControlStore {
    std::string bytes;
    bool readOk=true,writeOk=true,corrupt=false,commitOnError=false;
    unsigned reads=0,writes=0,unboundedCalls=0;
    unsigned throwReadAt=0;
    bool throwBeforeSave=false,throwAfterCommit=false;
    ModelResourceGate* reenterOnSave=nullptr;
    ControlPartitionStats stats{20480,630,20,610,true};
    bool load(std::string&) override{++unboundedCalls;return false;}
    bool save(std::string_view)override{++unboundedCalls;return false;}
    bool loadBounded(std::string& out,size_t maximum)override {
        ++reads;if(throwReadAt==reads)throw std::runtime_error("read failure");
        if(!readOk||bytes.size()>maximum)return false;out=bytes;return true;
    }
    bool saveBounded(std::string_view in,size_t maximum)override {
        ++writes;if(throwBeforeSave)throw std::runtime_error("write failure");
        if(in.size()>maximum)return false;
        if(writeOk||commitOnError)bytes.assign(in);
        if(throwAfterCommit)throw std::runtime_error("ambiguous committed write");
        if(corrupt&&!bytes.empty()){bytes[0]='X';}
        if(reenterOnSave)reenterOnSave->begin(0,ModelKind::warm);
        return writeOk;
    }
    ControlPartitionStats modelPartitionStats()const override{return stats;}
};
struct Triple {
    ThermalResponseModel warm;
    ThermalCoastModel coast;
    CurveAdaptation curve;
    Backend w,c,v;
    ThermalModelStore ws;
    CoastModelStore cs;
    CurveModelStore vs;
    Triple(ModelResourceGate& gate,uint8_t z):warm(warmProfile(),binding(z)),coast(coastProfile(),binding(z)),
        curve(curveProfile(),group(),binding(z)),ws(w,testBoundedModelHash,gate,z),
        cs(c,testBoundedModelHash,gate,z),vs(v,testBoundedModelHash,gate,z){}
    bool load(){return ws.load(warm)&&cs.load(coast)&&vs.load(curve);}
    bool maximumSnapshots() {
        auto a=warm.snapshot();a.count=16;
        auto b=coast.snapshot();b.count=16;
        auto d=curve.snapshot();d.count=16;
        for(unsigned i=0;i<16;++i) {
            const auto utc=epoch+i*86400;
            a.runs[i]={utc,utc+1800,1800,200,500,4500,1900};
            b.runs[i]={utc,utc+1800,1800,1800,2100,500,4500,-10,10,-10};
            d.windows[i]={utc,utc+14400,14400,500,30,35};
        }
        return warm.restore(a)&&coast.restore(b)&&curve.restore(d);
    }
};
void record(const char* scenario,const ModelResourceGate& g,unsigned writes=0,size_t bytes=0) {
    if(const auto path=std::getenv("OPENTHERMOSTAT_MODEL_RESOURCE_EVIDENCE")) {
        std::ofstream out(path,std::ios::app);const auto& q=g.required();
        out<<"{\"scenario\":\""<<scenario<<"\",\"resource_gate_healthy\":"<<(g.healthy()?"true":"false")
            <<",\"reserved_slots\":"<<q.slots<<",\"resident_bytes\":"<<q.residentBytes
            <<",\"scratch_bytes\":"<<q.scratchBytes<<",\"codec_bytes\":"<<q.codecBytes
            <<",\"payload_quota_bytes\":"<<q.persistentBytes<<",\"writes\":"<<writes
            <<",\"actual_codec_bytes\":"<<bytes<<",\"physical_outputs_enabled\":false}\n";
    }
}
TEST(ModelResources, UnreviewedDefaultZeroNineUnknownProfileSchemaAndCountOverflowFailClosed) {
    ModelResourceGate defaults({});EXPECT_FALSE(defaults.healthy());
    for(int reason=0;reason<9;++reason) {
        auto p=testModelResourcePlan();
        if(reason==0){p.zones=0;}if(reason==1){p.zones=9;}
        if(reason==2){p.profile=static_cast<ModelResourceProfile>(99);}
        if(reason==3){p.schema=2;}
        if(reason==4){p.models.warmZones=SIZE_MAX;}
        if(reason==5){p.models.coastZones=9;}
        if(reason==6){p.models.curveGroups=2;}
        if(reason==7)p.models={};
        if(reason==8){p.models.curveGroups=SIZE_MAX;}
        ModelResourceGate gate(p);EXPECT_FALSE(gate.healthy())<<reason;
        EXPECT_FALSE(gate.begin(0,ModelKind::warm));record("invalid_plan",gate);
    }
}
TEST(ModelResources, ExactJointRamScratchStackPayloadBudgetsAndOverflowAreRequired) {
    auto p=testModelResourcePlan(8);ModelResourceRequirements q;
    ASSERT_TRUE(ModelResourceGate::requirements(p,q));
    p.residentBytes=q.residentBytes;p.scratchBytes=q.scratchBytes;p.stackBytes=q.stackBytes;p.persistentBytes=q.persistentBytes;
    {ModelResourceGate gate(p);EXPECT_TRUE(gate.healthy());record("exact_8zone_source_budget",gate);}
    for(int reason=0;reason<8;++reason) {
        auto bad=p;
        if(reason==0){--bad.residentBytes;}if(reason==1){--bad.scratchBytes;}
        if(reason==2){--bad.stackBytes;}if(reason==3){--bad.persistentBytes;}
        if(reason==4){bad.residentBytes=SIZE_MAX;}if(reason==5){bad.scratchBytes=SIZE_MAX;}
        if(reason==6){bad.stackBytes=SIZE_MAX;}if(reason==7){bad.persistentBytes=SIZE_MAX;}
        ModelResourceGate gate(bad);EXPECT_FALSE(gate.healthy())<<reason;
    }
}
TEST(ModelResources, E32Existing20KiBLedgerAllowsBoundedReservationButRejectsEightTriples) {
    auto p=testModelResourcePlan();p.profile=ModelResourceProfile::e32_nvs_shadow_v1;p.persistentBytes=20480;
    {ModelResourceGate gate(p);ASSERT_TRUE(gate.healthy());Triple one(gate,0);ASSERT_TRUE(one.load());ASSERT_TRUE(one.ws.checkpoint(one.warm,0));
        EXPECT_EQ(one.w.writes,1u);record("e32_source_ledger_one_triple",gate,1,one.w.bytes.size());}
    p.zones=8;p.models={8,8,8};ModelResourceGate rejected(p);EXPECT_FALSE(rejected.healthy());record("e32_8triples_rejected",rejected);
}
TEST(ModelResources, EightZonesMaximumAllThreeRealCodecsCheckpointAndDisabledRestore) {
    auto p=testModelResourcePlan(8);ModelResourceGate gate(p);
    std::array<std::unique_ptr<Triple>,8> models; // heap test fixture; NOT8large firmware stack objects
    uint64_t now=0;size_t bytes=0;unsigned writes=0;
    for(uint8_t z=0;z<8;++z) {
        models[z]=std::make_unique<Triple>(gate,z);auto& t=*models[z];
        ASSERT_TRUE(t.load());ASSERT_TRUE(t.maximumSnapshots());
        ASSERT_TRUE(t.ws.checkpoint(t.warm,now));now+=60000;
        ASSERT_TRUE(t.cs.checkpoint(t.coast,now));now+=60000;
        ASSERT_TRUE(t.vs.checkpoint(t.curve,now));now+=60000;
        EXPECT_EQ(t.w.bytes.size(),426u);EXPECT_EQ(t.c.bytes.size(),554u);EXPECT_EQ(t.v.bytes.size(),412u);
        bytes+=t.w.bytes.size()+t.c.bytes.size()+t.v.bytes.size();writes+=t.w.writes+t.c.writes+t.v.writes;
        EXPECT_EQ(t.w.unboundedCalls+t.c.unboundedCalls+t.v.unboundedCalls,0u);
    }
    EXPECT_EQ(bytes,11136u);EXPECT_EQ(writes,24u);record("memory_fixture_8zones_24_maxcodecs",gate,writes,bytes);
    // New boot resource owner. Existing persisted bytes, never old learning/admission.
    ModelResourceGate fresh(p);
    for(uint8_t z=0;z<8;++z) {
        Triple restore(fresh,z);restore.w.bytes=models[z]->w.bytes;restore.c.bytes=models[z]->c.bytes;restore.v.bytes=models[z]->v.bytes;
        restore.warm.setMode(LearningMode::shadow);restore.coast.setMode(LearningMode::shadow);restore.curve.setMode(LearningMode::shadow);
        ASSERT_TRUE(restore.load());
        EXPECT_EQ(restore.warm.mode(),LearningMode::disabled);EXPECT_EQ(restore.coast.mode(),LearningMode::disabled);EXPECT_EQ(restore.curve.mode(),LearningMode::disabled);
        EXPECT_EQ(restore.warm.snapshot().count,16);EXPECT_EQ(restore.coast.snapshot().count,16);EXPECT_EQ(restore.curve.snapshot().count,16);
        EXPECT_EQ(restore.w.writes+restore.c.writes+restore.v.writes,0u);
    }
}
TEST(ModelResources, UnallocatedZoneUnknownModelAndDuplicateOwnerInvalidateExistingRegisteredModels) {
    for(int reason=0;reason<3;++reason) {
        ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);ASSERT_TRUE(one.load());
        one.warm.setMode(LearningMode::shadow);one.coast.setMode(LearningMode::shadow);one.curve.setMode(LearningMode::shadow);
        if(reason==0){EXPECT_FALSE(gate.begin(1,ModelKind::warm));}
        if(reason==1){EXPECT_FALSE(gate.begin(0,static_cast<ModelKind>(99)));}
        if(reason==2){Backend b;ThermalResponseModel other(warmProfile(),binding());ThermalModelStore duplicate(b,testBoundedModelHash,gate,0);EXPECT_FALSE(duplicate.load(other));EXPECT_EQ(b.reads,0u);}
        EXPECT_FALSE(gate.healthy());EXPECT_FALSE(one.ws.healthy());EXPECT_FALSE(one.cs.healthy());EXPECT_FALSE(one.vs.healthy());
        EXPECT_EQ(one.warm.mode(),LearningMode::disabled);EXPECT_EQ(one.coast.mode(),LearningMode::disabled);EXPECT_EQ(one.curve.mode(),LearningMode::disabled);
    }
}
TEST(ModelResources, NestedTransactionsCannotAllocateAnotherSnapshotAndFaultAllRegisteredModels) {
    ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);ASSERT_TRUE(one.load());
    ModelResourceTransaction first(gate,0,ModelKind::warm);ASSERT_TRUE(first);
    EXPECT_FALSE(one.cs.checkpoint(one.coast,0));EXPECT_EQ(one.c.writes,0u);EXPECT_FALSE(gate.healthy());
}
TEST(ModelResources, GlobalSpacingPerKeyMinimumAndByteQuotaCannotBeBypassedWithAnotherStore) {
    auto p=testModelResourcePlan();p.checkpointsPerHour=2;p.checkpointBytesPerHour=554;
    ModelResourceGate gate(p);Triple one(gate,0);ASSERT_TRUE(one.load());
    ASSERT_TRUE(one.ws.checkpoint(one.warm,0));
    EXPECT_FALSE(one.cs.checkpoint(one.coast,59999));EXPECT_EQ(one.c.writes,0u);
    ASSERT_TRUE(one.cs.checkpoint(one.coast,60000));
    EXPECT_FALSE(one.vs.checkpoint(one.curve,120000));EXPECT_EQ(one.v.writes,0u);EXPECT_TRUE(gate.healthy());
    ASSERT_TRUE(one.vs.checkpoint(one.curve,3600000));EXPECT_EQ(one.v.writes,1u);
    one.warm.reset(); // unchanged empty body is idempotent, never extra write
    ASSERT_TRUE(one.ws.checkpoint(one.warm,3600001));EXPECT_EQ(one.w.writes,1u);
}
TEST(ModelResources, ByteQuotaExactBoundaryAndNoPartialOrRefundedAttempt) {
    auto p=testModelResourcePlan();p.checkpointBytesPerHour=554;
    ModelResourceGate gate(p);
    // Real gate with explicitly bounded caller-owned slot; no storage IO.
    ASSERT_TRUE(gate.begin(0,ModelKind::coast));
    EXPECT_EQ(gate.admitWrite(0,ModelKind::coast,0,554),ModelResourceGate::Write::allowed);gate.end();
    ASSERT_TRUE(gate.begin(0,ModelKind::warm));EXPECT_EQ(gate.admitWrite(0,ModelKind::warm,60000,1),ModelResourceGate::Write::deferred);gate.end();
    ASSERT_TRUE(gate.begin(0,ModelKind::warm));EXPECT_EQ(gate.admitWrite(0,ModelKind::warm,3600000,426),ModelResourceGate::Write::allowed);gate.end();
}
TEST(ModelResources, CountQuotaSpacingAndThirtyMinuteSlotSurviveStoreReconstruction) {
    ModelResourceGate gate(testModelResourcePlan());Backend backend;
    {ThermalResponseModel m(warmProfile(),binding());ThermalModelStore s(backend,testBoundedModelHash,gate,0);ASSERT_TRUE(s.load(m));ASSERT_TRUE(s.checkpoint(m,0));}
    // Same owner, same key, changed valid codec; cannot reset joint high-water.
    ThermalResponseModel m(warmProfile(),binding());ThermalModelStore s(backend,testBoundedModelHash,gate,0);ASSERT_TRUE(s.load(m));
    auto snap=m.snapshot();snap.count=1;snap.runs[0]={epoch,epoch+1800,1800,200,500,4500,1900};ASSERT_TRUE(m.restore(snap));
    EXPECT_FALSE(s.checkpoint(m,1799999));EXPECT_EQ(backend.writes,1u);
    ASSERT_TRUE(s.checkpoint(m,1800000));EXPECT_EQ(backend.writes,2u);
}
TEST(ModelResources, HourlyCountLimitCannotBeBypassedAcrossKeysAndIdempotenceDoesNotSpendQuota) {
    auto p=testModelResourcePlan();p.checkpointsPerHour=1;ModelResourceGate gate(p);Triple one(gate,0);ASSERT_TRUE(one.load());
    ASSERT_TRUE(one.ws.checkpoint(one.warm,0));
    for(uint64_t now=1;now<100;++now)ASSERT_TRUE(one.ws.checkpoint(one.warm,now));
    EXPECT_EQ(one.w.writes,1u);EXPECT_FALSE(one.cs.checkpoint(one.coast,60000));EXPECT_EQ(one.c.writes,0u);
    ASSERT_TRUE(one.cs.checkpoint(one.coast,3600000));EXPECT_EQ(one.c.writes,1u);
}
TEST(ModelResources, StorageReadbackHashAndOversizeFailuresDisableAllModelsAndNeverRetry) {
    for(int reason=0;reason<5;++reason) {
        ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);ASSERT_TRUE(one.load());ASSERT_TRUE(one.maximumSnapshots());
        one.warm.setMode(LearningMode::shadow);one.coast.setMode(LearningMode::shadow);one.curve.setMode(LearningMode::shadow);
        if(reason==0){one.w.readOk=false;}if(reason==1){one.w.writeOk=false;}
        if(reason==2){one.w.corrupt=true;}if(reason==3){one.w.writeOk=false;one.w.commitOnError=true;}
        if(reason==4){one.w.bytes.assign(427,'X');}
        EXPECT_FALSE(one.ws.checkpoint(one.warm,0));EXPECT_FALSE(gate.healthy());
        EXPECT_EQ(one.coast.mode(),LearningMode::disabled);EXPECT_EQ(one.curve.mode(),LearningMode::disabled);
        const auto writes=one.w.writes;EXPECT_FALSE(one.ws.checkpoint(one.warm,3600000));EXPECT_EQ(one.w.writes,writes);
        EXPECT_EQ(one.w.unboundedCalls,0u);
    }
}
TEST(ModelResources, DefaultConfigStoreHasNoImplicitBoundedModelKeyAllocation) {
    struct ConfigOnly:ControlStore {unsigned reads=0,writes=0;bool load(std::string&)override{++reads;return true;}bool save(std::string_view)override{++writes;return true;}} backend;
    ModelResourceGate gate(testModelResourcePlan());ThermalResponseModel model(warmProfile(),binding());
    ThermalModelStore store(backend,testBoundedModelHash,gate,0);
    EXPECT_FALSE(store.load(model));EXPECT_EQ(backend.reads+backend.writes,0u);EXPECT_FALSE(gate.healthy());
}
TEST(ModelResources, FixedDigestCallbackFailureAndMalformedHexAreFailClosedBeforeStorage) {
    for(int reason=0;reason<2;++reason) {
        ModelResourceGate gate(testModelResourcePlan());Backend b;ThermalResponseModel m(warmProfile(),binding());
        const ModelHash fail=[](std::string_view,ModelDigest&){return false;};
        const ModelHash bad=[](std::string_view,ModelDigest& out){out.fill('z');return true;};
        ThermalModelStore store(b,reason?bad:fail,gate,0);
        EXPECT_FALSE(store.load(m));EXPECT_EQ(b.reads+b.writes,0u);EXPECT_EQ(m.mode(),LearningMode::disabled);
    }
}
TEST(ModelResources, E32MutationRequiresCurrentValidFreeEntryQuotaNotOnlyStaticPlan) {
    for(int reason=0;reason<4;++reason) {
        auto p=testModelResourcePlan();p.profile=ModelResourceProfile::e32_nvs_shadow_v1;p.persistentBytes=20480;
        ModelResourceGate gate(p);Triple one(gate,0);ASSERT_TRUE(one.load());
        if(reason==0)one.w.stats={};
        if(reason==1)one.w.stats={20480,630,629,1,true};
        if(reason==2)one.w.stats={65536,630,20,610,true};
        if(reason==3)one.w.stats={20480,630,20,609,true};
        EXPECT_FALSE(one.ws.checkpoint(one.warm,0));EXPECT_EQ(one.w.writes,0u);EXPECT_FALSE(gate.healthy());
    }
}
TEST(ModelResources, SharedClockReverseAndUint64GapNeverRefundQuotaOrRestoreAdmission) {
    ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);ASSERT_TRUE(one.load());ASSERT_TRUE(one.ws.checkpoint(one.warm,100));
    EXPECT_FALSE(one.cs.checkpoint(one.coast,99));EXPECT_FALSE(gate.healthy());EXPECT_EQ(one.c.writes,0u);
    ModelResourceGate fresh(testModelResourcePlan());Triple two(fresh,0);ASSERT_TRUE(two.load());
    ASSERT_TRUE(two.ws.checkpoint(two.warm,UINT64_MAX-60000));
    EXPECT_FALSE(two.cs.checkpoint(two.coast,1));EXPECT_FALSE(fresh.healthy());EXPECT_EQ(two.c.writes,0u);
}
TEST(ModelResources, EmptyRestoreDisablesPreviouslyRequestedShadowModeForEveryModel) {
    ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);
    one.warm.setMode(LearningMode::shadow);one.coast.setMode(LearningMode::shadow);one.curve.setMode(LearningMode::shadow);
    ASSERT_TRUE(one.load());EXPECT_EQ(one.warm.mode(),LearningMode::disabled);
    EXPECT_EQ(one.coast.mode(),LearningMode::disabled);EXPECT_EQ(one.curve.mode(),LearningMode::disabled);
    EXPECT_EQ(one.w.writes+one.c.writes+one.v.writes,0u);
}

TEST(ModelResources, ActualUnreviewedProfilesAndUnknownBindingFailEvenForAnEmptyBackend) {
    for(int reason=0;reason<4;++reason) {
        ModelResourceGate gate(testModelResourcePlan());Backend b;
        if(reason<2) {
            auto p=warmProfile();if(reason==0)p.reviewed=false;
            ThermalResponseModel model(p,reason==1?std::array<uint8_t,32>{}:binding());
            ThermalModelStore store(b,testBoundedModelHash,gate,0);EXPECT_FALSE(store.load(model));
        } else if(reason==2) {
            auto p=coastProfile();p.reviewed=false;ThermalCoastModel model(p,binding());
            CoastModelStore store(b,testBoundedModelHash,gate,0);EXPECT_FALSE(store.load(model));
        } else {
            auto p=curveProfile();p.reviewed=false;CurveAdaptation model(p,group(),binding());
            CurveModelStore store(b,testBoundedModelHash,gate,0);EXPECT_FALSE(store.load(model));
        }
        EXPECT_FALSE(gate.healthy());EXPECT_EQ(b.reads+b.writes,0u);
    }
}

TEST(ModelResources, UnknownOrUnboundedCheckpointScheduleCannotCreateAnOwner) {
    for(int reason=0;reason<7;++reason) {
        auto p=testModelResourcePlan();
        if(reason==0){p.checkpointSpacingMs=0;}
        if(reason==1){p.checkpointSpacingMs=59999;}
        if(reason==2){p.checkpointSpacingMs=1800001;}
        if(reason==3){p.checkpointsPerHour=0;}
        if(reason==4){p.checkpointsPerHour=25;}
        if(reason==5){p.checkpointBytesPerHour=553;}
        if(reason==6){p.checkpointBytesPerHour=13297;}
        ModelResourceGate gate(p);EXPECT_FALSE(gate.healthy());Backend b;
        ThermalResponseModel model(warmProfile(),binding());ThermalModelStore store(b,testBoundedModelHash,gate,0);
        EXPECT_FALSE(store.load(model));EXPECT_EQ(b.reads+b.writes,0u);
    }
}

ModelResourceGate* reentrantHashGate=nullptr; // finite callback fault fixture only
bool reentrantHash(std::string_view in,ModelDigest& out) {
    reentrantHashGate->begin(0,ModelKind::coast);
    return testBoundedModelHash(in,out);
}
TEST(ModelResources, HashCallbackReentryCannotProceedIntoBackendAfterOwnerFault) {
    ModelResourceGate gate(testModelResourcePlan());Backend backend;ThermalResponseModel m(warmProfile(),binding());
    reentrantHashGate=&gate;ThermalModelStore store(backend,reentrantHash,gate,0);
    EXPECT_FALSE(store.load(m));EXPECT_FALSE(gate.healthy());EXPECT_EQ(backend.reads+backend.writes,0u);
    EXPECT_EQ(m.mode(),LearningMode::disabled);reentrantHashGate=nullptr;
}
TEST(ModelResources, SaveCallbackReentryCannotReportSuccessfulCompletionOrPerformFurtherReadback) {
    ModelResourceGate gate(testModelResourcePlan());Triple one(gate,0);ASSERT_TRUE(one.load());
    one.w.reenterOnSave=&gate;EXPECT_FALSE(one.ws.checkpoint(one.warm,0));
    EXPECT_EQ(one.w.writes,1u);EXPECT_EQ(one.w.reads,2u);EXPECT_FALSE(gate.healthy());
    EXPECT_FALSE(one.cs.healthy());EXPECT_FALSE(one.vs.healthy());
    EXPECT_FALSE(one.ws.checkpoint(one.warm,3600000));EXPECT_EQ(one.w.writes,1u);
}

TEST(ModelResources, ReleasingCheckpointOwnerDisablesLearningAndDoesNotEraseStoredBytes) {
    ModelResourceGate gate(testModelResourcePlan());Backend b;ThermalResponseModel m(warmProfile(),binding());
    {
        ThermalModelStore store(b,testBoundedModelHash,gate,0);ASSERT_TRUE(store.load(m));ASSERT_TRUE(store.checkpoint(m,0));
        m.setMode(LearningMode::shadow);EXPECT_EQ(m.mode(),LearningMode::shadow);
    }
    EXPECT_EQ(m.mode(),LearningMode::disabled);EXPECT_TRUE(gate.healthy());EXPECT_FALSE(b.bytes.empty());EXPECT_EQ(b.writes,1u);
    ThermalModelStore next(b,testBoundedModelHash,gate,0);ASSERT_TRUE(next.load(m));
    EXPECT_EQ(m.mode(),LearningMode::disabled);EXPECT_EQ(b.writes,1u);
}

ModelResourceGate* decodeReentryGate=nullptr;
unsigned decodeReentryCalls=0;
bool hashReentersOnlyNonemptyDecode(std::string_view in,ModelDigest& out) {
    ++decodeReentryCalls;
    if(!in.empty())decodeReentryGate->begin(0,ModelKind::warm);
    return testBoundedModelHash(in,out);
}
TEST(ModelResources, NonemptyWarmDecodeHashCannotRestoreOverSharedOwnerStorageFault) {
    ModelResourceGate first(testModelResourcePlan());Triple original(first,0);
    ASSERT_TRUE(original.load());ASSERT_TRUE(original.maximumSnapshots());ASSERT_TRUE(original.ws.checkpoint(original.warm,0));
    ModelResourceGate fresh(testModelResourcePlan());Triple healthy(fresh,0); // only attach OTHER kinds
    ASSERT_TRUE(healthy.cs.load(healthy.coast));ASSERT_TRUE(healthy.vs.load(healthy.curve));
    Backend backend;backend.bytes=original.w.bytes;ThermalResponseModel model(warmProfile(),binding());
    decodeReentryGate=&fresh;decodeReentryCalls=0;ThermalModelStore store(backend,hashReentersOnlyNonemptyDecode,fresh,0);
    EXPECT_FALSE(store.load(model));EXPECT_EQ(decodeReentryCalls,2u);EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    EXPECT_FALSE(fresh.healthy());EXPECT_FALSE(store.healthy());EXPECT_STREQ(model.status(),"model_storage_fault");
    EXPECT_EQ(model.mode(),LearningMode::disabled);EXPECT_FALSE(healthy.cs.healthy());EXPECT_FALSE(healthy.vs.healthy());
    EXPECT_STREQ(healthy.coast.status(),"coast_storage_fault");EXPECT_STREQ(healthy.curve.status(),"curve_storage_fault");
    EXPECT_FALSE(store.load(model));EXPECT_FALSE(store.checkpoint(model,3600000));EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    decodeReentryGate=nullptr;
}
TEST(ModelResources, NonemptyCoastDecodeHashCannotRestoreOverSharedOwnerStorageFault) {
    ModelResourceGate first(testModelResourcePlan());Triple original(first,0);
    ASSERT_TRUE(original.load());ASSERT_TRUE(original.maximumSnapshots());ASSERT_TRUE(original.cs.checkpoint(original.coast,0));
    ModelResourceGate fresh(testModelResourcePlan());Triple healthy(fresh,0);
    ASSERT_TRUE(healthy.ws.load(healthy.warm));ASSERT_TRUE(healthy.vs.load(healthy.curve));
    Backend backend;backend.bytes=original.c.bytes;ThermalCoastModel model(coastProfile(),binding());
    decodeReentryGate=&fresh;decodeReentryCalls=0;CoastModelStore store(backend,hashReentersOnlyNonemptyDecode,fresh,0);
    EXPECT_FALSE(store.load(model));EXPECT_EQ(decodeReentryCalls,2u);EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    EXPECT_FALSE(fresh.healthy());EXPECT_FALSE(store.healthy());EXPECT_STREQ(model.status(),"coast_storage_fault");
    EXPECT_EQ(model.mode(),LearningMode::disabled);EXPECT_FALSE(healthy.ws.healthy());EXPECT_FALSE(healthy.vs.healthy());
    EXPECT_FALSE(store.load(model));EXPECT_FALSE(store.checkpoint(model,3600000));EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    decodeReentryGate=nullptr;
}
TEST(ModelResources, NonemptyCurveDecodeHashCannotRestoreOverSharedOwnerStorageFault) {
    ModelResourceGate first(testModelResourcePlan());Triple original(first,0);
    ASSERT_TRUE(original.load());ASSERT_TRUE(original.maximumSnapshots());ASSERT_TRUE(original.vs.checkpoint(original.curve,0));
    ModelResourceGate fresh(testModelResourcePlan());Triple healthy(fresh,0);
    ASSERT_TRUE(healthy.ws.load(healthy.warm));ASSERT_TRUE(healthy.cs.load(healthy.coast));
    Backend backend;backend.bytes=original.v.bytes;CurveAdaptation model(curveProfile(),group(),binding());
    decodeReentryGate=&fresh;decodeReentryCalls=0;CurveModelStore store(backend,hashReentersOnlyNonemptyDecode,fresh,0);
    EXPECT_FALSE(store.load(model));EXPECT_EQ(decodeReentryCalls,2u);EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    EXPECT_FALSE(fresh.healthy());EXPECT_FALSE(store.healthy());EXPECT_STREQ(model.status(),"curve_storage_fault");
    EXPECT_EQ(model.mode(),LearningMode::disabled);EXPECT_FALSE(healthy.ws.healthy());EXPECT_FALSE(healthy.cs.healthy());
    EXPECT_FALSE(store.load(model));EXPECT_FALSE(store.checkpoint(model,3600000));EXPECT_EQ(backend.reads,1u);EXPECT_EQ(backend.writes,0u);
    decodeReentryGate=nullptr;
}

}

namespace {
class ModelCheckpointException : public ::testing::TestWithParam<std::tuple<int,int>> {};
TEST_P(ModelCheckpointException, RetiresSharedOwnerWithoutRetryingAmbiguousStorage) {
    const auto [kind,stage]=GetParam();
    ModelResourceGate gate(testModelResourcePlan());Triple models(gate,0);
    ASSERT_TRUE(models.load());ASSERT_TRUE(models.maximumSnapshots());
    models.warm.setMode(LearningMode::shadow);models.coast.setMode(LearningMode::shadow);
    models.curve.setMode(LearningMode::shadow);
    auto& backend=kind==0?models.w:kind==1?models.c:models.v;
    if(stage==0)backend.throwReadAt=backend.reads+1;
    if(stage==1)backend.throwBeforeSave=true;
    if(stage==2)backend.throwAfterCommit=true;
    if(stage==3)backend.throwReadAt=backend.reads+2;
    const auto checkpoint=[&] {
        return kind==0?models.ws.checkpoint(models.warm,1):
            kind==1?models.cs.checkpoint(models.coast,1):models.vs.checkpoint(models.curve,1);
    };
    bool saved=true;
    ASSERT_NO_THROW(saved=checkpoint());EXPECT_FALSE(saved);
    EXPECT_FALSE(gate.healthy());
    EXPECT_EQ(models.warm.mode(),LearningMode::disabled);
    EXPECT_EQ(models.coast.mode(),LearningMode::disabled);
    EXPECT_EQ(models.curve.mode(),LearningMode::disabled);
    if(stage==2||stage==3){EXPECT_FALSE(backend.bytes.empty());}
    const auto reads=backend.reads,writes=backend.writes;
    EXPECT_FALSE(checkpoint());EXPECT_EQ(backend.reads,reads);EXPECT_EQ(backend.writes,writes);
}
INSTANTIATE_TEST_SUITE_P(AllModelStores,ModelCheckpointException,
    ::testing::Combine(::testing::Values(0,1,2),::testing::Values(0,1,2,3)));
TEST(ModelResources, ExceptionDuringLoadCannotLeaveTheModelStoreRetryable) {
    for(int kind=0;kind<3;++kind) {
        ModelResourceGate gate(testModelResourcePlan());Triple models(gate,0);
        auto& backend=kind==0?models.w:kind==1?models.c:models.v;
        backend.throwReadAt=1;
        const auto load=[&] {return kind==0?models.ws.load(models.warm):
            kind==1?models.cs.load(models.coast):models.vs.load(models.curve);};
        bool restored=true;
        ASSERT_NO_THROW(restored=load());EXPECT_FALSE(restored);EXPECT_FALSE(gate.healthy());
        EXPECT_FALSE(load());EXPECT_EQ(backend.reads,1u);
    }
}
}
