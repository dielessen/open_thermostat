#pragma once
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
namespace heating::control {
// The tuning knobs of active control and learning (1.0: after a week of active
// data, tuning is a settings change, not a firmware change). Stored with the flow
// options (FlowSettings "tuning", GET/POST /config/heating/flow); a record
// without them, or a missing key, gives exactly the built-in values below.
// Safety limits are not knobs: the flow ceiling (plan maximum, boiler limit,
// 80 degC), frost protection at 8/9 degC and the foreign-controller and
// measurement-loss timeouts stay fixed. Each knob has a bounded range.
struct ControlTuning {
    uint16_t minOnS = 300, minOffS = 300;     // FlowDemand: burner minimum on / off (also an optimum start's minimum on)
    uint16_t startCentiC = 20, stopCentiC = 20; // a room asks for heat from setpoint - start, until setpoint + stop
    uint16_t flowPerDegreeC = 10;             // FlowDemand: flow per degC shortfall, and per degC for 30 min (integral)
    uint16_t curveCorrectionPct = 50;         // FlowPolicy: share of the room correction on top of the weather curve
    uint16_t floorLeadMinutes = 120, radiatorLeadMinutes = 45; // WarmupPlanner: unlearned lead per degC
    uint16_t acceptPct = 100;                 // FlowLearner::Acceptance: accepted warm-up time, % of the emitter's
    uint16_t nightSavingPct = 2;              // WarmupPlanner::night: another strategy beats the program by this share (and 0.05 m3)

    struct Knob { const char* key; uint16_t ControlTuning::*field; uint16_t low, high; bool centi; }; // centi: degC, 2 decimals
    static const Knob* knobs(size_t& count) {
        static constexpr Knob table[] = {
            {"min_on_s", &ControlTuning::minOnS, 120, 1800, false},
            {"min_off_s", &ControlTuning::minOffS, 120, 1800, false},
            {"heat_start_c", &ControlTuning::startCentiC, 5, 100, true},
            {"heat_stop_c", &ControlTuning::stopCentiC, 0, 100, true},
            {"flow_per_degree_c", &ControlTuning::flowPerDegreeC, 2, 30, false},
            {"curve_correction_pct", &ControlTuning::curveCorrectionPct, 0, 100, false},
            {"floor_lead_min_per_c", &ControlTuning::floorLeadMinutes, 30, 360, false},
            {"radiator_lead_min_per_c", &ControlTuning::radiatorLeadMinutes, 10, 180, false},
            {"learned_accept_pct", &ControlTuning::acceptPct, 50, 200, false},
            {"night_saving_min_pct", &ControlTuning::nightSavingPct, 0, 20, false},
        };
        count = sizeof table / sizeof *table;
        return table;
    }
    static constexpr size_t maxBytes = 240; // json() with every knob at its widest
    // Any of the keys on top of `out` (whole numbers; degC with at most 2 decimals);
    // null: the built-in values. nullptr on success, else the API error name.
    static const char* parse(const cJSON* o, ControlTuning& out) {
        if (cJSON_IsNull(o)) { out = {}; return nullptr; }
        if (!cJSON_IsObject(o)) return "invalid_value";
        ControlTuning t = out;
        size_t n; const Knob* k = knobs(n);
        for (const cJSON* c = o->child; c; c = c->next) {
            const Knob* knob = nullptr;
            for (size_t i = 0; i < n && c->string; ++i) if (!std::strcmp(c->string, k[i].key)) knob = &k[i];
            if (!knob) return "invalid_key";
            const double scaled = cJSON_IsNumber(c) ? c->valuedouble * (knob->centi ? 100 : 1) : -1;
            const double v = std::floor(scaled + 0.5);
            if (!(std::fabs(scaled - v) < 1e-6) || v < knob->low || v > knob->high) return "invalid_value";
            t.*knob->field = static_cast<uint16_t>(v);
        }
        out = t;
        return nullptr;
    }
    // {"min_on_s":300,"min_off_s":300,"heat_start_c":0.20,...,"night_saving_min_pct":2}
    std::string json() const {
        std::string text = "{";
        size_t n; const Knob* k = knobs(n);
        for (size_t i = 0; i < n; ++i) {
            const unsigned v = this->*k[i].field;
            char part[48];
            if (k[i].centi) std::snprintf(part, sizeof part, "\"%s\":%u.%02u", k[i].key, v / 100, v % 100);
            else std::snprintf(part, sizeof part, "\"%s\":%u", k[i].key, v);
            if (i) text += ',';
            text += part;
        }
        return text + '}';
    }
    bool operator==(const ControlTuning& o) const {
        size_t n; const Knob* k = knobs(n);
        for (size_t i = 0; i < n; ++i) if (this->*k[i].field != o.*k[i].field) return false;
        return true;
    }
};
}
