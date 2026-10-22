#pragma once
#include "SessionAdmission.h"
#include "SeasonalControllerSource.h"
#include "GraphShadowValidation.h"
#include "PackedSchedule.h"
#include <memory>

namespace heating::control {
// New explicitly negotiated logical SHADOW contract. Not the existing pinned
// seasonal.shadow.v1 policy and NOT physical installation/actuator authority.
struct NativePlanZoneSource {
    SeasonalZoneSource policy;
    std::string groupId,emitter,actuatorProfile,sensorResource,outputResource;
    std::string reportEvidence="physical_report";
    uint32_t maximumSensorAgeMs=120000;
    int16_t minimumSupplyCentiC=2000,maximumSupplyCentiC=5500;
};
struct NativePlanInstallationSource {
    static constexpr const char* contract="control.plan.v1";
    static constexpr const char* weekContract="control.plan.week.v1";
    static constexpr const char* kind="installation.shadow.v1";
    static constexpr size_t maximumZones=2,maximumTransitions=8;
    std::string controllerId,adapterId,profileDigest;
    std::array<NativePlanZoneSource,maximumZones> zones;
    size_t count=0;
    // Independent SOURCE-reviewed extension; never accepted from configuration.
    bool legacyReadbackReviewed=false;
    bool weekReviewed=false;
    const char* planContract()const {return weekReviewed?weekContract:contract;}
    // Explicit local SOURCE lineage, READBACK ONLY. No restored zones/grants.
    // One predecessor; no recursive history or additional persisted config key.
    std::shared_ptr<const NativePlanInstallationSource> predecessor;
    static constexpr const char* evolutionCapability="control.plan.profile_evolution.v1";
    static constexpr const char* legacyCapability="control.plan.legacy_readback.v1";
    uint32_t maximumSafetyAgeMs=0,mappingRevision=1;
    bool valid() const {
        using namespace heating::graph_test;
        if(!SessionAdmission::validId(controllerId)||!SessionAdmission::validId(adapterId)
            ||!hex(profileDigest)||(weekReviewed?(!count||count>maximumZones):count!=maximumZones)||!mappingRevision
            ||maximumSafetyAgeMs<1000||maximumSafetyAgeMs>120000
            ||(weekReviewed&&legacyReadbackReviewed))return false;
        if(predecessor&&(predecessor.get()==this||predecessor->predecessor
            ||legacyReadbackReviewed||predecessor->legacyReadbackReviewed||!predecessor->valid()
            ||predecessor->controllerId!=controllerId||predecessor->adapterId!=adapterId
            ||predecessor->profileDigest==profileDigest||predecessor->mappingRevision==UINT32_MAX
            ||mappingRevision!=predecessor->mappingRevision+1))return false;
        std::set<std::string> ids{"adapter","config","snapshot"},resources;
        bool floor=false,radiator=false;
        for(size_t i=0;i<count;++i) {
            const auto& z=zones[i];const auto& p=z.policy;
            if(p.zoneId.size()!=8||!hex(p.zoneId,8)||!SessionAdmission::validId(p.sensorId)
                ||!SessionAdmission::validId(p.actuatorId)||!SessionAdmission::validId(z.groupId)
                ||!p.control.valid()||!p.seasonal.valid()
                ||p.minimumTargetCentiC<500||p.maximumTargetCentiC>3500||p.minimumTargetCentiC>p.maximumTargetCentiC
                ||(p.seasonal.frostAdviceReviewed&&(p.seasonal.frostTargetCentiC<p.minimumTargetCentiC
                    ||p.seasonal.frostTargetCentiC>p.maximumTargetCentiC))
                ||z.maximumSensorAgeMs<1000||z.maximumSensorAgeMs>120000
                ||z.minimumSupplyCentiC<500||z.maximumSupplyCentiC>9000||z.minimumSupplyCentiC>=z.maximumSupplyCentiC
                ||!hex(z.sensorResource)||!hex(z.outputResource)
                ||(z.reportEvidence!="physical_report"&&z.reportEvidence!="validated_integration_report"))return false;
            for(const auto& id:{p.zoneId,p.sensorId,p.actuatorId,z.groupId})
                if(!ids.insert(id).second)return false;
            for(const auto& r:{z.sensorResource,z.outputResource})if(!resources.insert(r).second)return false;
            if(z.emitter=="radiator"&&z.actuatorProfile=="trv_room_setpoint"&&p.control.mode==ZoneControl::localTrv&&(weekReviewed||!radiator))radiator=true;
            else if(z.emitter=="floor"&&z.actuatorProfile=="binary_valve"&&p.control.mode==ZoneControl::slowBinaryPi&&(weekReviewed||!floor))floor=true;
            else return false;
        }
        return weekReviewed||(floor&&radiator);
    }
    const NativePlanZoneSource* zone(std::string_view id)const {
        for(size_t i=0;i<count;++i)if(zones[i].policy.zoneId==id)return &zones[i];
        return nullptr;
    }
};

// Exact complete durable plan, not a projected schema1 configuration. Caller
// consumes zones in this SAME parsed config, persists identical bytes and
// authenticates the independent SOURCE policy before any session is opened.
inline bool validateNativeControlPlan(const cJSON* config,const NativePlanInstallationSource& source,
                                     const heating::graph_test::Hash& hash) {
    using namespace heating::graph_test;
    try {
        need(source.valid()&&bool(hash),"native_source_invalid");
        if(source.weekReviewed) {
            object(config,{"groups","mapping","mapping_digest","mode","plan_contract","profile_digest","revision","schema","zones"});
            literal(get(config,"plan_contract"),NativePlanInstallationSource::weekContract,"native_week_contract");
        } else object(config,{"groups","mapping","mapping_digest","mode","profile_digest","revision","schema","zones"});
        need(integer(get(config,"schema"),2,2)==2,"unsupported_schema");
        literal(get(config,"mode"),"shadow_plan","unsupported_schema");
        literal(get(config,"profile_digest"),source.profileDigest.c_str(),"profile_conflict");
        integer(get(config,"revision"),1,UINT32_MAX);
        const auto mapping=get(config,"mapping");
        object(mapping,{"channels","mapping_revision","mapping_schema"});
        integer(get(mapping,"mapping_schema"),2,2);
        need(integer(get(mapping,"mapping_revision"),1,UINT32_MAX)==source.mappingRevision,"native_mapping_revision");
        const auto channels=get(mapping,"channels");
        need(cJSON_IsArray(channels)&&cJSON_GetArraySize(channels)==int(source.count*2),"native_mapping_limit");
        const auto mappingBytes=print(mapping),mappingDigest=hash(mappingBytes);
        need(hex(mappingDigest),"hash_fault");
        literal(get(config,"mapping_digest"),mappingDigest.c_str(),"mapping_conflict");
        std::set<std::string> resources,channelIds;
        std::string previous;
        for(auto c=channels->child;c;c=c->next) {
            object(c,{"channel_id","direction","owner_id","resource_id"});
            const auto id=str(get(c,"channel_id")),resource=str(get(c,"resource_id"));
            need(SessionAdmission::validId(id)&&id>previous&&hex(resource)
                &&resources.insert(resource).second&&channelIds.insert(id).second,"native_mapping_conflict");
            previous=id;
            const NativePlanZoneSource* selected=nullptr;bool sensor=false;
            for(size_t i=0;i<source.count;++i) {
                const auto& z=source.zones[i];
                if(id==z.policy.sensorId){selected=&z;sensor=true;break;}
                if(id==z.policy.actuatorId){selected=&z;break;}
            }
            need(selected,"native_mapping_conflict");
            literal(get(c,"direction"),sensor?"input":"output","native_mapping_conflict");
            literal(get(c,"owner_id"),sensor?selected->policy.zoneId.c_str():selected->policy.actuatorId.c_str(),"native_mapping_conflict");
            literal(get(c,"resource_id"),sensor?selected->sensorResource.c_str():selected->outputResource.c_str(),"native_mapping_conflict");
        }
        const auto groups=get(config,"groups");
        need(cJSON_IsArray(groups)&&cJSON_GetArraySize(groups)==int(source.count),"native_group_limit");
        previous.clear();
        for(auto g=groups->child;g;g=g->next) {
            object(g,{"emitter","group_id","maximum_supply_centi_c","minimum_supply_centi_c"});
            const auto id=str(get(g,"group_id"));need(id>previous,"native_group_conflict");previous=id;
            const NativePlanZoneSource* selected=nullptr;
            for(size_t i=0;i<source.count;++i)if(source.zones[i].groupId==id)selected=&source.zones[i];
            need(selected,"native_group_conflict");
            literal(get(g,"emitter"),selected->emitter.c_str(),"native_group_conflict");
            need(integer(get(g,"minimum_supply_centi_c"),500,8999)==selected->minimumSupplyCentiC
                &&integer(get(g,"maximum_supply_centi_c"),501,9000)==selected->maximumSupplyCentiC,"native_group_profile_conflict");
        }
        const auto zones=get(config,"zones");
        need(cJSON_IsArray(zones)&&cJSON_GetArraySize(zones)==int(source.count),"native_zone_limit");
        previous.clear();size_t transitions=0;
        for(auto z=zones->child;z;z=z->next) {
            const auto id=str(get(z,"zone_id"));need(id>previous,"native_zone_conflict");previous=id;
            const auto pin=source.zone(id);need(pin,"native_zone_conflict");
            literal(get(z,"sensor_id"),pin->policy.sensorId.c_str(),"native_binding_conflict");
            literal(get(z,"actuator_id"),pin->policy.actuatorId.c_str(),"native_binding_conflict");
            literal(get(z,"group_id"),pin->groupId.c_str(),"native_binding_conflict");
            literal(get(z,"actuator_profile"),pin->actuatorProfile.c_str(),"native_profile_conflict");
            literal(get(z,"report_evidence"),pin->reportEvidence.c_str(),"native_evidence_conflict");
            integer(get(z,"base_centi_c"),pin->policy.minimumTargetCentiC,pin->policy.maximumTargetCentiC);
            integer(get(z,"max_age_ms"),1000,pin->maximumSensorAgeMs);
            const auto schedule=get(z,"schedule");
            if(!cJSON_IsNull(schedule)) {
                const auto ts=get(schedule,"transitions");
                need(cJSON_IsArray(ts),"schedule");
                if(source.weekReviewed) {
                    literal(get(schedule,"policy"),packedSchedulePolicy,"native_week_schedule");
                    need(forEachPackedTransition(schedule,[&](int64_t,int16_t,size_t){++transitions;return true;}),"native_compact_schedule");
                    need(transitions<=2*UtcSchedule::maximumTransitions,"native_transition_limit");
                } else {
                    transitions+=static_cast<size_t>(cJSON_GetArraySize(ts));
                    need(transitions<=NativePlanInstallationSource::maximumTransitions,"native_transition_limit");
                }
            }
        }
        return true;
    } catch(const Failure& e) {
        if(std::string_view(e.code)=="hash_fault"||std::string_view(e.code)=="allocation")throw;
        return false;
    }
}
}
