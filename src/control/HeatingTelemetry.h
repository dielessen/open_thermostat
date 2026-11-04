#pragma once
#include "control/BurnerCycleMonitor.h"
#include "control/FlowLearner.h"
#include "control/FlowPolicy.h"
#include "control/WarmupPlanner.h"
#include <cJSON.h>
#include <cstring>
#include <functional>
#include <initializer_list>
#include <algorithm>
#include <memory>
#include <optional>
#include <string>
namespace heating::control {
// Parts of /status/heating and its MQTT forms fw/telemetry/heating, .../heating_summary
// and .../heating_learned/<room id> (ModernTransport: heatingTelemetryMaxBytes). Pure.

// What HeatingController knows around the learner for "learned".
struct LearnedContext {
    std::optional<int64_t> utc;                           // trusted clock: "plans"
    const std::optional<int16_t>* temperatures = nullptr; // fresh reading per plan room
    std::optional<int16_t> outdoorCentiC;
    const char* outdoorSource = nullptr;                  // "boiler", "ha" or nullptr (none)
    uint64_t now = 0;                                     // uptime ms
    const ArrivalLearner* arrival = nullptr;              // rc.4: the arrival feedback (FlowPolicy::arrival())
    const FreeHeat* freeHeat = nullptr;                   // rc.5 (P3): "free_heat" per room (FlowPolicy::freeHeat())
};
// rc.5 (P3): the budget of fw/telemetry/learned/<id> (TELEMETRIEBUDGET.nl.md; the tests, fuzz_room_plan
// and the soak check it), counted as if the room id had its maximum of 32 characters.
inline constexpr size_t learnedRoomBytes = 1100; // rc.5: a judged morning, long reasons and free heat with a 32-character id (the rc.4 soak saw 1018 B at 1000); above 1024 B the message only counts as "large", the hard limit is 1536
// A gas meter counts as connected while its last total is at most 2 h old
// (DSMR 4 meters report gas once an hour).
inline constexpr uint64_t gasMeterFreshMs = 2 * 3600000ull;

// "inputs": what HA delivered to the learner, so HA and the page can show what
// is missing: {"gas_meter","gas_price","outdoor":"boiler"|"ha"|null,"boiler_kw",
// "boiler_kw_source":"default"|"ha","gas_kwh_per_m3","gas_kwh_per_m3_source"}.
inline bool addLearnedInputs(cJSON* parent, const FlowLearner& learner, const LearnedContext& c) {
    cJSON* inputs = cJSON_AddObjectToObject(parent, "inputs");
    const auto gasAt = learner.gasMeterAt();
    return inputs && cJSON_AddBoolToObject(inputs, "gas_meter", gasAt && *gasAt <= c.now && c.now - *gasAt <= gasMeterFreshMs)
        && cJSON_AddBoolToObject(inputs, "gas_price", learner.price().has_value())
        && (c.outdoorSource ? cJSON_AddStringToObject(inputs, "outdoor", c.outdoorSource) : cJSON_AddNullToObject(inputs, "outdoor"))
        && cJSON_AddNumberToObject(inputs, "boiler_kw", learnmath::round(double(learner.nominalKw()) * 10) / 10)
        && cJSON_AddStringToObject(inputs, "boiler_kw_source", learner.nominalFromHa() ? "ha" : "default")
        && cJSON_AddNumberToObject(inputs, "gas_kwh_per_m3", learnmath::round(double(learner.params().kwhPerM3) * 1000) / 1000)
        && cJSON_AddStringToObject(inputs, "gas_kwh_per_m3_source", learner.kwhPerM3FromHa() ? "ha" : "default");
}

// "gas": the gas calibration (GasCalibration::json): status, confidence, factor,
// kW at full modulation and whether it comes from the meter or boiler_kw
// (compact: without the interval counts, for heating_summary).
inline bool addGasCalibration(cJSON* parent, const FlowLearner& learner, const LearnedContext& c, bool compact = false) {
    cJSON* gas = cJSON_AddObjectToObject(parent, "gas");
    return gas && learner.gas().json(gas, c.now, gasMeterFreshMs, learner.nominalKw(), compact);
}

// "learned" (/status/heating): FlowLearner::json() plus "inputs", "gas" and, with a
// trusted clock, "plans" from WarmupPlanner. nullptr: no memory.
inline cJSON* learnedJson(const FlowLearner& learner, const RoomPlan& plan, const LearnedContext& c) {
    cJSON* root = learner.json();
    if (!root) return nullptr;
    if (!addLearnedInputs(root, learner, c) || !addGasCalibration(root, learner, c)) { cJSON_Delete(root); return nullptr; }
    // rc.5 (P3): each room's "free_heat" (the page's per-room learned detail).
    const cJSON* rooms = cJSON_GetObjectItemCaseSensitive(root, "rooms");
    size_t i = 0;
    for (cJSON* r = c.freeHeat && cJSON_IsArray(rooms) ? rooms->child : nullptr; r; r = r->next, ++i)
        if (!c.freeHeat->addJson(r, i)) { cJSON_Delete(root); return nullptr; }
    if (!c.utc || !c.temperatures) return root;
    cJSON* plans = WarmupPlanner::json(learner, plan, *c.utc, c.temperatures, c.outdoorCentiC, c.arrival);
    if (!plans || !cJSON_AddItemToObject(root, "plans", plans)) { cJSON_Delete(plans); cJSON_Delete(root); return nullptr; }
    return root;
}

// "ha": {"input_age_s": seconds since the last accepted ha/heating_input (null:
// none this boot), "broker_connected": bool}, for the rooms page banner. P22, only once
// there is something to say: "last_rejected": {"reason", "age_s"} of the last refused
// message (HeatingInputRoute::Rejection) and "resubscribed_s": seconds since the E32
// subscribed ha/heating_input again after 15 silent minutes (HaInputSilence).
inline bool addHaLink(cJSON* root, std::optional<uint64_t> lastInputMs, uint64_t now, bool brokerConnected,
                      const char* rejectedReason = nullptr, uint64_t rejectedAtMs = 0,
                      std::optional<uint64_t> resubscribedMs = std::nullopt) {
    cJSON* ha = cJSON_AddObjectToObject(root, "ha");
    if (!ha) return false;
    const bool known = lastInputMs && *lastInputMs <= now;
    if (!(known ? cJSON_AddNumberToObject(ha, "input_age_s", double((now - *lastInputMs) / 1000))
                : cJSON_AddNullToObject(ha, "input_age_s"))) return false;
    if (!cJSON_AddBoolToObject(ha, "broker_connected", brokerConnected)) return false;
    if (rejectedReason && rejectedAtMs <= now) {
        cJSON* rejected = cJSON_AddObjectToObject(ha, "last_rejected");
        if (!rejected || !cJSON_AddStringToObject(rejected, "reason", rejectedReason)
            || !cJSON_AddNumberToObject(rejected, "age_s", double((now - rejectedAtMs) / 1000))) return false;
    }
    return !(resubscribedMs && *resubscribedMs <= now)
        || cJSON_AddNumberToObject(ha, "resubscribed_s", double((now - *resubscribedMs) / 1000)) != nullptr;
}

// "burner": {"starts_last_hour","heating_starts_last_hour","short_cycling","activity"};
// while unknown the same keys are null (the MQTT shape stays). Partial: no memory.
// activity: what the boiler does now (DhwEpisodes::activity: tapping, keep_warm,
// charging, hot_water, heating, idle), so Home Assistant can draw a timeline.
inline void addBurnerJson(cJSON* root, const BurnerCycleMonitor::Summary& c, const char* activity = nullptr) {
    cJSON* burner = cJSON_AddObjectToObject(root, "burner");
    if (!burner) return;
    const auto count = [&](const char* key, size_t n) {
        if (c.known) cJSON_AddNumberToObject(burner, key, double(n)); else cJSON_AddNullToObject(burner, key);
    };
    count("starts_last_hour", c.starts);
    count("heating_starts_last_hour", c.heatingStarts);
    if (c.known) cJSON_AddBoolToObject(burner, "short_cycling", c.shortCycling); else cJSON_AddNullToObject(burner, "short_cycling");
    if (activity) cJSON_AddStringToObject(burner, "activity", activity); else cJSON_AddNullToObject(burner, "activity");
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

// Learned room in its MQTT form: emitter, readiness, segments, periods,
// loss_per_h, capacity_kwh_per_k, "advice" with only the 1 degC shortfall and "now"
// (no "id": the payload names its room once, HA takes the topic's).
inline void compactLearnedRoom(cJSON* r) {
    using telemetry_detail::keepOnly;
    keepOnly(r, {"emitter", "readiness", "readiness_timing", "segments", "periods", "loss_per_h", "capacity_kwh_per_k", "advice", "now"});
    cJSON* advice = cJSON_GetObjectItemCaseSensitive(r, "advice");
    for (cJSON* a = cJSON_IsArray(advice) ? advice->child : nullptr; a;) {
        cJSON* next = a->next;
        const cJSON* s = cJSON_GetObjectItemCaseSensitive(a, "shortfall_c");
        if (!cJSON_IsNumber(s) || s->valuedouble != 1) cJSON_Delete(cJSON_DetachItemViaPointer(advice, a));
        a = next;
    }
}
// Plan room in its MQTT form (no "id" either): {"optimum_start":{"reason","predicted_start_utc",
// "lead_minutes","flow_c","confidence","reachable","start_now","applies","estimate","next_switch":{"utc","target_c"}},
// "night":{"reason","recommended","recommended_night_c","saving_m3","saving_eur"},"arrival":{..}|null}
// (fields of an unplanned reason are absent, as in the full form). rc.4: "estimate" and "arrival".
inline void compactPlanRoom(cJSON* p) {
    using telemetry_detail::keepOnly;
    keepOnly(p, {"optimum_start", "night", "arrival"});
    cJSON* start = cJSON_GetObjectItemCaseSensitive(p, "optimum_start");
    keepOnly(start, {"reason", "predicted_start_utc", "lead_minutes", "flow_c", "confidence", "reachable", "start_now", "applies", "estimate", "next_switch"});
    keepOnly(cJSON_GetObjectItemCaseSensitive(start, "next_switch"), {"utc", "target_c"}); // rc.2: "to be 21 degC at 09:00"
    keepOnly(cJSON_GetObjectItemCaseSensitive(p, "night"), {"reason", "recommended", "recommended_night_c", "saving_m3", "saving_eur"});
}

// fw/telemetry/heating: /status/heating without what only the page reads.
// Always the same shape (HA entities must not flap):
//  - rooms[]: no static plan fields fallback/minimum/maximum_centi_c (HA reads them
//    from the plan; inactive_until stays: HA 0.4.0b9 reads it here);
//  - shadow: no past days;
//  - no learned and no dhw: fw/telemetry/heating_summary (header, hot water) and
//    fw/telemetry/heating_learned/<id> (per room) carry them;
//  - request.capped_by only while set (no bytes in the usual case).
inline void compactHeatingTelemetry(cJSON* status) {
    using telemetry_detail::keepOnly;
    if (!cJSON_IsObject(status)) return;
    const cJSON* rooms = cJSON_GetObjectItemCaseSensitive(status, "rooms");
    for (cJSON* r = cJSON_IsArray(rooms) ? rooms->child : nullptr; r; r = r->next)
        for (const char* key : {"fallback_centi_c", "minimum_centi_c", "maximum_centi_c"})
            cJSON_DeleteItemFromObjectCaseSensitive(r, key);
    cJSON_DeleteItemFromObjectCaseSensitive(cJSON_GetObjectItemCaseSensitive(status, "shadow"), "days");
    cJSON_DeleteItemFromObjectCaseSensitive(status, "learned");
    cJSON_DeleteItemFromObjectCaseSensitive(status, "dhw");
    // request.capped_by only while the boiler's limit lowers the request (HA reads a missing key as none).
    cJSON* request = cJSON_GetObjectItemCaseSensitive(status, "request");
    if (cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(request, "capped_by"))) cJSON_DeleteItemFromObjectCaseSensitive(request, "capped_by");
}

// fw/telemetry/heating_summary: {"schema":1,"learned":{"schema":1,"applied":bool,
// "status":..,"heating_periods":..,["boiler_minimum_flow_c":..,]"inputs":{..},"gas":{..}},"dhw":{"method","clock_known",
// "today":{..}},"flow":{..},"night_gas":{..}}. dhw: DhwEpisodes::summaryJson() (taken
// over); flow and night_gas: FlowPolicy::addSummary() (with a policy). Empty: no memory.
// more: further parts (HeatingController: the self-tuning's "tuning", sent apart as
// fw/telemetry/tuning); false: no memory.
inline std::string heatingSummaryTelemetry(const FlowLearner& learner, const LearnedContext& c, cJSON* dhw,
                                           const FlowPolicy* policy = nullptr, const std::function<bool(cJSON*)>& more = nullptr) {
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> owned(dhw, cJSON_Delete);
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
    cJSON* learned = root && dhw && cJSON_AddNumberToObject(root.get(), "schema", 1) ? cJSON_AddObjectToObject(root.get(), "learned") : nullptr;
    if (!learned || !cJSON_AddNumberToObject(learned, "schema", 1)
        || !cJSON_AddBoolToObject(learned, "applied", learner.applied()) || !cJSON_AddStringToObject(learned, "status", learner.status())
        || !cJSON_AddNumberToObject(learned, "heating_periods", learner.heatingPeriods())
        || (learner.learnedMinimumC() && !cJSON_AddNumberToObject(learned, "boiler_minimum_flow_c", learner.learnedMinimumC()))
        || !addLearnedInputs(learned, learner, c) || !addGasCalibration(learned, learner, c, true)) return {};
    telemetry_detail::keepOnly(dhw, {"method", "clock_known", "today"});
    if (!cJSON_AddItemToObject(root.get(), "dhw", owned.release())) { cJSON_Delete(dhw); return {}; }
    if (policy && !policy->addSummary(root.get())) return {};
    if (more && !more(root.get())) return {};
    char* text = cJSON_PrintUnformatted(root.get());
    std::string out = text ? text : "";
    cJSON_free(text);
    return out;
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
    if (c.freeHeat && !c.freeHeat->addJson(learned, room)) return {}; // rc.5 (P3), in "learned"
    cJSON* p = c.utc && c.temperatures ? WarmupPlanner::roomJson(learner, plan, room, *c.utc, c.temperatures[room], c.outdoorCentiC, c.arrival) : nullptr;
    if (p) { if (!cJSON_AddItemToObject(root.get(), "plan", p)) { cJSON_Delete(p); return {}; } compactPlanRoom(p); }
    else if (c.utc && c.temperatures) return {};          // no memory
    else if (!cJSON_AddNullToObject(root.get(), "plan")) return {};
    const auto print = [&] {
        char* text = cJSON_PrintUnformatted(root.get());
        std::string out = text ? text : "";
        cJSON_free(text);
        return out;
    };
    auto out = print();
    // rc.5 (P3): "free_heat" only while the payload keeps its budget with any room id; else it stays
    // out of this message (the page has it in /status/heating).
    if (c.freeHeat && out.size() + 32 - std::min<size_t>(32, plan.rooms[room].id.size()) > learnedRoomBytes) {
        cJSON_DeleteItemFromObjectCaseSensitive(learned, "free_heat");
        out = print();
    }
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
