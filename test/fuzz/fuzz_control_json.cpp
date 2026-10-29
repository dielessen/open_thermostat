// parseControlJson fuzzer: the bounded pre-scanner in front of cJSON for every
// MQTT control message (ShadowController, actuator channels) and the device
// settings. It must never let through a document deeper, larger or wider than
// its budgets (the E32 loop task stack and heap depend on them).
//
// Input: [mode][bytes]; mode bit0 = deviceSettings variant.
#include "fuzz_common.h"
#include "control/BoundedJson.h"
#include "control/ScheduleDocument.h"
#include <cstring>

namespace {
struct Stats { std::size_t nodes = 0, depth = 0; };
void walk(const cJSON* n, std::size_t depth, Stats& s, bool device) {
    ++s.nodes;
    const std::size_t containerDepth = (cJSON_IsArray(n) || cJSON_IsObject(n)) ? depth + 1 : depth;
    s.depth = std::max(s.depth, containerDepth);
    if (cJSON_IsString(n)) {
        const auto len = std::strlen(n->valuestring);
        if (len > (device ? 512u : 64u)) otfuzz::invariant("string over budget accepted");
        if (!device) for (std::size_t i = 0; i < len; ++i) {
            const auto c = static_cast<unsigned char>(n->valuestring[i]);
            if (c < 32 || c > 126) otfuzz::invariant("non printable control string accepted");
        }
    }
    if (n->string && !device && std::strlen(n->string) > 64) otfuzz::invariant("key over budget accepted");
    for (auto c = n->child; c; c = c->next) walk(c, containerDepth, s, device);
}
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    if (!size) return 0;
    const bool device = data[0] & 1;
    const std::string_view bytes(reinterpret_cast<const char*>(data + 1), size - 1);
    auto root = heating::control::parseControlJson(bytes, device);
    if (!root) return 0;
    Stats s; walk(root.get(), 0, s, device);
    if (s.depth > 8) otfuzz::invariant("parseControlJson accepted nesting deeper than 8");
    // Keys + values; cJSON makes one node per value, the scanner counts values.
    if (s.nodes > 512) otfuzz::invariant("parseControlJson accepted more than 512 nodes");
    if (bytes.size() > 8192) otfuzz::invariant("oversized document accepted");
    std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(root.get()), cJSON_free);
    (void)text;
    return 0;
}
