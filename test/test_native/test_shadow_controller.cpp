#include "control/ShadowController.h"
#include "ControlTestHash.h"
#include <gtest/gtest.h>
#include <map>
#include <random>

namespace {
using namespace heating::control;
struct Store:ControlStore {
    std::string bytes;
    bool failSave=false,failLoad=false,commitOnError=false,corruptReadback=false;
    unsigned writes=0;
    bool load(std::string &out) override { if(failLoad) return false; out=bytes; if(corruptReadback&&writes)out+=" "; return true; }
    bool save(std::string_view value) override { ++writes; if(!failSave||commitOnError) bytes=value; return !failSave; }
};
const std::string mapping(64,'a');
std::string config(unsigned revision=1,const std::string &zones="") {
    return "{\"mapping_digest\":\""+mapping+"\",\"mode\":\"shadow\",\"revision\":"+std::to_string(revision)+
        ",\"schema\":1,\"zones\":["+(zones.empty()?R"({"actuator_id":"trv1","base_centi_c":2100,"max_age_ms":120000,"report_evidence":"physical_report","schedule":null,"sensor_id":"room1","zone_id":"1234abcd"})":zones)+"]}";
}
struct Fixture {
    Store store;
    std::map<std::string,std::string> output;
    std::function<void()> afterPublish;
    uint32_t nonce=0;
    std::unique_ptr<ShadowController> core;
    uint64_t now=1000;
    std::string session,grant,boot="boot1",digest;
    uint32_t epoch=1,gseq=1,rev=0;
    void start() {
        core=std::make_unique<ShadowController>("e32_lab",boot,"ha1",store,controlTestHash,
            [this]{return "nonce"+std::to_string(++nonce);},
            [this](auto topic,auto bytes){output[std::string(topic)]=bytes; if(afterPublish)afterPublish();});
        core->connected(now); tick();
    }
    ControlJson get(const std::string &topic) { return parseControlJson(output.at(topic)); }
    void tick() { core->tick(now,1792368000,true); }
    void send(const char *topic,const cJSON *o) { core->receive(topic,printJson(o),now,1792368000,true); }
    void connect(bool wrongMapping=false) {
        now+=1; core->tick(now+3000,1792368000,true); now+=3000;
        auto h=get("fw/hello"); epoch=uintField(h.get(),"epoch"); rev=uintField(h.get(),"config_revision"); digest=stringField(h.get(),"config_digest");
        auto o=objectJson();
        cJSON_AddNumberToObject(o.get(),"api",1); cJSON_AddStringToObject(o.get(),"controller_id","e32_lab");
        cJSON_AddStringToObject(o.get(),"boot_id",boot.c_str()); cJSON_AddNumberToObject(o.get(),"epoch",epoch);
        cJSON_AddStringToObject(o.get(),"adapter_id","ha1"); cJSON_AddStringToObject(o.get(),"client_nonce","client1");
        cJSON_AddStringToObject(o.get(),"challenge_id",stringField(h.get(),"challenge_id").c_str());
        cJSON_AddNumberToObject(o.get(),"known_revision",wrongMapping?0:rev); cJSON_AddStringToObject(o.get(),"known_digest",wrongMapping?"":digest.c_str());
        send("ha/open_session",o.get()); syncSession();
    }
    void syncSession() {
        auto s=get("fw/session"); session=stringField(s.get(),"adapter_session_id");
        grant=stringField(s.get(),"grant_id"); gseq=uintField(s.get(),"grant_sequence");
    }
    ControlJson envelope(const char *binding,unsigned seq=1) {
        auto o=objectJson();
        cJSON_AddNumberToObject(o.get(),"api",1); cJSON_AddStringToObject(o.get(),"controller_id","e32_lab");
        cJSON_AddStringToObject(o.get(),"boot_id",boot.c_str()); cJSON_AddNumberToObject(o.get(),"epoch",epoch);
        cJSON_AddStringToObject(o.get(),"adapter_id","ha1"); cJSON_AddStringToObject(o.get(),"adapter_session_id",session.c_str());
        cJSON_AddStringToObject(o.get(),"grant_id",grant.c_str()); cJSON_AddNumberToObject(o.get(),"grant_sequence",gseq);
        cJSON_AddNumberToObject(o.get(),"config_revision",rev); cJSON_AddStringToObject(o.get(),"binding_id",binding);
        cJSON_AddNumberToObject(o.get(),"sequence",seq); return o;
    }
    void heartbeat(unsigned seq=1) { auto o=envelope("adapter",seq); send("ha/heartbeat",o.get()); }
    ControlJson configuration(std::string bytes=config(),unsigned sequence=1) {
        auto o=envelope("config",sequence); cJSON_AddNumberToObject(o.get(),"expected_revision",rev);
        cJSON_AddStringToObject(o.get(),"config_digest",controlTestHash(bytes).c_str());
        cJSON_AddItemToObject(o.get(),"config",cJSON_Parse(bytes.c_str())); return o;
    }
    void configure() { auto o=configuration(); send("ha/config",o.get()); }
    void ready() { start(); connect(); heartbeat(); configure(); connect(); heartbeat(); }
    ControlJson observation(unsigned seq=1,double temperature=19,const char *evidence="physical_report",unsigned age=0) {
        auto o=envelope("room1",seq); cJSON_AddStringToObject(o.get(),"zone_id","1234abcd");
        cJSON_AddBoolToObject(o.get(),"source_available",true); cJSON_AddNumberToObject(o.get(),"temperature_c",temperature);
        cJSON_AddNumberToObject(o.get(),"source_sample_age_ms",age); cJSON_AddStringToObject(o.get(),"evidence",evidence); return o;
    }
    ControlJson command(const char *mode="temporary",unsigned seq=1,int target=2300) {
        auto o=envelope("1234abcd",seq); cJSON_AddStringToObject(o.get(),"mode",mode);
        cJSON_AddNumberToObject(o.get(),"temperature_centi_c",target); cJSON_AddNumberToObject(o.get(),"duration_ms",60000); return o;
    }
    ControlJson state() { return get("fw/state/zones"); }
    static const cJSON *row(const ControlJson &s) { return field(s.get(),"zones")->child; }
};

TEST(ShadowRuntime, ActualWireConfigurationObservationAndTargetRoundTripNeverEnablesOutputs) {
    Fixture f; f.ready(); ASSERT_EQ(f.core->revision(),1u); EXPECT_EQ(f.store.writes,1u);
    auto o=f.observation(); f.send("ha/observations",o.get());
    auto state=f.state(); ASSERT_NE(Fixture::row(state),nullptr);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(state),"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    auto command=f.command(); f.send("ha/user_command",command.get());
    auto s=f.state(); EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2300u);
    EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"temporary");
}
TEST(ShadowRuntime, HeartbeatsAndCacheReportsCannotMakeStaleSourceFresh) {
    Fixture f; f.ready(); auto o=f.observation(1,19,"unverified"); f.send("ha/observations",o.get());
    auto s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    auto valid=f.observation(2,19,"physical_report",119000); f.now+=2000; f.send("ha/observations",valid.get());
    s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand"))); // conservative grant elapsed included
    auto fresh=f.observation(3); f.send("ha/observations",fresh.get());
    s=f.state(); EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    for(unsigned i=0;i<25;++i) { f.now+=5000; f.tick(); f.syncSession(); f.heartbeat(2+i); }
    f.now+=3000; f.tick(); s=f.state();
    EXPECT_TRUE(cJSON_IsTrue(field(s.get(),"adapter_alive")));
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"temperature_centi_c")));
}
TEST(ShadowRuntime, DuplicateChangedPayloadAndOldSequenceNeverReapplyOverride) {
    Fixture f; f.ready(); auto command=f.command(); f.send("ha/user_command",command.get());
    f.now+=1000; f.send("ha/user_command",command.get());
    auto ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"duplicate");
    cJSON_ReplaceItemInObjectCaseSensitive(command.get(),"temperature_centi_c",cJSON_CreateNumber(3000)); f.send("ha/user_command",command.get());
    ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"rejected");
    for(unsigned i=0;i<13;++i) { f.now+=5000; f.tick(); f.syncSession(); f.heartbeat(i+2); }
    f.now+=3000; f.tick(); auto s=f.state(); EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"base");
    auto old=f.command("temporary",1,3000); f.send("ha/user_command",old.get());
    ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"rejected");
}
TEST(ShadowRuntime, AtomicCommitFailuresIncludingCommittedButLostAckForceRecovery) {
    for(bool committed:{false,true}) {
        Fixture f; f.start(); f.connect(); f.heartbeat(); f.store.failSave=true; f.store.commitOnError=committed;
        f.configure(); EXPECT_TRUE(f.core->faulted()); EXPECT_EQ(f.core->revision(),0u);
        auto ack=f.get("fw/config_result"); EXPECT_EQ(stringField(ack.get(),"status"),"storage_fault");
        f.store.failSave=false; f.boot="boot2"; f.start();
        EXPECT_FALSE(f.core->faulted()); EXPECT_EQ(f.core->revision(),committed?1u:0u);
    }
}
TEST(ShadowRuntime, RebootReadbackMismatchAndDisconnectFenceAllOldPackets) {
    Fixture f; f.ready(); auto old=f.observation(); f.send("ha/observations",old.get());
    f.boot="boot2"; f.start(); EXPECT_EQ(f.core->revision(),1u); f.connect(true); f.heartbeat();
    f.send("ha/observations",old.get()); auto s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    auto obs=f.observation(2); f.send("ha/observations",obs.get());
    auto ack=f.get("fw/observation_result"); EXPECT_EQ(stringField(ack.get(),"status"),"mapping_conflict");
    auto request=f.envelope("snapshot"); f.send("ha/snapshot_request",request.get());
    auto snapshot=f.get("fw/config_snapshot"); EXPECT_EQ(uintField(snapshot.get(),"config_revision"),1u);
    f.core->disconnected(); f.core->connected(f.now); f.now+=3000; f.tick();
    s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"adapter_alive")));
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"temperature_centi_c")));
}
TEST(ShadowRuntime, MissingHeartbeatSessionExpiresAndDelayedHeartbeatCannotReviveIt) {
    Fixture f; f.start(); f.connect(); const auto oldSession=f.session; auto heartbeat=f.envelope("adapter");
    f.now+=15000; f.send("ha/heartbeat",heartbeat.get()); f.tick(); f.connect(); EXPECT_NE(f.session,oldSession);
}
TEST(ShadowRuntime, InvalidConfigDoesNotConsumeSequenceOrTouchStoreAndWrongOwnerFailsClosed) {
    Fixture f; f.start(); f.connect(); f.heartbeat(); auto bad=f.configuration();
    cJSON_ReplaceItemInObjectCaseSensitive(bad.get(),"config_digest",cJSON_CreateString(mapping.c_str()));
    f.send("ha/config",bad.get()); EXPECT_EQ(f.store.writes,0u); f.configure(); EXPECT_EQ(f.store.writes,1u);
    auto cfg=config(2); auto pos=cfg.find("shadow"); cfg.replace(pos,6,"active");
    f.connect(); f.heartbeat(); auto unsupported=f.configuration(cfg); f.send("ha/config",unsupported.get()); EXPECT_EQ(f.store.writes,1u);
    auto duplicate=config(2); pos=duplicate.find("\"max_age_ms\":120000"); duplicate.replace(pos,19,"\"max_age_ms\":true");
    auto boolean=f.configuration(duplicate); f.send("ha/config",boolean.get()); EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, StoreCorruptionIsDiagnosedAndReadOnlySnapshotsNeverWrite) {
    Fixture f; f.store.bytes="{broken"; f.start(); EXPECT_TRUE(f.core->faulted());
    Fixture ok; ok.ready(); auto request=ok.envelope("snapshot"); ok.send("ha/snapshot_request",request.get());
    auto snapshot=ok.get("fw/config_snapshot"); EXPECT_EQ(uintField(snapshot.get(),"config_revision"),1u);
    EXPECT_EQ(controlTestHash(printJson(field(snapshot.get(),"config"))),ok.core->digest()); EXPECT_EQ(ok.store.writes,1u);
}
TEST(ShadowRuntime, ReadbackErrorNeverPartiallyActivatesAndWrongOwnerCannotOpen) {
    Fixture f; f.start(); f.connect(); f.heartbeat(); f.store.corruptReadback=true; f.configure();
    EXPECT_TRUE(f.core->faulted()); EXPECT_EQ(f.core->revision(),0u);
    Fixture wrong; wrong.start(); auto hello=wrong.get("fw/hello");
    std::string raw=R"({"api":1,"controller_id":"e32_lab","boot_id":"boot1","epoch":1,"challenge_id":")"+
        stringField(hello.get(),"challenge_id")+R"(","adapter_id":"other_ha","client_nonce":"new","known_revision":0,"known_digest":""})";
    wrong.core->receive("ha/open_session",raw,wrong.now,1792368000,true);
    EXPECT_FALSE(wrong.output.count("fw/session"));
}
TEST(ShadowRuntime, EightZonesAreBoundedAndDuplicateSensorCannotReplaceAcceptedConfig) {
    std::string zones;
    for(unsigned i=0;i<8;++i) {
        auto z=R"({"actuator_id":"trv)"+std::to_string(i)+R"(","base_centi_c":2100,"max_age_ms":120000,"report_evidence":"physical_report","schedule":null,"sensor_id":"room)"+
            std::to_string(i)+R"(","zone_id":"1234abc)"+std::to_string(i)+R"("})";
        if(i) zones+=",";
        zones+=z;
    }
    Fixture f; f.start(); f.connect(); f.heartbeat(); auto eight=f.configuration(config(1,zones)); f.send("ha/config",eight.get());
    EXPECT_EQ(f.core->revision(),1u); f.connect(); f.heartbeat(); f.now+=3000; f.tick();
    auto state=f.state(); EXPECT_EQ(cJSON_GetArraySize(field(state.get(),"zones")),8);
    const auto position=zones.find("room1"); ASSERT_NE(position,std::string::npos); zones.replace(position,5,"room0");
    auto invalid=f.configuration(config(2,zones)); f.send("ha/config",invalid.get()); EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, KnownHashAndSeededRawMalformedWireNeverEnableAnyOutput) {
    EXPECT_EQ(controlTestHash("abc"),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    Fixture f; f.ready(); auto command=f.command(); const auto valid=printJson(command.get());
    std::mt19937 random(0x20261020);
    for(unsigned i=0;i<30000;++i) {
        std::string bytes;
        if(i%2) { bytes=valid; bytes[random()%bytes.size()]=static_cast<char>(random()%256); }
        else { bytes.resize(random()%1000); for(auto &c:bytes)c=static_cast<char>(random()%256); }
        f.core->receive("ha/user_command",bytes,f.now,1792368000,true);
    }
    f.now+=3000; f.tick(); auto state=f.state();
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, PubSubClientReceiveBufferReuseCannotEraseSnapshotRetryTopic) {
    Fixture f; f.ready(); auto request=f.envelope("snapshot"); f.send("ha/snapshot_request",request.get());
    f.output.erase("fw/config_snapshot");
    std::string topic="ha/snapshot_request";
    f.afterPublish=[&]{std::fill(topic.begin(),topic.end(),'x');};
    f.core->receive(topic,printJson(request.get()),f.now,1792368000,true);
    EXPECT_TRUE(f.output.count("fw/config_snapshot"));
}

TEST(ShadowRuntime, RealDemandIsNotUnqualifiedHydraulicReadinessAndReconnectClearsBand) {
    Fixture f; f.ready(); auto cold=f.observation(1,19);
    f.send("ha/observations",cold.get()); auto first=f.state();
    auto supervisor=field(first.get(),"supervisor");
    ASSERT_NE(supervisor,nullptr);
    EXPECT_STREQ(stringField(supervisor,"reason").c_str(),"hydraulic_profile_unqualified");
    EXPECT_TRUE(cJSON_IsTrue(field(supervisor,"requested_heat")));
    EXPECT_FALSE(cJSON_IsTrue(field(supervisor,"physical_outputs_enabled")));
    f.core->disconnected(); f.core->connected(f.now); f.connect(); f.heartbeat();
    auto band=f.observation(1,21);
    f.send("ha/observations",band.get()); auto after=f.state();
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(after),"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(after.get(),"boiler_output_enabled")));
}

}
