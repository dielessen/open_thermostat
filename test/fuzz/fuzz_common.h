#pragma once
// Shared helpers for the libFuzzer harnesses. Host-only test code: no radio,
// UART, network, NVS or device contact. See test/fuzz/README.md.
#include <logger/LoggerInterface.h>
#include <cstdarg>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <string_view>

namespace otfuzz {

// Consumes the fuzz input front to back; reads past the end return zeros.
struct Reader {
    const uint8_t* data;
    size_t size;
    size_t at = 0;
    Reader(const uint8_t* d, size_t n) : data(d), size(n) {}
    bool empty() const { return at >= size; }
    size_t left() const { return at < size ? size - at : 0; }
    uint8_t u8() { return at < size ? data[at++] : 0; }
    uint16_t u16() { const uint16_t lo = u8(); return static_cast<uint16_t>(lo | (u8() << 8)); }
    uint32_t u32() { const uint32_t lo = u16(); return lo | (uint32_t(u16()) << 16); }
    // Up to n bytes (fewer at the end of the input).
    std::string_view bytes(size_t n) {
        if (n > left()) n = left();
        std::string_view out(reinterpret_cast<const char*>(data + at), n);
        at += n;
        return out;
    }
    std::string_view rest() { return bytes(left()); }
};

// Logger that accepts every level and really formats each message, so a bad
// format argument (e.g. an unterminated %s buffer) is seen by ASan.
class FormattingLogger : public ib::logger::LoggerInterface {
public:
    void printf(LogLevel, const char* format, ...) const override {
        va_list args; va_start(args, format); format_(format, args); va_end(args);
    }
    void printf(LogLevel, LogFeatureType, const char* format, ...) const override {
        va_list args; va_start(args, format); format_(format, args); va_end(args);
    }
    bool doesMeetsLevelCondition(LogLevel) const override { return true; }
    bool doesFeatureMeetsLevelCondition(LogLevel, LogFeatureType) const override { return true; }
    LogLevel getMaxLogLevel() const override { return LogLevel::TRACE; }
    void setLogFeatures(LogFeature) override {}
    LogFeatureType addFeature(std::string, bool) override { return 1; }
    std::string getFeatureName(LogFeatureType) const override { return "fuzz"; }
    std::unordered_map<LogFeatureType, std::string> getRegisteredFeatures() const override { return {}; }
    bool isFeatureEnabled(LogFeatureType) const override { return true; }
    void enableFeature(LogFeatureType, bool) override {}
    void attachSink(std::shared_ptr<ib::logger::LoggerSinkInterface>) override {}
    mutable size_t total = 0;
private:
    void format_(const char* format, va_list args) const {
        char buffer[512];
        const int n = std::vsnprintf(buffer, sizeof(buffer), format, args);
        if (n > 0) total += static_cast<size_t>(n);
    }
};

// Harness invariant (logic bug, not a memory error): report and abort so the
// input is kept as a crash file.
[[noreturn]] inline void invariant(const char* what) {
    std::fprintf(stderr, "OTFUZZ INVARIANT FAILED: %s\n", what);
    std::abort();
}

}
