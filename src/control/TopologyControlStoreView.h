#pragma once
#include "GraphTopologyReview.h"
#include "SessionAdmission.h"
#include <algorithm>
#include <memory>
#include "ControlStore.h"
#include "SeasonalControllerSource.h"

namespace heating::control {
// Distinct SOURCE profile/version, not an expanded graph DATA capability.
// Nothing in config/GUI/discovery constructs or selects this contract.
struct TopologyControlHandoffSource {
    static constexpr const char* version="two-room-targets.v1";
    std::string profileVersion,adapterId,reviewDigest,profileDigest;
    heating::graph_review::Context context;
    std::array<std::string,2> evidence;
    bool valid()const {
        using namespace heating::graph_test;
        if(profileVersion!=version||!hex(reviewDigest)||!hex(profileDigest)||!hex(context.planDigest)
            ||!SessionAdmission::validId(context.controllerId)||!SessionAdmission::validId(adapterId)
            ||!SessionAdmission::validId(context.bootId)||!SessionAdmission::validId(context.sessionId)||!context.epoch||!context.registryRevision
            ||!context.sourceRevision||context.configRevision==UINT32_MAX)return false;
        for(const auto& e:evidence)if(e!="physical_report"&&e!="validated_integration_report")return false;
        return true;
    }
};
// Same existing config key, READ ONLY. Review-only DATA is insufficient:
// independent SOURCE policy/profile/config/binding pins must ALL match.
// No new store/writer, schema limit, controller, scheduler, grant or output.
class TopologyControlStoreView final:public ControlStore {
public:
    using Hash=heating::graph_test::Hash;
    TopologyControlStoreView(const std::string& controller,const std::string& adapter,
        ControlStore& backing,Hash hash,const TopologyControlHandoffSource& source,
        const SeasonalControllerSource& policy):backing_(backing),hash_(std::move(hash)) {
        if(!source.valid()||!policy.valid()||policy.count!=2||source.context.controllerId!=controller
            ||source.adapterId!=adapter||policy.controllerId!=controller
            ||policy.profileDigest!=source.profileDigest||!hash_) {
            fail("topology_control_source_invalid");return;
        }
        // Only TWO used pins may own strings; reject hidden dynamic payloads
        // in the existing eight-slot policy representation before copying it.
        for(size_t i=2;i<policy.zones.size();++i)
            if(!policy.zones[i].zoneId.empty()||!policy.zones[i].sensorId.empty()||!policy.zones[i].actuatorId.empty()) {
                fail("topology_control_unused_pin");return;
            }
        source_=source;policy_=std::make_unique<SeasonalControllerSource>(policy);
    }
    bool load(std::string& out)override {
        out.clear();
        if(fault_||busy_)return fail("topology_control_fault");
        busy_=true;
        try {
            std::string raw;
            if(!backing_.load(raw)||raw.empty()||raw.size()>heating::graph_review::Review::maxBytes||fault_)
                return finish(false,"topology_control_read_failure");
            if(hash_(raw)!=source_.reviewDigest||fault_)return finish(false,"topology_control_review_conflict");
            const auto result=heating::graph_review::read(raw,source_.context,hash_);
            if(std::string_view(result.code)!="source_topology_review_only"||fault_)
                return finish(false,"topology_control_review_invalid");
            using namespace heating::graph_test;
            const auto text=[](cJSON* o,const char* key,const std::string& v){need(cJSON_AddStringToObject(o,key,v.c_str()),"allocation");};
            const auto number=[](cJSON* o,const char* key,uint32_t v){need(cJSON_AddNumberToObject(o,key,v),"allocation");};
            Json mapping(cJSON_CreateObject(),cJSON_Delete);need(bool(mapping),"allocation");
            auto channels=cJSON_AddArrayToObject(mapping.get(),"channels");need(channels,"allocation");
            number(mapping.get(),"mapping_revision",source_.context.registryRevision);number(mapping.get(),"mapping_schema",2);
            std::set<std::string> names;
            struct Channel {std::string id,direction,owner,resource;};
            std::array<Channel,4> list;
            for(size_t i=0;i<2;++i) {
                const auto& r=result.review.rooms[i];const auto& z=policy_->zones[i];
                const std::string id(r.zone.data()),actuator(r.actuator.data()),sensor="s_"+id;
                if(z.zoneId!=id||z.sensorId!=sensor||z.actuatorId!=actuator
                    ||z.minimumTargetCentiC!=r.minimum||z.maximumTargetCentiC!=r.maximum
                    ||r.maximumAge>z.seasonal.maximumSensorAgeMs
                    ||(!r.floor&&z.control.mode!=ZoneControl::localTrv)
                    ||(r.floor&&z.control.mode!=ZoneControl::slowBinaryPi))
                    return finish(false,"topology_control_binding_or_policy_conflict");
                if(!names.insert(sensor).second||!names.insert(actuator).second)
                    return finish(false,"topology_control_channel_conflict");
                list[i*2]={sensor,"input",id,r.sensorResource.data()};
                list[i*2+1]={actuator,"output",actuator,r.outputResource.data()};
            }
            std::sort(list.begin(),list.end(),[](const auto& a,const auto& b){return a.id<b.id;});
            for(const auto& c:list) {
                Json owned(cJSON_CreateObject(),cJSON_Delete);need(bool(owned),"allocation");
                auto q=owned.get();text(q,"channel_id",c.id);text(q,"direction",c.direction);
                text(q,"owner_id",c.owner);text(q,"resource_id",c.resource);
                need(cJSON_AddItemToArray(channels,q),"allocation");owned.release();
            }
            const auto mappingDigest=hash_(print(mapping.get()));
            if(!hex(mappingDigest)||fault_)return finish(false,"topology_control_hash_fault");
            Json config(cJSON_CreateObject(),cJSON_Delete);need(bool(config),"allocation");
            text(config.get(),"mapping_digest",mappingDigest);text(config.get(),"mode","shadow");
            number(config.get(),"revision",source_.context.configRevision+1);number(config.get(),"schema",1);
            auto zones=cJSON_AddArrayToObject(config.get(),"zones");need(zones,"allocation");
            for(size_t i=0;i<2;++i) {
                const auto& r=result.review.rooms[i];const auto& z=policy_->zones[i];
                Json owned(cJSON_CreateObject(),cJSON_Delete);need(bool(owned),"allocation");
                auto q=owned.get();text(q,"actuator_id",z.actuatorId);number(q,"base_centi_c",r.base);
                number(q,"max_age_ms",r.maximumAge);text(q,"report_evidence",source_.evidence[i]);
                need(cJSON_AddNullToObject(q,"schedule"),"allocation");
                text(q,"sensor_id",z.sensorId);text(q,"zone_id",z.zoneId);
                need(cJSON_AddItemToArray(zones,q),"allocation");owned.release();
            }
            auto bytes=print(config.get());
            if(bytes.size()>4096||hash_(bytes)!=policy_->configDigest||fault_)
                return finish(false,"topology_control_config_conflict");
            out=std::move(bytes);
            if(fault_){out.clear();return finish(false,"topology_control_fault");}
            return finish(true,"topology_control_projection_no_admission");
        }catch(...){out.clear();return finish(false,"topology_control_dependency_fault");}
    }
    bool save(std::string_view)override{return fail("topology_control_read_only");}
    bool faulted()const{return fault_;}
    const char* status()const{return status_;}
private:
    bool fail(const char* status){fault_=true;status_=status;return false;}
    bool finish(bool ok,const char* status){busy_=false;if(!ok)return fail(status);status_=status;return true;}
    ControlStore& backing_;Hash hash_;TopologyControlHandoffSource source_;
    std::unique_ptr<SeasonalControllerSource> policy_;
    bool busy_=false,fault_=false;const char* status_="topology_control_uninitialized";
};
}
