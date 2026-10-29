#include "control/WebPassword.h"
#include "control/WebAuthSession.h"
#include <gtest/gtest.h>
#include <dlfcn.h>
#include <stdexcept>
#include <string>
using namespace heating::control;

namespace {
// Test-only public OpenSSL3 PBKDF2 ABI (already on the build host, as in
// ControlTestHash.h): the firmware uses SDK mbedTLS with the same parameters.
bool opensslPbkdf2(std::string_view password, const uint8_t* salt, std::size_t saltSize, uint32_t iterations, uint8_t* out) {
    using Md = const void* (*)();
    using Fn = int (*)(const char*, int, const unsigned char*, int, int, const void*, int, unsigned char*);
    static void* library = dlopen("libcrypto.so.3", RTLD_NOW | RTLD_LOCAL);
    static Md sha256 = library ? reinterpret_cast<Md>(dlsym(library, "EVP_sha256")) : nullptr;
    static Fn kdf = library ? reinterpret_cast<Fn>(dlsym(library, "PKCS5_PBKDF2_HMAC")) : nullptr;
    if (!sha256 || !kdf) throw std::runtime_error("Native tests require existing OpenSSL3 libcrypto");
    return kdf(password.data(), int(password.size()), salt, int(saltSize), int(iterations), sha256(), 32, out) == 1;
}
bool failingKdf(std::string_view, const uint8_t*, std::size_t, uint32_t, uint8_t*) { return false; }
std::string hex(const uint8_t* bytes, std::size_t size) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out;
    for (std::size_t i = 0; i < size; ++i) { out += digits[bytes[i] >> 4]; out += digits[bytes[i] & 15]; }
    return out;
}
WebPassword::Record record(std::string_view password, uint32_t iterations = 1000) {
    WebPassword::Record r; r.iterations = iterations;
    for (std::size_t i = 0; i < r.salt.size(); ++i) r.salt[i] = static_cast<uint8_t>("0123456789abcdef"[i]);
    EXPECT_TRUE(WebPassword::derive(r, password, opensslPbkdf2));
    return r;
}
std::string token(char c) { return std::string(64, c); }
}

TEST(WebPassword, DerivesStandardPbkdf2HmacSha256) {
    // Python: hashlib.pbkdf2_hmac('sha256', b'admin', b'0123456789abcdef', 1000).hex()
    const auto r = record("admin");
    EXPECT_EQ(hex(r.hash.data(), r.hash.size()), "68d9fc050af96922491c721b533d14426508dd3bedd472fe70e5f8be686dfeae");
}
TEST(WebPassword, VerifiesOnlyTheExactPassword) {
    const auto r = record("correct horse");
    EXPECT_TRUE(WebPassword::verify(r, "correct horse", opensslPbkdf2));
    for (const char* wrong : {"correct hors", "correct horse ", "Correct horse", "", "admin"})
        EXPECT_FALSE(WebPassword::verify(r, wrong, opensslPbkdf2)) << wrong;
    EXPECT_FALSE(WebPassword::verify(r, "correct horse", failingKdf));
    EXPECT_FALSE(WebPassword::verify(r, "correct horse", nullptr));
    // Another salt gives another hash for the same password.
    auto salted = r; salted.salt[0] ^= 1;
    ASSERT_TRUE(WebPassword::derive(salted, "correct horse", opensslPbkdf2));
    EXPECT_NE(salted.hash, r.hash);
}
TEST(WebPassword, RecordRoundTripsAndRejectsDamage) {
    const auto r = record("correct horse", WebPassword::iterations);
    const auto blob = WebPassword::encode(r);
    ASSERT_EQ(blob.size(), 57u);
    EXPECT_EQ(std::string(blob.begin(), blob.begin() + 5), std::string("OTPW\x01", 5));
    WebPassword::Record back;
    ASSERT_TRUE(WebPassword::decode(blob.data(), blob.size(), back));
    EXPECT_EQ(back.iterations, WebPassword::iterations);
    EXPECT_TRUE(WebPassword::verify(back, "correct horse", opensslPbkdf2));
    EXPECT_FALSE(WebPassword::decode(blob.data(), blob.size() - 1, back));
    EXPECT_FALSE(WebPassword::decode(nullptr, blob.size(), back));
    auto version = blob; version[4] = 2;
    EXPECT_FALSE(WebPassword::decode(version.data(), version.size(), back));
    // A damaged iteration count can neither skip the KDF nor stall the E32.
    for (uint32_t iterations : {0u, 999u, 200001u, 0xffffffffu}) {
        auto damaged = r; damaged.iterations = iterations;
        const auto bytes = WebPassword::encode(damaged);
        EXPECT_FALSE(WebPassword::decode(bytes.data(), bytes.size(), back)) << iterations;
    }
}
TEST(WebPassword, NewPasswordLengthCountsCharacters) {
    EXPECT_EQ(WebPassword::checkNew("1234567"), WebPassword::Length::tooShort);
    EXPECT_EQ(WebPassword::checkNew(""), WebPassword::Length::tooShort);
    EXPECT_EQ(WebPassword::checkNew("12345678"), WebPassword::Length::ok);
    EXPECT_EQ(WebPassword::checkNew(std::string(64, 'x')), WebPassword::Length::ok);
    EXPECT_EQ(WebPassword::checkNew(std::string(65, 'x')), WebPassword::Length::tooLong);
    std::string accents; for (int i = 0; i < 7; ++i) accents += "\xc3\xa9"; // 7 characters, 14 bytes
    EXPECT_EQ(WebPassword::checkNew(accents), WebPassword::Length::tooShort);
    accents.clear(); for (int i = 0; i < 64; ++i) accents += "\xf0\x9f\x94\x92"; // 64 emoji, 256 bytes
    EXPECT_EQ(WebPassword::checkNew(accents), WebPassword::Length::ok);
    EXPECT_EQ(WebPassword::checkNew(accents + "x"), WebPassword::Length::tooLong);
    EXPECT_EQ(WebPassword::checkNew(std::string(257, '\x80')), WebPassword::Length::tooLong); // bytes bound too
}
TEST(WebPassword, ChangeRequestShapeAndErrorBodies) {
    const auto parse = [](const std::string& body) { return WebPassword::parseChange(body.data(), body.size()); };
    const auto ok = parse(R"({"current":"admin","new":"correct horse"})");
    EXPECT_EQ(ok.error, WebPassword::RequestError::none);
    EXPECT_EQ(ok.current, "admin"); EXPECT_EQ(ok.next, "correct horse");
    EXPECT_EQ(parse(R"({"new":"correct horse","current":"admin"})").error, WebPassword::RequestError::none);
    EXPECT_EQ(parse(R"({"current":"admin","new":"short"})").error, WebPassword::RequestError::tooShort);
    EXPECT_EQ(parse("{\"current\":\"admin\",\"new\":\"" + std::string(65, 'x') + "\"}").error, WebPassword::RequestError::tooLong);
    EXPECT_EQ(parse(R"({"current":"admin","new":"café latte"})").next, "caf\xc3\xa9 latte");
    for (const std::string bad : {std::string(), std::string("{}"), std::string("null"), std::string(R"(["admin","correct horse"])"),
             std::string(R"({"current":"admin"})"), std::string(R"({"current":1,"new":"correct horse"})"),
             std::string(R"({"current":"admin","new":"correct horse","extra":true})"),
             std::string(R"({"current":"admin","current":"admin","new":"correct horse"})"),
             std::string(R"({"current":"admin","new":"correct\u0000horse"})"),
             std::string(R"({"current":"admin","new":"correct horse"}x)"),
             "{\"current\":\"" + std::string(257, 'x') + "\",\"new\":\"correct horse\"}",
             std::string(2049, ' ')})
        EXPECT_EQ(parse(bad).error, WebPassword::RequestError::invalid) << bad.substr(0, 80);
    EXPECT_STREQ(WebPassword::errorBody(WebPassword::RequestError::tooShort), R"({"error":"password_too_short"})");
    EXPECT_STREQ(WebPassword::errorBody(WebPassword::RequestError::tooLong), R"({"error":"password_too_long"})");
    EXPECT_STREQ(WebPassword::errorBody(WebPassword::RequestError::invalid), R"({"error":"invalid_password_request"})");
}
TEST(WebPassword, ChangeKeepsOnlyTheCallersSession) {
    WebAuthSession s;
    for (char c : {'a', 'c', 'e', 'g'}) ASSERT_NE(s.issue(token(c), token(char(c + 1)), 100), nullptr);
    s.revokeOthers(token('c'));
    EXPECT_NE(s.find(token('c'), 200), nullptr);
    EXPECT_TRUE(s.csrf(token('c'), token('d'), 200));
    for (char c : {'a', 'e', 'g'}) EXPECT_EQ(s.find(token(c), 200), nullptr);
    // Freed slots admit the other browsers and Home Assistant again.
    EXPECT_NE(s.issue(token('a'), token('b'), 300), nullptr);
    // An invalid caller token keeps nothing.
    s.revokeOthers("");
    EXPECT_EQ(s.find(token('a'), 301), nullptr);
    EXPECT_EQ(s.find(token('c'), 301), nullptr);
}
TEST(WebPassword, SharesTheSignInFailureLimit) {
    WebAuthSession s;
    for (int i = 0; i < 5; ++i) { EXPECT_TRUE(s.loginAllowed(1000)); s.loginFailed(1000); }
    EXPECT_FALSE(s.loginAllowed(1000));
    EXPECT_FALSE(s.loginAllowed(30999));
    EXPECT_TRUE(s.loginAllowed(31000));
}
