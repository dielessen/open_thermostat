#pragma once
#include "BoilerTestSession.h"

namespace heating::ems {
// SOFTWARE limits for a short supervised trial on the target Ecomline Classic
// installation, not a hydraulic rating or independent validation of its adapter.
// Manufacturer manual: InstalEcomLineClassic, sections2.2/2.3.1/5.1.
// The narrower trial limits/duration below are our engineering choices.
struct ClassicHeatTrialEnvelope {
    static constexpr const char* id = "ecomline-classic-manual-v1";
    enum class PressureSource { reportedSensor, separateCheck };
    static constexpr const char* profileId(PressureSource source) {
        return source == PressureSource::separateCheck ? "ecomline-classic-separate-pressure-v1" : id;
    }
    static constexpr uint32_t configurationTtlMs = 600000;
    static constexpr int32_t minimumPressureDecibar = 10, maximumPressureDecibar = 25;
    // A 50 C target needs room for actual water temperature and hysteresis.
    // This remains a supervised-trial cutoff, not a normal thermostat rule.
    static constexpr int32_t minimumMeasuredFlowCenti = 500, maximumMeasuredFlowCenti = 6000;
    struct Check { bool ready; const char* reason; };
    static BoilerTestSession::Profile profile() {
        auto result = BoilerTestSession::Profile::supervisedZeroOnly();
        result.minimumFlowC = 40; result.maximumFlowC = 50;
        result.maximumHeatMs = BoilerTestSession::maximumTrialMs;
        return result;
    }
    static Check inspect(const ClassicBoilerMonitor& monitor, uint64_t now,
                         PressureSource pressureSource = PressureSource::reportedSensor,
                         bool separatePressureMethodReviewed = false,
                         bool heatInProgress = false) {
        if (monitor.capabilities().profile() != BoilerProtocol::classic) return {false, "classic_required"};
        const auto liveTtl = profile().reportTtlMs;
        const auto& flow = monitor.sample(BoilerField::flow);
        if (!usable(flow, 0x18, now, liveTtl)) return {false, "flow_unavailable"};
        if (*flow.raw < minimumMeasuredFlowCenti || *flow.raw >= maximumMeasuredFlowCenti)
            return {false, "flow_outside_trial_limits"};
        if (pressureSource == PressureSource::separateCheck) {
            // Installation-specific source decision, never inferred from a
            // missing reading or selected boiler picture. This does not create
            // telemetry or replace the per-test operator declaration.
            if (!separatePressureMethodReviewed) return {false, "pressure_check_method_unreviewed"};
        } else if (pressureSource == PressureSource::reportedSensor) {
            const auto& pressure = monitor.sample(BoilerField::pressure);
            if (!usable(pressure, 0x18, now, liveTtl)) return {false, "pressure_unavailable"};
            if (*pressure.raw < minimumPressureDecibar || *pressure.raw > maximumPressureDecibar)
                return {false, "pressure_outside_trial_limits"};
        } else return {false, "pressure_source_invalid"};
        const auto& enabled = monitor.sample(BoilerField::heatingEnabled);
        // Settings must be fresh before starting. During that finite run retain
        // the admitted settings for at most one trial duration; live flow and
        // stop feedback still expire after 15 seconds. New settings override old.
        const auto settingsTtl = configurationTtlMs + (heatInProgress ? profile().maximumHeatMs : 0);
        if (!usable(enabled, 0x16, now, settingsTtl)) return {false, "heating_setting_unavailable"};
        if (*enabled.raw != 1) return {false, "heating_disabled"};
        const auto& limit = monitor.sample(BoilerField::heatingLimit);
        if (!usable(limit, 0x16, now, settingsTtl)) return {false, "heating_limit_unavailable"};
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
