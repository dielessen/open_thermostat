// Boiler services fuzzer: the authenticated web APIs that drive EMS writes
// (BoilerTestService actions, ClassicBoilerSettingsService settings requests,
// ClassicConfigurationRead configuration/identity reads), the UART replies they
// consume, and the session cookie / If-Match parsing in front of them.
//
// Input: text lines.
//   a <action> <body>   BoilerTestService::action (prepare, prepare_zero, start, ...)
//   s <body>            ClassicBoilerSettingsService::request
//   c <body> / i <body> ClassicConfigurationRead::request (configuration / identity)
//   e <hex>             a received EMS frame incl. CRC (monitor + replies + observe)
//   n                   BoilerTestService::next + transmit; settings/config poll
//   t <ms>              advance the clock and tick everything
//   k <header>          Cookie header -> session token; o = other operator
//   m <header>          If-Match header against the Bluetooth settings fence
#include "fuzz_common.h"
#include "EMS/BoilerTestService.h"
#include "EMS/ClassicBoilerSettingsService.h"
#include "EMS/ClassicConfigurationRead.h"
#include "BoilerTestIoFixture.h"
#include <sstream>
#include <string>

namespace {
using namespace heating::ems;
using heating::control::WebAuthSession;

std::string unhex(std::string_view s) {
    std::string out;
    const auto digit = [](char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; };
    for (std::size_t i = 0; i + 1 < s.size() && out.size() < 64; i += 2) {
        const int hi = digit(s[i]), lo = digit(s[i + 1]);
        if (hi < 0 || lo < 0) break;
        out.push_back(static_cast<char>(hi * 16 + lo));
    }
    return out;
}

struct Harness {
    BoilerTestSession::Profile profile{true, 20, 60, 10000, 3000, 2000, 5000, 100};
    BoilerTestSession::Gates gates{true, true, true, true, true};
    ClassicBoilerMonitor monitor;
    BoilerTestService test{42, true, profile, true, true};
    ClassicBoilerSettingsService settings{42, true};
    ClassicConfigurationRead read{42, true};
    WebAuthSession sessions;
    std::string owner = std::string(64, 'a'), other = std::string(64, 'b');
    std::string current = owner;
    uint64_t now = 100;
    Harness() {
        (void)sessions.issue(owner, std::string(64, 'c'), now);
        (void)sessions.issue(other, std::string(64, 'd'), now);
        (void)sessions.settingsReadback(owner, std::string(64, 'e'), std::string(64, 'f'), now, WebAuthSession::SettingsScope::bluetooth);
    }
    uint64_t us() const { return now * 1000; }
    void line(std::string_view l) {
        if (l.empty()) return;
        const char op = l[0];
        const auto arg = l.size() > 2 ? l.substr(2) : std::string_view{};
        const auto clock = [this] { return us(); };
        const auto gate = [this](std::string_view) { return true; };
        switch (op) {
            case 'a': {
                const auto space = arg.find(' ');
                const auto action = arg.substr(0, space);
                const auto body = space == std::string_view::npos ? std::string_view{} : arg.substr(space + 1);
                (void)test.action(action, body, current, now, gates, monitor);
                break;
            }
            case 's': (void)settings.request(arg, current, now, true); settings.synchronizeSessions(sessions, now); break;
            case 'c': case 'i':
                (void)read.request(arg, current, now, true, false, sessions,
                    op == 'i' ? ClassicConfigurationRead::Kind::identity : ClassicConfigurationRead::Kind::configuration,
                    [](uint8_t address) { return address == 0x10 || address == 0x17; });
                read.synchronizeSessions(sessions, now);
                break;
            case 'e': {
                const auto raw = unhex(arg);
                const auto* bytes = reinterpret_cast<const uint8_t*>(raw.data());
                settings.receive(bytes, raw.size(), us(), clock, gate,
                    [] { ManualClassicUartWrite::Result r; r.writeCompleted = true; return r; });
                try {
                    const auto telegram = EmsTelegram::fromRawData(bytes, raw.size());
                    monitor.receive(telegram, now);
                    read.observe(telegram, now, now, true, monitor);
                } catch (const std::exception&) {}
                break;
            }
            case 'n': {
                const auto intent = test.next(now, gates, monitor);
                if (intent.command != BoilerTestSession::Command::none)
                    (void)testing_detail::instantTransmission(test, intent, now, true, gates, monitor);
                (void)settings.poll(clock, gate, [](const EmsRawFrame&, auto, int, bool) {
                    ManualClassicUartWrite::Result r; r.writeCompleted = true; return r; });
                (void)read.poll([this] { return now; }, [] { return true; }, [](const EmsRawFrame&) { return true; });
                break;
            }
            case 't': {
                uint64_t v = 0; for (char c : arg) { if (c < '0' || c > '9') break; v = v * 10 + uint64_t(c - '0'); if (v > 100000000) break; }
                now += v;
                test.tick(now, gates, monitor);
                settings.tick(clock, gate);
                read.tick(now, true);
                break;
            }
            case 'k': {
                const auto token = WebAuthSession::cookieToken(arg);
                if (!token.empty() && !WebAuthSession::hexToken(token)) otfuzz::invariant("cookie token not a hex token");
                (void)sessions.find(token, now);
                (void)sessions.csrf(token, arg, now);
                current = token.empty() ? std::string(arg.substr(0, 80)) : std::string(token);
                break;
            }
            case 'o': current = other; break;
            case 'm': (void)sessions.settingsReadbackMatches(owner, arg, std::string(64, 'e'), now, WebAuthSession::SettingsScope::bluetooth); break;
            default: break;
        }
        std::ostringstream out;
        test.writeJSON(out, now, current, gates, monitor);
        test.writeCommandJSON(out, now);
        settings.writeJSON(out, now, true, current);
        read.writeJSON(out, now, true, false);
    }
};
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    Harness h;
    const std::string_view all(reinterpret_cast<const char*>(data), size);
    std::size_t at = 0;
    for (unsigned lines = 0; at < all.size() && lines < 128; ++lines) {
        auto end = all.find('\n', at);
        if (end == std::string_view::npos) end = all.size();
        h.line(all.substr(at, end - at));
        at = end + 1;
    }
    return 0;
}
