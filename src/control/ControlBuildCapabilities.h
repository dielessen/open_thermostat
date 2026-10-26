#pragma once
#include "NativeSourceProvisioning.h"
#include "ShadowController.h"
#include "UtcSchedule.h"
#include <ostream>

namespace heating::control {
// Compile-time discovery on the EXISTING authenticated /status route. This is
// deliberately separate from the current owner's fw/hello/source_policy and
// /status.control. Advertising compiled code never selects a SOURCE, opens a
// session, qualifies a sensor/actuator, or authorizes physical outputs.
inline void writeControlBuildCapabilities(std::ostream& out) {
    out << "{\"schema\":1,\"scope\":\"compiled_support_only\","
        << "\"requires_local_source_selection\":true,\"authorizes_physical_outputs\":false,"
        << "\"settings_bytes_exclusive\":" << nativeNetworkSettingsMaximumBytes
        << ",\"config_bytes\":" << ShadowController::maximumConfigBytes
        << ",\"source_formats\":[\"" << nativeLocalSourceFormat << "\",\""
        << nativeWeekSourceFormat << "\",\"" << nativeEvolutionSourceFormat << "\"],"
        << "\"plans\":[{\"contract\":\"" << NativePlanInstallationSource::contract
        << "\",\"minimum_zones\":" << NativePlanInstallationSource::maximumZones
        << ",\"maximum_zones\":" << NativePlanInstallationSource::maximumZones
        << ",\"maximum_total_transitions\":" << NativePlanInstallationSource::maximumTransitions
        << "},{\"contract\":\"" << NativePlanInstallationSource::weekContract
        << "\",\"minimum_zones\":1,\"maximum_zones\":" << NativePlanInstallationSource::maximumZones
        << ",\"maximum_transitions_per_zone\":" << UtcSchedule::maximumTransitions
        << ",\"maximum_total_transitions\":" << NativePlanInstallationSource::maximumZones * UtcSchedule::maximumTransitions
        << ",\"maximum_horizon_seconds\":" << UtcSchedule::maximumHorizonSeconds << "}]}";
}
}
