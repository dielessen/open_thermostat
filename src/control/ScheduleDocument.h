#pragma once
#include "UtcSchedule.h"
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <string_view>

namespace heating::control {

// Decodes an already bounded JSON payload, not a transport/session admission.
// The caller retains tree ownership. Reject ambiguous/extra members rather than
// accepting a partial schedule. cJSON numbers are checked BEFORE narrowing.
inline bool configureScheduleDocument(UtcSchedule &schedule, const cJSON *document) {
    if (!cJSON_IsObject(document)) return false;
    constexpr const char *keys[]{"timezone", "policy", "valid_from_utc", "valid_until_utc",
                                  "base_centi_c", "transitions"};
    bool seen[6]{};
    for (auto item = document->child; item; item = item->next) {
        bool known = false;
        for (std::size_t i = 0; i < 6; ++i) {
            if (item->string && !std::strcmp(item->string, keys[i])) {
                if (seen[i]) return false;
                seen[i] = true; known = true; break;
            }
        }
        if (!known) return false;
    }
    for (bool present : seen) if (!present) return false;
    const auto member = [document](const char *name) { return cJSON_GetObjectItemCaseSensitive(document, name); };
    const auto literal = [](const cJSON *item, std::string_view expected) {
        return cJSON_IsString(item) && item->valuestring && expected == item->valuestring;
    };
    if (!(literal(member("timezone"), "UTC") || literal(member("timezone"), "Europe/Amsterdam")) ||
        !literal(member("policy"), "wall-clock-membership/v1")) return false;
    const auto integer = [](const cJSON *item, int64_t low, int64_t high) {
        return cJSON_IsNumber(item) && std::isfinite(item->valuedouble) &&
            item->valuedouble >= low && item->valuedouble <= high && std::floor(item->valuedouble) == item->valuedouble;
    };
    const auto from = member("valid_from_utc"), until = member("valid_until_utc"), base = member("base_centi_c");
    if (!integer(from, UtcSchedule::minimumUtcSecond, UtcSchedule::maximumUtcSecond) ||
        !integer(until, UtcSchedule::minimumUtcSecond, UtcSchedule::maximumUtcSecond) ||
        !integer(base, 500, 3500)) return false;
    const auto list = member("transitions");
    if (!cJSON_IsArray(list)) return false;
    const int count = cJSON_GetArraySize(list);
    if (count < 1 || count > static_cast<int>(UtcSchedule::maximumTransitions)) return false;
    std::array<ScheduleTransition, UtcSchedule::maximumTransitions> transitions;
    int i = 0;
    for (auto pair = list->child; pair; pair = pair->next, ++i) {
        if (!cJSON_IsArray(pair) || cJSON_GetArraySize(pair) != 2) return false;
        auto at = pair->child, temperature = at->next;
        if (!integer(at, UtcSchedule::minimumUtcSecond, UtcSchedule::maximumUtcSecond) ||
            !integer(temperature, 500, 3500)) return false;
        transitions[i] = {static_cast<int64_t>(at->valuedouble), static_cast<int16_t>(temperature->valuedouble)};
    }
    return schedule.configure(static_cast<int64_t>(from->valuedouble), static_cast<int64_t>(until->valuedouble),
                              static_cast<int16_t>(base->valuedouble), transitions.data(), count);
}
}
