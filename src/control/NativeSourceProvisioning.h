#pragma once
#include "BoundedJson.h"
#include "NativeControlPlan.h"
#include <memory>
#include <new>

namespace heating::control {
// Local authenticated SETTINGS only. This descriptor selects logical SHADOW
// policy, never a physical protection/report/readiness/actuator qualification.
// Config, MQTT packets and DATA advertisements MUST NOT call this factory.
inline std::unique_ptr<NativePlanInstallationSource> nativeSourceFromLocalSettingsBase(
        const cJSON* compact,std::string_view controller,std::string_view adapter,
        const heating::graph_test::Hash& hash) {
    using namespace heating::graph_test;
    try {
        need(bool(hash)&&cJSON_IsArray(compact)&&cJSON_GetArraySize(compact)==7,"local_source_shape");
        auto at=[](const cJSON* a,int i){return cJSON_GetArrayItem(a,i);};
        const auto tag=str(at(compact,0));
        const bool week=tag=="native.source.local.week.v1";
        need(week||tag=="native.source.local.v1","local_source_version");
        need(str(at(compact,1))==controller&&str(at(compact,2))==adapter,"local_source_owner");
        const auto layout=str(at(compact,3));need(hex(layout),"local_source_layout");
        const auto revision=integer(at(compact,4),1,UINT32_MAX);
        need(cJSON_IsBool(at(compact,5)),"local_source_legacy");
        const bool legacy=cJSON_IsTrue(at(compact,5));
        need(!(legacy&&week),"local_source_week_legacy");
        const auto zones=at(compact,6);
        need(cJSON_IsArray(zones)&&(week?(cJSON_GetArraySize(zones)>=1&&cJSON_GetArraySize(zones)<=2):cJSON_GetArraySize(zones)==2),"local_source_two_rooms");
        auto source=std::make_unique<NativePlanInstallationSource>();
        source->controllerId=std::string(controller);source->adapterId=std::string(adapter);
        source->mappingRevision=revision;source->legacyReadbackReviewed=legacy;source->weekReviewed=week;
        source->count=static_cast<size_t>(cJSON_GetArraySize(zones));source->maximumSafetyAgeMs=2000;
        Json expanded(cJSON_CreateObject(),cJSON_Delete);need(bool(expanded),"allocation");
        auto text=[](cJSON* o,const char* k,const std::string& s){need(cJSON_AddStringToObject(o,k,s.c_str()),"allocation");};
        auto number=[](cJSON* o,const char* k,int64_t n){need(cJSON_AddNumberToObject(o,k,n),"allocation");};
        text(expanded.get(),"adapter_id",std::string(adapter));
        text(expanded.get(),"controller_id",std::string(controller));
        text(expanded.get(),"kind",week?"native_profile.week.v1":legacy?"native_profile.shadow.v2":"native_profile.shadow.v1");
        text(expanded.get(),"layout_digest",layout);
        if(legacy)text(expanded.get(),"legacy_readback","schema1_quarantine_only");
        number(expanded.get(),"mapping_revision",revision);number(expanded.get(),"schema",week?3:legacy?2:1);
        auto out=cJSON_AddArrayToObject(expanded.get(),"zones");need(out,"allocation");
        std::string previous;
        for(size_t i=0;i<source->count;++i) {
            const auto row=at(zones,i);need(cJSON_IsArray(row)&&cJSON_GetArraySize(row)==14,"local_source_zone_shape");
            auto& z=source->zones[i];auto& p=z.policy;
            p.zoneId=str(at(row,0));need(p.zoneId>previous,"local_source_zone_order");previous=p.zoneId;
            p.sensorId=str(at(row,1));p.actuatorId=str(at(row,2));z.groupId=str(at(row,3));
            const bool floor=integer(at(row,4),0,1)==1;
            z.emitter=floor?"floor":"radiator";z.actuatorProfile=floor?"binary_valve":"trv_room_setpoint";
            z.sensorResource=str(at(row,5));z.outputResource=str(at(row,6));
            p.minimumTargetCentiC=integer(at(row,7),500,3500);p.maximumTargetCentiC=integer(at(row,8),500,3500);
            z.maximumSensorAgeMs=integer(at(row,9),1000,120000);
            z.minimumSupplyCentiC=integer(at(row,10),500,8999);z.maximumSupplyCentiC=integer(at(row,11),501,9000);
            z.reportEvidence=integer(at(row,12),0,1)?"validated_integration_report":"physical_report";
            const auto control=at(row,13);need(cJSON_IsArray(control)&&cJSON_GetArraySize(control)==6,"local_source_control");
            auto& c=p.control;c.mode=floor?ZoneControl::slowBinaryPi:ZoneControl::localTrv;
            c.cycleMs=integer(at(control,0),0,3600000);
            c.hysteresisCentiC=integer(at(control,1),1,200);
            c.kiPermillePerCMinute=integer(at(control,2),0,1000);
            c.kpPermillePerC=integer(at(control,3),0,1000);
            c.minimumOffMs=integer(at(control,4),0,1800000);c.minimumOnMs=integer(at(control,5),0,1800000);
            need(floor||(!c.cycleMs&&!c.kiPermillePerCMinute&&!c.kpPermillePerC&&!c.minimumOffMs&&!c.minimumOnMs),"local_source_control");
            // Only logical SOURCE policy. Actual runtime safety remains UNKNOWN
            // without an independent supported producer; no GUI all-safe bit.
            p.seasonal.enabled=p.seasonal.installationQualified=true;
            p.seasonal.maximumSensorAgeMs=z.maximumSensorAgeMs;p.seasonal.maximumStepGapMs=300000;
            auto o=cJSON_CreateObject();need(o,"allocation");cJSON_AddItemToArray(out,o);
            // Canonical field order matches the existing HA NativePlanSource.
            text(o,"actuator_id",p.actuatorId);text(o,"actuator_profile",z.actuatorProfile);
            auto co=cJSON_AddObjectToObject(o,"control");need(co,"allocation");
            number(co,"cycle_ms",c.cycleMs);number(co,"hysteresis_centi_c",c.hysteresisCentiC);
            number(co,"ki_permille_per_c_minute",c.kiPermillePerCMinute);number(co,"kp_permille_per_c",c.kpPermillePerC);
            number(co,"minimum_off_ms",c.minimumOffMs);number(co,"minimum_on_ms",c.minimumOnMs);
            text(co,"mode",floor?"slow_binary_pi":"local_trv");
            text(o,"emitter",z.emitter);text(o,"group_id",z.groupId);
            number(o,"maximum_sensor_age_ms",z.maximumSensorAgeMs);number(o,"maximum_supply_centi_c",z.maximumSupplyCentiC);
            number(o,"maximum_target_centi_c",p.maximumTargetCentiC);number(o,"minimum_supply_centi_c",z.minimumSupplyCentiC);
            number(o,"minimum_target_centi_c",p.minimumTargetCentiC);text(o,"output_resource",z.outputResource);
            text(o,"report_evidence",z.reportEvidence);text(o,"sensor_id",p.sensorId);
            text(o,"sensor_resource",z.sensorResource);text(o,"zone_id",p.zoneId);
        }
        const auto expandedBytes=print(expanded.get());
        need(expandedBytes.size()<=4096,"local_source_budget");
        source->profileDigest=hash(expandedBytes);
        need(source->valid(),"local_source_invalid");
        return source;
    } catch(const Failure&) {return nullptr;}
      catch(const std::bad_alloc&) {return nullptr;}
}
}

namespace heating::control {
// Separately reviewed one-generation lineage. Decode only plain descriptors,
// not recursive envelopes. Hashes identify actual independently validated pins.
inline std::unique_ptr<NativePlanInstallationSource> nativeSourceFromLocalSettings(
        const cJSON* compact,std::string_view controller,std::string_view adapter,
        const heating::graph_test::Hash& hash) {
    try {
        if(cJSON_IsArray(compact)&&cJSON_GetArraySize(compact)==3) {
            const auto tag=cJSON_GetArrayItem(compact,0);
            if(!cJSON_IsString(tag)||std::string_view(tag->valuestring)!="native.source.evolution.v1")return nullptr;
            auto old=nativeSourceFromLocalSettingsBase(cJSON_GetArrayItem(compact,1),controller,adapter,hash);
            auto next=nativeSourceFromLocalSettingsBase(cJSON_GetArrayItem(compact,2),controller,adapter,hash);
            if(!old||!next)return nullptr;
            next->predecessor=std::shared_ptr<const NativePlanInstallationSource>(std::move(old));
            return next->valid()?std::move(next):nullptr;
        }
        return nativeSourceFromLocalSettingsBase(compact,controller,adapter,hash);
    } catch(const std::bad_alloc&) {return nullptr;}
}
// Actual saved-settings entry, bounded BEFORE parser/string allocation. Same
// function is used by the production transport and the finite integration peer.
inline std::unique_ptr<NativePlanInstallationSource> nativeSourceFromSavedDescriptor(
        std::string_view bytes,std::string_view controller,std::string_view adapter,
        const heating::graph_test::Hash& hash) {
    if(bytes.empty()||bytes.size()>=2048)return nullptr;
    try {
        const auto parsed=parseControlJson(bytes);
        return parsed?nativeSourceFromLocalSettings(parsed.get(),controller,adapter,hash):nullptr;
    } catch(const std::bad_alloc&) {return nullptr;}
}
// Old cached forms omit the new field: omission never removes a saved SOURCE.
// Explicit null is a deliberate NONE selection on the existing settings form.
inline bool retainNativeSourceSetting(const cJSON* previous,cJSON* candidate) {
    const auto old=cJSON_GetObjectItemCaseSensitive(previous,"native_shadow_source");
    if(!old||cJSON_IsNull(old))return true;
    if(!cJSON_IsObject(candidate))return false;
    if(cJSON_GetObjectItemCaseSensitive(candidate,"native_shadow_source"))return true;
    auto copy=cJSON_Duplicate(old,true);
    if(!copy)return false;
    if(!cJSON_AddItemToObject(candidate,"native_shadow_source",copy)){cJSON_Delete(copy);return false;}
    return true;
}
inline bool nativeSourceSettingValid(const cJSON* mqtt,std::string_view controller,
                                     const heating::graph_test::Hash& hash) {
    const auto doc=cJSON_GetObjectItemCaseSensitive(mqtt,"native_shadow_source");
    if(!doc||cJSON_IsNull(doc))return true;
    const auto adapter=cJSON_GetObjectItemCaseSensitive(mqtt,"adapter_id");
    if(!cJSON_IsString(adapter)||!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(mqtt,"modern_shadow")))return false;
    return bool(nativeSourceFromLocalSettings(doc,controller,adapter->valuestring,hash));
}
// An explicit evolution must name the EXACT old local descriptor. This only
// permits its readback quarantine, never old control/actuator authority.
inline bool nativeSourceReplacementAllowed(const cJSON* previous,const cJSON* candidate) {
    const auto old=cJSON_GetObjectItemCaseSensitive(previous,"native_shadow_source");
    const auto next=cJSON_GetObjectItemCaseSensitive(candidate,"native_shadow_source");
    if(!old||cJSON_IsNull(old)||(next&&cJSON_IsNull(next))||(next&&cJSON_Compare(old,next,true)))return true;
    const auto oldCurrent=(cJSON_IsArray(old)&&cJSON_GetArraySize(old)==3
        &&cJSON_IsString(cJSON_GetArrayItem(old,0))
        &&std::string_view(cJSON_GetArrayItem(old,0)->valuestring)=="native.source.evolution.v1")
        ?cJSON_GetArrayItem(old,2):old;
    return cJSON_IsArray(next)&&cJSON_GetArraySize(next)==3
        &&cJSON_IsString(cJSON_GetArrayItem(next,0))
        &&std::string_view(cJSON_GetArrayItem(next,0)->valuestring)=="native.source.evolution.v1"
        &&(cJSON_Compare(oldCurrent,cJSON_GetArrayItem(next,1),true)
            ||(oldCurrent!=old&&cJSON_Compare(cJSON_GetArrayItem(old,1),cJSON_GetArrayItem(next,1),true)));
}
// Explicit hot SOURCE selection cannot smuggle a network/owner/device change.
// Copy only bounded already-parsed settings; never change saved caller trees.
inline bool nativeSourceNeedsExplicitApply(const cJSON* previous,const cJSON* next) {
    const auto a=cJSON_GetObjectItemCaseSensitive(previous,"native_shadow_source");
    const auto b=cJSON_GetObjectItemCaseSensitive(next,"native_shadow_source");
    return a&&!cJSON_IsNull(a)&&b&&!cJSON_IsNull(b)&&!cJSON_Compare(a,b,true);
}
inline bool nativeSourceOnlySettingsChange(const cJSON* previous,const cJSON* next) {
    if(!cJSON_IsObject(previous)||!cJSON_IsObject(next))return false;
    heating::graph_test::Json old(cJSON_Duplicate(previous,true),cJSON_Delete),candidate(cJSON_Duplicate(next,true),cJSON_Delete);
    if(!old||!candidate)return false;
    auto a=cJSON_GetObjectItemCaseSensitive(old.get(),"mqtt");
    auto b=cJSON_GetObjectItemCaseSensitive(candidate.get(),"mqtt");
    if(!cJSON_IsObject(a)||!cJSON_IsObject(b))return false;
    const auto oldSource=cJSON_GetObjectItemCaseSensitive(a,"native_shadow_source");
    const auto newSource=cJSON_GetObjectItemCaseSensitive(b,"native_shadow_source");
    if(!cJSON_IsArray(oldSource)||!cJSON_IsArray(newSource))return false;
    cJSON_DeleteItemFromObjectCaseSensitive(a,"native_shadow_source");
    cJSON_DeleteItemFromObjectCaseSensitive(b,"native_shadow_source");
    return cJSON_Compare(old.get(),candidate.get(),true);
}
// Ephemeral startup settings identity, bounded by existing2048B. It is NOT
// persisted or an authority token. Ignore ONLY source selection; retain all
// broker/device/secrets/unknown future fields so pending network edits block hot
// apply. cJSON comparison tolerates field order, not changed values.
inline heating::graph_test::Json nativeSourceNetworkBase(const cJSON* settings) {
    using namespace heating::graph_test;
    Json copy(cJSON_IsObject(settings)?cJSON_Duplicate(settings,true):nullptr,cJSON_Delete);
    if(!copy)return copy;
    auto mq=cJSON_GetObjectItemCaseSensitive(copy.get(),"mqtt");
    if(!cJSON_IsObject(mq))return Json(nullptr,cJSON_Delete);
    cJSON_DeleteItemFromObjectCaseSensitive(mq,"native_shadow_source");
    return copy;
}
inline bool nativeSourceNetworkStillCurrent(std::string_view base,std::string_view saved) {
    if(base.empty()||base.size()>=2048||saved.empty()||saved.size()>=2048)return false;
    try {
        const auto before=parseControlJson(base,true),current=parseControlJson(saved,true);
        const auto filtered=current?nativeSourceNetworkBase(current.get()):heating::graph_test::Json(nullptr,cJSON_Delete);
        return before&&filtered&&cJSON_Compare(before.get(),filtered.get(),true);
    } catch(const std::bad_alloc&) {return false;} // read-only eligibility must fail before settings mutation.
}

inline bool nativeNetworkSettingsBytesFit(std::string_view encoded) {return !encoded.empty()&&encoded.size()<2048;}
}
