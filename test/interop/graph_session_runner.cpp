// Finite stdin/EOF actual protocol owner. No broker/service/device IO.
#include "control/GraphSessionOwner.h"
#include "ControlTestHash.h"
#include <iostream>
using namespace heating::control;
namespace gt=heating::graph_test;
struct Store:ControlStore {
    std::string data;size_t writes=0;bool ok=true,commit=false;
    bool load(std::string& out)override{out=data;return true;}
    bool save(std::string_view bytes)override{++writes;if(ok||commit)data=bytes;return ok;}
};
int main() {
    Store store;std::unique_ptr<GraphSessionOwner> owner;
    std::string controller,boot,adapter,anchor,line;uint32_t nonce=0;
    std::vector<std::pair<std::string,std::string>> frames;
    auto construct=[&] {
        owner=std::make_unique<GraphSessionOwner>(controller,boot,adapter,anchor,store,controlTestHash,
            [&]{return "test_random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);});
    };
    while(std::getline(std::cin,line)) {
        if(line.size()>20000)return 2;
        gt::Json root(cJSON_Parse(line.c_str()),cJSON_Delete);if(!root)return 3;
        auto text=[&](const char* key){return gt::str(gt::get(root.get(),key));};
        const auto now=static_cast<uint64_t>(gt::integer(gt::get(root.get(),"now"),0,UINT32_MAX));
        const auto op=text("op");frames.clear();
        if(op=="initialize") {
            controller=text("controller");boot=text("boot");adapter=text("owner");anchor=text("anchor");
            store.data=text("stored");construct();
        } else if(!owner)return 4;
        else if(op=="connect")owner->connected(now);
        else if(op=="disconnect")owner->disconnected();
        else if(op=="receive")owner->receive(text("topic"),text("raw"),now);
        else if(op=="tick")owner->tick(now);
        else if(op=="ambiguous"){store.ok=false;store.commit=true;}
        else if(op=="reboot"){boot=text("boot");store.ok=true;store.commit=false;construct();}
        else if(op!="status"&&op!="durable_readback")return 5;
        gt::Json result(cJSON_CreateObject(),cJSON_Delete);auto messages=cJSON_AddArrayToObject(result.get(),"frames");
        for(auto& frame:frames) {
            auto item=cJSON_CreateObject();cJSON_AddItemToArray(messages,item);
            cJSON_AddStringToObject(item,"topic",frame.first.c_str());
            cJSON_AddStringToObject(item,"raw",frame.second.c_str());
        }
        if(op=="durable_readback")cJSON_AddStringToObject(result.get(),"stored",store.data.c_str());
        cJSON_AddBoolToObject(result.get(),"fault",owner->faulted());
        cJSON_AddNumberToObject(result.get(),"revision",owner->configuration().revision());
        cJSON_AddNumberToObject(result.get(),"writes",store.writes);
        cJSON_AddNumberToObject(result.get(),"store_bytes",store.data.size());
        cJSON_AddNumberToObject(result.get(),"object_bytes",sizeof(GraphSessionOwner));
        cJSON_AddNumberToObject(result.get(),"grant_deadline_ms",owner->configuration().grantDeadline(now));
        cJSON_AddStringToObject(result.get(),"status",owner->configuration().status().c_str());
        cJSON_AddBoolToObject(result.get(),"boiler_output_enabled",owner->configuration().boilerOutputEnabled());
        cJSON_AddBoolToObject(result.get(),"actuator_output_enabled",owner->configuration().actuatorOutputEnabled());
        std::cout<<gt::print(result.get())<<std::endl;
    }
}
