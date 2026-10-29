#pragma once
#include "BoilerFieldTelemetry.h"
#include "TelemetryPolicy.h"
#include "EMS/ClassicBoilerMonitor.h"
#include <cJSON.h>
#include <array>
#include <string>
#include <string_view>

namespace heating::control {
// Retained boiler telemetry (TELEMETRIEBUDGET.nl.md section 4), not bound to a
// shadow session: HA keeps the last value while the E32 is alive.
//   fw/state/boiler_fields/<g>  {"schema":1,"group":g,"values":<boiler.fields.v2 group>}
//   fw/state/boiler             {"schema":1,"values":{"schema":1,"sampled_at_ms",
//                                "profile","fields":[the rows of boilerStateIndexes]}}
// Rows keep the [index, raw, observed_ms, quality, type] form; a value older
// than its field's lifetime is sent as raw null (the E32 decides freshness,
// since an unchanged value is not sent again for up to 15 minutes).
// Flow, return, modulation, pressure, burner, hot water and faults, Classic and EMS+.
inline constexpr std::array<uint8_t, 18> boilerStateIndexes{1, 2, 4, 6, 7, 11, 12, 24, 25, 78, 80, 81, 82, 83, 85, 100, 101, 102};
inline constexpr std::array<uint8_t, 6> boilerStateGroups{0, 1, 2, 7, 8, 10};
inline uint32_t boilerFieldTtlMs(size_t index) {
    if (index < boilerFieldCount) return ems::boilerFieldSpecs[index].ttlMs;
    if (index >= catalogFieldBase && index - catalogFieldBase < ems::entityFieldCount)
        return ems::entityCatalog[ems::entityFieldRows[index - catalogFieldBase]].ttlMs;
    return 0;
}
// Raw units: centi-degC (Classic), deci-degC (EMS+), percent.
inline double boilerStateBand(size_t index) {
    switch (index) {
    case 1: case 2: return 50;    // 0.5 degC
    case 78: case 83: return 5;   // 0.5 degC
    case 4: case 80: return 5;    // 5 % modulation
    default: return 0;            // pressure, burner, hot water, faults: any change
    }
}
inline double boilerFieldBand(size_t) { return 0; }
static_assert(catalogGroupCount(ems::entityFieldCount) == boilerFieldGroupCountV2);

// The group as the E32 reports it (EmsController::getBoilerFieldGroup), checked,
// its stale values nulled. nullptr: empty or invalid.
inline cJSON* boilerGroupValues(std::string_view raw, size_t group) {
    if (raw.empty() || raw.size() > maximumBoilerGroupBytes) return nullptr;
    cJSON* values = cJSON_ParseWithLength(raw.data(), raw.size());
    if (!values || !validBoilerGroup(values, group, true)) { cJSON_Delete(values); return nullptr; }
    const double sampled = cJSON_GetObjectItemCaseSensitive(values, "sampled_at_ms")->valuedouble;
    for (cJSON* row = cJSON_GetObjectItemCaseSensitive(values, "fields")->child; row; row = row->next) {
        const cJSON* observed = cJSON_GetArrayItem(row, 2);
        const size_t index = size_t(cJSON_GetArrayItem(row, 0)->valuedouble);
        if (cJSON_IsNumber(observed) && cJSON_IsNumber(cJSON_GetArrayItem(row, 1)) && sampled - observed->valuedouble > boilerFieldTtlMs(index))
            cJSON_ReplaceItemInArray(row, 1, cJSON_CreateNull());
    }
    return values;
}
inline cJSON* boilerEnvelope(cJSON* values, int group = -1) {
    cJSON* doc = values ? cJSON_CreateObject() : nullptr;
    if (!doc || !cJSON_AddNumberToObject(doc, "schema", 1) || (group >= 0 && !cJSON_AddNumberToObject(doc, "group", group))
        || !cJSON_AddItemToObject(doc, "values", values)) { cJSON_Delete(doc); cJSON_Delete(values); return nullptr; }
    return doc;
}
// fw/state/boiler from the groups that hold boilerStateIndexes; read(ss, group)
// is EmsController::getBoilerFieldGroup. nullptr: no boiler data.
template <class Read>
cJSON* boilerStateDocument(Read&& read) {
    cJSON* fields = cJSON_CreateArray();
    double sampled = 0;
    std::string profile;
    for (const auto group : boilerStateGroups) {
        std::string raw;
        read(raw, group);
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> values(boilerGroupValues(raw, group), cJSON_Delete);
        if (!values || !fields) continue;
        const double at = cJSON_GetObjectItemCaseSensitive(values.get(), "sampled_at_ms")->valuedouble;
        if (at >= sampled) { sampled = at; profile = cJSON_GetObjectItemCaseSensitive(values.get(), "profile")->valuestring; }
        for (const cJSON* row = cJSON_GetObjectItemCaseSensitive(values.get(), "fields")->child; row; row = row->next)
            for (const auto index : boilerStateIndexes)
                if (cJSON_GetArrayItem(row, 0)->valuedouble == index) { cJSON_AddItemToArray(fields, cJSON_Duplicate(row, true)); break; }
    }
    if (!fields || !cJSON_GetArraySize(fields)) { cJSON_Delete(fields); return nullptr; }
    cJSON* values = cJSON_CreateObject();
    if (!values || !cJSON_AddNumberToObject(values, "schema", 1) || !cJSON_AddNumberToObject(values, "sampled_at_ms", sampled)
        || !cJSON_AddStringToObject(values, "profile", profile.c_str()) || !cJSON_AddItemToObject(values, "fields", fields)) {
        cJSON_Delete(values); cJSON_Delete(fields); return nullptr;
    }
    return boilerEnvelope(values);
}
}
