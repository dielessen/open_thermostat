#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include "BthomeV2Codec.h"
#include "BleSensorFrame.h"

namespace heating::control {
// Thermometers with the pvvx custom firmware (github.com/pvvx/ATC_MiThermometer,
// e.g. the owner's MJWSD05MMC, firmware 5.9). Firmware 6.x only sends BTHome v2
// (service 0xFCD2, standard objects); older versions can also send the "PVVX
// Custom" format (service 0x181A, little endian, 0.01 units).

// Standard BTHome v2 objects with a fixed length. Temperature, humidity and
// battery are kept; other known objects are skipped; an unknown id is malformed.
inline BleSensorFrame decodeBthomeThermometerService(const uint8_t* service, std::size_t size) {
    using Status = BleSensorFrameStatus;
    const auto failure = [](Status status) { BleSensorFrame r; r.status = status; return r; };
    if (!service || size < 2 || size > 251) return failure(Status::malformed);
    if ((service[0] & 0xe0) != 0x40 || (service[0] & 0x1a)) return failure(Status::malformed);
    if (service[0] & 1) return failure(size >= 11 ? Status::key_required : Status::malformed);
    BleSensorFrame r;
    r.triggerBased = (service[0] & 4) != 0;
    for (std::size_t i = 1; i < size;) {
        const uint8_t id = service[i++];
        std::size_t length;
        switch (id) {
            case 0x00: case 0x01: case 0x09: case 0x0f: case 0x10: case 0x11: case 0x15: case 0x1a:
            case 0x2d: case 0x2e: case 0x3a: length = 1; break;
            case 0x02: case 0x03: case 0x0c: case 0x45: length = 2; break;
            default: return failure(Status::malformed); // no guessed object lengths
        }
        if (length > size - i) return failure(Status::malformed);
        const uint32_t raw = length == 1 ? service[i] : uint32_t(service[i]) | (uint32_t(service[i + 1]) << 8);
        i += length;
        switch (id) {
            case 0x00: r.packetId = static_cast<uint8_t>(raw); break;
            case 0x01: if (raw > 100) return failure(Status::malformed); r.battery = static_cast<uint8_t>(raw); break;
            case 0x02: { // sint16, 0.01 degC
                const int32_t v = raw < 0x8000 ? int32_t(raw) : int32_t(raw) - 65536;
                if (v < -4000 || v > 8500) return failure(Status::malformed);
                r.temperature = static_cast<int16_t>(v); break;
            }
            case 0x45: { // sint16, 0.1 degC
                const int32_t v = raw < 0x8000 ? int32_t(raw) : int32_t(raw) - 65536;
                if (v < -400 || v > 850) return failure(Status::malformed);
                r.temperature = static_cast<int16_t>(v * 10); break;
            }
            case 0x03: if (raw > 10000) return failure(Status::malformed); r.humidity = static_cast<int16_t>(raw); break;
            case 0x2e: if (raw > 100) return failure(Status::malformed); r.humidity = static_cast<int16_t>(raw * 100); break;
            default: break; // voltage, binary sensors, button: not used here
        }
    }
    // An events-only packet (e.g. a reed contact) carries no reading: ignore it,
    // so it cannot withdraw the last valid measurement.
    if (!r.temperature && !r.humidity && !r.battery) return {};
    r.status = Status::decoded;
    return r;
}

// "PVVX Custom" service 0x181A: MAC[6] (lo..hi), temperature int16 0.01 degC,
// humidity uint16 0.01 %, battery mV, battery %, counter, flags.
inline BleSensorFrame decodePvvxCustomService(const std::array<uint8_t, 6>& address, const uint8_t* s, std::size_t size) {
    BleSensorFrame r;
    if (!s || size != 15) { r.status = BleSensorFrameStatus::malformed; return r; }
    for (std::size_t i = 0; i < 6; ++i)
        if (s[i] != address[5 - i]) { r.status = BleSensorFrameStatus::malformed; return r; } // another device's report
    const auto le16 = [&](std::size_t at) { return uint16_t(s[at] | (s[at + 1] << 8)); };
    const int16_t temperature = static_cast<int16_t>(le16(6));
    const uint16_t humidity = le16(8);
    if (temperature < -4000 || temperature > 8500 || humidity > 10000 || s[12] > 100) { r.status = BleSensorFrameStatus::malformed; return r; }
    r.temperature = temperature; r.humidity = static_cast<int16_t>(humidity);
    r.battery = s[12]; r.packetId = s[13];
    r.status = BleSensorFrameStatus::decoded;
    return r;
}

template<class Decryptor>
BleSensorFrame decodeBoundPvvxAdvertisement(const std::array<uint8_t, 6>& address, const uint8_t* bytes, std::size_t size,
        const BleBindKey* key, bool requireEncryption, Decryptor& decryptor, BthomeWorkspace& workspace) {
    const auto opened = openBthomeV2(address, bytes, size, key, requireEncryption, decryptor, workspace);
    BleSensorFrame r;
    switch (opened.status) {
        case BthomeOpenStatus::opened:
            r = decodeBthomeThermometerService(opened.data, opened.size);
            if (r.status == BleSensorFrameStatus::decoded) { r.authenticated = opened.authenticated; r.encryptionCounter = opened.counter; }
            return r;
        case BthomeOpenStatus::not_present: break;
        case BthomeOpenStatus::key_required: r.status = BleSensorFrameStatus::key_required; return r;
        case BthomeOpenStatus::encryption_required: r.status = BleSensorFrameStatus::encryption_required; return r;
        case BthomeOpenStatus::authentication_failed: r.status = BleSensorFrameStatus::authentication_failed; return r;
        case BthomeOpenStatus::crypto_unavailable: r.status = BleSensorFrameStatus::crypto_unavailable; return r;
        default: r.status = BleSensorFrameStatus::malformed; return r;
    }
    // The custom format is never encrypted: not accepted when a bindkey is required.
    const auto custom = findBleServiceData(bytes, size, 0x181a);
    if (custom.status == BleServiceStatus::absent) return {};
    if (custom.status == BleServiceStatus::malformed) { r.status = BleSensorFrameStatus::malformed; return r; }
    if (requireEncryption) { r.status = BleSensorFrameStatus::encryption_required; return r; }
    return decodePvvxCustomService(address, custom.data, custom.size);
}
}
