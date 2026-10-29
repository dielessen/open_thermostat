#pragma once
#include "control/FlowDemand.h"
#include "control/RoomPlan.h"
#include "control/ShadowComparison.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
namespace heating::control {
// exp, sqrt and round without newlib's libm members (e_exp/w_exp, wf_sqrt,
// s_round are not in docs/third-party/e32v2-link-review.json; floor is).
namespace learnmath {
// e^x for |x| <= 64: x / 2^10 by a 7-term Taylor series, squared 10 times (rel. error < 1e-10).
inline double exp(double x) {
    x = std::clamp(x, -64.0, 64.0) / 1024.0;
    double term = 1, sum = 1;
    for (int k = 1; k <= 7; ++k) { term *= x / k; sum += term; }
    for (int k = 0; k < 10; ++k) sum *= sum;
    return sum;
}
// Newton iterations from a power-of-two start; 0 for x <= 0.
inline float sqrt(float x) {
    if (!(x > 0)) return 0;
    double y = 1, v = x;
    while (y * y > v * 4) y *= 0.5;
    while (y * y < v * 0.25) y *= 2;
    for (int k = 0; k < 6; ++k) y = 0.5 * (y + v / y);
    return static_cast<float>(y);
}
// Half away from zero, like std::round.
inline double round(double x) { return x < 0 ? -std::floor(-x + 0.5) : std::floor(x + 0.5); }
}
// Learns per room how fast it warms up (degC/h) at each flow temperature, and
// from that the LOWEST flow that still closes a shortfall in an acceptable time
// (owner, 28/29 Oct: "zo laag mogelijk moduleren ... dat ga je vanzelf leren").
// Beta.18: shadow/report only; FlowDemand keeps its rule. Evidence: while some
// controller (now the tado) heats, every room gets stable segments (45 min..3 h,
// flow within 3 degC, no hot water, fresh data); a segment's least-squares room
// slope goes into a 2 degC flow bin. Bins are made non-decreasing (more flow is
// never slower) and, with enough outdoor spread, shifted by one learned outdoor
// slope. Heat-off segments (after the emitter coasted) give the heat-loss rate b
// (1/h) against room - outdoor; heating segments with burner modulation give the
// heat capacity C (kWh/K) of the house as seen from this room: P = C (rate + b dT).
// A gas meter calibrates modulation x nominal power. RAM only: pure,
// single-threaded, call sample() every 10 s (WarmupPlanner.h uses the models).
class FlowLearner {
public:
    static constexpr uint8_t binLowC = 20, binWidthC = 2;
    static constexpr size_t binCount = 20;                     // 20..60 degC
    static constexpr std::array<int16_t, 4> reportShortfalls{0, 50, 100, 200}; // hold, 0.5, 1, 2 degC
    struct Params {
        uint32_t maxGapMs = 60000;                     // a longer silence ends a segment
        uint32_t settleMs = 600000;                    // after a heating start the flow still rises
        uint32_t hotWaterHoldoffMs = 900000;           // after hot water the circuit refills
        uint32_t minSegmentMs = 2700000, maxSegmentMs = 10800000;
        uint8_t flowBandC = 3;                         // requested (else measured) flow stays in this band
        int16_t maxStepCentiC = 30;                    // a bigger jump is a source/offset change
        uint16_t maxRateCentiCPerHour = 300;           // faster: window, sun, cooking, not the emitter
        uint8_t binSegments = 3, binPeriods = 2;       // a bin counts from 3 segments in 2 heating periods
        uint8_t roomSegments = 6, roomPeriods = 3, roomBins = 2;
        float binMemoryHours = 48;                     // older evidence fades beyond this weight
        uint32_t floorCoastMs = 7200000, radiatorCoastMs = 1800000; // heat off this long: pure cooling
        uint32_t minCoolMs = 3600000, maxCoolMs = 21600000;
        uint8_t modelSegments = 3;                     // cooling / power segments before b and C count
        // Gas input at 100 % modulation until HA reports the boiler's (boiler_kw): 22 kW,
        // the owner's EcomLine HRC 22 class; only scales the capacity estimate, and a
        // gas meter calibrates it either way.
        float nominalKw = 22;
        float kwhPerM3 = 9.77f;  // NL gas, Groningen-equivalent upper value, until HA reports its own (gas_kwh_per_m3)
        float returnDropK = 6;   // flow - return when the return is not reported
    };
    // Condensing efficiency against the return temperature: 97.5 % at <= 35 degC,
    // linear to 88.9 % at 55 degC and above (lower flow -> higher efficiency).
    static float efficiency(float returnC) { return 0.975f - std::clamp(returnC - 35.0f, 0.0f, 20.0f) * 0.0043f; }
    // Acceptable warm-up for a shortfall s: base + perDegree x s (minutes).
    // Defaults: floor 1 degC in 2 h, radiator 1 degC in 1 h. Shortfall 0 = hold.
    struct Acceptance {
        uint16_t baseMinutes = 60, perDegreeMinutes = 60;
        static Acceptance of(RoomPlan::Emitter e) { return e == RoomPlan::Emitter::floor ? Acceptance{60, 60} : Acceptance{30, 30}; }
        bool valid() const { return baseMinutes <= 720 && perDegreeMinutes >= 10 && perDegreeMinutes <= 720; }
        float requiredRate(int16_t shortfallCentiC) const { // degC/h
            if (shortfallCentiC <= 0) return 0;
            const float s = shortfallCentiC / 100.0f;
            return s * 60.0f / (baseMinutes + perDegreeMinutes * s);
        }
    };
    // One locked EMS view per step; nullopt = unknown or stale.
    struct Boiler {
        std::optional<int16_t> flowCentiC;     // measured flow
        std::optional<bool> burnerOn, hotWater;
        std::optional<uint8_t> requestedFlowC; // the controlling thermostat's 0x1A
        std::optional<int16_t> outdoorCentiC;
        std::optional<uint8_t> modulationPct;  // burner modulation (share of the gas input)
        std::optional<int16_t> returnCentiC;
    };
    struct RoomInput {
        std::optional<int16_t> temperatureCentiC, setpointCentiC; // fresh reading only
        int8_t source = -1;                                       // leading source, -1 unknown
    };
    struct Advice {
        float requiredRate = 0;
        std::optional<uint8_t> flowC;          // nullopt: not ready
        std::optional<uint32_t> warmupS, ruleWarmupS;
        uint8_t ruleFlowC = 0;                 // FlowDemand's proportional rule for this shortfall
        const char* reason = "not_ready";
        const char* rule = "unknown";          // higher_wasteful / lower_too_slow / similar
    };
    struct HeatModel {
        std::optional<float> lossPerHour;                // b: degC/h lost per K room - outdoor
        std::optional<float> capacityKwhPerK, uaKwPerK;  // calibrated C, and UA = b C
        uint16_t coolSegments = 0, powerSegments = 0;
    };

    FlowLearner() = default;
    explicit FlowLearner(Params p) : p_(p) {}

    // An edit keeps what each room (by id) learned unless its emitter changed;
    // open segments end (source indices may have moved).
    void setPlan(const RoomPlan& plan) {
        std::vector<Room> next(plan.rooms.size());
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            const auto& pr = plan.rooms[i];
            auto old = std::find_if(rooms_.begin(), rooms_.end(), [&](const Room& r) { return r.id == pr.id && r.emitter == pr.emitter; });
            if (old != rooms_.end()) next[i] = std::move(*old);
            else { next[i].id = pr.id; next[i].emitter = pr.emitter; next[i].acceptance = Acceptance::of(pr.emitter); }
            next[i].segment = {};
        }
        rooms_ = std::move(next);
        minFlowC_ = plan.minimumFlowC; maxFlowC_ = plan.maximumFlowC;
    }
    bool setAcceptance(size_t room, Acceptance a) {
        if (room >= rooms_.size() || !a.valid()) return false;
        rooms_[room].acceptance = a; return true;
    }

    void sample(uint64_t now, const Boiler& b, const RoomInput* rooms, size_t count) {
        const bool gap = !haveLast_ || now <= lastMs_ || now - lastMs_ > p_.maxGapMs;
        if (gap || !b.modulationPct || b.hotWater.value_or(true)) gasValid_ = false; // meter interval not comparable
        else predictedKwh_ += *b.modulationPct / 100.0 * p_.nominalKw * double(now - lastMs_) / 3600000.0;
        lastMs_ = now; haveLast_ = true; outdoor_ = b.outdoorCentiC;
        const bool known = b.flowCentiC && b.hotWater && (b.burnerOn || b.requestedFlowC);
        const bool hotWater = b.hotWater.value_or(false);
        const bool requested = b.requestedFlowC && *b.requestedFlowC >= ShadowComparison::tadoHeatFromC;
        const bool heat = known && !hotWater && (b.burnerOn.value_or(false) || requested);
        if (hotWater) holdUntil_ = now + p_.hotWaterHoldoffMs;
        if (heat && (!heating_ || gap)) { ++period_; holdUntil_ = std::max(holdUntil_, now + p_.settleMs); }
        if (!heat && (heating_ || gap || !known || hotWater)) offSince_ = now; // unknown: the emitter may be warm
        heating_ = heat;
        status_ = !known ? "boiler_unknown" : hotWater ? "hot_water" : !heat ? "not_heating" : now < holdUntil_ ? "settling" : "learning";
        const bool usable = heat && now >= holdUntil_;
        const uint8_t ref = requested ? *b.requestedFlowC
            : static_cast<uint8_t>(std::clamp<int>((b.flowCentiC.value_or(0) + 50) / 100, 0, 100));
        // Heat delivered (kW, before gas calibration) for the capacity fit.
        std::optional<float> heatKw;
        if (heat && b.modulationPct && b.flowCentiC)
            heatKw = *b.modulationPct / 100.0f * p_.nominalKw
                * efficiency(b.returnCentiC ? *b.returnCentiC / 100.0f : *b.flowCentiC / 100.0f - p_.returnDropK);
        for (size_t i = 0; i < count && i < rooms_.size(); ++i) {
            auto& r = rooms_[i];
            const bool coasted = known && !heat && !hotWater && now >= holdUntil_
                && now - offSince_ >= (r.emitter == RoomPlan::Emitter::floor ? p_.floorCoastMs : p_.radiatorCoastMs);
            step(r, now, gap, usable ? Kind::heat : coasted ? Kind::cool : Kind::none, ref, b, heatKw, rooms[i]);
        }
    }
    // The gas meter total (m3, e.g. HA sensor.gas_consumed). An interval of at
    // least 1 h without hot water, gaps or unknown modulation calibrates the
    // modulation x nominal power estimate against the real consumption.
    void gasMeter(double totalM3, uint64_t atMs) {
        if (haveGas_ && gasValid_ && totalM3 >= gasM3_ && atMs > gasAtMs_ && atMs - gasAtMs_ >= 3600000 && predictedKwh_ >= 1) {
            const double measured = (totalM3 - gasM3_) * p_.kwhPerM3, ratio = measured / predictedKwh_;
            if (ratio >= 0.3 && ratio <= 3) {
                if (calPredicted_ > 200) { calMeasured_ *= 0.5; calPredicted_ *= 0.5; } // stays current
                calMeasured_ += measured; calPredicted_ += predictedKwh_; gasIntervals_ = sat(gasIntervals_);
            }
        }
        haveGas_ = gasValid_ = true; gasM3_ = totalM3; gasAtMs_ = atMs; predictedKwh_ = 0;
    }
    void gasPrice(float eurPerM3) { if (eurPerM3 > 0 && eurPerM3 <= 20) price_ = eurPerM3; }
    std::optional<float> price() const { return price_; }
    // The last gas meter reading (uptime ms); nullopt: none yet.
    std::optional<uint64_t> gasMeterAt() const { return haveGas_ ? std::optional<uint64_t>(gasAtMs_) : std::nullopt; }
    // Nominal gas input at 100 % modulation from HA (3..60 kW); until then Params::nominalKw.
    bool setNominalKw(float kw) {
        if (!(kw >= 3 && kw <= 60)) return false;
        p_.nominalKw = kw; nominalFromHa_ = true; return true;
    }
    float nominalKw() const { return p_.nominalKw; }
    bool nominalFromHa() const { return nominalFromHa_; }
    // Calorific value from HA (5..15 kWh per m3); until then Params::kwhPerM3.
    bool setKwhPerM3(float kwh) {
        if (!(kwh >= 5 && kwh <= 15)) return false;
        p_.kwhPerM3 = kwh; kwhFromHa_ = true; return true;
    }
    bool kwhPerM3FromHa() const { return kwhFromHa_; }
    const char* status() const { return status_; }
    uint16_t heatingPeriods() const { return period_; }
    // Real / estimated gas; 1 until three intervals were compared.
    float calibration() const { return gasIntervals_ >= 3 ? static_cast<float>(std::clamp(calMeasured_ / calPredicted_, 0.5, 2.0)) : 1.0f; }
    uint16_t gasIntervals() const { return gasIntervals_; }
    const Params& params() const { return p_; }
    size_t rooms() const { return rooms_.size(); }
    RoomPlan::Emitter emitter(size_t room) const { return rooms_[room].emitter; }

    // Lowest learned flow that closes shortfallCentiC within the room's acceptance.
    Advice advise(size_t room, int16_t shortfallCentiC, std::optional<int16_t> outdoorCentiC) const {
        Advice a;
        if (room >= rooms_.size()) return a;
        const auto& r = rooms_[room];
        a.requiredRate = r.acceptance.requiredRate(shortfallCentiC);
        a.ruleFlowC = ruleFlow(shortfallCentiC);
        if (!ready(r)) return a;
        Curve c; const size_t n = curve(r, outdoorCentiC, c);
        size_t k = 0;
        while (k < n && c[k].rate < a.requiredRate) ++k;
        float flow;
        if (k == n) {
            flow = maxFlowC_;
            a.reason = c[n - 1].flowC >= maxFlowC_ - binWidthC ? "not_reachable_in_time" : "above_learned_range";
        } else if (k == 0) {
            flow = c[0].flowC; a.reason = "lowest_learned";
        } else {
            flow = c[k - 1].flowC + (a.requiredRate - c[k - 1].rate) / (c[k].rate - c[k - 1].rate) * (c[k].flowC - c[k - 1].flowC);
            a.reason = "learned";
        }
        a.flowC = static_cast<uint8_t>(std::clamp<double>(std::ceil(double(flow) - 0.01), minFlowC_, maxFlowC_));
        a.warmupS = warmup(c, n, *a.flowC, shortfallCentiC);
        a.ruleWarmupS = warmup(c, n, a.ruleFlowC, shortfallCentiC);
        const int diff = int(a.ruleFlowC) - int(*a.flowC);
        a.rule = !rateAt(c, n, a.ruleFlowC) ? "below_learned_range" // e.g. 30 degC when 32 was the lowest seen
            : diff >= binWidthC ? "higher_wasteful" : diff <= -binWidthC ? "lower_too_slow" : "similar";
        return a;
    }
    // FlowDemand's own rule at a fresh start (integral 0): the proportional part.
    uint8_t ruleFlow(int16_t shortfallCentiC) const {
        FlowDemand::Params fp; fp.minimumFlowC = minFlowC_; fp.maximumFlowC = maxFlowC_;
        return FlowDemand(fp).update(0, true, shortfallCentiC).flowC;
    }
    // Predicted time to close a shortfall at a flow; nullopt while not ready.
    std::optional<uint32_t> warmupSeconds(size_t room, int16_t shortfallCentiC, uint8_t flowC, std::optional<int16_t> outdoorCentiC) const {
        if (room >= rooms_.size() || !ready(rooms_[room])) return std::nullopt;
        Curve c; const size_t n = curve(rooms_[room], outdoorCentiC, c);
        return warmup(c, n, flowC, shortfallCentiC);
    }
    // Learned warm-up rate (degC/h) at a flow; nullopt while not ready or below the learned range.
    std::optional<float> rate(size_t room, uint8_t flowC, std::optional<int16_t> outdoorCentiC) const {
        if (room >= rooms_.size() || !ready(rooms_[room])) return std::nullopt;
        Curve c; const size_t n = curve(rooms_[room], outdoorCentiC, c);
        return rateAt(c, n, flowC);
    }
    const char* readiness(size_t room) const { return room < rooms_.size() ? readiness(rooms_[room]) : "collecting"; }
    uint16_t segments(size_t room) const { return room < rooms_.size() ? rooms_[room].segments : 0; }
    std::optional<float> outdoorSlope(size_t room) const { return room < rooms_.size() ? outdoorSlope(rooms_[room]) : std::nullopt; }
    HeatModel heatModel(size_t room) const {
        HeatModel m;
        if (room >= rooms_.size()) return m;
        const auto& h = rooms_[room].heat;
        m.coolSegments = h.coolSegments; m.powerSegments = h.powerSegments;
        if (h.coolSegments < p_.modelSegments || h.cdd <= 0) return m;
        const double b = std::clamp(h.crd / h.cdd, 0.002, 0.2);
        m.lossPerHour = static_cast<float>(b);
        const double pz = h.spr + b * h.spd, zz = h.srr + 2 * b * h.srd + b * b * h.sdd;
        if (h.powerSegments < p_.modelSegments || zz <= 0 || pz <= 0) return m;
        m.capacityKwhPerK = static_cast<float>(pz / zz * calibration());
        m.uaKwPerK = static_cast<float>(b) * *m.capacityKwhPerK;
        return m;
    }

    // {"schema":1,"applied":false,"status":..,"rooms":[{..,"curve":[..],"advice":[..],"now":..}]}
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        cJSON* list = root ? cJSON_AddArrayToObject(root, "rooms") : nullptr;
        if (!list) { cJSON_Delete(root); return nullptr; }
        cJSON_AddNumberToObject(root, "schema", 1);
        cJSON_AddBoolToObject(root, "applied", false); // beta.18: FlowDemand keeps its rule
        cJSON_AddStringToObject(root, "status", status_);
        cJSON_AddNumberToObject(root, "heating_periods", period_);
        number(root, "outdoor_c", outdoor_ ? std::optional<float>(*outdoor_ / 100.0f) : std::nullopt, 10);
        number(root, "gas_calibration", calibration(), 1000);
        cJSON_AddNumberToObject(root, "gas_intervals", gasIntervals_);
        for (size_t i = 0; i < rooms_.size(); ++i) {
            cJSON* o = roomJson(i);
            if (!o || !cJSON_AddItemToArray(list, o)) { cJSON_Delete(o); cJSON_Delete(root); return nullptr; }
        }
        return root;
    }
    // One room of json() (also published alone as fw/telemetry/heating_learned/<id>).
    cJSON* roomJson(size_t i) const {
        if (i >= rooms_.size()) return nullptr;
        const auto& r = rooms_[i];
        cJSON* o = cJSON_CreateObject();
        if (!o) return nullptr;
        cJSON_AddStringToObject(o, "id", r.id.c_str());
        cJSON_AddStringToObject(o, "emitter", r.emitter == RoomPlan::Emitter::floor ? "floor" : "radiator");
        cJSON_AddStringToObject(o, "readiness", readiness(r));
        cJSON_AddNumberToObject(o, "segments", r.segments);
        cJSON_AddNumberToObject(o, "periods", r.periods);
        cJSON_AddNumberToObject(o, "rejected", r.rejected);
        cJSON_AddStringToObject(o, "last", r.last);
        cJSON_AddBoolToObject(o, "segment_open", r.segment.active);
        cJSON_AddNumberToObject(o, "accept_base_min", r.acceptance.baseMinutes);
        cJSON_AddNumberToObject(o, "accept_per_degree_min", r.acceptance.perDegreeMinutes);
        number(o, "outdoor_slope_c_per_h_per_k", outdoorSlope(r), 1000);
        const auto m = heatModel(i);
        number(o, "loss_per_h", m.lossPerHour, 10000);
        number(o, "capacity_kwh_per_k", m.capacityKwhPerK, 100);
        cJSON_AddNumberToObject(o, "cool_segments", m.coolSegments);
        cJSON_AddNumberToObject(o, "power_segments", m.powerSegments);
        cJSON* curve = cJSON_AddArrayToObject(o, "curve");
        cJSON* advice = cJSON_AddArrayToObject(o, "advice");
        if (!curve || !advice) { cJSON_Delete(o); return nullptr; }
        for (const auto& b : r.bins) {
            if (!b.segments) continue;
            cJSON* p = cJSON_CreateObject();
            if (!p || !cJSON_AddItemToArray(curve, p)) { cJSON_Delete(p); cJSON_Delete(o); return nullptr; }
            const float mean = b.wr / b.w;
            number(p, "flow_c", b.wf / b.w, 10);
            number(p, "rate_c_per_h", mean, 100);
            number(p, "sd_c_per_h", learnmath::sqrt(std::max(0.0f, b.wrr / b.w - mean * mean)), 100);
            cJSON_AddNumberToObject(p, "segments", b.segments);
            cJSON_AddNumberToObject(p, "periods", b.periods);
            cJSON_AddBoolToObject(p, "ready", ready(b));
        }
        for (const auto s : reportShortfalls)
            if (!adviceJson(advice, nullptr, s, advise(i, s, outdoor_))) { cJSON_Delete(o); return nullptr; }
        if (r.shortfall) { if (!adviceJson(o, "now", *r.shortfall, advise(i, *r.shortfall, outdoor_))) { cJSON_Delete(o); return nullptr; } }
        else cJSON_AddNullToObject(o, "now");
        return o;
    }
    static void number(cJSON* o, const char* key, std::optional<float> v, int scale) {
        if (v) cJSON_AddNumberToObject(o, key, learnmath::round(double(*v) * scale) / scale); else cJSON_AddNullToObject(o, key);
    }

private:
    enum class Kind : uint8_t { none, heat, cool };
    struct Bin {
        uint8_t segments = 0, periods = 0, outdoorSegments = 0;
        uint16_t lastPeriod = 0;
        float w = 0, wf = 0, wr = 0, wrr = 0;           // hours; x flow, x rate, x rate^2
        float ow = 0, wo = 0, woo = 0, wor = 0, wro = 0; // segments with the outdoor known
    };
    struct Segment {
        Kind kind = Kind::none;
        bool active = false;
        int8_t source = -1;
        uint16_t period = 0;
        uint8_t refMin = 0, refMax = 0;
        int16_t first = 0, last = 0;
        uint64_t startMs = 0, lastMs = 0;
        uint32_t n = 0, outdoorN = 0, powerN = 0;
        double st = 0, stt = 0, sy = 0, sty = 0, flow = 0, outdoor = 0, power = 0; // t in h, y in degC
    };
    // Hour-weighted sums. Cooling: -rate x dT, dT^2. Heating: P x rate, P x dT, rate^2, rate x dT, dT^2.
    struct Heat {
        uint16_t coolSegments = 0, powerSegments = 0;
        double cw = 0, crd = 0, cdd = 0, pw = 0, spr = 0, spd = 0, srr = 0, srd = 0, sdd = 0;
    };
    struct Room {
        std::string id;
        RoomPlan::Emitter emitter = RoomPlan::Emitter::radiator;
        Acceptance acceptance;
        Segment segment;
        std::array<Bin, binCount> bins{};
        Heat heat;
        uint16_t segments = 0, periods = 0, lastPeriod = 0, rejected = 0;
        std::optional<int16_t> shortfall;
        const char* last = "collecting";
    };
    struct Point { float flowC = 0, rate = 0, weight = 0; };
    using Curve = std::array<Point, binCount>;

    bool ready(const Bin& b) const { return b.segments >= p_.binSegments && b.periods >= p_.binPeriods; }
    bool ready(const Room& r) const { return readiness(r)[0] == 'r'; }
    const char* readiness(const Room& r) const {
        const auto bins = std::count_if(r.bins.begin(), r.bins.end(), [&](const Bin& b) { return ready(b); });
        if (bins >= p_.roomBins && r.segments >= p_.roomSegments && r.periods >= p_.roomPeriods) return "ready";
        return r.segments ? "learning" : "collecting";
    }
    void step(Room& r, uint64_t now, bool gap, Kind kind, uint8_t ref, const Boiler& b, std::optional<float> heatKw, const RoomInput& in) {
        auto& s = r.segment;
        r.shortfall = in.temperatureCentiC && in.setpointCentiC ? std::optional<int16_t>(*in.setpointCentiC - *in.temperatureCentiC) : std::nullopt;
        if (!in.temperatureCentiC) kind = Kind::none;
        if (s.active) {
            const bool jump = kind != Kind::none && std::abs(*in.temperatureCentiC - s.last) > p_.maxStepCentiC;
            const bool moved = kind == Kind::heat && std::max(s.refMax, ref) - std::min(s.refMin, ref) > p_.flowBandC;
            const uint32_t longest = s.kind == Kind::heat ? p_.maxSegmentMs : p_.maxCoolMs;
            if (kind != s.kind || gap || jump || moved || in.source != s.source || now - s.startMs >= longest) finish(r);
        }
        if (kind == Kind::none) return;
        if (!s.active) {
            s = {}; s.active = true; s.kind = kind; s.source = in.source; s.period = period_;
            s.startMs = now; s.first = *in.temperatureCentiC; s.refMin = s.refMax = ref;
        }
        const double t = double(now - s.startMs) / 3600000.0, y = (*in.temperatureCentiC - s.first) / 100.0;
        ++s.n; s.st += t; s.stt += t * t; s.sy += y; s.sty += t * y; s.flow += b.flowCentiC.value_or(0) / 100.0;
        if (b.outdoorCentiC) { ++s.outdoorN; s.outdoor += *b.outdoorCentiC / 100.0; }
        if (heatKw) { ++s.powerN; s.power += *heatKw; }
        s.refMin = std::min(s.refMin, ref); s.refMax = std::max(s.refMax, ref);
        s.last = *in.temperatureCentiC; s.lastMs = now;
    }
    void finish(Room& r) {
        auto& s = r.segment;
        s.active = false;
        const double den = s.n * s.stt - s.st * s.st;
        const uint32_t shortest = s.kind == Kind::heat ? p_.minSegmentMs : p_.minCoolMs;
        if (s.lastMs - s.startMs < shortest || s.n < 3 || den <= 0) { r.last = "segment_too_short"; return; }
        const double rate = (s.n * s.sty - s.st * s.sy) / den, hours = double(s.lastMs - s.startMs) / 3600000.0;
        if (std::fabs(rate) * 100 > p_.maxRateCentiCPerHour) { r.rejected = sat(r.rejected); r.last = "rate_out_of_range"; return; }
        // Mean room - outdoor, when the outdoor was known throughout.
        const std::optional<double> dT = s.outdoorN == s.n ? std::optional<double>(s.first / 100.0 + s.sy / s.n - s.outdoor / s.n) : std::nullopt;
        auto& h = r.heat;
        if (s.kind == Kind::cool) {
            if (!dT || *dT < 3 || rate > 0.05) { r.rejected = sat(r.rejected); r.last = !dT ? "cooling_needs_outdoor" : "cooling_unexplained"; return; }
            if (h.cw > 96) { h.cw *= 0.5; h.crd *= 0.5; h.cdd *= 0.5; }
            h.cw += hours; h.crd -= hours * rate * *dT; h.cdd += hours * *dT * *dT;
            h.coolSegments = sat(h.coolSegments); r.last = "cooling_learned"; return;
        }
        if (dT && s.powerN == s.n) {
            const double P = s.power / s.n;
            if (h.pw > 96) for (double* v : {&h.pw, &h.spr, &h.spd, &h.srr, &h.srd, &h.sdd}) *v *= 0.5;
            h.pw += hours; h.spr += hours * P * rate; h.spd += hours * P * *dT;
            h.srr += hours * rate * rate; h.srd += hours * rate * *dT; h.sdd += hours * *dT * *dT;
            h.powerSegments = sat(h.powerSegments);
        }
        const float w = static_cast<float>(hours), f = static_cast<float>(s.flow / s.n), q = static_cast<float>(rate);
        auto& b = r.bins[std::clamp<int>(static_cast<int>((f - binLowC) / binWidthC), 0, binCount - 1)];
        if (b.w + w > p_.binMemoryHours) {
            const float k = std::max(0.0f, p_.binMemoryHours - w) / b.w;
            for (float* v : {&b.w, &b.wf, &b.wr, &b.wrr, &b.ow, &b.wo, &b.woo, &b.wor, &b.wro}) *v *= k;
        }
        b.w += w; b.wf += w * f; b.wr += w * q; b.wrr += w * q * q;
        if (dT) {
            const float o = static_cast<float>(s.outdoor / s.n);
            b.ow += w; b.wo += w * o; b.woo += w * o * o; b.wor += w * o * q; b.wro += w * q;
            b.outdoorSegments = sat(b.outdoorSegments);
        }
        b.segments = sat(b.segments);
        if (b.lastPeriod != s.period) { b.lastPeriod = s.period; b.periods = sat(b.periods); }
        r.segments = sat(r.segments);
        if (r.lastPeriod != s.period) { r.lastPeriod = s.period; r.periods = sat(r.periods); }
        r.last = "segment_learned";
    }
    // One outdoor slope for the room (degC/h per K warmer outside), pooled
    // within flow bins; only with enough segments and outdoor spread.
    std::optional<float> outdoorSlope(const Room& r) const {
        double sxx = 0, sxy = 0, ow = 0; unsigned n = 0;
        for (const auto& b : r.bins) {
            if (b.ow <= 0) continue;
            sxx += b.woo - double(b.wo) * b.wo / b.ow; sxy += b.wor - double(b.wo) * b.wro / b.ow;
            ow += b.ow; n += b.outdoorSegments;
        }
        if (n < p_.roomSegments || ow <= 0 || sxx / ow < 4.0) return std::nullopt; // spread under 2 K
        return static_cast<float>(std::clamp(sxy / sxx, 0.0, 0.1));
    }
    // Ready bins in flow order, outdoor-shifted, made non-decreasing (pool adjacent violators).
    size_t curve(const Room& r, std::optional<int16_t> outdoor, Curve& c) const {
        const auto slope = outdoor ? outdoorSlope(r) : std::nullopt;
        size_t n = 0;
        for (const auto& b : r.bins) {
            if (!ready(b)) continue;
            float rate = b.wr / b.w;
            if (slope && b.ow > 0) rate += *slope * (*outdoor / 100.0f - b.wo / b.ow);
            c[n++] = {b.wf / b.w, rate, b.w};
        }
        Curve block; std::array<size_t, binCount> len{}; size_t m = 0;
        for (size_t i = 0; i < n; ++i) {
            block[m] = c[i]; len[m] = 1;
            while (m && block[m - 1].rate > block[m].rate) {
                const float w = block[m - 1].weight + block[m].weight;
                block[m - 1].rate = (block[m - 1].rate * block[m - 1].weight + block[m].rate * block[m].weight) / w;
                block[m - 1].weight = w; len[m - 1] += len[m]; --m;
            }
            ++m;
        }
        for (size_t j = 0, i = 0; j < m; ++j) for (size_t l = 0; l < len[j]; ++l) c[i++].rate = block[j].rate;
        return n;
    }
    // Below the learned range: unknown. Above it: the top rate (conservative).
    static std::optional<float> rateAt(const Curve& c, size_t n, uint8_t flowC) {
        if (!n || flowC < c[0].flowC - 0.5f) return std::nullopt;
        size_t k = 0;
        while (k + 1 < n && c[k + 1].flowC <= flowC) ++k;
        float rate = c[k].rate;
        if (k + 1 < n && flowC > c[k].flowC)
            rate += (flowC - c[k].flowC) / (c[k + 1].flowC - c[k].flowC) * (c[k + 1].rate - c[k].rate);
        return rate;
    }
    static std::optional<uint32_t> warmup(const Curve& c, size_t n, uint8_t flowC, int16_t shortfallCentiC) {
        const auto rate = rateAt(c, n, flowC);
        if (!rate) return std::nullopt;
        if (shortfallCentiC <= 0) return 0;
        if (*rate < 0.02f) return std::nullopt; // does not warm up
        return static_cast<uint32_t>(shortfallCentiC / 100.0f / *rate * 3600.0f + 0.5f);
    }
    template <typename T> static T sat(T v) { return v == T(~T(0)) ? v : T(v + 1); }
    static bool adviceJson(cJSON* parent, const char* key, int16_t shortfall, const Advice& a) {
        cJSON* o = cJSON_CreateObject();
        if (!o || !(key ? cJSON_AddItemToObject(parent, key, o) : cJSON_AddItemToArray(parent, o))) { cJSON_Delete(o); return false; }
        const auto hours = [](std::optional<uint32_t> s) { return s ? std::optional<float>(*s / 3600.0f) : std::nullopt; };
        number(o, "shortfall_c", shortfall / 100.0f, 100);
        number(o, "required_c_per_h", a.requiredRate, 100);
        number(o, "flow_c", a.flowC ? std::optional<float>(*a.flowC) : std::nullopt, 1);
        number(o, "warmup_h", hours(a.warmupS), 10);
        cJSON_AddStringToObject(o, "reason", a.reason);
        cJSON_AddNumberToObject(o, "rule_flow_c", a.ruleFlowC);
        number(o, "rule_warmup_h", hours(a.ruleWarmupS), 10);
        return cJSON_AddStringToObject(o, "rule", a.rule) != nullptr;
    }

    Params p_;
    std::vector<Room> rooms_;
    uint8_t minFlowC_ = 30, maxFlowC_ = 60;
    bool haveLast_ = false, heating_ = false, haveGas_ = false, gasValid_ = false, nominalFromHa_ = false, kwhFromHa_ = false;
    uint16_t period_ = 0, gasIntervals_ = 0;
    uint64_t lastMs_ = 0, holdUntil_ = 0, offSince_ = 0, gasAtMs_ = 0;
    double gasM3_ = 0, predictedKwh_ = 0, calMeasured_ = 0, calPredicted_ = 0;
    std::optional<int16_t> outdoor_;
    std::optional<float> price_;
    const char* status_ = "boiler_unknown";
};
}
