#pragma once
#include "BleCcm.h"
#include <mbedtls/ccm.h>
#include <algorithm>

namespace heating::control {
// One loop-owned context. No SDK callback, timer, connection or key persistence.
// Keep this object in the bounded observer rather than on the callback stack.
class MbedTlsBleCcm {
public:
    MbedTlsBleCcm() noexcept { mbedtls_ccm_init(&context_); }
    ~MbedTlsBleCcm() { mbedtls_ccm_free(&context_); }
    MbedTlsBleCcm(const MbedTlsBleCcm&) = delete;
    MbedTlsBleCcm& operator=(const MbedTlsBleCcm&) = delete;
    void clear() noexcept {
        mbedtls_ccm_free(&context_);
        mbedtls_ccm_init(&context_);
    }
    BleCcmStatus decrypt(const BleBindKey& key, const uint8_t* nonce, std::size_t nonceSize,
            const uint8_t* aad, std::size_t aadSize, const uint8_t* ciphertext,
            std::size_t size, const uint8_t* mic, uint8_t* plaintext, std::size_t capacity) noexcept {
        if (!nonce || (nonceSize != 12 && nonceSize != 13) || aadSize > 1 || (aadSize && !aad)
                || !ciphertext || !size || size > maximumBleCiphertextBytes || !mic
                || !plaintext || capacity < size) return BleCcmStatus::invalid_argument;
        std::fill_n(plaintext, size, uint8_t(0));
        auto result = mbedtls_ccm_setkey(&context_, MBEDTLS_CIPHER_ID_AES, key.data(), 128);
        if (result) { clear(); return BleCcmStatus::unavailable; }
        result = mbedtls_ccm_auth_decrypt(&context_, size, nonce, nonceSize, aad, aadSize,
            ciphertext, plaintext, mic, 4);
        if (!result) { clear(); return BleCcmStatus::authenticated; }
        std::fill_n(plaintext, size, uint8_t(0));
        clear();
        return result == MBEDTLS_ERR_CCM_AUTH_FAILED ? BleCcmStatus::authentication_failed
            : BleCcmStatus::unavailable;
    }
private:
    mbedtls_ccm_context context_{};
};
static_assert(sizeof(MbedTlsBleCcm) <= 256, "BLE CCM context budget changed");
}
