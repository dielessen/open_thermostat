// Finite SOURCE/clock/transport peer; stdout is evidence, never a broker/device.
#include "control/ActuatorDispatch.h"
#include <iostream>
using heating::control::ActuatorDispatch;
int main(int argc,char** argv) {
    const std::string mode=argc==2?argv[1]:"normal";
    ActuatorDispatch::Scope scope{"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};
    uint64_t now=1000,deadline=0;int reads=0,handoffs=0;
    ActuatorDispatch::Facts facts{scope,16000,true};std::string frame;
    ActuatorDispatch* ptr=nullptr;
    ActuatorDispatch owner(scope,[&]{
        ++reads;
        if(reads==3&&mode=="source_delay")now=6000;
        if(reads==4&&mode=="lease_after_encoding")facts.leaseUntil=now;
        return facts;
    },[&]{return now;},[&](std::string_view raw,uint64_t budget){
        ++handoffs;frame=raw;deadline=budget;
        if(mode=="late_transport")now=6000;
        if(mode=="reentrant_transport")ptr->dispatch(2200);
        return mode!="transport_false";
    });ptr=&owner;
    std::string grant;if(!std::getline(std::cin,grant))return 2;
    const bool admitted=owner.accept(grant,1000);
    if(mode=="lease_lost")facts.leaseUntil=now;
    if(mode=="authority_lost")facts.authorized=false;
    if(mode=="clock_reversed")now=999;
    if(mode=="grant_expired")now=6000;
    const auto outcome=owner.dispatch(2100);
    const auto repeat=owner.dispatch(2200);
    using O=ActuatorDispatch::Outcome;
    const char* label=outcome==O::refused?"refused":outcome==O::transport_accepted?"transport_accepted":"outcome_unknown";
    heating::control::ControlJson root(cJSON_CreateObject(),cJSON_Delete);if(!root)return 3;
    if(!cJSON_AddBoolToObject(root.get(),"admitted",admitted)||!cJSON_AddStringToObject(root.get(),"outcome",label)
            ||!cJSON_AddBoolToObject(root.get(),"retired",owner.retired())||!cJSON_AddNumberToObject(root.get(),"handoffs",handoffs)
            ||!cJSON_AddNumberToObject(root.get(),"deadline",deadline)||!cJSON_AddStringToObject(root.get(),"raw",frame.c_str())
            ||!cJSON_AddBoolToObject(root.get(),"repeat_refused",repeat==O::refused))return 3;
    std::unique_ptr<char,decltype(&cJSON_free)> result(cJSON_PrintUnformatted(root.get()),cJSON_free);if(!result)return 3;
    std::cout<<result.get()<<'\n';return 0;
}
