#pragma once
#include "control/ControlTuning.h"
#include "control/RoomDemand.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
namespace heating::control {
// The burner rest the E32 keeps, never shorter than the boiler's own (rc.5, P1). After a held
// target the boiler waits its own anti-cycle time before it fires again (BoilerResponse::restS,
// the median of what it did); a request sooner only meets a boiler that will not start yet, and
// counts a start the E32 did not get. So min_off_s in effect is at least that rest, at most
// 15 min, unless a room is cold now: more than 0.3 degC below its target (comfort first). The
// floor is never stored and never shown as the knob's value: AutoTuner keeps tuning min_off_s
// itself and the owner's value stays the owner's; the floor only lies on top of it. Pure.
struct RestFloor {
    static constexpr uint32_t maxS = 900;
    static constexpr int16_t coldCentiC = 30;
    // Raises t.minOffS to min(restS, maxS) unless coldNow; true when it did.
    static bool apply(ControlTuning& t, std::optional<uint32_t> restS, bool coldNow) {
        if (!restS || coldNow) return false;
        const auto floor = static_cast<uint16_t>(std::min<uint32_t>(*restS, maxS));
        if (t.minOffS >= floor) return false;
        t.minOffS = floor;
        return true;
    }
    // A usable room (RoomEngine's result) more than 0.3 degC below its target.
    static bool cold(const RoomDemand::Result& r) {
        return r.usable && r.status != RoomDemand::Status::inactive && r.errorCentiC > coldCentiC;
    }
    static bool cold(const RoomDemand::Result* rooms, size_t count) {
        for (size_t i = 0; rooms && i < count; ++i) if (cold(rooms[i])) return true;
        return false;
    }
};
}
