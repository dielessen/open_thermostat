// Reuse the real shared graph validator/store fixtures and preserve their tests.
#include "GraphConfigurationFixture.h"
#include "control/GraphControlStoreView.h"
#include "control/ShadowController.h"
namespace {
struct HandoffFixture {
    Fixture graph;
    Store store;
    GraphControlHandoffSource pin;
    SeasonalControllerSource policy;
    std::string projected;
    HandoffFixture() {
        GraphShadowConfiguration owner("e32_test","test_boot","test_owner",graph.anchor,store,controlTestHash);
        if(!owner.initialize())throw std::runtime_error("graph_init");
        // Actual existing graph admission -> single durable commit, not fake apply.
        owner.openSession(identity());owner.issueGrant("test_grant",1,100,1000);
        owner.heartbeat(heartbeat(),100);
        if(owner.apply(graph.raw(),graph.map(),101)!="graph_committed_no_admission")throw std::runtime_error("graph_apply");
        pin={"e32_test","test_owner",graph.anchor,owner.configDigest(),controlTestHash(owner.mappingBytes()),std::string(64,'f'),1,1};
        const auto r=cJSON_GetArrayItem(gt::get(graph.config(),"rooms"),0);
        const auto a=cJSON_GetArrayItem(gt::get(graph.config(),"actuators"),0);
        auto z=objectJson();
        cJSON_AddStringToObject(z.get(),"actuator_id",gt::str(gt::get(a,"actuator_id")).c_str());
        cJSON_AddNumberToObject(z.get(),"base_centi_c",gt::get(r,"base_centi_c")->valuedouble);
        cJSON_AddNumberToObject(z.get(),"max_age_ms",gt::get(r,"max_age_ms")->valuedouble);
        cJSON_AddStringToObject(z.get(),"report_evidence",gt::str(gt::get(r,"report_evidence")).c_str());
        cJSON_AddItemToObject(z.get(),"schedule",cJSON_Duplicate(gt::get(r,"schedule"),true));
        cJSON_AddStringToObject(z.get(),"sensor_id",gt::str(gt::get(r,"sensor_id")).c_str());
        cJSON_AddStringToObject(z.get(),"zone_id",gt::str(gt::get(r,"zone_id")).c_str());
        auto cfg=objectJson();
        cJSON_AddStringToObject(cfg.get(),"mapping_digest",pin.mappingDigest.c_str());
        cJSON_AddStringToObject(cfg.get(),"mode","shadow");cJSON_AddNumberToObject(cfg.get(),"revision",1);
        cJSON_AddNumberToObject(cfg.get(),"schema",1);
        auto zones=cJSON_AddArrayToObject(cfg.get(),"zones");cJSON_AddItemToArray(zones,z.release());
        projected=printJson(cfg.get());
        policy.controllerId=pin.controllerId;policy.configDigest=controlTestHash(projected);
        policy.profileDigest=std::string(64,'f');policy.count=1;policy.maximumSafetyAgeMs=2000;
        auto& source=policy.zones[0];
        source.zoneId=gt::str(gt::get(r,"zone_id"));source.sensorId=gt::str(gt::get(r,"sensor_id"));
        source.actuatorId=gt::str(gt::get(a,"actuator_id"));
        source.minimumTargetCentiC=gt::integer(gt::get(r,"minimum_target_centi_c"),500,3500);
        source.maximumTargetCentiC=gt::integer(gt::get(r,"maximum_target_centi_c"),500,3500);
        source.seasonal.enabled=source.seasonal.installationQualified=true;
        source.seasonal.frostAdviceReviewed=false; // NO floor/frost qualification from DATA.
        source.seasonal.maximumSensorAgeMs=120000;source.seasonal.maximumStepGapMs=300000;
    }
};
struct Controlled {
    HandoffFixture& f;
    GraphControlStoreView view;
    SeasonalSafetySnapshot safety;
    std::unique_ptr<ShadowController> core;
    std::vector<std::pair<std::string,std::string>> frames;
    uint64_t now=1000;unsigned nonce=0,obs=0,commands=0;
    explicit Controlled(HandoffFixture& fixture):f(fixture),
      view("e32_test","test_owner",f.store,controlTestHash,f.pin,f.policy) {
        safety.sampledAt=1000;safety.limitsKnownSafe=safety.dhwStateKnown=true;
        core=std::make_unique<ShadowController>("e32_test","control_boot","test_owner",view,
            controlTestHash,[&]{return "control_nonce_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);},
            ShadowController::Metrics{},&f.policy,[&]{return safety;});
    }
    ControlJson get(const std::string& topic)const {
        for(auto i=frames.rbegin();i!=frames.rend();++i)if(i->first==topic)return parseControlJson(i->second);
        return ControlJson(nullptr,cJSON_Delete);
    }
    void send(const char* topic,const cJSON* raw){core->receive(topic,printJson(raw),now,1792368000,true);}
    ControlJson envelope(const char* binding,unsigned sequence) {
        auto session=get("fw/session");auto o=objectJson();
        for(auto key:{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id","grant_sequence","config_revision"})
            cJSON_AddItemToObject(o.get(),key,cJSON_Duplicate(field(session.get(),key),true));
        cJSON_AddStringToObject(o.get(),"binding_id",binding);cJSON_AddNumberToObject(o.get(),"sequence",sequence);return o;
    }
    void connect() {
        core->connected(now);core->tick(now,1792368000,true);auto h=get("fw/hello");auto o=objectJson();
        for(auto key:{"api","controller_id","boot_id","epoch","challenge_id"})cJSON_AddItemToObject(o.get(),key,cJSON_Duplicate(field(h.get(),key),true));
        cJSON_AddStringToObject(o.get(),"adapter_id","test_owner");
        cJSON_AddStringToObject(o.get(),"client_nonce","native_handoff");
        cJSON_AddNumberToObject(o.get(),"known_revision",1);cJSON_AddStringToObject(o.get(),"known_digest",f.policy.configDigest.c_str());
        cJSON_AddStringToObject(o.get(),"source_profile_digest",f.policy.profileDigest.c_str());
        cJSON_AddStringToObject(o.get(),"source_config_pin",f.policy.configDigest.c_str());send("ha/open_session",o.get());
        auto hb=envelope("adapter",1);send("ha/heartbeat",hb.get());
    }
    ControlJson observe() {
        auto o=envelope(f.policy.zones[0].sensorId.c_str(),++obs);
        cJSON_AddStringToObject(o.get(),"zone_id",f.policy.zones[0].zoneId.c_str());
        cJSON_AddBoolToObject(o.get(),"source_available",true);
        auto cfg=parseControlJson(f.projected);auto z=cJSON_GetArrayItem(field(cfg.get(),"zones"),0);
        cJSON_AddNumberToObject(o.get(),"temperature_c",(uintField(z,"base_centi_c")-100)/100.0);
        cJSON_AddNumberToObject(o.get(),"source_sample_age_ms",0);
        cJSON_AddStringToObject(o.get(),"evidence",stringField(z,"report_evidence").c_str());
        send("ha/observations",o.get());return get("fw/state/zones");
    }
    const cJSON* row(const ControlJson& s)const{return cJSON_GetArrayItem(field(s.get(),"zones"),0);}
    ControlJson command(int target,const char* mode="temporary") {
        auto o=envelope(f.policy.zones[0].zoneId.c_str(),++commands);
        cJSON_AddStringToObject(o.get(),"mode",mode);cJSON_AddNumberToObject(o.get(),"temperature_centi_c",target);
        cJSON_AddNumberToObject(o.get(),"duration_ms",60000);return o;
    }
};
TEST(GraphControlHandoff, ExactCommittedTupleIsReadOnlyProjectedIntoExistingController) {
    HandoffFixture f;auto bytes=f.store.bytes;Controlled c(f);
    ASSERT_FALSE(c.core->faulted());ASSERT_EQ(c.core->revision(),1u);
    ASSERT_EQ(c.core->digest(),f.policy.configDigest);EXPECT_EQ(f.store.bytes,bytes);EXPECT_EQ(f.store.writes,1);
    c.connect();c.observe();auto s=c.observe();
    ASSERT_TRUE(s);EXPECT_TRUE(cJSON_IsTrue(field(c.row(s),"demand")));
    EXPECT_TRUE(cJSON_IsFalse(field(s.get(),"boiler_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(s.get(),"actuator_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(field(s.get(),"supervisor"),"physical_outputs_enabled")));
    auto request=c.envelope("snapshot",1);c.send("ha/snapshot_request",request.get());
    auto read=c.get("fw/config_snapshot");ASSERT_TRUE(read);
    EXPECT_EQ(printJson(field(read.get(),"config")),f.projected);EXPECT_EQ(f.store.bytes,bytes);
}
TEST(GraphControlHandoff, DataReadbackWithoutExplicitSourceNeverBecomesControl) {
    HandoffFixture f;ShadowController ordinary("e32_test","control_boot","test_owner",f.store,controlTestHash,
        []{return "nonce";},[](auto,auto){});
    EXPECT_TRUE(ordinary.faulted());EXPECT_EQ(f.store.writes,1);
}
TEST(GraphControlHandoff, TupleOwnerProfileBindingAndBoundsRejectWithoutWrites) {
    for(unsigned kind=0;kind<14;++kind) {
        HandoffFixture f;const auto original=f.store.bytes;
        if(kind==0)f.pin.configDigest=std::string(64,'0');
        if(kind==1)f.pin.mappingDigest=std::string(64,'0');
        if(kind==2)f.pin.qualificationDigest=std::string(64,'0');
        if(kind==3)f.pin.adapterId="foreign";
        if(kind==4)f.pin.controllerId="foreign";
        if(kind==5)f.pin.revision=2;
        if(kind==6)f.pin.mappingRevision=2;
        if(kind==7)f.policy.profileDigest.clear();
        if(kind==8)f.policy.zones[0].sensorId="other";
        if(kind==9)f.policy.zones[0].actuatorId="other";
        if(kind==10)--f.policy.zones[0].minimumTargetCentiC;
        if(kind==11)++f.policy.zones[0].maximumTargetCentiC;
        if(kind==12)f.policy.configDigest=std::string(64,'0');
        if(kind==13)f.policy.profileDigest=std::string(64,'0');
        Controlled c(f);EXPECT_TRUE(c.core->faulted())<<kind;
        EXPECT_EQ(f.store.bytes,original)<<kind;EXPECT_EQ(f.store.writes,1)<<kind;
    }
}
TEST(GraphControlHandoff, ReadFailureOversizeUnknownSchemaAndWriteAttemptLatchNoRetry) {
    for(unsigned kind=0;kind<4;++kind) {
        HandoffFixture f;
        if(kind==0)f.store.readOk=false;
        if(kind==1)f.store.bytes.assign(4097,'x');
        if(kind==2)f.store.bytes="{\"schema\":99}";
        const auto original=f.store.bytes;
        GraphControlStoreView view("e32_test","test_owner",f.store,controlTestHash,f.pin,f.policy);
        std::string out="old";
        if(kind==3){EXPECT_FALSE(view.save(f.projected));}
        EXPECT_FALSE(view.load(out));EXPECT_TRUE(out.empty());EXPECT_TRUE(view.faulted());
        EXPECT_FALSE(view.load(out));EXPECT_EQ(f.store.bytes,original);EXPECT_EQ(f.store.writes,1);
    }
}
TEST(GraphControlHandoff, NonemptyHashReentryOrWriteFaultCannotReturnProjectionSuccess) {
    for(bool write:{false,true}) {
        HandoffFixture f;GraphControlStoreView* selected=nullptr;bool attack=false;unsigned calls=0;
        auto hash=[&](std::string_view raw) {
            if(attack&&!raw.empty()&&calls++==0) {
                if(write)selected->save("no");
                else {std::string nested;selected->load(nested);}
            }
            return controlTestHash(raw);
        };
        GraphControlStoreView view("e32_test","test_owner",f.store,hash,f.pin,f.policy);selected=&view;attack=true;
        std::string out;EXPECT_FALSE(view.load(out));EXPECT_TRUE(out.empty());EXPECT_TRUE(view.faulted());
        EXPECT_FALSE(view.load(out));EXPECT_EQ(f.store.writes,1);
    }
}
TEST(GraphControlHandoff, GraphTargetBoundsRejectCommandBeforeSequenceAndStopStillWins) {
    HandoffFixture f;Controlled c(f);ASSERT_FALSE(c.core->faulted());c.connect();c.observe();c.observe();
    auto command=c.command(f.policy.zones[0].maximumTargetCentiC+1);
    const auto count=c.frames.size();c.send("ha/user_command",command.get());
    EXPECT_EQ(c.frames.size(),count);
    cJSON_SetNumberValue(const_cast<cJSON*>(field(command.get(),"temperature_centi_c")),f.policy.zones[0].maximumTargetCentiC);
    c.send("ha/user_command",command.get());auto s=c.get("fw/state/zones");
    EXPECT_EQ(uintField(c.row(s),"target_centi_c"),static_cast<unsigned>(f.policy.zones[0].maximumTargetCentiC));
    auto off=c.command(500,"off");c.send("ha/user_command",off.get());
    auto stopped=c.get("fw/state/zones");EXPECT_TRUE(cJSON_IsFalse(field(c.row(stopped),"demand")));
    EXPECT_EQ(f.store.writes,1);
}
TEST(GraphControlHandoff, SourceBoundsRejectStoredBaseAndScheduleEvenWithMatchingHash) {
    for(unsigned kind=0;kind<3;++kind) {
        HandoffFixture f;auto config=parseControlJson(f.projected);
        auto z=const_cast<cJSON*>(cJSON_GetArrayItem(field(config.get(),"zones"),0));
        if(kind==0)cJSON_SetNumberValue(const_cast<cJSON*>(field(z,"base_centi_c")),2500);
        else {
            auto schedule=parseControlJson(R"({"base_centi_c":2100,"policy":"wall-clock-membership/v1","timezone":"UTC","transitions":[[1792368000,2100]],"valid_from_utc":1792368000,"valid_until_utc":1792454400})");
            if(kind==1)cJSON_SetNumberValue(const_cast<cJSON*>(field(schedule.get(),"base_centi_c")),2500);
            if(kind==2)cJSON_SetNumberValue(cJSON_GetArrayItem(cJSON_GetArrayItem(field(schedule.get(),"transitions"),0),1),2500);
            cJSON_ReplaceItemInObjectCaseSensitive(z,"schedule",schedule.release());
        }
        Store existing;existing.bytes=printJson(config.get());f.policy.configDigest=controlTestHash(existing.bytes);
        ShadowController core("e32_test","bounds_boot","test_owner",existing,controlTestHash,
            []{return "nonce";},[](auto,auto){},ShadowController::Metrics{},&f.policy,[]{return SeasonalSafetySnapshot{};});
        EXPECT_TRUE(core.faulted())<<kind;EXPECT_EQ(existing.writes,0);
    }
}
TEST(GraphControlHandoff, InvalidSourceLimitOrUnreviewedFrostNeverCreatesProtection) {
    HandoffFixture f;
    EXPECT_TRUE(f.policy.valid());EXPECT_FALSE(f.policy.zones[0].seasonal.frostAdviceReviewed);
    f.policy.zones[0].minimumTargetCentiC=2401;EXPECT_FALSE(f.policy.valid());
    f.policy.zones[0].minimumTargetCentiC=1600;
    f.policy.zones[0].seasonal.frostAdviceReviewed=true;EXPECT_FALSE(f.policy.valid());
}
TEST(GraphControlHandoff, SourceExpirySummerDhwAndDisconnectNeverReuseDemand) {
    for(unsigned kind=0;kind<5;++kind) {
        HandoffFixture f;Controlled c(f);ASSERT_FALSE(c.core->faulted());c.connect();c.observe();auto heat=c.observe();
        ASSERT_TRUE(cJSON_IsTrue(field(c.row(heat),"demand")));
        if(kind==0)c.now=3000;
        if(kind==1)c.safety.summer=true;
        if(kind==2)c.safety.allOff=true;
        if(kind==3)c.safety.dhwActive=true;
        if(kind==4){c.core->disconnected();c.now=1001;c.connect();}
        auto off=c.observe();EXPECT_TRUE(cJSON_IsFalse(field(c.row(off),"demand")))<<kind;
        EXPECT_EQ(f.store.writes,1);
    }
}
}
