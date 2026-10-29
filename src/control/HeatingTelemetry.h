#pragma once
#include "control/FlowLearner.h"
#include "control/WarmupPlanner.h"
#include <cJSON.h>
#include <cstring>
#include <initializer_list>
#include <algorithm>
#include <memory>
#include <optional>
#include <string>
namespace heating::control {
// Parts of /status/heating and its MQTT form fw/telemetry/heating (ModernTransport
// drops a payload over heatingTelemetryMaxBytes = 4096). Pure: no IO or clock.

// What HeatingController knows around the learner for "learned".
struct LearnedContext {
    std::optional<int64_t> utc;                           // trusted clock: "plans"
    const std::optional<int16_t>* temperatures = nullptr; // fresh reading per plan room
    std::optional<int16_t> outdoorCentiC;
    const char* outdoorSource = nullptr;                  // "boiler", "ha" or nullptr (none)
    uint64_t now = 0;                                     // uptime ms
};
// A gas meter counts as connected while its last total is at most 2 h old
// (DSMR 4 meters report gas once an hour).
inline constexpr uint64_t gasMeterFreshMs = 2 * 3600000ull;

// "learned": FlowLearner::json() plus "inputs" {"gas_meter","gas_price","outdoor",
// "boiler_kw","boiler_kw_source","gas_kwh_per_m3","gas_kwh_per_m3_source"} (what HA could still add) and, with a trusted
// clock, "plans" from WarmupPlanner. nullptr: no memory.
inline cJSON* learnedJson(const FlowLearner& learner, const RoomPlan& plan, const LearnedContext& c) {
    cJSON* root = learner.json();
    if (!root) return nullptr;
    cJSON* inputs = cJSON_AddObjectToObject(root, "inputs");
    const auto gasAt = learner.gasMeterAt();
    if (!inputs || !cJSON_AddBoolToObject(inputs, "gas_meter", gasAt && *gasAt <= c.now && c.now - *gasAt <= gasMeterFreshMs)
        || !cJSON_AddBoolToObject(inputs, "gas_price", learner.price().has_value())
        || !(c.outdoorSource ? cJSON_AddStringToObject(inputs, "outdoor", c.outdoorSource) : cJSON_AddNullToObject(inputs, "outdoor"))
        || !cJSON_AddNumberToObject(inputs, "boiler_kw", learnmath::round(double(learner.nominalKw()) * 10) / 10)
        || !cJSON_AddStringToObject(inputs, "boiler_kw_source", learner.nominalFromHa() ? "ha" : "default")
        || !cJSON_AddNumberToObject(inputs, "gas_kwh_per_m3", learnmath::round(double(learner.params().kwhPerM3) * 1000) / 1000)
        || !cJSON_AddStringToObject(inputs, "gas_kwh_per_m3_source", learner.kwhPerM3FromHa() ? "ha" : "default")) {
        cJSON_Delete(root); return nullptr;
    }
    if (!c.utc || !c.temperatures) return root;
    cJSON* plans = WarmupPlanner::json(learner, plan, *c.utc, c.temperatures, c.outdoorCentiC);
    if (!plans || !cJSON_AddItemToObject(root, "plans", plans)) { cJSON_Delete(plans); cJSON_Delete(root); return nullptr; }
    return root;
}

// "ha": {"input_age_s": seconds since the last accepted ha/heating_input (null:
// none this boot), "broker_connected": bool}, for the rooms page banner.
inline bool addHaLink(cJSON* root, std::optional<uint64_t> lastInputMs, uint64_t now, bool brokerConnected) {
    cJSON* ha = cJSON_AddObjectToObject(root, "ha");
    if (!ha) return false;
    const bool known = lastInputMs && *lastInputMs <= now;
    if (!(known ? cJSON_AddNumberToObject(ha, "input_age_s", double((now - *lastInputMs) / 1000))
                : cJSON_AddNullToObject(ha, "input_age_s"))) return false;
    return cJSON_AddBoolToObject(ha, "broker_connected", brokerConnected) != nullptr;
}

namespace telemetry_detail {
inline void keepOnly(cJSON* o, std::initializer_list<const char*> keys) {
    if (!cJSON_IsObject(o)) return;
    for (cJSON* c = o->child; c;) {
        cJSON* next = c->next;
        bool keep = false;
        for (const char* k : keys) keep = keep || (c->string && !std::strcmp(c->string, k));
        if (!keep) cJSON_Delete(cJSON_DetachItemViaPointer(o, c));
        c = next;
    }
}
}

// Learned room in its MQTT form: id, emitter, readiness, segments, periods,
// loss_per_h, capacity_kwh_per_k, "advice" with only the 1 degC shortfall and "now".
inline void compactLearnedRoom(cJSON* r) {
    using telemetry_detail::keepOnly;
    keepOnly(r, {"id", "emitter", "readiness", "segments", "periods", "loss_per_h", "capacity_kwh_per_k", "advice", "now"});
    cJSON* advice = cJSON_GetObjectItemCaseSensitive(r, "advice");
    for (cJSON* a = cJSON_IsArray(advice) ? advice->child : nullptr; a;) {
        cJSON* next = a->next;
        const cJSON* s = cJSON_GetObjectItemCaseSensitive(a, "shortfall_c");
        if (!cJSON_IsNumber(s) || s->valuedouble != 1) cJSON_Delete(cJSON_DetachItemViaPointer(advice, a));
        a = next;
    }
}
// Plan room in its MQTT form: {"id","optimum_start":{"reason","predicted_start_utc",
// "lead_minutes","flow_c","confidence","reachable","start_now"},"night":{"reason",
// "recommended","recommended_night_c","saving_m3","saving_eur"}} (fields of an
// unplanned reason are absent, as in the full form).
inline void compactPlanRoom(cJSON* p) {
    using telemetry_detail::keepOnly;
    keepOnly(p, {"id", "optimum_start", "night"});
    keepOnly(cJSON_GetObjectItemCaseSensitive(p, "optimum_start"),
             {"reason", "predicted_start_utc", "lead_minutes", "flow_c", "confidence", "reachable", "start_now"});
    keepOnly(cJSON_GetObjectItemCaseSensitive(p, "night"), {"reason", "recommended", "recommended_night_c", "saving_m3", "saving_eur"});
}

// fw/telemetry/heating: /status/heating without what only the page reads.
// Always the same shape (HA entities must not flap):
//  - rooms[]: no static plan fields fallback/minimum/maximum_centi_c (HA reads them
//    from the plan; inactive_until stays: HA 0.4.0b9 reads it here);
//  - shadow: no past days;
//  - learned: only the header schema, applied, status, heating_periods, inputs
//    (rooms and plans go per room to fw/telemetry/heating_learned/<id>);
//  - dhw: method, clock_known and today (no last_7_days).
inline void compactHeatingTelemetry(cJSON* status) {
    using telemetry_detail::keepOnly;
    if (!cJSON_IsObject(status)) return;
    const cJSON* rooms = cJSON_GetObjectItemCaseSensitive(status, "rooms");
    for (cJSON* r = cJSON_IsArray(rooms) ? rooms->child : nullptr; r; r = r->next)
        for (const char* key : {"fallback_centi_c", "minimum_centi_c", "maximum_centi_c"})
            cJSON_DeleteItemFromObjectCaseSensitive(r, key);
    cJSON_DeleteItemFromObjectCaseSensitive(cJSON_GetObjectItemCaseSensitive(status, "shadow"), "days");
    keepOnly(cJSON_GetObjectItemCaseSensitive(status, "learned"), {"schema", "applied", "status", "heating_periods", "inputs"});
    keepOnly(cJSON_GetObjectItemCaseSensitive(status, "dhw"), {"method", "clock_known", "today"});
}

// fw/telemetry/heating_learned/<room id>: {"schema":1,"id":..,"learned":{compact
// learned room},"plan":{compact plan room}|null}; plan is null without a trusted
// clock. Empty: no such room or no memory.
inline std::string learnedRoomTelemetry(const FlowLearner& learner, const RoomPlan& plan, size_t room, const LearnedContext& c) {
    if (room >= plan.rooms.size() || room >= learner.rooms()) return {};
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
    cJSON* learned = root ? learner.roomJson(room) : nullptr;
    if (!learned || !cJSON_AddNumberToObject(root.get(), "schema", 1) || !cJSON_AddStringToObject(root.get(), "id", plan.rooms[room].id.c_str())
        || !cJSON_AddItemToObject(root.get(), "learned", learned)) { cJSON_Delete(learned); return {}; }
    compactLearnedRoom(learned);
    cJSON* p = c.utc && c.temperatures ? WarmupPlanner::roomJson(learner, plan, room, *c.utc, c.temperatures[room], c.outdoorCentiC) : nullptr;
    if (p) { if (!cJSON_AddItemToObject(root.get(), "plan", p)) { cJSON_Delete(p); return {}; } compactPlanRoom(p); }
    else if (c.utc && c.temperatures) return {};          // no memory
    else if (!cJSON_AddNullToObject(root.get(), "plan")) return {};
    char* text = cJSON_PrintUnformatted(root.get());
    std::string out = text ? text : "";
    cJSON_free(text);
    return out;
}

// Round robin over the rooms: at most `perTick` distinct rooms per call, so
// with 8 rooms and 2 per 15 s tick every room is published at least every 60 s.
struct RoomRotation {
    size_t next = 0;
    template <class Publish> void tick(size_t rooms, size_t perTick, Publish&& publish) {
        for (size_t k = 0; k < std::min(rooms, perTick); ++k) {
            if (next >= rooms) next = 0;
            publish(next++);
        }
    }
};
// MQTT topic-safe room id (RoomPlan ids: [a-z0-9_]{1,32}).
inline bool topicSafeRoomId(const std::string& id) {
    if (id.empty() || id.size() > 32) return false;
    for (const char ch : id) if (!((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '_')) return false;
    return true;
}
}
