#pragma once
#include "BoundedJson.h"
#include "EMS/EmsEntityTable.h"
#include <array>
#include <cstdint>
namespace heating::control {
inline constexpr const char* boilerFieldsCapability="boiler.fields.v1";
inline constexpr size_t boilerFieldCount=69,boilerFieldsPerGroup=10,boilerFieldGroupCount=7;
inline constexpr size_t maximumBoilerGroupBytes=1200,maximumBoilerEnvelopeBytes=2048;
// boiler.fields.v2: the same route, extended with whole groups 7.. holding one
// field per EMS entity of ems::entityCatalog, from index 70 (groups 0-6 stay
// exactly v1). Sent only after HA announces support.
inline constexpr const char* boilerFieldsV2Capability="boiler.fields.v2";
inline constexpr size_t catalogFieldBase=70;
inline constexpr size_t boilerFieldGroupCountV2=7+(ems::entityFieldCount+9)/10;
inline constexpr uint8_t catalogFieldQuality=0; // reported values; offsets follow the EMS-ESP reference
inline constexpr uint64_t boilerGroupIntervalMs=2000,maximumBoilerTimestamp=9007199254740991ULL;
inline constexpr std::array<uint16_t,69> boilerFieldSourceTypes{24,24,24,25,24,24,24,24,24,24,24,24,24,51,52,52,22,51,25,25,25,25,52,52,24,24,22,22,22,52,24,24,24,24,24,24,24,24,25,25,25,25,25,22,22,22,22,22,22,22,22,22,51,51,51,51,51,51,51,51,52,52,52,52,52,52,52,52,52};
inline constexpr std::array<uint8_t,69> boilerFieldQualities{0,0,0,0,0,0,0,1,1,1,0,2,2,0,0,1,0,0,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,1,1,1,1,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1};
inline constexpr std::array<int32_t,69> boilerFieldMinimums{-6000,-6000,-6000,-6000,0,0,0,0,0,0,0,0,0,-6000,-6000,0,0,0,0,0,0,0,0,0,0,0,0,0,-6000,-6000,-6000,-6000,0,0,0,0,0,0,-6000,-6000,-6000,0,0,-128,-128,0,0,0,0,-128,-128,-6000,-128,0,-128,0,0,-6000,0,0,-6000,-6000,0,0,0,0,0,0,0};
inline constexpr std::array<int32_t,69> boilerFieldMaximums{13000,13000,13000,13000,100,100,254,1,1,1,255,1,1,13000,13000,254,1,1,16777214,16777214,16777214,16777214,16777214,16777214,65535,65534,100,16777214,13000,13000,13000,13000,65534,1,1,1,1,1,13000,50000,13000,100,16777214,254,254,16777214,100,100,65534,254,254,13000,254,1,254,1,65534,13000,65534,65534,13000,13000,65534,1,1,1,1,1,1};
inline bool validBoilerGroup(const cJSON* root,size_t group,bool extended=false) {
    const bool catalog=group>=boilerFieldGroupCount;
    if(group>=(extended?boilerFieldGroupCountV2:boilerFieldGroupCount)||!cJSON_IsObject(root)||cJSON_GetArraySize(root)!=4)return false;
    const auto get=[&](const char* k){return cJSON_GetObjectItemCaseSensitive(root,k);};
    const auto integer=[](const cJSON* p,double lo,double hi){return cJSON_IsNumber(p)&&std::isfinite(p->valuedouble)
        &&p->valuedouble>=lo&&p->valuedouble<=hi&&std::floor(p->valuedouble)==p->valuedouble;};
    if(!integer(get("schema"),1,1)||!integer(get("sampled_at_ms"),0,maximumBoilerTimestamp))return false;
    auto profile=get("profile");if(!cJSON_IsString(profile)||!profile->valuestring)return false;
    const std::string_view p=profile->valuestring;
    if(p!="classic_observed"&&p!="plus_observed"&&p!="unknown"&&p!="conflicting_families")return false;
    auto fields=get("fields");const size_t begin=group*boilerFieldsPerGroup;
    const size_t count=catalog?std::min(boilerFieldsPerGroup,catalogFieldBase+ems::entityFieldCount-begin)
        :std::min(boilerFieldsPerGroup,boilerFieldCount-begin);
    if(!cJSON_IsArray(fields)||cJSON_GetArraySize(fields)!=int(count))return false;
    for(size_t i=0;i<count;++i) {
        auto f=cJSON_GetArrayItem(fields,i);if(!cJSON_IsArray(f)||cJSON_GetArraySize(f)!=5)return false;
        const auto at=[&](int n){return cJSON_GetArrayItem(f,n);};
        if(!integer(at(0),begin+i,begin+i)||!integer(at(3),0,2))return false;
        const size_t index=begin+i;
        if(cJSON_IsNull(at(2))) {
            if(!cJSON_IsNull(at(1))||!integer(at(4),0,0)||!integer(at(3),0,0))return false;
        } else if(catalog) {
            const size_t field=index-catalogFieldBase;
            const auto& spec=ems::entityCatalog[ems::entityFieldRows[field]];
            if(!integer(at(2),0,get("sampled_at_ms")->valuedouble)||!integer(at(3),catalogFieldQuality,catalogFieldQuality)
                ||!integer(at(4),0,65535)||!ems::entityFieldType(field,static_cast<uint16_t>(at(4)->valuedouble))
                ||(!cJSON_IsNull(at(1))&&!integer(at(1),spec.minimum,spec.maximum)))return false;
        } else if(!integer(at(2),0,get("sampled_at_ms")->valuedouble)
            ||!integer(at(3),boilerFieldQualities[begin+i],boilerFieldQualities[begin+i])
            ||!integer(at(4),boilerFieldSourceTypes[begin+i],boilerFieldSourceTypes[begin+i])
            ||(!cJSON_IsNull(at(1))&&!integer(at(1),boilerFieldMinimums[begin+i],boilerFieldMaximums[begin+i])))return false;
        if(begin+i==24&&cJSON_IsNumber(at(1))) {
            const auto code=static_cast<uint16_t>(at(1)->valuedouble);
            if((code>>8)<32||(code>>8)>126||(code&255)<32||(code&255)>126)return false;
        }
    }
    return true;
}
}
