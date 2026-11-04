#pragma once
#include "control/FlowLearner.h"
#include "control/RoomPlan.h"
#include "control/Scoreboard.h"
#include "control/WeatherCurve.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <optional>
namespace heating::control {
// The house as one model (rc.5, P2; owner, 4 Nov 2026: "top of the build self learning"): how
// much heat it loses per K colder outside (UA, kW/K) and how much heat the radiators and floors
// give per K of water above the rooms (kW/K). Their ratio is the weather curve's slope: in a
// steady state the emitters give what the house loses, k (flow - room) = UA (room - outdoor), so
//   flow - room = UA / k x (room - outdoor), the slope of WeatherCurve::baseCentiC.
// FlowPolicy uses it between the learned curve and the design slope: CurveLearner needs six
// steady 3-hour windows, which a mild autumn or a boiler that cycles may take weeks to give, while
// the house model comes from what the learners already know:
//  - UA: the median of the rooms' UA (FlowLearner's heat model, b x C: the house as seen from each
//    room), from 2 rooms; else the gas per degree-day (the Insights' baseline in the Scoreboard,
//    from 3 local days): kWh/DD x the gas calibration x the condensing efficiency / 24 h, the
//    classic degree-day method (18 degC base);
//  - k: BoilerResponse's measured output per K (flow - return and the learned pump flow), when it
//    learned it; else from the rooms' models over their ready flow bins: a room warming at rate r
//    at flow F with the outdoor To took P = C (r + b (room - To)) (FlowLearner's own fit), so
//    k = sum w P x / sum w x^2 with x = F - room over the bins (the room taken at 20 degC: the bins
//    keep no room temperature), the median over the rooms;
//  - the slope: UA / k within [WeatherCurve::minSlope, maxSlope].
// "learned" once the slope is known, else "collecting". Universal: without the burner power
// (modulation) there is no heat model and no gas estimate, without an outdoor temperature no
// cooling, bins or degree-days: the model then stays "collecting" and the design slope stays.
// Nothing is stored: update() recomputes it from the learners (hourly and at the day change).
// Pure, single-threaded.
class HouseModel {
public:
    struct Params {
        uint8_t minRooms = 2;      // rooms with a learned UA before their median counts
        uint8_t minGasDays = 3;    // else local days in the gas per degree-day baseline
        float roomC = 20;          // the room temperature assumed during a heating segment (degC)
        float minLiftK = 5;        // a ready bin counts with its flow at least this far above the room
        float gasReturnC = 40;     // the return temperature of the gas route's efficiency (FlowLearner::efficiency)
    };
    struct Inputs {
        const FlowLearner* learner = nullptr;  // heatModel(i) per plan room, the ready bins, the gas calibration
        const Scoreboard* board = nullptr;     // the Insights' gas per degree-day baseline (kWh/DD)
        std::optional<float> kwPerFlowK;       // BoilerResponse::kwPerFlowK(), when learned
        const RoomPlan* plan = nullptr;        // the rooms (without: the learner's)
    };
    HouseModel() = default;
    explicit HouseModel(Params p) : p_(p) {}

    // Once an hour and at the day change.
    void update(const Inputs& in) {
        ua_.reset(); kw_.reset(); slope_.reset(); uaSource_ = kwSource_ = nullptr;
        const FlowLearner* l = in.learner;
        const size_t rooms = !l ? 0 : std::min({in.plan ? in.plan->rooms.size() : l->rooms(), l->rooms(), RoomPlan::maxRooms});
        std::array<float, RoomPlan::maxRooms> ua{}, kw{};
        size_t nUa = 0, nKw = 0;
        for (size_t i = 0; i < rooms; ++i) {
            const auto m = l->heatModel(i);
            if (m.uaKwPerK && *m.uaKwPerK > 0 && std::isfinite(*m.uaKwPerK)) ua[nUa++] = *m.uaKwPerK;
            if (const auto k = emitterKwPerK(*l, i, m)) kw[nKw++] = *k;
        }
        if (nUa >= p_.minRooms) { ua_ = median(ua, nUa); uaSource_ = "rooms"; }
        else if (const auto g = in.board && l ? in.board->insights().gasPerDegreeDay(p_.minGasDays) : std::nullopt; g && *g > 0) {
            ua_ = *g * l->calibration() * FlowLearner::efficiency(p_.gasReturnC) / 24.0f; uaSource_ = "gas";
        }
        if (in.kwPerFlowK && *in.kwPerFlowK > 0 && std::isfinite(*in.kwPerFlowK)) { kw_ = in.kwPerFlowK; kwSource_ = "boiler"; }
        else if (nKw) { kw_ = median(kw, nKw); kwSource_ = "rooms"; }
        if (ua_ && kw_ && std::isfinite(*ua_ / *kw_)) slope_ = std::clamp(*ua_ / *kw_, WeatherCurve::minSlope, WeatherCurve::maxSlope);
    }
    std::optional<float> uaKwPerK() const { return ua_; }      // house heat loss per K (kW/K)
    std::optional<float> kwPerFlowK() const { return kw_; }    // emitter output per K of flow above the rooms (kW/K)
    std::optional<float> slope() const { return slope_; }      // the weather curve's slope they imply
    const char* state() const { return slope_ ? "learned" : "collecting"; }
    const char* uaSource() const { return uaSource_; }         // "rooms", "gas" or nullptr
    const char* kwSource() const { return kwSource_; }         // "boiler", "rooms" or nullptr
    const Params& params() const { return p_; }
    // "house":{"ua_kw_per_k","kw_per_flow_k","slope","state"} (null while unknown), at most 110 B.
    bool addJson(cJSON* parent) const {
        cJSON* o = cJSON_AddObjectToObject(parent, "house");
        if (!o) return false;
        FlowLearner::number(o, "ua_kw_per_k", ua_, 1000);
        FlowLearner::number(o, "kw_per_flow_k", kw_, 1000);
        FlowLearner::number(o, "slope", slope_, 100);
        return cJSON_AddStringToObject(o, "state", state()) != nullptr;
    }

private:
    // One room's estimate of the emitters' output per K of flow (kW/K), over its ready bins with the outdoor known.
    std::optional<float> emitterKwPerK(const FlowLearner& l, size_t room, const FlowLearner::HeatModel& m) const {
        if (!m.lossPerHour || !m.capacityKwhPerK || room >= l.rooms_.size()) return std::nullopt;
        const double b = *m.lossPerHour, c = *m.capacityKwhPerK;
        double sxp = 0, sxx = 0;
        for (const auto& bin : l.rooms_[room].bins) {
            if (!l.ready(bin) || !(bin.ow > 0) || !(bin.w > 0)) continue;
            const double flow = bin.wf / bin.w, rate = bin.wro / bin.ow, outdoor = bin.wo / bin.ow;
            const double x = flow - p_.roomC, power = c * (rate + b * (p_.roomC - outdoor));
            if (!(x >= p_.minLiftK) || !(power > 0) || !std::isfinite(power)) continue;
            sxp += bin.ow * x * power; sxx += bin.ow * x * x;
        }
        if (!(sxx > 0) || !(sxp > 0)) return std::nullopt;
        return static_cast<float>(sxp / sxx);
    }
    static float median(std::array<float, RoomPlan::maxRooms>& v, size_t n) {
        std::sort(v.begin(), v.begin() + n);
        return n % 2 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
    }
    Params p_;
    std::optional<float> ua_, kw_, slope_;
    const char* uaSource_ = nullptr;
    const char* kwSource_ = nullptr;
};
}
