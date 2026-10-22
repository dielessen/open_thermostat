#pragma once
#include "GraphShadowConfiguration.h"
#include <map>
#include <vector>

namespace heating::control {
// Explicit SOURCE-stage bounded shadow owner. No socket/worker/broker credentials,
// physical IO or product default. Selected owner must use the EXISTING connection.
// Caller pins qualification manifest digest; incoming wire cannot replace it.
class GraphSessionOwner {
public:
    using Hash=heating::graph_test::Hash;
    using Nonce=std::function<std::string()>;
    using Publish=std::function<void(std::string_view,std::string_view)>;
    static constexpr uint32_t leaseMs=15000,grantMs=10000;
    static constexpr const char* transport="atomic_mapping_tuple.v1";
    static constexpr const char* profile="bounded_shadow_1r1f1b";
    GraphSessionOwner(std::string controller,std::string boot,std::string adapter,
                      std::string anchor,ControlStore& store,Hash hash,Nonce nonce,Publish publish)
        :controller_(std::move(controller)),boot_(std::move(boot)),adapter_(std::move(adapter)),
         anchor_(std::move(anchor)),hash_(std::move(hash)),nonce_(std::move(nonce)),publish_(std::move(publish)),
         core_(controller_,boot_,adapter_,anchor_,store,hash_) {
        fault_=!nonce_||!publish_||!core_.initialize();
    }
    void connected(uint64_t now) {
        guard([&]{if(!time(now))return;connected_=true;restart(now);hello();});
    }
    void disconnected() {connected_=false;clearSession();core_.disconnected();}
    void tick(uint64_t now,int64_t=0,bool=false) {
        guard([&]{
            if(!connected_||!time(now)||fault_)return;
            if(expired(now)) {restart(now);hello();return;}
            if(!session_.empty()&&now>=nextGrant_) {rotate(now);sessionStatus();}
            if(now>=challengeUntil_) newChallenge(now);
            if(now>=nextHello_)hello();
        });
    }
    void receive(std::string_view topic,std::string_view bytes,uint64_t now,int64_t=0,bool=false) {
        guard([&]{
            if(!connected_||!time(now)||fault_||topic.size()>32)return;
            const std::string owned(topic);topic=owned;
            if(expired(now)) {restart(now);hello();return;}
            auto root=heating::graph_test::parse(bytes);
            if(topic=="ha/open_session"){open(root.get(),bytes,now);return;}
            if(session_.empty())return;
            if(topic=="ha/config") {
                // Full shared graph+mapping+session admission occurs inside core.
                const auto result=core_.applyTuple(bytes,now);
                Frame frame=base(true);frame.text("status",result);
                frame.number("sequence",number(root.get(),"sequence"));
                send("fw/config_result",frame);
                if(core_.faulted()){fault();return;}
                if(result=="graph_committed_no_admission"){restart(now);hello();}
                return;
            }
            const bool heartbeat=topic=="ha/heartbeat",snapshot=topic=="ha/snapshot_request";
            if(!heartbeat&&!snapshot)return;
            using namespace heating::graph_test;
            if(heartbeat)object(root.get(),{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id",
                "grant_id","grant_sequence","config_revision","binding_id","sequence","grant_request_nonce"});
            else object(root.get(),{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id",
                "grant_id","grant_sequence","config_revision","binding_id","sequence"});
            if(heartbeat)need(SessionAdmission::validId(str(get(root.get(),"grant_request_nonce"))),"identity");
            auto e=envelope(root.get(),heartbeat?"adapter":"snapshot",
                heartbeat?StreamKind::heartbeat:StreamKind::configuration,bytes);
            const auto admitted=heartbeat?core_.heartbeat(e,now):core_.requestSnapshot(e,now);
            if(admitted.code!=AdmissionCode::accepted&&admitted.code!=AdmissionCode::duplicate)return;
            if(heartbeat&&admitted.code==AdmissionCode::accepted) {
                pendingNonce_=str(get(root.get(),"grant_request_nonce"));leaseWasAlive_=true;
            }
            Frame result=base(true);result.text("binding_id",heartbeat?"adapter":"snapshot");
            result.number("sequence",e.sequence);
            result.text("status",admitted.code==AdmissionCode::accepted?"accepted":"duplicate");
            send(heartbeat?"fw/heartbeat_result":"fw/snapshot_result",result);
            if(heartbeat&&admitted.code==AdmissionCode::accepted)capability();
            if(snapshot)readback(e.sequence);
        });
    }
    bool faulted()const{return fault_||core_.faulted();}
    const GraphShadowConfiguration& configuration()const{return core_;}
private:
    // Root fields canonicalised using transferred ownership, not duplicated trees.
    // All nested values originate from exact validated core DATA/static contract.
    class Frame {
    public:
        Frame():root_(cJSON_CreateObject(),cJSON_Delete){heating::graph_test::need(bool(root_),"allocation");}
        void text(const char* key,const std::string& value){heating::graph_test::need(cJSON_AddStringToObject(root_.get(),key,value.c_str()),"allocation");}
        void number(const char* key,uint32_t value){heating::graph_test::need(cJSON_AddNumberToObject(root_.get(),key,value),"allocation");}
        void flag(const char* key,bool value){heating::graph_test::need(cJSON_AddBoolToObject(root_.get(),key,value),"allocation");}
        void raw(const char* key,const std::string& value) {
            using namespace heating::graph_test;
            Json item(value.empty()?cJSON_CreateNull():cJSON_Parse(value.c_str()),cJSON_Delete);
            need(bool(item),"allocation");need(cJSON_AddItemToObject(root_.get(),key,item.get()),"allocation");item.release();
        }
        std::string bytes() {
            using namespace heating::graph_test;std::map<std::string,Json> fields;
            while(root_->child) {
                const std::string key=root_->child->string;
                Json item(cJSON_DetachItemFromObjectCaseSensitive(root_.get(),key.c_str()),cJSON_Delete);
                need(bool(item),"allocation");fields.emplace(key,std::move(item));
            }
            for(auto& field:fields) {
                need(cJSON_AddItemToObject(root_.get(),field.first.c_str(),field.second.get()),"allocation");
                field.second.release();
            }
            auto result=print(root_.get());auto checked=parse(result);(void)checked;return result;
        }
    private:
        heating::graph_test::Json root_;
    };
    template<class F>void guard(F&& action) {
        try{action();}
        catch(const heating::graph_test::Failure& e){
            // Invalid input is rejected WITHOUT changing admission/watermarks.
            // Allocation/hash/dependency failures disable this owner.
            if(std::strcmp(e.code,"allocation")==0||std::strcmp(e.code,"hash_fault")==0)fault();
        }catch(const std::exception&){fault();}
    }
    static uint32_t number(const cJSON* root,const char* key) {
        return static_cast<uint32_t>(heating::graph_test::integer(heating::graph_test::get(root,key),1,UINT32_MAX));
    }
    bool time(uint64_t now) {
        if((haveNow_&&now<lastNow_)||now>UINT64_MAX-30000){fault();return false;}
        haveNow_=true;lastNow_=now;return true;
    }
    void fault(){fault_=true;clearSession();core_.disconnected();}
    void clearSession() {
        session_.clear();clientNonce_.clear();lastOpen_.clear();grant_.clear();
        pendingNonce_.clear();issuedNonce_.clear();grantSequence_=capSequence_=0;
        leaseWasAlive_=false;
    }
    bool expired(uint64_t now)const {
        return !session_.empty()&&!core_.alive(now)&&(leaseWasAlive_||now>=sessionStart_+leaseMs);
    }
    std::string nonce() {
        auto value=nonce_();heating::graph_test::need(SessionAdmission::validId(value),"hash_fault");return value;
    }
    void newChallenge(uint64_t now) {challenge_=nonce();challengeUntil_=now+30000;}
    void restart(uint64_t now) {
        clearSession();core_.disconnected();
        if(epoch_==UINT32_MAX){fault();return;}
        ++epoch_;newChallenge(now);nextHello_=now;
    }
    Frame base(bool session)const {
        Frame frame;
        frame.number("api",2);frame.text("controller_id",controller_);frame.text("boot_id",boot_);
        frame.number("epoch",epoch_);frame.number("config_revision",core_.revision());
        frame.text("config_digest",core_.configDigest());frame.number("mapping_revision",core_.mappingRevision());
        frame.text("mapping_digest",core_.mappingBytes().empty()?"":hash_(core_.mappingBytes()));
        if(session) {
            frame.text("adapter_id",adapter_);frame.text("adapter_session_id",session_);
            frame.text("grant_id",grant_);frame.number("grant_sequence",grantSequence_);
        }
        return frame;
    }
    void send(const char* topic,Frame& frame){const auto bytes=frame.bytes();publish_(topic,bytes);}
    void hello() {
        auto frame=base(false);frame.text("challenge_id",challenge_);frame.text("mode","shadow_graph");
        frame.text("transport",transport);frame.text("profile",profile);frame.text("qualification_digest",anchor_);
        frame.number("lease_ms",leaseMs);frame.number("grant_ms",grantMs);frame.flag("storage_fault",faulted());
        send("fw/hello",frame);nextHello_=lastNow_+3000;
    }
    void open(const cJSON* root,std::string_view bytes,uint64_t now) {
        using namespace heating::graph_test;
        object(root,{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","client_nonce","challenge_id","transport"});
        literal(get(root,"transport"),transport,"unsupported_transport");
        need(integer(get(root,"api"),2,2)==2,"unsupported_schema");
        for(auto pair:{std::pair{"controller_id",&controller_},{"boot_id",&boot_},{"adapter_id",&adapter_}})
            literal(get(root,pair.first),pair.second->c_str(),"identity");
        need(number(root,"epoch")==epoch_,"identity");
        for(const char* key:{"adapter_session_id","client_nonce","challenge_id"})
            need(SessionAdmission::validId(str(get(root,key))),"identity");
        if(!session_.empty()) {
            if(bytes==lastOpen_)sessionStatus(); // Original grant, never rotate/renew.
            return;
        }
        need(now<challengeUntil_&&str(get(root,"challenge_id"))==challenge_,"identity");
        const auto proposed=str(get(root,"adapter_session_id"));
        const SessionIdentity identity{controller_,boot_,adapter_,proposed,epoch_,core_.revision()};
        need(core_.openSession(identity,leaseMs),"identity");
        session_=proposed;clientNonce_=str(get(root,"client_nonce"));
        lastOpen_=bytes;sessionStart_=now;rotate(now);newChallenge(now);sessionStatus();
    }
    void rotate(uint64_t now) {
        if(grantSequence_==UINT32_MAX){fault();return;}
        auto fresh=nonce();if(fresh==grant_){fault();return;}
        if(!core_.issueGrant(fresh,grantSequence_+1,now,grantMs)){fault();return;}
        grant_=std::move(fresh);++grantSequence_;nextGrant_=now+5000;
        issuedNonce_=std::move(pendingNonce_);pendingNonce_.clear();
    }
    void sessionStatus() {
        if(faulted()||session_.empty())return;
        auto frame=base(true);frame.text("client_nonce",clientNonce_);frame.number("grant_ms",grantMs);
        frame.text("transport",transport);frame.text("profile",profile);
        if(!issuedNonce_.empty())frame.text("grant_request_nonce",issuedNonce_);
        send("fw/session",frame);
    }
    Envelope envelope(const cJSON* root,const char* binding,StreamKind kind,std::string_view raw)const {
        using namespace heating::graph_test;
        need(number(root,"api")==2&&number(root,"epoch")==epoch_,"identity");
        need(integer(get(root,"config_revision"),0,UINT32_MAX)==core_.revision(),"revision_conflict");
        for(auto pair:{std::pair{"controller_id",&controller_},{"boot_id",&boot_},{"adapter_id",&adapter_},
            {"adapter_session_id",&session_},{"grant_id",&grant_}})
            literal(get(root,pair.first),pair.second->c_str(),"identity");
        need(number(root,"grant_sequence")==grantSequence_,"identity");
        literal(get(root,"binding_id"),binding,"identity");const auto hash=hash_(raw);need(hex(hash),"hash_fault");
        Envelope e;e.major=2;e.kind=kind;e.controller=controller_;e.boot=boot_;e.adapter=adapter_;e.session=session_;
        e.epoch=epoch_;e.revision=core_.revision();e.binding=binding;e.grant=grant_;e.grantSequence=grantSequence_;
        e.sequence=number(root,"sequence");
        for(size_t i=0;i<32;++i) {
            const auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
            e.payloadDigest[i]=static_cast<uint8_t>(16*digit(hash[2*i])+digit(hash[2*i+1]));
        }
        return e;
    }
    void capability() {
        if(!core_.alive(lastNow_)||capSequence_==UINT32_MAX)return;
        auto frame=base(true);frame.text("mode","shadow_graph");
        frame.flag("boiler_output_enabled",false);frame.flag("actuator_output_enabled",false);
        frame.raw("capabilities",R"(["heating.actuator.binary_valve.v1","heating.central_weather.v1","heating.emitter.floor.v1","heating.emitter_groups.v1","heating.graph_shadow.v1","schedule.utc.v1"])");
        frame.raw("limits",R"({"actuators":1,"config_bytes":4096,"groups":1,"rooms":1,"streams":7,"total_transitions":8,"transitions":8,"wire_bytes":8192})");
        auto value=frame.bytes();Frame wrapper;wrapper.number("api",2);wrapper.number("sequence",++capSequence_);
        wrapper.raw("capability",value);send("fw/graph_capability",wrapper);
    }
    void readback(uint32_t request) {
        auto frame=base(true);frame.number("request_sequence",request);
        frame.raw("config",core_.configBytes());frame.raw("mapping",core_.mappingBytes());
        frame.flag("boiler_output_enabled",false);frame.flag("actuator_output_enabled",false);
        send("fw/config_snapshot",frame);
    }
    std::string controller_,boot_,adapter_,anchor_;
    Hash hash_;Nonce nonce_;Publish publish_;GraphShadowConfiguration core_;
    std::string challenge_,session_,clientNonce_,lastOpen_,grant_,pendingNonce_,issuedNonce_;
    uint32_t epoch_=0,grantSequence_=0,capSequence_=0;
    uint64_t challengeUntil_=0,nextHello_=0,nextGrant_=0,sessionStart_=0,lastNow_=0;
    bool connected_=false,fault_=false,haveNow_=false,leaseWasAlive_=false;
};
}
