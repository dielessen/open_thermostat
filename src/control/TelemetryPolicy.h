#pragma once
#include <cJSON.h>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string_view>

namespace heating::control {
// When a telemetry topic goes out (docs/modern-thermostat/TELEMETRIEBUDGET.nl.md
// section 4): on a real change (deadbands), at most every minMs; otherwise every
// refreshMs; once after every (re)connect. Pure: the transport owns the clock.
struct TelemetryCadence {
    uint32_t minMs, refreshMs;
};
inline constexpr TelemetryCadence stateCadence{10000, 300000},       // rooms, heating, boiler, Bluetooth
    fieldsCadence{60000, 900000},                                       // boiler field groups
    learnedCadence{60000, 900000},                                      // learned/<room>: a new result
    summaryCadence{300000, 300000},                                     // summary, ems metrics
    configCadence{0, 3600000};                                          // plan and entities: on change
// Payload limits: a message fits the socket's send buffer in one go.
inline constexpr size_t telemetrySoftBytes = 1024, telemetryHardBytes = 1536;

struct TelemetrySlot {
    uint64_t sentAt = 0;
    uint32_t hash = 0;
    bool sent = false;  // since the last (re)connect
    void reset() { sent = false; }
    // changed: the payload differs beyond its deadbands (or, without, at all).
    bool due(uint64_t now, const TelemetryCadence& c, bool changed) const {
        if (!sent || now < sentAt) return true;
        if (now - sentAt >= c.refreshMs) return true;
        return changed && now - sentAt >= c.minMs;
    }
    void mark(uint64_t now, uint32_t h) { sentAt = now; hash = h; sent = true; }
};

inline uint32_t telemetryHash(std::string_view s) {
    uint32_t h = 2166136261u;
    for (const char c : s) h = (h ^ uint8_t(c)) * 16777619u;
    return h;
}

// key: absolute deadband for that member's numbers (0: any change); a negative
// band ignores the member (an age that grows every second).
struct Deadband {
    const char* key;
    double band;
};
inline constexpr Deadband roomBands[] = {{"temperature", 0.1}};
inline constexpr Deadband bleBands[] = {{"temperature", 0.1}, {"humidity", 1}, {"age_s", -1}};
inline constexpr Deadband heatingBands[] = {{"flow_c", 1}, {"input_age_s", -1}, {"age_s", -1}, {"listened_s", -1}};
// learned/<room>: a new result, not the advice that follows the room minute by minute.
inline constexpr Deadband learnedBands[] = {{"now", -1}, {"plan", -1}};

namespace telemetry_detail {
inline double bandOf(const Deadband* rules, size_t n, const char* key) {
    for (size_t i = 0; key && i < n; ++i) if (!std::strcmp(rules[i].key, key)) return rules[i].band;
    return 0;
}
inline bool differs(const cJSON* a, const cJSON* b, double band, const Deadband* rules, size_t n) {
    if (!a || !b) return a != b;
    if ((a->type & 0xFF) != (b->type & 0xFF)) return true;
    if (cJSON_IsNumber(a)) return band > 0 ? std::fabs(a->valuedouble - b->valuedouble) >= band - 1e-9 : a->valuedouble != b->valuedouble;
    if (cJSON_IsString(a)) return std::strcmp(a->valuestring ? a->valuestring : "", b->valuestring ? b->valuestring : "") != 0;
    if (cJSON_IsArray(a)) {
        if (cJSON_GetArraySize(a) != cJSON_GetArraySize(b)) return true;
        for (const cJSON *x = a->child, *y = b->child; x && y; x = x->next, y = y->next)
            if (differs(x, y, band, rules, n)) return true;
        return false;
    }
    if (!cJSON_IsObject(a)) return false;  // true/false/null: the type said it
    size_t members = 0;
    for (const cJSON* x = a->child; x; x = x->next) {
        const double own = bandOf(rules, n, x->string);
        if (own < 0) continue;
        ++members;
        if (differs(x, cJSON_GetObjectItemCaseSensitive(b, x->string), own, rules, n)) return true;
    }
    for (const cJSON* y = b->child; y; y = y->next) if (bandOf(rules, n, y->string) >= 0) --members;
    return members != 0;  // a member came or went
}
}
// Whether `now` differs from `before` beyond the deadbands. Unparsable: changed.
template <size_t N>
inline bool changedBeyond(std::string_view before, const cJSON* now, const Deadband (&rules)[N]) {
    if (before.empty() || !now) return true;
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> old(cJSON_ParseWithLength(before.data(), before.size()), cJSON_Delete);
    return !old || telemetry_detail::differs(old.get(), now, 0, rules, N);
}

// Boiler field groups and the boiler state: [index, raw, observed_ms, quality,
// type] rows. A new observation of the same value is no change; raw by its own
// deadband (bands(index), raw units), quality and type exactly.
template <class Bands>
inline bool boilerFieldsChanged(std::string_view before, const cJSON* now, Bands&& bands) {
    if (before.empty() || !now) return true;
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> old(cJSON_ParseWithLength(before.data(), before.size()), cJSON_Delete);
    const auto rows = [](const cJSON* o) { return cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(o, "values"), "fields"); };
    const cJSON *a = old ? rows(old.get()) : nullptr, *b = rows(now);
    const auto text = [](const cJSON* o, const char* k) { const cJSON* v = cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(o, "values"), k); return cJSON_IsString(v) ? std::string_view(v->valuestring) : std::string_view(); };
    if (!cJSON_IsArray(a) || !cJSON_IsArray(b) || cJSON_GetArraySize(a) != cJSON_GetArraySize(b) || text(old.get(), "profile") != text(now, "profile")) return true;
    for (const cJSON *x = a->child, *y = b->child; x && y; x = x->next, y = y->next) {
        if (cJSON_GetArraySize(x) != 5 || cJSON_GetArraySize(y) != 5) return true;
        const cJSON* index = cJSON_GetArrayItem(y, 0);
        for (int k : {0, 1, 3, 4}) {
            const double band = k == 1 && cJSON_IsNumber(index) ? bands(size_t(index->valuedouble)) : 0;
            if (telemetry_detail::differs(cJSON_GetArrayItem(x, k), cJSON_GetArrayItem(y, k), band, nullptr, 0)) return true;
        }
    }
    return false;
}
}
