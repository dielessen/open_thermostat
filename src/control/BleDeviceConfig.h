#pragma once
#include "BleCcm.h"
#include "RoomDisplayNames.h"
#include <algorithm>
#include <array>
#include <string_view>

namespace heating::control {
using ManagedBleAddress = std::array<uint8_t, 6>;
enum class ManagedBleProfile : uint8_t { none = 0, shellyHtDisplay = 1, xiaomiMonitor3 = 2, shellyTrv = 3, pvvxThermometer = 4,
    last = pvvxThermometer }; // the stored-settings reader accepts 1..last
enum class ManagedBleEncryption : uint8_t { plain = 0, bthomeV2 = 1, miBeaconV4V5 = 2 };
inline void wipeBleKey(BleBindKey& key) noexcept {
    volatile uint8_t* out = key.data();
    for (std::size_t i = 0; i < key.size(); ++i) out[i] = 0;
}
struct ManagedBleBinding {
    ManagedBleAddress address{};
    ManagedBleProfile profile = ManagedBleProfile::none;
    ManagedBleEncryption encryption = ManagedBleEncryption::plain;
    BleBindKey key{};
    bool hasKey = false;
    std::array<char, 41> name{};
    ~ManagedBleBinding() { wipeBleKey(key); }
};
struct ManagedBleBindings {
    static constexpr std::size_t capacity = 8;
    std::array<ManagedBleBinding, capacity> devices{};
    uint8_t count = 0;
    void clear() noexcept {
        for (auto& device : devices) {
            wipeBleKey(device.key); device.hasKey = false;
            device.address.fill(0); device.name.fill(0);
            device.profile = ManagedBleProfile::none;
            device.encryption = ManagedBleEncryption::plain;
        }
        count = 0;
    }
    const ManagedBleBinding* find(const ManagedBleAddress& address) const noexcept {
        if (count > capacity) return nullptr;
        for (std::size_t i = 0; i < count; ++i)
            if (devices[i].address == address) return &devices[i];
        return nullptr;
    }
    bool same(const ManagedBleBindings& other) const noexcept {
        if (count > capacity || count != other.count) return false;
        uint8_t keyDifference = 0;
        for (std::size_t i = 0; i < count; ++i) {
            const auto& a = devices[i]; const auto& b = other.devices[i];
            if (a.address != b.address || a.profile != b.profile || a.encryption != b.encryption
                    || a.hasKey != b.hasKey || a.name != b.name) return false;
            for (std::size_t j = 0; j < a.key.size(); ++j) keyDifference |= a.key[j] ^ b.key[j];
        }
        return !keyDifference;
    }
    bool sort() {
        if (count > capacity) { clear(); return false; }
        std::sort(devices.begin(), devices.begin() + count,
            [](const auto& a, const auto& b) { return a.address < b.address; });
        return true;
    }
};
template<std::size_t N>
bool parseBleHex(std::string_view value, std::array<uint8_t, N>& out) noexcept {
    out.fill(0);
    if (value.size() != 2 * N) return false;
    const auto digit = [](char ch) -> int {
        return ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'a' && ch <= 'f' ? ch - 'a' + 10
            : ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
    };
    for (std::size_t i = 0; i < N; ++i) {
        const auto hi = digit(value[2 * i]), lo = digit(value[2 * i + 1]);
        if (hi < 0 || lo < 0) { out.fill(0); return false; }
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}
template<std::size_t N>
std::array<char, 2 * N + 1> printBleHex(const std::array<uint8_t, N>& value) noexcept {
    constexpr char digits[] = "0123456789abcdef";
    std::array<char, 2 * N + 1> out{};
    for (std::size_t i = 0; i < N; ++i) { out[2*i] = digits[value[i] >> 4]; out[2*i+1] = digits[value[i] & 15]; }
    return out;
}
inline bool parseManagedBleAddress(std::string_view value, ManagedBleAddress& out) noexcept {
    out.fill(0);
    std::array<char, 12> compact{};
    if (value.size() == 17) {
        for (std::size_t i = 0; i < 6; ++i) {
            if (i && value[3*i-1] != ':') return false;
            compact[2*i] = value[3*i]; compact[2*i+1] = value[3*i+1];
        }
        value = {compact.data(), compact.size()};
    }
    if (!parseBleHex(value, out)) return false;
    if (!std::any_of(out.begin(), out.end(), [](auto b){return b != 0;})
            || !std::any_of(out.begin(), out.end(), [](auto b){return b != 255;})) {
        out.fill(0); return false;
    }
    return true;
}
inline bool validManagedBleName(std::string_view value) noexcept {
    if (value.empty()) return true;
    if (value.size() > 40) return false;
    constexpr char digits[] = "0123456789abcdef";
    std::array<char, 80> encoded{};
    for (std::size_t i = 0; i < value.size(); ++i) {
        const auto byte = static_cast<uint8_t>(value[i]);
        encoded[2*i] = digits[byte >> 4]; encoded[2*i+1] = digits[byte & 15];
    }
    return validRoomDisplayNameHex({encoded.data(), 2*value.size()});
}
inline const char* managedBleProfileName(ManagedBleProfile profile) noexcept {
    switch(profile){case ManagedBleProfile::shellyHtDisplay:return "shelly_ht_display";
        case ManagedBleProfile::xiaomiMonitor3:return "xiaomi_monitor_3";
        case ManagedBleProfile::shellyTrv:return "shelly_blu_trv";
        case ManagedBleProfile::pvvxThermometer:return "pvvx_thermometer";default:return nullptr;}
}
inline const char* managedBleEncryptionName(ManagedBleEncryption encryption) noexcept {
    switch(encryption){case ManagedBleEncryption::plain:return "none";
        case ManagedBleEncryption::bthomeV2:return "bthome_v2";
        case ManagedBleEncryption::miBeaconV4V5:return "mibeacon_v4_v5";default:return nullptr;}
}
inline bool validManagedBleProfileEncryption(ManagedBleProfile profile,ManagedBleEncryption encryption) noexcept {
    return ((profile==ManagedBleProfile::shellyHtDisplay||profile==ManagedBleProfile::shellyTrv||profile==ManagedBleProfile::pvvxThermometer)
        && (encryption==ManagedBleEncryption::plain||encryption==ManagedBleEncryption::bthomeV2))
        || (profile==ManagedBleProfile::xiaomiMonitor3&&encryption==ManagedBleEncryption::miBeaconV4V5);
}
inline bool validManagedBleBinding(const ManagedBleBinding& value) noexcept {
    const auto end = std::find(value.name.begin(), value.name.end(), '\0');
    return validManagedBleProfileEncryption(value.profile,value.encryption)
        && !(value.encryption == ManagedBleEncryption::plain && value.hasKey)
        && (value.hasKey||std::all_of(value.key.begin(),value.key.end(),[](auto b){return b==0;}))
        && std::any_of(value.address.begin(), value.address.end(), [](auto b) { return b != 0; })
        && std::any_of(value.address.begin(), value.address.end(), [](auto b) { return b != 255; })
        && end != value.name.end()
        && validManagedBleName({value.name.data(), static_cast<std::size_t>(end - value.name.begin())});
}
static_assert(sizeof(ManagedBleBindings) <= 768, "BLE binding resident budget changed");
}
