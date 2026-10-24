#pragma once
#include "ActuatorIntent.h"

namespace heating::control {
// Prepared SOURCE/lease/transport owner. NOT selected by the normal factory.
// Clock and SOURCE are current LOCAL producers, never incoming broker fields.
// Send is the existing synchronous transport handoff, not a queue or device ACK.
// The caller uses its existing serialized task; re-entry detection is no mutex.
// SOURCE/clock callbacks must be bounded local reads, not network operations.
class ActuatorDispatch {
public:
    using Scope=ActuatorIntent::Scope;
    struct Facts {
        Scope scope;
        uint64_t leaseUntil=0;
        bool authorized=false;
    };
    using Source=std::function<Facts()>;
    using Clock=std::function<uint64_t()>;
    // The callback must consume/copy bytes synchronously, check the absolute
    // LOCAL deadline at actual handoff and return transport acceptance only.
    // It must not retain the view or queue/retry an action after this call.
    using Send=std::function<bool(std::string_view,uint64_t)>;
    enum class Outcome { refused, transport_accepted, outcome_unknown };

    explicit ActuatorDispatch(Scope scope,Source source={},Clock clock={},Send send={})
        :scope_(std::move(scope)),source_(std::move(source)),clock_(std::move(clock)),send_(std::move(send)),
         intent_(scope_,[this]{return permitted_&&!retired_;}) {
        if(!scope_.valid()||!source_||!clock_||!send_)retire();
    }
    ActuatorDispatch(const ActuatorDispatch&)=delete;
    ActuatorDispatch& operator=(const ActuatorDispatch&)=delete;
    bool retired()const{return retired_;}
    void retire(){retired_=true;permitted_=false;intent_.retire();}

    bool accept(std::string_view raw,uint64_t requestStarted,bool retained=false) {
        if(retained||raw.size()>2048||!enter())return false;
        Operation operation(*this);
        Facts facts;uint64_t now;
        if(!sample(facts,now)||!intent_.accept(raw,facts.scope,now,requestStarted,facts.leaseUntil))return false;
        // Time spent in source validation belongs to the SAME original budget.
        // Duplicate admission cannot renew the grant deadline or consumption.
        return sample(facts,now)&&intent_.accept(raw,facts.scope,now,requestStarted,facts.leaseUntil);
    }
    Outcome dispatch(int target) {
        if(!enter())return Outcome::refused;
        Operation operation(*this);
        Facts facts;uint64_t now;
        if(!sample(facts,now))return Outcome::refused;
        const auto raw=intent_.command(target,facts.scope,now,facts.leaseUntil);
        if(raw.empty())return Outcome::refused;
        if(!sample(facts,now)||!intent_.dispatchCurrent(facts.scope,now,facts.leaseUntil))return Outcome::refused;
        const auto deadline=std::min(intent_.deadline_,facts.leaseUntil);
        bool accepted=false;
        try {accepted=send_(raw,deadline);} catch(...) {retire();return Outcome::outcome_unknown;}
        // Even false/exception may follow partial transport IO. Never guess
        // that nothing happened, retry, extend a lease or declare valve ready.
        if(!accepted){retire();return Outcome::outcome_unknown;}
        if(!sample(facts,now)||!intent_.dispatchCurrent(facts.scope,now,facts.leaseUntil)) {
            retire();return Outcome::outcome_unknown;
        }
        return Outcome::transport_accepted;
    }
private:
    struct Operation {
        ActuatorDispatch& owner;
        explicit Operation(ActuatorDispatch& value):owner(value){}
        ~Operation(){
            if(owner.intent_.retired())owner.retire();
            owner.permitted_=false;owner.busy_=false;
        }
    };
    bool enter() {
        if(retired_)return false;
        if(busy_){retire();return false;}
        busy_=true;return true;
    }
    bool time(uint64_t& now) {
        if(retired_)return false;
        try {now=clock_();} catch(...) {retire();return false;}
        if(retired_||(haveClock_&&now<lastClock_)){retire();return false;}
        lastClock_=now;haveClock_=true;return true;
    }
    bool sample(Facts& facts,uint64_t& now) {
        if(!time(now))return false;
        try {facts=source_();} catch(...) {retire();return false;}
        // Independent trusted clock AFTER the possibly delayed source getter.
        if(!time(now))return false;
        if(!facts.scope.valid()||!(facts.scope==scope_)||!facts.authorized||now>=facts.leaseUntil) {
            retire();return false;
        }
        permitted_=true;return true;
    }
    const Scope scope_;
    Source source_;
    Clock clock_;
    Send send_;
    bool retired_=false,busy_=false,permitted_=false,haveClock_=false;
    uint64_t lastClock_=0;
    ActuatorIntent intent_;
};
}
