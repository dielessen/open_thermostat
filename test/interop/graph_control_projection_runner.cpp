// Finite SOURCE-fixture factory probe, not wire/GUI profile provisioning.
#include "control/GraphControlStoreView.h"
#include "control/ShadowController.h"
#include "ControlTestHash.h"
#include <iostream>
namespace gt=heating::graph_test;
using namespace heating::control;
struct ProbeStore:ControlStore {
    std::string data;unsigned reads=0,writes=0;
    bool load(std::string& out)override{++reads;out=data;return true;}
    bool save(std::string_view)override{++writes;return false;}
};
int main() {
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>16384)return 2;
        gt::Json input(cJSON_Parse(line.c_str()),cJSON_Delete);if(!input)return 3;
        // Outer test harness transports escaped durable bytes, not API2 wire.
        // The actual view still validates the inner record with the strict core.
        auto text=[&](const cJSON* o,const char* k){return gt::str(gt::get(o,k));};
        const auto source=gt::get(input.get(),"source");
        ProbeStore backing;backing.data=text(input.get(),"stored");const auto original=backing.data;
        GraphControlHandoffSource pin{text(source,"controller_id"),text(source,"adapter_id"),
            text(source,"qualification_digest"),text(source,"config_digest"),text(source,"mapping_digest"),text(source,"expected_profile_digest"),
            static_cast<uint32_t>(gt::integer(gt::get(source,"revision"),1,UINT32_MAX)),
            static_cast<uint32_t>(gt::integer(gt::get(source,"mapping_revision"),1,UINT32_MAX))};
        SeasonalControllerSource policy;policy.controllerId=pin.controllerId;policy.profileDigest=text(source,"profile_digest");
        policy.configDigest=text(source,"control_digest");policy.count=1;policy.maximumSafetyAgeMs=2000;
        auto& z=policy.zones[0];z.zoneId=text(source,"zone_id");z.sensorId=text(source,"sensor_id");z.actuatorId=text(source,"actuator_id");
        z.minimumTargetCentiC=gt::integer(gt::get(source,"minimum"),500,3500);
        z.maximumTargetCentiC=gt::integer(gt::get(source,"maximum"),500,3500);
        z.seasonal.enabled=z.seasonal.installationQualified=true; // Declared synthetic SOURCE fixture ONLY.
        z.seasonal.maximumSensorAgeMs=120000;z.seasonal.maximumStepGapMs=300000;
        GraphControlStoreView view("e32_test","test_owner",backing,controlTestHash,pin,policy);
        unsigned nonce=0;std::string state;
        ShadowController controller("e32_test","projection_boot","test_owner",view,controlTestHash,
            [&]{return "probe_nonce_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){if(topic=="fw/state/zones")state=bytes;},ShadowController::Metrics{},
            &policy,[]{return SeasonalSafetySnapshot{};});
        controller.connected(1000);controller.tick(1000,1792368000,true);
        auto result=objectJson();
        cJSON_AddBoolToObject(result.get(),"fault",controller.faulted());
        cJSON_AddNumberToObject(result.get(),"revision",controller.revision());
        cJSON_AddStringToObject(result.get(),"digest",controller.digest().c_str());
        cJSON_AddStringToObject(result.get(),"projection_status",view.status());
        cJSON_AddNumberToObject(result.get(),"reads",backing.reads);cJSON_AddNumberToObject(result.get(),"writes",backing.writes);
        cJSON_AddBoolToObject(result.get(),"durable_unchanged",backing.data==original);
        cJSON_AddBoolToObject(result.get(),"physical_outputs_enabled",false);
        cJSON_AddNumberToObject(result.get(),"view_object_bytes",sizeof(GraphControlStoreView));
        if(!state.empty())cJSON_AddItemToObject(result.get(),"controller_state",cJSON_Parse(state.c_str()));
        std::cout<<printJson(result.get())<<std::endl;
    }
}
