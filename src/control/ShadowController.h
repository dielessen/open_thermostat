#pragma once
#include "BoundedJson.h"
#include "ControlStore.h"
#include "EffectiveTarget.h"
#include "MetricsTelemetry.h"
#include "BoilerFieldTelemetry.h"
#include <sstream>
#include "Measurement.h"
#include "ScheduleDocument.h"
#include "SessionAdmission.h"
#include "ActuatorScope.h"
#include "ZoneRegulator.h"
#include "SeasonalControllerSource.h"
#include "NativeControlPlan.h"
#include "RoomDisplayNames.h"
#include "HydraulicSupervisor.h"
#include "HydraulicControllerSource.h"
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


// Single serialized controller owner, including feedback and local fault
// acknowledgement. Providers observe existing facts; they issue no commands.
class ShadowController {
public:
    using Hash=std::function<std::string(std::string_view)>;
    using Nonce=std::function<std::string()>;
    using Publish=std::function<void(std::string_view,std::string_view)>;
    using BoilerFields=std::function<void(std::ostream&,size_t)>;
    using Metrics=std::function<void(std::ostream&)>;
    // Existing NVS partition is20KiB, with GC + old/new atomic blob overhead.
    // Do not turn a JSON transport ceiling into a hidden persistence promise.
    static constexpr size_t maximumZones=8, maximumConfigBytes=4096;
    static constexpr uint32_t grantMs=10000, leaseMs=15000;
    ShadowController(std::string controller,std::string boot,std::string owner,
                     ControlStore &store,Hash hash,Nonce nonce,Publish publish,Metrics metrics={},
                     const SeasonalControllerSource* seasonalSource=nullptr,
                     SeasonalControllerSource::Safety safety={},
                     const NativePlanInstallationSource* nativePlanSource=nullptr,BoilerFields boilerFields={},
                     const HydraulicControllerSource* hydraulicSource=nullptr,HydraulicFeedbackProvider hydraulicFeedback={})
        :controller_(std::move(controller)),boot_(std::move(boot)),owner_(std::move(owner)),
         store_(store),hash_(std::move(hash)),nonce_(std::move(nonce)),publish_(std::move(publish)),metrics_(std::move(metrics)),admission_(owner_),boilerFields_(std::move(boilerFields)) {
        if(!SessionAdmission::validId(controller_)||!SessionAdmission::validId(boot_)||!SessionAdmission::validId(owner_)) { fault_=true; return; }
        if(nativePlanSource) {
            if(seasonalSource||!nativePlanSource->valid()||nativePlanSource->controllerId!=controller_
                ||nativePlanSource->adapterId!=owner_||!safety) {fault_=true;return;}
            selectNativeSource(*nativePlanSource,std::move(safety));
        }
        if(seasonalSource) {
            if(!seasonalSource->valid()||seasonalSource->controllerId!=controller_||!safety) {
                fault_=true;return; // Selected source MUST NOT fall back to ordinary policy.
            }
            seasonalSource_=std::make_unique<SeasonalControllerSource>(*seasonalSource);
            seasonalSafety_=std::move(safety);
        }
        if(hydraulicSource) {
            if(!hydraulicSource->valid()||hydraulicSource->controllerId!=controller_
                ||hydraulicSource->adapterId!=owner_||!seasonalSource_||!hydraulicFeedback
                ||hydraulicSource->profileDigest!=seasonalSource_->profileDigest) {fault_=true;return;}
            hydraulicSource_=std::make_unique<HydraulicControllerSource>(*hydraulicSource);
            hydraulicFeedback_=std::move(hydraulicFeedback);
            supervisor_=HydraulicSupervisor(hydraulicSource_->profile);
        }
        loadSavedConfiguration();
    }
    // Only the already selected local native factory may call this after an
    // independently authenticated source-only settings commit. No remote config,
    // DATA/hello/GUI flag creates a SOURCE. Same object/store/transport/boot.
    bool replaceNativeSource(const NativePlanInstallationSource& next,uint64_t now) {
        const bool reconnect=connected_;
        disconnected(); // Withdraw old grant/observations/overrides BEFORE IO.
        if(!nativeSourceReplaceable()||now<lastNow_) {fault_=true;return false;}
        struct Scope {bool& flag;explicit Scope(bool& f):flag(f){flag=true;}~Scope(){flag=false;}} scope(nativeReceiving_);
        try {
            if(!matchesNativeSourceTransition(next)) {
                fault_=true;return false;
            }
            // Fresh logical profile never restores an earlier safety producer.
            selectNativeSource(next,[] {return SeasonalSafetySnapshot{};});
            config_=std::make_unique<Configuration>();
            configBytes_.clear();digest_.clear();legacyQuarantine_=false;
            loadSavedConfiguration();
            if(fault_)return false;
            if(reconnect)connected(now); // Strictly increasing epoch, SAME boot.
            return !fault_;
        } catch(...) {fault_=true;disconnected();return false;}
    }
    void inhibitNativeSourceMutation() {fault_=true;disconnected();}

    // Local reviewed SOURCE owner only; deliberately no HTTP/MQTT/reset flag.
    // Acknowledging a fault cannot renew postrun or create a heat intent. The
    // next cycle still needs a new opening command and subsequent feedback.
    bool acknowledgeHydraulicFault(uint64_t now,const HydraulicFeedbackSnapshot& evidence) {
        if(!hydraulicSource_||hydraulicSourceFault_||policySourceFault_||hydraulicReading_||safetyReading_
            ||supervisor_.lastIntent().phase!=HydraulicPhase::fault||now<lastNow_)return false;
        const HydraulicOwnerContext context{policyGeneration_,config_->revision,
            supervisor_.lastIntent().openingCommand,sessionStart_,boot_};
        const auto current=[&] {return session_&&mappingReady_&&!fault_&&admission_.alive(now)
            &&context.generation==policyGeneration_&&context.revision==config_->revision&&context.startedAt==sessionStart_
            &&seasonalSource_&&seasonalSource_->profileDigest==hydraulicSource_->profileDigest;};
        if(!current())return false;
        const auto checked=hydraulicGate_.evaluate(now,hydraulicSource_->maximumFactAgeMs,context,evidence);
        const auto& in=checked.inputs;
        if(!in.limitsKnownSafe||in.limitTripped||!in.faultStateKnown||in.boilerFault
            ||!in.dhwStateKnown||in.dhwActive||in.stop||in.actuatorFailure)return false;
        SeasonalSafetySnapshot safety;safetyReading_=true;
        try {safety=seasonalSafety_();} catch(...) {policySourceFault_=true;}
        safetyReading_=false;
        if(policySourceFault_||hydraulicSourceFault_||!current()||now<lastNow_
            ||!acceptSeasonalSafety(now,safety)
            ||!safety.limitsKnownSafe||!safety.dhwStateKnown||safety.dhwActive||safety.allOff||safety.preempted)return false;
        return supervisor_.clearFault(true);
    }
    void connected(uint64_t now) {
        invalidate();
        if(epoch_==UINT32_MAX) { fault_=true; return; }
        ++epoch_; connected_=true; newChallenge(now); nextHello_=nextState_=now;
    }
    void disconnected() { connected_=false; invalidate(); }
    // Local read-only context for a configured normalized actuator channel.
    // Not a broker/API endpoint, source qualification or output-enable path.
    std::optional<ActuatorSessionContext> actuatorSessionContext(std::string_view binding,uint64_t now) const {
        if(!SessionAdmission::validId(binding)||!connected_||!session_||!mappingReady_||fault_
                ||legacyQuarantine_||nativeReceiving_||!config_->revision||now<lastNow_)return std::nullopt;
        bool bound=false;
        for(size_t i=0;i<config_->count;++i)if(config_->zones[i].actuator==binding){bound=true;break;}
        if(!bound)return std::nullopt;
        const auto lease=admission_.leaseDeadline(now),grant=admission_.grantDeadline(now);
        if(!lease||!grant)return std::nullopt;
        ActuatorSessionContext context{{controller_,boot_,owner_,sessionId_,digest_,std::string(binding),
            epoch_,config_->revision},lease,grant};
        return context.scope.valid()?std::optional<ActuatorSessionContext>(std::move(context)):std::nullopt;
    }
    // Internal read-only intent, not physical feedback or actuation authority.
    const HydraulicSupervisor::Result& hydraulicIntent() const {return supervisor_.lastIntent();}
    void tick(uint64_t now,int64_t utc,bool clockValid) {
        if(now<lastNow_) { fault_=true; invalidate(); }
        lastNow_=std::max(lastNow_,now);
        if(!connected_) {supervisor_.advanceWithoutOwner(now);return;}
        if(session_ && !admission_.alive(now) && (leaseWasAlive_ || now>=sessionStart_+leaseMs)) { invalidate(); newChallenge(now); }
        if(now>=challengeUntil_) newChallenge(now);
        if(session_ && now>=nextGrant_) {
            if(grantSequence_==UINT32_MAX || !newGrant(now)) { invalidate(); newChallenge(now); }
            else sessionStatus();
        }
        if(now>=nextHello_) { hello(); nextHello_=now+3000; }
        if(now>=nextState_) { state(now,utc,clockValid); nextState_=now+3000; }
        metricsSnapshot(now);
        boilerFieldSnapshot(now);
    }
    void receive(std::string_view topic,std::string_view bytes,uint64_t now,int64_t utc,bool clockValid) {
        if(!nativePlanSource_) {receiveImpl(topic,bytes,now,utc,clockValid);return;}
        if(nativeReceiving_) {fault_=true;invalidate();return;}
        struct Scope {bool& flag;explicit Scope(bool& f):flag(f){flag=true;}~Scope(){flag=false;}} scope(nativeReceiving_);
        try{receiveImpl(topic,bytes,now,utc,clockValid);}
        catch(...){fault_=true;invalidate();}
    }
private:
    void receiveImpl(std::string_view topic,std::string_view bytes,uint64_t now,int64_t utc,bool clockValid) {
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
        bool validComfort=true;
        if(topic=="ha/user_command" && config_->zones[index].comfortEnabled) {
            auto copy=config_->zones[index].comfort;
            validComfort=applyComfort(copy,root.get(),now,utc,clockValid);
        }
        if(kind!=StreamKind::heartbeat && kind!=StreamKind::configuration && !mappingReady_) {
            result(resultTopic,e,"mapping_conflict"); return;
        }
        auto payloadHash=hash_(bytes);
        if(!hexString(payloadHash,64)||(nativePlanSource_&&fault_)) { fault_=true; invalidate(); return; }
        for(size_t i=0;i<32;++i) e.payloadDigest[i]=static_cast<uint8_t>(hexByte(payloadHash[2*i])*16+hexByte(payloadHash[2*i+1]));
        if(!validComfort) {
            // An already applied vacation may expire before its exact-byte ACK
            // retry. Preserve duplicate acknowledgement, never reapply it or
            // consume a NEW invalid command sequence. Allocate only on failure.
            auto trial=std::make_unique<SessionAdmission>(admission_);
            if(trial->admit(stream,e,now).code!=AdmissionCode::duplicate) return;
        }
        const auto a=admission_.admit(stream,e,now);
        if(kind==StreamKind::user_command) {
            lastUserCommand_=UserCommandAdmission{};
            std::copy_n(e.binding.begin(),std::min(e.binding.size(),size_t{32}),lastUserCommand_.binding.begin());
            lastUserCommand_.sequence=e.sequence;lastUserCommand_.revision=e.revision;
            lastUserCommand_.at=now;lastUserCommand_.code=a.code;
        }
        if(a.code==AdmissionCode::duplicate) { result(resultTopic,e,"duplicate"); if(topic=="ha/snapshot_request") snapshot(e.sequence); return; }
        if(a.code!=AdmissionCode::accepted) { result(resultTopic,e,"rejected",admissionCodeName(a.code)); return; }
        if(kind==StreamKind::heartbeat) {
            // Only a NEW accepted heartbeat can anchor a future grant. Exact
            // retries/changed duplicates never replace or re-arm this proof.
            pendingGrantNonce_=stringField(root.get(),"grant_request_nonce");
            if(const auto names=field(root.get(),"room_names")) {
                // Whole list validated before admission. Only a NEW accepted
                // heartbeat may change labels; duplicates never replace them.
                size_t i=0;
                for(auto name=names->child;name;name=name->next,++i) {
                    const auto label=stringField(name,"name_utf8_hex");
                    roomNamesHex_[i].fill(0);std::copy(label.begin(),label.end(),roomNamesHex_[i].begin());
                }
            }
            leaseWasAlive_=true; result(resultTopic,e,"accepted"); return;
        }
        if(topic=="ha/config") {
            if(uintField(root.get(),"expected_revision")!=revision() || revision()==UINT32_MAX || candidate->revision!=revision()+1) {
                result(resultTopic,e,"conflict"); return;
            }
            // Storage can have committed despite a timeout/error. Never continue
            // operating old memory after an ambiguous durable write/read-back.
            std::string readback;
            if(!store_.save(candidateBytes)||!store_.load(readback)||readback!=candidateBytes
                ||(nativePlanSource_&&fault_)) {
                result(resultTopic,e,"storage_fault"); fault_=true; invalidate(); return;
            }
            config_=std::move(candidate);legacyQuarantine_=false; configBytes_=candidateBytes; digest_=stringField(root.get(),"config_digest");
            result(resultTopic,e,"applied"); invalidate(); newChallenge(now); hello(); return;
        }
        if(topic=="ha/snapshot_request") { result(resultTopic,e,"accepted"); snapshot(e.sequence); state(now,utc,clockValid); return; }
        auto &z=config_->zones[index];
        if(kind==StreamKind::observation) {
            if(z.comfortEnabled) {
                auto &in=z.comfortInputs;
                const auto context=[&](const char *key,const char *ageKey,bool supported,uint32_t maximumAge,bool &known,bool &value,uint64_t &at,uint32_t &receivedAge) {
                    const uint64_t age=uintField(root.get(),ageKey)+admission_.grantElapsed(now);
                    known=supported&&!cJSON_IsNull(field(root.get(),key))&&age<maximumAge;
                    value=cJSON_IsTrue(field(root.get(),key));at=now;receivedAge=known?age:maximumAge;
                };
                context("window_open","window_age_ms",z.comfortProfile.windowSupported,z.comfortProfile.maximumWindowAgeMs,in.windowKnown,in.windowOpen,in.windowAt,in.windowAgeAtReceipt);
                context("presence_away","presence_age_ms",z.comfortProfile.presenceSupported,z.comfortProfile.maximumPresenceAgeMs,in.presenceKnown,in.away,in.presenceAt,in.presenceAgeAtReceipt);
            }
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
            if(z.comfortEnabled) applyComfort(z.comfort,root.get(),now,utc,clockValid);
            z.off=mode=="off";
            z.overrideUntil=mode=="temporary" && now<=UINT64_MAX-uintField(root.get(),"duration_ms") ? now+uintField(root.get(),"duration_ms") : 0;
            z.overrideTarget=static_cast<int16_t>(uintField(root.get(),"temperature_centi_c"));
        }
        result(resultTopic,e,"accepted"); state(now,utc,clockValid);
    }
public:
    uint32_t revision() const { return config_->revision; }
    const std::string &digest() const { return digest_; }
    bool faulted() const { return fault_; }
    bool nativeSourceSelected() const {
        return nativePlanSource_&&!fault_&&!policySourceFault_&&!nativeReceiving_&&!safetyReading_;
    }
    bool nativeSourceReplaceable() const {
        return nativeSourceSelected()&&!nativePlanSource_->legacyReadbackReviewed&&epoch_!=UINT32_MAX;
    }
    bool nativeSourceCanReplace(const NativePlanInstallationSource& next) const {
        if(!nativeSourceReplaceable())return false;
        try {return matchesNativeSourceTransition(next);}
        catch(const std::bad_alloc&) {return false;}
    }
private:
    bool matchesNativeSourceTransition(const NativePlanInstallationSource& next) const {
        const auto effective=legacyQuarantine_?nativePlanSource_->predecessor.get():nativePlanSource_.get();
        return effective&&next.valid()&&next.predecessor&&next.controllerId==controller_
            &&next.adapterId==owner_&&next.predecessor->profileDigest==effective->profileDigest;
    }
    // Shared by normal policy evaluation AND fault acknowledgement. Re-reading
    // the producer never makes rejected/cached evidence fresh or immutable again.
    bool acceptSeasonalSafety(uint64_t now,const SeasonalSafetySnapshot& safety) {
        if(!seasonalSource_)return false;
        const auto acquiredAt=safety.sampledAt;
        const auto value=uint8_t(safety.limitsKnownSafe)|(uint8_t(safety.dhwStateKnown)<<1)
            |(uint8_t(safety.dhwActive)<<2)|(uint8_t(safety.summer)<<3)
            |(uint8_t(safety.allOff)<<4)|(uint8_t(safety.preempted)<<5);
        // Uptime zero can be a real acquisition. Known-state flags distinguish
        // usable safety evidence; zero must not double as an empty watermark.
        if(acquiredAt>now||(haveSafetyFact_&&(acquiredAt<lastSafetyAt_
                ||(acquiredAt==lastSafetyAt_&&value!=lastSafetyValue_)))
            ||now-acquiredAt>=seasonalSource_->maximumSafetyAgeMs) {
            retiredSafetyThrough_=std::max(retiredSafetyThrough_,std::max(acquiredAt,lastSafetyAt_));
            haveRetiredSafety_=true;
            return false;
        }
        if(haveRetiredSafety_&&acquiredAt<=retiredSafetyThrough_)return false;
        haveSafetyFact_=true;lastSafetyAt_=acquiredAt;lastSafetyValue_=uint8_t(value);
        return true;
    }
    void selectNativeSource(const NativePlanInstallationSource& source,SeasonalControllerSource::Safety safety) {
        const auto nativePlanSource=&source;
            nativePlanSource_=std::make_unique<NativePlanInstallationSource>(*nativePlanSource);
            // Reuse the existing typed regulator/safety policy; this private
            // compatibility field is NEVER an advertised/per-config SOURCE pin.
            seasonalSource_=std::make_unique<SeasonalControllerSource>();
            seasonalSource_->controllerId=controller_;seasonalSource_->profileDigest=nativePlanSource_->profileDigest;
            seasonalSource_->configDigest=std::string(64,'0');seasonalSource_->count=nativePlanSource_->count;
            seasonalSource_->maximumSafetyAgeMs=nativePlanSource_->maximumSafetyAgeMs;
            for(size_t i=0;i<nativePlanSource_->count;++i)seasonalSource_->zones[i]=nativePlanSource_->zones[i].policy;
            seasonalSafety_=std::move(safety);
    }
    void loadSavedConfiguration() {
        std::string saved;
        if(!store_.load(saved)) { fault_=true; return; }
        if(saved.empty()) return;
        if(saved.size()>maximumConfigBytes) {fault_=true;return;}
        auto root=parseControlJson(saved);
        if(!root) {fault_=true;return;}
        if(nativePlanSource_&&nativePlanSource_->predecessor
            &&stringField(root.get(),"profile_digest")!=nativePlanSource_->profileDigest) {
            auto old=std::make_unique<Configuration>();
            if(!decodeConfig(root.get(),*old,false,nativePlanSource_->predecessor.get())||fault_) {fault_=true;return;}
            config_->revision=old->revision; // Exact metadata, ZERO active zones.
            legacyQuarantine_=true;
        } else if(nativePlanSource_&&nativePlanSource_->legacyReadbackReviewed&&integerField(root.get(),"schema",1,1)) {
            // Same bounded old decoder, no old runtime/second controller.
            auto old=std::make_unique<Configuration>();
            if(!decodeConfig(root.get(),*old,true)||!old->count||old->count>nativePlanSource_->count) {fault_=true;return;}
            size_t transitions=0;
            for(size_t i=0;i<old->count;++i) {
                const auto& z=old->zones[i];const auto pin=nativePlanSource_->zone(z.id);
                const auto rawZone=cJSON_GetArrayItem(field(root.get(),"zones"),static_cast<int>(i));
                const auto schedule=field(rawZone,"schedule");
                if(!pin||z.comfortEnabled||z.base<pin->policy.minimumTargetCentiC
                    ||z.base>pin->policy.maximumTargetCentiC||z.profile.maximumAgeMs>pin->maximumSensorAgeMs
                    ||z.reportEvidence!=pin->reportEvidence||!sourceScheduleBounds(schedule,pin->policy)) {fault_=true;return;}
                if(!cJSON_IsNull(schedule))transitions+=static_cast<size_t>(cJSON_GetArraySize(field(schedule,"transitions")));
            }
            if(transitions>NativePlanInstallationSource::maximumTransitions) {fault_=true;return;}
            config_->revision=old->revision; // Metadata only. ZERO active zones.
            legacyQuarantine_=true;
        } else if(!decodeConfig(root.get(),*config_)) { fault_=true; return; }
        configBytes_=printJson(root.get());
        if(configBytes_.empty()) {fault_=true;return;} // failed serialization is not a successful readback.
        digest_=hash_(configBytes_);
        if(!hexString(digest_,64)||(seasonalSource_&&!nativePlanSource_&&digest_!=seasonalSource_->configDigest)) fault_=true;
    }
    struct Zone {
        std::string id,sensor,actuator,reportEvidence;
        int16_t base=1700,overrideTarget=1700;
        TemperatureProfile profile;
        TemperatureSample sample;
        UtcSchedule schedule;
        bool scheduled=false,off=false,demand=false,comfortEnabled=false;
        ComfortProfile comfortProfile;
        EffectiveTarget comfort;
        ComfortInputs comfortInputs;
        ZoneRegulator regulator;
        uint64_t overrideUntil=0;
    };
    struct Configuration { uint32_t revision=0; size_t count=0; std::array<Zone,maximumZones> zones; };
    static std::optional<ComfortMode> comfortMode(const std::string &name) {
        if(name=="auto")return ComfortMode::automatic;
        if(name=="off")return ComfortMode::off;
        if(name=="temporary")return ComfortMode::temporary;
        if(name=="boost")return ComfortMode::boost;
        if(name=="away")return ComfortMode::away;
        if(name=="vacation")return ComfortMode::vacation;
        if(name=="frost")return ComfortMode::frost;
        return {};
    }
    static bool applyComfort(EffectiveTarget &comfort,const cJSON *o,uint64_t now,int64_t utc,bool validClock) {
        const auto mode=comfortMode(stringField(o,"mode"));if(!mode)return false;
        std::optional<int16_t> target;
        if(cJSON_IsNumber(field(o,"temperature_centi_c")))target=uintField(o,"temperature_centi_c");
        return comfort.command(*mode,target,now,uintField(o,"duration_ms"),uintField(o,"vacation_until_utc"),utc,validClock);
    }
    static int hexByte(char c) { return c<='9'?c-'0':c-'a'+10; }
    bool decodeConfig(const cJSON *o,Configuration &out,bool legacyReadback=false,
                      const NativePlanInstallationSource* readbackSource=nullptr) const {
        const auto native=readbackSource?readbackSource:nativePlanSource_.get();
        if(native&&!legacyReadback) {
            if(!canonicalConfig(o)||!validateNativeControlPlan(o,*native,hash_)||fault_)return false;
        } else if(!exactFields(o,{"mapping_digest","mode","revision","schema","zones"}) || !canonicalConfig(o) ||
            !hexString(stringField(o,"mapping_digest"),64)||stringField(o,"mode")!="shadow"||
            !integerField(o,"revision",1,UINT32_MAX)||!integerField(o,"schema",1,1)) return false;
        auto zones=field(o,"zones");
        if(!cJSON_IsArray(zones)||cJSON_GetArraySize(zones)>static_cast<int>(maximumZones)
            ||(seasonalSource_&&!legacyReadback&&cJSON_GetArraySize(zones)!=static_cast<int>(native?native->count:seasonalSource_->count))) return false;
        std::set<std::string> identities{"adapter","config","snapshot"};
        for(auto zone=zones->child;zone;zone=zone->next) {
            const bool comfort=field(zone,"comfort");
            const bool shape=(nativePlanSource_&&!legacyReadback)?
                (comfort?exactFields(zone,{"actuator_id","actuator_profile","base_centi_c","comfort","group_id","max_age_ms","report_evidence","schedule","sensor_id","zone_id"}):
                    exactFields(zone,{"actuator_id","actuator_profile","base_centi_c","group_id","max_age_ms","report_evidence","schedule","sensor_id","zone_id"})):
                (comfort?exactFields(zone,{"actuator_id","base_centi_c","comfort","max_age_ms","report_evidence","schedule","sensor_id","zone_id"}):
                    exactFields(zone,{"actuator_id","base_centi_c","max_age_ms","report_evidence","schedule","sensor_id","zone_id"}));
            if(!shape||
                !integerField(zone,"base_centi_c",500,3500)||!integerField(zone,"max_age_ms",1000,86400000)) return false;
            auto &z=out.zones[out.count];
            z.id=stringField(zone,"zone_id"); z.sensor=stringField(zone,"sensor_id"); z.actuator=stringField(zone,"actuator_id");
            z.reportEvidence=stringField(zone,"report_evidence");
            if(!cJSON_IsString(field(zone,"actuator_id"))||!hexString(z.id,8)||!SessionAdmission::validId(z.sensor)||
                (!z.actuator.empty()&&!SessionAdmission::validId(z.actuator))||
                !identities.insert(z.id).second||!identities.insert(z.sensor).second||
                (!z.actuator.empty()&&!identities.insert(z.actuator).second)||
                (z.reportEvidence!="physical_report"&&z.reportEvidence!="validated_integration_report")) return false;
            if(comfort) {
                const auto c=field(zone,"comfort");
                const bool contacts=cJSON_HasObjectItem(c,"window_max_age_ms");
                const bool validKeys=contacts
                    ? exactFields(c,{"away_centi_c","frost_centi_c","maximum_centi_c","minimum_centi_c","presence","temporary_ms","window","window_max_age_ms"})
                    : exactFields(c,{"away_centi_c","frost_centi_c","maximum_centi_c","minimum_centi_c","presence","temporary_ms","window"});
                if(!validKeys||
                    !integerField(c,"minimum_centi_c",500,3500)||!integerField(c,"maximum_centi_c",500,3500)||
                    !integerField(c,"away_centi_c",500,3500)||!integerField(c,"frost_centi_c",500,3500)||
                    !integerField(c,"temporary_ms",60000,43200000)||
                    (!cJSON_IsTrue(field(c,"window"))&&!cJSON_IsFalse(field(c,"window")))||
                    (!cJSON_IsTrue(field(c,"presence"))&&!cJSON_IsFalse(field(c,"presence")))) return false;
                auto &p=z.comfortProfile;p.reviewed=true;p.minimumCentiC=uintField(c,"minimum_centi_c");
                p.maximumCentiC=uintField(c,"maximum_centi_c");p.awayCentiC=uintField(c,"away_centi_c");
                p.frostCentiC=uintField(c,"frost_centi_c");p.maximumTemporaryMs=43200000;p.maximumBoostMs=14400000;
                p.windowSupported=cJSON_IsTrue(field(c,"window"));p.presenceSupported=cJSON_IsTrue(field(c,"presence"));
                p.maximumWindowAgeMs=p.maximumPresenceAgeMs=120000;
                if(contacts) {
                    if(!p.windowSupported||!integerField(c,"window_max_age_ms",1000,86400000))return false;
                    p.maximumWindowAgeMs=uintField(c,"window_max_age_ms");
                }
                if(!p.valid()||p.frostCentiC<p.minimumCentiC||p.frostCentiC>p.maximumCentiC||uintField(zone,"base_centi_c")<static_cast<unsigned>(p.minimumCentiC)||
                    uintField(zone,"base_centi_c")>static_cast<unsigned>(p.maximumCentiC)) return false;
                z.comfortEnabled=true;z.comfort=EffectiveTarget(p);
            }
            z.base=uintField(zone,"base_centi_c"); z.profile.maximumAgeMs=uintField(zone,"max_age_ms");
            z.profile.acceptsValidatedIntegrationReport=z.reportEvidence=="validated_integration_report";
            auto schedule=field(zone,"schedule");
            z.scheduled=!cJSON_IsNull(schedule);
            if(z.scheduled && !configureScheduleDocument(z.schedule,schedule,native&&!legacyReadback&&native->weekReviewed)) return false;
            if(seasonalSource_&&!legacyReadback) {
                const auto oldPin=readbackSource?readbackSource->zone(z.id):nullptr;
                const auto pin=readbackSource?(oldPin?&oldPin->policy:nullptr):seasonalSource_->zone(z.id);
                if(!pin||pin->sensorId!=z.sensor||pin->actuatorId!=z.actuator
                    ||z.base<pin->minimumTargetCentiC||z.base>pin->maximumTargetCentiC
                    ||!sourceScheduleBounds(schedule,*pin,native&&native->weekReviewed)
                    ||(z.comfortEnabled&&(z.comfortProfile.minimumCentiC<pin->minimumTargetCentiC
                        ||z.comfortProfile.maximumCentiC>pin->maximumTargetCentiC
                        ||pin->seasonal.frostTargetCentiC<z.comfortProfile.minimumCentiC
                        ||pin->seasonal.frostTargetCentiC>z.comfortProfile.maximumCentiC
                        ||pin->seasonal.frostTargetCentiC!=z.comfortProfile.frostCentiC)))return false;
                z.regulator=ZoneRegulator(pin->control,pin->seasonal);
            }
            ++out.count;
        }
        out.revision=uintField(o,"revision"); return true;
    }
    static bool sourceScheduleBounds(const cJSON* schedule,const SeasonalZoneSource& pin,bool allowPacked=false) {
        if(cJSON_IsNull(schedule))return true;
        const auto base=field(schedule,"base_centi_c");
        if(!cJSON_IsNumber(base)||base->valuedouble<pin.minimumTargetCentiC
            ||base->valuedouble>pin.maximumTargetCentiC)return false;
        if(stringField(schedule,"policy")==packedSchedulePolicy) {
            return allowPacked&&forEachPackedTransition(schedule,[&](int64_t,int16_t target,size_t) {
                return target>=pin.minimumTargetCentiC&&target<=pin.maximumTargetCentiC;
            });
        }
        auto values=field(schedule,"transitions");
        if(!cJSON_IsArray(values))return false;
        for(auto p=values->child;p;p=p->next) {
            const auto target=cJSON_GetArrayItem(p,1);
            if(!cJSON_IsNumber(target)||target->valuedouble<pin.minimumTargetCentiC
                ||target->valuedouble>pin.maximumTargetCentiC)return false;
        }
        return true;
    }
    bool shape(const cJSON *o,std::string_view topic,int index,Configuration &candidate,std::string &configBytes) const {
        std::set<std::string> keys{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id","grant_sequence","config_revision","binding_id","sequence"};
        if(topic=="ha/heartbeat" && field(o,"grant_request_nonce")) {
            keys.insert("grant_request_nonce");
            if(!SessionAdmission::validId(stringField(o,"grant_request_nonce"))) return false;
        }
        if(topic=="ha/heartbeat" && field(o,"room_names")) {
            keys.insert("room_names");
            const auto names=field(o,"room_names");
            if(!nativePlanSource_||!mappingReady_||config_->count>roomNamesHex_.size()||
               !cJSON_IsArray(names)||cJSON_GetArraySize(names)!=int(config_->count))return false;
            size_t i=0;
            for(auto name=names->child;name;name=name->next,++i) {
                if(!exactFields(name,{"zone_id","name_utf8_hex"})||
                   stringField(name,"zone_id")!=config_->zones[i].id||
                   !validRoomDisplayNameHex(stringField(name,"name_utf8_hex")))return false;
            }
        }
        if(topic=="ha/config") {
            keys.insert({"expected_revision","config_digest","config"});
            if(!integerField(o,"expected_revision",0,UINT32_MAX)||!hexString(stringField(o,"config_digest"),64)||!decodeConfig(field(o,"config"),candidate)) return false;
            configBytes=printJson(field(o,"config"));
            if(configBytes.empty()||configBytes.size()>maximumConfigBytes||hash_(configBytes)!=stringField(o,"config_digest")
                ||(seasonalSource_&&!nativePlanSource_&&stringField(o,"config_digest")!=seasonalSource_->configDigest)
                ||(nativePlanSource_&&fault_)) return false;
        } else if(topic=="ha/observations") {
            keys.insert({"zone_id","source_available","temperature_c","source_sample_age_ms","evidence"});
            if(index>=0&&config_->zones[index].comfortEnabled) {
                keys.insert({"window_open","window_age_ms","presence_away","presence_age_ms"});
                for(auto key:{"window_open","presence_away"})
                    if(!cJSON_IsBool(field(o,key))&&!cJSON_IsNull(field(o,key))) return false;
                for(auto key:{"window_age_ms","presence_age_ms"})
                    if(!integerField(o,key,0,86400000)) return false;
            }
            auto available=field(o,"source_available"),temp=field(o,"temperature_c");
            auto evidence=stringField(o,"evidence");
            if(index<0||stringField(o,"zone_id")!=config_->zones[index].id||(!cJSON_IsTrue(available)&&!cJSON_IsFalse(available))||
                !cJSON_IsNumber(temp)||!std::isfinite(temp->valuedouble)||temp->valuedouble< -20||temp->valuedouble>60||
                !integerField(o,"source_sample_age_ms",0,86400000)||
                (evidence!="physical_report"&&evidence!="validated_integration_report"&&evidence!="unverified"&&evidence!="restored")) return false;
        } else if(topic=="ha/user_command") {
            if(seasonalSource_&&index>=0&&stringField(o,"mode")!="off"&&stringField(o,"mode")!="auto"
                &&cJSON_IsNumber(field(o,"temperature_centi_c"))) {
                const auto pin=seasonalSource_->zone(config_->zones[index].id);
                const auto value=field(o,"temperature_centi_c")->valuedouble;
                if(!pin||!std::isfinite(value)||value<pin->minimumTargetCentiC||value>pin->maximumTargetCentiC)return false;
            }
            keys.insert({"mode","temperature_centi_c","duration_ms"}); auto mode=stringField(o,"mode");
            if(config_->zones[index].comfortEnabled) {
                keys.insert("vacation_until_utc");
                if(!integerField(o,"vacation_until_utc",0,UtcSchedule::maximumUtcSecond)||
                    !integerField(o,"duration_ms",0,43200000)||
                    !(cJSON_IsNull(field(o,"temperature_centi_c"))||integerField(o,"temperature_centi_c",500,3500))||
                    !comfortMode(mode)) return false;
            } else if((mode!="temporary"&&mode!="off"&&mode!="auto")||!integerField(o,"temperature_centi_c",500,3500)||!integerField(o,"duration_ms",60000,43200000)) return false;
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
        lastUserCommand_=UserCommandAdmission{};
        for(auto &name:roomNamesHex_)name.fill(0);
        supervisor_.invalidate();
        admission_.invalidateTransport(); session_=mappingReady_=leaseWasAlive_=false;
        sessionId_.clear(); lastOpen_.clear(); pendingGrantNonce_.clear(); issuedGrantNonce_.clear();
        nextMetrics_=0;metricsSequence_=0;nextBoilerFields_=0;boilerSequence_=0;boilerGroup_=0;
        for(size_t i=0;i<config_->count;++i) {
            auto &z=config_->zones[i]; z.sample.unavailable(); z.comfort.invalidate();z.comfortInputs=ComfortInputs{}; z.overrideUntil=0; z.off=false; z.demand=false;
            // SOURCE-selected regulator keeps its owner/timing fences and minimum
            // cycle state. A fresh authenticated session gets a new LOCAL generation.
            if(!seasonalSource_) z.regulator=ZoneRegulator{};
        }
    }
    void newChallenge(uint64_t now) {
        challenge_=nonce_(); challengeUntil_=now+grantMs;
        if(!SessionAdmission::validId(challenge_)) fault_=true;
    }
    bool newGrant(uint64_t now) {
        grant_=nonce_(); ++grantSequence_; nextGrant_=now+5000;
        // Issue strictly AFTER receipt of the accepted heartbeat. No immediate
        // extra rotation that could invalidate another in-flight command.
        issuedGrantNonce_=std::move(pendingGrantNonce_); pendingGrantNonce_.clear();
        return admission_.issueGrant(grant_,grantSequence_,now,grantMs);
    }
    void open(const cJSON *o,uint64_t now) {
        const bool namedPolicy=seasonalSource_&&!seasonalSource_->profileDigest.empty();
        const bool fields=nativePlanSource_?
            exactFields(o,{"api","controller_id","boot_id","epoch","challenge_id","adapter_id","client_nonce","known_revision","known_digest","source_profile_digest","plan_contract"}):
            namedPolicy?exactFields(o,{"api","controller_id","boot_id","epoch","challenge_id","adapter_id","client_nonce","known_revision","known_digest","source_profile_digest","source_config_pin"}):
            exactFields(o,{"api","controller_id","boot_id","epoch","challenge_id","adapter_id","client_nonce","known_revision","known_digest"});
        if(!fields||(nativePlanSource_&&(stringField(o,"source_profile_digest")!=nativePlanSource_->profileDigest
                ||stringField(o,"plan_contract")!=nativePlanSource_->planContract()))
            ||(!nativePlanSource_&&namedPolicy&&(stringField(o,"source_profile_digest")!=seasonalSource_->profileDigest
                ||stringField(o,"source_config_pin")!=seasonalSource_->configDigest))||
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
        // Bounded one-off fresh handshake scratch. Do not place the 48-stream
        // admission object on the 6096-byte Arduino loop stack. Challenge and
        // same-owner checks above are unchanged; this does NOT admit any data.
        auto freshAdmission=std::make_unique<SessionAdmission>(owner_);
        if(!freshAdmission->begin(identity,leaseMs)) return;
        admission_=std::move(*freshAdmission);
        freshAdmission.reset();
        admission_.bind(0,"adapter",StreamKind::heartbeat);
        admission_.bind(1,"config",StreamKind::configuration);
        admission_.bind(2,"snapshot",StreamKind::configuration);
        for(size_t i=0;i<config_->count;++i) {
            admission_.bind(3+i,config_->zones[i].sensor,StreamKind::observation);
            admission_.bind(11+i,config_->zones[i].id,StreamKind::user_command);
        }
        mappingReady_=!legacyQuarantine_&&uintField(o,"known_revision")==revision()&&stringField(o,"known_digest")==digest_;
        if(seasonalSource_&&policyGeneration_==UINT32_MAX) {fault_=true;invalidate();return;}
        if(seasonalSource_)++policyGeneration_;
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
    void sourcePolicy(cJSON* o) const {
        if(nativePlanSource_) {
            auto profile=cJSON_AddObjectToObject(o,"source_policy");if(!profile)return;
            cJSON_AddNumberToObject(profile,"schema",nativePlanSource_->predecessor?4:nativePlanSource_->legacyReadbackReviewed?3:2);
            cJSON_AddStringToObject(profile,"kind",nativePlanSource_->predecessor?"installation.shadow.v3":nativePlanSource_->legacyReadbackReviewed?"installation.shadow.v2":NativePlanInstallationSource::kind);
            if(nativePlanSource_->predecessor)cJSON_AddStringToObject(profile,"predecessor_profile_digest",nativePlanSource_->predecessor->profileDigest.c_str());
            if(nativePlanSource_->legacyReadbackReviewed)cJSON_AddStringToObject(profile,"legacy_readback","schema1_quarantine_only");
            cJSON_AddStringToObject(profile,"adapter_id",owner_.c_str());
            cJSON_AddStringToObject(profile,"profile_digest",nativePlanSource_->profileDigest.c_str());
            cJSON_AddStringToObject(profile,"plan_contract",nativePlanSource_->planContract());
            cJSON_AddBoolToObject(profile,"physical_outputs_enabled",false);
            cJSON_AddBoolToObject(profile,"frost_protection_available",false);
            auto limits=cJSON_AddObjectToObject(profile,"limits");
            if(limits) {
                cJSON_AddNumberToObject(limits,"zones",2);cJSON_AddNumberToObject(limits,"groups",2);
                cJSON_AddNumberToObject(limits,"channels",4);cJSON_AddNumberToObject(limits,"config_bytes",maximumConfigBytes);
                cJSON_AddNumberToObject(limits,"wire_bytes",8192);cJSON_AddNumberToObject(limits,"total_transitions",nativePlanSource_->weekReviewed?256:8);
            }
            return;
        }
        if(!seasonalSource_||seasonalSource_->profileDigest.empty())return;
        auto profile=cJSON_AddObjectToObject(o,"source_policy");
        if(!profile)return;
        cJSON_AddNumberToObject(profile,"schema",1);
        cJSON_AddStringToObject(profile,"kind","seasonal.shadow.v1");
        cJSON_AddStringToObject(profile,"adapter_id",owner_.c_str());
        cJSON_AddStringToObject(profile,"profile_digest",seasonalSource_->profileDigest.c_str());
        cJSON_AddStringToObject(profile,"config_pin",seasonalSource_->configDigest.c_str());
        cJSON_AddBoolToObject(profile,"physical_outputs_enabled",false);
        cJSON_AddBoolToObject(profile,"frost_protection_available",false);
    }
    void hello() {
        auto o=base(); sourcePolicy(o.get()); cJSON_AddStringToObject(o.get(),"challenge_id",challenge_.c_str());
        cJSON_AddStringToObject(o.get(),"mode","shadow"); cJSON_AddNumberToObject(o.get(),"lease_ms",leaseMs);
        cJSON_AddNumberToObject(o.get(),"grant_ms",grantMs); cJSON_AddBoolToObject(o.get(),"storage_fault",fault_);
        auto controlCaps=cJSON_AddArrayToObject(o.get(),"session_capabilities");
        if(controlCaps)cJSON_AddItemToArray(controlCaps,cJSON_CreateString("session.grant_nonce.v1"));
        auto comfortCaps=cJSON_AddArrayToObject(o.get(),"control_capabilities");
        if(comfortCaps)cJSON_AddItemToArray(comfortCaps,cJSON_CreateString("comfort.target.v1"));
        if(comfortCaps)cJSON_AddItemToArray(comfortCaps,cJSON_CreateString("comfort.contacts.v1"));
        if(comfortCaps&&nativePlanSource_)cJSON_AddItemToArray(comfortCaps,cJSON_CreateString(nativePlanSource_->planContract()));
        if(comfortCaps&&nativePlanSource_)cJSON_AddItemToArray(comfortCaps,cJSON_CreateString(roomDisplayNamesCapability));
        if(comfortCaps&&nativePlanSource_&&nativePlanSource_->legacyReadbackReviewed)
            cJSON_AddItemToArray(comfortCaps,cJSON_CreateString(NativePlanInstallationSource::legacyCapability));
        if(comfortCaps&&nativePlanSource_&&nativePlanSource_->predecessor)
            cJSON_AddItemToArray(comfortCaps,cJSON_CreateString(NativePlanInstallationSource::evolutionCapability));
        if(metrics_||boilerFields_) {
            auto caps=cJSON_AddArrayToObject(o.get(),"read_only_capabilities");
            if(caps&&metrics_)cJSON_AddItemToArray(caps,cJSON_CreateString(metricsCapability));
            if(caps&&boilerFields_)cJSON_AddItemToArray(caps,cJSON_CreateString(boilerFieldsCapability));
        }
        send("fw/hello",o.get());
    }
    void metricsSnapshot(uint64_t now) {
        if(!metrics_||fault_||!session_||!mappingReady_||!admission_.alive(now)
            ||!admission_.grantDeadline(now)||now<nextMetrics_||metricsSequence_==UINT32_MAX
            ||now>UINT64_MAX-metricsIntervalMs) return;
        // At most one bounded source read/publish attempt every30s. No retries
        // or telemetry-driven lease/sample/model renewal.
        nextMetrics_=now+metricsIntervalMs;
#if defined(__cpp_exceptions)
        try {
#endif
        std::ostringstream stream;metrics_(stream);const auto raw=stream.str();
        if(raw.size()>maximumMetricsBytes)return;
        auto metrics=parseControlJson(raw);
        if(!metrics||!validMetricsSnapshot(metrics.get()))return;
        auto o=base();
        if(!exactFields(o.get(),{"api","controller_id","boot_id","epoch","config_revision","config_digest"}))return;
        if(!cJSON_AddStringToObject(o.get(),"mode","shadow")
            ||!cJSON_AddStringToObject(o.get(),"adapter_id",owner_.c_str())
            ||!cJSON_AddStringToObject(o.get(),"adapter_session_id",sessionId_.c_str())
            ||!cJSON_AddStringToObject(o.get(),"grant_id",grant_.c_str())
            ||!cJSON_AddNumberToObject(o.get(),"grant_sequence",grantSequence_)
            ||!cJSON_AddNumberToObject(o.get(),"sequence",metricsSequence_+1)
            ||!cJSON_AddBoolToObject(o.get(),"boiler_output_enabled",false)
            ||!cJSON_AddBoolToObject(o.get(),"actuator_output_enabled",false)
            ||!cJSON_AddItemToObject(o.get(),"metrics",metrics.get()))return;
        metrics.release();const auto bytes=printJson(o.get());
        if(bytes.empty()||bytes.size()>maximumMetricsEnvelopeBytes)return;
        ++metricsSequence_;publish_("fw/telemetry/ems_metrics",bytes);
#if defined(__cpp_exceptions)
        } catch(const std::exception&) { /* Read-only getter failure: next cadence, no control renewal. */ }
#endif
    }
    void boilerFieldSnapshot(uint64_t now) {
        if(!boilerFields_||fault_||!session_||!mappingReady_||!admission_.alive(now)
            ||!admission_.grantDeadline(now)||now<nextBoilerFields_||boilerSequence_==UINT32_MAX
            ||now>maximumBoilerTimestamp-boilerGroupIntervalMs)return;
        nextBoilerFields_=now+boilerGroupIntervalMs;
        const auto group=boilerGroup_;boilerGroup_=(boilerGroup_+1)%boilerFieldGroupCount;
        try {
            std::ostringstream ss;boilerFields_(ss,group);const auto raw=ss.str();
            if(raw.size()>maximumBoilerGroupBytes)return;
            auto values=parseControlJson(raw);if(!values||!validBoilerGroup(values.get(),group))return;
            auto o=base();
            if(!exactFields(o.get(),{"api","controller_id","boot_id","epoch","config_revision","config_digest"}))return;
            if(!cJSON_AddStringToObject(o.get(),"mode","shadow")
                ||!cJSON_AddStringToObject(o.get(),"adapter_id",owner_.c_str())
                ||!cJSON_AddStringToObject(o.get(),"adapter_session_id",sessionId_.c_str())
                ||!cJSON_AddStringToObject(o.get(),"grant_id",grant_.c_str())
                ||!cJSON_AddNumberToObject(o.get(),"grant_sequence",grantSequence_)
                ||!cJSON_AddNumberToObject(o.get(),"sequence",boilerSequence_+1)
                ||!cJSON_AddNumberToObject(o.get(),"group",group)
                ||!cJSON_AddBoolToObject(o.get(),"boiler_output_enabled",false)
                ||!cJSON_AddBoolToObject(o.get(),"actuator_output_enabled",false)
                ||!cJSON_AddItemToObject(o.get(),"values",values.get()))return;
            values.release();const auto bytes=printJson(o.get());
            if(bytes.empty()||bytes.size()>maximumBoilerEnvelopeBytes)return;
            ++boilerSequence_;publish_("fw/telemetry/boiler_fields",bytes);
        } catch(const std::exception&) { /* A getter failure never renews control or measurements. */ }
    }
    void sessionStatus() {
        auto o=base(); cJSON_AddStringToObject(o.get(),"adapter_id",owner_.c_str());
        cJSON_AddStringToObject(o.get(),"adapter_session_id",sessionId_.c_str()); cJSON_AddStringToObject(o.get(),"client_nonce",clientNonce_.c_str());
        cJSON_AddStringToObject(o.get(),"grant_id",grant_.c_str()); cJSON_AddNumberToObject(o.get(),"grant_sequence",grantSequence_);
        cJSON_AddNumberToObject(o.get(),"grant_ms",grantMs); cJSON_AddBoolToObject(o.get(),"mapping_ready",mappingReady_);
        if(!issuedGrantNonce_.empty()) cJSON_AddStringToObject(o.get(),"grant_request_nonce",issuedGrantNonce_.c_str());
        send("fw/session",o.get());
    }
    void result(const char *topic,const Envelope &e,const char *status,const char *rejectionReason=nullptr) {
        auto o=base(); cJSON_AddStringToObject(o.get(),"adapter_session_id",std::string(e.session).c_str());
        cJSON_AddStringToObject(o.get(),"binding_id",std::string(e.binding).c_str());
        cJSON_AddNumberToObject(o.get(),"sequence",e.sequence); cJSON_AddStringToObject(o.get(),"status",status);
        if(rejectionReason)cJSON_AddStringToObject(o.get(),"rejection_reason",rejectionReason);
        send(topic,o.get());
    }
    void snapshot(uint32_t request=0) {
        auto o=base(); auto cfg=configBytes_.empty()?nullptr:cJSON_Parse(configBytes_.c_str());
        cJSON_AddItemToObject(o.get(),"config",cfg?cfg:cJSON_CreateNull());
        if(nativePlanSource_) {
            cJSON_AddStringToObject(o.get(),"adapter_id",owner_.c_str());
            cJSON_AddStringToObject(o.get(),"adapter_session_id",sessionId_.c_str());
            cJSON_AddStringToObject(o.get(),"grant_id",grant_.c_str());cJSON_AddNumberToObject(o.get(),"grant_sequence",grantSequence_);
            cJSON_AddNumberToObject(o.get(),"request_sequence",request);
            cJSON_AddStringToObject(o.get(),"profile_digest",nativePlanSource_->profileDigest.c_str());
            cJSON_AddStringToObject(o.get(),"plan_contract",nativePlanSource_->planContract());
            cJSON_AddBoolToObject(o.get(),"boiler_output_enabled",false);cJSON_AddBoolToObject(o.get(),"actuator_output_enabled",false);
        }
        send("fw/config_snapshot",o.get());
    }
    void state(uint64_t now,int64_t utc,bool clockValid) {
        auto o=base(); sourcePolicy(o.get()); cJSON_AddStringToObject(o.get(),"mode","shadow");
        cJSON_AddBoolToObject(o.get(),"boiler_output_enabled",false); cJSON_AddBoolToObject(o.get(),"actuator_output_enabled",false);
        // Same owner's bounded last admission, not a command receipt/authority
        // or measurement timestamp. No grant, nonce, session or settings hash.
        if(lastUserCommand_.sequence) {
            auto diagnostic=cJSON_AddObjectToObject(o.get(),"last_user_command_admission");
            cJSON_AddStringToObject(diagnostic,"binding_id",lastUserCommand_.binding.data());
            cJSON_AddNumberToObject(diagnostic,"sequence",lastUserCommand_.sequence);
            cJSON_AddNumberToObject(diagnostic,"received_config_revision",lastUserCommand_.revision);
            cJSON_AddNumberToObject(diagnostic,"received_at_ms",static_cast<double>(lastUserCommand_.at));
            cJSON_AddStringToObject(diagnostic,"outcome",admissionCodeName(lastUserCommand_.code));
        }
        SeasonalSafetySnapshot safety;
        bool safetyFresh=false;
        if(seasonalSource_&&seasonalSafety_&&!policySourceFault_) {
            if(safetyReading_)policySourceFault_=true;
            else {
                safetyReading_=true;
#if defined(__cpp_exceptions)
                try {
#endif
                    safety=seasonalSafety_();
                    safetyFresh=acceptSeasonalSafety(now,safety);
#if defined(__cpp_exceptions)
                } catch(...) {safety={};safetyFresh=false;}
#endif
                safetyReading_=false;
            }
            safetyFresh=safetyFresh&&!policySourceFault_;
        }
        HydraulicFeedbackGate::Result hydraulicFacts;
        if(hydraulicSource_&&!hydraulicSourceFault_) {
            const auto generation=policyGeneration_,revision=config_->revision;
            const auto startedAt=sessionStart_;
            if(hydraulicReading_)hydraulicSourceFault_=true;
            else if(seasonalSource_&&seasonalSource_->profileDigest==hydraulicSource_->profileDigest) {
                hydraulicReading_=true;
                try {
                    const HydraulicOwnerContext context{generation,revision,supervisor_.lastIntent().openingCommand,startedAt,boot_};
                    const auto snapshot=hydraulicFeedback_(context);
                    if(!hydraulicSourceFault_&&generation==policyGeneration_&&revision==config_->revision
                        &&startedAt==sessionStart_&&now>=lastNow_&&session_&&mappingReady_&&!fault_&&admission_.alive(now))
                        hydraulicFacts=hydraulicGate_.evaluate(now,hydraulicSource_->maximumFactAgeMs,context,snapshot);
                } catch(...) {hydraulicSourceFault_=true;}
                hydraulicReading_=false;
            }
        }
        // A synchronous native observer may invalidate ownership. Recheck AFTER
        // it returns, never use a pre-callback alive/admission snapshot.
        const bool alive=session_&&mappingReady_&&!fault_&&admission_.alive(now);
        cJSON_AddBoolToObject(o.get(),"adapter_alive",alive);
        bool requestedHeat=false;
        auto list=cJSON_AddArrayToObject(o.get(),"zones");
        for(size_t i=0;i<config_->count;++i) {
            auto &z=config_->zones[i]; auto row=cJSON_CreateObject(); cJSON_AddItemToArray(list,row);
            cJSON_AddStringToObject(row,"zone_id",z.id.c_str());
            if(alive&&i<roomNamesHex_.size()&&roomNamesHex_[i][0])
                cJSON_AddStringToObject(row,"name_utf8_hex",roomNamesHex_[i].data());
            const auto temperature=alive?z.sample.value(now):std::nullopt;
            auto target=std::optional<int16_t>(z.base);
            const char *source="base",*reason="shadow_idle";
            if(z.scheduled) { target=z.schedule.target(utc,clockValid).temperatureCentiC; source="schedule"; }
            auto in=z.comfortInputs;in.automaticCentiC=target;in.automaticSource=source;
            in.ownerAdmitted=alive;in.utc=utc;in.clockTrusted=clockValid;
            const auto effective=z.comfortEnabled?z.comfort.evaluate(now,in):
                EffectiveTarget::api1(target,source,z.off,z.overrideTarget,z.overrideUntil,now);
            if(z.comfortEnabled) {
                reason=effective.reason;
                cJSON_AddStringToObject(row,"comfort_mode",z.comfort.modeName());
                cJSON_AddNumberToObject(row,"override_remaining_ms",z.comfort.remainingMs(now));
                cJSON_AddNumberToObject(row,"vacation_until_utc",z.comfort.vacationUntil());
            }
            target=effective.target;source=effective.source;
            if(!alive) reason="adapter_unavailable";
            else if(!temperature) reason="source_unverified_or_stale";
            else if(!target&&!z.comfortEnabled) reason=z.off?"off":"schedule_time_invalid_or_expired";
            const bool usable=alive&&temperature&&target;
            ZoneRegulator::Result regulation;
            if(seasonalSource_) {
                SeasonalInputs policy;
                const auto age=z.sample.age(now);
                policy.temperature=temperature;policy.target=target;policy.ownerAdmitted=alive;
                policy.sourceQualified=alive&&bool(temperature)&&bool(age)&&*age<=now;
                policy.sensorAt=policy.sourceQualified?now-*age:0;
                policy.ownerGeneration=policyGeneration_;
                policy.stop=!target;policy.allOff=safety.allOff;
                policy.preempted=safety.preempted;
                policy.limitsKnownSafe=safetyFresh&&safety.limitsKnownSafe;
                policy.dhwStateKnown=safetyFresh&&safety.dhwStateKnown;
                policy.dhwActive=safety.dhwActive;
                policy.summer=safety.summer;
                policy.frostSelected=target&&std::string_view(source)=="frost";
                // Explicit frost value must remain the SAME displayed selected target.
                const auto pin=seasonalSource_->zone(z.id);
                if(policy.frostSelected&&(!pin||*target!=pin->seasonal.frostTargetCentiC))policy.stop=true;
                regulation=z.regulator.stepSeasonal(now,policy);
                if(target)reason=regulation.reason;
                cJSON_AddBoolToObject(row,"seasonal_policy",true);
                cJSON_AddNumberToObject(row,"seasonal_restrictions",regulation.seasonalRestrictions);
                cJSON_AddBoolToObject(row,"frost_protection_available",false);
                cJSON_AddBoolToObject(row,"physical_outputs_enabled",false);
            } else regulation=z.regulator.step(now,temperature,target,usable);
            if(z.comfortEnabled)cJSON_AddBoolToObject(row,"learning_allowed",
                effective.learningAllowed&&alive&&bool(temperature)&&(!seasonalSource_
                    ||(regulation.seasonalQualified&&!regulation.seasonalRestrictions&&!regulation.frostAdvice)));
            z.demand=regulation.demand;
            requestedHeat=requestedHeat||z.demand;
            if(z.demand&&!z.comfortEnabled&&!seasonalSource_) reason="shadow_demand";
            const auto nullable=[row](const char *key,auto value) { if(value) cJSON_AddNumberToObject(row,key,*value); else cJSON_AddNullToObject(row,key); };
            nullable("temperature_centi_c",temperature); nullable("target_centi_c",target); nullable("sample_age_ms",z.sample.age(now));
            cJSON_AddNumberToObject(row,"sample_state",static_cast<int>(z.sample.state(now)));
            cJSON_AddStringToObject(row,"target_source",source); cJSON_AddBoolToObject(row,"demand",z.demand); cJSON_AddStringToObject(row,"reason",reason);
        }
        HydraulicInputs inputs=hydraulicSource_?hydraulicFacts.inputs:HydraulicInputs{};
        inputs.adapterAlive=alive;inputs.sourceValid=requestedHeat;inputs.heatDemand=requestedHeat;
        if(hydraulicSource_) {
            // Compose restrictions from the CURRENT selected policy as well.
            inputs.limitsKnownSafe=inputs.limitsKnownSafe&&safetyFresh&&safety.limitsKnownSafe;
            inputs.dhwStateKnown=inputs.dhwStateKnown&&safetyFresh&&safety.dhwStateKnown;
            inputs.dhwActive=inputs.dhwActive||safety.dhwActive;
            inputs.stop=inputs.stop||safety.allOff||safety.preempted;
        }
        HydraulicSupervisor::Result hydraulic;
        // Before the first admitted owner there is no active hydraulic lifetime
        // to invalidate. Later ownership loss still reaches the SAME supervisor.
        const bool hydraulicOwnerReady=alive&&config_->revision&&config_->count;
        if(!hydraulicSource_||hydraulicOwnerReady||hydraulicStarted_) {
            hydraulicStarted_=hydraulicStarted_||bool(hydraulicSource_&&hydraulicOwnerReady);
            hydraulic=supervisor_.step(now,inputs);
        } else hydraulic.reason="adapter_unavailable";
        auto status=cJSON_AddObjectToObject(o.get(),"supervisor");
        cJSON_AddStringToObject(status,"phase",hydraulicPhaseName(hydraulic.phase));
        cJSON_AddStringToObject(status,"reason",hydraulic.reason);
        cJSON_AddBoolToObject(status,"requested_heat",requestedHeat);
        cJSON_AddBoolToObject(status,"physical_outputs_enabled",false);
        if(hydraulicSource_) {
            cJSON_AddStringToObject(status,"feedback_status",hydraulicFacts.reason);
            cJSON_AddBoolToObject(status,"heat_intent",hydraulic.heatIntent);
            cJSON_AddBoolToObject(status,"pump_intent",hydraulic.pumpIntent);
            cJSON_AddStringToObject(status,"path_intent",hydraulic.pathIntent==HydraulicPathIntent::requestQualifiedPath
                ?"request_qualified_path":hydraulic.pathIntent==HydraulicPathIntent::retainExistingPath?"retain_existing_path":"none");
            cJSON_AddNumberToObject(status,"opening_command",hydraulic.openingCommand);
            if(hydraulic.waterTarget)cJSON_AddNumberToObject(status,"water_target_centi_c",*hydraulic.waterTarget);
            else cJSON_AddNullToObject(status,"water_target_centi_c");
        }
        send("fw/state/zones",o.get());
    }
    std::string controller_,boot_,owner_,digest_,configBytes_,challenge_,grant_,sessionId_,clientNonce_,lastOpen_;
    std::string pendingGrantNonce_,issuedGrantNonce_;
    ControlStore &store_; Hash hash_; Nonce nonce_; Publish publish_; Metrics metrics_;
    std::unique_ptr<Configuration> config_=std::make_unique<Configuration>();
    SessionAdmission admission_;
    // Current native product supports two rooms. Labels never enter durable
    // control configuration or increase its policy/channel limits.
    std::array<std::array<char,maximumRoomDisplayNameBytes*2+1>,2> roomNamesHex_{};
    HydraulicSupervisor supervisor_;
    std::unique_ptr<HydraulicControllerSource> hydraulicSource_;
    HydraulicFeedbackProvider hydraulicFeedback_;
    HydraulicFeedbackGate hydraulicGate_;
    bool hydraulicReading_=false,hydraulicSourceFault_=false,hydraulicStarted_=false;
    std::unique_ptr<SeasonalControllerSource> seasonalSource_;
    std::unique_ptr<NativePlanInstallationSource> nativePlanSource_;
    bool nativeReceiving_=false,legacyQuarantine_=false;
    SeasonalControllerSource::Safety seasonalSafety_;
    uint32_t policyGeneration_=0;
    bool safetyReading_=false,policySourceFault_=false;
    uint64_t lastSafetyAt_=0,retiredSafetyThrough_=0;
    uint8_t lastSafetyValue_=0;
    bool haveSafetyFact_=false,haveRetiredSafety_=false;
    struct UserCommandAdmission {
        std::array<char,33> binding{};
        uint32_t sequence=0,revision=0;
        uint64_t at=0;
        AdmissionCode code=AdmissionCode::not_configured;
    } lastUserCommand_;
    uint32_t epoch_=0,grantSequence_=0,metricsSequence_=0;
    uint64_t nextMetrics_=0;
    BoilerFields boilerFields_;
    uint64_t nextBoilerFields_=0;
    uint32_t boilerSequence_=0;
    size_t boilerGroup_=0;
    uint64_t challengeUntil_=0,nextHello_=0,nextState_=0,nextGrant_=0,lastNow_=0,sessionStart_=0;
    bool session_=false,mappingReady_=false,connected_=false,fault_=false,leaseWasAlive_=false;
};
}
