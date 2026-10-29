#pragma once
#include "control/BoundedJson.h"
#include <cJSON.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>

namespace heating::control {
// Web sign-in password policy, pure for host tests. The E32 stores only a
// salted PBKDF2-HMAC-SHA256 record (DeviceAccess, NVS "ot_access"/"web_pw");
// without a record the factory password "admin" applies, so existing installs
// and Home Assistant keep working until the owner sets a password.
struct WebPassword {
    static constexpr std::string_view factoryDefault = "admin";
    static constexpr std::size_t minimumCharacters = 8, maximumCharacters = 64;
    // UTF-8: at most 4 bytes per character. Also the sign-in form's limit.
    static constexpr std::size_t maximumBytes = maximumCharacters * 4;
    static constexpr uint32_t iterations = 4096;
    static constexpr uint32_t minimumIterations = 1000, maximumIterations = 200000;
    static constexpr std::size_t saltBytes = 16, hashBytes = 32;
    static constexpr std::size_t recordBytes = 4 + 1 + 4 + saltBytes + hashBytes;
    // password, salt, iterations -> 32 output bytes; false on a crypto failure.
    using Kdf = bool (*)(std::string_view, const uint8_t*, std::size_t, uint32_t, uint8_t*);

    struct Record {
        uint32_t iterations = WebPassword::iterations;
        std::array<uint8_t, saltBytes> salt{};
        std::array<uint8_t, hashBytes> hash{};
    };
    enum class Length : uint8_t { ok, tooShort, tooLong };
    // Characters, not bytes: "Zoë" counts 3. UTF-8 continuation bytes are skipped.
    static std::size_t characters(std::string_view text) {
        std::size_t count = 0;
        for (unsigned char c : text) if ((c & 0xC0) != 0x80) ++count;
        return count;
    }
    static Length checkNew(std::string_view password) {
        if (password.size() > maximumBytes || characters(password) > maximumCharacters) return Length::tooLong;
        if (characters(password) < minimumCharacters) return Length::tooShort;
        return Length::ok;
    }
    static bool derive(Record& record, std::string_view password, Kdf kdf) {
        return kdf && kdf(password, record.salt.data(), record.salt.size(), record.iterations, record.hash.data());
    }
    // Constant time over the 32 bytes; a KDF failure never verifies.
    static bool verify(const Record& record, std::string_view password, Kdf kdf) {
        Record candidate = record;
        if (!derive(candidate, password, kdf)) return false;
        uint8_t difference = 0;
        for (std::size_t i = 0; i < hashBytes; ++i) difference |= candidate.hash[i] ^ record.hash[i];
        return difference == 0;
    }
    // Blob: "OTPW", version 1, iterations (little endian), salt, hash.
    static std::array<uint8_t, recordBytes> encode(const Record& r) {
        std::array<uint8_t, recordBytes> out{'O', 'T', 'P', 'W', 1};
        for (int i = 0; i < 4; ++i) out[5 + i] = static_cast<uint8_t>(r.iterations >> (8 * i));
        std::memcpy(out.data() + 9, r.salt.data(), saltBytes);
        std::memcpy(out.data() + 9 + saltBytes, r.hash.data(), hashBytes);
        return out;
    }
    static bool decode(const uint8_t* data, std::size_t size, Record& out) {
        if (!data || size != recordBytes || std::memcmp(data, "OTPW\x01", 5)) return false;
        Record r;
        r.iterations = 0;
        for (int i = 0; i < 4; ++i) r.iterations |= uint32_t(data[5 + i]) << (8 * i);
        if (r.iterations < minimumIterations || r.iterations > maximumIterations) return false;
        std::memcpy(r.salt.data(), data + 9, saltBytes);
        std::memcpy(r.hash.data(), data + 9 + saltBytes, hashBytes);
        out = r;
        return true;
    }

    // POST /auth/password body: exactly {"current":"…","new":"…"}.
    enum class RequestError : uint8_t { none, invalid, tooShort, tooLong };
    struct Change { std::string current, next; RequestError error = RequestError::invalid; };
    static Change parseChange(const char* body, std::size_t size) {
        Change change;
        if (!body || !size || size > 2048) return change;
        // cJSON strings end at NUL; refuse an escaped NUL instead of truncating.
        if (std::string_view(body, size).find("\\u0000") != std::string_view::npos) return change;
        // body[size] is the terminating NUL (String/std::string c_str()). One flat document.
        const auto root = parseNestedJson(body, size, true, 1);
        if (!root) return change;
        const cJSON* current = cJSON_GetObjectItemCaseSensitive(root.get(), "current");
        const cJSON* next = cJSON_GetObjectItemCaseSensitive(root.get(), "new");
        const bool shape = cJSON_IsObject(root.get()) && cJSON_GetArraySize(root.get()) == 2 && cJSON_IsString(current)
            && cJSON_IsString(next) && current->valuestring && next->valuestring;
        if (shape) {
            change.current = current->valuestring; change.next = next->valuestring;
            const auto length = checkNew(change.next);
            change.error = change.current.size() > maximumBytes ? RequestError::invalid
                : length == Length::tooShort ? RequestError::tooShort
                : length == Length::tooLong ? RequestError::tooLong : RequestError::none;
        }
        return change;
    }
    static const char* errorBody(RequestError e) {
        switch (e) {
            case RequestError::tooShort: return "{\"error\":\"password_too_short\"}";
            case RequestError::tooLong: return "{\"error\":\"password_too_long\"}";
            default: return "{\"error\":\"invalid_password_request\"}";
        }
    }
};
}
