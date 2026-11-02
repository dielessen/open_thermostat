#pragma once
#include "control/RoomPlan.h"
#include <cJSON.h>
#include <cstdint>
namespace heating::control {
// The mode of a NEW plan, from what the E32 hears on the boiler bus (owner,
// 2 Nov 2026). Only an E32 without a stored plan follows it; a stored plan
// always keeps its own mode, and the owner can choose the other route.
//   thermostat_heard  another EMS controller asked the boiler for heat (0x1A)
//                     this boot: a trial run beside it (shadow), with the
//                     comparison and the readiness checklist
//   no_thermostat     the boiler was heard listenMs without such a request
//                     (none, removed, or not an EMS thermostat): active, with
//                     the guided boiler test leading to the takeover
//   checking          the bus was not heard long enough yet: shadow, so it is
//                     never active while a thermostat may still be there
// Active still sends nothing before the owner confirms the takeover.
struct NewPlanDefault {
    enum class Reason : uint8_t { checking, thermostatHeard, noThermostat };
    static constexpr uint64_t listenMs = 120000;
    RoomPlan::Mode mode = RoomPlan::Mode::shadow;
    Reason reason = Reason::checking;

    // foreignHeard: a 0x1A from another master this boot; listenedMs: continuous boiler reception
    // (ActiveHeatGuard::listenedMs); activeAllowed: the firmware's active gate.
    static NewPlanDefault decide(bool foreignHeard, uint64_t listenedMs, bool activeAllowed) {
        if (foreignHeard) return {RoomPlan::Mode::shadow, Reason::thermostatHeard};
        if (listenedMs < listenMs) return {RoomPlan::Mode::shadow, Reason::checking};
        return {activeAllowed ? RoomPlan::Mode::active : RoomPlan::Mode::shadow, Reason::noThermostat};
    }
    // An E32 without a stored plan takes the default; true when its mode changed.
    bool apply(RoomPlan& plan, bool stored) const {
        if (stored || plan.mode == mode) return false;
        plan.mode = mode;
        return true;
    }
    static const char* name(Reason r) {
        return r == Reason::thermostatHeard ? "thermostat_heard" : r == Reason::noThermostat ? "no_thermostat" : "checking";
    }
    // {"stored":bool,"mode":"shadow"|"active","reason":..}: the route a new plan takes, and why.
    bool addJson(cJSON* root, bool stored) const {
        cJSON* o = cJSON_AddObjectToObject(root, "new_plan");
        return o && cJSON_AddBoolToObject(o, "stored", stored)
            && cJSON_AddStringToObject(o, "mode", mode == RoomPlan::Mode::active ? "active" : "shadow")
            && cJSON_AddStringToObject(o, "reason", name(reason));
    }
};
}
