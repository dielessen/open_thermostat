#pragma once
#include <cstdint>

namespace heating::ems {

enum class BoilerProtocol { unknown, classic, plus, conflict };

// Observed wire family, NOT a claim about physical boiler/adapter compatibility.
class BoilerCapabilities {
public:
    static constexpr BoilerProtocol family(uint16_t type) {
        switch (type) {
            case 0x16: case 0x18: case 0x19: case 0x33: case 0x34:
                return BoilerProtocol::classic;
            case 0xE3: case 0xE4: case 0xE5: case 0xE6: case 0xE9: case 0xEA:
                return BoilerProtocol::plus;
            default: return BoilerProtocol::unknown;
        }
    }
    void observe(uint16_t type) {
        const auto next = family(type);
        if (next == BoilerProtocol::unknown) return;
        if (profile_ == BoilerProtocol::unknown) profile_ = next;
        else if (profile_ != next) profile_ = BoilerProtocol::conflict;
    }
    BoilerProtocol profile() const { return profile_; }
    const char *name() const {
        switch (profile_) {
            case BoilerProtocol::classic: return "classic_observed";
            case BoilerProtocol::plus: return "plus_observed";
            case BoilerProtocol::conflict: return "conflicting_families";
            default: return "unknown";
        }
    }
    // Existing generic-board Plus control only; E32 compile-time lock is separate.
    bool allowsLegacyPlusWrites() const { return profile_ == BoilerProtocol::plus; }
    static constexpr bool classicControlCommissioned = false;
private:
    BoilerProtocol profile_ = BoilerProtocol::unknown;
};
}
