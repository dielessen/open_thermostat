#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <optional>
namespace heating::control {
// Optional weather-compensated base flow (beta.19 item 19): the flow that holds
// a room at its setpoint for the outdoor temperature, one circuit:
//   base = setpoint + slope x max(0, setpoint - outdoor)
// slope: K of flow above the room per K the outdoor is below it. Until learned
// it follows the design flow at -10 degC outdoor and a 20 degC room: floor 40
// degC (slope 0.67), radiators 55 degC (1.17); one radiator on the circuit
// makes it a radiator circuit. FlowPolicy adds half the room PI correction on
// top and bounds the result to the plan and the boiler. Pure.
struct WeatherCurve {
    static constexpr int16_t designOutdoorCentiC = -1000, designRoomCentiC = 2000;
    static constexpr float minSlope = 0.2f, maxSlope = 2.5f;
    static constexpr uint8_t floorDesignFlowC = 40, radiatorDesignFlowC = 55;
    static constexpr uint8_t minDesignFlowC = 25, maxDesignFlowC = 80;
    static float slopeFor(uint8_t designFlowC) {
        return std::clamp((designFlowC * 100.0f - designRoomCentiC) / float(designRoomCentiC - designOutdoorCentiC), minSlope, maxSlope);
    }
    static int16_t baseCentiC(float slope, int16_t setpointCentiC, int16_t outdoorCentiC) {
        const int32_t below = std::max<int32_t>(0, int32_t(setpointCentiC) - outdoorCentiC);
        return static_cast<int16_t>(std::min<int32_t>(9000, setpointCentiC + static_cast<int32_t>(std::clamp(slope, minSlope, maxSlope) * below + 0.5f)));
    }
};

// Learns the curve's slope from what the house shows, whoever heats (now the
// tado, later the E32): a 3 h window in which the leading room stays at its
// setpoint (mean within 0.5 degC, drift at most 0.3 degC, setpoint unchanged)
// while the outdoor is at least 5 K colder, with at most 10 % hot water and
// fresh data throughout, held the room with the heat it got. With burner duty d
// (heating time with flame / heating time) at mean flow F while firing, a steady
// flow giving the same emitter output is about Feq = room + d (F - room)
// (emitter output ~ flow - room). Each window's point (setpoint - outdoor,
// Feq - setpoint) joins a least-squares fit through the foot point (no heat at
// outdoor = setpoint); from 6 windows the learned slope replaces the design
// one. Older windows fade past 30. RAM only; pure, single-threaded, every 10 s.
class CurveLearner {
public:
    struct Params {
        uint32_t windowMs = 10800000, maxGapMs = 60000;
        int16_t maxDriftCentiC = 30, maxErrorCentiC = 50, minLiftCentiC = 500;
        uint8_t minWindows = 6;
        float memoryWindows = 30, maxHotWaterShare = 0.1f, minDuty = 0.05f;
    };
    struct Sample {
        int8_t room = -1;                                             // leading plan room, -1: none
        std::optional<int16_t> roomCentiC, setpointCentiC, outdoorCentiC, flowCentiC;
        std::optional<bool> burnerOn, hotWater;
    };
    CurveLearner() = default;
    explicit CurveLearner(Params p) : p_(p) {}

    void sample(uint64_t now, const Sample& s) {
        const bool gap = !haveLast_ || now <= lastMs_ || now - lastMs_ > p_.maxGapMs;
        const uint32_t dt = gap ? 0 : static_cast<uint32_t>(now - lastMs_);
        lastMs_ = now; haveLast_ = true;
        const bool known = s.room >= 0 && s.roomCentiC && s.setpointCentiC && s.outdoorCentiC && s.burnerOn && s.hotWater
            && (!*s.burnerOn || *s.hotWater || s.flowCentiC);
        if (w_.open && (gap || !known || s.room != w_.room || *s.setpointCentiC != w_.setpoint)) { w_.open = false; last_ = "window_interrupted"; }
        if (!known) return;
        if (!w_.open) { w_ = {}; w_.open = true; w_.room = s.room; w_.setpoint = *s.setpointCentiC; w_.first = *s.roomCentiC; w_.startMs = now; }
        w_.last = *s.roomCentiC;
        if (dt) {
            w_.totalMs += dt; w_.roomSum += double(*s.roomCentiC) * dt; w_.outdoorSum += double(*s.outdoorCentiC) * dt;
            if (*s.hotWater) w_.hotWaterMs += dt;
            else if (*s.burnerOn) { w_.onMs += dt; w_.flowSum += double(*s.flowCentiC) * dt; }
        }
        if (now - w_.startMs >= p_.windowMs) finish();
    }
    std::optional<float> slope() const {
        if (windows_ < p_.minWindows || sxx_ <= 0) return std::nullopt;
        return static_cast<float>(std::clamp(sxy_ / sxx_, double(WeatherCurve::minSlope), double(WeatherCurve::maxSlope)));
    }
    uint16_t windows() const { return windows_; }
    uint16_t rejected() const { return rejected_; }
    const char* last() const { return last_; }

private:
    struct Window {
        bool open = false;
        int8_t room = -1;
        int16_t setpoint = 0, first = 0, last = 0;
        uint64_t startMs = 0;
        double totalMs = 0, roomSum = 0, outdoorSum = 0, onMs = 0, flowSum = 0, hotWaterMs = 0;
    };
    void finish() {
        w_.open = false;
        const auto reject = [&](const char* why) { rejected_ = sat(rejected_); last_ = why; };
        const double heatMs = w_.totalMs - w_.hotWaterMs;
        if (w_.totalMs <= 0 || w_.hotWaterMs > p_.maxHotWaterShare * w_.totalMs) return reject("hot_water");
        const double room = w_.roomSum / w_.totalMs, outdoor = w_.outdoorSum / w_.totalMs; // centi degC
        if (std::abs(w_.setpoint - room) > p_.maxErrorCentiC) return reject("not_at_setpoint");
        if (std::abs(w_.last - w_.first) > p_.maxDriftCentiC) return reject("room_not_steady");
        const double x = (w_.setpoint - outdoor) / 100.0;
        if (x * 100 < p_.minLiftCentiC) return reject("too_mild");
        const double duty = heatMs > 0 ? w_.onMs / heatMs : 0;
        if (duty < p_.minDuty) return reject("no_heat");
        const double flow = w_.flowSum / w_.onMs, equivalent = room + duty * (flow - room);
        const double y = (equivalent - w_.setpoint) / 100.0, slope = y / x;
        if (slope < 0.05 || slope > 3) return reject("out_of_range");
        if (n_ >= p_.memoryWindows) { sxy_ *= 0.5; sxx_ *= 0.5; n_ *= 0.5; }
        sxy_ += x * y; sxx_ += x * x; n_ += 1;
        windows_ = sat(windows_); last_ = "window_learned";
    }
    template <typename T> static T sat(T v) { return v == T(~T(0)) ? v : T(v + 1); }
    Params p_;
    Window w_;
    bool haveLast_ = false;
    uint64_t lastMs_ = 0;
    uint16_t windows_ = 0, rejected_ = 0;
    double sxy_ = 0, sxx_ = 0, n_ = 0;
    const char* last_ = "collecting";
};
}
