#pragma once
#include "BoundedJson.h"
#include "ControlStore.h"
#include "EffectiveTarget.h"
#include "Measurement.h"
#include "ScheduleDocument.h"
#include "SessionAdmission.h"
#include "ZoneRegulator.h"
#include "HydraulicSupervisor.h"
#include <algorithm>
#include <functional>
#include <set>
#include <vector>

namespace heating::control {

inline const cJSON *field(const cJSON *o, const char *key) { return cJSON_GetObjectItemCaseSensitive(o,key); }
inline std::string stringField(const cJSON *o,const char *key) {
    auto p=field(o,key); return cJSON_IsString(p) && p->valuestring ? p->valuestring : "";
}
inline bool integerField(const cJSON *o,const char *key,uint64_t lo,uint64_t hi) {
    auto p=field(o,key); return cJSON_IsNumber(p) && std::isfinite(p->valuedouble) &&
        p->valuedouble>=lo && p->valuedouble<=hi && std::floor(p->valuedouble)==p->valuedouble;
}
inline uint64_t uintField(const cJSON *o,const char *key) { return static_cast<uint64_t>(field(o,key)->valuedouble); }
inline bool exactFields(const cJSON *o,std::initializer_list<const char *> keys) {
    if(!cJSON_IsObject(o) || cJSON_GetArraySize(o)!=static_cast<int>(keys.size())) return false;
    for(auto key:keys) if(!field(o,key)) return false;
    return true; // parseControlJson already rejects duplicate members recursively.
}
inline bool hexString(std::string_view s,size_t size) {
    if(s.size()!=size) return false;
    for(char c:s) if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
    return true;
}
inline std::string printJson(const cJSON *o) {
    std::unique_ptr<char,decltype(&cJSON_free)> s(cJSON_PrintUnformatted(o),cJSON_free);
    return s ? s.get() : "";
}
inline ControlJson objectJson() { return ControlJson(cJSON_CreateObject(),cJSON_Delete); }
inline bool canonicalConfig(const cJSON *o) {
    if(cJSON_IsNumber(o) && (!std::isfinite(o->valuedouble) || std::floor(o->valuedouble)!=o->valuedouble)) return false;
    const char *previous=nullptr;
    for(auto p=o->child;p;p=p->next) {
        if(cJSON_IsObject(o)) {
            if(!p->string || (previous && std::strcmp(previous,p->string)>=0)) return false;
            previous=p->string;
        }
        if(!canonicalConfig(p)) return false;
    }
    return true;
}


class ShadowController {
public:
    using Hash=std::function<std::string(std::string_view)>;
    using Nonce=std::function<std::string()>;
    using Publish=std::function<void(std::string_view,std::string_view)>;
    // Existing NVS partition is20KiB, with GC + old/new atomic blob overhead.
    // Do not turn a JSON transport ceiling into a hidden persistence promise.
    static constexpr size_t maximumZones=8, maximumConfigBytes=4096;
    static constexpr uint32_t grantMs=10000, leaseMs=15000;
    ShadowController(std::string controller,std::string boot,std::string owner,
                     ControlStore &store,Hash hash,Nonce nonce,Publish publish)
        :controller_(std::move(controller)),boot_(std::move(boot)),owner_(std::move(owner)),
         store_(store),hash_(std::move(hash)),nonce_(std::move(nonce)),publish_(std::move(publish)),admission_(owner_) {
        if(!SessionAdmission::validId(controller_)||!SessionAdmission::validId(boot_)||!SessionAdmission::validId(owner_)) { fault_=true; return; }
        std::string saved;
        if(!store_.load(saved)) { fault_=true; return; }
        if(saved.empty()) return;
        auto root=parseControlJson(saved);
        if(!root || saved.size()>maximumConfigBytes || !decodeConfig(root.get(),*config_)) { fault_=true; return; }
        configBytes_=printJson(root.get()); digest_=hash_(configBytes_);
        if(!hexString(digest_,64)) fault_=true;
    }
    void connected(uint64_t now) {
        invalidate();
        if(epoch_==UINT32_MAX) { fault_=true; return; }
        ++epoch_; connected_=true; newChallenge(now); nextHello_=nextState_=now;
    }
    void disconnected() { connected_=false; invalidate(); }
    void tick(uint64_t now,int64_t utc,bool clockValid) {
        if(!connected_) return;
        if(now<lastNow_) { fault_=true; invalidate(); }
        lastNow_=now;
        if(session_ && !admission_.alive(now) && (leaseWasAlive_ || now>=sessionStart_+leaseMs)) { invalidate(); newChallenge(now); }
        if(now>=challengeUntil_) newChallenge(now);
        if(session_ && now>=nextGrant_) {
            if(grantSequence_==UINT32_MAX || !newGrant(now)) { invalidate(); newChallenge(now); }
            else sessionStatus();
        }
        if(now>=nextHello_) { hello(); nextHello_=now+3000; }
        if(now>=nextState_) { state(now,utc,clockValid); nextState_=now+3000; }
    }
    void receive(std::string_view topic,std::string_view bytes,uint64_t now,int64_t utc,bool clockValid) {
        if(!connected_ || fault_ || now<lastNow_) return;
        // PubSubClient reuses its receive buffer for synchronous publish(). A
        // response must not invalidate the topic view used later in this call.
        if(topic.size()>32) return;
        const std::string ownedTopic(topic); topic=ownedTopic;
        if(session_ && !admission_.alive(now) && (leaseWasAlive_ || now>=sessionStart_+leaseMs)) {
            invalidate(); newChallenge(now); hello(); return;
        }
        auto root=parseControlJson(bytes);
        if(!root || !cJSON_IsObject(root.get())) return;
        if(topic=="ha/open_session") { open(root.get(),now); return; }
        StreamKind kind;
        size_t stream;
        const char *resultTopic;
        if(topic=="ha/heartbeat") { kind=StreamKind::heartbeat; stream=0; resultTopic="fw/heartbeat_result"; }
        else if(topic=="ha/config") { kind=StreamKind::configuration; stream=1; resultTopic="fw/config_result"; }
        else if(topic=="ha/snapshot_request") { kind=StreamKind::configuration; stream=2; resultTopic="fw/snapshot_result"; }
        else if(topic=="ha/observations") { kind=StreamKind::observation; stream=3; resultTopic="fw/observation_result"; }
        else if(topic=="ha/user_command") { kind=StreamKind::user_command; stream=11; resultTopic="fw/user_command_result"; }
        else return;
        Envelope e;
        if(!envelope(root.get(),kind,e)) return;
        int index=-1;
        if(topic=="ha/observations" || topic=="ha/user_command") {
            for(size_t i=0;i<config_->count;++i)
                if(e.binding==(kind==StreamKind::observation?config_->zones[i].sensor:config_->zones[i].id)) { index=i; stream+=i; break; }
            if(index<0) return;
        }
        // Validate whole body BEFORE consuming its sequence or changing a source.
        auto candidate=std::make_unique<Configuration>();
        std::string candidateBytes;
        if(!shape(root.get(),topic,index,*candidate,candidateBytes)) return;
        if(kind!=StreamKind::heartbeat && kind!=StreamKind::configuration && !mappingReady_) {
            result(resultTopic,e,"mapping_conflict"); return;
        }
        auto payloadHash=hash_(bytes);
        if(!hexString(payloadHash,64)) { fault_=true; invalidate(); return; }
        for(size_t i=0;i<32;++i) e.payloadDigest[i]=static_cast<uint8_t>(hexByte(payloadHash[2*i])*16+hexByte(payloadHash[2*i+1]));
        const auto a=admission_.admit(stream,e,now);
        if(a.code==AdmissionCode::duplicate) { result(resultTopic,e,"duplicate"); if(topic=="ha/snapshot_request") snapshot(); return; }
        if(a.code!=AdmissionCode::accepted) { result(resultTopic,e,"rejected"); return; }
        if(kind==StreamKind::heartbeat) { leaseWasAlive_=true; result(resultTopic,e,"accepted"); return; }
        if(topic=="ha/config") {
            if(uintField(root.get(),"expected_revision")!=revision() || revision()==UINT32_MAX || candidate->revision!=revision()+1) {
                result(resultTopic,e,"conflict"); return;
            }
            // Storage can have committed despite a timeout/error. Never continue
            // operating old memory after an ambiguous durable write/read-back.
            std::string readback;
            if(!store_.save(candidateBytes)||!store_.load(readback)||readback!=candidateBytes) {
                result(resultTopic,e,"storage_fault"); fault_=true; invalidate(); return;
            }
            config_=std::move(candidate); configBytes_=candidateBytes; digest_=stringField(root.get(),"config_digest");
            result(resultTopic,e,"applied"); invalidate(); newChallenge(now); hello(); return;
        }
        if(topic=="ha/snapshot_request") { result(resultTopic,e,"accepted"); snapshot(); state(now,utc,clockValid); return; }
        auto &z=config_->zones[index];
        if(kind==StreamKind::observation) {
            if(cJSON_IsFalse(field(root.get(),"source_available"))) z.sample.unavailable();
            else {
                const auto evidence=stringField(root.get(),"evidence");
                auto ev=evidence=="physical_report"?SampleEvidence::physical_report:
                    evidence=="validated_integration_report"?SampleEvidence::validated_integration_report:SampleEvidence::unknown;
                // Configured provenance is exact, not an incoming privilege.
                if(evidence!=z.reportEvidence) ev=SampleEvidence::unknown;
                z.sample.observe(field(root.get(),"temperature_c")->valuedouble,TemperatureUnit::celsius,ev,
                    uintField(root.get(),"source_sample_age_ms"),admission_.grantElapsed(now),now,z.profile,evidence=="restored");
            }
        } else {
            const auto mode=stringField(root.get(),"mode");
            z.off=mode=="off";
            z.overrideUntil=mode=="temporary" && now<=UINT64_MAX-uintField(root.get(),"duration_ms") ? now+uintField(root.get(),"duration_ms") : 0;
            z.overrideTarget=static_cast<int16_t>(uintField(root.get(),"temperature_centi_c"));
        }
        result(resultTopic,e,"accepted"); state(now,utc,clockValid);
    }
    uint32_t revision() const { return config_->revision; }
    const std::string &digest() const { return digest_; }
    bool faulted() const { return fault_; }
private:
    struct Zone {
        std::string id,sensor,actuator,reportEvidence;
        int16_t base=1700,overrideTarget=1700;
        TemperatureProfile profile;
        TemperatureSample sample;
        UtcSchedule schedule;
        bool scheduled=false,off=false,demand=false;
        ZoneRegulator regulator;
        uint64_t overrideUntil=0;
    };
    struct Configuration { uint32_t revision=0; size_t count=0; std::array<Zone,maximumZones> zones; };
    static int hexByte(char c) { return c<='9'?c-'0':c-'a'+10; }
    bool decodeConfig(const cJSON *o,Configuration &out) const {
        if(!exactFields(o,{"mapping_digest","mode","revision","schema","zones"}) || !canonicalConfig(o) ||
            !hexString(stringField(o,"mapping_digest"),64)||stringField(o,"mode")!="shadow"||
            !integerField(o,"revision",1,UINT32_MAX)||!integerField(o,"schema",1,1)) return false;
        auto zones=field(o,"zones");
        if(!cJSON_IsArray(zones)||cJSON_GetArraySize(zones)>static_cast<int>(maximumZones)) return false;
        std::set<std::string> identities{"adapter","config","snapshot"};
        for(auto zone=zones->child;zone;zone=zone->next) {
            if(!exactFields(zone,{"actuator_id","base_centi_c","max_age_ms","report_evidence","schedule","sensor_id","zone_id"})||
                !integerField(zone,"base_centi_c",500,3500)||!integerField(zone,"max_age_ms",1000,86400000)) return false;
            auto &z=out.zones[out.count];
            z.id=stringField(zone,"zone_id"); z.sensor=stringField(zone,"sensor_id"); z.actuator=stringField(zone,"actuator_id");
            z.reportEvidence=stringField(zone,"report_evidence");
            if(!cJSON_IsString(field(zone,"actuator_id"))||!hexString(z.id,8)||!SessionAdmission::validId(z.sensor)||
                (!z.actuator.empty()&&!SessionAdmission::validId(z.actuator))||
                !identities.insert(z.id).second||!identities.insert(z.sensor).second||
                (!z.actuator.empty()&&!identities.insert(z.actuator).second)||
                (z.reportEvidence!="physical_report"&&z.reportEvidence!="validated_integration_report")) return false;
            z.base=uintField(zone,"base_centi_c"); z.profile.maximumAgeMs=uintField(zone,"max_age_ms");
            z.profile.acceptsValidatedIntegrationReport=z.reportEvidence=="validated_integration_report";
            auto schedule=field(zone,"schedule");
            z.scheduled=!cJSON_IsNull(schedule);
            if(z.scheduled && !configureScheduleDocument(z.schedule,schedule)) return false;
            ++out.count;
        }
        out.revision=uintField(o,"revision"); return true;
    }
    bool shape(const cJSON *o,std::string_view topic,int index,Configuration &candidate,std::string &configBytes) const {
        std::set<std::string> keys{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id","grant_sequence","config_revision","binding_id","sequence"};
        if(topic=="ha/config") {
            keys.insert({"expected_revision","config_digest","config"});
            if(!integerField(o,"expected_revision",0,UINT32_MAX)||!hexString(stringField(o,"config_digest"),64)||!decodeConfig(field(o,"config"),candidate)) return false;
            configBytes=printJson(field(o,"config"));
            if(configBytes.empty()||configBytes.size()>maximumConfigBytes||hash_(configBytes)!=stringField(o,"config_digest")) return false;
        } else if(topic=="ha/observations") {
            keys.insert({"zone_id","source_available","temperature_c","source_sample_age_ms","evidence"});
            auto available=field(o,"source_available"),temp=field(o,"temperature_c");
            auto evidence=stringField(o,"evidence");
            if(index<0||stringField(o,"zone_id")!=config_->zones[index].id||(!cJSON_IsTrue(available)&&!cJSON_IsFalse(available))||
                !cJSON_IsNumber(temp)||!std::isfinite(temp->valuedouble)||temp->valuedouble< -20||temp->valuedouble>60||
                !integerField(o,"source_sample_age_ms",0,86400000)||
                (evidence!="physical_report"&&evidence!="validated_integration_report"&&evidence!="unverified"&&evidence!="restored")) return false;
        } else if(topic=="ha/user_command") {
            keys.insert({"mode","temperature_centi_c","duration_ms"}); auto mode=stringField(o,"mode");
            if((mode!="temporary"&&mode!="off"&&mode!="auto")||!integerField(o,"temperature_centi_c",500,3500)||!integerField(o,"duration_ms",60000,43200000)) return false;
        }
        if(cJSON_GetArraySize(o)!=static_cast<int>(keys.size())) return false;
        for(auto p=o->child;p;p=p->next) if(!keys.count(p->string)) return false;
        return true;
    }
    bool envelope(const cJSON *o,StreamKind kind,Envelope &e) const {
        for(auto key:{"controller_id","boot_id","adapter_id","adapter_session_id","grant_id","binding_id"})
            if(!SessionAdmission::validId(stringField(o,key))) return false;
        if(!integerField(o,"api",1,1)||!integerField(o,"epoch",1,UINT32_MAX)||!integerField(o,"grant_sequence",1,UINT32_MAX)||
            !integerField(o,"config_revision",0,UINT32_MAX)||!integerField(o,"sequence",1,UINT32_MAX)) return false;
        e.kind=kind; e.major=1; e.direction=Direction::ha_to_fw;
        // Views refer to the bounded cJSON document through admit/result only.
        e.controller=field(o,"controller_id")->valuestring; e.boot=field(o,"boot_id")->valuestring;
        e.adapter=field(o,"adapter_id")->valuestring; e.session=field(o,"adapter_session_id")->valuestring;
        e.grant=field(o,"grant_id")->valuestring; e.binding=field(o,"binding_id")->valuestring;
        e.epoch=uintField(o,"epoch"); e.revision=uintField(o,"config_revision");
        e.grantSequence=uintField(o,"grant_sequence"); e.sequence=uintField(o,"sequence"); return true;
    }
    void invalidate() {
        supervisor_.invalidate();
        admission_.invalidateTransport(); session_=mappingReady_=leaseWasAlive_=false;
        sessionId_.clear(); lastOpen_.clear();
        for(size_t i=0;i<config_->count;++i) {
            auto &z=config_->zones[i]; z.sample.unavailable(); z.overrideUntil=0; z.off=false; z.demand=false; z.regulator=ZoneRegulator{};
        }
    }
    void newChallenge(uint64_t now) {
        challenge_=nonce_(); challengeUntil_=now+grantMs;
        if(!SessionAdmission::validId(challenge_)) fault_=true;
    }
    bool newGrant(uint64_t now) {
        grant_=nonce_(); ++grantSequence_; nextGrant_=now+5000;
        return admission_.issueGrant(grant_,grantSequence_,now,grantMs);
    }
    void open(const cJSON *o,uint64_t now) {
        if(!exactFields(o,{"api","controller_id","boot_id","epoch","challenge_id","adapter_id","client_nonce","known_revision","known_digest"})||
            !integerField(o,"api",1,1)||!integerField(o,"epoch",1,UINT32_MAX)||!integerField(o,"known_revision",0,UINT32_MAX)||
            stringField(o,"controller_id")!=controller_||stringField(o,"boot_id")!=boot_||uintField(o,"epoch")!=epoch_||
            stringField(o,"adapter_id")!=owner_||!SessionAdmission::validId(stringField(o,"client_nonce"))||
            !cJSON_IsString(field(o,"known_digest"))) return;
        const auto request=printJson(o);
        if(session_) { if(request==lastOpen_) sessionStatus(); return; }
        if(stringField(o,"challenge_id")!=challenge_||now>=challengeUntil_) return;
        sessionId_=nonce_();
        SessionIdentity identity{controller_,boot_,owner_,sessionId_,epoch_,revision()};
        // New legitimate same-connection sessions get a fresh local primitive.
        // Consumed handshake challenge prevents resetting old watermarks.
        admission_=SessionAdmission(owner_);
        if(!admission_.begin(identity,leaseMs)) return;
        admission_.bind(0,"adapter",StreamKind::heartbeat);
        admission_.bind(1,"config",StreamKind::configuration);
        admission_.bind(2,"snapshot",StreamKind::configuration);
        for(size_t i=0;i<config_->count;++i) {
            admission_.bind(3+i,config_->zones[i].sensor,StreamKind::observation);
            admission_.bind(11+i,config_->zones[i].id,StreamKind::user_command);
        }
        mappingReady_=uintField(o,"known_revision")==revision()&&stringField(o,"known_digest")==digest_;
        session_=true; sessionStart_=now; grantSequence_=0; clientNonce_=stringField(o,"client_nonce"); lastOpen_=request;
        if(!newGrant(now)) { invalidate(); return; }
        newChallenge(now); sessionStatus();
    }
    ControlJson base() const {
        auto o=objectJson();
        cJSON_AddNumberToObject(o.get(),"api",1); cJSON_AddStringToObject(o.get(),"controller_id",controller_.c_str());
        cJSON_AddStringToObject(o.get(),"boot_id",boot_.c_str()); cJSON_AddNumberToObject(o.get(),"epoch",epoch_);
        cJSON_AddNumberToObject(o.get(),"config_revision",revision()); cJSON_AddStringToObject(o.get(),"config_digest",digest_.c_str()); return o;
    }
    void send(std::string_view topic,const cJSON *o) { const auto bytes=printJson(o); if(!bytes.empty()&&bytes.size()<=8192) publish_(topic,bytes); }
    void hello() {
        auto o=base(); cJSON_AddStringToObject(o.get(),"challenge_id",challenge_.c_str());
        cJSON_AddStringToObject(o.get(),"mode","shadow"); cJSON_AddNumberToObject(o.get(),"lease_ms",leaseMs);
        cJSON_AddNumberToObject(o.get(),"grant_ms",grantMs); cJSON_AddBoolToObject(o.get(),"storage_fault",fault_); send("fw/hello",o.get());
    }
    void sessionStatus() {
        auto o=base(); cJSON_AddStringToObject(o.get(),"adapter_id",owner_.c_str());
        cJSON_AddStringToObject(o.get(),"adapter_session_id",sessionId_.c_str()); cJSON_AddStringToObject(o.get(),"client_nonce",clientNonce_.c_str());
        cJSON_AddStringToObject(o.get(),"grant_id",grant_.c_str()); cJSON_AddNumberToObject(o.get(),"grant_sequence",grantSequence_);
        cJSON_AddNumberToObject(o.get(),"grant_ms",grantMs); cJSON_AddBoolToObject(o.get(),"mapping_ready",mappingReady_); send("fw/session",o.get());
    }
    void result(const char *topic,const Envelope &e,const char *status) {
        auto o=base(); cJSON_AddStringToObject(o.get(),"adapter_session_id",std::string(e.session).c_str());
        cJSON_AddStringToObject(o.get(),"binding_id",std::string(e.binding).c_str());
        cJSON_AddNumberToObject(o.get(),"sequence",e.sequence); cJSON_AddStringToObject(o.get(),"status",status); send(topic,o.get());
    }
    void snapshot() {
        auto o=base(); auto cfg=configBytes_.empty()?nullptr:cJSON_Parse(configBytes_.c_str());
        cJSON_AddItemToObject(o.get(),"config",cfg?cfg:cJSON_CreateNull()); send("fw/config_snapshot",o.get());
    }
    void state(uint64_t now,int64_t utc,bool clockValid) {
        auto o=base(); cJSON_AddStringToObject(o.get(),"mode","shadow");
        const bool alive=session_&&mappingReady_&&!fault_&&admission_.alive(now);
        cJSON_AddBoolToObject(o.get(),"adapter_alive",alive);
        cJSON_AddBoolToObject(o.get(),"boiler_output_enabled",false); cJSON_AddBoolToObject(o.get(),"actuator_output_enabled",false);
        bool requestedHeat=false;
        auto list=cJSON_AddArrayToObject(o.get(),"zones");
        for(size_t i=0;i<config_->count;++i) {
            auto &z=config_->zones[i]; auto row=cJSON_CreateObject(); cJSON_AddItemToArray(list,row);
            cJSON_AddStringToObject(row,"zone_id",z.id.c_str());
            const auto temperature=alive?z.sample.value(now):std::nullopt;
            auto target=std::optional<int16_t>(z.base);
            const char *source="base",*reason="shadow_idle";
            if(z.scheduled) { target=z.schedule.target(utc,clockValid).temperatureCentiC; source="schedule"; }
            const auto effective=EffectiveTarget::api1(target,source,z.off,z.overrideTarget,z.overrideUntil,now);
            target=effective.target;source=effective.source;
            if(!alive) reason="adapter_unavailable";
            else if(!temperature) reason="source_unverified_or_stale";
            else if(!target) reason=z.off?"off":"schedule_time_invalid_or_expired";
            const bool usable=alive&&temperature&&target;
            const auto regulation=z.regulator.step(now,temperature,target,usable);
            z.demand=regulation.demand;
            requestedHeat=requestedHeat||z.demand;
            if(z.demand) reason="shadow_demand";
            const auto nullable=[row](const char *key,auto value) { if(value) cJSON_AddNumberToObject(row,key,*value); else cJSON_AddNullToObject(row,key); };
            nullable("temperature_centi_c",temperature); nullable("target_centi_c",target); nullable("sample_age_ms",z.sample.age(now));
            cJSON_AddNumberToObject(row,"sample_state",static_cast<int>(z.sample.state(now)));
            cJSON_AddStringToObject(row,"target_source",source); cJSON_AddBoolToObject(row,"demand",z.demand); cJSON_AddStringToObject(row,"reason",reason);
        }
        // No installation has been qualified through this api1 contract.
        // Actual shadow request is visible; it NEVER becomes hydraulic readiness.
        HydraulicInputs inputs;
        inputs.adapterAlive=alive; inputs.sourceValid=requestedHeat;
        inputs.heatDemand=requestedHeat;
        const auto hydraulic=supervisor_.step(now,inputs);
        auto status=cJSON_AddObjectToObject(o.get(),"supervisor");
        cJSON_AddStringToObject(status,"phase",hydraulicPhaseName(hydraulic.phase));
        cJSON_AddStringToObject(status,"reason",hydraulic.reason);
        cJSON_AddBoolToObject(status,"requested_heat",requestedHeat);
        cJSON_AddBoolToObject(status,"physical_outputs_enabled",false);
        send("fw/state/zones",o.get());
    }
    std::string controller_,boot_,owner_,digest_,configBytes_,challenge_,grant_,sessionId_,clientNonce_,lastOpen_;
    ControlStore &store_; Hash hash_; Nonce nonce_; Publish publish_;
    std::unique_ptr<Configuration> config_=std::make_unique<Configuration>();
    SessionAdmission admission_;
    HydraulicSupervisor supervisor_;
    uint32_t epoch_=0,grantSequence_=0;
    uint64_t challengeUntil_=0,nextHello_=0,nextState_=0,nextGrant_=0,lastNow_=0,sessionStart_=0;
    bool session_=false,mappingReady_=false,connected_=false,fault_=false,leaseWasAlive_=false;
};
}
