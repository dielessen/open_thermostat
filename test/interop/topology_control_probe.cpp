// Finite actual read-only SOURCE view failure probe, no network/HA replacement.
#include "control/TopologyControlStoreView.h"
#include "ControlTestHash.h"
#include <iostream>
#include <stdexcept>
namespace gt=heating::graph_test;
using namespace heating::control;
struct ProbeStore:ControlStore {
    std::string data;size_t reads=0,writes=0;bool ok=true;std::function<void()> onRead;
    bool load(std::string& out)override{++reads;if(onRead)onRead();out=data;return ok;}
    bool save(std::string_view)override{++writes;return false;}
};
int main() {
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>20000)return 2;
        gt::Json root(cJSON_Parse(line.c_str()),cJSON_Delete);if(!root)return 3;
        const auto src=gt::get(root.get(),"source"),cx=gt::get(src,"context");
        auto t=[](const cJSON* o,const char* k){return gt::str(gt::get(o,k));};
        auto n=[](const cJSON* o,const char* k,uint32_t low){return static_cast<uint32_t>(gt::integer(gt::get(o,k),low,UINT32_MAX));};
        const auto mode=t(root.get(),"mode");
        ProbeStore backing;backing.data=t(root.get(),"stored");const auto original=backing.data;
        TopologyControlHandoffSource source;source.profileVersion=t(src,"profile_version");
        source.adapterId="test_owner";source.reviewDigest=t(src,"review_digest");source.profileDigest=t(src,"expected_profile_digest");
        source.context={t(cx,"controller_id"),t(cx,"boot_id"),t(cx,"adapter_session_id"),t(cx,"plan_digest"),
            n(cx,"epoch",1),n(cx,"config_revision",0),n(cx,"registry_revision",1),n(cx,"source_revision",1)};
        SeasonalControllerSource policy;policy.controllerId=source.context.controllerId;policy.configDigest=t(src,"control_digest");
        policy.profileDigest=t(src,"profile_digest");policy.count=2;policy.maximumSafetyAgeMs=2000;
        const auto zones=gt::get(src,"zones");if(cJSON_GetArraySize(zones)!=2)return 4;
        for(size_t i=0;i<2;++i) {
            auto r=cJSON_GetArrayItem(zones,static_cast<int>(i));auto& z=policy.zones[i];
            z.zoneId=t(r,"zone_id");z.sensorId=t(r,"sensor_id");z.actuatorId=t(r,"actuator_id");
            z.minimumTargetCentiC=n(r,"minimum",500);z.maximumTargetCentiC=n(r,"maximum",500);
            source.evidence[i]=t(r,"evidence");
            z.control.mode=t(r,"emitter")=="floor"?ZoneControl::slowBinaryPi:ZoneControl::localTrv;
            if(z.control.mode==ZoneControl::slowBinaryPi) {
                z.control.kpPermillePerC=500;z.control.kiPermillePerCMinute=10;
                z.control.cycleMs=900000;z.control.minimumOnMs=180000;z.control.minimumOffMs=120000;
            }
            z.seasonal.enabled=z.seasonal.installationQualified=true; // Declared fixture ONLY.
            z.seasonal.maximumSensorAgeMs=120000;z.seasonal.maximumStepGapMs=300000;
        }
        if(mode=="read_failure")backing.ok=false;
        if(mode=="empty")backing.data.clear();
        if(mode=="too_large")backing.data.assign(4097,'x');
        if(mode=="bad_version")source.profileVersion="two-room-targets.v2";
        if(mode=="bad_profile")source.profileDigest.assign(64,'0');
        if(mode=="bad_config")policy.configDigest.assign(64,'0');
        if(mode=="bad_binding")policy.zones[1].sensorId="different";
        if(mode=="bad_bounds")policy.zones[1].minimumTargetCentiC=1700;
        if(mode=="unqualified")policy.zones[1].seasonal.installationQualified=false;
        if(mode=="unused_zone")policy.zones[7].actuatorId="hidden";
        if(mode=="bad_boot")source.context.bootId=std::string(4097,'x');
        if(mode=="bad_session")source.context.sessionId="invalid space";
        if(mode=="one_zone")policy.count=1;
        if(mode=="three_zones")policy.count=3;
        if(mode=="bad_evidence")source.evidence[0]="cached_state";
        if(mode=="bad_context")++source.context.sourceRevision;
        if(mode=="wrong_store")backing.data="{}";
        TopologyControlStoreView* active=nullptr;bool fired=false;
        auto hash=[&](std::string_view bytes) {
            const bool full=bytes.find("source_topology_review")!=std::string_view::npos;
            const bool plan=bytes.find("draft_digest")!=std::string_view::npos&&!full;
            const bool mapping=bytes.find("mapping_schema")!=std::string_view::npos;
            const bool config=bytes.find("\"mode\":\"shadow\"")!=std::string_view::npos;
            if(mode=="hash_throw")throw std::runtime_error("injected fixed SOURCE provider failure");
            if(!fired&&active&&((mode=="hash_reentry"&&full)||(mode=="decode_reentry"&&plan)
                    ||(mode=="mapping_reentry"&&mapping)||(mode=="config_reentry"&&config))) {
                fired=true;std::string ignored;active->load(ignored);
            }
            return controlTestHash(bytes);
        };
        TopologyControlStoreView view(source.context.controllerId,"test_owner",backing,hash,source,policy);
        active=&view;
        if(mode=="read_reentry")backing.onRead=[&]{if(!fired){fired=true;std::string ignored;active->load(ignored);}};
        std::string projected="must_be_cleared";const bool first=view.load(projected);
        const auto reads=backing.reads;
        if(mode=="write_attempt")view.save("not_allowed");
        // Correct backing bytes cannot heal any sticky SOURCE/storage fault.
        backing.data=original;backing.ok=true;backing.onRead={};
        std::string again="must_be_cleared";const bool second=view.load(again);
        const bool expected=mode=="ok";
        const bool pass=expected?(first&&second&&!view.faulted()&&projected==again&&controlTestHash(projected)==policy.configDigest):
            (mode=="write_attempt"?(first&&!second&&again.empty()&&view.faulted()&&backing.reads==reads):
                (!first&&!second&&projected.empty()&&again.empty()&&view.faulted()&&backing.reads==reads));
        gt::Json out(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddStringToObject(out.get(),"mode",mode.c_str());cJSON_AddBoolToObject(out.get(),"pass",pass);
        cJSON_AddBoolToObject(out.get(),"first",first);cJSON_AddBoolToObject(out.get(),"second",second);
        cJSON_AddBoolToObject(out.get(),"fault",view.faulted());cJSON_AddBoolToObject(out.get(),"callback_fired",fired);
        cJSON_AddNumberToObject(out.get(),"reads",backing.reads);cJSON_AddNumberToObject(out.get(),"writes",backing.writes);
        cJSON_AddStringToObject(out.get(),"status",view.status());
        cJSON_AddBoolToObject(out.get(),"durable_unchanged",backing.data==original);
        cJSON_AddNumberToObject(out.get(),"view_object_bytes",sizeof(TopologyControlStoreView));
        cJSON_AddNumberToObject(out.get(),"review_result_bytes",sizeof(heating::graph_review::Result));
        cJSON_AddNumberToObject(out.get(),"projected_bytes",projected.size());
        std::cout<<gt::print(out.get())<<std::endl;
    }
}
