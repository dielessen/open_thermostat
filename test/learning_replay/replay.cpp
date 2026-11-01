// Replays recorded history (tools/switchover/replay_export.py CSV) through the firmware's own
// learning and flow code: FlowLearner (what it would learn), RoomEngine (the E32's own flow
// request, compared with the recorded one) and FlowDemand parameter variants (compared with the
// old thermostat). Read-only analysis input for docs/modern-thermostat/LEREN-ANALYSE.nl.md.
//
//   replay <replay.csv> [--emitter floor|radiator] [--min-flow 30] [--max-flow 60]
//
// Prints one JSON object. Pure: no clock, no IO besides the CSV and stdout.
#include "control/FlowDemand.h"
#include "control/FlowLearner.h"
#include "control/RoomEngine.h"
#include "control/RoomPlan.h"
#include <cJSON.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

using namespace heating::control;

namespace {
struct Row {
    long t = 0;
    std::optional<double> room, setpoint, flow, ret, modulation, outdoor, thermostat, e32;
    std::optional<bool> dhw;
};

std::optional<double> num(const std::string& s) {
    if (s.empty()) return std::nullopt;
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    if (end == s.c_str() || !std::isfinite(v)) return std::nullopt;
    return v;
}

std::vector<Row> readCsv(const char* path) {
    std::ifstream in(path);
    std::string line;
    std::vector<Row> rows;
    if (!std::getline(in, line)) return rows;
    std::vector<std::string> head;
    { std::stringstream ss(line); std::string c; while (std::getline(ss, c, ',')) head.push_back(c); }
    while (std::getline(in, line)) {
        std::stringstream ss(line); std::string c; std::map<std::string, std::string> f; size_t i = 0;
        while (std::getline(ss, c, ',')) { if (i < head.size()) f[head[i]] = c; ++i; }
        if (i < head.size()) f[head[head.size() - 1]] = f.count(head.back()) ? f[head.back()] : "";
        Row r;
        r.t = std::strtol(f["t_s"].c_str(), nullptr, 10);
        r.room = num(f["room_c"]); r.setpoint = num(f["setpoint_c"]); r.flow = num(f["flow_c"]);
        r.ret = num(f["return_c"]); r.modulation = num(f["modulation_pct"]); r.outdoor = num(f["outdoor_c"]);
        r.thermostat = num(f["thermostat_flow_c"]); r.e32 = num(f["e32_flow_c"]);
        if (auto d = num(f["dhw"])) r.dhw = *d > 0;
        rows.push_back(r);
    }
    return rows;
}

std::optional<int16_t> centi(std::optional<double> v) {
    if (!v) return std::nullopt;
    return static_cast<int16_t>(std::lround(*v * 100));
}

double median(std::vector<double> v) {
    if (v.empty()) return NAN;
    std::sort(v.begin(), v.end());
    const size_t n = v.size();
    return n % 2 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
}

void addNumber(cJSON* o, const char* k, double v) {
    if (std::isfinite(v)) cJSON_AddNumberToObject(o, k, std::round(v * 100) / 100); else cJSON_AddNullToObject(o, k);
}

RoomPlan plan(const char* emitter, int minFlow, int maxFlow) {
    char text[1024];
    std::snprintf(text, sizeof text, R"({"schema":1,"mode":"shadow","minimum_flow_c":%d,"maximum_flow_c":%d,"rooms":[
      {"id":"room","name":"Room","state":"active","inactive_until":0,"emitter":"%s",
       "sources":[{"type":"ha","id":"sensor.room"}],"setpoint_entity":"sensor.room",
       "fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500}]})", minFlow, maxFlow, emitter);
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(text), cJSON_Delete);
    RoomPlan p;
    if (const char* error = RoomPlan::parse(root.get(), p)) { std::fprintf(stderr, "plan: %s\n", error); std::exit(2); }
    return p;
}

// What the learner would have learned with one parameter set.
cJSON* learn(const std::vector<Row>& rows, const RoomPlan& p, FlowLearner::Params params, const char* name) {
    FlowLearner learner(params);
    learner.setPlan(p);
    std::map<std::string, long> status;
    for (const auto& r : rows) {
        FlowLearner::Boiler b;
        b.flowCentiC = centi(r.flow); b.returnCentiC = centi(r.ret);
        if (r.modulation) { b.modulationPct = static_cast<uint8_t>(std::clamp(*r.modulation, 0.0, 100.0)); b.burnerOn = *r.modulation > 0; }
        b.hotWater = r.dhw;
        if (r.thermostat) b.requestedFlowC = static_cast<uint8_t>(std::clamp(*r.thermostat, 0.0, 100.0));
        b.outdoorCentiC = centi(r.outdoor);
        FlowLearner::RoomInput in;
        in.temperatureCentiC = centi(r.room); in.setpointCentiC = centi(r.setpoint); in.source = r.room ? 0 : -1;
        learner.sample(static_cast<uint64_t>(r.t) * 1000, b, &in, 1);
        ++status[learner.status()];
    }
    cJSON* o = cJSON_CreateObject();
    cJSON_AddStringToObject(o, "variant", name);
    cJSON_AddNumberToObject(o, "hot_water_holdoff_min", (params.bridgeHotWater ? params.bridgeHoldoffMs : params.hotWaterHoldoffMs) / 60000.0);
    cJSON_AddBoolToObject(o, "bridge_hot_water", params.bridgeHotWater);
    cJSON_AddNumberToObject(o, "min_segment_min", params.minSegmentMs / 60000.0);
    cJSON_AddNumberToObject(o, "heating_periods", learner.heatingPeriods());
    cJSON* st = cJSON_AddObjectToObject(o, "status_minutes");
    const long step = rows.size() > 1 ? rows[1].t - rows[0].t : 10;
    for (const auto& [k, v] : status) cJSON_AddNumberToObject(st, k.c_str(), std::round(v * step / 60.0));
    cJSON_AddItemToObject(o, "room", learner.roomJson(0));
    return o;
}

struct Compare { std::vector<double> diff; long eOnly = 0, tOnly = 0, both = 0, starts = 0, tadoStarts = 0; };

// FlowDemand with its own room hysteresis (0.2 degC band like ZoneRegulator) against the old thermostat.
cJSON* variant(const std::vector<Row>& rows, FlowDemand::Params params, const char* name) {
    FlowDemand demand(params);
    bool on = false, wasHeat = false, tadoWas = false;
    Compare c;
    for (const auto& r : rows) {
        std::optional<int16_t> error;
        if (r.room && r.setpoint) error = centi(*r.setpoint - *r.room);
        if (error) { if (*error >= 10) on = true; else if (*error <= -10) on = false; }
        const auto q = demand.update(static_cast<uint64_t>(r.t) * 1000, on, error);
        const bool tado = r.thermostat && *r.thermostat >= 20;
        if (q.heat && !wasHeat) ++c.starts;
        if (tado && !tadoWas) ++c.tadoStarts;
        wasHeat = q.heat; tadoWas = tado;
        if (q.heat && tado) { ++c.both; c.diff.push_back(q.flowC - *r.thermostat); }
        else if (q.heat) ++c.eOnly;
        else if (tado) ++c.tOnly;
    }
    const long step = rows.size() > 1 ? rows[1].t - rows[0].t : 10;
    cJSON* o = cJSON_CreateObject();
    cJSON_AddStringToObject(o, "variant", name);
    cJSON_AddNumberToObject(o, "minimum_flow_c", params.minimumFlowC);
    cJSON_AddNumberToObject(o, "flow_per_degree_c", params.flowPerDegreeC);
    cJSON_AddNumberToObject(o, "integral_min", params.integralSeconds / 60.0);
    addNumber(o, "median_minus_thermostat_c", median(c.diff));
    cJSON_AddNumberToObject(o, "both_heat_min", std::round(c.both * step / 60.0));
    cJSON_AddNumberToObject(o, "only_e32_min", std::round(c.eOnly * step / 60.0));
    cJSON_AddNumberToObject(o, "only_thermostat_min", std::round(c.tOnly * step / 60.0));
    cJSON_AddNumberToObject(o, "e32_starts", c.starts);
    cJSON_AddNumberToObject(o, "thermostat_starts", c.tadoStarts);
    return o;
}

// The E32's own RoomEngine on the same inputs, against what the E32 recorded.
cJSON* engine(const std::vector<Row>& rows, const RoomPlan& p) {
    RoomEngine e;
    e.setPlan(p);
    std::vector<double> diff;
    long agree = 0, n = 0;
    for (const auto& r : rows) {
        const uint64_t now = static_cast<uint64_t>(r.t) * 1000;
        e.haState("sensor.room", centi(r.room), centi(r.setpoint), now);
        const auto q = e.step(now, std::nullopt);
        if (!r.e32) continue;
        ++n;
        const bool recorded = *r.e32 >= 20;
        if (recorded == q.heat) ++agree;
        if (recorded && q.heat) diff.push_back(q.flowC - *r.e32);
    }
    cJSON* o = cJSON_CreateObject();
    addNumber(o, "heat_agreement", n ? double(agree) / n : NAN);
    addNumber(o, "median_minus_recorded_c", median(diff));
    cJSON_AddNumberToObject(o, "compared_samples", n);
    return o;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) { std::fprintf(stderr, "usage: replay <replay.csv> [--emitter floor|radiator] [--min-flow N] [--max-flow N]\n"); return 2; }
    const char* emitter = "floor";
    int minFlow = 30, maxFlow = 60;
    for (int i = 2; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        if (k == "--emitter") emitter = argv[i + 1];
        else if (k == "--min-flow") minFlow = std::atoi(argv[i + 1]);
        else if (k == "--max-flow") maxFlow = std::atoi(argv[i + 1]);
    }
    const auto rows = readCsv(argv[1]);
    if (rows.size() < 2) { std::fprintf(stderr, "no rows\n"); return 2; }
    const auto p = plan(emitter, minFlow, maxFlow);

    cJSON* root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "rows", static_cast<double>(rows.size()));
    cJSON_AddNumberToObject(root, "hours", (rows.back().t - rows.front().t) / 3600.0);
    cJSON* learners = cJSON_AddArrayToObject(root, "learner");
    FlowLearner::Params base;
    cJSON_AddItemToArray(learners, learn(rows, p, base, "firmware"));
    FlowLearner::Params shortHold = base; shortHold.hotWaterHoldoffMs = 300000;
    cJSON_AddItemToArray(learners, learn(rows, p, shortHold, "hot_water_holdoff_5min"));
    FlowLearner::Params shortSeg = shortHold; shortSeg.minSegmentMs = 1200000;
    cJSON_AddItemToArray(learners, learn(rows, p, shortSeg, "holdoff_5min_segment_20min"));
    FlowLearner::Params bridge = base; bridge.bridgeHotWater = true;
    cJSON_AddItemToArray(learners, learn(rows, p, bridge, "bridge_hot_water"));
    FlowLearner::Params bridgeShort = bridge; bridgeShort.minSegmentMs = 1800000;
    cJSON_AddItemToArray(learners, learn(rows, p, bridgeShort, "bridge_hot_water_segment_30min"));
    FlowLearner::Params floorLag = bridgeShort; floorLag.settleMs = 1800000; // floor heating: skip the first 30 min
    cJSON_AddItemToArray(learners, learn(rows, p, floorLag, "bridge_segment_30min_settle_30min"));

    cJSON* variants = cJSON_AddArrayToObject(root, "flow_demand");
    FlowDemand::Params fd; fd.minimumFlowC = static_cast<uint8_t>(minFlow); fd.maximumFlowC = static_cast<uint8_t>(maxFlow);
    cJSON_AddItemToArray(variants, variant(rows, fd, "firmware"));
    auto v = fd; v.minimumFlowC = 34; cJSON_AddItemToArray(variants, variant(rows, v, "minimum_34"));
    v = fd; v.flowPerDegreeC = 15; cJSON_AddItemToArray(variants, variant(rows, v, "gain_15_per_degree"));
    v = fd; v.integralSeconds = 3600; cJSON_AddItemToArray(variants, variant(rows, v, "integral_60min"));
    v = fd; v.minimumOnMs = 600000; v.minimumOffMs = 600000; cJSON_AddItemToArray(variants, variant(rows, v, "min_on_off_10min"));

    cJSON_AddItemToObject(root, "room_engine", engine(rows, p));
    char* out = cJSON_Print(root);
    std::puts(out);
    cJSON_free(out);
    cJSON_Delete(root);
    return 0;
}
