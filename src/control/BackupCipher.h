#pragma once
// Passphrase sealing of the optional secrets in a settings backup, built only
// from SDK objects the E32 already links (docs/third-party/e32v2-link-review.json):
// PBKDF2-HMAC-SHA256 (md.c, pkcs5.c, as the web password in DeviceAccess.h)
// and AES-128-CCM (ccm.c, as the Bluetooth bindkeys in MbedTlsBleCcm.h).
// box = salt (16) || nonce (13) || ciphertext || tag (16). A wrong passphrase
// and a changed byte are the same authentication failure.
#include <mbedtls/ccm.h>
#include <mbedtls/md.h>
#include <mbedtls/pkcs5.h>
#include <mbedtls/version.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace heating::control::backup::cipher {
inline constexpr std::size_t saltBytes = 16, nonceBytes = 13, tagBytes = 16, keyBytes = 16;
inline constexpr char associated[] = "openthermostat-e32-backup/1";

template<class Bytes> inline void wipe(Bytes& b) {
    volatile uint8_t* p = reinterpret_cast<volatile uint8_t*>(&b[0]);
    for (std::size_t i = 0; i < b.size(); ++i) p[i] = 0;
}
inline bool deriveKey(std::string_view pass, const uint8_t* salt, uint32_t iterations, std::array<uint8_t, keyBytes>& key) {
    const auto* password = reinterpret_cast<const unsigned char*>(pass.data());
#if MBEDTLS_VERSION_MAJOR >= 3
    return mbedtls_pkcs5_pbkdf2_hmac_ext(MBEDTLS_MD_SHA256, password, pass.size(), salt, saltBytes,
                                         iterations, key.size(), key.data()) == 0;
#else
    mbedtls_md_context_t md; mbedtls_md_init(&md);
    const auto* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    const bool ok = info && mbedtls_md_setup(&md, info, 1) == 0
        && mbedtls_pkcs5_pbkdf2_hmac(&md, password, pass.size(), salt, saltBytes, iterations, key.size(), key.data()) == 0;
    mbedtls_md_free(&md);
    return ok;
#endif
}
// salt and nonce: fresh random bytes from the caller (DeviceAccess::randomBytes).
inline bool seal(std::string_view pass, std::string_view plain, const std::array<uint8_t, saltBytes>& salt,
                 const std::array<uint8_t, nonceBytes>& nonce, uint32_t iterations, std::string& box) {
    box.clear();
    if (pass.empty() || plain.empty()) return false;
    std::array<uint8_t, keyBytes> key{};
    if (!deriveKey(pass, salt.data(), iterations, key)) { wipe(key); return false; }
    box.assign(saltBytes + nonceBytes + plain.size() + tagBytes, '\0');
    auto* out = reinterpret_cast<unsigned char*>(&box[0]);
    std::copy(salt.begin(), salt.end(), out);
    std::copy(nonce.begin(), nonce.end(), out + saltBytes);
    mbedtls_ccm_context ccm; mbedtls_ccm_init(&ccm);
    const bool ok = mbedtls_ccm_setkey(&ccm, MBEDTLS_CIPHER_ID_AES, key.data(), keyBytes * 8) == 0
        && mbedtls_ccm_encrypt_and_tag(&ccm, plain.size(), nonce.data(), nonceBytes,
               reinterpret_cast<const unsigned char*>(associated), sizeof associated - 1,
               reinterpret_cast<const unsigned char*>(plain.data()), out + saltBytes + nonceBytes,
               out + saltBytes + nonceBytes + plain.size(), tagBytes) == 0;
    mbedtls_ccm_free(&ccm);
    wipe(key);
    if (!ok) box.clear();
    return ok;
}
inline bool open(std::string_view pass, std::string_view box, uint32_t iterations, std::string& plain) {
    plain.clear();
    if (pass.empty() || box.size() <= saltBytes + nonceBytes + tagBytes) return false;
    const auto* in = reinterpret_cast<const unsigned char*>(box.data());
    const std::size_t size = box.size() - saltBytes - nonceBytes - tagBytes;
    std::array<uint8_t, keyBytes> key{};
    if (!deriveKey(pass, in, iterations, key)) { wipe(key); return false; }
    plain.assign(size, '\0');
    mbedtls_ccm_context ccm; mbedtls_ccm_init(&ccm);
    const bool ok = mbedtls_ccm_setkey(&ccm, MBEDTLS_CIPHER_ID_AES, key.data(), keyBytes * 8) == 0
        && mbedtls_ccm_auth_decrypt(&ccm, size, in + saltBytes, nonceBytes,
               reinterpret_cast<const unsigned char*>(associated), sizeof associated - 1,
               in + saltBytes + nonceBytes, reinterpret_cast<unsigned char*>(&plain[0]),
               in + saltBytes + nonceBytes + size, tagBytes) == 0;
    mbedtls_ccm_free(&ccm);
    wipe(key);
    if (!ok) { wipe(plain); plain.clear(); }
    return ok;
}
}
