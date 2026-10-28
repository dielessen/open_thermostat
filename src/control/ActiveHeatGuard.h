#pragma once
#include "control/FlowDemand.h"
#include "control/RoomDemand.h"
#include "control/RoomPlan.h"
#include <cJSON.h>
#include <algorithm>
#include <cstdint>
#include <optional>
#include <utility>
namespace heating::control {
// Active-mode policy between the room engine and the boiler (owner plan,
// phase 3). Per 10 s step it decides whether the E32 owns the boiler request
// and which UBASetPoints (0x1A) flow byte to send: the request every 60 s, at
// once when heat switches on or off, and a zero repeated for one stop window
// whenever a positive request ends or the E32 leaves active mode. It never
// sends in shadow mode, while another master sends 0x1A, or before this boot
// has listened to the bus. Pure and single-threaded: the caller owns the
// reviewed transmit route and reports each write back. flowC 0 = zero request.
class ActiveHeatGuard {
public:
    static constexpr uint8_t hardMaximumFlowC = 60; // floor group inlet limit
    static constexpr uint8_t boilerAddress = 0x08, serviceAddress = 0x0b;
    struct Params {
        uint8_t minimumFlowC = 30, maximumFlowC = 60;           // the plan's limits
        uint32_t requestIntervalMs = 60000;                     // refresh of an unchanged request
        uint32_t zeroIntervalMs = 10000, stopWindowMs = 60000;  // zero repeat after a stop
        uint32_t foreignQuietMs = 600000;  // no foreign 0x1A this long before arming
        uint32_t bootHoldoffMs = 120000;   // after an E32 restart: sources settle first
        uint32_t lostAfterMs = 1800000;    // arming without fresh rooms this long: own, ask zero
        uint32_t feedbackMs = 900000;      // heat asked this long without burner or flow rise: warn
        int16_t flowRiseCentiC = 300;
        int16_t frostOnCentiC = 500, frostOffCentiC = 600;
        bool valid() const {
            return minimumFlowC >= 20 && minimumFlowC < maximumFlowC && maximumFlowC <= hardMaximumFlowC
                && zeroIntervalMs >= 1000 && zeroIntervalMs <= stopWindowMs
                && requestIntervalMs >= zeroIntervalMs && requestIntervalMs <= 60000 && frostOnCentiC < frostOffCentiC;
        }
    };
    enum class State : uint8_t { shadow, blockedForeignController, arming, active, stoppedMeasurementLost, stopping };
    enum Warning : uint8_t { foreignController = 1, measurementLost = 2, boilerNoResponse = 4, transmitFailed = 8 };
    // Room summary for one step. add() each RoomDemand result; measured() any
    // fresh reading, also of inactive rooms (frost minimum).
    struct Rooms {
        uint8_t active = 0, fresh = 0, lost = 0;
        std::optional<int16_t> coldestCentiC;
        void add(const RoomDemand::Result& r) {
            if (r.status == RoomDemand::Status::inactive) return;
            ++active;
            if (r.status == RoomDemand::Status::lost) ++lost;
            if (r.status == RoomDemand::Status::ok || r.status == RoomDemand::Status::fallback) { ++fresh; measured(r.temperature); }
        }
        void measured(std::optional<int16_t> centiC) {
            if (centiC) coldestCentiC = coldestCentiC ? std::min(*coldestCentiC, *centiC) : *centiC;
        }
    };
    struct Foreign { uint8_t address = 0; uint64_t ageMs = 0; }; // last 0x1A to the boiler from another master
    struct Boiler { std::optional<bool> burnerOn; std::optional<int16_t> flowCentiC; }; // fresh reports only
    struct Inputs {
        RoomPlan::Mode mode = RoomPlan::Mode::shadow;
        FlowDemand::Request request{};
        Rooms rooms{};
        std::optional<Foreign> foreign;
        uint64_t uptimeMs = 0;   // how long this boot has listened to the bus
        bool routeReady = false; // the reviewed transmit route may send now
        Boiler boiler{};
    };
    struct Command { bool send = false; uint8_t flowC = 0; const char* why = "shadow"; };

    ActiveHeatGuard() = default;
    explicit ActiveHeatGuard(Params params) : p_(params) {}
    // Plan change: keeps ownership, so a stop still ends with its zero window.
    void setFlowLimits(uint8_t minimumFlowC, uint8_t maximumFlowC) { p_.minimumFlowC = minimumFlowC; p_.maximumFlowC = maximumFlowC; }

    Command step(uint64_t now, const Inputs& in) {
        foreign_ = in.foreign && in.foreign->address != serviceAddress && in.foreign->address != boilerAddress
            && in.foreign->ageMs < p_.foreignQuietMs ? in.foreign : std::nullopt;
        const bool wanted = in.mode == RoomPlan::Mode::active && p_.valid();
        if (owning() && (!wanted || foreign_)) enter(State::stopping, now);
        if (state_ == State::stopping && elapsed(now, since_) >= p_.stopWindowMs) enter(State::shadow, now);
        if (state_ != State::stopping) {
            if (!wanted) state_ = State::shadow;
            else if (foreign_) state_ = State::blockedForeignController;
            else if (!owning()) {
                if (state_ != State::arming) enter(State::arming, now);
                const bool listened = in.uptimeMs >= std::max(p_.bootHoldoffMs, p_.foreignQuietMs);
                const bool inputsFresh = in.rooms.fresh == in.rooms.active;
                if (listened && in.routeReady && (inputsFresh || elapsed(now, since_) >= p_.lostAfterMs)) enter(State::active, now);
            }
            if (owning()) state_ = in.rooms.active && in.rooms.lost == in.rooms.active ? State::stoppedMeasurementLost : State::active;
        }
        command_ = owning() ? request(now, in) : state_ == State::stopping ? stopZero(now, in) : Command{false, 0, name(state_)};
        if (!owning()) { lastTarget_ = 0; frost_ = false; heatSince_.reset(); }
        warnings_ = 0;
        if (wanted && foreign_) warnings_ |= foreignController;
        if (wanted && (in.rooms.lost || state_ == State::stoppedMeasurementLost)) warnings_ |= measurementLost;
        if (feedback(now, in.boiler)) warnings_ |= boilerNoResponse;
        if (owning() && elapsed(now, phaseSent_ ? std::max(since_, lastSentAt_) : since_) >= 3 * p_.requestIntervalMs)
            warnings_ |= transmitFailed;
        pending_ = command_.send;
        return command_;
    }
    // After each sent command: ok = the reviewed route completed the write.
    // A failed or missing report makes the next step retry.
    void transmitted(uint64_t now, bool ok) {
        if (!pending_) return;
        pending_ = false;
        if (!ok) return;
        warnings_ &= uint8_t(~transmitFailed);
        lastSentAt_ = now; lastSentFlow_ = command_.flowC; phaseSent_ = everSent_ = true;
        if (command_.flowC && !heatSince_) { heatSince_ = now; flowBaseline_.reset(); responded_ = false; }
    }

    State state() const { return state_; }
    const Command& command() const { return command_; }
    bool warning(Warning w) const { return warnings_ & w; }
    bool owning() const { return state_ == State::active || state_ == State::stoppedMeasurementLost; }
    static const char* name(State s) {
        switch (s) {
            case State::blockedForeignController: return "blocked_foreign_controller";
            case State::arming: return "arming";
            case State::active: return "active";
            case State::stoppedMeasurementLost: return "stopped_measurement_lost";
            case State::stopping: return "stopping";
            default: return "shadow";
        }
    }
    // {"state":..,"command":{..},"last_sent":{..}|null,"foreign_controller":{..}|null,"warnings":[..]}
    cJSON* json(uint64_t now) const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON_AddStringToObject(root, "state", name(state_));
        cJSON* command = cJSON_AddObjectToObject(root, "command");
        cJSON_AddBoolToObject(command, "send", command_.send);
        cJSON_AddNumberToObject(command, "flow_c", command_.flowC);
        cJSON_AddStringToObject(command, "why", command_.why);
        if (everSent_) {
            cJSON* sent = cJSON_AddObjectToObject(root, "last_sent");
            cJSON_AddNumberToObject(sent, "flow_c", lastSentFlow_);
            cJSON_AddNumberToObject(sent, "age_ms", double(elapsed(now, lastSentAt_)));
        } else cJSON_AddNullToObject(root, "last_sent");
        if (foreign_) {
            cJSON* f = cJSON_AddObjectToObject(root, "foreign_controller");
            cJSON_AddNumberToObject(f, "address", foreign_->address);
            cJSON_AddNumberToObject(f, "age_ms", double(foreign_->ageMs));
        } else cJSON_AddNullToObject(root, "foreign_controller");
        cJSON* warnings = cJSON_AddArrayToObject(root, "warnings");
        static constexpr std::pair<Warning, const char*> names[] = {{foreignController, "foreign_controller"},
            {measurementLost, "measurement_lost"}, {boilerNoResponse, "boiler_no_response"}, {transmitFailed, "transmit_failed"}};
        for (const auto& [w, n] : names) if (warning(w)) cJSON_AddItemToArray(warnings, cJSON_CreateString(n));
        return root;
    }

private:
    static uint64_t elapsed(uint64_t now, uint64_t since) { return now >= since ? now - since : 0; }
    void enter(State s, uint64_t now) { state_ = s; since_ = now; phaseSent_ = false; }
    Command due(bool send, uint8_t flowC, const char* why, const Inputs& in) const {
        if (send && !in.routeReady) return {false, flowC, "route_not_ready"};
        return {send, flowC, why};
    }
    Command stopZero(uint64_t now, const Inputs& in) const {
        return due(!phaseSent_ || elapsed(now, lastSentAt_) >= p_.zeroIntervalMs, 0, "stop_zero", in);
    }
    Command request(uint64_t now, const Inputs& in) {
        const auto& coldest = in.rooms.coldestCentiC;
        if (coldest && *coldest < p_.frostOnCentiC) frost_ = true;
        else if (!coldest || *coldest >= p_.frostOffCentiC) frost_ = false;
        const uint8_t cap = std::min(p_.maximumFlowC, hardMaximumFlowC);
        uint8_t target = 0;
        const char* why = state_ == State::stoppedMeasurementLost ? "measurement_lost" : "no_heat";
        if (state_ == State::active && in.request.heat) { target = std::clamp(in.request.flowC, p_.minimumFlowC, cap); why = "heat_request"; }
        if (frost_ && target < p_.minimumFlowC) { target = p_.minimumFlowC; why = "frost_minimum"; }
        target = std::min(target, cap);
        if (lastTarget_ && !target) { zeroFrom_ = now; zeroWindow_ = true; heatSince_.reset(); }
        if (target) zeroWindow_ = false;
        lastTarget_ = target;
        const uint64_t age = elapsed(now, lastSentAt_);
        const bool repeatZero = zeroWindow_ && elapsed(now, zeroFrom_) < p_.stopWindowMs && age >= p_.zeroIntervalMs;
        const bool send = !phaseSent_ || (target > 0) != (lastSentFlow_ > 0) || repeatZero || age >= p_.requestIntervalMs;
        return due(send, target, repeatZero && !target ? "stop_zero" : why, in);
    }
    // Requested heat that the boiler never answers: a warning, not a stop.
    bool feedback(uint64_t now, const Boiler& b) {
        if (!heatSince_ || !lastTarget_) return false;
        if (!flowBaseline_) flowBaseline_ = b.flowCentiC;
        if ((b.burnerOn && *b.burnerOn) || (flowBaseline_ && b.flowCentiC && *b.flowCentiC - *flowBaseline_ >= p_.flowRiseCentiC))
            responded_ = true;
        return !responded_ && elapsed(now, *heatSince_) >= p_.feedbackMs;
    }
    Params p_;
    State state_ = State::shadow;
    Command command_{};
    std::optional<Foreign> foreign_;
    uint64_t since_ = 0, lastSentAt_ = 0, zeroFrom_ = 0;
    uint8_t lastSentFlow_ = 0, lastTarget_ = 0, warnings_ = 0;
    bool phaseSent_ = false, everSent_ = false, pending_ = false, frost_ = false, zeroWindow_ = false, responded_ = false;
    std::optional<uint64_t> heatSince_;
    std::optional<int16_t> flowBaseline_;
};
}
