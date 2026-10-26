#pragma once
#include "EMS/BoilerTestSession.h"

namespace heating::ems::testing_detail {
// Only finite tests collapse emission into one instant. Real IO must reserve at
// its last send boundary and record completion with the actual completion time.
template<class Owner>
bool instantTransmission(Owner& owner, const BoilerTestSession::Intent& intent,
                         uint64_t now, bool success, const BoilerTestSession::Gates& gates,
                         const ClassicBoilerMonitor& monitor) {
    return owner.beginTransmit(intent, now, gates, monitor)
        && owner.finishTransmit(intent, now, success, gates, monitor);
}
}
