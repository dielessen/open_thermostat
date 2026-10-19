#pragma once
#include <cmath>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class TemperatureUnit { celsius, fahrenheit };
enum class SampleEvidence { unknown, physical_report, validated_integration_report, cache_read, device_seen };
enum class SampleState { unknown, valid, invalid, unavailable, restored, unverified, stale };

struct TemperatureProfile {
    int16_t minimumCentiC = -2000;
    int16_t maximumCentiC = 6000;
    int16_t calibrationCentiC = 0;
    uint32_t maximumAgeMs = 120000;
    bool acceptsValidatedIntegrationReport = false;
    bool valid() const {
        return minimumCentiC < maximumCentiC && calibrationCentiC >= -500 &&
            calibrationCentiC <= 500 && maximumAgeMs > 0 && maximumAgeMs <= 86400000;
    }
};

// Transport identity/sequence/grant admission happens BEFORE this source model.
// A grant's elapsed time is a conservative transport-delay upper bound; a new
// packet never resets the age of an old physical observation to zero.
class TemperatureSample {
public:
    bool observe(double temperature, TemperatureUnit unit, SampleEvidence evidence,
                 uint64_t sourceAgeMs, uint64_t transportUpperBoundMs, uint64_t receivedMs,
                 const TemperatureProfile &profile, bool restored = false) {
        raw_.reset(); receivedMs_ = receivedMs; ageAtReceiveMs_ = 0;
        ageKnown_ = sourceAgeMs <= UINT64_MAX - transportUpperBoundMs;
        if (ageKnown_) ageAtReceiveMs_ = sourceAgeMs + transportUpperBoundMs;
        maximumAgeMs_ = profile.maximumAgeMs; evidence_ = evidence;
        if (!profile.valid() || !std::isfinite(temperature) ||
            (unit != TemperatureUnit::celsius && unit != TemperatureUnit::fahrenheit))
            return reject(SampleState::invalid);
        const double celsius = unit == TemperatureUnit::fahrenheit ? (temperature - 32.0) * 5.0 / 9.0 : temperature;
        const double calibrated = celsius * 100.0 + profile.calibrationCentiC;
        if (!std::isfinite(calibrated) || calibrated < profile.minimumCentiC || calibrated > profile.maximumCentiC)
            return reject(SampleState::invalid);
        raw_ = static_cast<int16_t>(std::lround(calibrated));
        if (restored) return reject(SampleState::restored);
        if (evidence != SampleEvidence::physical_report &&
            !(evidence == SampleEvidence::validated_integration_report && profile.acceptsValidatedIntegrationReport))
            return reject(SampleState::unverified);
        // Compare before adding, so hostile huge ages cannot wrap into freshness.
        if (sourceAgeMs >= maximumAgeMs_ || transportUpperBoundMs >= maximumAgeMs_ ||
            sourceAgeMs + transportUpperBoundMs >= maximumAgeMs_)
            return reject(SampleState::stale);
        ageAtReceiveMs_ = sourceAgeMs + transportUpperBoundMs;
        state_ = SampleState::valid;
        return true;
    }
    void unavailable() { raw_.reset(); state_ = SampleState::unavailable; }
    SampleState state(uint64_t now) const {
        if (state_ != SampleState::valid) return state_;
        if (now < receivedMs_ || now - receivedMs_ >= maximumAgeMs_ - ageAtReceiveMs_)
            return SampleState::stale;
        return SampleState::valid;
    }
    std::optional<int16_t> value(uint64_t now) const {
        return state(now) == SampleState::valid ? raw_ : std::nullopt;
    }
    std::optional<uint64_t> age(uint64_t now) const {
        if (!raw_ || !ageKnown_ || now < receivedMs_ || now - receivedMs_ > UINT64_MAX - ageAtReceiveMs_) return {};
        return ageAtReceiveMs_ + (now - receivedMs_);
    }
    SampleEvidence evidence() const { return evidence_; }
private:
    bool reject(SampleState state) { state_ = state; return false; }
    std::optional<int16_t> raw_;
    uint64_t receivedMs_ = 0, ageAtReceiveMs_ = 0;
    uint32_t maximumAgeMs_ = 0;
    bool ageKnown_ = false;
    SampleEvidence evidence_ = SampleEvidence::unknown;
    SampleState state_ = SampleState::unknown;
};
}
