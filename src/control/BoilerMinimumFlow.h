#pragma once
#include "control/FlowDemand.h"
#include <algorithm>
#include <cstdint>
#include <optional>
namespace heating::control {
// The lowest flow request this boiler answers with a heating burn (rc.2). The
// owner's EcomLine HRC 22 keeps its store warm, so its water stays at >= 38
// degC and it does not fire for heating below about 40 degC: requests of 33..35
// degC (minimum 30, gain 10, a small shortfall) gave no heat at all on the first
// active evening. Learned only while the E32 drives the boiler: heat asked at X
// degC, a room below its target and no heating burn for noFireMs of countable
// time (no hot water, not just after it, no gap) raises the minimum to
// max(X, the lowest boiler water seen meanwhile) + stepC, at most maxC. Every
// decayBurnMs of heating burns lowers it by 1 degC, so a boiler that changed
// (a setting, the season) is found out again. Another boiler (EMS product id)
// starts over. effective() bounds it by the plan and the boiler's limit; the
// guard sends max(request, effective). Pure; FlowLearner owns it (LearnedState
// keeps it).
class BoilerMinimumFlow {
public:
    struct Params {
        uint32_t noFireMs = 15 * 60000;       // countable time without a heating burn
        uint32_t afterHotWaterMs = 3 * 60000; // a boiler may hold heating back right after hot water
        uint32_t burnMs = 2 * 60000;          // a heating burn: flame without the hot-water bit this long
        uint32_t maxStepMs = 60000;           // a longer silence counts nothing
        uint32_t decayBurnS = 12 * 3600;      // heating burn time per 1 degC lower
        uint8_t stepC = 2, maxC = 50;         // a boiler that needs more has another problem
    };
    struct Input {
        bool asked = false;                   // the E32 drives the boiler and asks heat
        uint8_t flowC = 0;                    // the flow it asked (the guard's command)
        std::optional<int16_t> boilerFlowCentiC;
        std::optional<bool> burnerOn, hotWater;
        bool roomBelow = false;               // a fresh room at least 0.1 degC below its target
        std::optional<uint8_t> productId;     // the boiler's EMS product id, when read
    };

    BoilerMinimumFlow() = default;
    explicit BoilerMinimumFlow(Params p) : p_(p) {}

    void sample(uint64_t now, uint32_t dtMs, const Input& in) {
        if (in.productId && *in.productId) {
            if (productId_ && productId_ != *in.productId) forget();
            productId_ = *in.productId;
        }
        const bool known = in.burnerOn && in.hotWater;
        if (known && *in.hotWater) hotWaterUntil_ = now + p_.afterHotWaterMs;
        const bool flame = known && *in.burnerOn && !*in.hotWater;
        if (!flame) burnSince_.reset();
        else if (!burnSince_) burnSince_ = now;
        const bool burning = flame && now - *burnSince_ >= p_.burnMs;
        const bool step = dtMs > 0 && dtMs <= p_.maxStepMs;
        if (burning) {
            // It fires: the request works. Slowly forget, so a lower minimum is tried again.
            waitMs_ = 0; lowest_.reset();
            if (learnedC_ && step && (burnS_ += dtMs / 1000) >= p_.decayBurnS) { burnS_ = 0; --learnedC_; }
            return;
        }
        if (!known || !in.asked || !in.roomBelow) { waitMs_ = 0; lowest_.reset(); return; }
        if (flame || *in.hotWater || now < hotWaterUntil_ || !step) return; // not countable, not an answer either
        waitMs_ += dtMs;
        if (in.boilerFlowCentiC) lowest_ = lowest_ ? std::min(*lowest_, *in.boilerFlowCentiC) : *in.boilerFlowCentiC;
        if (waitMs_ < p_.noFireMs) return;
        const int water = lowest_ ? (std::max<int>(*lowest_, 0) + 99) / 100 : 0;
        const int raised = std::max<int>({learnedC_, in.flowC, water}) + p_.stepC;
        learnedC_ = static_cast<uint8_t>(std::min<int>(raised, p_.maxC));
        raises_ = raises_ == UINT16_MAX ? raises_ : uint16_t(raises_ + 1);
        burnS_ = 0; waitMs_ = 0; lowest_.reset();
    }
    // The minimum to ask while heating: at least the plan's, at most below the plan's
    // maximum (ActiveHeatGuard needs minimum < maximum) and the boiler's own limit.
    uint8_t effective(uint8_t planMinC, uint8_t planMaxC, std::optional<uint8_t> limitC) const {
        const int cap = std::min<int>({planMaxC - 1, limitC.value_or(FlowDemand::ceilingC), p_.maxC});
        return static_cast<uint8_t>(std::max<int>(planMinC, std::min<int>(learnedC_, cap)));
    }
    uint8_t learnedC() const { return learnedC_; } // 0: none (the plan's minimum)
    uint16_t raises() const { return raises_; }
    const Params& params() const { return p_; }
    void forget() { learnedC_ = 0; raises_ = 0; burnS_ = 0; waitMs_ = 0; lowest_.reset(); }

private:
    friend class LearnedState;
    Params p_;
    uint8_t learnedC_ = 0, productId_ = 0;
    uint16_t raises_ = 0;
    uint32_t burnS_ = 0, waitMs_ = 0;
    uint64_t hotWaterUntil_ = 0;
    std::optional<uint64_t> burnSince_;
    std::optional<int16_t> lowest_;
};
}
