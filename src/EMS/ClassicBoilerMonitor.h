#pragma once

#include "BoilerCapabilities.h"
#include "EmsTelegram.h"
#include <array>
#include <cstdint>
#include <optional>
#include <ostream>

namespace heating::ems {

enum class BoilerField : size_t {
    selectedFlow, flow, returnTemp, outdoor, modulation, requestedPowerLimit,
    pressure, rawBurner, rawPump, rawFan, rawState, heatingActive, dhwActive,
    selectedDhw, dhwTemp, dhwFlow, heatingEnabled, dhwEnabled,
    burnerStarts, burnerMinutes, heatingMinutes, heatingStarts, dhwMinutes, dhwStarts,
    displayCode, serviceNumber, maxBurnerPower, pumpRunOn, heatingLimit, monitorDhwTarget, count
};
enum class BoilerQuality { reported, unreliable, inferred };

struct BoilerFieldSpec { const char *name; const char *unit; int divisor; uint32_t ttlMs; };
inline constexpr std::array<BoilerFieldSpec, static_cast<size_t>(BoilerField::count)> boilerFieldSpecs{{
    {"reported_selected_flow_temperature", "degC", 100, 30000},
    {"measured_flow_temperature", "degC", 100, 30000},
    {"measured_return_temperature", "degC", 100, 30000},
    {"outdoor_temperature", "degC", 100, 180000},
    {"reported_burner_modulation", "%", 1, 30000},
    {"reported_requested_power_limit", "%", 1, 30000},
    {"pressure", "bar", 10, 30000},
    {"raw_burner_bit", "bool", 1, 30000},
    {"raw_pump_bit", "bool", 1, 30000},
    {"raw_fan_bit", "bool", 1, 30000},
    {"raw_boiler_state", "bits", 1, 30000},
    {"heating_active", "bool", 1, 30000},
    {"dhw_active", "bool", 1, 30000},
    {"selected_dhw_temperature", "degC", 100, 600000},
    {"measured_dhw_temperature", "degC", 100, 30000},
    {"dhw_flow", "L/min", 10, 30000},
    {"heating_enabled", "bool", 1, 600000},
    {"dhw_enabled", "bool", 1, 600000},
    {"reported_burner_starts", "starts", 1, 180000},
    {"reported_burner_runtime", "min", 1, 180000},
    {"reported_heating_runtime", "min", 1, 180000},
    {"reported_heating_starts", "starts", 1, 180000},
    {"reported_dhw_runtime", "min", 1, 30000},
    {"reported_dhw_starts", "starts", 1, 30000},
    {"display_code", "text", 1, 30000},
    {"service_number", "code", 1, 30000},
    {"maximum_burner_power", "%", 1, 600000},
    {"pump_run_on", "min", 1, 600000},
    {"configured_heating_temperature", "degC", 100, 600000},
    {"reported_dhw_target", "degC", 100, 30000}
}};

struct BoilerSample {
    std::optional<int32_t> raw;
    uint64_t observedMs = 0;
    uint16_t sourceType = 0;
    BoilerQuality quality = BoilerQuality::reported;
    bool observed = false;
    bool fresh(uint64_t now, uint32_t ttl) const {
        return observed && now >= observedMs && now - observedMs < ttl;
    }
};

// Independent implementation from documented wire offsets. No copied EMS-ESP code.
// Stored numeric temperatures are hundredths Celsius; publication applies specs.
class ClassicBoilerMonitor {
public:
    const BoilerCapabilities &capabilities() const { return capabilities_; }
    const BoilerSample &sample(BoilerField f) const { return samples_[index(f)]; }
    std::optional<int32_t> value(BoilerField f, uint64_t now, bool allowUnreliable = false) const {
        const auto &s = sample(f);
        if (!s.fresh(now, boilerFieldSpecs[index(f)].ttlMs) ||
            (!allowUnreliable && s.quality == BoilerQuality::unreliable)) return {};
        return s.raw;
    }

    bool receive(const EmsTelegram &t, uint64_t now) {
        if (t.getSenderId() != 0x08 || t.dataSize() == 0 ||
            t.getOperationType() == EmsTelegram::READ ||
            t.getOperationType() == EmsTelegram::READ_WITH_DATA) return false;
        const auto family = BoilerCapabilities::family(t.getTypeId());
        if (family == BoilerProtocol::unknown) return false;
        capabilities_.observe(t.getTypeId());
        if (family != BoilerProtocol::classic) return false; // Plus processors remain intact.
        const auto put = [&](BoilerField field, std::optional<int32_t> v,
                             BoilerQuality quality = BoilerQuality::reported) {
            samples_[index(field)] = {v, now, t.getTypeId(), quality, true};
        };
        const auto byte = [&](BoilerField f, uint8_t offset, int scale = 1, int maximum = 254) {
            if (auto b = t.byteAt(offset)) put(f, *b <= maximum ? std::optional<int32_t>(*b * scale) : std::nullopt);
        };
        const auto temp = [&](BoilerField f, uint8_t offset, bool signedValue = false) {
            if (auto w = t.wordAt(offset)) {
                const int32_t v = signedValue ? static_cast<int16_t>(*w) : *w;
                put(f, *w != 0x8000 && *w != 0x7FFF && v >= -600 && v <= 1300
                    ? std::optional<int32_t>(v * 10) : std::nullopt);
            }
        };
        const auto counter = [&](BoilerField f, uint8_t offset) {
            // Present on the wire, but historically stationary on this Classic chain.
            if (auto c = t.counterAt(offset)) put(f, *c != 0xFFFFFF ? std::optional<int32_t>(*c) : std::nullopt,
                BoilerQuality::unreliable);
        };
        const auto enabled = [&](BoilerField f, uint8_t offset) {
            if (auto b = t.byteAt(offset)) put(f, (*b == 0 || *b == 0xFF)
                ? std::optional<int32_t>(*b == 0xFF) : std::nullopt);
        };
        switch (t.getTypeId()) {
            case 0x18:
                byte(BoilerField::selectedFlow, 0, 100, 100);
                temp(BoilerField::flow, 1);
                byte(BoilerField::requestedPowerLimit, 3, 1, 100);
                byte(BoilerField::modulation, 4, 1, 100);
                if (auto state = t.byteAt(5)) {
                    // EMS adapter-reported state, not an independent flame sensor.
                    put(BoilerField::rawState, *state);
                    put(BoilerField::heatingActive, (*state & 0x09) == 0x09, BoilerQuality::inferred);
                    put(BoilerField::dhwActive, (*state & 0x0A) == 0x0A, BoilerQuality::inferred);
                }
                if (auto flags = t.byteAt(7)) {
                    // Conservative Classic profile: historically unreliable on Mark's adapter.
                    put(BoilerField::rawBurner, (*flags & 1) != 0, BoilerQuality::unreliable);
                    put(BoilerField::rawPump, (*flags & 0x20) != 0, BoilerQuality::unreliable);
                    put(BoilerField::rawFan, (*flags & 4) != 0, BoilerQuality::unreliable);
                }
                temp(BoilerField::returnTemp, 13);
                byte(BoilerField::pressure, 17);
                if (auto code = t.wordAt(18)) {
                    const auto a = *code >> 8, b = *code & 255;
                    put(BoilerField::displayCode, a >= 32 && a <= 126 && b >= 32 && b <= 126
                        ? std::optional<int32_t>(*code) : std::nullopt);
                }
                if (auto code = t.wordAt(20)) put(BoilerField::serviceNumber, *code != 0xFFFF
                    ? std::optional<int32_t>(*code) : std::nullopt);
                break;
            case 0x19:
                temp(BoilerField::outdoor, 0, true);
                counter(BoilerField::burnerStarts, 10);
                counter(BoilerField::burnerMinutes, 13);
                counter(BoilerField::heatingMinutes, 19);
                counter(BoilerField::heatingStarts, 22);
                break;
            case 0x16:
                enabled(BoilerField::heatingEnabled, 0);
                byte(BoilerField::heatingLimit, 1, 100, 130);
                byte(BoilerField::maxBurnerPower, 2, 1, 100);
                byte(BoilerField::pumpRunOn, 8);
                break;
            case 0x33:
                enabled(BoilerField::dhwEnabled, 1);
                byte(BoilerField::selectedDhw, 2, 100, 100);
                break;
            case 0x34:
                byte(BoilerField::monitorDhwTarget, 0, 100, 100);
                temp(BoilerField::dhwTemp, 1);
                if (auto flow = t.byteAt(9)) put(BoilerField::dhwFlow,
                    *flow != 0xFF ? std::optional<int32_t>(*flow) : std::nullopt, BoilerQuality::unreliable);
                counter(BoilerField::dhwMinutes, 10);
                counter(BoilerField::dhwStarts, 13);
                break;
        }
        return true;
    }

    void writeJSON(std::ostream &ss, uint64_t now) const {
        ss << "{\"protocol_profile\":\"" << capabilities_.name()
           << "\",\"classic_control_commissioned\":false,\"physical_validation\":false,\"fields\":{";
        for (size_t i = 0; i < samples_.size(); ++i) {
            if (i) ss << ',';
            const auto &s = samples_[i]; const auto &spec = boilerFieldSpecs[i];
            const bool fresh = s.fresh(now, spec.ttlMs);
            const char *state = !s.observed ? "unknown" : !s.raw ? "invalid" : !fresh ? "stale" : "valid";
            ss << '"' << spec.name << "\":{\"value\":";
            // Unreliable bits remain inspectable, but are never trustworthy measurements.
            if (fresh && s.raw) {
                if (i == index(BoilerField::displayCode)) {
                    ss << '"';
                    for (char c : {static_cast<char>(*s.raw >> 8), static_cast<char>(*s.raw & 255)}) {
                        if (c == '"' || c == '\\') ss << '\\';
                        ss << c;
                    }
                    ss << '"';
                } else ss << static_cast<double>(*s.raw) / spec.divisor;
            } else ss << "null";
            ss << ",\"unit\":\"" << spec.unit << "\",\"state\":\"" << state << "\",\"quality\":\""
               << (s.quality == BoilerQuality::reported ? "reported" : s.quality == BoilerQuality::inferred ? "inferred" : "unreliable")
               << "\",\"source_type\":" << s.sourceType << ",\"source_address\":8,\"age_ms\":";
            if (s.observed && now >= s.observedMs) ss << now - s.observedMs; else ss << "null";
            ss << '}';
        }
        ss << "}}";
    }

private:
    static constexpr size_t index(BoilerField f) { return static_cast<size_t>(f); }
    BoilerCapabilities capabilities_;
    std::array<BoilerSample, static_cast<size_t>(BoilerField::count)> samples_{};
};
}
