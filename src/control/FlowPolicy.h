#pragma once
#include "control/BoundedJson.h"
#include "control/ControlTuning.h"
#include "control/FlowDemand.h"
#include "control/FlowLearner.h"
#include "control/RoomDemand.h"
#include "control/RoomPlan.h"
#include "control/WarmupPlanner.h"
#include "control/WeatherCurve.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
namespace heating::control {
// The beta.19 flow options, stored on the E32 (NVS, beside the plan) and edited
// with GET/POST /config/heating/flow.
// 1.0: with the tuning knobs (ControlTuning, "tuning"); an older record has none
// and keeps the built-in values. rc.2: per automatic knob (ControlTuning::autoKnobs)
// "set by you" (manual) or automatic (AutoTuner); "tuning" holds the owner's values.
// rc.3: both options are on unless the owner turns them off, and the E32 decides
// itself when what it learned is good enough. "Smart warm-up" (apply_learned): a
// time in the week program means "warm at that time" (learned starts and flows
// only once learned, FlowPolicy). The heating curve (weather_curve): the design
// slope until CurveLearner has its steady periods, then the learned one (rc.5: in
// between the house model's, HouseModel: heat loss over emitter output); without
// a fresh outdoor temperature the rule's flow. Before rc.3 both defaulted off and
// a record cannot tell that default from a choice: a record or backup of an older
// format (no "version" >= 2) reads both as on; one this firmware wrote keeps the
// owner's off (see stored()/readStored()).
struct FlowSettings {
    bool weatherCurve = true;  // item 19, rc.3 on by default: the weather curve sets the flow
    bool applyLearned = true;  // item 6, rc.3 "Smart warm-up": the learned lowest flow and optimum start set the request
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
    static const char* parse(const cJSON* root, FlowSettings& out) {
        if (!cJSON_IsObject(root) || !root->child) return "invalid_request";
        FlowSettings s = out;
        size_t n; const auto* k = ControlTuning::knobs(n);
        const cJSON* exact = nullptr;
        for (const cJSON* c = root->child; c; c = c->next) {
            if (!c->string) return "invalid_request";
            if (!std::strcmp(c->string, "weather_curve") || !std::strcmp(c->string, "apply_learned")) {
                if (!cJSON_IsBool(c)) return "invalid_value";
                (c->string[0] == 'w' ? s.weatherCurve : s.applyLearned) = cJSON_IsTrue(c);
            } else if (!std::strcmp(c->string, "version")) { // the record format; a newer one restores here too
                if (!cJSON_IsNumber(c) || c->valuedouble < 1 || c->valuedouble != double(int(c->valuedouble))) return "invalid_value";
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
    // The record format: 2 since rc.3 (apply_learned and weather_curve are the owner's choices).
    static constexpr int version = 2;
    // The rc.2 read buffer (its maxBytes): the stored text never grows past it, so a rollback reads it.
    static constexpr size_t rc2StoredMaxBytes = 548;
    static_assert(maxBytes == rc2StoredMaxBytes, "the NVS read buffer of this firmware and of rc.2");
    // shown: the knobs to report as "tuning" (GET: those in effect); nullptr: the owner's (the record).
    // GET, POST answers and backups: one object with "version".
    std::string json(const ControlTuning* shown = nullptr) const {
        return fields(shown) + ",\"version\":" + std::to_string(version) + "}";
    }
    // The NVS record: the object rc.2 reads (only the keys it knows: it refuses
    // any other and then falls back to its defaults), then on its own line the
    // format, which rc.2 never reads (its parser stops after the first document).
    std::string stored() const { return fields(nullptr) + "}\n{\"version\":" + std::to_string(version) + "}"; }
    // A record or backup object before rc.3 (no "version" >= 2): apply_learned and weather_curve false were defaults, not choices.
    static bool beforeSmartWarmup(const cJSON* root) {
        const cJSON* v = cJSON_GetObjectItemCaseSensitive(root, "version");
        return !cJSON_IsNumber(v) || v->valuedouble < version;
    }
    // A stored record (stored(), or rc.2's single object): false when it is not one.
    static bool readStored(const char* text, size_t size, FlowSettings& out) {
        if (!text || !size) return false;
        const char* end = static_cast<const char*>(std::memchr(text, '\n', size));
        const size_t head = end ? size_t(end - text) : size;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(parseNestedJson(std::string(text, head), true));
        FlowSettings parsed;
        if (!root || parse(root.get(), parsed)) return false;
        bool legacy = true;
        if (end) {
            std::unique_ptr<cJSON, decltype(&cJSON_Delete)> tail(parseNestedJson(std::string(end + 1, size - head - 1), true));
            legacy = !cJSON_IsObject(tail.get()) || beforeSmartWarmup(tail.get());
        }
        if (legacy) parsed.applyLearned = parsed.weatherCurve = true; // the old defaults off become on
        out = parsed;
        return true;
    }
    bool operator==(const FlowSettings& o) const {
        return weatherCurve == o.weatherCurve && applyLearned == o.applyLearned && designFlowC == o.designFlowC && tuning == o.tuning && manual == o.manual;
    }
private:
    // The rc.2 record without its closing brace.
    std::string fields(const ControlTuning* shown) const {
        char text[96];
        std::snprintf(text, sizeof text, "{\"weather_curve\":%s,\"apply_learned\":%s,\"curve_design_flow_c\":%u,\"tuning\":",
                      weatherCurve ? "true" : "false", applyLearned ? "true" : "false", unsigned(designFlowC));
        std::string out = text + (shown ? *shown : tuning).json() + ",\"tuning_manual\":[";
        size_t n; const auto* k = ControlTuning::knobs(n);
        for (size_t i = 0, first = 1; i < n; ++i) if (manual >> i & 1) { out += first ? "\"" : ",\""; out += k[i].key; out += '"'; first = 0; }
        return out + "]";
    }
};

// Per local day, the effect of the options next to the rule: while the E32
// would heat, the rule's mean flow and, at the same moments, the curve's and the
// learned flow's, plus optimum-start heating the rule did not ask for. Fixed size.
class FlowCompare {
public:
    static constexpr uint32_t maxCreditMs = 30000;
    struct Day {
        int32_t day = -1;
        uint32_t heatS = 0, ruleSum = 0, appliedSum = 0, curveS = 0, curveSum = 0, curveRuleSum = 0;
        uint32_t learnedS = 0, learnedSum = 0, learnedRuleSum = 0, startS = 0;
    };
    void sample(uint64_t now, std::optional<uint32_t> unixNow, const FlowDemand::Request& rule, const FlowDemand::Request& applied,
                std::optional<uint8_t> curve, std::optional<uint8_t> learned) {
        if (unixNow) {
            const int32_t day = RoomSchedule::localDay(*unixNow);
            if (today_.day < 0) today_.day = day;
            else if (day > today_.day) { // a day the E32 was off (or a restored older one) leaves no "yesterday"
                yesterday_ = day == today_.day + 1 ? std::optional<Day>(today_) : std::nullopt;
                today_ = {}; today_.day = day;
            }
        }
        carryMs_ += static_cast<uint32_t>(haveLast_ && now > lastMs_ ? std::min<uint64_t>(now - lastMs_, maxCreditMs) : 0);
        const uint32_t dt = carryMs_ / 1000;
        carryMs_ %= 1000; lastMs_ = now; haveLast_ = true;
        if (!dt) return;
        if (!rule.heat) { if (applied.heat) today_.startS += dt; return; }
        today_.heatS += dt; today_.ruleSum += dt * rule.flowC; today_.appliedSum += dt * applied.flowC;
        if (curve) { today_.curveS += dt; today_.curveSum += dt * *curve; today_.curveRuleSum += dt * rule.flowC; }
        if (learned) { today_.learnedS += dt; today_.learnedSum += dt * *learned; today_.learnedRuleSum += dt * rule.flowC; }
    }
    const Day& today() const { return today_; }
    const std::optional<Day>& yesterday() const { return yesterday_; }
    static bool dayJson(cJSON* parent, const char* key, const Day& d) {
        cJSON* o = cJSON_AddObjectToObject(parent, key);
        if (!o) return false;
        const auto mean = [&](const char* k, uint32_t sum, uint32_t s) {
            FlowLearner::number(o, k, s ? std::optional<float>(float(sum) / s) : std::nullopt, 10);
        };
        cJSON_AddNumberToObject(o, "heat_s", d.heatS);
        mean("rule_mean_c", d.ruleSum, d.heatS); mean("applied_mean_c", d.appliedSum, d.heatS);
        cJSON_AddNumberToObject(o, "curve_s", d.curveS);
        mean("curve_mean_c", d.curveSum, d.curveS); mean("curve_rule_mean_c", d.curveRuleSum, d.curveS);
        cJSON_AddNumberToObject(o, "learned_s", d.learnedS);
        mean("learned_mean_c", d.learnedSum, d.learnedS); mean("learned_rule_mean_c", d.learnedRuleSum, d.learnedS);
        return cJSON_AddNumberToObject(o, "optimum_start_s", d.startS) != nullptr;
    }
private:
    friend class LearnedState;
    Day today_{};
    std::optional<Day> yesterday_;
    uint64_t lastMs_ = 0;
    uint32_t carryMs_ = 0;
    bool haveLast_ = false;
};

// Gas per night next to the model (item 7, owner: "vergelijking per nacht"):
// from the program's drop (or the first trusted minute after it) to 6 h after
// the next rise, like WarmupPlanner::night(). At the start it keeps the meter
// total, the hot water estimate and the model's prediction (program, thermostat
// like, recommended); at the end the measured gas minus the hot water share
// (modulation x calibrated input while hot water ran) is the heating gas of
// that night. Report only: the model is calibrated through GasCalibration.
class NightLedger {
public:
    static constexpr int64_t maxNightS = 16 * 3600;
    static constexpr uint64_t meterFreshMs = 2 * 3600000ull; // as HeatingTelemetry's gasMeterFreshMs
    struct Record {
        int64_t startUtc = 0, switchUtc = 0;
        std::optional<double> startM3;
        double hotWaterKwh = 0;
        std::optional<float> measuredM3, hotWaterM3, heatingM3, programM3, thermostatM3, recommendedM3;
        const char* recommended = nullptr;
        const char* status = "open";        // open / measured / no_meter
    };
    // Every step with a trusted clock; room: the plan room whose week program
    // sets the night (-1: none).
    void step(int64_t utc, uint64_t now, const FlowLearner& l, const RoomPlan& plan, int room,
              std::optional<int16_t> temperature, std::optional<int16_t> outdoor) {
        if (open_ && utc < open_->startUtc) open_.reset();           // the clock stepped back
        if (open_) { if (utc >= open_->switchUtc + int64_t(WarmupPlanner::compareS)) close(now, l); return; }
        if (room < 0 || size_t(room) >= plan.rooms.size() || utc / 60 == checkedMinute_) return;
        checkedMinute_ = utc / 60;
        const auto& schedule = plan.rooms[room].schedule;
        const auto rise = WarmupPlanner::nextRise(schedule, utc);
        if (!rise || rise->eveningCentiC || rise->atUtc - utc > maxNightS || rise->atUtc == lastSwitch_) return;
        Record r; r.startUtc = utc; r.switchUtc = rise->atUtc;
        if (fresh(l, now)) r.startM3 = l.gas().meterM3();
        r.hotWaterKwh = l.gas().hotWaterKwh();
        const auto n = WarmupPlanner::night(l, size_t(room), schedule, utc, temperature, outdoor);
        for (uint8_t i = 0; i < n.count; ++i) {
            const auto& s = n.strategies[i];
            if (!std::strcmp(s.name, "program")) r.programM3 = s.m3;
            if (!std::strcmp(s.name, "thermostat_like")) r.thermostatM3 = s.m3;
        }
        if (n.reason[0] == 'e') { r.recommended = n.strategies[n.best].name; r.recommendedM3 = n.strategies[n.best].m3; }
        open_ = r; lastSwitch_ = rise->atUtc;
    }
    // {"nights","model_ratio","last":{"switch_utc","status","heating_m3","hot_water_m3",
    // "predicted_program_m3","recommended"}|null}; not compact (the page) adds "state",
    // "model_nights" and the last night's "start_utc", "measured_m3", the thermostat-like
    // and recommended predictions. Compact: heating_summary (changes once a night).
    bool json(cJSON* o, bool compact = false) const {
        if (!cJSON_AddNumberToObject(o, "nights", nights_)) return false;
        FlowLearner::number(o, "model_ratio", ratioN_ ? std::optional<float>(float(ratioSum_ / ratioN_)) : std::nullopt, 100);
        if (!compact) { cJSON_AddStringToObject(o, "state", open_ ? "open" : "waiting"); cJSON_AddNumberToObject(o, "model_nights", ratioN_); }
        if (!last_) return cJSON_AddNullToObject(o, "last") != nullptr;
        cJSON* r = cJSON_AddObjectToObject(o, "last");
        if (!r) return false;
        if (!compact) cJSON_AddNumberToObject(r, "start_utc", double(last_->startUtc));
        cJSON_AddNumberToObject(r, "switch_utc", double(last_->switchUtc));
        cJSON_AddStringToObject(r, "status", last_->status);
        if (!compact) FlowLearner::number(r, "measured_m3", last_->measuredM3, 1000);
        FlowLearner::number(r, "heating_m3", last_->heatingM3, 1000);
        FlowLearner::number(r, "hot_water_m3", last_->hotWaterM3, 1000);
        FlowLearner::number(r, "predicted_program_m3", last_->programM3, 1000);
        if (!compact) {
            FlowLearner::number(r, "predicted_thermostat_like_m3", last_->thermostatM3, 1000);
            FlowLearner::number(r, "predicted_recommended_m3", last_->recommendedM3, 1000);
        }
        return (last_->recommended ? cJSON_AddStringToObject(r, "recommended", last_->recommended) : cJSON_AddNullToObject(r, "recommended")) != nullptr;
    }
    const std::optional<Record>& last() const { return last_; }
    uint16_t nights() const { return nights_; }

private:
    friend class LearnedState;
    static bool fresh(const FlowLearner& l, uint64_t now) {
        const auto at = l.gas().meterAt();
        return at && *at <= now && now - *at <= meterFreshMs && l.gas().meterM3();
    }
    void close(uint64_t now, const FlowLearner& l) {
        Record r = *open_;
        open_.reset();
        const auto total = fresh(l, now) ? l.gas().meterM3() : std::nullopt;
        if (r.startM3 && total && *total >= *r.startM3) {
            const double hotWater = (l.gas().hotWaterKwh() - r.hotWaterKwh) * l.calibration() / l.params().kwhPerM3;
            r.measuredM3 = static_cast<float>(*total - *r.startM3);
            r.hotWaterM3 = static_cast<float>(hotWater);
            r.heatingM3 = std::max(0.0f, *r.measuredM3 - *r.hotWaterM3);
            r.status = "measured";
            if (r.programM3 && *r.programM3 > 0.05f) { ratioSum_ += *r.heatingM3 / *r.programM3; ratioN_ = sat(ratioN_); }
        } else r.status = "no_meter";
        last_ = r; nights_ = sat(nights_);
    }
    template <typename T> static T sat(T v) { return v == T(~T(0)) ? v : T(v + 1); }
    std::optional<Record> open_, last_;
    int64_t checkedMinute_ = -1, lastSwitch_ = 0;
    uint16_t nights_ = 0, ratioN_ = 0;
    double ratioSum_ = 0;
};

// Between the room engine's request (the rule: FlowDemand's PI flow) and the
// boiler guard, beta.19 items 19 and 6. The rule decides WHETHER to heat; with
// the options on, this sets HOW WARM (and an optimum start may begin earlier):
//  - weather curve (needs a fresh outdoor; else the rule's flow stays):
//    flow = base(setpoint, outdoor) + (rule flow - plan minimum) / 2, the room
//    PI at half authority on top of the curve (tuning: curve_correction_pct);
//  - use learned flow: during a warm-up (shortfall >= 0.3 degC) the learner's
//    lowest flow that closes it within the room's acceptance; and an optimum start
//    whose warm-up AND cooling are learned heats a room ahead of its next program rise (never while the
//    rule is in its minimum off time or has no usable room), at least 5 min
//    (tuning: min_on_s).
// Every flow stays within [plan minimum, min(plan maximum, 80, boiler limit)];
// the boiler limit wins over the plan minimum. Off (the default), everything is
// computed and reported as advice and the request is the rule's, unchanged.
// ActiveHeatGuard still bounds and sends (or, in shadow mode, only reports).
// Pure and single-threaded: apply() every 10 s after RoomEngine::step().
class FlowPolicy {
public:
    enum class Source : uint8_t { rule, curve, learned, optimumStart };
    static constexpr int16_t warmupFromCentiC = 30;
    static constexpr float houseSlopeFloor = 0.5f; // rc.5 (P2): the house model's slope at least this share of the design slope
    struct Inputs {
        uint64_t now = 0;
        std::optional<int64_t> utc;                 // trusted clock only
        FlowDemand::Request rule{};
        const RoomPlan* plan = nullptr;
        const RoomDemand::Result* rooms = nullptr;  // per plan room, after RoomEngine::step()
        std::optional<int16_t> outdoorCentiC;       // fresh only
        std::optional<uint8_t> boilerLimitC;        // the boiler's 0x16 heating limit
        std::optional<int16_t> flowCentiC;          // fresh EMS view, for the curve learner
        std::optional<bool> burnerOn, hotWater;
        // rc.5 (P2): HouseModel::slope(), the curve's slope until CurveLearner learned one, at least half the
        // design slope (order: learned curve, house model, design; "slope_source" "learned" / "house" / "design").
        std::optional<float> houseSlope;
    };

    void setSettings(const FlowSettings& s) { settings_ = s; }
    // A plan edit (rc.4, R1-04): what was keyed by room index restarts or is re-keyed by id.
    void setPlan(const RoomPlan& plan) {
        arrival_.setPlan(plan);
        starts_ = {}; heating_ = {}; start_ = {}; startHeating_ = false; startEnded_ = false; startMinute_ = -1;
        lead_ = -1; copyId(leadId_, ""); copyId(startId_, "");
        curveLearner_.interrupt();
    }
    const ArrivalLearner& arrival() const { return arrival_; }
    ArrivalLearner& arrival() { return arrival_; }
    const FlowSettings& settings() const { return settings_; }
    const FlowDemand::Request& request() const { return applied_; }
    Source source() const { return source_; }
    const CurveLearner& curveLearner() const { return curveLearner_; }
    const NightLedger& nights() const { return nights_; }

    FlowDemand::Request apply(const Inputs& in, const FlowLearner& learner) {
        rule_ = in.rule; applied_ = in.rule; source_ = Source::rule;
        curveFlow_.reset(); curveBase_.reset(); learnedFlow_.reset(); lead_ = -1;
        if (!in.plan || !in.rooms) { step(in, learner); return applied_; }
        const auto& plan = *in.plan;
        const size_t n = std::min(plan.rooms.size(), RoomPlan::maxRooms);
        cap_ = std::min<uint8_t>(std::min<uint8_t>(plan.maximumFlowC, FlowDemand::ceilingC), in.boilerLimitC.value_or(FlowDemand::ceilingC));
        const uint8_t lo = std::min(plan.minimumFlowC, cap_);
        const auto bound = [&](int v) { return static_cast<uint8_t>(std::clamp<int>(v, lo, cap_)); };
        // The boiler's own limit, not the plan, is the ceiling for `v`.
        const bool limitBelowPlan = in.boilerLimitC && *in.boilerLimitC < std::min(plan.maximumFlowC, FlowDemand::ceilingC);
        int curveWant = 0, learnedWant = 0;
        bool radiator = false;
        for (size_t i = 0; i < n; ++i) {
            radiator = radiator || plan.rooms[i].emitter == RoomPlan::Emitter::radiator;
            const auto& r = in.rooms[i];
            if (r.usable && (lead_ < 0 || r.errorCentiC > in.rooms[lead_].errorCentiC)) lead_ = int8_t(i);
        }
        copyId(leadId_, lead_ >= 0 ? plan.rooms[lead_].id.c_str() : "");
        designFlowC_ = settings_.designFlowC ? settings_.designFlowC : radiator ? WeatherCurve::radiatorDesignFlowC : WeatherCurve::floorDesignFlowC;
        const auto learnedSlope = curveLearner_.slope();
        // rc.5 (P2): the house model's slope (HouseModel) until the curve learned its own; comfort first, an
        // estimate takes at most half off the design slope (only CurveLearner, from steady periods at the
        // target, may go lower).
        const bool house = !learnedSlope && in.houseSlope && std::isfinite(*in.houseSlope) && *in.houseSlope > 0;
        const float design = WeatherCurve::slopeFor(designFlowC_);
        slope_ = learnedSlope ? *learnedSlope
            : house ? std::clamp(*in.houseSlope, std::max(WeatherCurve::minSlope, design * houseSlopeFloor), WeatherCurve::maxSlope) : design;
        slopeSource_ = learnedSlope ? "learned" : house ? "house" : "design";
        // Weather curve: the highest base over the usable rooms (one circuit).
        if (in.outdoorCentiC && lead_ >= 0) {
            for (size_t i = 0; i < n; ++i)
                if (in.rooms[i].usable && in.rooms[i].setpoint) {
                    const int16_t b = WeatherCurve::baseCentiC(slope_, *in.rooms[i].setpoint, *in.outdoorCentiC);
                    curveBase_ = curveBase_ ? std::max(*curveBase_, b) : b;
                }
            if (curveBase_) {
                const int correction = in.rule.heat ? std::max(0, int(in.rule.flowC) - int(plan.minimumFlowC)) * settings_.tuning.curveCorrectionPct / 100 : 0;
                curveWant = (*curveBase_ + 99) / 100 + correction;
                curveFlow_ = bound(curveWant);
            }
        }
        // Learned: the lead room's lowest flow that closes its shortfall in time.
        learnedReason_ = lead_ < 0 ? "no_room" : "not_ready";
        if (lead_ >= 0) {
            const int16_t shortfall = in.rooms[lead_].errorCentiC;
            const auto a = learner.advise(size_t(lead_), shortfall, in.outdoorCentiC);
            if (a.flowC && shortfall >= warmupFromCentiC) { learnedWant = *a.flowC; learnedFlow_ = bound(learnedWant); learnedReason_ = a.reason; }
            else if (a.flowC) learnedReason_ = "holding";
        }
        if (applied_.heat) {
            int want = in.rule.flowC;
            if (settings_.weatherCurve && curveFlow_) { want = curveWant; source_ = Source::curve; }
            if (settings_.applyLearned && learnedFlow_) { want = learnedWant; source_ = Source::learned; }
            // Options off: the rule's own request (already within the boiler's
            // limit), byte for byte. Options on: every output within [plan min, cap].
            if (source_ != Source::rule || settings_.weatherCurve || settings_.applyLearned) {
                applied_.flowC = bound(want);
                applied_.capped = (source_ == Source::rule && in.rule.capped) || (limitBelowPlan && want > cap_);
            }
        }
        optimumStart(in, learner, bound);
        step(in, learner);
        return applied_;
    }

    // Sets "request" to the applied request and, unless compact (the main MQTT
    // topic keeps its size: source and advice are in heating_summary), adds
    // "flow" with every detail for the page, and "night_gas" (NightLedger::json, full form:
    // the page's "last night" line).
    bool addStatus(cJSON* root, bool compact) const {
        cJSON* request = cJSON_GetObjectItemCaseSensitive(root, "request");
        if (cJSON_IsObject(request)) {
            // A failed replace (out of memory for the key copy) leaves the new item unowned.
            const auto replace = [&](const char* key, cJSON* item) {
                if (!cJSON_ReplaceItemInObjectCaseSensitive(request, key, item)) cJSON_Delete(item);
            };
            replace("heat", cJSON_CreateBool(applied_.heat));
            replace("flow_c", cJSON_CreateNumber(applied_.flowC));
            replace("reason", cJSON_CreateString(reason()));
            replace("capped_by", applied_.capped ? cJSON_CreateString("boiler_limit") : cJSON_CreateNull());
        }
        if (compact) return true;
        cJSON* flow = cJSON_AddObjectToObject(root, "flow");
        cJSON* night = flow ? cJSON_AddObjectToObject(root, "night_gas") : nullptr;
        return night && cJSON_AddStringToObject(flow, "source", name(source_)) && cJSON_AddNumberToObject(flow, "rule_flow_c", rule_.flowC)
            && detail(flow) && nights_.json(night);
    }
    // heating_summary, compact (about 1 KB with the rest of the summary):
    // "flow":{"source","rule_flow_c","applied_flow_c","curve":{"state","flow_c","slope",
    // "slope_source"},"learned":{"state","flow_c"},"optimum_start":state,"yesterday":
    // {"rule_mean_c","applied_mean_c","curve_mean_c","learned_mean_c"}|null} (rc.3: curve "windows") and
    // "night_gas" (NightLedger::json compact). The options themselves are static:
    // GET /config/heating/flow.
    bool addSummary(cJSON* root) const {
        cJSON* flow = cJSON_AddObjectToObject(root, "flow");
        cJSON* night = flow ? cJSON_AddObjectToObject(root, "night_gas") : nullptr;
        cJSON* curve = night ? cJSON_AddObjectToObject(flow, "curve") : nullptr;
        cJSON* learned = curve ? cJSON_AddObjectToObject(flow, "learned") : nullptr;
        if (!learned || !cJSON_AddStringToObject(flow, "source", name(source_)) || !cJSON_AddNumberToObject(flow, "rule_flow_c", rule_.flowC)
            || !cJSON_AddNumberToObject(flow, "applied_flow_c", applied_.flowC)) return false;
        cJSON_AddStringToObject(curve, "state", curveState());
        FlowLearner::number(curve, "flow_c", curveFlow_ ? std::optional<float>(*curveFlow_) : std::nullopt, 1);
        FlowLearner::number(curve, "slope", slope_, 100);
        cJSON_AddStringToObject(curve, "slope_source", slopeSource_); // rc.5: also "house" (HouseModel)
        cJSON_AddNumberToObject(curve, "windows", curveLearner_.windows()); // rc.3: "2 of 6 steady periods"
        cJSON_AddStringToObject(learned, "state", learnedState());
        FlowLearner::number(learned, "flow_c", learnedFlow_ ? std::optional<float>(*learnedFlow_) : std::nullopt, 1);
        cJSON_AddStringToObject(flow, "optimum_start", startState_);
        if (const auto& y = compare_.yesterday()) {
            cJSON* o = cJSON_AddObjectToObject(flow, "yesterday");
            if (!o) return false;
            const auto mean = [&](const char* k, uint32_t sum, uint32_t sec) {
                FlowLearner::number(o, k, sec ? std::optional<float>(float(sum) / sec) : std::nullopt, 10);
            };
            mean("rule_mean_c", y->ruleSum, y->heatS); mean("applied_mean_c", y->appliedSum, y->heatS);
            mean("curve_mean_c", y->curveSum, y->curveS); mean("learned_mean_c", y->learnedSum, y->learnedS);
        } else if (!cJSON_AddNullToObject(flow, "yesterday")) return false;
        return nights_.json(night, true);
    }
    static const char* name(Source s) {
        switch (s) {
            case Source::curve: return "curve";
            case Source::learned: return "learned";
            case Source::optimumStart: return "optimum_start";
            default: return "rule";
        }
    }

private:
    friend class LearnedState; // the curve learner, the comparison and the night ledger
    // rc.4 (L3, R1-07): every room with a planned start is served (the highest flow wins), an
    // estimate too, only on fresh readings, with the start's own minimum rest after it ended.
    // The arrival learner (L2) watches every rise once a minute and judges each morning.
    template <class Bound> void optimumStart(const Inputs& in, const FlowLearner& learner, Bound bound) {
        const auto& plan = *in.plan;
        if (!in.utc) { starts_ = {}; heating_ = {}; start_ = {}; startState_ = "no_clock"; startHeating_ = false; return; }
        const size_t n = std::min({plan.rooms.size(), size_t(RoomPlan::maxRooms), learner.rooms()});
        const auto fresh = [](const RoomDemand::Result& r) {
            return r.usable && r.temperature && (r.status == RoomDemand::Status::ok || r.status == RoomDemand::Status::fallback);
        };
        // Once a minute the planner walks each room's week program; a start that began stays
        // until its rise (the warming room would otherwise shorten its own lead).
        if (*in.utc / 60 != startMinute_) {
            startMinute_ = *in.utc / 60;
            for (size_t i = 0; i < RoomPlan::maxRooms; ++i) {
                const bool latched = i < n && heating_[i] && starts_[i].room >= 0 && *in.utc < starts_[i].riseUtc;
                if (i >= n || in.rooms[i].status == RoomDemand::Status::inactive || !in.rooms[i].temperature) {
                    if (!latched) starts_[i] = {};
                    if (i < n) arrival_.observe(i, *in.utc, std::nullopt, false, std::nullopt);
                    continue;
                }
                const auto& r = in.rooms[i];
                const auto s = WarmupPlanner::optimumStart(learner, i, plan.rooms[i].schedule, *in.utc, r.temperature, in.outdoorCentiC, arrival_.lead(i));
                std::optional<ArrivalLearner::Rise> rise;
                if (s.reason[0] == 'p') rise = ArrivalLearner::Rise{s.rise.atUtc, s.startUtc, s.rise.toCentiC};
                arrival_.observe(i, *in.utc, rise, heating_[i], fresh(r) ? r.temperature : std::nullopt);
                if (latched) continue;
                starts_[i] = rise && s.startNow ? Start{int8_t(i), s.flowC, s.applicable(), s.estimate, s.rise.toCentiC, s.startUtc, s.rise.atUtc} : Start{};
            }
        }
        // Heat ahead of the rise while a room is below its coming target (0.1 degC to start).
        bool wanted = false, arrived = false; uint8_t want = 0; int8_t primary = -1;
        std::array<bool, RoomPlan::maxRooms> wants{};
        for (size_t i = 0; i < n; ++i) {
            const auto& st = starts_[i];
            if (st.room < 0 || !fresh(in.rooms[i])) continue;
            if (*in.rooms[i].temperature >= st.targetCentiC - (heating_[i] ? 0 : 10)) { arrived = arrived || heating_[i]; continue; }
            wants[i] = wanted = true; want = std::max(want, st.flowC);
            if (primary < 0 || (st.learned && !starts_[primary].learned) || (st.learned == starts_[primary].learned && st.flowC > starts_[primary].flowC)) primary = int8_t(i);
        }
        start_ = primary >= 0 ? starts_[primary] : Start{};
        copyId(startId_, start_.room >= 0 ? plan.rooms[start_.room].id.c_str() : "");
        const bool allowed = in.rule.reason == FlowDemand::Reason::idle || in.rule.reason == FlowDemand::Reason::satisfied || in.rule.heat;
        const bool holdOn = startHeating_ && in.now - startedAt_ < settings_.tuning.minOnS * 1000ull && in.rule.reason != FlowDemand::Reason::noDemand;
        // A start that ended because its room arrived rests the burner's minimum off before a dip
        // starts it again; the rule's own rests (holdOff) and a stale reading end nothing. A burner
        // the rule keeps on anyway needs no rest for a higher flow.
        const bool rested = !startEnded_ || in.now - endedAt_ >= settings_.tuning.minOffS * 1000ull;
        startState_ = start_.room < 0 ? "none" : settings_.applyLearned ? "applied" : "advice";
        const bool apply = settings_.applyLearned && allowed && ((wanted && (rested || in.rule.heat)) || holdOn);
        if (!apply) {
            if (startHeating_ && arrived && !wanted) { startEnded_ = true; endedAt_ = in.now; }
            startHeating_ = false; heating_ = {};
            return;
        }
        if (!startHeating_) { startHeating_ = true; startedAt_ = in.now; startFlowC_ = bound(want ? want : startFlowC_); }
        if (want) startFlowC_ = bound(want);
        if (wanted) heating_ = wants; // held on for the minimum on time: the rooms stay its rooms (they rest after it)
        if (!applied_.heat) { applied_ = {true, startFlowC_, FlowDemand::Reason::heating}; source_ = Source::optimumStart; }
        else if (startFlowC_ > applied_.flowC) { applied_.flowC = startFlowC_; source_ = Source::optimumStart; }
    }
    void step(const Inputs& in, const FlowLearner& learner) {
        CurveLearner::Sample s;
        if (lead_ >= 0) { s.room = lead_; s.roomCentiC = in.rooms[lead_].temperature; s.setpointCentiC = in.rooms[lead_].setpoint; }
        s.outdoorCentiC = in.outdoorCentiC; s.flowCentiC = in.flowCentiC; s.burnerOn = in.burnerOn; s.hotWater = in.hotWater;
        curveLearner_.sample(in.now, s);
        std::optional<uint32_t> unixNow;
        if (in.utc && *in.utc > 0 && *in.utc < 4294967296ll) unixNow = static_cast<uint32_t>(*in.utc);
        compare_.sample(in.now, unixNow, rule_, applied_, rule_.heat ? curveFlow_ : std::nullopt, rule_.heat ? learnedFlow_ : std::nullopt);
        if (!in.utc || !in.plan || !in.rooms) return;
        // The night follows the first active room with a week program.
        int room = -1;
        for (size_t i = 0; i < in.plan->rooms.size() && i < RoomPlan::maxRooms && room < 0; ++i)
            if (in.rooms[i].status != RoomDemand::Status::inactive && !in.plan->rooms[i].schedule.empty()) room = int(i);
        nights_.step(*in.utc, in.now, learner, *in.plan, room, room >= 0 ? in.rooms[room].temperature : std::nullopt, in.outdoorCentiC);
    }
    const char* curveState() const { return !curveBase_ ? (lead_ < 0 ? "no_room" : "no_outdoor") : settings_.weatherCurve ? "applied" : "advice"; }
    const char* learnedState() const { return !learnedFlow_ ? learnedReason_ : settings_.applyLearned ? "applied" : "advice"; }
    const char* reason() const { return source_ == Source::optimumStart && !rule_.heat ? "optimum_start" : FlowDemand::name(applied_.reason); }
    bool detail(cJSON* flow) const {
        cJSON* settings = cJSON_CreateObject();
        if (!settings || !cJSON_AddItemToObject(flow, "settings", settings)) { cJSON_Delete(settings); return false; }
        cJSON_AddBoolToObject(settings, "weather_curve", settings_.weatherCurve);
        cJSON_AddBoolToObject(settings, "apply_learned", settings_.applyLearned);
        cJSON_AddNumberToObject(settings, "curve_design_flow_c", settings_.designFlowC);
        cJSON_AddNumberToObject(flow, "applied_flow_c", applied_.flowC);
        cJSON_AddNumberToObject(flow, "cap_c", cap_);
        cJSON* curve = cJSON_AddObjectToObject(flow, "curve");
        cJSON* learned = curve ? cJSON_AddObjectToObject(flow, "learned") : nullptr;
        cJSON* start = learned ? cJSON_AddObjectToObject(flow, "optimum_start") : nullptr;
        if (!start) return false;
        cJSON_AddStringToObject(curve, "state", curveState());
        FlowLearner::number(curve, "flow_c", curveFlow_ ? std::optional<float>(*curveFlow_) : std::nullopt, 1);
        FlowLearner::number(curve, "base_c", curveBase_ ? std::optional<float>(*curveBase_ / 100.0f) : std::nullopt, 10);
        FlowLearner::number(curve, "slope", slope_, 100);
        cJSON_AddStringToObject(curve, "slope_source", slopeSource_);
        cJSON_AddNumberToObject(curve, "design_flow_c", designFlowC_);
        cJSON_AddNumberToObject(curve, "windows", curveLearner_.windows());
        cJSON_AddStringToObject(curve, "last", curveLearner_.last());
        cJSON_AddStringToObject(learned, "state", learnedState());
        FlowLearner::number(learned, "flow_c", learnedFlow_ ? std::optional<float>(*learnedFlow_) : std::nullopt, 1);
        id(learned, leadId_);
        cJSON_AddStringToObject(start, "state", startState_);
        id(start, start_.room >= 0 ? startId_ : "");
        if (start_.room >= 0) cJSON_AddNumberToObject(start, "start_utc", double(start_.startUtc)); else cJSON_AddNullToObject(start, "start_utc");
        FlowLearner::number(start, "flow_c", start_.room >= 0 ? std::optional<float>(start_.flowC) : std::nullopt, 1);
        cJSON_AddStringToObject(start, "confidence", start_.room < 0 ? "none" : start_.learned ? "learned" : "default");
        cJSON_AddBoolToObject(start, "estimate", start_.room >= 0 && start_.estimate); // rc.4: applied as an estimate (L3)
        cJSON_AddBoolToObject(start, "heating", startHeating_);
        cJSON_AddNumberToObject(start, "rooms", double(std::count(heating_.begin(), heating_.end(), true)));
        if (!FlowCompare::dayJson(flow, "today", compare_.today())) return false;
        if (compare_.yesterday()) return FlowCompare::dayJson(flow, "yesterday", *compare_.yesterday());
        return cJSON_AddNullToObject(flow, "yesterday") != nullptr;
    }
    // Plan room ids ([a-z0-9_]{1,32}) kept by value: the plan may change between steps.
    static void copyId(char (&to)[33], const char* from) { std::snprintf(to, sizeof to, "%s", from); }
    static void id(cJSON* o, const char* value) { if (*value) cJSON_AddStringToObject(o, "room", value); else cJSON_AddNullToObject(o, "room"); }
    struct Start { int8_t room = -1; uint8_t flowC = 0; bool learned = false, estimate = false; int16_t targetCentiC = 0; int64_t startUtc = 0, riseUtc = 0; };
    FlowSettings settings_;
    FlowDemand::Request rule_{}, applied_{};
    Source source_ = Source::rule;
    std::optional<uint8_t> curveFlow_, learnedFlow_;
    std::optional<int16_t> curveBase_;
    uint8_t cap_ = FlowDemand::ceilingC, designFlowC_ = WeatherCurve::floorDesignFlowC, startFlowC_ = 0;
    float slope_ = 0;
    const char* slopeSource_ = "design"; // rc.5: "learned", "house" or "design"
    bool startHeating_ = false, startEnded_ = false;
    int8_t lead_ = -1;
    char leadId_[33] = "", startId_[33] = "";
    const char* learnedReason_ = "no_room";
    const char* startState_ = "no_clock";
    Start start_;                                      // the primary start (telemetry)
    std::array<Start, RoomPlan::maxRooms> starts_{};   // rc.4: this minute's planned start per room
    std::array<bool, RoomPlan::maxRooms> heating_{};   // rc.4: the rooms the applied start serves
    int64_t startMinute_ = -1;
    uint64_t startedAt_ = 0, endedAt_ = 0;
    ArrivalLearner arrival_;                           // rc.4 (L2), kept by LearnedState
    CurveLearner curveLearner_;
    FlowCompare compare_;
    NightLedger nights_;
};
}
