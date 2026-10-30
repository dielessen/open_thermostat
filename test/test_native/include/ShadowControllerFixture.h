#pragma once
#include "control/ShadowController.h"
#include "ControlTestHash.h"
#include <gtest/gtest.h>
#include <map>
#include <random>

namespace {
using namespace heating::control;
struct Store:ControlStore {
    std::string bytes;
    bool failSave=false,failLoad=false,commitOnError=false,corruptReadback=false,refuseSave=false;
    unsigned writes=0,reads=0,saves=0; // saves: every save() call, refused ones too
    bool load(std::string &out) override { ++reads; if(failLoad) return false; out=bytes; if(corruptReadback&&writes)out+=" "; return true; }
    bool save(std::string_view value) override {
        ++saves;
        if(refuseSave) return false; // budget refusal: no write attempt at all
        ++writes; if(!failSave||commitOnError) bytes=value; return !failSave;
    }
    bool lastSaveRefused() const override { return refuseSave; }
};
const std::string mapping(64,'a');
inline std::string config(unsigned revision=1,const std::string &zones="") {
    return "{\"mapping_digest\":\""+mapping+"\",\"mode\":\"shadow\",\"revision\":"+std::to_string(revision)+
        ",\"schema\":1,\"zones\":["+(zones.empty()?R"({"actuator_id":"trv1","base_centi_c":2100,"max_age_ms":120000,"report_evidence":"physical_report","schedule":null,"sensor_id":"room1","zone_id":"1234abcd"})":zones)+"]}";
}
struct Fixture {
    Store store;
    std::map<std::string,std::string> output;
    std::function<void()> afterPublish;
    ShadowController::Metrics metricsProvider;
    ShadowController::BoilerFields boilerProvider;
    const SeasonalControllerSource* seasonalSource=nullptr;
    SeasonalControllerSource::Safety seasonalSafety;
    const HydraulicControllerSource* hydraulicSource=nullptr;
    const NativePlanInstallationSource* nativeSource=nullptr; // with seasonalSafety set
    HydraulicFeedbackProvider hydraulicFeedback;
    unsigned seasonalObservationSequence=0;
    uint32_t nonce=0;
    std::unique_ptr<ShadowController> core;
    uint64_t now=1000;
    std::string session,grant,boot="boot1",digest;
    uint32_t epoch=1,gseq=1,rev=0;
    void start() {
        core=std::make_unique<ShadowController>("e32_lab",boot,"ha1",store,controlTestHash,
            [this]{return "nonce"+std::to_string(++nonce);},
            [this](auto topic,auto bytes){output[std::string(topic)]=bytes; if(afterPublish)afterPublish();},metricsProvider,seasonalSource,seasonalSafety,nativeSource,boilerProvider,hydraulicSource,hydraulicFeedback);
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
        if(nativeSource) {
            cJSON_AddStringToObject(o.get(),"source_profile_digest",nativeSource->profileDigest.c_str());
            cJSON_AddStringToObject(o.get(),"plan_contract",nativeSource->planContract());
        }
        if(seasonalSource&&!seasonalSource->profileDigest.empty()) {
            cJSON_AddStringToObject(o.get(),"source_profile_digest",seasonalSource->profileDigest.c_str());
            cJSON_AddStringToObject(o.get(),"source_config_pin",seasonalSource->configDigest.c_str());
        }
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

inline std::string metricFixture() {
    auto o=objectJson();cJSON_AddNumberToObject(o.get(),"metricsSchema",2);
    cJSON_AddStringToObject(o.get(),"counterDefinition","observation-total-v2");
    cJSON_AddStringToObject(o.get(),"counterScope","boot");
    cJSON_AddStringToObject(o.get(),"energyQuality","estimated_nominal_modulation");
    cJSON_AddStringToObject(o.get(),"protocolScope","plus");
    cJSON_AddStringToObject(o.get(),"flowQuality","reported_integrated");
    for(auto key:legacyMetricFields)cJSON_AddNullToObject(o.get(),key);
    for(auto key:versionedMetricFields)cJSON_AddNumberToObject(o.get(),key,0);
    cJSON_AddBoolToObject(o.get(),"powerFresh",false);cJSON_AddNumberToObject(o.get(),"outdoorTemperature",-5.7);
    return printJson(o.get());
}
inline ControlJson nonceHeartbeat(Fixture &f,unsigned sequence,const char *nonce) {
    auto o=f.envelope("adapter",sequence);
    if(nonce)cJSON_AddStringToObject(o.get(),"grant_request_nonce",nonce);
    return o;
}
inline std::string comfortConfig(bool context=true) {
    auto root=parseControlJson(config());
    auto z=field(root.get(),"zones")->child;
    auto c=cJSON_AddObjectToObject(z,"comfort");
    cJSON_AddNumberToObject(c,"away_centi_c",1600);cJSON_AddNumberToObject(c,"frost_centi_c",500);
    cJSON_AddNumberToObject(c,"maximum_centi_c",2500);cJSON_AddNumberToObject(c,"minimum_centi_c",500);
    cJSON_AddBoolToObject(c,"presence",context);cJSON_AddNumberToObject(c,"temporary_ms",60000);cJSON_AddBoolToObject(c,"window",context);
    // Configs are canonical sorted-key documents, as on the actual HA path.
    return "{\"mapping_digest\":\""+mapping+"\",\"mode\":\"shadow\",\"revision\":1,\"schema\":1,\"zones\":[{\"actuator_id\":\"trv1\",\"base_centi_c\":2100,\"comfort\":"+printJson(c)+",\"max_age_ms\":120000,\"report_evidence\":\"physical_report\",\"schedule\":null,\"sensor_id\":\"room1\",\"zone_id\":\"1234abcd\"}]}";
}
inline void comfortReady(Fixture &f,bool context=true) {
    f.start();f.connect();f.heartbeat();
    auto cfg=f.configuration(comfortConfig(context));f.send("ha/config",cfg.get());f.connect();f.heartbeat();
    ASSERT_EQ(f.core->revision(),1u);
}
inline ControlJson comfortCommand(Fixture &f,const char *mode,unsigned seq=1,int target=0,unsigned duration=0) {
    auto o=f.envelope("1234abcd",seq);cJSON_AddStringToObject(o.get(),"mode",mode);
    if(target)cJSON_AddNumberToObject(o.get(),"temperature_centi_c",target);else cJSON_AddNullToObject(o.get(),"temperature_centi_c");
    cJSON_AddNumberToObject(o.get(),"duration_ms",duration);cJSON_AddNumberToObject(o.get(),"vacation_until_utc",0);return o;
}
inline ControlJson contextObservation(Fixture &f,unsigned seq=1,bool open=false,bool away=false,bool known=true) {
    auto o=f.observation(seq);
    cJSON_AddBoolToObject(o.get(),"window_open",open);cJSON_AddNumberToObject(o.get(),"window_age_ms",0);
    if(known)cJSON_AddBoolToObject(o.get(),"presence_away",away);else cJSON_AddNullToObject(o.get(),"presence_away");
    cJSON_AddNumberToObject(o.get(),"presence_age_ms",0);return o;
}
}
