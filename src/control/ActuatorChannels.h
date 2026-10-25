#pragma once
#include "ActuatorChannel.h"
#include <optional>
#include <vector>

namespace heating::control {
// Optional inventory owned by the existing serialized transport. No IO client,
// worker or queue. Callback reentry fails closed; it never mutates live iteration.
class ActuatorChannels {
public:
    using Factory=std::function<ActuatorChannel::Source(const ActuatorSessionContext&)>;
    using Context=std::function<std::optional<ActuatorSessionContext>(std::string_view,uint64_t)>;
    using Available=std::function<bool()>;
    ActuatorChannels(Factory factory,Context context,Available available,
                     ActuatorChannel::Clock clock,ActuatorChannel::Send send)
        :factory_(std::move(factory)),context_(std::move(context)),available_(std::move(available)),
         clock_(std::move(clock)),send_(std::move(send)) {
        if(!factory_||!context_||!available_||!clock_||!send_)retire();
    }
    ActuatorChannels(const ActuatorChannels&)=delete;
    ActuatorChannels& operator=(const ActuatorChannels&)=delete;
    bool retired()const{return retired_;}
    size_t size()const{return channels_.size();}
    // The existing socket writer uses this immediately at actual nonblocking
    // handoff, sharing every clock observation with all channel owners.
    bool beforeHandoff(uint64_t deadline) {
        // This entry is also used inside the send callback, so the inventory's
        // general operation guard cannot be acquired here. Fence this boundary
        // independently: availability/clock callbacks must not recurse into it.
        if(checkingHandoff_){retire();return false;}
        checkingHandoff_=true;
        struct Exit {bool& checking;~Exit(){checking=false;}} exit{checkingHandoff_};
        try{return usable()&&readClock()<deadline;}
        catch(...){retire();return false;}
    }
    void retire(){retired_=true;for(auto& channel:channels_)channel->retire();}
    ActuatorChannel* get(std::string_view binding) {
        if(!enter())return nullptr;
        Operation operation(*this);
        try {
            if(!usable())return nullptr;
            for(auto& channel:channels_)if(channel->binding()==binding)return channel.get();
            if(channels_.size()>=8)return nullptr;
            const auto context=current(binding);
            if(!context||!context->scope.valid()||context->scope.binding!=binding)return nullptr;
            ActuatorChannel::Source qualified;
            {Callback callback(*this);qualified=factory_(*context);}
            if(!qualified||!usable()){retire();return nullptr;}
            const auto after=current(binding);
            if(!usable()||!after||!(after->scope==context->scope)){retire();return nullptr;}
            // Revalidate admission after every caller-supplied factory callback.
            if(channels_.size()>=8)return nullptr;
            for(auto& channel:channels_)if(channel->binding()==binding){retire();return nullptr;}
            const auto scope=context->scope;
            auto source=[this,scope,qualified=std::move(qualified)] {
                if(inCallback_){retire();return ActuatorChannel::Facts{};}
                Callback callback(*this);
                if(!usable())return ActuatorChannel::Facts{};
                const auto before=current(scope.binding);
                if(!before||!(before->scope==scope)){retire();return ActuatorChannel::Facts{};}
                auto facts=qualified();
                if(!usable())return ActuatorChannel::Facts{};
                const auto after=current(scope.binding);
                if(!after||!(after->scope==scope)){retire();return ActuatorChannel::Facts{};}
                facts.leaseUntil=std::min(facts.leaseUntil,std::min(before->validUntil(),after->validUntil()));
                return facts; // Exact scope and authority still come from qualified SOURCE.
            };
            auto send=[this](std::string_view topic,std::string_view raw,uint64_t deadline) {
                if(inCallback_){retire();return false;}
                Callback callback(*this);
                if(!usable()||readClock()>=deadline)return false;
                bool accepted=false;
                try{accepted=send_(topic,raw,deadline);}catch(...){retire();throw;}
                if(!accepted){retire();return false;}
                return usable(); // An observed outage retires all owners sharing this transport.
            };
            auto channel=std::make_unique<ActuatorChannel>(scope,std::move(source),[this]{return readClock();},std::move(send));
            auto* result=channel.get();channels_.push_back(std::move(channel));return result;
        }catch(...){retire();return nullptr;}
    }
    bool receive(std::string_view topic,std::string_view raw,bool retained=false) {
        if(!enter())return false;
        Operation operation(*this);
        for(auto& channel:channels_)if(channel->receive(topic,raw,retained))return true;
        return false;
    }
    void checkCurrent() {
        if(!enter())return;
        Operation operation(*this);
        if(!usable())return;
        for(auto& channel:channels_)channel->checkCurrent();
    }
private:
    struct Operation {
        ActuatorChannels& owner;
        explicit Operation(ActuatorChannels& value):owner(value){}
        ~Operation(){owner.busy_=false;}
    };
    struct Callback {
        ActuatorChannels& owner;bool previous;
        explicit Callback(ActuatorChannels& value):owner(value),previous(value.inCallback_){owner.inCallback_=true;}
        ~Callback(){owner.inCallback_=previous;}
    };
    uint64_t readClock() {
        if(retired_)throw std::runtime_error("Actuator transport retired");
        if(readingClock_){retire();throw std::runtime_error("Actuator transport clock reentry");}
        readingClock_=true;
        struct Exit {bool& reading;~Exit(){reading=false;}} exit{readingClock_};
        Callback callback(*this);
        uint64_t now;
        try{now=clock_();}catch(...){retire();throw;}
        if(retired_||(haveClock_&&now<lastClock_)) {
            retire();throw std::runtime_error("Actuator transport clock invalid");
        }
        haveClock_=true;lastClock_=now;return now;
    }
    std::optional<ActuatorSessionContext> current(std::string_view binding) {
        const auto now=readClock();
        std::optional<ActuatorSessionContext> context;
        {Callback callback(*this);context=context_(binding,now);}
        readClock(); // Include callback time and retirement before any next callback/commit.
        if(!usable())return std::nullopt;
        return context;
    }
    bool enter(){if(retired_)return false;if(busy_||inCallback_){retire();return false;}busy_=true;return true;}
    bool usable() {
        if(retired_)return false;
        if(checkingAvailability_){retire();return false;}
        checkingAvailability_=true;
        struct Exit {bool& checking;~Exit(){checking=false;}} exit{checkingAvailability_};
        bool available=false;
        try{Callback callback(*this);available=available_();}catch(...){retire();return false;}
        if(!available||retired_){retire();return false;}
        return true;
    }
    Factory factory_;Context context_;Available available_;
    ActuatorChannel::Clock clock_;ActuatorChannel::Send send_;
    std::vector<std::unique_ptr<ActuatorChannel>> channels_;
    bool retired_=false,busy_=false,inCallback_=false,haveClock_=false,checkingHandoff_=false,readingClock_=false,checkingAvailability_=false;
    uint64_t lastClock_=0;
};
}
