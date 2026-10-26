#pragma once
#include "BoilerTestService.h"

namespace heating::ems {
// Restricted, attended field commissioning; it does not qualify the physical
// installation or enable the automatic controller or persistent settings.
// The operator supplies exclusive ownership, local stop, heat path and a new
// boiler-manometer reading for EACH heat preparation. The real policy still
// proves a zero baseline before start and expires demand/attendance separately.
// Nefit EcomLine user instruction 70542900, p.2-1: read the manometer, >1 bar.
// https://nefit-nl-nl-b.boschhc-documents.com/download/file/file/70542900.pdf
struct EcomlineCommissioningProfile {
    static constexpr const char* mode = "supervised_commissioning";
    static constexpr bool attendedTrialEnabled = true;
    static constexpr bool boilerGaugeProcedureSupported = true;
    static BoilerTestService service(uint64_t boot, bool transmitterCompiled) {
        return {boot, transmitterCompiled, ClassicHeatTrialEnvelope::profile(), true, true, true, true};
    }
    static ClassicHeatTrialEnvelope::Check inspect(const ClassicBoilerMonitor& monitor, uint64_t now) {
        return ClassicHeatTrialEnvelope::inspect(monitor, now,
            ClassicHeatTrialEnvelope::PressureSource::separateCheck, boilerGaugeProcedureSupported);
    }
    static BoilerTestSession::Gates gates(const ClassicBoilerMonitor& monitor, uint64_t now, bool transportReady) {
        BoilerTestSession::Gates result;
        result.transmitterReviewed = transportReady && monitor.capabilities().profile() == BoilerProtocol::classic;
        result.pathReady = attendedTrialEnabled;
        result.limitsSafe = inspect(monitor, now).ready;
        // Site/pressure declarations belong to the service's accepted request.
        // Never fabricate exclusive ownership or an independent stop here.
        return result;
    }
};
}
