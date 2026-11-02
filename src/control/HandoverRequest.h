#pragma once
#include <cJSON.h>
#include <memory>
#include <optional>
#include <string_view>
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
// Giving control back is a safety action: the factory-password gate (WebAuthSession.h
// passwordChangeRequired) never blocks it. Exactly what the Rooms page sends to stop:
// POST /config/heating/handover {"thermostat_disconnected":false}, then POST
// /config/heating with the current plan (as GET answers it) and "mode":"shadow", nothing
// else changed. Taking control (true) or any other plan change is not a hand-back.
inline bool handBackRequest(std::string_view path, const cJSON* body, const cJSON* currentPlan) {
    if (path == "/config/heating/handover") {
        const auto disconnected = handoverRequest(body);
        return disconnected && !*disconnected;
    }
    if (path != "/config/heating" || !cJSON_IsObject(body) || !cJSON_IsObject(currentPlan)) return false;
    const cJSON* mode = cJSON_GetObjectItemCaseSensitive(body, "mode");
    if (!cJSON_IsString(mode) || std::string_view(mode->valuestring) != "shadow") return false;
    using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
    Json request(cJSON_Duplicate(body, true), cJSON_Delete), current(cJSON_Duplicate(currentPlan, true), cJSON_Delete);
    if (!request || !current) return false;
    cJSON_DeleteItemFromObjectCaseSensitive(request.get(), "mode");
    cJSON_DeleteItemFromObjectCaseSensitive(current.get(), "mode");
    return cJSON_Compare(request.get(), current.get(), true) != 0;
}
}
