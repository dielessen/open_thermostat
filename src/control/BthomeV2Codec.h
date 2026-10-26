#pragma once
#include "BleCcm.h"
#include "BleServiceData.h"
#include <optional>

namespace heating::control {
enum class BthomeOpenStatus { not_present, malformed, key_required, encryption_required,
    authentication_failed, crypto_unavailable, opened };
struct BthomeWorkspace {
    std::array<uint8_t, maximumBleCiphertextBytes + 1> plaintext{};
};
struct BthomeOpenedService {
    BthomeOpenStatus status = BthomeOpenStatus::not_present;
    const uint8_t* data = nullptr; // complete plaintext service, including device-info byte
    std::size_t size = 0;
    std::optional<uint32_t> counter;
    bool authenticated = false;
};

// BTHome v2: https://bthome.io/encryption/ . MAC is conventional display order;
// nonce = MAC || d2fc || original device-info || four little-endian counter bytes.
// No v1/Xiaomi AAD, implicit plaintext fallback or physical acquisition claim.
// Caller owns workspace and source bytes; do not retain this view past either.
template<class Decryptor>
BthomeOpenedService openBthomeV2(const std::array<uint8_t, 6>& address,
        const uint8_t* bytes, std::size_t size, const BleBindKey* key,
        bool requireEncryption, Decryptor& decryptor, BthomeWorkspace& workspace) {
    const auto failure = [&](BthomeOpenStatus status) {
        workspace.plaintext.fill(0);
        return BthomeOpenedService{status, nullptr, 0, std::nullopt, false};
    };
    const auto service = findBleServiceData(bytes, size, 0xfcd2);
    if (service.status == BleServiceStatus::malformed) return failure(BthomeOpenStatus::malformed);
    if (service.status == BleServiceStatus::absent) return failure(BthomeOpenStatus::not_present);
    if (service.size < 2) return failure(BthomeOpenStatus::malformed);
    const auto info = service.data[0];
    if ((info & 0xe0) != 0x40 || (info & 0x1a)) return failure(BthomeOpenStatus::malformed);
    if (!(info & 1)) {
        if (requireEncryption) return failure(BthomeOpenStatus::encryption_required);
        workspace.plaintext.fill(0);
        return {BthomeOpenStatus::opened, service.data, service.size, std::nullopt, false};
    }
    if (service.size < 11) return failure(BthomeOpenStatus::malformed);
    if (!key) return failure(BthomeOpenStatus::key_required);
    const auto ciphertextSize = service.size - 9;
    if (ciphertextSize > maximumBleCiphertextBytes) return failure(BthomeOpenStatus::malformed);
    std::array<uint8_t, 13> nonce{};
    for (std::size_t i = 0; i < 6; ++i) nonce[i] = address[i];
    nonce[6] = 0xd2; nonce[7] = 0xfc; nonce[8] = info;
    const auto counter = service.data + service.size - 8;
    for (std::size_t i = 0; i < 4; ++i) nonce[9 + i] = counter[i];
    workspace.plaintext.fill(0);
    BleCcmStatus result;
    try {
        result = decryptor.decrypt(*key, nonce.data(), nonce.size(), nullptr, 0,
            service.data + 1, ciphertextSize, service.data + service.size - 4,
            workspace.plaintext.data() + 1, maximumBleCiphertextBytes);
    } catch (...) { return failure(BthomeOpenStatus::crypto_unavailable); }
    if (result != BleCcmStatus::authenticated)
        return failure(result == BleCcmStatus::authentication_failed ? BthomeOpenStatus::authentication_failed
            : result == BleCcmStatus::invalid_argument ? BthomeOpenStatus::malformed : BthomeOpenStatus::crypto_unavailable);
    workspace.plaintext[0] = info & ~uint8_t(1);
    const uint32_t sequence = uint32_t(counter[0]) | (uint32_t(counter[1]) << 8)
        | (uint32_t(counter[2]) << 16) | (uint32_t(counter[3]) << 24);
    return {BthomeOpenStatus::opened, workspace.plaintext.data(), ciphertextSize + 1, sequence, true};
}
static_assert(sizeof(BthomeWorkspace) <= 256, "BTHome plaintext workspace budget changed");
}
