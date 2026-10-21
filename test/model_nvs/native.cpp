// New actual production-header cases; original resource regression sources reused,
// not rewritten, and not re-executed by the focused verifier's GTest filter.
#include "../test_native/test_model_resource.cpp"
#include "control/NvsModelStore.h"
namespace f=modelNvsFixture;
namespace {
ModelResourcePlan nvsPlan() {
    auto p=testModelResourcePlan();p.profile=ModelResourceProfile::e32_nvs_shadow_v1;
    p.persistentBytes=ControlPartitionBudget::partitionBytes;
    ModelResourceRequirements required;
    if(ModelResourceGate::requirements(p,required)){
        p.residentBytes=required.residentBytes;p.scratchBytes=required.scratchBytes;
        p.stackBytes=required.stackBytes;p.persistentBytes=required.persistentBytes;
    }
    return p;
}
struct NvsModelBackend:testing::Test {
    void SetUp()override{f::reset();}
    void TearDown()override{EXPECT_TRUE(f::handles.empty());}
};
struct NativeWarm {
    NvsModelProvider provider{nvsPlan()};
    NvsModelStore backend{provider,0,ModelKind::warm};
    ThermalResponseModel model{warmProfile(),binding()};
    ThermalModelStore store{backend,modelSha256,provider.gate(),0};
};
void unchangedAfterFailure(NativeWarm& a) {
    const auto calls=std::array<unsigned,7>{f::opens,f::lengths,f::copies,f::sets,f::commits,f::statsCalls,f::closes};
    EXPECT_FALSE(a.store.checkpoint(a.model,3600000));
    std::string out;EXPECT_FALSE(a.backend.loadBounded(out,426));
    EXPECT_FALSE(a.backend.saveBounded("bad",426));
    EXPECT_FALSE(a.provider.healthy());EXPECT_FALSE(a.store.healthy());
    EXPECT_EQ(a.model.mode(),LearningMode::disabled);
    EXPECT_EQ(calls,(std::array<unsigned,7>{f::opens,f::lengths,f::copies,f::sets,f::commits,f::statsCalls,f::closes}));
}
TEST_F(NvsModelBackend, ActualPinnedShaKnownVectorsAndFixedOutput) {
    ModelDigest d{};ASSERT_TRUE(modelSha256("",d));
    EXPECT_EQ(std::string(d.data(),d.size()),"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    ASSERT_TRUE(modelSha256("abc",d));
    EXPECT_EQ(std::string(d.data(),d.size()),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}
TEST_F(NvsModelBackend, AllThreeActualCodecsUseOnlyReservedKeysExactReadbackAndDisabledRestore) {
    f::data["ot_control"]["config"]={'s','a','f','e'};
    std::array<std::string,3> durable;
    {
        NvsModelProvider provider(nvsPlan());ASSERT_TRUE(provider.healthy());
        NvsModelStore w(provider,0,ModelKind::warm),c(provider,0,ModelKind::coast),r(provider,0,ModelKind::curve);
        ThermalResponseModel warm(warmProfile(),binding());ThermalCoastModel coast(coastProfile(),binding());
        CurveAdaptation curve(curveProfile(),group(),binding());
        ThermalModelStore ws(w,modelSha256,provider.gate(),0);CoastModelStore cs(c,modelSha256,provider.gate(),0);
        CurveModelStore rs(r,modelSha256,provider.gate(),0);
        ASSERT_TRUE(ws.load(warm));ASSERT_TRUE(cs.load(coast));ASSERT_TRUE(rs.load(curve));
        auto wa=warm.snapshot();wa.count=16;auto co=coast.snapshot();co.count=16;
        auto cu=curve.snapshot();cu.count=16;
        for(unsigned i=0;i<16;++i){const auto utc=epoch+i*86400;
            wa.runs[i]={utc,utc+1800,1800,200,500,4500,1900};
            co.runs[i]={utc,utc+1800,1800,1800,2100,500,4500,-10,10,-10};
            cu.windows[i]={utc,utc+14400,14400,500,30,35};}
        ASSERT_TRUE(warm.restore(wa));ASSERT_TRUE(coast.restore(co));ASSERT_TRUE(curve.restore(cu));
        ASSERT_TRUE(ws.checkpoint(warm,0));ASSERT_TRUE(cs.checkpoint(coast,60000));ASSERT_TRUE(rs.checkpoint(curve,120000));
        EXPECT_EQ(f::sets,3u);EXPECT_EQ(f::commits,3u);EXPECT_EQ(f::copies,3u);
        EXPECT_EQ(f::statsCalls,18u); // every bounded read + shared gate + both mutation boundaries
        EXPECT_EQ(f::data["ot_models_v1"].size(),3u);
        EXPECT_EQ(f::data["ot_models_v1"]["warm_0"].size(),426u);
        EXPECT_EQ(f::data["ot_models_v1"]["coast_0"].size(),554u);
        EXPECT_EQ(f::data["ot_models_v1"]["curve_0"].size(),412u);
        EXPECT_EQ(warm.mode(),LearningMode::disabled);EXPECT_EQ(coast.mode(),LearningMode::disabled);
        EXPECT_EQ(curve.mode(),LearningMode::disabled);
        size_t i=0;for(auto key:{"warm_0","coast_0","curve_0"}) {
            const auto& v=f::data["ot_models_v1"][key];durable[i++].assign(v.begin(),v.end());
        }
        NvsModelStore duplicate(provider,0,ModelKind::coast);
        EXPECT_FALSE(provider.healthy());EXPECT_FALSE(ws.healthy());EXPECT_FALSE(cs.healthy());EXPECT_FALSE(rs.healthy());
        EXPECT_STREQ(warm.status(),"model_storage_fault");
        EXPECT_STREQ(coast.status(),"coast_storage_fault");EXPECT_STREQ(curve.status(),"curve_storage_fault");
        EXPECT_FALSE(ws.checkpoint(warm,3600000));EXPECT_FALSE(cs.checkpoint(coast,3600000));EXPECT_FALSE(rs.checkpoint(curve,3600000));
        EXPECT_EQ(f::sets,3u);EXPECT_EQ(f::commits,3u);
    }
    {
        NvsModelProvider provider(nvsPlan());
        NvsModelStore w(provider,0,ModelKind::warm),c(provider,0,ModelKind::coast),r(provider,0,ModelKind::curve);
        ThermalResponseModel warm(warmProfile(),binding());ThermalCoastModel coast(coastProfile(),binding());
        CurveAdaptation curve(curveProfile(),group(),binding());
        ThermalModelStore ws(w,modelSha256,provider.gate(),0);CoastModelStore cs(c,modelSha256,provider.gate(),0);
        CurveModelStore rs(r,modelSha256,provider.gate(),0);
        ASSERT_TRUE(ws.load(warm));ASSERT_TRUE(cs.load(coast));ASSERT_TRUE(rs.load(curve));
        EXPECT_EQ(warm.mode(),LearningMode::disabled);EXPECT_EQ(coast.mode(),LearningMode::disabled);EXPECT_EQ(curve.mode(),LearningMode::disabled);
        EXPECT_TRUE(ws.checkpoint(warm,3600000));EXPECT_TRUE(cs.checkpoint(coast,3600000));EXPECT_TRUE(rs.checkpoint(curve,3600000));
        EXPECT_EQ(f::sets,3u);EXPECT_EQ(f::commits,3u); // unchanged snapshot = NO write
    }
    EXPECT_EQ(f::data["ot_control"]["config"],(std::vector<unsigned char>{'s','a','f','e'}));
}
TEST_F(NvsModelBackend, UnreviewedMemoryProfileAndEightTriplesRefuseBeforeAnyIo) {
    for(int k=0;k<3;++k){
        auto p=nvsPlan();
        if(k==0)p.profile=ModelResourceProfile::unreviewed;
        if(k==1)p.profile=ModelResourceProfile::bounded_memory_shadow_v1;
        if(k==2){p.zones=8;p.models={8,8,8};p.residentBytes=131072;
            p.scratchBytes=16384;p.stackBytes=4096;p.persistentBytes=20480;}
        NvsModelProvider provider(p);EXPECT_FALSE(provider.healthy());
    }
    EXPECT_EQ(f::opens+f::sets+f::statsCalls,0u);
}
TEST_F(NvsModelBackend, DuplicateProviderAndDuplicateKeyFaultAllRegisteredModels) {
    {
        NativeWarm a;ASSERT_TRUE(a.store.load(a.model));
        NvsModelProvider duplicate(nvsPlan());EXPECT_FALSE(duplicate.healthy());EXPECT_FALSE(a.provider.healthy());
        unchangedAfterFailure(a);
    }
    f::reset();
    {
        NativeWarm a;ASSERT_TRUE(a.store.load(a.model));
        NvsModelStore duplicate(a.provider,0,ModelKind::warm);unchangedAfterFailure(a);
    }
}
TEST_F(NvsModelBackend, OutOfReservationUnknownKindAndUnboundedApiCannotReachNvs) {
    for(int k=0;k<4;++k){
        NvsModelProvider provider(nvsPlan());
        NvsModelStore backend(provider,k==0?1:0,k==1?static_cast<ModelKind>(255):ModelKind::warm);
        std::string out;
        if(k==2){EXPECT_FALSE(backend.load(out));}
        if(k==3){EXPECT_FALSE(backend.save("x"));}
        EXPECT_FALSE(provider.healthy());
    }
    EXPECT_EQ(f::opens+f::statsCalls+f::sets,0u);
}
TEST_F(NvsModelBackend, OversizedOrZeroDurableLengthFailsBeforeCopyOrResize) {
    for(auto size:{size_t(0),size_t(427),SIZE_MAX}){
        f::reset();NvsModelProvider provider(nvsPlan());NvsModelStore backend(provider,0,ModelKind::warm);
        f::data["ot_models_v1"]["warm_0"]={'x'};f::reportedSize=size;f::overrideReportedSize=true;
        std::string out="keep";const auto capacity=out.capacity();
        EXPECT_FALSE(backend.loadBounded(out,426));EXPECT_EQ(f::copies,0u);
        EXPECT_EQ(out,"keep");EXPECT_EQ(out.capacity(),capacity);EXPECT_FALSE(provider.healthy());
    }
}
TEST_F(NvsModelBackend, WrongBoundOversizedCallerBufferAndOversizedSaveFailBeforeIo) {
    for(int k=0;k<4;++k) {
        f::reset();NvsModelProvider provider(nvsPlan());NvsModelStore backend(provider,0,ModelKind::warm);
        std::string out;
        if(k==1)out.reserve(4096);
        if(k<2){EXPECT_FALSE(backend.loadBounded(out,k==0?554:426));}
        else {EXPECT_FALSE(backend.saveBounded(k==2?std::string(427,'x'):std::string(),426));}
        EXPECT_EQ(f::opens+f::statsCalls+f::sets,0u);EXPECT_FALSE(provider.healthy());
    }
}
TEST_F(NvsModelBackend, OpenLengthReadAndChangedLengthFailStickyWithoutRetry) {
    for(int k=0;k<4;++k){
        f::reset();NativeWarm a;f::data["ot_models_v1"]["warm_0"]={'a','b','c'};
        if(k==0)f::badOpen=true;
        if(k==1)f::badLength=true;
        if(k==2)f::badRead=true;
        if(k==3)f::growAfterLength=true;
        EXPECT_FALSE(a.store.load(a.model));EXPECT_LE(f::opens,1u);EXPECT_LE(f::copies,1u);
        unchangedAfterFailure(a);
    }
}
TEST_F(NvsModelBackend, MissingNamespaceNeverCreatesKeysDuringEmptyLoad) {
    NativeWarm a;ASSERT_TRUE(a.store.load(a.model));EXPECT_TRUE(f::data.empty());
    EXPECT_EQ(f::opens,1u);EXPECT_EQ(f::lengths+f::copies+f::sets+f::commits,0u);
    EXPECT_EQ(f::statsCalls,1u);
}
TEST_F(NvsModelBackend, SetCommitAndAmbiguousCommitFailOncePreserveDurableAndNeverRetry) {
    for(int k=0;k<3;++k){
        f::reset();NativeWarm a;ASSERT_TRUE(a.store.load(a.model));
        if(k==0)f::badSet=true;
        else {f::badCommit=true;f::commitDespiteError=k==2;}
        EXPECT_FALSE(a.store.checkpoint(a.model,0));
        EXPECT_EQ(f::sets,1u);EXPECT_EQ(f::commits,k==0?0u:1u);EXPECT_EQ(f::copies,0u);
        EXPECT_EQ(f::data["ot_models_v1"].count("warm_0"),k==2?1u:0u);
        unchangedAfterFailure(a);
    }
}
TEST_F(NvsModelBackend, ExactOuterStoreReadbackDetectsCorruptionWithoutBackendDuplicateRead) {
    NativeWarm a;ASSERT_TRUE(a.store.load(a.model));f::corruptReadback=true;
    EXPECT_FALSE(a.store.checkpoint(a.model,0));
    EXPECT_EQ(f::sets,1u);EXPECT_EQ(f::commits,1u);EXPECT_EQ(f::copies,1u);
    EXPECT_TRUE(f::data["ot_models_v1"].count("warm_0"));
    unchangedAfterFailure(a);
}
TEST_F(NvsModelBackend, InvalidMissingExhaustedOrChangingPartitionStatsForbidMutation) {
    for(int k=0;k<8;++k){
        f::reset();NativeWarm a;ASSERT_TRUE(a.store.load(a.model));
        if(k==0)f::badStats=true;
        if(k==1)f::missingPartition=true;
        if(k==2)f::partitionBytes=65536;
        if(k==3)f::stats={629,1,630,1};
        if(k==4)f::stats={20,609,630,1};
        if(k==5)f::onStats=[](){if(f::statsCalls==4)f::stats={629,1,630,1};};
        if(k==6)f::onStats=[](){if(f::statsCalls==5)f::stats={629,1,630,1};};
        if(k==7)f::stats={303,327,630,1}; // old ledger fits; extra model namespace must not
        EXPECT_FALSE(a.store.checkpoint(a.model,0));EXPECT_EQ(f::sets+f::commits,0u);
        unchangedAfterFailure(a);
    }
}
TEST_F(NvsModelBackend, SharedQuotaDefersWithoutSecondMutationAndRetainsCheckpointFloor) {
    NativeWarm a;ASSERT_TRUE(a.store.load(a.model));ASSERT_TRUE(a.store.checkpoint(a.model,0));
    auto snapshot=a.model.snapshot();snapshot.count=1;
    snapshot.runs[0]={epoch,epoch+900,900,100,500,4500,1900};
    ASSERT_TRUE(a.model.restore(snapshot));EXPECT_FALSE(a.store.checkpoint(a.model,1)); // changed epoch snapshot deferred
    EXPECT_TRUE(a.provider.healthy());EXPECT_EQ(f::sets,1u);EXPECT_EQ(f::commits,1u);
}
TEST_F(NvsModelBackend, FailedHashAndCorruptStoredHashCannotLoadOrClearSharedFault) {
    {
        NativeWarm a;
        const ModelHash bad=[](std::string_view,ModelDigest&){return false;};
        ThermalResponseModel model(warmProfile(),binding());
        ThermalModelStore store(a.backend,bad,a.provider.gate(),0);
        EXPECT_FALSE(store.load(model));EXPECT_EQ(f::opens,0u);EXPECT_FALSE(a.provider.healthy());
    }
    f::reset();
    {
        NativeWarm a;ASSERT_TRUE(a.store.load(a.model));ASSERT_TRUE(a.store.checkpoint(a.model,0));
    }
    f::data["ot_models_v1"]["warm_0"].back()='z';
    {
        NativeWarm a;EXPECT_FALSE(a.store.load(a.model));unchangedAfterFailure(a);
    }
}
TEST_F(NvsModelBackend, NativeSdkReentryFaultNeverProceedsToCopyOrCommit) {
    {
        NativeWarm a;f::data["ot_models_v1"]["warm_0"]={'a','b'};
        f::onLength=[&](){a.provider.gate().fail();};
        EXPECT_FALSE(a.store.load(a.model));EXPECT_EQ(f::copies,0u);unchangedAfterFailure(a);
    }
    f::reset();
    {
        NativeWarm a;ASSERT_TRUE(a.store.load(a.model));
        f::onSet=[&](){a.provider.gate().fail();};
        EXPECT_FALSE(a.store.checkpoint(a.model,0));EXPECT_EQ(f::sets,1u);EXPECT_EQ(f::commits,0u);
        unchangedAfterFailure(a);
    }
}
} // namespace

namespace {
ModelResourceGate* decodeGate=nullptr;
ModelKind decodeKind=ModelKind::warm;
unsigned emptyHashCalls=0,bodyHashCalls=0;
bool nonemptyReentryHash(std::string_view bytes,ModelDigest& out) {
    const bool ok=modelSha256(bytes,out); // real SHA always executes first
    if(bytes.empty())++emptyHashCalls;
    else {
        ++bodyHashCalls;
        if(decodeGate)decodeGate->begin(0,decodeKind); // busy transaction: shared latch
    }
    return ok; // NOT a fake hash failure: gate must be checked after decode
}
struct ThreeNvs {
    NvsModelProvider provider{nvsPlan()};
    NvsModelStore w{provider,0,ModelKind::warm},c{provider,0,ModelKind::coast},r{provider,0,ModelKind::curve};
    ThermalResponseModel warm{warmProfile(),binding()};
    ThermalCoastModel coast{coastProfile(),binding()};
    CurveAdaptation curve{curveProfile(),group(),binding()};
    ThermalModelStore ws;
    CoastModelStore cs;
    CurveModelStore rs;
    explicit ThreeNvs(int injected=-1):ws(w,injected==0?nonemptyReentryHash:modelSha256,provider.gate(),0),
        cs(c,injected==1?nonemptyReentryHash:modelSha256,provider.gate(),0),
        rs(r,injected==2?nonemptyReentryHash:modelSha256,provider.gate(),0){}
    bool load(int kind){return kind==0?ws.load(warm):kind==1?cs.load(coast):rs.load(curve);}
    bool checkpoint(int kind){return kind==0?ws.checkpoint(warm,3600000):kind==1?cs.checkpoint(coast,3600000):rs.checkpoint(curve,3600000);}
    void seed(){
        ASSERT_TRUE(load(0));ASSERT_TRUE(load(1));ASSERT_TRUE(load(2));
        auto a=warm.snapshot();a.count=1;a.runs[0]={epoch,epoch+1800,1800,200,500,4500,1900};
        auto b=coast.snapshot();b.count=1;b.runs[0]={epoch,epoch+1800,1800,1800,2100,500,4500,-10,10,-10};
        auto d=curve.snapshot();d.count=1;d.windows[0]={epoch,epoch+14400,14400,500,30,35};
        ASSERT_TRUE(warm.restore(a));ASSERT_TRUE(coast.restore(b));ASSERT_TRUE(curve.restore(d));
        ASSERT_TRUE(ws.checkpoint(warm,0));ASSERT_TRUE(cs.checkpoint(coast,60000));ASSERT_TRUE(rs.checkpoint(curve,120000));
    }
    void faulted(){
        EXPECT_FALSE(provider.healthy());EXPECT_FALSE(ws.healthy());EXPECT_FALSE(cs.healthy());EXPECT_FALSE(rs.healthy());
        EXPECT_STREQ(warm.status(),"model_storage_fault");
        EXPECT_STREQ(coast.status(),"coast_storage_fault");EXPECT_STREQ(curve.status(),"curve_storage_fault");
        EXPECT_EQ(warm.mode(),LearningMode::disabled);EXPECT_EQ(coast.mode(),LearningMode::disabled);EXPECT_EQ(curve.mode(),LearningMode::disabled);
    }
};
auto ioCounts(){return std::array<unsigned,7>{f::opens,f::lengths,f::copies,f::sets,f::commits,f::statsCalls,f::closes};}
void clearIoCounts(){f::opens=f::lengths=f::copies=f::sets=f::commits=f::statsCalls=f::closes=0;}
void decodeReentry(int kind) {
    {ThreeNvs seed;seed.seed();}
    const auto bytes=f::data;
    {
        ThreeNvs subject(kind);
        for(int k=0;k<3;++k)if(k!=kind){ASSERT_TRUE(subject.load(k));}
        clearIoCounts();emptyHashCalls=bodyHashCalls=0;
        decodeGate=&subject.provider.gate();decodeKind=static_cast<ModelKind>(kind);
        EXPECT_FALSE(subject.load(kind));
        decodeGate=nullptr;
        EXPECT_EQ(emptyHashCalls,1u);EXPECT_EQ(bodyHashCalls,1u);
        EXPECT_EQ(f::copies,1u);EXPECT_EQ(f::sets+f::commits,0u);
        subject.faulted();const auto calls=ioCounts();
        for(int k=0;k<3;++k){EXPECT_FALSE(subject.load(k));EXPECT_FALSE(subject.checkpoint(k));}
        EXPECT_EQ(ioCounts(),calls);EXPECT_EQ(f::data,bytes);
    }
}
TEST_F(NvsModelBackend, NonemptyWarmDecodeReentryNeverRestoresOrSucceedsOrRetries) {decodeReentry(0);}
TEST_F(NvsModelBackend, NonemptyCoastDecodeReentryNeverRestoresOrSucceedsOrRetries) {decodeReentry(1);}
TEST_F(NvsModelBackend, NonemptyCurveDecodeReentryNeverRestoresOrSucceedsOrRetries) {decodeReentry(2);}
TEST_F(NvsModelBackend, NonemptyReadMustCheckFreshPartitionEvidenceBeforeAnyOpenOrCopy) {
    for(int kind=0;kind<3;++kind)for(int reason=0;reason<3;++reason) {
        f::reset();{ThreeNvs seed;seed.seed();}
        const auto bytes=f::data;clearIoCounts();
        if(reason==0)f::badStats=true;
        if(reason==1)f::missingPartition=true;
        if(reason==2)f::partitionBytes=65536;
        ThreeNvs subject;
        EXPECT_FALSE(subject.load(kind));
        EXPECT_FALSE(subject.provider.healthy());EXPECT_EQ(f::opens+f::lengths+f::copies+f::sets+f::commits,0u);
        const auto calls=ioCounts();
        EXPECT_FALSE(subject.load(kind));EXPECT_FALSE(subject.checkpoint(kind));
        EXPECT_EQ(ioCounts(),calls);EXPECT_EQ(f::data,bytes);
    }
}
TEST_F(NvsModelBackend, PostCommitFreshStatsFailureStopsReadbackWithoutRetryOrErasingBytes) {
    NativeWarm subject;ASSERT_TRUE(subject.store.load(subject.model));
    f::onStats=[](){if(f::statsCalls==6)f::badStats=true;};
    EXPECT_FALSE(subject.store.checkpoint(subject.model,0));
    EXPECT_EQ(f::sets,1u);EXPECT_EQ(f::commits,1u);EXPECT_EQ(f::copies,0u);
    EXPECT_TRUE(f::data["ot_models_v1"].count("warm_0"));
    const auto bytes=f::data;unchangedAfterFailure(subject);EXPECT_EQ(f::data,bytes);
}
} // namespace
