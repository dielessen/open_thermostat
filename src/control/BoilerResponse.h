#pragma once
#include "control/FlowDemand.h"
#include "control/FlowLearner.h"
#include "control/LearnedState.h"
#include "control/RoomSchedule.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
// Listening to the boiler (rc.5, P1; owner, 4 Nov 2026: "top of the build self learning",
// "het moet voor alle ketels ook kunnen werken"). Standard EMS values every boiler reports
// (flow, return, burner, hot water, burner power) tell how it answers the E32's request,
// without reading or changing any boiler setting:
//  - a held target: while the E32 drives the boiler and asks heat that a room wants (no hot
//    water in the last minute, past the first 10 min of the request, no warm-up: the lead room
//    less than 1 degC short), the burner stops by itself after a heating burn of at least 1 min
//    with the water between 2 degC below and 8 degC above the request, or it burns at its least
//    power for 3 min while the water rises 2 degC above the request: the circuit takes less heat
//    than the boiler's least. Two in one request: over-asked; that
//    request - 2 degC is a candidate ceiling for the outdoor band of the request (6 bands of
//    5 K from -10 degC; unknown outdoor: 5..10). A band's ceiling is an EMA (0.3) of its
//    candidates, raised 1 degC per 6 hours of heat asked at or above it without a held event
//    (the season or the house changed: it is found out again), always within [the lowest flow
//    the E32 asks (BoilerMinimumFlow), the plan's maximum]. FlowPolicy asks no more than it
//    (Smart warm-up on, the E32 driving the boiler). Learned from one over-asked request (the
//    boiler said so itself);
//  - its own rest: after a held target, the time until the burner starts again (60..1800 s;
//    the median of the last 8, from 3). RestFloor keeps the E32's burner rest at least as long;
//  - absorbed heat: with the return reported, a steady burn (5 min on, no hot water, burner
//    power known, flow - return >= 2 K, the water holding its temperature) gives the pump's
//    mass flow m = power x efficiency / (4.186 x (flow - return)), one EMA (0.2) step per
//    1..10 min of steady burn. From then on
//    the emitters take m x 4.186 x (flow - return) kW whenever the burner heats, also without
//    the burner power, and per K of water above the rooms' mean (steady, from 5 K; EMA 0.2):
//    the emitters' output per K for the house model. Without the return both stay unknown
//    and nothing else changes: the state is "learned" from the first ceiling or the rest rhythm
//    either way ("no_return" only while nothing is learned yet; "return" in the JSON tells).
// Hot water, a silence over 60 s, an unknown burner, the end of the request or another
// controller close an open rest without counting it; another boiler (EMS product id) starts
// over, as BoilerMinimumFlow does. Pure and single-threaded: sample() every 10 s. What was
// learned is one LearnedState frame (kind 'B', version 1, at most 48 B) in the global record
// (LearnedStore); firmware before rc.5 skips it and a damaged frame is ignored whole.
class BoilerResponse {
public:
    static constexpr size_t bands = 6, restRing = 8, unknownBand = 3; // unknown outdoor: 5..10 degC
    static constexpr char frameKind = 'B';
    static constexpr uint8_t frameVersion = 1;
    static constexpr size_t payloadBytes = 33, frameBytes = 4 + payloadBytes + 4;
    static constexpr size_t storedMaxBytes = 48, jsonMaxBytes = 140;  // the frame; "boiler":{..} printed
    static constexpr float water = 4.186f;                            // kJ per kg and K
    struct Params {
        int16_t heldMarginCentiC = 200;            // a stop with the water at least request - 2 degC
        // ... and at most request + 8 degC, after a heating burn of at least 1 min with no hot water in
        // the minute before the stop. The owner's recording (30 Oct - 2 Nov 2026): the boiler stopped
        // 3..6 degC above the flow the thermostat asked when it held it (7 times), while a keep-warm
        // round often drops its hot-water bit one report before the burner stops, 19..42 degC above
        // (the round's tail, not a request held; AutoTuner's dhwLookMs, the same boiler habit).
        int16_t heldAboveCentiC = 800;
        uint32_t minBurnMs = 60000, hotWaterLookMs = 60000;
        uint32_t settleMs = 600000;                // the first 10 min of a request fill the circuit
        int16_t warmupCentiC = 100;                // the lead room this far below its target: a warm-up
        uint8_t minModulationPct = 25;             // the burner's least power (or the lowest seen this boot)
        uint32_t minModulationMs = 180000;         // at it this long,
        int16_t risingCentiC = 200;                // with the water this far above the request and rising
        uint32_t minRestS = 60, maxRestS = 1800;   // a rest observation
        uint8_t restsReported = 3;                 // rest_s from this many observations (a median)
        uint32_t maxGapMs = 60000;                 // a longer silence closes what is open
        uint8_t overAskedEvents = 2;               // held targets in one request: over-asked
        uint8_t candidateBelowC = 2;               // its candidate: the request - 2 degC
        float ceilingAlpha = 0.3f;
        uint32_t raiseS = 6 * 3600;                // heat asked at or above the ceiling without a held target: +1 degC
        uint32_t steadyMs = 300000;                // a steady burn: on this long
        int16_t minDeltaCentiC = 200;              // flow - return at least
        int16_t minOverRoomCentiC = 500;           // flow - the rooms' mean at least (kW per K)
        float pumpAlpha = 0.2f, emitterAlpha = 0.2f;
        uint16_t windowMin = 6, windowMax = 60;    // samples of one steady window (1..10 min)
        // A window counts only while the water holds its temperature: at most 0.1 degC + 0.05 degC per
        // minute between its first and last flow. Heat that warms the circuit's own water (a burn at the
        // least power that runs up to its stop) would otherwise be counted as the pump's flow.
        int16_t driftCentiC = 10, driftPerMinuteCentiC = 5;
        uint32_t returnStaleMs = 900000;           // no return reported this long: "no_return"
    };
    struct Sample {
        uint64_t now = 0;
        std::optional<int64_t> utc;                // trusted clock only
        uint8_t requestC = 0;                      // the request handed to the boiler, 0 = no heat
        bool ownRequest = false;                   // the E32 drives the boiler (active mode, confirmed)
        bool demand = false;                       // at least one usable room asks heat (RoomDemand)
        std::optional<int16_t> flowCentiC, returnCentiC, outdoorCentiC, roomMeanCentiC;
        std::optional<bool> burnerOn, hotWater;
        std::optional<uint8_t> modulationPct;
        float nominalKw = 22, kwhPerM3 = 9.77f;    // FlowLearner::Params (HA may report the boiler's)
        // Beside the rc.5 contract (P1 report): the lead room's shortfall (the largest error of a
        // usable room, > 0: too cold), the ceiling's bounds (the lowest flow the E32 asks,
        // FlowLearner::effectiveMinimumC, and the plan's maximum; 0: unknown) and the boiler's EMS
        // product id (another boiler: everything starts over).
        std::optional<int16_t> shortfallCentiC;
        uint8_t minimumC = 0, maximumC = 0;
        std::optional<uint8_t> productId;
    };

    BoilerResponse() = default;
    explicit BoilerResponse(Params p) : p_(p) {}

    void sample(const Sample& s) {
        if (s.productId && *s.productId) {
            if (productId_ && productId_ != *s.productId) forget();
            productId_ = *s.productId;
        }
        if (s.utc) {
            const int32_t day = RoomSchedule::localDay(*s.utc);
            if (day_ != unknownDay && day != day_) held_ = 0; // a new local day (a restored older one too)
            day_ = day;
        }
        const bool gap = !have_ || s.now <= lastMs_ || s.now - lastMs_ > p_.maxGapMs;
        const uint32_t dt = gap ? 0 : uint32_t(s.now - lastMs_);
        have_ = true; lastMs_ = s.now; driving_ = s.ownRequest; outdoor_ = s.outdoorCentiC;
        if (s.minimumC) lowC_ = s.minimumC;
        if (s.maximumC) highC_ = s.maximumC;
        if (s.returnCentiC) returnAt_ = s.now;
        const bool known = s.burnerOn && s.hotWater;
        const bool hot = s.hotWater.value_or(false);
        const bool heating = known && *s.burnerOn && !hot; // the burner heats the circuit
        const bool asked = s.ownRequest && s.requestC > 0;
        if (heating && s.modulationPct && *s.modulationPct) lowestPct_ = std::min(lowestPct_, *s.modulationPct);
        if (hot) hotAt_ = s.now;
        // An open rest ends without counting: hot water, a silence, an unknown burner, the request ended.
        if (gap || !known || hot || !asked) rest_.reset();
        // One request: from the E32's heat request to its end (or a silence).
        if (gap || !asked) run_ = {};
        if (asked && !run_.active) { run_.active = true; run_.since = s.now; }
        if (run_.active && s.outdoorCentiC) { run_.outdoorSum += *s.outdoorCentiC; ++run_.outdoorN; }
        const bool countable = asked && s.demand && known && !hot && !gap && s.now - run_.since >= p_.settleMs
            && !(s.shortfallCentiC && *s.shortfallCentiC >= p_.warmupCentiC) && !(hotAt_ && s.now - *hotAt_ <= p_.hotWaterLookMs);
        const int request = int(s.requestC) * 100;
        if (!gap && wasHeating_ && !heating && known && !hot) {
            // The burner stopped by itself with the water at its target (the highest of this and the
            // last sample) after a heating burn: a held target, and the boiler's own rest starts.
            const int peak = std::max<int>(s.flowCentiC.value_or(INT16_MIN), lastFlow_.value_or(INT16_MIN));
            const bool atTarget = peak >= request - p_.heldMarginCentiC && peak <= request + p_.heldAboveCentiC;
            if (countable && (burn_.held || (atTarget && s.now - burn_.since >= p_.minBurnMs))) {
                if (!burn_.held) held(s);
                rest_ = s.now;
            }
        }
        if (heating && (gap || !wasHeating_)) {
            if (rest_) { // back on after a held target: one rest observation
                const uint64_t r = (s.now - *rest_) / 1000;
                if (r >= p_.minRestS && r <= p_.maxRestS) pushRest(uint32_t(r));
            }
            rest_.reset();
            burn_ = {}; burn_.since = s.now;
        }
        // Burning at its least power while the water rises above the request: held as well.
        if (heating && countable && !burn_.held && s.modulationPct && s.flowCentiC && *s.modulationPct <= std::min(p_.minModulationPct, lowestPct_)
            && *s.flowCentiC >= request + p_.risingCentiC && *s.flowCentiC <= request + p_.heldAboveCentiC) {
            if (!burn_.leastSince) { burn_.leastSince = s.now; burn_.leastFlow = *s.flowCentiC; }
            else if (s.now - *burn_.leastSince >= p_.minModulationMs && *s.flowCentiC > burn_.leastFlow) held(s);
        } else burn_.leastSince.reset();
        // Heat asked at or above the band's ceiling without a held target: found out again, 1 degC per 6 h.
        const size_t b = band(s.outdoorCentiC);
        if (asked && !hot && dt && ceiling_[b] > 0 && s.requestC >= *bandCeiling(b) && (raiseMs_[b] += dt) >= uint64_t(p_.raiseS) * 1000) {
            raiseMs_[b] = 0;
            ceiling_[b] = std::min(ceiling_[b] + 1.0f, float(high()));
        }
        absorption(s, heating, gap);
        wasHeating_ = heating; lastFlow_ = s.flowCentiC;
    }

    // The learned ceiling for the outdoor band of `outdoorCentiC`, within the bounds of the last
    // sample (nullopt: unknown outdoor or not learned).
    std::optional<uint8_t> ceilingC(std::optional<int16_t> outdoorCentiC) const {
        return outdoorCentiC ? bandCeiling(band(outdoorCentiC)) : std::nullopt;
    }
    std::optional<uint8_t> bandCeiling(size_t b) const {
        if (b >= bands || !(ceiling_[b] > 0)) return std::nullopt;
        return uint8_t(std::clamp<int>(int(learnmath::round(double(ceiling_[b]))), low(), std::max(low(), high())));
    }
    // The boiler's own rest after a held target (the median of the last 8, from 3 observations).
    std::optional<uint32_t> restS() const {
        if (restCount_ < p_.restsReported) return std::nullopt;
        std::array<uint16_t, restRing> r = rests_;
        std::nth_element(r.begin(), r.begin() + restCount_ / 2, r.begin() + restCount_);
        return r[restCount_ / 2];
    }
    std::optional<float> absorbedKw() const { return absorbed_; } // now, from flow - return and the learned pump flow
    std::optional<float> kwPerFlowK() const { return emitter_; }  // emitter output per K of flow above the rooms' mean
    std::optional<float> pumpKgPerS() const { return pump_; }     // the learned mass flow of the pump
    uint16_t heldToday() const { return held_; }                   // held targets today (local day via utc)
    uint8_t overAsked() const { return overAsked_; }               // over-asked requests (saturating)
    // What the boiler said about itself: a ceiling (any band) or its rest rhythm, also without the return.
    bool learned() const { return restS() || std::any_of(ceiling_.begin(), ceiling_.end(), [](float c) { return c > 0; }); }
    // The return temperature reported in the last 15 min: absorbed heat can be known (false: never "no_return" once learned).
    bool hasReturn() const { return returnAt_ && lastMs_ - *returnAt_ <= p_.returnStaleMs; }
    // "not_driving" while another controller drives the boiler, "learned" from the first ceiling or the
    // rest rhythm, until then "no_return" without the return (the absorption cannot be learned) or "collecting".
    const char* state() const {
        if (have_ && !driving_) return "not_driving";
        if (learned()) return "learned";
        if (have_ && !hasReturn()) return "no_return";
        return "collecting";
    }
    // Outdoor band: <-5, -5..0, 0..5, 5..10, 10..15, >=15 degC; unknown: 5..10.
    static size_t band(std::optional<int16_t> outdoorCentiC) {
        if (!outdoorCentiC) return unknownBand;
        const int v = *outdoorCentiC + 1000;
        return size_t(std::clamp(v >= 0 ? v / 500 : -((-v + 499) / 500), 0, int(bands) - 1));
    }
    const Params& params() const { return p_; }

    // "boiler":{"held","rest_s","ceiling_c","absorbed_kw","kw_per_k","state","return"} (at most
    // jsonMaxBytes printed); ceiling_c for the last sample's outdoor; "return": hasReturn(), so a page
    // can say that absorbed heat is unavailable on this boiler. False: no memory.
    bool addJson(cJSON* parent) const {
        cJSON* o = cJSON_AddObjectToObject(parent, "boiler");
        if (!o || !cJSON_AddNumberToObject(o, "held", held_)) return false;
        const auto rest = restS();
        const auto ceiling = ceilingC(outdoor_);
        FlowLearner::number(o, "rest_s", rest ? std::optional<float>(float(*rest)) : std::nullopt, 1);
        FlowLearner::number(o, "ceiling_c", ceiling ? std::optional<float>(*ceiling) : std::nullopt, 1);
        FlowLearner::number(o, "absorbed_kw", absorbed_, 10);
        FlowLearner::number(o, "kw_per_k", emitter_, 1000);
        return cJSON_AddStringToObject(o, "state", state()) && cJSON_AddBoolToObject(o, "return", hasReturn());
    }

    // The LearnedState frame (kind 'B', version 1, frameBytes; empty: nothing learned). Payload,
    // little-endian: product id (u8), over-asked requests (u8), per band the ceiling (u8: 0 none,
    // else 1 + 4 x (degC - 20), 20..80 degC) and the raise time (u8, 2 min), the rest ring (u8
    // count | next << 4, 8 x u8 of 10 s), the pump flow (u16 g/s, 0 none), the emitters' output
    // per K (u16 W/K, 0 none), the local day (i32) of the held count (u16).
    std::string stored() const {
        const bool any = overAsked_ || restCount_ || pump_ || emitter_ || held_
            || std::any_of(ceiling_.begin(), ceiling_.end(), [](float c) { return c > 0; });
        if (!any) return {};
        std::string f;
        f.reserve(frameBytes);
        f += char(frameVersion); f += frameKind; f += char(payloadBytes & 0xFF); f += char(payloadBytes >> 8);
        f += char(productId_); f += char(overAsked_);
        for (const float c : ceiling_) f += char(c > 0 ? 1 + int(learnmath::round((double(std::clamp(c, 20.0f, 80.0f)) - 20) * 4)) : 0);
        for (const uint32_t r : raiseMs_) f += char(std::min<uint32_t>(r / 120000, 180));
        f += char(restCount_ | restNext_ << 4);
        for (const uint16_t r : rests_) f += char((r + 5) / 10);
        put(f, uint16_t(pump_ ? learnmath::round(double(*pump_) * 1000) : 0));
        put(f, uint16_t(emitter_ ? learnmath::round(double(*emitter_) * 1000) : 0));
        put(f, uint32_t(day_)); put(f, held_);
        put(f, LearnedState::crc(f.data(), f.size()));
        return f;
    }
    // A frame of stored(): applied whole, or (another version or kind, a bad length, CRC or value)
    // not at all.
    bool restore(std::string_view f) {
        if (f.size() != frameBytes || uint8_t(f[0]) != frameVersion || f[1] != frameKind
            || (uint8_t(f[2]) | size_t(uint8_t(f[3])) << 8) != payloadBytes || get<uint32_t>(f, 4 + payloadBytes) != LearnedState::crc(f.data(), 4 + payloadBytes))
            return false;
        const auto u = [&](size_t i) { return uint8_t(f[4 + i]); };
        std::array<float, bands> ceiling{};
        std::array<uint32_t, bands> raise{};
        for (size_t b = 0; b < bands; ++b) {
            if (u(2 + b) > 241 || u(8 + b) > 180) return false;
            ceiling[b] = u(2 + b) ? 20 + (u(2 + b) - 1) / 4.0f : 0;
            raise[b] = u(8 + b) * 120000u;
        }
        const uint8_t count = u(14) & 15, next = u(14) >> 4;
        if (count > restRing || next >= restRing || (count < restRing && next != count)) return false;
        std::array<uint16_t, restRing> rests{};
        for (size_t i = 0; i < count; ++i) {
            if (u(15 + i) < (p_.minRestS + 9) / 10 || u(15 + i) > p_.maxRestS / 10) return false;
            rests[i] = uint16_t(u(15 + i) * 10);
        }
        const uint16_t pump = get<uint16_t>(f, 4 + 23), emitter = get<uint16_t>(f, 4 + 25);
        if ((pump && (pump < 10 || pump > 5000)) || emitter > 20000) return false;
        productId_ = u(0); overAsked_ = u(1); ceiling_ = ceiling; raiseMs_ = raise;
        restCount_ = count; restNext_ = next; rests_ = rests;
        pump_ = pump ? std::optional<float>(pump / 1000.0f) : std::nullopt;
        emitter_ = emitter ? std::optional<float>(emitter / 1000.0f) : std::nullopt;
        day_ = int32_t(get<uint32_t>(f, 4 + 27)); held_ = get<uint16_t>(f, 4 + 31);
        return true;
    }
    // Another boiler: nothing learned about the old one applies.
    void forget() {
        ceiling_ = {}; raiseMs_ = {}; rests_ = {}; restCount_ = restNext_ = 0; overAsked_ = 0; held_ = 0;
        pump_.reset(); emitter_.reset(); absorbed_.reset(); pumpWindow_ = {}; emitterWindow_ = {};
        run_ = {}; burn_ = {}; rest_.reset(); lowestPct_ = UINT8_MAX;
    }

private:
    static constexpr int32_t unknownDay = INT32_MIN;
    struct Run { bool active = false; uint64_t since = 0; int32_t outdoorSum = 0; uint32_t outdoorN = 0; uint8_t held = 0, lowest = 0; };
    struct Burn { uint64_t since = 0; bool held = false; std::optional<uint64_t> leastSince; int16_t leastFlow = 0; };
    struct Window {
        double sum = 0;
        uint16_t n = 0;
        int16_t firstFlow = 0, lastFlow = 0;
        uint64_t firstAt = 0, lastAt = 0;
        void add(double v, int16_t flow, uint64_t now) {
            if (!n) { firstFlow = flow; firstAt = now; }
            sum += v; ++n; lastFlow = flow; lastAt = now;
        }
    };
    template <class T> static T sat(T v) { return v == T(~T(0)) ? v : T(v + 1); }
    template <class T> static void put(std::string& s, T v) { for (size_t i = 0; i < sizeof v; ++i) s += char(uint64_t(v) >> (8 * i) & 0xFF); }
    template <class T> static T get(std::string_view s, size_t at) {
        uint64_t v = 0;
        for (size_t i = 0; i < sizeof(T); ++i) v |= uint64_t(uint8_t(s[at + i])) << (8 * i);
        return T(v);
    }
    uint8_t low() const { return lowC_ ? lowC_ : 20; }
    uint8_t high() const { return highC_ ? highC_ : FlowDemand::ceilingC; }
    void held(const Sample& s) {
        burn_.held = true;
        held_ = sat(held_);
        raiseMs_[band(s.outdoorCentiC)] = 0;
        run_.lowest = run_.held ? std::min(run_.lowest, s.requestC) : s.requestC;
        run_.held = sat(run_.held);
        if (run_.held != p_.overAskedEvents) return;
        // Over-asked (once per request): request - 2 degC for the band of the request's mean outdoor.
        const auto outdoor = run_.outdoorN ? std::optional<int16_t>(int16_t(run_.outdoorSum / int32_t(run_.outdoorN))) : std::nullopt;
        float& c = ceiling_[band(outdoor)];
        const float candidate = float(int(run_.lowest) - int(p_.candidateBelowC));
        c = std::clamp(c > 0 ? c + p_.ceilingAlpha * (candidate - c) : candidate, float(low()), float(std::max(low(), high())));
        overAsked_ = sat(overAsked_);
    }
    void pushRest(uint32_t s) {
        rests_[restNext_] = uint16_t(s);
        restNext_ = uint8_t((restNext_ + 1) % restRing);
        restCount_ = uint8_t(std::min<size_t>(restCount_ + 1, restRing));
    }
    // A steady window's mean joins the EMA (the first one sets it); a short window, one whose water
    // drifted, or a mean outside [lo, hi] is dropped.
    void fold(Window& w, std::optional<float>& ema, float alpha, float lo, float hi) const {
        const uint64_t minutes = (w.lastAt - w.firstAt) / 60000;
        const bool held = std::abs(w.lastFlow - w.firstFlow) <= p_.driftCentiC + int64_t(p_.driftPerMinuteCentiC) * int64_t(minutes);
        if (w.n >= p_.windowMin && held) {
            const float mean = float(w.sum / w.n);
            if (mean >= lo && mean <= hi) ema = ema ? *ema + alpha * (mean - *ema) : mean;
        }
        w = {};
    }
    void absorption(const Sample& s, bool heating, bool gap) {
        absorbed_.reset();
        const bool steady = heating && !gap && s.now - burn_.since >= p_.steadyMs;
        if (heating && s.flowCentiC && s.returnCentiC) {
            const int dT = *s.flowCentiC - *s.returnCentiC;
            if (steady && s.modulationPct && dT >= p_.minDeltaCentiC) {
                const float kw = *s.modulationPct / 100.0f * s.nominalKw * FlowLearner::efficiency(*s.returnCentiC / 100.0f);
                pumpWindow_.add(kw / (water * dT / 100.0f), *s.flowCentiC, s.now);
                if (pumpWindow_.n >= p_.windowMax) fold(pumpWindow_, pump_, p_.pumpAlpha, 0.01f, 5.0f);
            }
            if (pump_) absorbed_ = std::min(999.9f, *pump_ * water * std::max(0, dT) / 100.0f);
            const int over = s.roomMeanCentiC ? *s.flowCentiC - *s.roomMeanCentiC : 0;
            if (steady && absorbed_ && s.roomMeanCentiC && over >= p_.minOverRoomCentiC) {
                emitterWindow_.add(*absorbed_ / (over / 100.0f), *s.flowCentiC, s.now);
                if (emitterWindow_.n >= p_.windowMax) fold(emitterWindow_, emitter_, p_.emitterAlpha, 0.001f, 20.0f);
            }
        }
        if (!steady) {
            fold(pumpWindow_, pump_, p_.pumpAlpha, 0.01f, 5.0f);
            fold(emitterWindow_, emitter_, p_.emitterAlpha, 0.001f, 20.0f);
        }
    }

    Params p_;
    // Learned (the frame).
    uint8_t productId_ = 0, overAsked_ = 0, restCount_ = 0, restNext_ = 0;
    std::array<float, bands> ceiling_{};    // degC, 0: none
    std::array<uint32_t, bands> raiseMs_{}; // heat asked at or above the ceiling since its last held target
    std::array<uint16_t, restRing> rests_{};
    std::optional<float> pump_, emitter_;  // kg/s, kW per K
    int32_t day_ = unknownDay;
    uint16_t held_ = 0;
    // This boot.
    bool have_ = false, driving_ = false, wasHeating_ = false;
    uint64_t lastMs_ = 0;
    uint8_t lowC_ = 0, highC_ = 0, lowestPct_ = UINT8_MAX;
    std::optional<int16_t> outdoor_, lastFlow_;
    std::optional<uint64_t> returnAt_, rest_, hotAt_;
    std::optional<float> absorbed_;
    Run run_;
    Burn burn_;
    Window pumpWindow_, emitterWindow_;
};
}
