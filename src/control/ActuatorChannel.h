#pragma once
#include "ActuatorDispatch.h"

namespace heating::control {
// One binding on the existing serialized transport. No client, queue, retry or
// physical SOURCE selection. Product factories must supply current local facts.
class ActuatorChannel {
public:
    using Scope=ActuatorDispatch::Scope;
    using Facts=ActuatorDispatch::Facts;
    using Source=ActuatorDispatch::Source;
    using Clock=ActuatorDispatch::Clock;
    using Outcome=ActuatorDispatch::Outcome;
    // Copy/consume synchronously and enforce the absolute local deadline at
    // actual handoff. No retained publish, command queue or later retry.
    using Send=std::function<bool(std::string_view,std::string_view,uint64_t)>;
    ActuatorChannel(Scope scope,Source source={},Clock clock={},Send send={})
        :scope_(std::move(scope)),source_(std::move(source)),clock_(std::move(clock)),send_(std::move(send)),
         dispatch_(scope_,[this]{
                auto facts=source_();
                facts.leaseUntil=std::min(facts.leaseUntil,deadline_);
                return facts;
            },[this]{
                uint64_t now;
                if(!time(now))throw std::runtime_error("Actuator channel clock invalid");
                return now;
            },
            [this](std::string_view raw,uint64_t deadline){
                uint64_t now;
                const auto until=std::min(deadline,deadline_);
                if(!time(now)||now>=until){retire();return false;}
                return send_(commandTopic_,raw,until);
            }),requestTopic_("fw/actuator_grant_request/"+scope_.binding),
         commandTopic_("fw/actuator_command/"+scope_.binding),
         grantTopic_("ha/actuator_grant/"+scope_.binding) {
        if(!scope_.valid()||!source_||!clock_||!send_)retire();
    }
    ActuatorChannel(const ActuatorChannel&)=delete;
    ActuatorChannel& operator=(const ActuatorChannel&)=delete;
    bool retired()const{return retired_||dispatch_.retired();}
    std::string_view binding()const{return scope_.binding;}
    void retire(){retired_=true;pending_=false;ready_=false;dispatch_.retire();}
    // One request owns its original timestamp, sequence and narrowing deadline.
    // A new call never retransmits a pending or already accepted request.
    Outcome request() {
        if(!enter())return Outcome::refused;
        Operation operation(*this);
        uint64_t now;
        if(!sample(now)||pending_||ready_)return Outcome::refused;
        if(sequence_==UINT32_MAX||now>UINT64_MAX-5000){retire();return Outcome::refused;}
        started_=now;deadline_=std::min(lease_,now+5000);
        std::string raw;
        try {raw=encode(++sequence_);}catch(...){retire();return Outcome::refused;}
        if(!sample(now))return Outcome::refused;
        deadline_=std::min(deadline_,lease_);
        if(now>=deadline_)return Outcome::refused;
        // Mark before handoff: reentry cannot publish a second request.
        pending_=true;
        bool accepted=false;
        try {accepted=send_(requestTopic_,raw,deadline_);}catch(...){retire();return Outcome::outcome_unknown;}
        if(!accepted||!sample(now)||now>=deadline_){retire();return Outcome::outcome_unknown;}
        return Outcome::transport_accepted;
    }
    bool receive(std::string_view topic,std::string_view raw,bool retained=false) {
        if(topic!=grantTopic_)return false;
        if(retained||raw.size()>2048||!enter())return true;
        Operation operation(*this);
        uint64_t now;
        if(!sample(now)||!pending_||now>=deadline_)return true;
        try {
            const auto root=parseControlJson(raw);
            const auto sequence=root?cJSON_GetObjectItemCaseSensitive(root.get(),"request_sequence"):nullptr;
            if(!cJSON_IsNumber(sequence)||sequence->valuedouble!=sequence_)return true;
            ready_=dispatch_.accept(raw,started_,false);
        }catch(...){retire();}
        // Pending stays true until dispatch. Duplicate replies cannot renew time.
        return true;
    }
    Outcome dispatch(int target) {
        if(!enter())return Outcome::refused;
        Operation operation(*this);
        uint64_t now;
        if(!sample(now)||!ready_||now>=deadline_)return Outcome::refused;
        const auto result=dispatch_.dispatch(target);
        if(result==Outcome::transport_accepted&&(!sample(now)||now>=deadline_)) {
            retire();return Outcome::outcome_unknown;
        }
        if(result!=Outcome::refused){ready_=false;pending_=false;}
        if(result==Outcome::outcome_unknown||dispatch_.retired())retire();
        return result;
    }
    // Called by the existing loop, including while disconnected. No IO.
    void checkCurrent() {
        if(!enter())return;
        Operation operation(*this);
        uint64_t now;
        if(sample(now)&&pending_&&now>=deadline_){pending_=false;ready_=false;}
    }
private:
    struct Operation {
        ActuatorChannel& owner;
        explicit Operation(ActuatorChannel& value):owner(value){}
        ~Operation(){owner.busy_=false;if(owner.dispatch_.retired())owner.retire();}
    };
    bool enter(){if(retired())return false;if(busy_){retire();return false;}busy_=true;return true;}
    bool time(uint64_t& now) {
        try{now=clock_();}catch(...){retire();return false;}
        if(retired()||(haveClock_&&now<lastClock_)){retire();return false;}
        haveClock_=true;lastClock_=now;return true;
    }
    bool sample(uint64_t& now) {
        if(!time(now))return false;
        Facts facts;
        try{facts=source_();}catch(...){retire();return false;}
        if(!time(now))return false;
        if(!facts.authorized||!(facts.scope==scope_)||now>=facts.leaseUntil){retire();return false;}
        lease_=facts.leaseUntil;
        if(pending_||ready_)deadline_=std::min(deadline_,lease_);
        return true;
    }
    std::string encode(uint32_t sequence)const {
        ControlJson root(cJSON_CreateObject(),cJSON_Delete);
        if(!root)throw std::bad_alloc();
        auto text=[&](const char* k,const std::string& v){if(!cJSON_AddStringToObject(root.get(),k,v.c_str()))throw std::bad_alloc();};
        auto number=[&](const char* k,uint32_t v){if(!cJSON_AddNumberToObject(root.get(),k,v))throw std::bad_alloc();};
        text("adapter_id",scope_.adapter);text("adapter_session_id",scope_.session);number("api",1);
        text("binding_id",scope_.binding);text("boot_id",scope_.boot);text("command_kind","room_target");
        text("config_digest",scope_.digest);number("config_revision",scope_.revision);
        text("controller_id",scope_.controller);number("epoch",scope_.epoch);number("request_sequence",sequence);
        std::unique_ptr<char,decltype(&cJSON_free)> raw(cJSON_PrintUnformatted(root.get()),cJSON_free);
        if(!raw)throw std::bad_alloc();
        return raw.get();
    }
    const Scope scope_;
    Source source_;Clock clock_;Send send_;
    ActuatorDispatch dispatch_;
    const std::string requestTopic_,commandTopic_,grantTopic_;
    uint64_t started_=0,deadline_=0,lease_=0,lastClock_=0;
    uint32_t sequence_=0;
    bool retired_=false,busy_=false,pending_=false,ready_=false,haveClock_=false;
};
}
