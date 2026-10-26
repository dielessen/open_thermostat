#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::control {
enum class BleServiceStatus { malformed, absent, present };
struct BleServiceData {
    BleServiceStatus status = BleServiceStatus::absent;
    const uint8_t* data = nullptr;
    std::size_t size = 0;
};

// Non-owning view, valid only while the caller's advertisement remains alive.
// Validate every AD element, including the suffix, before returning any data.
inline BleServiceData findBleServiceData(const uint8_t* bytes, std::size_t size, uint16_t uuid) {
    const auto invalid = [] { return BleServiceData{BleServiceStatus::malformed, nullptr, 0}; };
    if (!bytes || !size || size > 255) return invalid();
    BleServiceData result;
    for (std::size_t i = 0; i < size;) {
        const auto length = bytes[i++];
        if (!length) {
            while (i < size) if (bytes[i++]) return invalid();
            break;
        }
        if (length > size - i) return invalid();
        if (bytes[i] == 0x16) {
            if (length < 3) return invalid();
            if ((uint16_t(bytes[i + 1]) | (uint16_t(bytes[i + 2]) << 8)) == uuid) {
                if (result.status == BleServiceStatus::present) return invalid();
                result = {BleServiceStatus::present, bytes + i + 3, std::size_t(length - 3)};
            }
        }
        i += length;
    }
    return result;
}
}
