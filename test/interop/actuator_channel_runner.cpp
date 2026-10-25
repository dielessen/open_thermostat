// Finite stdin/stdout peer. Imported scope and authorization are TEST FIXTURES.
// No production factory, broker, hardware or retained network credentials.
#include "control/ActuatorChannel.h"
#include <iostream>
using heating::control::ActuatorChannel;
int main(int argc,char** argv) {
    const std::string mode=argc==2?argv[1]:"normal";
    std::string line;
    if(!std::getline(std::cin,line))return 2;
    auto root=heating::control::parseControlJson(line);
    if(!root)return 3;
    auto text=[&](const char* key){auto v=cJSON_GetObjectItemCaseSensitive(root.get(),key);return cJSON_IsString(v)?std::string(v->valuestring):std::string{};};
    auto number=[&](const char* key)->uint32_t{auto v=cJSON_GetObjectItemCaseSensitive(root.get(),key);return cJSON_IsNumber(v)&&v->valuedouble>=1&&v->valuedouble<=UINT32_MAX&&std::floor(v->valuedouble)==v->valuedouble?static_cast<uint32_t>(v->valuedouble):0;};
    ActuatorChannel::Scope scope{text("controller_id"),text("boot_id"),text("adapter_id"),text("adapter_session_id"),text("config_digest"),text("binding_id"),number("epoch"),number("config_revision")};
    if(!scope.valid())return 4;
    uint64_t now=1000;int handoffs=0;
    ActuatorChannel::Facts facts{scope,16000,true};
    std::string command;uint64_t deadline=0;
    ActuatorChannel owner(scope,[&]{return facts;},[&]{return now;},[&](std::string_view topic,std::string_view raw,uint64_t until){
        ++handoffs;deadline=until;
        if(handoffs==1)std::cout<<raw<<std::endl;
        else{command=raw;if(topic!="fw/actuator_command/"+scope.binding)return false;}
        return true;
    });
    if(owner.request()!=ActuatorChannel::Outcome::transport_accepted)return 5;
    if(!std::getline(std::cin,line))return 6;
    if(mode=="expired")now=6000;
    if(mode=="offline")facts.authorized=false;
    if(mode=="wrong_request") {
        auto grant=heating::control::parseControlJson(line);
        if(!grant)return 7;
        cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(grant.get(),"request_sequence"),2);
        std::unique_ptr<char,decltype(&cJSON_free)> raw(cJSON_PrintUnformatted(grant.get()),cJSON_free);
        if(!raw)return 8;
        line=raw.get();
    }
    owner.receive("ha/actuator_grant/"+scope.binding,line,mode=="retained");
    const auto outcome=owner.dispatch(2100);
    if(owner.dispatch(2200)!=ActuatorChannel::Outcome::refused)return 9;
    heating::control::ControlJson result(cJSON_CreateObject(),cJSON_Delete);
    if(!result||!cJSON_AddStringToObject(result.get(),"command",command.c_str())
        ||!cJSON_AddNumberToObject(result.get(),"handoffs",handoffs)||!cJSON_AddNumberToObject(result.get(),"deadline",deadline)
        ||!cJSON_AddBoolToObject(result.get(),"accepted",outcome==ActuatorChannel::Outcome::transport_accepted)
        ||!cJSON_AddBoolToObject(result.get(),"retired",owner.retired()))return 10;
    std::unique_ptr<char,decltype(&cJSON_free)> output(cJSON_PrintUnformatted(result.get()),cJSON_free);
    if(!output)return 11;
    std::cout<<output.get()<<std::endl;
}
