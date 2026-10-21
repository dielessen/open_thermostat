// Finite stdin/EOF actual protocol owner. No broker/service/device IO.
#include "control/GraphSessionOwner.h"
#include "control/GraphControlStoreView.h"
#include "control/TopologyControlStoreView.h"
#include "control/GraphFloorControlStoreView.h"
#include "control/ShadowController.h"
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
    std::unique_ptr<GraphControlStoreView> controlView;
    std::unique_ptr<ShadowController> control;
    std::unique_ptr<TopologyControlStoreView> topologyView;
    TopologyControlHandoffSource topologySource;
    bool topologyMode=false,floorBridgeMode=false;
    GraphFloorControlHandoffSource floorBridgeSource;
    std::unique_ptr<GraphFloorControlStoreView> floorBridgeView;
    std::unique_ptr<SeasonalControllerSource> policy;
    GraphControlHandoffSource handoff;
    SeasonalSafetySnapshot safety;
    bool controlMode=false;
    std::string controller,boot,adapter,anchor,line;uint32_t nonce=0;
    std::vector<std::pair<std::string,std::string>> frames;
    auto construct=[&] {
        owner=std::make_unique<GraphSessionOwner>(controller,boot,adapter,anchor,store,controlTestHash,
            [&]{return "test_random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);});
    };
    auto constructControl=[&] {
        owner.reset();control.reset();controlView.reset();topologyView.reset();floorBridgeView.reset(); // Never two admitted owners.
        ControlStore* selected=nullptr;
        if(floorBridgeMode) {
            floorBridgeView=std::make_unique<GraphFloorControlStoreView>(controller,adapter,store,controlTestHash,floorBridgeSource,*policy);
            selected=floorBridgeView.get();
        } else if(topologyMode) {
            topologyView=std::make_unique<TopologyControlStoreView>(controller,adapter,store,controlTestHash,topologySource,*policy);
            selected=topologyView.get();
        } else {
            controlView=std::make_unique<GraphControlStoreView>(controller,adapter,store,controlTestHash,handoff,*policy);
            selected=controlView.get();
        }
        control=std::make_unique<ShadowController>(controller,boot,adapter,*selected,controlTestHash,
            [&]{return "test_random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);},
            ShadowController::Metrics{},policy.get(),[&]{return safety;});
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
        } else if(op=="initialize_topology_source"||op=="select_graph_floor_source") {
            // SOURCE-fixture preload ONLY. Existing graph writer cannot yet
            // create this distinct review record; NOT a wire/GUI provisioner.
            if(op=="initialize_topology_source") {
                controller=text("controller");boot=text("boot");adapter=text("owner");store.data=text("stored");
            } else {
                // Explicit SOURCE factory review event only. Existing actual
                // graph writer produced store.data; NEVER preload/replace it.
                boot="bridge_control_boot";
            }
            const auto src=gt::get(root.get(),"source"),cx=gt::get(src,"context");
            auto t=[&](const cJSON* o,const char* key){return gt::str(gt::get(o,key));};
            auto n=[&](const cJSON* o,const char* key,uint32_t minimum){return static_cast<uint32_t>(gt::integer(gt::get(o,key),minimum,UINT32_MAX));};
            topologySource.profileVersion=t(src,"profile_version");topologySource.adapterId=adapter;
            topologySource.reviewDigest=t(src,"review_digest");topologySource.profileDigest=t(src,"expected_profile_digest");
            topologySource.context={t(cx,"controller_id"),t(cx,"boot_id"),t(cx,"adapter_session_id"),t(cx,"plan_digest"),
                n(cx,"epoch",1),n(cx,"config_revision",0),n(cx,"registry_revision",1),n(cx,"source_revision",1)};
            policy=std::make_unique<SeasonalControllerSource>();policy->controllerId=controller;
            policy->profileDigest=t(src,"profile_digest");policy->configDigest=t(src,"control_digest");
            policy->maximumSafetyAgeMs=2000;policy->count=2;
            const auto pins=gt::get(src,"zones");if(!cJSON_IsArray(pins)||cJSON_GetArraySize(pins)!=2)return 5;
            for(size_t i=0;i<2;++i) {
                auto row=cJSON_GetArrayItem(pins,static_cast<int>(i));auto& z=policy->zones[i];
                z.zoneId=t(row,"zone_id");z.sensorId=t(row,"sensor_id");z.actuatorId=t(row,"actuator_id");
                z.minimumTargetCentiC=n(row,"minimum",500);z.maximumTargetCentiC=n(row,"maximum",500);
                topologySource.evidence[i]=t(row,"evidence");
                z.control.mode=t(row,"emitter")=="floor"?ZoneControl::slowBinaryPi:ZoneControl::localTrv;
                if(z.control.mode==ZoneControl::slowBinaryPi) {
                    z.control.kpPermillePerC=500;z.control.kiPermillePerCMinute=10;
                    z.control.cycleMs=900000;z.control.minimumOnMs=180000;z.control.minimumOffMs=120000;
                }
                // Explicit synthetic SOURCE qualification, NOT data-derived
                // product profile or proof of real physical installation.
                z.seasonal.enabled=z.seasonal.installationQualified=true;
                z.seasonal.maximumSensorAgeMs=120000;z.seasonal.maximumStepGapMs=300000;
            }
            floorBridgeMode=op=="select_graph_floor_source";
            if(floorBridgeMode) {
                const auto g=gt::get(src,"graph");
                floorBridgeSource.profileVersion=t(src,"bridge_version");
                floorBridgeSource.reviewJson=t(src,"review_json");
                floorBridgeSource.topology=topologySource;
                floorBridgeSource.data={controller,adapter,t(g,"qualification_digest"),t(g,"config_digest"),
                    t(g,"mapping_digest"),t(src,"expected_profile_digest"),n(g,"revision",1),n(g,"mapping_revision",1)};
            }
            topologyMode=!floorBridgeMode;controlMode=true;constructControl();
        } else if(op=="select_control_source") {
            // Trusted fixture-only factory selection, NOT a wire command or
            // production GUI option. Same actual backing key/store is retained.
            const auto src=gt::get(root.get(),"source");
            auto t=[&](const char* key){return gt::str(gt::get(src,key));};
            handoff={controller,adapter,t("qualification_digest"),t("config_digest"),t("mapping_digest"),
                t("expected_profile_digest"),
                static_cast<uint32_t>(gt::integer(gt::get(src,"revision"),1,UINT32_MAX)),
                static_cast<uint32_t>(gt::integer(gt::get(src,"mapping_revision"),1,UINT32_MAX))};
            policy=std::make_unique<SeasonalControllerSource>();policy->controllerId=controller;
            policy->configDigest=t("control_digest");policy->profileDigest=t("profile_digest");
            policy->count=1;policy->maximumSafetyAgeMs=2000;
            auto& z=policy->zones[0];z.zoneId=t("zone_id");z.sensorId=t("sensor_id");z.actuatorId=t("actuator_id");
            z.minimumTargetCentiC=gt::integer(gt::get(src,"minimum"),500,3500);
            z.maximumTargetCentiC=gt::integer(gt::get(src,"maximum"),500,3500);
            z.seasonal.enabled=z.seasonal.installationQualified=true;
            z.seasonal.maximumSensorAgeMs=120000;z.seasonal.maximumStepGapMs=300000;
            controlMode=true;boot="control_boot";constructControl();
        } else if(op=="select_data_source") {
            // Explicit fixture-only source rollback; original DATA unchanged.
            control.reset();controlView.reset();topologyView.reset();floorBridgeView.reset();
            floorBridgeMode=topologyMode=controlMode=false;boot="data_review_boot";construct();
        } else if(controlMode) {
            const int64_t utc=gt::get(root.get(),"utc")?gt::integer(gt::get(root.get(),"utc"),0,4102444800LL):1792368000;
            if(op=="connect")control->connected(now);
            else if(op=="disconnect")control->disconnected();
            else if(op=="receive")control->receive(text("topic"),text("raw"),now,utc,true);
            else if(op=="tick")control->tick(now,utc,true);
            else if(op=="reboot"){boot=text("boot");constructControl();}
            else if(op=="safety_snapshot") {
                safety.sampledAt=now;
                safety.limitsKnownSafe=cJSON_IsTrue(gt::get(root.get(),"limits_known_safe"));
                safety.dhwStateKnown=cJSON_IsTrue(gt::get(root.get(),"dhw_state_known"));
                safety.dhwActive=cJSON_IsTrue(gt::get(root.get(),"dhw_active"));
                safety.summer=cJSON_IsTrue(gt::get(root.get(),"summer"));
                safety.allOff=cJSON_IsTrue(gt::get(root.get(),"all_off"));
            } else if(op!="status"&&op!="durable_readback")return 5;
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
        cJSON_AddBoolToObject(result.get(),"fault",(controlMode?control->faulted():owner->faulted()));
        cJSON_AddNumberToObject(result.get(),"revision",(controlMode?control->revision():owner->configuration().revision()));
        cJSON_AddNumberToObject(result.get(),"writes",store.writes);
        cJSON_AddNumberToObject(result.get(),"store_bytes",store.data.size());
        cJSON_AddNumberToObject(result.get(),"object_bytes",sizeof(GraphSessionOwner));
        cJSON_AddBoolToObject(result.get(),"source_control_mode",controlMode);
        if(floorBridgeMode) {
            cJSON_AddNumberToObject(result.get(),"floor_bridge_view_object_bytes",sizeof(GraphFloorControlStoreView));
            cJSON_AddNumberToObject(result.get(),"floor_bridge_source_object_bytes",sizeof(GraphFloorControlHandoffSource));
        }
        if(topologyMode) {
            cJSON_AddNumberToObject(result.get(),"topology_view_object_bytes",sizeof(TopologyControlStoreView));
            cJSON_AddNumberToObject(result.get(),"topology_review_bytes",store.data.size());
        }
        cJSON_AddNumberToObject(result.get(),"grant_deadline_ms",(controlMode?0:owner->configuration().grantDeadline(now)));
        cJSON_AddStringToObject(result.get(),"status",(controlMode?(floorBridgeMode?floorBridgeView->status():(topologyMode?topologyView->status():controlView->status())):owner->configuration().status().c_str()));
        cJSON_AddBoolToObject(result.get(),"boiler_output_enabled",controlMode?false:owner->configuration().boilerOutputEnabled());
        cJSON_AddBoolToObject(result.get(),"actuator_output_enabled",controlMode?false:owner->configuration().actuatorOutputEnabled());
        std::cout<<gt::print(result.get())<<std::endl;
    }
}
