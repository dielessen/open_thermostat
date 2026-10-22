#pragma once
#include "BoundedJson.h"
#include <array>
#include <cstdint>
#include <cstddef>

namespace heating::control {
inline constexpr const char* metricsCapability="metrics.observation_total.v2";
inline constexpr uint64_t metricsIntervalMs=30000,metricsExpiryMs=45000;
inline constexpr size_t maximumMetricsBytes=1024,maximumMetricsEnvelopeBytes=2048;
inline constexpr std::array<const char*,8> legacyMetricFields{
    "totalEnergyUsedKwh","heatingEnergyUsedKwh","warmWaterEnergyUsedKwh","unattributedEnergyUsedKwh",
    "warmWaterUsage","warmWaterAvgFlow","warmWaterFlow","observedBurnerSeconds"};
inline constexpr std::array<const char*,8> versionedMetricFields{
    "totalEnergyUsedKwhV2","heatingEnergyUsedKwhV2","warmWaterEnergyUsedKwhV2","unattributedEnergyUsedKwhV2",
    "warmWaterUsageV2","warmWaterAvgFlowV2","warmWaterFlowV2","observedBurnerSecondsV2"};
// Fixed observational schema only: never an arbitrary JSON/config/secret relay.
inline bool validMetricsSnapshot(const cJSON* root) {
    const auto get=[&](const char* key){return cJSON_GetObjectItemCaseSensitive(root,key);};
    const auto text=[&](const char* key,const char* expected){
        auto p=get(key);return cJSON_IsString(p)&&p->valuestring&&!std::strcmp(p->valuestring,expected);};
    if(!cJSON_IsObject(root)||cJSON_GetArraySize(root)!=24
        || !cJSON_IsNumber(get("metricsSchema"))||get("metricsSchema")->valuedouble!=2
        || !text("counterDefinition","observation-total-v2")||!text("counterScope","boot")
        || !text("energyQuality","estimated_nominal_modulation")||!text("protocolScope","plus")
        || !text("flowQuality","reported_integrated")) return false;
    for(auto key:legacyMetricFields)if(!cJSON_IsNull(get(key)))return false;
    for(auto key:versionedMetricFields) {
        auto p=get(key);
        if(!cJSON_IsNull(p)&&(!cJSON_IsNumber(p)||!std::isfinite(p->valuedouble)||p->valuedouble<0))return false;
    }
    auto power=get("powerFresh"),outdoor=get("outdoorTemperature");
    return (cJSON_IsTrue(power)||cJSON_IsFalse(power))
        && (cJSON_IsNull(outdoor)||(cJSON_IsNumber(outdoor)&&std::isfinite(outdoor->valuedouble)
            &&outdoor->valuedouble>=-100&&outdoor->valuedouble<=100));
}
}
