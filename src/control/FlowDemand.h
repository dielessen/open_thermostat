#pragma once
#include <algorithm>
#include <cstdint>
#include <optional>
namespace heating::control {
// Boiler flow-temperature request. Whether a room needs heat is decided per
// room by ZoneRegulator; this adds the boiler side: a flow temperature from the
// largest shortfall (PI) and minimum burner on/off times, between the plan's
// minimum and maximum flow (each home sets its own; 80 degC is the absolute
// ceiling). A floor circuit is protected by the plan's maximum or by its own
// mixing valve; the boiler's own heating limit caps the request further
// (ActiveHeatGuard).
// Pure: the caller transmits (or, in shadow mode, only reports) the result.
class FlowDemand {
public:
    static constexpr uint8_t ceilingC = 80; // highest plan maximum accepted
    struct Params {
        uint8_t minimumFlowC = 30, maximumFlowC = 60;
        uint8_t flowPerDegreeC = 10;                          // proportional part
        uint32_t integralSeconds = 1800;                      // 1 degC for 30 min adds flowPerDegreeC
        uint32_t minimumOnMs = 300000, minimumOffMs = 300000;
        bool valid() const {
            return minimumFlowC >= 20 && minimumFlowC < maximumFlowC && maximumFlowC <= ceilingC && integralSeconds >= 60;
        }
    };
    enum class Reason : uint8_t { idle, heating, holdOn, holdOff, satisfied, noDemand, invalid };
    struct Request { bool heat = false; uint8_t flowC = 0; Reason reason = Reason::idle; };

    FlowDemand() = default;
    explicit FlowDemand(Params params) : p_(params) {}

    // demand: some room's regulator wants heat. error: largest (setpoint -
    // temperature) over usable rooms; nullopt when no room can ask for heat
    // (all inactive, lost or without setpoint): an immediate safety stop.
    Request update(uint64_t now, bool demand, std::optional<int16_t> error) {
        if (!p_.valid()) return stop(now, Reason::invalid);
        if (!error) return stop(now, Reason::noDemand);
        const uint64_t dt = haveTime_ && now > lastNow_ ? now - lastNow_ : 0;
        lastNow_ = now; haveTime_ = true;
        if (!heating_) {
            if (!demand) return {false, 0, Reason::idle};
            if (changedAt_ && now - changedAt_ < p_.minimumOffMs) return {false, 0, Reason::holdOff};
            heating_ = true; changedAt_ = now; integralCentiCs_ = 0;
        } else if (!demand) {
            if (now - changedAt_ < p_.minimumOnMs) return {true, flow(*error), Reason::holdOn};
            return stop(now, Reason::satisfied);
        } else {
            // Anti-windup: integrate only while the request is inside its limits.
            const int64_t next = integralCentiCs_ + int64_t(*error) * int64_t(dt / 1000);
            if (flowFor(*error, next) < p_.maximumFlowC || next < integralCentiCs_) integralCentiCs_ = std::max<int64_t>(0, next);
        }
        return {true, flow(*error), Reason::heating};
    }
    bool heating() const { return heating_; }
    static const char* name(Reason r) {
        switch (r) {
            case Reason::heating: return "heating";
            case Reason::holdOn: return "minimum_on";
            case Reason::holdOff: return "minimum_off";
            case Reason::satisfied: return "satisfied";
            case Reason::noDemand: return "no_demand";
            case Reason::invalid: return "invalid_parameters";
            default: return "idle";
        }
    }
private:
    Request stop(uint64_t now, Reason reason) {
        if (heating_) { heating_ = false; changedAt_ = now; }
        integralCentiCs_ = 0; lastNow_ = now; haveTime_ = true;
        return {false, 0, reason};
    }
    uint8_t flow(int16_t error) const { return flowFor(error, integralCentiCs_); }
    uint8_t flowFor(int16_t error, int64_t integral) const {
        const int64_t proportional = int64_t(std::max<int16_t>(error, 0)) * p_.flowPerDegreeC / 100;
        const int64_t integralPart = integral * p_.flowPerDegreeC / (100 * int64_t(p_.integralSeconds));
        return static_cast<uint8_t>(std::clamp<int64_t>(p_.minimumFlowC + proportional + integralPart,
                                                        p_.minimumFlowC, p_.maximumFlowC));
    }
    Params p_;
    bool heating_ = false, haveTime_ = false;
    uint64_t changedAt_ = 0, lastNow_ = 0;
    int64_t integralCentiCs_ = 0;
};
}
