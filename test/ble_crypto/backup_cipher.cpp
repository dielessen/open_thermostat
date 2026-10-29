// Real Mbed TLS for the sealed secrets of a settings backup (control/BackupCipher.h),
// checked against an independent Python vector (hashlib PBKDF2 + cryptography
// AESCCM). Fixture passphrase and plaintext only; no device contact.
#include "control/BackupCipher.h"
#include <gtest/gtest.h>
#include <string>

namespace {
using namespace heating::control::backup;
std::string hex(const std::string& bytes) {
    static constexpr char d[] = "0123456789abcdef";
    std::string out;
    for (unsigned char c : bytes) { out += d[c >> 4]; out += d[c & 15]; }
    return out;
}
std::string unhex(const std::string& text) {
    std::string out;
    for (std::size_t i = 0; i < text.size(); i += 2) out += static_cast<char>(std::stoul(text.substr(i, 2), nullptr, 16));
    return out;
}
constexpr auto passphrase = "correct horse battery";
constexpr auto plain = R"({"mqtt_password":"fixture"})";
// python: salt=bytes(range(16)); nonce=bytes(range(0xa0,0xad));
// key=hashlib.pbkdf2_hmac("sha256",pass,salt,4096,16); AESCCM(key,16).encrypt(nonce,plain,b"openthermostat-e32-backup/1")
constexpr auto vector = "000102030405060708090a0b0c0d0e0fa0a1a2a3a4a5a6a7a8a9aaabac"
                        "c7ab9059df72dc65cb153a5162b268ecd6a365f68cc8bee7ddf2b83a92e029eed334ccb36a7b4c0384f752";
std::array<uint8_t, cipher::saltBytes> salt() { std::array<uint8_t, cipher::saltBytes> s{}; for (std::size_t i = 0; i < s.size(); ++i) s[i] = uint8_t(i); return s; }
std::array<uint8_t, cipher::nonceBytes> nonce() { std::array<uint8_t, cipher::nonceBytes> n{}; for (std::size_t i = 0; i < n.size(); ++i) n[i] = uint8_t(0xa0 + i); return n; }
}

TEST(BackupCipher, SealMatchesTheIndependentVector) {
    std::string box;
    ASSERT_TRUE(cipher::seal(passphrase, plain, salt(), nonce(), 4096, box));
    EXPECT_EQ(hex(box), vector);
}

TEST(BackupCipher, OpenRecoversThePlaintext) {
    std::string out;
    ASSERT_TRUE(cipher::open(passphrase, unhex(vector), 4096, out));
    EXPECT_EQ(out, plain);
}

TEST(BackupCipher, WrongPassphraseOrChangedByteIsRefused) {
    const auto box = unhex(vector);
    std::string out = "stale";
    EXPECT_FALSE(cipher::open("correct horse battery!", box, 4096, out));
    EXPECT_TRUE(out.empty());
    for (std::size_t i = 0; i < box.size(); ++i) {
        auto changed = box; changed[i] = static_cast<char>(changed[i] ^ 1);
        EXPECT_FALSE(cipher::open(passphrase, changed, 4096, out)) << i;
    }
    EXPECT_FALSE(cipher::open(passphrase, box.substr(0, box.size() - 1), 4096, out));
    EXPECT_FALSE(cipher::open(passphrase, box.substr(0, cipher::saltBytes + cipher::nonceBytes + cipher::tagBytes), 4096, out));
    EXPECT_FALSE(cipher::open(passphrase, box, 4095, out));
    EXPECT_FALSE(cipher::open("", box, 4096, out));
}

TEST(BackupCipher, EmptyInputsAreNotSealed) {
    std::string box;
    EXPECT_FALSE(cipher::seal("", plain, salt(), nonce(), 4096, box));
    EXPECT_FALSE(cipher::seal(passphrase, "", salt(), nonce(), 4096, box));
    EXPECT_TRUE(box.empty());
}
