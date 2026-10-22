#pragma once
#include "ControlStore.h"
#include "GraphWireTuple.h"
#include "SessionAdmission.h"
#include <optional>

namespace heating::control {
// SOURCE-stage firmware counterpart to HA GraphShadowJournal. Existing native
// transport is NOT changed to select/advertise api2 by this class.
// One owner calls after its authenticated local handshake. No broker auth here.
class GraphShadowConfiguration {
public:
    static constexpr size_t maximumStoreBytes=4096;
    using Hash=heating::graph_test::Hash;
    GraphShadowConfiguration(std::string controller,std::string boot,std::string owner,
                             std::string qualification,ControlStore& store,Hash hash)
        :controller_(std::move(controller)),boot_(std::move(boot)),owner_(std::move(owner)),
         qualification_(std::move(qualification)),store_(store),hash_(std::move(hash)),
         admission_(owner_,Direction::ha_to_fw,2) {}
    bool initialize() {
        if (initialized_ || fault_) return false;
        if (!SessionAdmission::validId(controller_) || !SessionAdmission::validId(boot_)
            || !SessionAdmission::validId(owner_) || !heating::graph_test::hex(qualification_) || !hash_)
            return fault("graph_identity_unqualified");
        try {
            if (!heating::graph_test::hex(hash_("")) || !store_.load(durable_)) return fault("storage_fault");
            if (!durable_.empty()) {
                if (durable_.size()>maximumStoreBytes) return fault("storage_budget");
                auto record=heating::graph_test::parse(durable_);
                using namespace heating::graph_test;
                object(record.get(),{"config","config_digest","controller_id","mapping","owner","schema"});
                literal(get(record.get(),"controller_id"),controller_.c_str(),"controller_conflict");
                literal(get(record.get(),"owner"),owner_.c_str(),"owner_conflict");
                need(integer(get(record.get(),"schema"),1,1)==1,"unsupported_schema");
                const auto config=get(record.get(),"config"),mapping=get(record.get(),"mapping");
                const auto configBytes=print(config),mappingBytes=print(mapping);
                const auto revision=static_cast<uint32_t>(integer(get(config,"revision"),1,UINT32_MAX));
                const auto mappingRevision=static_cast<uint32_t>(integer(get(mapping,"mapping_revision"),1,UINT32_MAX));
                auto context=restoreContext(revision,mappingRevision,hash_(mappingBytes));
                const auto raw=envelope(config,context,1);
                auto result=validate(raw,mappingBytes,context,hash_);
                need(result.code=="valid_shadow_candidate","stored_graph_invalid");
                const auto digest=hash_(configBytes);
                literal(get(record.get(),"config_digest"),digest.c_str(),"config_digest");
                adopt(configBytes,mappingBytes,digest,context.mappingDigest,result.candidate);
            }
        } catch (const heating::graph_test::Failure&) {return fault("stored_graph_invalid");}
          catch (const std::bad_alloc&) {return fault("allocation");}
          catch (const std::exception&) {return fault("graph_dependency_fault");}
        initialized_=true;status_="graph_loaded_no_admission";return true;
    }
    bool openSession(const SessionIdentity& identity,uint32_t leaseMs=15000) {
        if (!initialized_ || fault_ || identity.controller!=controller_ || identity.boot!=boot_
            || identity.adapter!=owner_ || identity.revision!=revision_) return false;
        if (!admission_.begin(identity,leaseMs)) return false;
        identity_=identity;grant_.clear();grantSequence_=0;
        if (!admission_.bind(0,"adapter",StreamKind::heartbeat)
            || !admission_.bind(1,"config",StreamKind::configuration)
            || !admission_.bind(2,"snapshot",StreamKind::configuration)) return fault("graph_binding_fault");
        status_="graph_session_no_lease";return true;
    }
    bool issueGrant(std::string_view grant,uint32_t sequence,uint64_t now,uint32_t durationMs) {
        if (fault_ || !checkNow(now) || !admission_.issueGrant(grant,sequence,now,durationMs)) return false;
        grant_=grant;grantSequence_=sequence;return true;
    }
    Admission heartbeat(const Envelope& e,uint64_t now) {
        // Caller shape-checks heartbeat before this existing admission primitive.
        if (fault_ || !checkNow(now)) return {AdmissionCode::not_configured};
        auto result=admission_.admit(0,e,now);
        if (result.code==AdmissionCode::accepted) status_="graph_session_lease";
        return result;
    }
    Admission requestSnapshot(const Envelope& e,uint64_t now) {
        if(fault_||!checkNow(now))return {AdmissionCode::not_configured};
        return admission_.admit(2,e,now);
    }
    void disconnected() {admission_.invalidateTransport();if(!fault_)status_="graph_readback_required";}
    bool alive(uint64_t now) const {return initialized_&&!fault_&&(!haveNow_||now>=lastNow_)&&admission_.alive(now);}
    uint64_t grantDeadline(uint64_t now) const {
        return initialized_&&!fault_&&(!haveNow_||now>=lastNow_)?admission_.grantDeadline(now):0;
    }
    std::string apply(std::string_view raw,std::string_view mapping,uint64_t now) {
        if (fault_) return status_;
        if (!initialized_) return status_="graph_unavailable";
        if (!checkNow(now)) return status_;
        try {
            const auto context=currentContext();
            auto result=heating::graph_test::validate(raw,mapping,context,hash_);
            if (result.code!="valid_shadow_candidate") return status_=result.code;
            auto root=heating::graph_test::parse(raw);
            const auto config=heating::graph_test::get(root.get(),"config");
            const auto configBytes=heating::graph_test::print(config);
            const auto configDigest=hash_(configBytes),mappingDigest=hash_(mapping);
            const auto payloadDigest=hash_(raw);
            if (!heating::graph_test::hex(payloadDigest) || !heating::graph_test::hex(configDigest)
                || !heating::graph_test::hex(mappingDigest)) {fault("hash_fault");return status_;}
            Envelope e;e.major=2;e.kind=StreamKind::configuration;e.direction=Direction::ha_to_fw;
            e.controller=controller_;e.boot=boot_;e.adapter=owner_;e.session=identity_.session;e.epoch=identity_.epoch;
            e.revision=revision_;e.grant=grant_;e.grantSequence=grantSequence_;e.binding="config";
            e.sequence=static_cast<uint32_t>(heating::graph_test::integer(heating::graph_test::get(root.get(),"sequence"),1,UINT32_MAX));
            for(size_t i=0;i<32;++i)e.payloadDigest[i]=static_cast<uint8_t>((digit(payloadDigest[2*i])<<4)|digit(payloadDigest[2*i+1]));
            auto map=heating::graph_test::parse(mapping);
            const auto bytes=record(config,configDigest,map.get());
            if (bytes.size()>maximumStoreBytes) return status_="storage_budget";
            const auto admitted=admission_.admit(1,e,now);
            if (admitted.code==AdmissionCode::duplicate) return status_="duplicate";
            if (admitted.code!=AdmissionCode::accepted) return status_="graph_session_rejected";
            std::string readback;
            if (!store_.load(readback) || readback!=durable_) {fault("storage_drift");return status_;}
            if (!store_.save(bytes) || !store_.load(readback) || readback!=bytes) {
                fault("storage_fault");return status_;
            }
            durable_=bytes;adopt(configBytes,std::string(mapping),configDigest,mappingDigest,result.candidate);
            admission_.invalidateTransport();status_="graph_committed_no_admission";return status_;
        } catch(const heating::graph_test::Failure&) {fault("graph_invalid");return status_;}
          catch(const std::bad_alloc&) {fault("allocation");return status_;}
          catch(const std::exception&) {fault("graph_dependency_fault");return status_;}
    }
    // Same atomic store/admission, but real transport carries mapping in ONE
    // explicitly negotiated API2 frame. Decoder does not confer any privilege.
    std::string applyTuple(std::string_view wire,uint64_t now) {
        if(fault_) return status_;
        try {
            const auto parts=decodeGraphTuple(wire,hash_);
            return apply(parts.message,parts.mapping,now);
        } catch(const heating::graph_test::Failure& error) {return status_=error.code;}
          catch(const std::bad_alloc&) {fault("allocation");return status_;}
          catch(const std::exception&) {fault("graph_dependency_fault");return status_;}
    }
    uint32_t revision() const {return revision_;}
    uint32_t mappingRevision() const {return mappingRevision_;}
    const std::string& configBytes() const {return config_;}
    const std::string& mappingBytes() const {return mapping_;}
    const std::string& configDigest() const {return digest_;}
    const std::string& status() const {return status_;}
    bool faulted() const {return fault_;}
    static constexpr bool boilerOutputEnabled() {return false;}
    static constexpr bool actuatorOutputEnabled() {return false;}
private:
    static uint8_t digit(char c) {return c<='9'?c-'0':c-'a'+10;}
    bool fault(const char* reason) {fault_=true;admission_.invalidateTransport();status_=reason;return false;}
    bool checkNow(uint64_t now) {
        if (haveNow_ && now<lastNow_) return fault("graph_monotonic_fault");
        haveNow_=true;lastNow_=now;return true;
    }
    using Context=heating::graph_test::Context;
    Context currentContext() const {
        return {controller_,boot_,owner_,identity_.session,grant_,identity_.epoch,grantSequence_,
                revision_,mappingRevision_,mappingDigest_,qualification_};
    }
    Context restoreContext(uint32_t revision,uint32_t mappingRevision,const std::string& mappingDigest) const {
        // Validates durable DATA only. NEVER passed to SessionAdmission::begin.
        return {controller_,boot_,owner_,"restored_data","not_a_grant",1,1,
                revision-1,mappingRevision,mappingDigest,qualification_};
    }
    std::string envelope(const cJSON* config,const Context& context,uint32_t sequence) const {
        using namespace heating::graph_test;
        Json message(cJSON_CreateObject(),cJSON_Delete);need(bool(message),"allocation");
        const auto text=[&](const char* k,const std::string& v){need(cJSON_AddStringToObject(message.get(),k,v.c_str()),"allocation");};
        const auto number=[&](const char* k,uint32_t v){need(cJSON_AddNumberToObject(message.get(),k,v),"allocation");};
        // Exact canonical key order expected by the shared validator.
        text("adapter_id",context.adapterId);text("adapter_session_id",context.sessionId);number("api",2);
        text("binding_id","config");text("boot_id",context.bootId);
        Json copy(cJSON_Duplicate(config,true),cJSON_Delete);need(bool(copy),"allocation");
        need(cJSON_AddItemToObject(message.get(),"config",copy.get()),"allocation");copy.release();
        text("config_digest",hash_(print(config)));number("config_revision",context.currentRevision);
        text("controller_id",context.controllerId);number("epoch",context.epoch);
        number("expected_revision",context.currentRevision);text("grant_id",context.grantId);
        number("grant_sequence",context.grantSequence);number("sequence",sequence);return print(message.get());
    }
    std::string record(const cJSON* config,const std::string& digest,const cJSON* mapping) const {
        using namespace heating::graph_test;
        Json root(cJSON_CreateObject(),cJSON_Delete);need(bool(root),"allocation");
        const auto copy=[&](const char* key,const cJSON* value){
            Json item(cJSON_Duplicate(value,true),cJSON_Delete);need(bool(item),"allocation");
            need(cJSON_AddItemToObject(root.get(),key,item.get()),"allocation");item.release();
        };
        copy("config",config);need(cJSON_AddStringToObject(root.get(),"config_digest",digest.c_str()),"allocation");
        need(cJSON_AddStringToObject(root.get(),"controller_id",controller_.c_str()),"allocation");
        copy("mapping",mapping);need(cJSON_AddStringToObject(root.get(),"owner",owner_.c_str()),"allocation");
        need(cJSON_AddNumberToObject(root.get(),"schema",1),"allocation");return print(root.get());
    }
    void adopt(const std::string& config,const std::string& mapping,const std::string& digest,
               const std::string& mappingDigest,const heating::graph_test::GraphShadowCandidate& candidate) {
        config_=config;mapping_=mapping;digest_=digest;revision_=candidate.revision;
        mappingRevision_=candidate.mappingRevision;mappingDigest_=mappingDigest;
    }
    std::string controller_,boot_,owner_,qualification_;
    ControlStore& store_;Hash hash_;SessionAdmission admission_;SessionIdentity identity_;
    std::string durable_,config_,mapping_,digest_,mappingDigest_,grant_,status_="not_initialized";
    uint32_t revision_=0,mappingRevision_=0,grantSequence_=0;uint64_t lastNow_=0;
    bool initialized_=false,fault_=false,haveNow_=false;
};
}
