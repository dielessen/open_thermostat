#pragma once
// ============================================================================================
// rc.5 (P2) STUB, FOR THE INTEGRATOR TO REPLACE: P1's control/BoilerResponse.h is the real class.
// Until P1 lands, the insight topic (fw/telemetry/insight), Knowledge and HouseModel compile and
// run against this stand-in with the contract's interface (docs/modern-thermostat/RC5-PLAN.md
// section 2.1) and the same "boiler" JSON shape. It learns nothing: every figure stays unknown,
// state() only says whether the E32 drives the boiler ("not_driving") and whether the return
// temperature is reported ("no_return"), else "collecting". Once control/BoilerResponse.h exists
// this header includes it instead, so a merged tree uses the real class unchanged; then include
// control/BoilerResponse.h directly and delete this file.
// ============================================================================================
#if __has_include("control/BoilerResponse.h")
#include "control/BoilerResponse.h"
#else
#include <cJSON.h>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
class BoilerResponse {
public:
    struct Params {};
    struct Sample {
        uint64_t now = 0;
        std::optional<int64_t> utc;                 // trusted clock only
        uint8_t requestC = 0;                       // the request handed to the boiler, 0 = no heat
        bool ownRequest = false;                    // the E32 drives the boiler (active mode, confirmed)
        bool demand = false;                        // at least one usable room asks heat
        std::optional<int16_t> flowCentiC, returnCentiC, outdoorCentiC, roomMeanCentiC;
        std::optional<bool> burnerOn, hotWater;
        std::optional<uint8_t> modulationPct;
        float nominalKw = 22, kwhPerM3 = 9.77f;
    };
    void sample(const Sample& s) { driving_ = s.ownRequest; returnKnown_ = s.returnCentiC.has_value(); }
    std::optional<uint8_t> ceilingC(std::optional<int16_t>) const { return std::nullopt; }
    std::optional<uint32_t> restS() const { return std::nullopt; }
    std::optional<float> absorbedKw() const { return std::nullopt; }
    std::optional<float> kwPerFlowK() const { return std::nullopt; }
    uint16_t heldToday() const { return 0; }
    const char* state() const { return !driving_ ? "not_driving" : !returnKnown_ ? "no_return" : "collecting"; }
    // "boiler":{"held","rest_s","ceiling_c","absorbed_kw","kw_per_k","state"}, as the real one (<= 140 B).
    bool addJson(cJSON* parent) const {
        cJSON* o = cJSON_AddObjectToObject(parent, "boiler");
        return o && cJSON_AddNumberToObject(o, "held", heldToday()) && cJSON_AddNullToObject(o, "rest_s")
            && cJSON_AddNullToObject(o, "ceiling_c") && cJSON_AddNullToObject(o, "absorbed_kw")
            && cJSON_AddNullToObject(o, "kw_per_k") && cJSON_AddStringToObject(o, "state", state());
    }
    std::string stored() const { return {}; }
    bool restore(std::string_view) { return false; }

private:
    bool driving_ = false, returnKnown_ = false;
};
}
#endif
