#pragma once
#include <cJSON.h>
#include <optional>
namespace heating::control {
// POST /config/heating/handover: exactly {"thermostat_disconnected":true|false}.
// The beta.18 key "tado_disconnected" stays accepted for older pages/scripts.
// nullopt: not such a request.
inline std::optional<bool> handoverRequest(const cJSON* root) {
    if (!cJSON_IsObject(root) || cJSON_GetArraySize(root) != 1) return std::nullopt;
    const cJSON* value = cJSON_GetObjectItemCaseSensitive(root, "thermostat_disconnected");
    if (!value) value = cJSON_GetObjectItemCaseSensitive(root, "tado_disconnected");
    if (!cJSON_IsBool(value)) return std::nullopt;
    return cJSON_IsTrue(value) != 0;
}
}
