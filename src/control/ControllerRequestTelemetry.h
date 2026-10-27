#pragma once
#include "BoundedJson.h"
#include <string>
#include <string_view>

namespace heating::control {
// Read-only projection of the existing local EMS snapshot. Never revive a
// legacy MQTT connection or expose unrelated fields on this native topic.
// The snapshot names the observed family ("classic_observed"); the topic keeps
// the "classic" profile value that the Home Assistant consumer already accepts.
inline std::string controllerRequestTelemetry(std::string_view status) {
    if(status.empty() || status.size()>8192)return {};
    const auto root=parseControlJson(status);
    if(!root || !cJSON_IsObject(root.get()))return {};
    const auto* profile=cJSON_GetObjectItemCaseSensitive(root.get(),"protocolProfile");
    const auto* command=cJSON_GetObjectItemCaseSensitive(root.get(),"controller_request");
    if(!cJSON_IsString(profile) || std::string_view(profile->valuestring)!="classic_observed"
       || !cJSON_IsObject(command))return {};
    static constexpr const char* keys[]={"schema","profile_id","source","boot_id","observed_at_ms",
        "known","boiler_readback","value_c","emitted_at_ms","sequence"};
    if(cJSON_GetArraySize(command)!=10)return {};
    for(const auto* key:keys)if(!cJSON_GetObjectItemCaseSensitive(command,key))return {};
    ControlJson projected(cJSON_CreateObject(),cJSON_Delete);
    if(!projected || !cJSON_AddStringToObject(projected.get(),"protocolProfile","classic"))return {};
    ControlJson copy(cJSON_Duplicate(command,true),cJSON_Delete);
    if(!copy || !cJSON_AddItemToObject(projected.get(),"controller_request",copy.get()))return {};
    copy.release();std::unique_ptr<char,decltype(&cJSON_free)> rendered(cJSON_PrintUnformatted(projected.get()),cJSON_free);
    if(!rendered)return {};
    const std::string bytes(rendered.get());
    return bytes.size()<=1024 ? bytes : std::string{};
}
}
