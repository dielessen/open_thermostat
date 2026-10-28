#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <optional>
namespace heating::control {
// One room's heat demand from an ordered list of temperature sources.
// The first fresh source leads; the rest are fallback (owner, 2026-10-28:
// living room = tado via HA, then a Bluetooth sensor; a room with only a
// Bluetooth sensor uses it as primary). Pure: no IO, clock or allocation.
struct RoomDemand {
    static constexpr size_t maxSources = 4;
    enum class State : uint8_t { active, inactive };
    enum class Status : uint8_t { inactive, ok, fallback, stale, lost };

    struct Reading {
        std::optional<int16_t> centiC; // nullopt: source reported nothing usable
        uint64_t atMs = 0;
    };
    struct Spec {
        State state = State::inactive;
        uint8_t sources = 0;            // number of configured sources, in priority order
        uint32_t maxAgeMs = 900000;     // a reading older than this is not used
        uint32_t lostAfterMs = 1800000; // no usable source this long: stop asking for heat
        int16_t minimumCentiC = 500, maximumCentiC = 3000;
    };
    struct Result {
        Status status = Status::inactive;
        int8_t source = -1;                 // index of the leading source
        std::optional<int16_t> temperature; // leading reading
        std::optional<int16_t> setpoint;    // clamped setpoint
        int16_t errorCentiC = 0;            // setpoint - temperature (> 0: too cold)
        bool usable = false;                // measurement and setpoint known: feed the regulator
    };

    // setpoint: from HA (tado target) or the local program; nullopt: none known.
    // lastUsable: caller-kept last usable reading. Without any fresh source the
    // room keeps using it until lostAfterMs, then stops asking for heat.
    static Result evaluate(const Spec& spec, const std::array<Reading, maxSources>& readings,
                           std::optional<int16_t> setpoint, uint64_t now, const Reading& lastUsable) {
        Result r;
        if (spec.state != State::active) return r; // caller resolves temporary pauses
        for (uint8_t i = 0; i < spec.sources && i < maxSources; ++i) {
            const auto& reading = readings[i];
            if (!reading.centiC || reading.atMs > now || now - reading.atMs > spec.maxAgeMs) continue;
            r.source = static_cast<int8_t>(i);
            r.temperature = reading.centiC;
            break;
        }
        if (setpoint) r.setpoint = std::clamp(*setpoint, spec.minimumCentiC, spec.maximumCentiC);
        if (r.temperature) {
            r.status = r.source == 0 ? Status::ok : Status::fallback;
        } else {
            const bool held = lastUsable.centiC && lastUsable.atMs <= now && now - lastUsable.atMs < spec.lostAfterMs;
            r.status = held ? Status::stale : Status::lost;
            if (!held) return r;
            r.temperature = lastUsable.centiC;
        }
        if (!r.setpoint) return r;
        r.errorCentiC = static_cast<int16_t>(*r.setpoint - *r.temperature);
        r.usable = true;
        return r;
    }
    static const char* name(Status s) {
        switch (s) {
            case Status::ok: return "ok";
            case Status::fallback: return "fallback";
            case Status::stale: return "stale";
            case Status::lost: return "lost";
            default: return "inactive";
        }
    }
};
}
