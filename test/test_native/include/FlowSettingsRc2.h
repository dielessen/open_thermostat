#pragma once
// Frozen copy of FlowSettings (src/control/FlowPolicy.h) as released in E32
// v1.0.0-rc.2 (commit 88edbb8), struct renamed, plus rc.2's FlowSettingsNvs::read
// (src/FlowSettingsStore.h) without the NVS calls. Only for the rollback test: a
// flow record written by newer firmware must still be read by rc.2. Do not edit.
#include "control/BoundedJson.h"
#include "control/ControlTuning.h"
#include "control/WeatherCurve.h"
#include <cJSON.h>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
namespace heating::control {
struct FlowSettingsRc2 {
    bool weatherCurve = false; // item 19: the weather curve sets the flow
    bool applyLearned = false; // item 6: the learned lowest flow and optimum start set the request
    uint8_t designFlowC = 0;   // curve flow at -10 degC outdoor; 0: by emitter (floor 40, radiator 55)
    ControlTuning tuning;
    uint16_t manual = 0;       // bit i: knobs()[i] is the owner's; else AutoTuner sets it
    static constexpr size_t maxBytes = 95 + 11 + ControlTuning::maxBytes + 20 + 7 * 26; // stored as one NVS string
    // POST /config/heating/flow: the whole record as GET answers it (~0.55 KB at the widest)
    // posts back, also pretty-printed; still bounded (and at most 2 levels deep).
    static constexpr size_t postMaxBytes = 1024;
    // Any of "weather_curve", "apply_learned" (bool), "curve_design_flow_c" (0 or
    // 25..80), "tuning" (ControlTuning::parse; an automatic knob given away from
    // its built-in value becomes manual, null: built-in and all automatic) and
    // "tuning_manual" (the manual knobs exactly; an automatic one forgets the
    // owner's value) on top of `out`; nullptr on success, else the API error name.
    // A record without "tuning_manual" (1.0 before rc.2): what differs is manual.
    static const char* parse(const cJSON* root, FlowSettingsRc2& out) {
        if (!cJSON_IsObject(root) || !root->child) return "invalid_request";
        FlowSettingsRc2 s = out;
        size_t n; const auto* k = ControlTuning::knobs(n);
        const cJSON* exact = nullptr;
        for (const cJSON* c = root->child; c; c = c->next) {
            if (!c->string) return "invalid_request";
            if (!std::strcmp(c->string, "weather_curve") || !std::strcmp(c->string, "apply_learned")) {
                if (!cJSON_IsBool(c)) return "invalid_value";
                (c->string[0] == 'w' ? s.weatherCurve : s.applyLearned) = cJSON_IsTrue(c);
            } else if (!std::strcmp(c->string, "curve_design_flow_c")) {
                const double v = cJSON_IsNumber(c) ? c->valuedouble : -1;
                if (!(v == 0 || (v >= WeatherCurve::minDesignFlowC && v <= WeatherCurve::maxDesignFlowC)) || v != double(int(v))) return "invalid_value";
                s.designFlowC = static_cast<uint8_t>(v);
            } else if (!std::strcmp(c->string, "tuning")) {
                if (const char* e = ControlTuning::parse(c, s.tuning)) return e;
                if (cJSON_IsNull(c)) s.manual = 0;
                const ControlTuning built;
                for (size_t i = 0; i < n; ++i)
                    if ((ControlTuning::autoKnobs >> i & 1) && cJSON_GetObjectItemCaseSensitive(c, k[i].key) && s.tuning.*k[i].field != built.*k[i].field)
                        s.manual |= uint16_t(1u << i);
            } else if (!std::strcmp(c->string, "tuning_manual")) {
                if (!cJSON_IsArray(c)) return "invalid_value";
                exact = c;
            } else return "invalid_key";
        }
        if (exact) {
            uint16_t mask = 0;
            for (const cJSON* e = exact->child; e; e = e->next) {
                size_t i = 0;
                while (i < n && !(cJSON_IsString(e) && !std::strcmp(e->valuestring, k[i].key))) ++i;
                if (i == n || !(ControlTuning::autoKnobs >> i & 1)) return "invalid_value";
                mask |= uint16_t(1u << i);
            }
            const ControlTuning built;
            for (size_t i = 0; i < n; ++i) if ((ControlTuning::autoKnobs >> i & 1) && !(mask >> i & 1)) s.tuning.*k[i].field = built.*k[i].field;
            s.manual = mask;
        }
        out = s;
        return nullptr;
    }
    // shown: the knobs to report as "tuning" (GET: those in effect); nullptr: the owner's (the record).
    std::string json(const ControlTuning* shown = nullptr) const {
        char text[96];
        std::snprintf(text, sizeof text, "{\"weather_curve\":%s,\"apply_learned\":%s,\"curve_design_flow_c\":%u,\"tuning\":",
                      weatherCurve ? "true" : "false", applyLearned ? "true" : "false", unsigned(designFlowC));
        std::string out = text + (shown ? *shown : tuning).json() + ",\"tuning_manual\":[";
        size_t n; const auto* k = ControlTuning::knobs(n);
        for (size_t i = 0, first = 1; i < n; ++i) if (manual >> i & 1) { out += first ? "\"" : ",\""; out += k[i].key; out += '"'; first = 0; }
        return out + "]}";
    }
    bool operator==(const FlowSettingsRc2& o) const {
        return weatherCurve == o.weatherCurve && applyLearned == o.applyLearned && designFlowC == o.designFlowC && tuning == o.tuning && manual == o.manual;
    }
};
// rc.2 FlowSettingsNvs::read: nvs_get_str into maxBytes + 1 bytes (a longer
// string is ESP_ERR_NVS_INVALID_LENGTH: the defaults), then the first JSON
// document of the text (cJSON_ParseWithLength does not require the end).
inline bool readFlowRecordRc2(const std::string& stored, FlowSettingsRc2& out) {
    if (stored.size() + 1 > FlowSettingsRc2::maxBytes + 1) return false;
    char text[FlowSettingsRc2::maxBytes + 1] = {};
    std::memcpy(text, stored.c_str(), stored.size() + 1);
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(parseNestedJson(text, std::strlen(text)));
    FlowSettingsRc2 parsed;
    if (!root || FlowSettingsRc2::parse(root.get(), parsed)) return false;
    out = parsed;
    return true;
}
}
