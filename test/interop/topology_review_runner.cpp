// Finite stdin/EOF SOURCE review fixture; never a runtime transport.
#include "control/GraphTopologyReview.h"
#include "ControlTestHash.h"
#include <iostream>
namespace gr=heating::graph_review;
namespace gt=heating::graph_test;
int main() {
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>20000)return 2;
        gt::Json f(cJSON_Parse(line.c_str()),cJSON_Delete);if(!f)return 3;
        try {
            const auto cx=gt::get(f.get(),"context");
            auto text=[cx](const char* k){return gt::str(gt::get(cx,k));};
            auto num=[cx](const char* k){return uint32_t(gt::integer(gt::get(cx,k),0,UINT32_MAX));};
            gr::Context ctx{text("controller_id"),text("boot_id"),text("adapter_session_id"),text("plan_digest"),
                num("epoch"),num("config_revision"),num("registry_revision"),num("source_revision")};
            const auto raw=gt::str(gt::get(f.get(),"raw"));
            auto result=gr::read(raw,ctx,controlTestHash);
            gt::Json reply(cJSON_CreateObject(),cJSON_Delete);
            cJSON_AddStringToObject(reply.get(),"code",result.code);
            cJSON_AddStringToObject(reply.get(),"readback",std::string(result.code)=="source_topology_review_only"?raw.c_str():"");
            cJSON_AddNumberToObject(reply.get(),"review_bytes",sizeof(gr::Review));
            cJSON_AddNumberToObject(reply.get(),"room_bytes",sizeof(gr::Room));
            cJSON_AddNumberToObject(reply.get(),"legacy_candidate_bytes",sizeof(gt::GraphShadowCandidate));
            cJSON_AddBoolToObject(reply.get(),"boiler_output_enabled",result.review.boilerOutputEnabled);
            cJSON_AddBoolToObject(reply.get(),"actuator_output_enabled",result.review.actuatorOutputEnabled);
            cJSON_AddBoolToObject(reply.get(),"admission",result.review.admission);
            cJSON_AddBoolToObject(reply.get(),"applied",result.review.applied);
            auto rows=cJSON_AddArrayToObject(reply.get(),"rooms");
            if(std::string(result.code)=="source_topology_review_only")for(const auto& r:result.review.rooms) {
                auto row=cJSON_CreateObject();cJSON_AddItemToArray(rows,row);
                cJSON_AddStringToObject(row,"zone_id",r.zone.data());
                cJSON_AddStringToObject(row,"emitter",r.floor?"floor":"radiator");
                cJSON_AddStringToObject(row,"sensor_resource",r.sensorResource.data());
                cJSON_AddStringToObject(row,"output_resource",r.outputResource.data());
                cJSON_AddNumberToObject(row,"base_centi_c",r.base);
            }
            std::cout<<gt::print(reply.get())<<std::endl;
        }catch(...) {return 4;}
    }
}
