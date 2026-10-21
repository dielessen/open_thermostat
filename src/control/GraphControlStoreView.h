#pragma once
#include "GraphShadowConfiguration.h"
#include "SeasonalControllerSource.h"

namespace heating::control {
// Explicit reviewed SOURCE pin of inert accepted DATA, not a runtime grant.
// No incoming frame/GUI graph_ready can construct/select this factory contract.
struct GraphControlHandoffSource {
    std::string controllerId,adapterId,qualificationDigest,configDigest,mappingDigest,profileDigest;
    uint32_t revision=0,mappingRevision=0;
    bool valid()const {
        return SessionAdmission::validId(controllerId)&&SessionAdmission::validId(adapterId)
            &&heating::graph_test::hex(qualificationDigest)&&heating::graph_test::hex(configDigest)
            &&heating::graph_test::hex(mappingDigest)&&heating::graph_test::hex(profileDigest)&&revision&&mappingRevision;
    }
};

// Sole existing transport owner selects this view INSTEAD OF the graph writer.
// It reads the same durable graph key and NEVER rewrites it to an API1 schema.
// Reads validate the whole original DATA with the existing shared validator,
// then compare independent SOURCE tuple/binding/bounds/policy/config pins.
class GraphControlStoreView final:public ControlStore {
public:
    using Hash=heating::graph_test::Hash;
    GraphControlStoreView(const std::string& controller,const std::string& adapter,
                         ControlStore& backing,Hash hash,const GraphControlHandoffSource& pin,
                         const SeasonalControllerSource& policy)
        :backing_(backing),hash_(std::move(hash)) {
        if(!pin.valid()||!policy.valid()||policy.count!=1||policy.profileDigest.empty()
            ||policy.profileDigest!=pin.profileDigest
            ||controller!=pin.controllerId||adapter!=pin.adapterId||policy.controllerId!=controller||!hash_) {
            fail("graph_control_source_invalid");return;
        }
        pin_=pin;policy_=std::make_unique<SeasonalControllerSource>(policy);
    }
    bool load(std::string& out)override {
        out.clear();
        if(fault_||busy_)return fail("graph_control_fault");
        busy_=true;
        try {
            std::string raw;
            if(!backing_.load(raw)||raw.empty()||raw.size()>GraphShadowConfiguration::maximumStoreBytes)
                return finish(false,"graph_control_read_failure");
            // Reuse the authoritative restore validator without another backing
            // IO, session, grant, writer, or new persistent key.
            class Snapshot final:public ControlStore {
            public:
                explicit Snapshot(const std::string& data):data_(data){}
                bool load(std::string& out)override{out=data_;return true;}
                bool save(std::string_view)override{return false;}
            private:const std::string& data_;
            } snapshot(raw);
            auto graph=std::make_unique<GraphShadowConfiguration>(pin_.controllerId,"source_projection",
                pin_.adapterId,pin_.qualificationDigest,snapshot,hash_);
            if(!graph->initialize()||graph->faulted()||fault_)return finish(false,"graph_control_data_invalid");
            if(graph->revision()!=pin_.revision||graph->mappingRevision()!=pin_.mappingRevision
                ||graph->configDigest()!=pin_.configDigest||hash_(graph->mappingBytes())!=pin_.mappingDigest||fault_)
                return finish(false,"graph_control_tuple_mismatch");
            using namespace heating::graph_test;
            auto config=parse(graph->configBytes());
            const auto rooms=get(config.get(),"rooms"),actuators=get(config.get(),"actuators");
            const auto room=cJSON_GetArrayItem(rooms,0),actuator=cJSON_GetArrayItem(actuators,0);
            const auto& zone=policy_->zones[0];
            if(str(get(room,"zone_id"))!=zone.zoneId||str(get(room,"sensor_id"))!=zone.sensorId
                ||str(get(actuator,"actuator_id"))!=zone.actuatorId
                ||integer(get(room,"minimum_target_centi_c"),500,3500)!=zone.minimumTargetCentiC
                ||integer(get(room,"maximum_target_centi_c"),500,3500)!=zone.maximumTargetCentiC
                ||integer(get(room,"max_age_ms"),1000,86400000)>zone.seasonal.maximumSensorAgeMs)
                return finish(false,"graph_control_binding_or_bounds_mismatch");
            Json projected(cJSON_CreateObject(),cJSON_Delete);need(bool(projected),"allocation");
            const auto text=[](cJSON* o,const char* key,const std::string& v){need(cJSON_AddStringToObject(o,key,v.c_str()),"allocation");};
            const auto number=[](cJSON* o,const char* key,uint32_t v){need(cJSON_AddNumberToObject(o,key,v),"allocation");};
            text(projected.get(),"mapping_digest",pin_.mappingDigest);text(projected.get(),"mode","shadow");
            number(projected.get(),"revision",pin_.revision);number(projected.get(),"schema",1);
            auto zones=cJSON_AddArrayToObject(projected.get(),"zones");need(zones,"allocation");
            Json ownedZone(cJSON_CreateObject(),cJSON_Delete);need(bool(ownedZone),"allocation");
            auto z=ownedZone.get();need(cJSON_AddItemToArray(zones,z),"allocation");ownedZone.release();
            text(z,"actuator_id",zone.actuatorId);number(z,"base_centi_c",integer(get(room,"base_centi_c"),500,3500));
            number(z,"max_age_ms",integer(get(room,"max_age_ms"),1000,86400000));
            text(z,"report_evidence",str(get(room,"report_evidence")));
            Json schedule(cJSON_Duplicate(get(room,"schedule"),true),cJSON_Delete);need(bool(schedule),"allocation");
            need(cJSON_AddItemToObject(z,"schedule",schedule.get()),"allocation");schedule.release();
            text(z,"sensor_id",zone.sensorId);text(z,"zone_id",zone.zoneId);
            auto bytes=print(projected.get());
            if(bytes.size()>GraphShadowConfiguration::maximumStoreBytes
                ||hash_(bytes)!=policy_->configDigest||fault_)
                return finish(false,"graph_control_policy_config_mismatch");
            out=std::move(bytes);
            if(fault_){out.clear();return finish(false,"graph_control_fault");}
            return finish(true,"graph_control_data_projection_no_admission");
        }catch(...){return finish(false,"graph_control_dependency_fault");}
    }
    bool save(std::string_view)override{return fail("graph_control_read_only");}
    bool faulted()const{return fault_;}
    const char* status()const{return status_;}
private:
    bool fail(const char* status){fault_=true;status_=status;return false;}
    bool finish(bool ok,const char* status){busy_=false;if(!ok)return fail(status);status_=status;return true;}
    ControlStore& backing_;Hash hash_;GraphControlHandoffSource pin_;
    std::unique_ptr<SeasonalControllerSource> policy_;
    bool busy_=false,fault_=false;const char* status_="graph_control_uninitialized";
};
}
