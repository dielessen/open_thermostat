#pragma once
#include "control/BoundedJson.h"
#include "control/FlowLearner.h"
#include "control/RoomEngine.h"
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
// One MQTT ha/heating_input message from HA (pure; HeatingController routes it).
//  - room (no "kind"): {"entity":"climate.woonkamer","temperature":20.4,"target":21.0},
//    either value may be null or absent;
//  - {"kind":"gas_m3","entity":"sensor.gas","value":1234.567}: gas meter total (m3);
//  - {"kind":"gas_price","value":1.32}: EUR per m3 (0 < value <= 20);
//  - {"kind":"outdoor_c","entity":"sensor.outdoor","value":7.4}: -50..60 degC;
//  - {"kind":"boiler_kw","value":22}: nominal boiler gas input, 3..60 kW.
// Anything else (unknown kind, a value out of range, a missing entity) is ignored.
struct HeatingInput {
    enum class Kind : uint8_t { room, gasM3, gasPrice, outdoorC, boilerKw };
    static constexpr size_t maxBytes = 256, maxEntity = 80;
    Kind kind = Kind::room;
    std::string entity;
    std::optional<int16_t> temperatureCentiC, targetCentiC; // room
    double value = 0;                                       // typed kinds

    static std::optional<HeatingInput> parse(std::string_view payload) {
        if (payload.size() > maxBytes) return std::nullopt;
        // A retained deep message would otherwise crash every boot (cJSON recursion).
        if (!jsonNestingWithin(payload.data(), payload.size(), 4)) return std::nullopt;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        if (!cJSON_IsObject(root.get())) return std::nullopt;
        const auto* o = root.get();
        HeatingInput in;
        const auto* entity = cJSON_GetObjectItemCaseSensitive(o, "entity");
        const bool hasEntity = cJSON_IsString(entity) && entity->valuestring && *entity->valuestring
            && std::strlen(entity->valuestring) <= maxEntity;
        if (hasEntity) in.entity = entity->valuestring;
        const auto* kind = cJSON_GetObjectItemCaseSensitive(o, "kind");
        if (!kind) {
            if (!hasEntity) return std::nullopt;
            const auto centi = [&](const char* key, double lo, double hi) -> std::optional<int16_t> {
                const auto* v = cJSON_GetObjectItemCaseSensitive(o, key);
                if (!cJSON_IsNumber(v) || !(v->valuedouble >= lo && v->valuedouble <= hi)) return std::nullopt;
                return static_cast<int16_t>(std::lround(v->valuedouble * 100));
            };
            in.temperatureCentiC = centi("temperature", -40, 85);
            in.targetCentiC = centi("target", 5, 30);
            return in;
        }
        if (!cJSON_IsString(kind) || !kind->valuestring) return std::nullopt;
        const auto* v = cJSON_GetObjectItemCaseSensitive(o, "value");
        if (!cJSON_IsNumber(v) || !std::isfinite(v->valuedouble)) return std::nullopt;
        in.value = v->valuedouble;
        const std::string_view k = kind->valuestring;
        const auto within = [&](double lo, double hi) { return in.value >= lo && in.value <= hi; };
        if (k == "gas_m3" && hasEntity && within(0, 1e8)) in.kind = Kind::gasM3;
        else if (k == "gas_price" && in.value > 0 && in.value <= 20) in.kind = Kind::gasPrice;
        else if (k == "outdoor_c" && hasEntity && within(-50, 60)) in.kind = Kind::outdoorC;
        else if (k == "boiler_kw" && within(3, 60)) in.kind = Kind::boilerKw;
        else return std::nullopt;
        return in;
    }
};

// Routes accepted messages: room states to the RoomEngine, gas, price and
// boiler power to the FlowLearner; keeps HA's outdoor temperature. Single-threaded.
class HeatingInputRoute {
public:
    static constexpr uint64_t outdoorMaxAgeMs = 900000; // HA's outdoor expires after 15 min
    bool accept(std::string_view payload, uint64_t now, RoomEngine& rooms, FlowLearner& learner) {
        const auto in = HeatingInput::parse(payload);
        if (!in) return false;
        switch (in->kind) {
            case HeatingInput::Kind::room: rooms.haState(in->entity, in->temperatureCentiC, in->targetCentiC, now); break;
            case HeatingInput::Kind::gasM3: learner.gasMeter(in->value, now); break;
            case HeatingInput::Kind::gasPrice: learner.gasPrice(static_cast<float>(in->value)); break;
            case HeatingInput::Kind::outdoorC:
                outdoorCentiC_ = static_cast<int16_t>(std::lround(in->value * 100)); outdoorAt_ = now; break;
            case HeatingInput::Kind::boilerKw: learner.setNominalKw(static_cast<float>(in->value)); break;
        }
        lastAccepted_ = now;
        return true;
    }
    // Uptime ms of the last accepted message (any kind); nullopt: none this boot.
    std::optional<uint64_t> lastAcceptedMs() const { return lastAccepted_; }
    struct Outdoor { std::optional<int16_t> centiC; const char* source = nullptr; };
    // The learner's outdoor: a fresh boiler value first, else HA's while fresh.
    Outdoor outdoor(std::optional<int16_t> boilerCentiC, uint64_t now) const {
        if (boilerCentiC) return {boilerCentiC, "boiler"};
        if (outdoorCentiC_ && outdoorAt_ <= now && now - outdoorAt_ <= outdoorMaxAgeMs) return {outdoorCentiC_, "ha"};
        return {};
    }

private:
    std::optional<uint64_t> lastAccepted_;
    std::optional<int16_t> outdoorCentiC_;
    uint64_t outdoorAt_ = 0;
};
}
