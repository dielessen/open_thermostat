#pragma once
#include <optional>
#include <cstdint>
namespace heating::control {
enum class BleSensorFrameStatus { not_present, malformed, key_required, decoded,
    encryption_required, authentication_failed, crypto_unavailable };

// Profile decoders return explicit fields, never a qualified control measurement.
struct BleSensorFrame {
    BleSensorFrameStatus status = BleSensorFrameStatus::not_present;
    bool triggerBased = false;
    bool authenticated = false; // message integrity only, never measurement/actuation qualification
    std::optional<uint32_t> encryptionCounter;
    std::optional<uint8_t> packetId, battery, lightLevel, button;
    std::optional<bool> batteryLow, light;
    std::optional<int16_t> temperature, humidity; // hundredths C / percent
    std::optional<uint16_t> declaredDeviceType;
    std::optional<uint32_t> firmware32, firmware24; // raw separate declarations
};

}
