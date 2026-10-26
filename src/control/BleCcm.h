#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace heating::control {
using BleBindKey = std::array<uint8_t, 16>;
enum class BleCcmStatus { authenticated, authentication_failed, unavailable, invalid_argument };
inline constexpr std::size_t maximumBleCiphertextBytes = 242;
}
