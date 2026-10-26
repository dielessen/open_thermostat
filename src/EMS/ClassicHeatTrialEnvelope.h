#pragma once
#include "BoilerTestSession.h"

namespace heating::ems {
// SOFTWARE limits for a short supervised trial on the target Ecomline Classic
// installation, not a hydraulic rating or independent validation of its adapter.
// Manufacturer manual: InstalEcomLineClassic, sections2.2/2.3.1/5.1.
// The narrower trial limits/duration below are our engineering choices.
struct ClassicHeatTrialEnvelope {
    static constexpr const char* id = "ecomline-classic-manual-v1";
    static constexpr uint32_t configurationTtlMs = 600000;
    static constexpr int32_t minimumPressureDecibar = 10, maximumPressureDecibar = 25;
    static constexpr int32_t minimumMeasuredFlowCenti = 500, maximumMeasuredFlowCenti = 5000;
    struct Check { bool ready; const char* reason; };
    static BoilerTestSession::Profile profile() {
        auto result = BoilerTestSession::Profile::supervisedZeroOnly();
        result.minimumFlowC = 40; result.maximumFlowC = 45; result.maximumHeatMs = 60000;
        return result;
    }
    static Check inspect(const ClassicBoilerMonitor& monitor, uint64_t now) {
        if (monitor.capabilities().profile() != BoilerProtocol::classic) return {false, "classic_required"};
        const auto liveTtl = profile().reportTtlMs;
        const auto& flow = monitor.sample(BoilerField::flow);
        if (!usable(flow, 0x18, now, liveTtl)) return {false, "flow_unavailable"};
        if (*flow.raw < minimumMeasuredFlowCenti || *flow.raw >= maximumMeasuredFlowCenti)
            return {false, "flow_outside_trial_limits"};
        const auto& pressure = monitor.sample(BoilerField::pressure);
        if (!usable(pressure, 0x18, now, liveTtl)) return {false, "pressure_unavailable"};
        if (*pressure.raw < minimumPressureDecibar || *pressure.raw > maximumPressureDecibar)
            return {false, "pressure_outside_trial_limits"};
        const auto& enabled = monitor.sample(BoilerField::heatingEnabled);
        if (!usable(enabled, 0x16, now, configurationTtlMs)) return {false, "heating_setting_unavailable"};
        if (*enabled.raw != 1) return {false, "heating_disabled"};
        const auto& limit = monitor.sample(BoilerField::heatingLimit);
        if (!usable(limit, 0x16, now, configurationTtlMs)) return {false, "heating_limit_unavailable"};
        if (*limit.raw < int32_t(profile().maximumFlowC) * 100 || *limit.raw > 9000)
            return {false, "heating_limit_outside_trial_limits"};
        return {true, "telemetry_ready"};
    }
private:
    static bool usable(const BoilerSample& sample, uint16_t source, uint64_t now, uint32_t ttl) {
        return sample.raw && sample.fresh(now, ttl) && sample.quality == BoilerQuality::reported
            && sample.sourceType == source;
    }
};
}
