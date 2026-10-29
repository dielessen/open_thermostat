// ShadowController fuzzer: the MQTT ha/* messages Home Assistant sends to the
// E32 (open_session, heartbeat, config, snapshot_request, observations,
// user_command, capabilities), with ticks, reconnects and a reboot that reloads
// the stored configuration. Every publication must be valid JSON.
//
// Input: text lines.
//   r <topic> <payload>   receive (placeholders below are substituted)
//   t <ms>                tick after <ms>          z <ms>  tick, clock invalid
//   c / d                 broker connected / disconnected
//   b                     reboot: new controller over the same store
// Placeholders (from the latest fw/hello and fw/session publication):
//   $C challenge_id  $S adapter_session_id  $G grant_id  $Q grant_sequence
//   $E epoch  $R config_revision  $D config_digest  $B boot id  $H hash
// The hash is a constant 64-hex value, so digests never block the fuzzer;
// SHA-256 itself is not under test here.
#include "fuzz_common.h"
#include "control/ShadowController.h"
#include <map>
#include <string>

namespace {
using namespace heating::control;
const std::string constantHash(64, '0');

struct Store : ControlStore {
    std::string bytes;
    bool load(std::string& out) override { out = bytes; return true; }
    bool save(std::string_view value) override { bytes = value; return true; }
};

struct Harness {
    Store store;
    std::unique_ptr<ShadowController> core;
    std::map<std::string, std::string> vars{{"$C", ""}, {"$S", ""}, {"$G", ""}, {"$Q", "1"}, {"$E", "1"},
                                            {"$R", "0"}, {"$D", ""}, {"$B", "boot1"}, {"$H", constantHash}};
    uint64_t now = 1000;
    unsigned nonce = 0, boots = 1, publications = 0;
    void start() {
        vars["$B"] = "boot" + std::to_string(boots);
        core = std::make_unique<ShadowController>("e32_lab", vars["$B"], "ha1", store,
            [](std::string_view) { return constantHash; },
            [this] { return "nonce" + std::to_string(++nonce); },
            [this](std::string_view topic, std::string_view bytes) { published(topic, bytes); });
    }
    void published(std::string_view topic, std::string_view bytes) {
        ++publications;
        const std::string text(bytes);
        if (std::getenv("OTFUZZ_VERBOSE")) std::fprintf(stderr, "PUB %.*s %s\n", int(topic.size()), topic.data(), text.c_str());
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(text.c_str()), cJSON_Delete);
        if (!root) otfuzz::invariant("ShadowController published invalid JSON");
        const auto str = [&](const char* key, const char* var) {
            const auto* v = cJSON_GetObjectItemCaseSensitive(root.get(), key);
            if (cJSON_IsString(v)) vars[var] = v->valuestring;
            else if (cJSON_IsNumber(v)) vars[var] = std::to_string(static_cast<unsigned long long>(v->valuedouble));
        };
        if (topic == "fw/hello") { str("challenge_id", "$C"); str("epoch", "$E"); str("config_revision", "$R"); str("config_digest", "$D"); }
        if (topic == "fw/session") { str("adapter_session_id", "$S"); str("grant_id", "$G"); str("grant_sequence", "$Q"); }
    }
    std::string substitute(std::string_view in) const {
        std::string out; out.reserve(in.size());
        for (std::size_t i = 0; i < in.size(); ++i) {
            if (in[i] == '$' && i + 1 < in.size()) {
                const auto found = vars.find(std::string(in.substr(i, 2)));
                if (found != vars.end()) { out += found->second; ++i; continue; }
            }
            out += in[i];
        }
        return out;
    }
    static uint64_t number(std::string_view s) {
        uint64_t v = 0;
        for (char c : s) { if (c < '0' || c > '9') break; v = v * 10 + uint64_t(c - '0'); if (v > 100000000) break; }
        return v;
    }
    void line(std::string_view l) {
        if (l.empty()) return;
        const char op = l[0];
        const auto arg = l.size() > 2 ? l.substr(2) : std::string_view{};
        switch (op) {
            case 'r': {
                const auto space = arg.find(' ');
                const auto topic = arg.substr(0, space);
                const auto payload = space == std::string_view::npos ? std::string_view{} : arg.substr(space + 1);
                core->receive(topic, substitute(payload), now, 1792368000 + int64_t(now / 1000), true);
                break;
            }
            case 't': now += number(arg); core->tick(now, 1792368000 + int64_t(now / 1000), true); break;
            case 'z': now += number(arg); core->tick(now, 0, false); break;
            case 'c': core->connected(now); break;
            case 'd': core->disconnected(); break;
            case 'b': if (boots < 4) { ++boots; start(); } break;
            default: break;
        }
        // Read-only accessors HA status and the actuator channels use.
        (void)core->hydraulicIntent();
        (void)core->actuatorSessionContext("trv1", now);
    }
};
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    Harness h;
    h.start();
    const std::string_view all(reinterpret_cast<const char*>(data), size);
    std::size_t at = 0;
    for (unsigned lines = 0; at < all.size() && lines < 200; ++lines) {
        auto end = all.find('\n', at);
        if (end == std::string_view::npos) end = all.size();
        h.line(all.substr(at, end - at));
        at = end + 1;
    }
    h.core->tick(h.now + 60000, 1792368000, true);
    return 0;
}
