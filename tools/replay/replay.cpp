// Real-data replay of the E32's learning and self-tuning (tools/replay/README.md).
//
// Replays recorded house data (the CSV format of the README) through the firmware's own
// classes, wired as HeatingController::stepHeating wires them: RoomEngine (the rule),
// FlowPolicy (the flow options), FlowLearner, AutoTuner and WarmupPlanner, plus
// BurnerCycleMonitor. Every mode (shadow, active, recorded) is one run over the same data.
// Host-only analysis: it reads src/ and never talks to a device or Home Assistant.
//
//   replay [options] <data.csv> [more.csv ...]
//     --mode shadow,active,recorded   runs (default shadow,active)
//     --plan FILE                     a RoomPlan JSON (API form); default: one floor room per CSV room
//     --schedule JSON                 a week program for every room of the default plan
//     --emitter floor|radiator --min-flow N --max-flow N   the default plan (floor, 30, 60)
//     --no-grace                      AutoTuner without its 24 h after the boot (the first row)
//     --recorded-request              use the CSV's E32 request where known, not the computed one
//     --weather-curve --apply-learned the FlowPolicy options (default off: advice only)
//     --bridge-hot-water, --no-bridge-hot-water  FlowLearner::Params::bridgeHotWater (default on, as the firmware)
//     --hold-s N                      a row holds this long before it is a gap (default 60)
//     --tz TZ                         POSIX time zone (default CET-1CEST,M3.5.0,M10.5.0/3)
//     --json FILE --text FILE         outputs (default: JSON on stdout, nothing else)
#include "control/AutoTuner.h"
#include "control/BurnerCycleMonitor.h"
#include "control/ControlTuning.h"
#include "control/FlowDemand.h"
#include "control/FlowLearner.h"
#include "control/FlowPolicy.h"
#include "control/RoomEngine.h"
#include "control/RoomPlan.h"
#include "control/Scoreboard.h"
#include "control/ShadowComparison.h"
#include "control/WarmupPlanner.h"
// rc.5 (RC5-PLAN.md 2.1-2.3): the learners of P1-P3, wired as HeatingController wires them once their
// headers exist; until then these hooks compile out and the JSON says so ("firmware").
#if __has_include("control/BoilerResponse.h")
#include "control/BoilerResponse.h"
#define REPLAY_BOILER_RESPONSE 1
#endif
#if __has_include("control/HouseModel.h")
#include "control/HouseModel.h"
#define REPLAY_HOUSE_MODEL 1
#endif
#if __has_include("control/FreeHeat.h")
#include "control/FreeHeat.h"
#define REPLAY_FREE_HEAT 1
#endif
#include <cJSON.h>
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <type_traits>
#include <vector>

// rc.5 hooks the contract leaves open are detected, not assumed (as in test/soak/soak.cpp): the
// FlowPolicy inputs of P1-P3, the modules' setPlan() and P1's RestFloor helper.
namespace heating::control { struct RestFloor; }
namespace replay_detect {
template <class T, class = void> struct Complete : std::false_type {};
template <class T> struct Complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};
template <class T, class = void> struct CeilingInput : std::false_type {};
template <class T> struct CeilingInput<T, std::void_t<decltype(std::declval<T&>().ceilingC = std::optional<uint8_t>()),
                                                     decltype(std::declval<T&>().ownRequest = true)>> : std::true_type {};
template <class T, class = void> struct HouseSlopeInput : std::false_type {};
template <class T> struct HouseSlopeInput<T, std::void_t<decltype(std::declval<T&>().houseSlope = std::optional<float>())>> : std::true_type {};
template <class T, class F, class = void> struct FreeHeatMember : std::false_type {};
template <class T, class F> struct FreeHeatMember<T, F, std::void_t<decltype(std::declval<T&>().freeHeat = static_cast<const F*>(nullptr))>> : std::true_type {};
template <class T, class P, class = void> struct SetPlan : std::false_type {};
template <class T, class P> struct SetPlan<T, P, std::void_t<decltype(std::declval<T&>().setPlan(std::declval<const P&>()))>> : std::true_type {};
template <class In> void ceiling(In& in, bool ownRequest, std::optional<uint8_t> c) {
    if constexpr (CeilingInput<In>::value) { in.ownRequest = ownRequest; in.ceilingC = c; }
}
template <class In> void houseSlope(In& in, std::optional<float> slope) {
    if constexpr (HouseSlopeInput<In>::value) in.houseSlope = slope;
}
template <class F, class In> void freeHeat(In& in, const F* f) {
    if constexpr (FreeHeatMember<In, F>::value) in.freeHeat = f;
}
template <class M, class P> void setPlan(M& m, const P& plan) {
    if constexpr (SetPlan<M, P>::value) m.setPlan(plan);
}
template <class Tuning, class F = heating::control::RestFloor>
bool restFloor(Tuning& t, std::optional<uint32_t> restS, bool coldNow) {
    if constexpr (Complete<F>::value) { F::apply(t, restS, coldNow); return true; }
    else return false;
}
// FlowLearner::Boiler::ownRequest (rc.2) and FlowLearner::effectiveMinimumC (rc.2), absent in older
// firmware that REPLAY_REV may build against.
template <class B, class = void> struct OwnRequest : std::false_type {};
template <class B> struct OwnRequest<B, std::void_t<decltype(std::declval<B&>().ownRequest = true)>> : std::true_type {};
template <class B> void ownRequest(B& b, bool own) {
    if constexpr (OwnRequest<B>::value) b.ownRequest = own;
}
template <class L, class = void> struct EffectiveMinimum : std::false_type {};
template <class L> struct EffectiveMinimum<L, std::void_t<decltype(std::declval<const L&>().effectiveMinimumC(std::optional<uint8_t>()))>> : std::true_type {};
template <class L> uint8_t lowestFlow(const L& l, uint8_t planMinimumC) {
    if constexpr (EffectiveMinimum<L>::value) return l.effectiveMinimumC(std::nullopt);
    else return planMinimumC;
}
}

using namespace heating::control;

namespace {
using Opt = std::optional<double>;
using Flag = std::optional<bool>;
constexpr int64_t stepS = 10; // the firmware's control step

// --- FlowLearner's heating reference -------------------------------------------------
// HeatingController (rc2-learning-active) passes FlowLearner::heatingReference(): while the
// E32 drives the boiler its own last command, else the controlling thermostat's 0x1A. Older
// firmware passes the thermostat's 0x1A only (absent once the thermostat is off the bus).
template <class L, class = void> struct HasHeatingReference : std::false_type {};
template <class L>
struct HasHeatingReference<L, std::void_t<decltype(L::heatingReference(true, uint8_t(0), std::optional<uint8_t>()))>> : std::true_type {};
constexpr bool firmwareHasReference = HasHeatingReference<FlowLearner>::value;
template <class L = FlowLearner>
std::optional<uint8_t> heatingReference(bool e32Drives, uint8_t e32FlowC, std::optional<uint8_t> thermostat) {
    if constexpr (HasHeatingReference<L>::value) return L::heatingReference(e32Drives, e32FlowC, thermostat);
    else return thermostat;
}

// --- input ---------------------------------------------------------------------------
struct RoomSample { Opt temp, target; };
struct Row {
    int64_t utc = 0;
    std::vector<RoomSample> rooms;
    Opt flow, ret, modulation, e32Flow, thermostat, outdoor;
    Flag burner, heatingActive, dhw, e32Heat;
    std::string e32Reason, mode;
};
struct Data {
    std::vector<std::string> rooms, files, ignored;
    std::vector<Row> rows;
};

[[noreturn]] void fail(const std::string& why) { std::fprintf(stderr, "replay: %s\n", why.c_str()); std::exit(2); }

Opt number(const std::string& s) {
    if (s.empty()) return std::nullopt;
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    if (end == s.c_str() || *end || !std::isfinite(v)) return std::nullopt;
    return v;
}
Flag flag(const std::string& s) {
    if (s == "1" || s == "true" || s == "on") return true;
    if (s == "0" || s == "false" || s == "off") return false;
    if (const auto v = number(s)) return *v > 0;
    return std::nullopt;
}
std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> out;
    size_t start = 0;
    for (;;) {
        const size_t comma = line.find(',', start);
        out.push_back(line.substr(start, comma == std::string::npos ? std::string::npos : comma - start));
        if (comma == std::string::npos) break;
        start = comma + 1;
    }
    if (!out.empty() && !out.back().empty() && out.back().back() == '\r') out.back().pop_back();
    return out;
}

void readCsv(const std::string& path, Data& d) {
    std::ifstream in(path);
    if (!in) fail("cannot read " + path);
    d.files.push_back(path);
    std::string line;
    std::vector<std::string> head;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#' || line == "\r") continue;
        head = split(line);
        break;
    }
    if (std::find(head.begin(), head.end(), "utc") == head.end()) fail(path + ": no utc column");
    // Per column: a fixed field, or (room index, temp/target).
    enum Col { utc, flow, ret, burner, heating, dhw, modulation, e32Heat, e32Flow, e32Reason, thermostat, outdoor, mode, roomTemp, roomTarget, ignore };
    static const std::map<std::string, Col> fixed{{"utc", utc}, {"flow_c", flow}, {"return_c", ret}, {"burner", burner},
        {"heating_active", heating}, {"dhw_active", dhw}, {"modulation_pct", modulation}, {"e32_heat", e32Heat},
        {"e32_flow_c", e32Flow}, {"e32_reason", e32Reason}, {"thermostat_flow_c", thermostat}, {"outdoor_c", outdoor}, {"mode", mode}};
    std::vector<std::pair<Col, size_t>> cols;
    for (const auto& h : head) {
        if (const auto f = fixed.find(h); f != fixed.end()) { cols.push_back({f->second, 0}); continue; }
        const size_t dot = h.find('.');
        const std::string id = dot == std::string::npos ? "" : h.substr(0, dot), what = dot == std::string::npos ? "" : h.substr(dot + 1);
        if (!id.empty() && (what == "temp_c" || what == "target_c")) {
            size_t k = std::find(d.rooms.begin(), d.rooms.end(), id) - d.rooms.begin();
            if (k == d.rooms.size()) d.rooms.push_back(id);
            cols.push_back({what == "temp_c" ? roomTemp : roomTarget, k});
        } else {
            cols.push_back({ignore, 0});
            if (std::find(d.ignored.begin(), d.ignored.end(), h) == d.ignored.end()) d.ignored.push_back(h);
        }
    }
    size_t lineNo = 1;
    while (std::getline(in, line)) {
        ++lineNo;
        if (line.empty() || line[0] == '#' || line == "\r") continue;
        const auto f = split(line);
        Row r;
        bool haveUtc = false;
        for (size_t i = 0; i < f.size() && i < cols.size(); ++i) {
            const auto& v = f[i];
            switch (cols[i].first) {
                case utc: if (const auto t = number(v)) { r.utc = int64_t(std::llround(*t)); haveUtc = true; } break;
                case flow: r.flow = number(v); break;
                case ret: r.ret = number(v); break;
                case burner: r.burner = flag(v); break;
                case heating: r.heatingActive = flag(v); break;
                case dhw: r.dhw = flag(v); break;
                case modulation: r.modulation = number(v); break;
                case e32Heat: r.e32Heat = flag(v); break;
                case e32Flow: r.e32Flow = number(v); break;
                case e32Reason: r.e32Reason = v; break;
                case thermostat: r.thermostat = number(v); break;
                case outdoor: r.outdoor = number(v); break;
                case mode: r.mode = v; break;
                case roomTemp: case roomTarget: {
                    if (r.rooms.size() <= cols[i].second) r.rooms.resize(cols[i].second + 1);
                    (cols[i].first == roomTemp ? r.rooms[cols[i].second].temp : r.rooms[cols[i].second].target) = number(v);
                    break;
                }
                case ignore: break;
            }
        }
        if (!haveUtc) fail(path + ":" + std::to_string(lineNo) + ": no utc");
        d.rows.push_back(std::move(r));
    }
}
void finishData(Data& d) {
    for (auto& r : d.rows) r.rooms.resize(d.rooms.size());
    std::stable_sort(d.rows.begin(), d.rows.end(), [](const Row& a, const Row& b) { return a.utc < b.utc; });
    // Equal timestamps: the later file wins.
    std::vector<Row> out;
    for (auto& r : d.rows) { if (!out.empty() && out.back().utc == r.utc) out.back() = std::move(r); else out.push_back(std::move(r)); }
    d.rows = std::move(out);
    if (d.rows.size() < 2) fail("fewer than two rows");
}

// --- options -------------------------------------------------------------------------
struct Options {
    std::vector<std::string> files, modes{"shadow", "active"};
    std::string json, text, plan, schedule, tz = "CET-1CEST,M3.5.0,M10.5.0/3", emitter = "floor";
    int minFlow = 30, maxFlow = 60, holdS = 60;
    bool grace = true, recordedRequest = false, weatherCurve = false, applyLearned = false, bridge = FlowLearner::Params{}.bridgeHotWater;
};
Options parseArgs(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const auto value = [&]() -> std::string { if (i + 1 >= argc) fail("missing value for " + a); return argv[++i]; };
        if (a == "--mode") {
            o.modes.clear();
            std::stringstream ss(value()); std::string m;
            while (std::getline(ss, m, ',')) {
                if (m != "shadow" && m != "active" && m != "recorded") fail("unknown mode " + m);
                o.modes.push_back(m);
            }
        } else if (a == "--plan") o.plan = value();
        else if (a == "--schedule") o.schedule = value();
        else if (a == "--emitter") { o.emitter = value(); if (o.emitter != "floor" && o.emitter != "radiator") fail("emitter: floor or radiator"); }
        else if (a == "--min-flow") o.minFlow = std::atoi(value().c_str());
        else if (a == "--max-flow") o.maxFlow = std::atoi(value().c_str());
        else if (a == "--hold-s") o.holdS = std::max(stepS, int64_t(std::atoi(value().c_str())));
        else if (a == "--tz") o.tz = value();
        else if (a == "--json") o.json = value();
        else if (a == "--text") o.text = value();
        else if (a == "--no-grace") o.grace = false;
        else if (a == "--recorded-request") o.recordedRequest = true;
        else if (a == "--weather-curve") o.weatherCurve = true;
        else if (a == "--apply-learned") o.applyLearned = true;
        else if (a == "--bridge-hot-water") o.bridge = true;
        else if (a == "--no-bridge-hot-water") o.bridge = false;
        else if (a == "-h" || a == "--help") { std::puts("usage: replay [options] <data.csv> [more.csv ...] (tools/replay/README.md)"); std::exit(0); }
        else if (!a.empty() && a[0] == '-') fail("unknown option " + a);
        else o.files.push_back(a);
    }
    if (o.files.empty()) fail("usage: replay [options] <data.csv> [more.csv ...]");
    return o;
}

using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json parseJson(const std::string& text) { return Json(cJSON_Parse(text.c_str()), cJSON_Delete); }

RoomPlan makePlan(const Options& o, const Data& d) {
    std::string text;
    if (!o.plan.empty()) {
        std::ifstream in(o.plan);
        if (!in) fail("cannot read " + o.plan);
        std::stringstream ss; ss << in.rdbuf(); text = ss.str();
    } else {
        char head[160];
        std::snprintf(head, sizeof head, R"({"schema":1,"revision":1,"mode":"shadow","minimum_flow_c":%d,"maximum_flow_c":%d,"rooms":[)", o.minFlow, o.maxFlow);
        text = head;
        for (size_t i = 0; i < d.rooms.size(); ++i) {
            const auto& id = d.rooms[i];
            text += (i ? "," : "") + std::string(R"({"id":")") + id + R"(","name":")" + id + R"(","state":"active","inactive_until":0,"emitter":")"
                + o.emitter + R"(","sources":[{"type":"ha","id":"sensor.)" + id + R"("}],"setpoint_entity":"sensor.)" + id
                + R"(","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500)" + (o.schedule.empty() ? "" : ",\"schedule\":" + o.schedule) + "}";
        }
        text += "]}";
    }
    const auto root = parseJson(text);
    RoomPlan p;
    if (const char* e = RoomPlan::parse(root.get(), p)) fail(std::string("plan: ") + e);
    if (p.rooms.empty()) fail("plan: no rooms");
    return p;
}

// --- time ----------------------------------------------------------------------------
std::string local(int64_t utc, const char* format = "%Y-%m-%d %H:%M") {
    const time_t t = time_t(utc);
    struct tm tm{};
    localtime_r(&t, &tm);
    char b[40];
    std::strftime(b, sizeof b, format, &tm);
    return b;
}
std::string localDayText(int64_t utc) { return local(utc, "%Y-%m-%d"); }
double round1(double v) { return std::round(v * 10) / 10; }
double round2(double v) { return std::round(v * 100) / 100; }
std::optional<int16_t> centi(Opt v) { return v ? std::optional<int16_t>(int16_t(std::lround(*v * 100))) : std::nullopt; }
std::optional<uint8_t> byte(Opt v) { return v ? std::optional<uint8_t>(uint8_t(std::clamp(std::lround(*v), 0l, 255l))) : std::nullopt; }
void addOptional(cJSON* o, const char* key, Opt v) { if (v) cJSON_AddNumberToObject(o, key, *v); else cJSON_AddNullToObject(o, key); }
void addLocal(cJSON* o, const char* key, std::optional<int64_t> utc) {
    if (utc) cJSON_AddStringToObject(o, key, local(*utc).c_str()); else cJSON_AddNullToObject(o, key);
}

// The 10 s timeline: every step from the first row to the last, with the last row at or
// before it while it is at most hold_s old; otherwise the step is a gap (nothing is fed).
template <class Fn> void forEachStep(const Data& d, const Options& o, Fn&& fn) {
    const int64_t t0 = d.rows.front().utc, t1 = d.rows.back().utc;
    size_t k = 0;
    for (int64_t t = t0; t <= t1; t += stepS) {
        while (k + 1 < d.rows.size() && d.rows[k + 1].utc <= t) ++k;
        const Row& r = d.rows[k];
        fn(t, t - r.utc <= o.holdS ? &r : nullptr);
    }
}
// The firmware: burner on = modulation > 0 (EmsController::activeHeatView); the burner bit only without it.
Flag burnerOf(const Row& r) { return r.modulation ? Flag(*r.modulation > 0) : r.burner; }

// --- what the data itself shows ------------------------------------------------------
struct DataDay {
    std::string day;
    int64_t observedS = 0, dhwS = 0, heatingActiveS = 0, thermostatHeatS = 0, recordedHeatS = 0, activeS = 0;
    int starts = 0, heatingBurns = 0, hotWaterBurns = 0;
    int64_t heatingBurnS = 0;
    double outdoorSum = 0, outdoorMin = 1e9, outdoorMax = -1e9; int64_t outdoorN = 0;
};
std::vector<DataDay> dataDays(const Data& d, const Options& o) {
    std::vector<DataDay> days;
    Flag last;
    struct { bool on = false, dhw = false; int64_t start = 0; size_t day = 0; } burn;
    const auto close = [&](int64_t t) {
        if (!burn.on) return;
        auto& day = days[burn.day];
        if (burn.dhw) ++day.hotWaterBurns; else { ++day.heatingBurns; day.heatingBurnS += t - burn.start; }
        burn.on = false;
    };
    forEachStep(d, o, [&](int64_t t, const Row* r) {
        const std::string name = localDayText(t);
        if (days.empty() || days.back().day != name) { days.push_back({}); days.back().day = name; }
        auto& day = days.back();
        if (!r) { close(t); last.reset(); return; }
        day.observedS += stepS;
        if (r->dhw.value_or(false)) day.dhwS += stepS;
        if (r->heatingActive.value_or(false)) day.heatingActiveS += stepS;
        if (r->thermostat && *r->thermostat >= ShadowComparison::tadoHeatFromC) day.thermostatHeatS += stepS;
        if (r->e32Heat.value_or(false)) day.recordedHeatS += stepS;
        if (r->mode == "active") day.activeS += stepS;
        if (r->outdoor) { day.outdoorSum += *r->outdoor; ++day.outdoorN; day.outdoorMin = std::min(day.outdoorMin, *r->outdoor); day.outdoorMax = std::max(day.outdoorMax, *r->outdoor); }
        const Flag on = burnerOf(*r);
        if (on && *on && last && !*last) { ++day.starts; burn = {true, r->dhw.value_or(false), t, days.size() - 1}; }
        else if (on && *on && burn.on) burn.dhw = burn.dhw || r->dhw.value_or(false);
        else if (on && !*on) close(t);
        if (!on) { close(t); }
        last = on;
    });
    return days;
}

// A recorded target rise (the program the house actually ran) and how the room warmed up.
struct Rise {
    size_t room = 0;
    int64_t atUtc = 0;
    std::optional<int64_t> dropUtc;
    int16_t from = 0, to = 0;
    int64_t windowUtc = 0; // planner evaluations from here (the drop, at most 8 h before)
    int64_t untilUtc = 0;  // the next target change (or 6 h after the rise)
    std::optional<double> roomAtRise;
    std::optional<int64_t> heatStart, reached;
    bool needed = true;    // the room was below the new target at the rise
};
std::vector<Rise> findRises(const Data& d, const Options& o) {
    std::vector<Rise> out;
    for (size_t room = 0; room < d.rooms.size(); ++room) {
        // Change points of the known target, blips under 10 min removed, across no gap.
        struct Point { int64_t t; int16_t v; bool continuous; };
        std::vector<Point> points;
        int64_t lastT = 0;
        for (const auto& r : d.rows) {
            const auto v = centi(r.rooms[room].target);
            if (!v) continue;
            const bool continuous = !points.empty() && r.utc - lastT <= o.holdS;
            if (points.empty() || points.back().v != *v) points.push_back({r.utc, *v, continuous});
            lastT = r.utc;
        }
        std::vector<Point> steady;
        for (size_t i = 0; i < points.size(); ++i) {
            const int64_t until = i + 1 < points.size() ? points[i + 1].t : d.rows.back().utc;
            if (until - points[i].t < 600 && i + 1 < points.size()) continue;
            if (!steady.empty() && steady.back().v == points[i].v) continue;
            steady.push_back(points[i]);
        }
        for (size_t i = 1; i < steady.size(); ++i) {
            if (steady[i].v - steady[i - 1].v < 30 || !steady[i].continuous) continue;
            Rise r;
            r.room = room; r.atUtc = steady[i].t; r.from = steady[i - 1].v; r.to = steady[i].v;
            if (steady[i - 1].t > steady[i].t - 86400 && i >= 2 && steady[i - 1].v < steady[i - 2].v) r.dropUtc = steady[i - 1].t;
            r.windowUtc = std::max(r.dropUtc.value_or(r.atUtc - 8 * 3600), r.atUtc - int64_t(WarmupPlanner::maxLeadS));
            r.untilUtc = std::min(i + 1 < steady.size() ? steady[i + 1].t : d.rows.back().utc, r.atUtc + 6 * 3600);
            out.push_back(r);
        }
    }
    // The actual warm-up, while the new target held: when the room reached it, and the start of
    // the controlling heat request's run (an off->on seen in the window) that got it there.
    for (auto& rise : out) {
        std::optional<bool> on;
        std::optional<int64_t> runStart;
        forEachStep(d, o, [&](int64_t t, const Row* r) {
            if (t < rise.windowUtc || rise.reached || t > rise.untilUtc) return;
            if (!r) { on.reset(); return; }
            const auto temp = centi(r->rooms[rise.room].temp);
            if (t >= rise.atUtc && !rise.roomAtRise && temp) {
                rise.roomAtRise = *temp / 100.0;
                rise.needed = *temp < rise.to - 10;
            }
            Flag heat;
            if (r->mode == "active") heat = r->e32Heat;
            else if (r->thermostat) heat = *r->thermostat >= ShadowComparison::tadoHeatFromC;
            if (heat && *heat && on && !*on) runStart = t;
            if (heat) on = *heat;
            if (t >= rise.atUtc && temp && *temp >= rise.to - 10) { rise.reached = t; if (rise.needed) rise.heatStart = runStart; }
        });
    }
    return out;
}

// A one-day program (every weekday) with the recorded drop and rise.
RoomSchedule riseSchedule(const Rise& r) {
    RoomSchedule s;
    const uint16_t up = RoomSchedule::localAt(r.atUtc).minute;
    std::vector<RoomSchedule::Point> p;
    if (r.dropUtc && RoomSchedule::localAt(*r.dropUtc).minute != up) {
        const uint16_t down = RoomSchedule::localAt(*r.dropUtc).minute;
        if (down < up) p = {{0, r.to}, {down, r.from}, {up, r.to}};
        else p = {{0, r.from}, {up, r.to}, {down, r.from}};
    } else p = {{0, r.from}, {up, r.to}};
    if (p.size() > 1 && p[1].minute == 0) p.erase(p.begin());
    for (auto& day : s.days) { day.count = uint8_t(p.size()); for (size_t i = 0; i < p.size(); ++i) day.points[i] = p[i]; }
    return s;
}

// --- one run -------------------------------------------------------------------------
struct PlannerCheck {
    long evaluations = 0, withoutCooling = 0, overDefault = 0, learned = 0;
    double maxOverMin = 0;
    // Without a cooling model the start temperature is the night setpoint (or a colder reading):
    // the lead stays within the default lead for that shortfall, in the planner's 5 min steps.
    void add(const WarmupPlanner::Start& st, const FlowLearner& l, size_t room) {
        if (st.reason[0] != 'p') return;
        ++evaluations;
        if (st.confidence[0] == 'l') ++learned;
        if (l.heatModel(room).lossPerHour) return;
        ++withoutCooling;
        const uint32_t bound = WarmupPlanner::defaultLeadS(l.emitter(room), int16_t(st.rise.toCentiC - st.startTemperatureCentiC), l.tuning());
        const uint32_t allowed = (bound + 299) / 300 * 300;
        if (st.leadS > allowed) { ++overDefault; maxOverMin = std::max(maxOverMin, (st.leadS - allowed) / 60.0); }
    }
    cJSON* json() const {
        cJSON* o = cJSON_CreateObject();
        cJSON_AddNumberToObject(o, "evaluations", evaluations);
        cJSON_AddNumberToObject(o, "learned", learned);
        cJSON_AddNumberToObject(o, "without_cooling_model", withoutCooling);
        cJSON_AddNumberToObject(o, "over_default_lead", overDefault);
        cJSON_AddNumberToObject(o, "max_over_default_min", round1(maxOverMin));
        return o;
    }
};
cJSON* startJson(int64_t at, const WarmupPlanner::Start& st) {
    cJSON* o = cJSON_CreateObject();
    cJSON_AddStringToObject(o, "at_local", local(at).c_str());
    cJSON_AddStringToObject(o, "reason", st.reason);
    if (st.reason[0] != 'p') return o;
    cJSON_AddStringToObject(o, "rise_local", local(st.rise.atUtc).c_str());
    cJSON_AddStringToObject(o, "start_local", local(st.startUtc).c_str());
    cJSON_AddNumberToObject(o, "lead_min", (st.leadS + 30) / 60);
    cJSON_AddNumberToObject(o, "start_temperature_c", st.startTemperatureCentiC / 100.0);
    cJSON_AddNumberToObject(o, "flow_c", st.flowC);
    cJSON_AddStringToObject(o, "confidence", st.confidence);
    cJSON_AddBoolToObject(o, "reachable", st.reachable);
    cJSON_AddBoolToObject(o, "start_now", st.startNow);
    return o;
}
// The keys of one FlowLearner room worth following per day.
cJSON* learnerProgress(const FlowLearner& l, size_t room) {
    cJSON* full = l.roomJson(room);
    cJSON* o = cJSON_CreateObject();
    for (const char* key : {"id", "readiness", "segments", "periods", "rejected", "last", "cool_segments", "power_segments", "loss_per_h", "capacity_kwh_per_k"})
        if (cJSON* v = cJSON_GetObjectItemCaseSensitive(full, key)) cJSON_AddItemToObject(o, key, cJSON_Duplicate(v, true));
    cJSON_Delete(full);
    return o;
}

struct RunDay {
    std::string day;
    int64_t e32HeatS = 0, activeS = 0;
    std::map<std::string, int64_t> learnerStatus, flowSource;
};

// rc.5 (P4): the run's figures for tools/replay/score.py ("score" in each run). While the run's request
// (the E32's, computed or --recorded-request) asks heat: hours, burner starts for heating (an off->on
// edge of the burner, not hot water), the mean request, and the measured flow and return without hot
// water. Plus the learner's heating energy (GasCalibration::heatingKwh, before the meter's calibration),
// the optimum-start hours, every judged morning (ArrivalLearner) and, with P1, the held events.
struct Score {
    int64_t heatS = 0, startS = 0;
    long starts = 0, heatingStarts = 0;
    double requestSum = 0, flowSum = 0, returnSum = 0;
    long requestN = 0, flowN = 0, returnN = 0;
    Flag lastBurner;
    struct Arrival { std::string room; int64_t atUtc; int16_t errorMin; };
    std::vector<Arrival> arrivals;
    uint64_t held = 0;
    uint16_t heldLast = 0;
    long restFloorChanges = 0;
    void step(const FlowDemand::Request& request, bool optimumStart, Flag burner, Flag dhw, std::optional<int16_t> flow, std::optional<int16_t> ret) {
        const bool hotWater = dhw.value_or(false);
        const bool start = burner && *burner && lastBurner && !*lastBurner && !hotWater;
        if (burner) lastBurner = burner;
        if (start) ++starts;
        if (!request.heat) return;
        heatS += stepS;
        if (optimumStart) startS += stepS;
        if (start) ++heatingStarts;
        requestSum += request.flowC; ++requestN;
        if (hotWater) return;
        if (flow) { flowSum += *flow / 100.0; ++flowN; }
        if (ret) { returnSum += *ret / 100.0; ++returnN; }
    }
    void gap() { lastBurner.reset(); }
};

cJSON* run(const Data& d, const Options& o, const RoomPlan& basePlan, const std::vector<int>& csvRoom, const std::string& mode,
           const std::vector<Rise>& rises) {
    RoomPlan plan = basePlan;
    plan.mode = mode == "active" ? RoomPlan::Mode::active : RoomPlan::Mode::shadow;
    FlowLearner::Params lp; lp.bridgeHotWater = o.bridge;
    RoomEngine engine; engine.setPlan(plan);
    FlowLearner learner(lp); learner.setPlan(plan);
    FlowPolicy policy; policy.setPlan(plan);  // rc.4: the arrival factors and the start latch by room id
    AutoTuner tuner; tuner.setPlan(plan);
    BurnerCycleMonitor cycles;
    Scoreboard board; // HeatingController::stepScoreboard (rc.4): the local days HouseModel reads
#ifdef REPLAY_BOILER_RESPONSE
    BoilerResponse boiler; replay_detect::setPlan(boiler, plan);
#endif
#ifdef REPLAY_HOUSE_MODEL
    HouseModel house; replay_detect::setPlan(house, plan);
    int64_t houseHour = -1;
    int32_t houseDay = INT32_MIN;
#endif
#ifdef REPLAY_FREE_HEAT
    FreeHeat freeHeat; replay_detect::setPlan(freeHeat, plan);
#endif
    FlowSettings settings; settings.weatherCurve = o.weatherCurve; settings.applyLearned = o.applyLearned;
    // HeatingController::effectiveTuning: AutoTuner's knobs; rc.5 (P1, RestFloor) with the boiler's own
    // rest as a floor under min_off_s while no room is more than 0.3 degC below its target.
    bool cold = false;
    const auto effective = [&] {
        auto t = tuner.effective(settings.tuning, settings.manual);
#ifdef REPLAY_BOILER_RESPONSE
        replay_detect::restFloor(t, boiler.restS(), cold);
#endif
        return t;
    };
    // HeatingController::applyFlowSettings: the knobs in effect for every part.
    ControlTuning inEffect;
    const auto applySettings = [&] {
        auto applied = settings; applied.tuning = inEffect = effective();
        policy.setSettings(applied); learner.setApplied(settings.applyLearned);
        learner.setTuning(applied.tuning); engine.setTuning(applied.tuning);
    };
    applySettings();
    (void)cold;
    Score score;
    const int64_t t0 = d.rows.front().utc;
    const uint64_t offset = o.grace ? 0 : AutoTuner::graceMs + 1000; // grace: the E32 booted at the first row
    const size_t rooms = plan.rooms.size();

    cJSON* out = cJSON_CreateObject();
    cJSON_AddStringToObject(out, "mode", mode.c_str());
    cJSON_AddStringToObject(out, "learner_reference", mode == "shadow" ? "thermostat_0x1a"
                            : firmwareHasReference ? "e32_request" : "thermostat_0x1a_absent");
    cJSON* tunerOut = cJSON_AddObjectToObject(out, "autotuner");
    cJSON* evaluations = cJSON_AddArrayToObject(tunerOut, "evaluations");
    cJSON* proposals = cJSON_AddArrayToObject(tunerOut, "proposals");
    cJSON* learnerOut = cJSON_AddObjectToObject(out, "learner");
    cJSON* learnerDays = cJSON_AddArrayToObject(learnerOut, "by_day");
    cJSON* learnerEvents = cJSON_AddArrayToObject(learnerOut, "events");
    std::vector<std::pair<uint16_t, uint16_t>> learnedBefore(rooms); // segments, cooling segments
    cJSON* policyOut = cJSON_AddObjectToObject(out, "flow_policy");
    cJSON* policyDays = cJSON_AddArrayToObject(policyOut, "by_day");
    cJSON* plannerOut = cJSON_AddObjectToObject(out, "planner");
    cJSON* schedulePlans = cJSON_AddArrayToObject(plannerOut, "schedule");
    cJSON* risesOut = cJSON_AddArrayToObject(plannerOut, "rises");
    PlannerCheck check;

    struct RiseRun { RoomSchedule schedule; cJSON* first = nullptr; cJSON* last = nullptr; std::optional<int64_t> startNow; long evaluations = 0; };
    std::vector<RiseRun> riseRuns(rises.size());
    for (size_t i = 0; i < rises.size(); ++i) riseRuns[i].schedule = riseSchedule(rises[i]);

    std::vector<RunDay> days;
    long agree = 0, compared = 0;
    bool prevActive = false;
    uint8_t prevCommand = 0;
    int64_t lastStep = -1; // the previous step with data (its local day is the one a day change closes)
    const auto closeDay = [&](int64_t at) {
        cJSON* ld = cJSON_CreateObject();
        cJSON_AddStringToObject(ld, "day", days.back().day.c_str());
        cJSON_AddStringToObject(ld, "until_local", local(at).c_str());
        cJSON_AddNumberToObject(ld, "heating_periods", learner.heatingPeriods());
        cJSON* lr = cJSON_AddArrayToObject(ld, "rooms");
        for (size_t i = 0; i < rooms; ++i) cJSON_AddItemToArray(lr, learnerProgress(learner, i));
        cJSON* st = cJSON_AddObjectToObject(ld, "status_min");
        for (const auto& [k, v] : days.back().learnerStatus) cJSON_AddNumberToObject(st, k.c_str(), std::round(v / 60.0));
        cJSON_AddItemToArray(learnerDays, ld);
    };

    forEachStep(d, o, [&](int64_t t, const Row* r) {
        const std::string dayName = localDayText(t);
        if (days.empty() || days.back().day != dayName) {
            if (!days.empty()) closeDay(t);
            days.push_back({}); days.back().day = dayName;
        }
        if (!r) { score.gap(); return; }
        auto& day = days.back();
        const uint64_t now = uint64_t(t - t0) * 1000 + offset;
        const uint32_t unixNow = uint32_t(t);
        const bool active = mode == "active" || (mode == "recorded" && r->mode == "active");
        // Rooms: the HA (or Bluetooth) source and the target entity of every plan room.
        for (size_t i = 0; i < rooms; ++i) {
            if (csvRoom[i] < 0) continue;
            const auto& s = r->rooms[size_t(csvRoom[i])];
            const auto& pr = plan.rooms[i];
            const auto temp = centi(s.temp), target = centi(s.target);
            const auto& src = pr.sources.front();
            if (src.type == RoomPlan::SourceType::ha) engine.haState(src.id, temp, src.id == pr.setpointEntity ? target : std::nullopt, now);
            else engine.bleReading(src.id, temp, now);
            if (!pr.setpointEntity.empty() && pr.setpointEntity != src.id && target) engine.haState(pr.setpointEntity, std::nullopt, target, now);
        }
        const Flag burner = burnerOf(*r);
        const auto flow = centi(r->flow), outdoor = centi(r->outdoor), ret = centi(r->ret);
#ifdef REPLAY_BOILER_RESPONSE
        // rc.5 (P1): the knobs follow the boiler's rest and the rooms' comfort (effectiveTuning).
        cold = false;
        for (size_t i = 0; i < rooms; ++i) cold = cold || (engine.result(i).usable && engine.result(i).errorCentiC > 30);
        if (!(effective() == inEffect)) { applySettings(); ++score.restFloorChanges; }
#endif
        // stepHeating: the rule, then the flow options.
        const auto rule = engine.step(now, unixNow);
        std::array<RoomDemand::Result, RoomPlan::maxRooms> results{};
        for (size_t i = 0; i < rooms && i < results.size(); ++i) results[i] = engine.result(i);
        FlowPolicy::Inputs in;
        in.now = now; in.rule = rule; in.plan = &engine.plan(); in.rooms = results.data(); in.utc = t;
        in.outdoorCentiC = outdoor; in.flowCentiC = flow; in.burnerOn = burner; in.hotWater = r->dhw;
        // rc.5: the learned ceiling while the E32 drives (the guard's last output, P1), the house
        // model's slope (P2) and free heat (P3).
#ifdef REPLAY_BOILER_RESPONSE
        replay_detect::ceiling(in, prevActive, boiler.ceilingC(outdoor));
#endif
#ifdef REPLAY_HOUSE_MODEL
        replay_detect::houseSlope(in, house.slope());
#endif
#ifdef REPLAY_FREE_HEAT
        replay_detect::freeHeat(in, &freeHeat);
#endif
        FlowDemand::Request request = policy.apply(in, learner);
        ++day.flowSource[FlowPolicy::name(policy.source())];
        if (r->e32Heat) { ++compared; if (*r->e32Heat == request.heat) ++agree; }
        if (o.recordedRequest && r->e32Heat) {
            request.heat = *r->e32Heat;
            request.flowC = r->e32Heat.value() ? uint8_t(std::clamp(std::lround(r->e32Flow.value_or(0)), 0l, 100l)) : 0;
            request.reason = r->e32Heat.value() ? FlowDemand::Reason::heating : FlowDemand::Reason::idle;
        }
        if (request.heat) day.e32HeatS += stepS;
        if (active) day.activeS += stepS;
        // stepFlowLearner: the boiler view; the reference from the guard's last command.
        const auto thermostat = active ? std::optional<uint8_t>() : byte(r->thermostat); // active: the old thermostat is off the bus
        const auto modulation = r->modulation ? std::optional<uint8_t>(uint8_t(std::clamp(std::lround(*r->modulation), 0l, 100l))) : std::nullopt;
        FlowLearner::Boiler b{};
        b.flowCentiC = flow; b.burnerOn = burner; b.hotWater = r->dhw; b.requestedFlowC = heatingReference(prevActive, prevCommand, thermostat);
        b.outdoorCentiC = outdoor; b.modulationPct = modulation; b.returnCentiC = ret;
        replay_detect::ownRequest(b, prevActive); // rc.2, as HeatingController: BoilerMinimumFlow learns while the E32 drives
        std::array<FlowLearner::RoomInput, RoomPlan::maxRooms> inputs{};
        for (size_t i = 0; i < rooms && i < inputs.size(); ++i) {
            const auto fresh = engine.fresh(i, now);
            inputs[i] = {fresh.temperature, engine.result(i).setpoint, fresh.source};
        }
        learner.sample(now, b, inputs.data(), rooms);
        day.learnerStatus[learner.status()] += stepS;
        for (size_t i = 0; i < rooms; ++i) {
            const std::pair<uint16_t, uint16_t> nowLearned{learner.segments(i), learner.heatModel(i).coolSegments};
            if (nowLearned == learnedBefore[i]) continue;
            cJSON* e = cJSON_CreateObject();
            cJSON_AddStringToObject(e, "at_local", local(t).c_str());
            cJSON_AddStringToObject(e, "room", plan.rooms[i].id.c_str());
            cJSON_AddStringToObject(e, "kind", nowLearned.first != learnedBefore[i].first ? "segment" : "cooling");
            cJSON_AddNumberToObject(e, "segments", nowLearned.first);
            cJSON_AddNumberToObject(e, "cool_segments", nowLearned.second);
            cJSON_AddItemToArray(learnerEvents, e);
            learnedBefore[i] = nowLearned;
        }
#ifdef REPLAY_BOILER_RESPONSE
        {   // rc.5 (P1), HeatingController::stepHeating: the boiler view, the guard's last command as the
            // request, its output as ownRequest, the rooms' mean temperature and any demand.
            BoilerResponse::Sample s;
            s.now = now; s.utc = t; s.requestC = prevCommand; s.ownRequest = prevActive;
            int32_t sum = 0, n = 0;
            bool demand = false;
            for (size_t i = 0; i < rooms; ++i) {
                const auto& res = engine.result(i);
                demand = demand || (res.usable && engine.demand(i));
                if (res.status == RoomDemand::Status::inactive) continue;
                if (const auto temp = engine.fresh(i, now).temperature) { sum += *temp; ++n; }
            }
            s.demand = demand;
            if (n) s.roomMeanCentiC = int16_t(sum / n);
            s.flowCentiC = flow; s.returnCentiC = ret; s.outdoorCentiC = outdoor;
            s.burnerOn = burner; s.hotWater = r->dhw; s.modulationPct = modulation;
            s.nominalKw = learner.nominalKw(); s.kwhPerM3 = learner.params().kwhPerM3;
            boiler.sample(s);
            const uint16_t held = boiler.heldToday();
            score.held += held >= score.heldLast ? uint64_t(held - score.heldLast) : held; // a new local day starts at 0
            score.heldLast = held;
        }
#endif
#ifdef REPLAY_FREE_HEAT
        {   // rc.5 (P3): no heat reached the rooms while the burner was off for heating and nothing asked heat
            // (the E32's command while it drives, else the old thermostat's 0x1A).
            const auto ref = heatingReference(prevActive, prevCommand, thermostat);
            const bool delivered = (burner.value_or(false) && !r->dhw.value_or(false)) || (ref && *ref >= ShadowComparison::tadoHeatFromC);
            std::array<FreeHeat::RoomSample, RoomPlan::maxRooms> free{};
            for (size_t i = 0; i < rooms && i < free.size(); ++i) { free[i].temperatureCentiC = engine.fresh(i, now).temperature; free[i].heatDelivered = delivered; }
            freeHeat.sample(now, t, outdoor, free.data(), rooms);
        }
#endif
        // HeatingController::stepScoreboard: the day's outdoor and heating energy, and the judged mornings.
        board.step(t, lastStep >= 0 && t > lastStep ? uint32_t(std::min<int64_t>(t - lastStep, 60)) : 0, outdoor, learner.gas().heatingKwh());
        for (ArrivalLearner::Event ev; policy.arrival().pop(ev);) {
            board.arrival(ev.room, ev.atUtc, ev.errorMin);
            score.arrivals.push_back({ev.room < plan.rooms.size() ? plan.rooms[ev.room].id : std::to_string(ev.room), ev.atUtc, ev.errorMin});
        }
#ifdef REPLAY_HOUSE_MODEL
        if (t / 3600 != houseHour || RoomSchedule::localDay(t) != houseDay) { // rc.5 (P2): hourly and at the day change
            houseHour = t / 3600; houseDay = RoomSchedule::localDay(t);
            HouseModel::Inputs hi;
            hi.learner = &learner; hi.board = &board; hi.plan = &engine.plan();
#ifdef REPLAY_BOILER_RESPONSE
            hi.kwPerFlowK = boiler.kwPerFlowK();
#endif
            house.update(hi);
        }
#endif
        score.step(request, policy.source() == FlowPolicy::Source::optimumStart, burner, r->dhw, flow, ret);
        // stepActiveHeat (approximated): the guard sends the request within the plan's limits, at least
        // the boiler's learned minimum (HeatingController: FlowLearner::effectiveMinimumC).
        prevActive = active;
        prevCommand = active && request.heat
            ? uint8_t(std::clamp<int>(request.flowC, std::max(plan.minimumFlowC, replay_detect::lowestFlow(learner, plan.minimumFlowC)), plan.maximumFlowC)) : 0;
        // stepAutoTuner.
        if (burner && r->dhw) cycles.observe(*burner, *r->dhw, now);
        const auto tuning = engine.tuning();
        std::array<AutoTuner::Room, RoomPlan::maxRooms> tunerRooms{};
        for (size_t i = 0; i < rooms && i < tunerRooms.size(); ++i) {
            const auto& res = engine.result(i);
            if (res.usable && res.status != RoomDemand::Status::inactive) tunerRooms[i] = {res.temperature, res.setpoint, engine.demand(i)};
        }
        AutoTuner::Step s;
        s.now = now; s.utc = unixNow; s.request = request; s.burnerOn = burner; s.hotWater = r->dhw;
        s.shortCycling = cycles.summary(now).shortCycling; s.active = active;
        s.tuning = &tuning; s.rooms = tunerRooms.data(); s.count = rooms;
        if (tuner.sample(s)) {
            std::array<AutoTuner::Learned, RoomPlan::maxRooms> learned{};
            for (size_t i = 0; i < rooms && i < learner.rooms(); ++i) {
                learned[i].emitter = learner.emitter(i);
                if (const auto w = learner.warmupSeconds(i, 100, learner.ruleFlow(100), outdoor))
                    learned[i].minutesPerC = uint16_t(std::min<uint32_t>((*w + 30) / 60, 1000));
            }
            tuner.evaluate(now, unixNow, settings.manual, engine.plan(), learned.data(), rooms);
            const std::string evaluated = lastStep >= 0 ? localDayText(lastStep) : day.day;
            cJSON* e = cJSON_CreateObject();
            cJSON_AddStringToObject(e, "at_local", local(t).c_str());
            cJSON_AddStringToObject(e, "day", evaluated.c_str());
            cJSON_AddBoolToObject(e, "changed", tuner.changed());
            tuner.addStatus(e, now, tuner.effective(settings.tuning, settings.manual), settings.manual);
            // The proposals of this evaluation: "would" (shown) and the log entries made now (applied).
            const cJSON* tj = cJSON_GetObjectItemCaseSensitive(e, "tuning");
            std::vector<std::string> seen;
            const auto addProposal = [&](const cJSON* a, bool applied) {
                const int base = applied ? 1 : 0;
                const char* knob = cJSON_GetArrayItem(a, base)->valuestring;
                if (std::find(seen.begin(), seen.end(), knob) != seen.end()) {
                    if (applied) for (cJSON* p = proposals->child; p; p = p->next)
                        if (!std::strcmp(cJSON_GetObjectItem(p, "knob")->valuestring, knob) && !std::strcmp(cJSON_GetObjectItem(p, "day")->valuestring, evaluated.c_str()))
                            cJSON_ReplaceItemInObject(p, "applied", cJSON_CreateTrue());
                    return;
                }
                seen.push_back(knob);
                cJSON* p = cJSON_CreateObject();
                cJSON_AddStringToObject(p, "day", evaluated.c_str());
                cJSON_AddStringToObject(p, "knob", knob);
                cJSON_AddItemToObject(p, "from", cJSON_Duplicate(cJSON_GetArrayItem(a, base + 1), true));
                cJSON_AddItemToObject(p, "to", cJSON_Duplicate(cJSON_GetArrayItem(a, base + 2), true));
                cJSON_AddStringToObject(p, "reason", cJSON_GetArrayItem(a, base + 3)->valuestring);
                cJSON_AddItemToObject(p, "figure", cJSON_Duplicate(cJSON_GetArrayItem(a, base + 4), true));
                cJSON_AddStringToObject(p, "room", cJSON_GetArrayItem(a, base + 5)->valuestring);
                cJSON_AddBoolToObject(p, "applied", applied);
                cJSON_AddItemToArray(proposals, p);
            };
            for (const cJSON* a = cJSON_GetObjectItem(tj, "would")->child; a; a = a->next) addProposal(a, false);
            for (const cJSON* a = cJSON_GetObjectItem(tj, "log")->child; a; a = a->next)
                if (uint32_t(cJSON_GetArrayItem(a, 0)->valuedouble) == unixNow) addProposal(a, true);
            cJSON_AddItemToArray(evaluations, e);
            if (tuner.changed()) applySettings();
        }
        // The flow options' comparison of yesterday, once a day.
        if (lastStep >= 0 && localDayText(t) != localDayText(lastStep)) {
            Json summary(cJSON_CreateObject(), cJSON_Delete);
            policy.addSummary(summary.get());
            cJSON* y = cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(summary.get(), "flow"), "yesterday");
            cJSON* pd = cJSON_CreateObject();
            cJSON_AddStringToObject(pd, "day", localDayText(lastStep).c_str());
            cJSON_AddItemToObject(pd, "yesterday", cJSON_IsObject(y) ? cJSON_Duplicate(y, true) : cJSON_CreateNull());
            cJSON_AddItemToArray(policyDays, pd);
        }
        // WarmupPlanner: hourly against the plan's own program, every 15 min against each recorded rise.
        for (size_t i = 0; i < rooms; ++i) {
            const auto temp = engine.result(i).temperature;
            if (!temp) continue;
            if (!plan.rooms[i].schedule.empty() && t / 900 != (t - stepS) / 900) {
                const auto st = WarmupPlanner::optimumStart(learner, i, plan.rooms[i].schedule, t, temp, outdoor, policy.arrival().lead(i));
                check.add(st, learner, i);
                if (t / 3600 != (t - stepS) / 3600) {
                    cJSON* p = startJson(t, st);
                    cJSON_AddStringToObject(p, "room", plan.rooms[i].id.c_str());
                    cJSON_AddItemToArray(schedulePlans, p);
                }
            }
        }
        if (t / 900 != (t - stepS) / 900)
            for (size_t k = 0; k < rises.size(); ++k) {
                const auto& rise = rises[k];
                auto& rr = riseRuns[k];
                if (t < rise.windowUtc || t >= rise.atUtc) continue;
                size_t i = rooms;
                for (size_t j = 0; j < rooms; ++j) if (csvRoom[j] == int(rise.room)) i = j;
                if (i == rooms) continue;
                const auto temp = engine.result(i).temperature;
                if (!temp) continue;
                const auto st = WarmupPlanner::optimumStart(learner, i, rr.schedule, t, temp, outdoor, policy.arrival().lead(i));
                if (st.reason[0] != 'p' || std::llabs(st.rise.atUtc - rise.atUtc) >= 60) continue; // the program's minute
                check.add(st, learner, i);
                ++rr.evaluations;
                if (!rr.first) rr.first = startJson(t, st);
                cJSON_Delete(rr.last); rr.last = startJson(t, st);
                if (st.startNow && !rr.startNow) rr.startNow = t;
            }
        lastStep = t;
    });
    closeDay(d.rows.back().utc);

    // Per day of this run.
    cJSON* dayList = cJSON_AddArrayToObject(out, "days");
    for (const auto& day : days) {
        cJSON* o2 = cJSON_CreateObject();
        cJSON_AddStringToObject(o2, "day", day.day.c_str());
        cJSON_AddNumberToObject(o2, "e32_heat_h", round2(day.e32HeatS / 3600.0));
        cJSON_AddNumberToObject(o2, "active_h", round2(day.activeS / 3600.0));
        cJSON* src = cJSON_AddObjectToObject(o2, "flow_source_h");
        for (const auto& [k, v] : day.flowSource) cJSON_AddNumberToObject(src, k.c_str(), round2(v * stepS / 3600.0));
        cJSON_AddItemToArray(dayList, o2);
    }
    cJSON_AddNumberToObject(out, "computed_vs_recorded_heat_agreement", compared ? round2(double(agree) / compared) : -1);
    cJSON_AddNumberToObject(out, "computed_vs_recorded_steps", compared);
    const uint64_t endNow = uint64_t(d.rows.back().utc - t0) * 1000 + offset;
    cJSON* final = cJSON_AddObjectToObject(tunerOut, "final");
    tuner.addStatus(final, endNow, tuner.effective(settings.tuning, settings.manual), settings.manual);
    cJSON_AddNumberToObject(learnerOut, "heating_periods", learner.heatingPeriods());
    cJSON_AddStringToObject(learnerOut, "status", learner.status());
    if (const uint8_t lowest = learner.learnedMinimumC()) cJSON_AddNumberToObject(learnerOut, "boiler_minimum_flow_c", lowest);
    cJSON* learnedRooms = cJSON_AddArrayToObject(learnerOut, "rooms");
    for (size_t i = 0; i < rooms; ++i) {
        cJSON* room = learner.roomJson(i);
#ifdef REPLAY_FREE_HEAT
        freeHeat.addJson(room, i); // rc.5 (P3): "free_heat" per room
#endif
        cJSON_AddItemToArray(learnedRooms, room);
    }
#ifdef REPLAY_BOILER_RESPONSE
    boiler.addJson(out); // rc.5 (P1): "boiler"
#endif
#ifdef REPLAY_HOUSE_MODEL
    house.addJson(out);  // rc.5 (P2): "house"
#endif
    {   // rc.5 (P4): the figures tools/replay/score.py compares.
        cJSON* sc = cJSON_AddObjectToObject(out, "score");
        const auto mean = [&](const char* key, double sum, long n) { addOptional(sc, key, n ? Opt(round1(sum / n)) : std::nullopt); };
        cJSON_AddNumberToObject(sc, "heating_h", round2(score.heatS / 3600.0));
        cJSON_AddNumberToObject(sc, "burner_starts", score.starts);
        cJSON_AddNumberToObject(sc, "heating_starts", score.heatingStarts);
        addOptional(sc, "starts_per_heating_h", score.heatS ? Opt(round2(score.heatingStarts / (score.heatS / 3600.0))) : std::nullopt);
        mean("request_mean_c", score.requestSum, score.requestN);
        mean("flow_mean_c", score.flowSum, score.flowN);
        mean("return_mean_c", score.returnSum, score.returnN);
        cJSON_AddNumberToObject(sc, "heating_kwh", round1(learner.gas().heatingKwh()));
        cJSON_AddNumberToObject(sc, "optimum_start_h", round2(score.startS / 3600.0));
        cJSON* arrivals = cJSON_AddArrayToObject(sc, "arrivals");
        for (const auto& a : score.arrivals) {
            cJSON* x = cJSON_CreateObject();
            cJSON_AddStringToObject(x, "room", a.room.c_str());
            cJSON_AddStringToObject(x, "rise_local", local(a.atUtc).c_str());
            cJSON_AddNumberToObject(x, "error_min", a.errorMin);
            cJSON_AddItemToArray(arrivals, x);
        }
#ifdef REPLAY_BOILER_RESPONSE
        cJSON* b = cJSON_AddObjectToObject(sc, "boiler");
        cJSON_AddNumberToObject(b, "held", double(score.held));
        cJSON_AddStringToObject(b, "state", boiler.state());
        const auto rest = boiler.restS();
        addOptional(b, "rest_s", rest ? Opt(*rest) : std::nullopt);
        const auto absorbed = boiler.absorbedKw(), perK = boiler.kwPerFlowK();
        addOptional(b, "absorbed_kw", absorbed ? Opt(round2(*absorbed)) : std::nullopt);
        addOptional(b, "kw_per_k", perK ? Opt(round2(*perK)) : std::nullopt);
        // The ceiling per outdoor band of 5 K from -10 degC (<-5, -5..0, 0..5, 5..10, 10..15, >=15).
        cJSON* bands = cJSON_AddArrayToObject(b, "ceiling_c");
        for (int16_t mid = -750; mid <= 1750; mid += 500) {
            const auto c = boiler.ceilingC(mid);
            cJSON_AddItemToArray(bands, c ? cJSON_CreateNumber(*c) : cJSON_CreateNull());
        }
        cJSON_AddNumberToObject(b, "rest_floor_changes", score.restFloorChanges);
#endif
    }
    // rc.4: the arrival feedback per room ({"factor","events","last_error_min","last_at_utc"} or null).
    cJSON* arrivals = cJSON_AddArrayToObject(learnerOut, "arrival");
    for (size_t i = 0; i < rooms; ++i) cJSON_AddItemToArray(arrivals, policy.arrival().json(i));
    {
        Json status(cJSON_CreateObject(), cJSON_Delete);
        policy.addStatus(status.get(), false);
        if (cJSON* f = cJSON_GetObjectItemCaseSensitive(status.get(), "flow")) cJSON_AddItemToObject(policyOut, "final", cJSON_Duplicate(f, true));
    }
    for (size_t k = 0; k < rises.size(); ++k) {
        const auto& rise = rises[k];
        auto& rr = riseRuns[k];
        cJSON* p = cJSON_CreateObject();
        cJSON_AddStringToObject(p, "room", d.rooms[rise.room].c_str());
        cJSON_AddStringToObject(p, "rise_local", local(rise.atUtc).c_str());
        cJSON_AddNumberToObject(p, "evaluations", rr.evaluations);
        cJSON_AddItemToObject(p, "first", rr.first ? rr.first : cJSON_CreateNull());
        cJSON_AddItemToObject(p, "last", rr.last ? rr.last : cJSON_CreateNull());
        addLocal(p, "start_now_local", rr.startNow);
        if (rr.startNow) cJSON_AddNumberToObject(p, "planned_lead_min", (rise.atUtc - *rr.startNow) / 60);
        else cJSON_AddNullToObject(p, "planned_lead_min");
        if (rise.heatStart) cJSON_AddNumberToObject(p, "actual_lead_min", (rise.atUtc - *rise.heatStart) / 60);
        else cJSON_AddNullToObject(p, "actual_lead_min");
        cJSON_AddItemToArray(risesOut, p);
    }
    cJSON_AddItemToObject(plannerOut, "checks", check.json());
    return out;
}

// --- text summary ----------------------------------------------------------------------
std::string fmt(const char* f, ...) __attribute__((format(printf, 1, 2)));
std::string fmt(const char* f, ...) {
    char b[512];
    va_list ap; va_start(ap, f); std::vsnprintf(b, sizeof b, f, ap); va_end(ap);
    return b;
}
double num(const cJSON* o, const char* key, double fallback = 0) {
    const cJSON* v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsNumber(v) ? v->valuedouble : fallback;
}
const char* str(const cJSON* o, const char* key, const char* fallback = "-") {
    const cJSON* v = cJSON_GetObjectItemCaseSensitive(o, key);
    return cJSON_IsString(v) ? v->valuestring : fallback;
}
// "35 min before the switch" / "2 min after the switch" from a lead in minutes; "-" when unknown.
std::string relative(const cJSON* o, const char* key) {
    const cJSON* v = cJSON_GetObjectItemCaseSensitive(o, key);
    if (!cJSON_IsNumber(v)) return "-";
    const int m = int(v->valuedouble);
    return fmt("%d min %s the switch", m < 0 ? -m : m, m < 0 ? "after" : "before");
}
std::string summary(const cJSON* root) {
    std::string s;
    const cJSON* in = cJSON_GetObjectItem(root, "inputs");
    s += fmt("OpenThermostat replay: %d rows, %s .. %s local, rooms:", int(num(in, "rows")), str(in, "first_local"), str(in, "last_local"));
    for (const cJSON* r = cJSON_GetObjectItem(in, "rooms")->child; r; r = r->next) s += fmt(" %s", r->valuestring);
    s += fmt("\nfirmware: FlowLearner heating reference in active mode: %s\n",
             cJSON_IsTrue(cJSON_GetObjectItem(cJSON_GetObjectItem(root, "firmware"), "flow_learner_heating_reference"))
                 ? "the E32's own request (heatingReference)" : "the thermostat's 0x1A only (no heatingReference)");
    s += "\nday         data h  starts  heat/dhw burns  heat burn min  dhw min  tado heat h  E32 heat h (recorded)  outdoor\n";
    for (const cJSON* d = cJSON_GetObjectItem(root, "days")->child; d; d = d->next)
        s += fmt("%-10s  %6.1f  %6d  %4d/%-4d       %8.0f  %7.0f  %11.1f  %21.1f  %s\n", str(d, "day"), num(d, "observed_h"), int(num(d, "starts")),
                 int(num(d, "heating_burns")), int(num(d, "hot_water_burns")), num(d, "heating_burn_min"), num(d, "hot_water_min"),
                 num(d, "thermostat_heat_h"), num(d, "recorded_e32_heat_h"),
                 cJSON_IsNumber(cJSON_GetObjectItem(d, "outdoor_mean_c")) ? fmt("%.1f C", num(d, "outdoor_mean_c")).c_str() : "-");
    const cJSON* warm = cJSON_GetObjectItem(root, "warmups");
    if (cJSON_GetArraySize(warm)) {
        s += "\nrecorded warm-ups (target rises):\n";
        for (const cJSON* w = warm->child; w; w = w->next) {
            s += fmt("  %s %s %.1f -> %.1f C: room %s at the rise", str(w, "room"), str(w, "rise_local"), num(w, "from_c"), num(w, "to_c"),
                     cJSON_IsNumber(cJSON_GetObjectItem(w, "room_at_rise_c")) ? fmt("%.1f", num(w, "room_at_rise_c")).c_str() : "-");
            if (cJSON_IsFalse(cJSON_GetObjectItem(w, "warmup_needed"))) { s += ", already warm\n"; continue; }
            if (!cJSON_IsString(cJSON_GetObjectItem(w, "reached_local"))) { s += ", not reached while the target held\n"; continue; }
            s += fmt(", heat run from %s (%s), reached %s (%d min late)\n", str(w, "heat_start_local"), relative(w, "heat_lead_min").c_str(),
                     str(w, "reached_local"), int(num(w, "late_min")));
        }
    }
    for (const cJSON* r = cJSON_GetObjectItem(root, "runs")->child; r; r = r->next) {
        const char* mode = str(r, "mode");
        s += fmt("\n[%s] learner reference: %s; computed vs recorded E32 heat: %.0f %% of %d steps\n", mode, str(r, "learner_reference"),
                 num(r, "computed_vs_recorded_heat_agreement") * 100, int(num(r, "computed_vs_recorded_steps")));
        const cJSON* t = cJSON_GetObjectItem(r, "autotuner");
        const cJSON* proposals = cJSON_GetObjectItem(t, "proposals");
        s += fmt("[%s] AutoTuner: %d evaluations, state %s, %d proposals%s\n", mode, cJSON_GetArraySize(cJSON_GetObjectItem(t, "evaluations")),
                 str(cJSON_GetObjectItem(cJSON_GetObjectItem(t, "final"), "tuning"), "state"), cJSON_GetArraySize(proposals),
                 cJSON_GetArraySize(proposals) ? ":" : "");
        for (const cJSON* p = proposals->child; p; p = p->next)
            s += fmt("    %s %s %g -> %g (%s, figure %g%s%s)%s\n", str(p, "day"), str(p, "knob"), num(p, "from"), num(p, "to"), str(p, "reason"),
                     num(p, "figure"), *str(p, "room") ? ", room " : "", str(p, "room", ""), cJSON_IsTrue(cJSON_GetObjectItem(p, "applied")) ? " APPLIED" : "");
        const cJSON* l = cJSON_GetObjectItem(r, "learner");
        for (const cJSON* room = cJSON_GetObjectItem(l, "rooms")->child; room; room = room->next) {
            s += fmt("[%s] FlowLearner %s: %s, %d segments in %d periods (%d heating periods), %d rejected, last %s; cooling %d, power %d segments\n",
                     mode, str(room, "id"), str(room, "readiness"), int(num(room, "segments")), int(num(room, "periods")), int(num(l, "heating_periods")),
                     int(num(room, "rejected")), str(room, "last"), int(num(room, "cool_segments")), int(num(room, "power_segments")));
            for (const cJSON* c = cJSON_GetObjectItem(room, "curve")->child; c; c = c->next)
                s += fmt("    flow %.1f C: %.2f C/h (%d segments, %d periods%s)\n", num(c, "flow_c"), num(c, "rate_c_per_h"), int(num(c, "segments")),
                         int(num(c, "periods")), cJSON_IsTrue(cJSON_GetObjectItem(c, "ready")) ? ", ready" : "");
        }
        // rc.5 (P4): the score (tools/replay/score.py compares two runs).
        if (const cJSON* sc = cJSON_GetObjectItem(r, "score")) {
            const auto opt = [&](const char* key, const char* unit) {
                const cJSON* v = cJSON_GetObjectItem(sc, key);
                return cJSON_IsNumber(v) ? fmt("%g%s", v->valuedouble, unit) : std::string("-");
            };
            s += fmt("[%s] score: heating %.2f h, %d heating starts (%s per heating hour), request %s, flow %s, return %s while heating; "
                     "%.1f kWh heating (estimate), optimum start %.2f h, %d judged mornings\n",
                     mode, num(sc, "heating_h"), int(num(sc, "heating_starts")), opt("starts_per_heating_h", "").c_str(), opt("request_mean_c", " C").c_str(),
                     opt("flow_mean_c", " C").c_str(), opt("return_mean_c", " C").c_str(), num(sc, "heating_kwh"), num(sc, "optimum_start_h"),
                     cJSON_GetArraySize(cJSON_GetObjectItem(sc, "arrivals")));
            if (const cJSON* b = cJSON_GetObjectItem(sc, "boiler")) {
                std::string bands;
                for (const cJSON* c = cJSON_GetObjectItem(b, "ceiling_c")->child; c; c = c->next) bands += cJSON_IsNumber(c) ? fmt(" %d", c->valueint) : std::string(" -");
                s += fmt("[%s] boiler: %s, %d held events, rest %s, ceiling by outdoor band (<-5 .. >=15 C):%s\n", mode, str(b, "state"), int(num(b, "held")),
                         cJSON_IsNumber(cJSON_GetObjectItem(b, "rest_s")) ? fmt("%d s", int(num(b, "rest_s"))).c_str() : "-", bands.c_str());
            }
        }
        const cJSON* p = cJSON_GetObjectItem(r, "planner");
        const cJSON* ch = cJSON_GetObjectItem(p, "checks");
        s += fmt("[%s] WarmupPlanner: %d plans (%d learned), %d without a cooling model, %d over the default lead\n", mode, int(num(ch, "evaluations")),
                 int(num(ch, "learned")), int(num(ch, "without_cooling_model")), int(num(ch, "over_default_lead")));
        for (const cJSON* x = cJSON_GetObjectItem(p, "rises")->child; x; x = x->next) {
            const cJSON* first = cJSON_GetObjectItem(x, "first");
            if (!cJSON_IsObject(first)) { s += fmt("    rise %s: no plan (no room temperature in its window)\n", str(x, "rise_local")); continue; }
            s += fmt("    rise %s: at %s planned a start at %s (lead %d min, %s); start now from %s (%s); actual heat run %s\n",
                     str(x, "rise_local"), str(first, "at_local"), str(first, "start_local"), int(num(first, "lead_min")), str(first, "confidence"),
                     str(x, "start_now_local"), relative(x, "planned_lead_min").c_str(), relative(x, "actual_lead_min").c_str());
        }
    }
    return s;
}

bool writeFile(const std::string& path, const std::string& text) {
    std::ofstream f(path, std::ios::binary);
    f << text;
    return bool(f);
}
}  // namespace

int main(int argc, char** argv) {
    const Options o = parseArgs(argc, argv);
    setenv("TZ", o.tz.c_str(), 1);
    tzset();
    Data d;
    for (const auto& f : o.files) readCsv(f, d);
    finishData(d);
    const RoomPlan plan = makePlan(o, d);
    std::vector<int> csvRoom(plan.rooms.size(), -1);
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto it = std::find(d.rooms.begin(), d.rooms.end(), plan.rooms[i].id);
        if (it != d.rooms.end()) csvRoom[i] = int(it - d.rooms.begin());
        else std::fprintf(stderr, "replay: plan room %s has no CSV columns\n", plan.rooms[i].id.c_str());
    }
    const auto rises = findRises(d, o);

    Json root(cJSON_CreateObject(), cJSON_Delete);
    cJSON_AddStringToObject(root.get(), "tool", "openthermostat-replay");
    cJSON_AddNumberToObject(root.get(), "schema", 1);
    cJSON* in = cJSON_AddObjectToObject(root.get(), "inputs");
    cJSON* files = cJSON_AddArrayToObject(in, "files");
    for (const auto& f : d.files) cJSON_AddItemToArray(files, cJSON_CreateString(f.c_str()));
    cJSON_AddNumberToObject(in, "rows", double(d.rows.size()));
    cJSON_AddStringToObject(in, "first_local", local(d.rows.front().utc).c_str());
    cJSON_AddStringToObject(in, "last_local", local(d.rows.back().utc).c_str());
    cJSON_AddStringToObject(in, "tz", o.tz.c_str());
    cJSON* roomList = cJSON_AddArrayToObject(in, "rooms");
    for (const auto& r : d.rooms) cJSON_AddItemToArray(roomList, cJSON_CreateString(r.c_str()));
    cJSON* ignored = cJSON_AddArrayToObject(in, "ignored_columns");
    for (const auto& c : d.ignored) cJSON_AddItemToArray(ignored, cJSON_CreateString(c.c_str()));
    cJSON* fw = cJSON_AddObjectToObject(root.get(), "firmware");
    cJSON_AddBoolToObject(fw, "flow_learner_heating_reference", firmwareHasReference);
    // rc.5: which learners of P1-P3 this build wires, and which of their hooks it found.
    bool boilerResponse = false, ceilingHook = false, restFloorHook = false, houseModel = false, houseSlopeHook = false, freeHeatModule = false, freeHeatHook = false;
#ifdef REPLAY_BOILER_RESPONSE
    boilerResponse = true;
    ceilingHook = replay_detect::CeilingInput<FlowPolicy::Inputs>::value;
    restFloorHook = replay_detect::Complete<RestFloor>::value;
#endif
#ifdef REPLAY_HOUSE_MODEL
    houseModel = true;
    houseSlopeHook = replay_detect::HouseSlopeInput<FlowPolicy::Inputs>::value;
#endif
#ifdef REPLAY_FREE_HEAT
    freeHeatModule = true;
    freeHeatHook = replay_detect::FreeHeatMember<FlowPolicy::Inputs, FreeHeat>::value;
#endif
    cJSON_AddBoolToObject(fw, "boiler_response", boilerResponse);
    cJSON_AddBoolToObject(fw, "flow_policy_ceiling", ceilingHook);
    cJSON_AddBoolToObject(fw, "rest_floor", restFloorHook);
    cJSON_AddBoolToObject(fw, "house_model", houseModel);
    cJSON_AddBoolToObject(fw, "flow_policy_house_slope", houseSlopeHook);
    cJSON_AddBoolToObject(fw, "free_heat", freeHeatModule);
    cJSON_AddBoolToObject(fw, "flow_policy_free_heat", freeHeatHook);
    cJSON* opt = cJSON_AddObjectToObject(root.get(), "options");
    cJSON* modes = cJSON_AddArrayToObject(opt, "modes");
    for (const auto& m : o.modes) cJSON_AddItemToArray(modes, cJSON_CreateString(m.c_str()));
    cJSON_AddBoolToObject(opt, "grace", o.grace);
    cJSON_AddBoolToObject(opt, "recorded_request", o.recordedRequest);
    cJSON_AddBoolToObject(opt, "weather_curve", o.weatherCurve);
    cJSON_AddBoolToObject(opt, "apply_learned", o.applyLearned);
    cJSON_AddBoolToObject(opt, "bridge_hot_water", o.bridge);
    cJSON_AddNumberToObject(opt, "hold_s", o.holdS);
    cJSON_AddStringToObject(opt, "plan", o.plan.empty() ? "default" : o.plan.c_str());
    cJSON_AddNumberToObject(opt, "minimum_flow_c", plan.minimumFlowC);
    cJSON_AddNumberToObject(opt, "maximum_flow_c", plan.maximumFlowC);

    cJSON* days = cJSON_AddArrayToObject(root.get(), "days");
    for (const auto& day : dataDays(d, o)) {
        cJSON* x = cJSON_CreateObject();
        cJSON_AddStringToObject(x, "day", day.day.c_str());
        cJSON_AddNumberToObject(x, "observed_h", round2(day.observedS / 3600.0));
        cJSON_AddNumberToObject(x, "starts", day.starts);
        cJSON_AddNumberToObject(x, "heating_burns", day.heatingBurns);
        cJSON_AddNumberToObject(x, "hot_water_burns", day.hotWaterBurns);
        cJSON_AddNumberToObject(x, "heating_burn_min", round1(day.heatingBurnS / 60.0));
        cJSON_AddNumberToObject(x, "mean_heating_burn_min", day.heatingBurns ? round1(day.heatingBurnS / 60.0 / day.heatingBurns) : 0);
        cJSON_AddNumberToObject(x, "hot_water_min", round1(day.dhwS / 60.0));
        cJSON_AddNumberToObject(x, "heating_active_h", round2(day.heatingActiveS / 3600.0));
        cJSON_AddNumberToObject(x, "thermostat_heat_h", round2(day.thermostatHeatS / 3600.0));
        cJSON_AddNumberToObject(x, "recorded_e32_heat_h", round2(day.recordedHeatS / 3600.0));
        cJSON_AddNumberToObject(x, "recorded_active_h", round2(day.activeS / 3600.0));
        addOptional(x, "outdoor_mean_c", day.outdoorN ? Opt(round1(day.outdoorSum / day.outdoorN)) : std::nullopt);
        addOptional(x, "outdoor_min_c", day.outdoorN ? Opt(day.outdoorMin) : std::nullopt);
        addOptional(x, "outdoor_max_c", day.outdoorN ? Opt(day.outdoorMax) : std::nullopt);
        cJSON_AddItemToArray(days, x);
    }
    cJSON* warm = cJSON_AddArrayToObject(root.get(), "warmups");
    for (const auto& r : rises) {
        cJSON* x = cJSON_CreateObject();
        cJSON_AddStringToObject(x, "room", d.rooms[r.room].c_str());
        cJSON_AddStringToObject(x, "rise_local", local(r.atUtc).c_str());
        cJSON_AddNumberToObject(x, "from_c", r.from / 100.0);
        cJSON_AddNumberToObject(x, "to_c", r.to / 100.0);
        addLocal(x, "drop_local", r.dropUtc);
        addOptional(x, "room_at_rise_c", r.roomAtRise);
        cJSON_AddBoolToObject(x, "warmup_needed", r.needed);
        addLocal(x, "heat_start_local", r.heatStart);
        addOptional(x, "heat_lead_min", r.heatStart ? Opt(double((r.atUtc - *r.heatStart) / 60)) : std::nullopt);
        addLocal(x, "reached_local", r.reached);
        addOptional(x, "late_min", r.reached ? Opt(double((*r.reached - r.atUtc) / 60)) : std::nullopt);
        cJSON_AddItemToArray(warm, x);
    }
    cJSON* runs = cJSON_AddArrayToObject(root.get(), "runs");
    for (const auto& m : o.modes) cJSON_AddItemToArray(runs, run(d, o, plan, csvRoom, m, rises));

    char* text = cJSON_Print(root.get());
    const std::string json = text ? text : "";
    cJSON_free(text);
    if (json.empty()) fail("out of memory");
    if (o.json.empty() && o.text.empty()) std::puts(json.c_str());
    if (!o.json.empty() && !writeFile(o.json, json + "\n")) fail("cannot write " + o.json);
    if (!o.text.empty() && !writeFile(o.text, summary(root.get()))) fail("cannot write " + o.text);
    return 0;
}
