#pragma once
#include "HeatingTelemetry.h"
#include "TelemetryPolicy.h"
#include <cJSON.h>
#include <string>
#include <vector>

namespace heating::control {
// The compact /status/heating (HeatingController::heatingStatusJson(true) and
// compactHeatingTelemetry) as small MQTT documents, each <= telemetrySoftBytes
// for a worst-case plan (test_heating_state_topics):
//   fw/state/heating          every top-level member except the lists below
//   fw/state/room/<id>        one room, whole ({"schema":1,..room members})
//   fw/state/ble/<id>         one paired Bluetooth sensor
//   fw/config/plan            {"schema":1,"revision","mode","rooms":[ids],"ble":[ids],"entity_parts":n}
//   fw/config/entities[/<k>]  {"schema":1,"revision","part":k,"parts":n,"entities":[..]}
//   fw/telemetry/shadow       {"schema":1,..shadow members} (today's comparison)
// Members other modules add to the status flow through unchanged.
enum class HeatingTopic : uint8_t { heating, room, ble, plan, entities, shadow };
inline constexpr size_t entityPartBytes = 800;

// emit(kind, suffix, document): the document lives until emit returns.
template <class Emit>
bool splitHeatingStatus(cJSON* status, Emit&& emit) {
    using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
    if (!cJSON_IsObject(status)) return false;
    const auto take = [&](const char* key) { return Json(cJSON_DetachItemFromObjectCaseSensitive(status, key), cJSON_Delete); };
    Json rooms = take("rooms"), ble = take("ble_sensors"), entities = take("ha_entities"), shadow = take("shadow");
    const cJSON* revision = cJSON_GetObjectItemCaseSensitive(status, "revision");
    const cJSON* mode = cJSON_GetObjectItemCaseSensitive(status, "mode");
    Json plan(cJSON_CreateObject(), cJSON_Delete);
    cJSON* roomIds = plan ? cJSON_AddArrayToObject(plan.get(), "rooms") : nullptr;
    cJSON* bleIds = roomIds ? cJSON_AddArrayToObject(plan.get(), "ble") : nullptr;
    if (!bleIds || !cJSON_AddNumberToObject(plan.get(), "schema", 1)
        || !cJSON_AddItemToObject(plan.get(), "revision", cJSON_Duplicate(revision, false))
        || !cJSON_AddItemToObject(plan.get(), "mode", cJSON_Duplicate(mode, false))) return false;
    // One document per list item, under its id (RoomPlan ids and Bluetooth hex are topic-safe).
    const auto items = [&](cJSON* list, cJSON* ids, HeatingTopic kind, const char* prefix) {
        for (cJSON* item = cJSON_IsArray(list) ? list->child : nullptr; item; item = item->next) {
            const cJSON* id = cJSON_GetObjectItemCaseSensitive(item, "id");
            if (!cJSON_IsString(id) || !topicSafeRoomId(id->valuestring)) continue;
            cJSON_AddItemToArray(ids, cJSON_CreateString(id->valuestring));
            Json doc(cJSON_CreateObject(), cJSON_Delete);
            if (!doc || !cJSON_AddNumberToObject(doc.get(), "schema", 1)) return false;
            for (const cJSON* m = item->child; m; m = m->next) cJSON_AddItemToObject(doc.get(), m->string, cJSON_Duplicate(m, true));
            emit(kind, std::string(prefix) + id->valuestring, doc.get());
        }
        return true;
    };
    if (!items(rooms.get(), roomIds, HeatingTopic::room, "fw/state/room/") || !items(ble.get(), bleIds, HeatingTopic::ble, "fw/state/ble/")) return false;
    // The entity list in parts of <= entityPartBytes, so a worst-case plan
    // (8 rooms x 5 entities of 80 characters) still makes small messages.
    std::vector<std::pair<const cJSON*, const cJSON*>> parts;
    size_t bytes = 0;
    for (const cJSON* e = cJSON_IsArray(entities.get()) ? entities->child : nullptr; e; e = e->next) {
        const size_t n = (cJSON_IsString(e) ? std::strlen(e->valuestring) : 0) + 3;
        if (parts.empty() || bytes + n > entityPartBytes) { parts.emplace_back(e, nullptr); bytes = 0; }
        parts.back().second = e->next;
        bytes += n;
    }
    if (parts.empty()) parts.emplace_back(nullptr, nullptr);
    if (!cJSON_AddNumberToObject(plan.get(), "entity_parts", double(parts.size()))) return false;
    for (size_t k = 0; k < parts.size(); ++k) {
        Json doc(cJSON_CreateObject(), cJSON_Delete);
        cJSON* list = doc ? cJSON_AddArrayToObject(doc.get(), "entities") : nullptr;
        if (!list || !cJSON_AddNumberToObject(doc.get(), "schema", 1) || !cJSON_AddItemToObject(doc.get(), "revision", cJSON_Duplicate(revision, false))
            || !cJSON_AddNumberToObject(doc.get(), "part", double(k)) || !cJSON_AddNumberToObject(doc.get(), "parts", double(parts.size()))) return false;
        for (const cJSON* e = parts[k].first; e && e != parts[k].second; e = e->next) cJSON_AddItemToArray(list, cJSON_Duplicate(e, false));
        emit(HeatingTopic::entities, k ? "fw/config/entities/" + std::to_string(k) : std::string("fw/config/entities"), doc.get());
    }
    emit(HeatingTopic::plan, std::string("fw/config/plan"), plan.get());
    if (cJSON_IsObject(shadow.get())) {
        if (!cJSON_AddNumberToObject(shadow.get(), "schema", 1)) return false;
        emit(HeatingTopic::shadow, std::string("fw/telemetry/shadow"), shadow.get());
    }
    emit(HeatingTopic::heating, std::string("fw/state/heating"), status);
    return true;
}
}
