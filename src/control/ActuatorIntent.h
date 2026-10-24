#pragma once
#include "BoundedJson.h"
#include "ActuatorScope.h"
#include <algorithm>
#include <cstdint>
#include <functional>
#include <utility>
#include <stdexcept>

namespace heating::control {
// Prepared FW half of HA ActuatorReceiver. No publisher, device IO or product
// selection. Scope/authority are LOCAL current-owner facts, never broker flags.
// HA retains the authoritative original grant deadline on its own clock.
class ActuatorIntent {
public:
    using Scope=ActuatorScope;
    using Authority=std::function<bool()>;
    explicit ActuatorIntent(Scope scope,Authority authority={})
        :scope_(std::move(scope)),authority_(std::move(authority)) { retired_=!scope_.valid(); }
    ActuatorIntent(const ActuatorIntent&)=delete;
    ActuatorIntent& operator=(const ActuatorIntent&)=delete;
    void retire(){retired_=true;grant_.clear();}
    bool retired()const{return retired_;}
    // requestStarted and leaseUntil are original LOCAL monotonic deadlines.
    // Grants use the existing canonical v1 transport encoding.
    // No wire field can extend either. One consumed grant emits at most once;
    // duplicate delivery cannot reset its deadline or command sequence.
    bool accept(std::string_view raw,const Scope& current,uint64_t now,
                uint64_t requestStarted,uint64_t leaseUntil,bool retained=false) {
        if(!admitted(current,now))return false;
        if(leaseUntil<=now){retire();return false;}
        if(retained||raw.size()>2048||requestStarted>now||now-requestStarted>=5000
                ||requestStarted>UINT64_MAX-5000)return false;
        try {
            auto root=parseControlJson(raw);
            if(!root||!cJSON_IsObject(root.get())||cJSON_GetArraySize(root.get())!=13
                    ||print(root.get())!=raw||!match(root.get()))return false;
            const auto nonce=textValue(root.get(),"grant_id");
            if(!Scope::validId(nonce)||!numberValue(root.get(),"grant_ms",5000,5000))return false;
            const auto field=cJSON_GetObjectItemCaseSensitive(root.get(),"grant_sequence");
            if(!numberValue(root.get(),"grant_sequence",1,UINT32_MAX))return false;
            const auto sequence=static_cast<uint32_t>(field->valuedouble);
            if(sequence<grantSequence_)return false;
            if(sequence==grantSequence_) {
                // Exact duplicate is inert, including a changed local request
                // or lease deadline. A changed nonce at the same counter fails.
                if(nonce!=grant_)return false;
                deadline_=std::min(deadline_,leaseUntil);
                return !consumed_&&now<deadline_;
            }
            if(nonce==grant_)return false;
            const auto deadline=std::min(requestStarted+5000,leaseUntil);
            if(now>=deadline)return false;
            grant_=nonce;grantSequence_=sequence;deadline_=deadline;consumed_=false;
            return true;
        } catch(...) {retire();}
        return false;
    }
    // Returned bytes are a proposed intent only. No ACK/readiness/lease is
    // inferred. Caller must use its existing serialized reviewed transport.
    std::string command(int target,const Scope& current,uint64_t now,uint64_t leaseUntil) {
        if(!admitted(current,now))return {};
        if(now>=leaseUntil){retire();return {};}
        deadline_=std::min(deadline_,leaseUntil);
        if(grant_.empty()||consumed_||now>=deadline_||target<500||target>3500)return {};
        if(sequence_==UINT32_MAX){retire();return {};}
        try {
            ControlJson root(cJSON_CreateObject(),cJSON_Delete);need(bool(root));
            auto text=[&](const char* k,const std::string& v){need(cJSON_AddStringToObject(root.get(),k,v.c_str()));};
            auto number=[&](const char* k,uint32_t v){need(cJSON_AddNumberToObject(root.get(),k,v));};
            text("adapter_id",scope_.adapter);text("adapter_session_id",scope_.session);number("api",1);
            text("binding_id",scope_.binding);text("boot_id",scope_.boot);text("command_kind","room_target");
            text("config_digest",scope_.digest);number("config_revision",scope_.revision);
            text("controller_id",scope_.controller);number("epoch",scope_.epoch);
            text("grant_id",grant_);number("grant_sequence",grantSequence_);
            number("sequence",sequence_+1);number("target_centi_c",static_cast<uint32_t>(target));
            auto bytes=print(root.get());need(bytes.size()<=2048);
            // Allocation/encoding is complete before consuming a command. No
            // automatic resend after the caller accepts these bytes.
            ++sequence_;consumed_=true;return bytes;
        } catch(...) {retire();return {};}
    }
private:
    friend class ActuatorDispatch;
    // Validation of THIS owner's already prepared frame, not resend permission.
    // Only the serialized transport owner uses this after sampling fresh facts.
    bool dispatchCurrent(const Scope& current,uint64_t now,uint64_t leaseUntil) {
        if(!admitted(current,now))return false;
        if(now>=leaseUntil){retire();return false;}
        deadline_=std::min(deadline_,leaseUntil);
        return !grant_.empty()&&consumed_&&sequence_&&now<deadline_;
    }
    bool admitted(const Scope& current,uint64_t now) {
        if(retired_)return false;
        if(checking_){retire();return false;}
        if(!current.valid()||!(current==scope_)||(haveClock_&&now<lastClock_)) {
            retire();return false;
        }
        haveClock_=true;lastClock_=now;
        checking_=true;
        bool allowed=false;
        try {allowed=authority_&&authority_();} catch(...) {retire();}
        checking_=false;
        if(!allowed||retired_||!current.valid()||!(current==scope_)){retire();return false;}
        return true;
    }
    static void need(bool ok){if(!ok)throw std::bad_alloc();}
    static std::string print(const cJSON* root) {
        std::unique_ptr<char,decltype(&cJSON_free)> text(cJSON_PrintUnformatted(root),cJSON_free);
        need(bool(text));return text.get();
    }
    static std::string textValue(const cJSON* root,const char* key) {
        const auto value=cJSON_GetObjectItemCaseSensitive(root,key);
        return cJSON_IsString(value)&&value->valuestring?value->valuestring:"";
    }
    static bool numberValue(const cJSON* root,const char* key,uint32_t low,uint32_t high) {
        const auto value=cJSON_GetObjectItemCaseSensitive(root,key);
        return cJSON_IsNumber(value)&&std::isfinite(value->valuedouble)
            &&value->valuedouble>=low&&value->valuedouble<=high
            &&std::floor(value->valuedouble)==value->valuedouble;
    }
    bool match(const cJSON* root)const {
        return numberValue(root,"api",1,1)&&numberValue(root,"epoch",scope_.epoch,scope_.epoch)
            &&numberValue(root,"config_revision",scope_.revision,scope_.revision)
            &&textValue(root,"controller_id")==scope_.controller&&textValue(root,"boot_id")==scope_.boot
            &&textValue(root,"adapter_id")==scope_.adapter&&textValue(root,"adapter_session_id")==scope_.session
            &&textValue(root,"config_digest")==scope_.digest&&textValue(root,"binding_id")==scope_.binding
            &&textValue(root,"command_kind")=="room_target";
    }
    const Scope scope_;
    Authority authority_;
    bool retired_=false,haveClock_=false,consumed_=true,checking_=false;
    uint64_t lastClock_=0,deadline_=0;
    uint32_t grantSequence_=0,sequence_=0;
    std::string grant_;
};
}
