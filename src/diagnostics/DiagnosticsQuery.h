#pragma once
#include <cstdint>
#include <optional>
#include <string_view>

namespace heating::diagnostics {
// Read-only sections of GET /status/diagnostics. The console only names these;
// there is no command interpreter on the device.
enum Section : uint8_t {
    sectionMemory = 1, sectionTasks = 2, sectionNvs = 4, sectionMqtt = 8,
    sectionSessions = 16, sectionRestarts = 32, sectionLog = 64,
};
constexpr uint8_t allSections = 127;
struct SectionName { std::string_view name; uint8_t bit; };
constexpr SectionName sectionNames[] = {
    {"memory", sectionMemory}, {"tasks", sectionTasks}, {"nvs", sectionNvs}, {"mqtt", sectionMqtt},
    {"sessions", sectionSessions}, {"restarts", sectionRestarts}, {"log", sectionLog},
};
// "" or "all": every section. Otherwise a comma list of known names, each once.
// Anything else (unknown names, empty items, spaces, long input) is refused.
inline std::optional<uint8_t> parseSections(std::string_view text) {
    if (text.empty() || text == "all") return allSections;
    if (text.size() > 64) return std::nullopt;
    uint8_t mask = 0;
    while (true) {
        const auto comma = text.find(',');
        const auto item = text.substr(0, comma);
        uint8_t bit = 0;
        for (const auto& known : sectionNames) if (item == known.name) bit = known.bit;
        if (!bit || (mask & bit)) return std::nullopt;
        mask |= bit;
        if (comma == std::string_view::npos) return mask;
        text.remove_prefix(comma + 1);
    }
}
// A confirmed console action (end idle sessions) runs at most once per interval.
class ActionGate {
public:
    explicit constexpr ActionGate(uint64_t intervalMs) : intervalMs_(intervalMs) {}
    bool allow(uint64_t now) {
        if (used_ && now >= last_ && now - last_ < intervalMs_) return false;
        used_ = true; last_ = now; return true;
    }
private:
    uint64_t intervalMs_, last_ = 0;
    bool used_ = false;
};
}
