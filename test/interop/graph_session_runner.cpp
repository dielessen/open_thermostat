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
    std::string data;size_t writes=0,reads=0;bool ok=true,commit=false,loadOk=true,readbackMismatch=false;
    bool load(std::string& out)override{++reads;out=data;if(readbackMismatch)out+=" ";return loadOk;}
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
    bool controlMode=false,nativePlanMode=false;
    std::unique_ptr<NativePlanInstallationSource> nativePlanSource;
    std::string controller,boot,adapter,anchor,line;uint32_t nonce=0;
    bool failHash=false,reenterHash=false;
    uint64_t callbackNow=0;
    auto hash=[&](std::string_view bytes) {
        if(failHash){failHash=false;return std::string{};}
        if(reenterHash&&control) {
            reenterHash=false;
            control->receive("ha/heartbeat","{}",callbackNow,1792368000,true);
        }
        return controlTestHash(bytes);
    };
    std::vector<std::pair<std::string,std::string>> frames;
    auto construct=[&] {
        owner=std::make_unique<GraphSessionOwner>(controller,boot,adapter,anchor,store,controlTestHash,
            [&]{return "test_random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);});
    };
    auto constructControl=[&] {
        owner.reset();control.reset();controlView.reset();topologyView.reset();floorBridgeView.reset(); // Never two admitted owners.
        ControlStore* selected=nullptr;
        if(nativePlanMode) {
            selected=&store; // Complete accepted plan, no read-only projection.
        } else if(floorBridgeMode) {
            floorBridgeView=std::make_unique<GraphFloorControlStoreView>(controller,adapter,store,controlTestHash,floorBridgeSource,*policy);
            selected=floorBridgeView.get();
        } else if(topologyMode) {
            topologyView=std::make_unique<TopologyControlStoreView>(controller,adapter,store,controlTestHash,topologySource,*policy);
            selected=topologyView.get();
        } else {
            controlView=std::make_unique<GraphControlStoreView>(controller,adapter,store,controlTestHash,handoff,*policy);
            selected=controlView.get();
        }
        control=std::make_unique<ShadowController>(controller,boot,adapter,*selected,hash,
            [&]{return "test_random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);},
            ShadowController::Metrics{},nativePlanMode?nullptr:policy.get(),[&]{return safety;},
            nativePlanMode?nativePlanSource.get():nullptr);
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
        } else if(op=="initialize_native_plan") {
            // Independent fixed SOURCE fixture selected ONCE, before desired
            // configs. No stored config/review is manufactured or preloaded.
            controller=text("controller");boot=text("boot");adapter=text("owner");store.data=text("stored");
            nativePlanSource=std::make_unique<NativePlanInstallationSource>();
            auto& source=*nativePlanSource;const auto src=gt::get(root.get(),"source");
            auto txt=[&](const cJSON* o,const char* key){return gt::str(gt::get(o,key));};
            auto num=[&](const cJSON* o,const char* key,uint32_t lo,uint32_t hi){return static_cast<uint32_t>(gt::integer(gt::get(o,key),lo,hi));};
            source.controllerId=controller;source.adapterId=adapter;source.profileDigest=txt(src,"profile_digest");
            source.count=2;source.maximumSafetyAgeMs=2000;
            source.legacyReadbackReviewed=cJSON_IsTrue(gt::get(src,"legacy_readback_reviewed"));
            source.mappingRevision=num(src,"mapping_revision",1,UINT32_MAX);
            const auto rows=gt::get(src,"zones");if(!cJSON_IsArray(rows)||cJSON_GetArraySize(rows)!=2)return 5;
            for(size_t i=0;i<2;++i) {
                const auto row=cJSON_GetArrayItem(rows,static_cast<int>(i));auto& z=source.zones[i];auto& q=z.policy;
                q.zoneId=txt(row,"zone_id");q.sensorId=txt(row,"sensor_id");q.actuatorId=txt(row,"actuator_id");
                q.minimumTargetCentiC=num(row,"minimum_target_centi_c",500,3500);
                q.maximumTargetCentiC=num(row,"maximum_target_centi_c",500,3500);
                z.groupId=txt(row,"group_id");z.emitter=txt(row,"emitter");z.actuatorProfile=txt(row,"actuator_profile");
                z.sensorResource=txt(row,"sensor_resource");z.outputResource=txt(row,"output_resource");
                z.reportEvidence=txt(row,"report_evidence");z.maximumSensorAgeMs=num(row,"maximum_sensor_age_ms",1000,120000);
                z.minimumSupplyCentiC=num(row,"minimum_supply_centi_c",500,8999);
                z.maximumSupplyCentiC=num(row,"maximum_supply_centi_c",501,9000);
                const auto control=gt::get(row,"control");
                q.control.mode=txt(control,"mode")=="slow_binary_pi"?ZoneControl::slowBinaryPi:
                    txt(control,"mode")=="local_trv"?ZoneControl::localTrv:ZoneControl::hysteresis;
                q.control.hysteresisCentiC=num(control,"hysteresis_centi_c",1,200);
                q.control.kpPermillePerC=num(control,"kp_permille_per_c",0,1000);
                q.control.kiPermillePerCMinute=num(control,"ki_permille_per_c_minute",0,1000);
                q.control.cycleMs=num(control,"cycle_ms",0,3600000);
                q.control.minimumOnMs=num(control,"minimum_on_ms",0,1800000);
                q.control.minimumOffMs=num(control,"minimum_off_ms",0,1800000);
                // Explicit synthetic logical profile, NOT physical readiness.
                q.seasonal.enabled=q.seasonal.installationQualified=true;
                q.seasonal.maximumSensorAgeMs=z.maximumSensorAgeMs;q.seasonal.maximumStepGapMs=300000;
            }
            nativePlanMode=controlMode=true;floorBridgeMode=topologyMode=false;
            safety=SeasonalSafetySnapshot{};constructControl();
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
            else if(op=="reboot"){boot=text("boot");store.ok=true;store.commit=false;store.loadOk=true;store.readbackMismatch=false;
                if(nativePlanMode)safety=SeasonalSafetySnapshot{};
                constructControl();}
            else if(op=="ambiguous"){store.ok=false;store.commit=true;}
            else if(op=="save_failure"){store.ok=false;store.commit=false;}
            else if(op=="read_failure"){store.loadOk=false;}
            else if(op=="readback_mismatch"){store.readbackMismatch=true;}
            else if(op=="hash_failure"){failHash=true;}
            else if(op=="hash_reentry"){reenterHash=true;callbackNow=now;}
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
        cJSON_AddNumberToObject(result.get(),"reads",store.reads);
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
        cJSON_AddStringToObject(result.get(),"status",(controlMode?(nativePlanMode?"native_complete_plan":floorBridgeMode?floorBridgeView->status():(topologyMode?topologyView->status():controlView->status())):owner->configuration().status().c_str()));
        if(nativePlanMode)cJSON_AddNumberToObject(result.get(),"native_source_object_bytes",sizeof(NativePlanInstallationSource));
        cJSON_AddBoolToObject(result.get(),"boiler_output_enabled",controlMode?false:owner->configuration().boilerOutputEnabled());
        cJSON_AddBoolToObject(result.get(),"actuator_output_enabled",controlMode?false:owner->configuration().actuatorOutputEnabled());
        std::cout<<gt::print(result.get())<<std::endl;
    }
}
