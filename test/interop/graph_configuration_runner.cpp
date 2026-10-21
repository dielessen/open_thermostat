// Finite stdin/EOF test runner for real firmware core, NOT a runtime service.
#include "control/GraphShadowConfiguration.h"
#include "ControlTestHash.h"
#include <iostream>
using namespace heating::control;
namespace gt=heating::graph_test;
struct Store:ControlStore {
    std::string data;size_t writes=0;bool ok=true,commit=false;
    bool load(std::string& out)override{out=data;return true;}
    bool save(std::string_view bytes)override{++writes;if(ok||commit)data=bytes;return ok;}
};
int main(){
    Store store;std::unique_ptr<GraphShadowConfiguration> core;
    std::string controller,boot,owner,anchor,session,grant;uint32_t epoch=0,grantSequence=0;
    std::string line;
    while(std::getline(std::cin,line)){
        if(line.size()>20000)return 2;
        gt::Json root(cJSON_Parse(line.c_str()),cJSON_Delete);if(!root)return 3;
        auto text=[&](const char* k){return gt::str(gt::get(root.get(),k));};
        auto number=[&](const char* k){return static_cast<uint64_t>(gt::integer(gt::get(root.get(),k),0,UINT32_MAX));};
        bool accepted=false;
        try{
            auto op=text("op");
            if(op=="initialize"){
                controller=text("controller");boot=text("boot");owner=text("owner");anchor=text("anchor");
                core=std::make_unique<GraphShadowConfiguration>(controller,boot,owner,anchor,store,controlTestHash);
                accepted=core->initialize();
            }else if(op=="reboot"&&core){
                boot=text("boot");store.ok=true;store.commit=false;
                core=std::make_unique<GraphShadowConfiguration>(controller,boot,owner,anchor,store,controlTestHash);
                accepted=core->initialize();
            }else if(op=="admit"&&core){
                session=text("session");epoch=static_cast<uint32_t>(number("epoch"));grant=text("grant");
                grantSequence=static_cast<uint32_t>(number("grant_sequence"));auto now=number("now");
                SessionIdentity id{controller,boot,owner,session,epoch,core->revision()};
                accepted=core->openSession(id)&&core->issueGrant(grant,grantSequence,now,10000);
                if(accepted){Envelope e;e.major=2;e.kind=StreamKind::heartbeat;e.controller=controller;e.boot=boot;
                    e.adapter=owner;e.session=session;e.epoch=epoch;e.revision=core->revision();e.binding="adapter";
                    e.grant=grant;e.grantSequence=grantSequence;e.sequence=1;e.payloadDigest[0]=1;
                    accepted=core->heartbeat(e,now).code==AdmissionCode::accepted;}
            }else if(op=="apply"&&core){
                accepted=core->apply(text("raw"),text("mapping"),number("now"))=="graph_committed_no_admission";
            }else if(op=="apply_tuple"&&core){
                accepted=core->applyTuple(text("raw"),number("now"))=="graph_committed_no_admission";
            }else if(op=="ambiguous"&&core){store.ok=false;store.commit=true;accepted=true;}
            else if(op=="disconnect"&&core){core->disconnected();accepted=true;}
            else if(op!="status")return 4;
        }catch(const gt::Failure&){return 5;}
        if(!core)return 6;
        gt::Json reply(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddBoolToObject(reply.get(),"accepted",accepted);
        cJSON_AddStringToObject(reply.get(),"status",core->status().c_str());
        cJSON_AddNumberToObject(reply.get(),"revision",core->revision());
        cJSON_AddNumberToObject(reply.get(),"mapping_revision",core->mappingRevision());
        cJSON_AddStringToObject(reply.get(),"config_digest",core->configDigest().c_str());
        cJSON_AddBoolToObject(reply.get(),"fault",core->faulted());
        cJSON_AddNumberToObject(reply.get(),"store_bytes",store.data.size());
        cJSON_AddNumberToObject(reply.get(),"writes",store.writes);
        cJSON_AddNumberToObject(reply.get(),"object_bytes",sizeof(GraphShadowConfiguration));
        cJSON_AddBoolToObject(reply.get(),"boiler_output_enabled",core->boilerOutputEnabled());
        cJSON_AddBoolToObject(reply.get(),"actuator_output_enabled",core->actuatorOutputEnabled());
        cJSON_AddItemToObject(reply.get(),"config",core->configBytes().empty()?cJSON_CreateNull():cJSON_Parse(core->configBytes().c_str()));
        cJSON_AddItemToObject(reply.get(),"mapping",core->mappingBytes().empty()?cJSON_CreateNull():cJSON_Parse(core->mappingBytes().c_str()));
        std::cout<<gt::print(reply.get())<<std::endl;
    }
}
