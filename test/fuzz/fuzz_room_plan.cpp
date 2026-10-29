// Room plan fuzzer: POST /config/heating and the flash copy (cJSON +
// RoomPlan::parse incl. RoomSchedule::parse), the plan's own JSON round trip,
// the MQTT ha/heating_input handler and RoomEngine steps over the plan.
//
// Input: [mode][plan JSON] 0x00 [heating_input payload] 0x00 [payload] ...
// mode bit0: parse like REST (cJSON_ParseWithLengthOpts, NUL required) else
// like loadHeatingPlan (cJSON_Parse); bits1-7: start time offset (hours).
//
// HeatingController::heatingInput is not host-buildable (ESP/MQTT includes), so
// its body is copied verbatim below. Keep in sync with src/HeatingController.h.
#include "fuzz_common.h"
#include "control/RoomEngine.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include "control/BoundedJson.h"
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>

namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

struct Engine {
    RoomEngine rooms;
    uint64_t now = 0;
    // --- copy of HeatingController::heatingInput (beta.18) ---
    void heatingInput(std::string_view payload) {
        if (payload.size() > 256) return;
        // A retained deep message would otherwise crash every boot (cJSON recursion).
        if (!heating::control::jsonNestingWithin(payload.data(), payload.size(), 4)) return;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        const auto* entity = root ? cJSON_GetObjectItemCaseSensitive(root.get(), "entity") : nullptr;
        if (!cJSON_IsString(entity) || !entity->valuestring || std::strlen(entity->valuestring) > 80) return;
        const auto centi = [&](const char* key, double lo, double hi) -> std::optional<int16_t> {
            const auto* v = cJSON_GetObjectItemCaseSensitive(root.get(), key);
            if (!cJSON_IsNumber(v) || !(v->valuedouble >= lo && v->valuedouble <= hi)) return std::nullopt;
            return static_cast<int16_t>(std::lround(v->valuedouble * 100));
        };
        rooms.haState(entity->valuestring, centi("temperature", -40, 85), centi("target", 5, 30), now);
    }
    // --- end copy ---
};

void checkSchedule(const RoomSchedule& s, int16_t lo, int16_t hi) {
    for (uint8_t d = 0; d < 9; ++d)
        for (uint16_t m : {0, 1, 389, 390, 720, 1439, 1440, 65535}) {
            const auto v = s.at(d, m);
            if (v && (*v < lo || *v > hi)) otfuzz::invariant("schedule setpoint outside room limits");
        }
}
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    if (!size) return 0;
    const uint8_t mode = data[0];
    const std::string all(reinterpret_cast<const char*>(data + 1), size - 1);
    const auto cut = all.find('\0');
    const std::string planText = all.substr(0, cut);

    // REST::heatingPlan (depth 10) and HeatingController::loadHeatingPlan (default depth).
    Json root(mode & 1 ? parseNestedJson(planText, true, 10) : parseNestedJson(planText));
    // The device's precompiled cJSON uses 128 B of stack per level: never deeper.
    {
        std::size_t depth = 0;
        const auto walk = [&](auto&& self, const cJSON* n, std::size_t d) -> void {
            if (cJSON_IsArray(n) || cJSON_IsObject(n)) { if (++d > depth) depth = d; }
            for (auto c = n->child; c; c = c->next) self(self, c, d);
        };
        if (root) walk(walk, root.get(), 0);
        if (depth > legacyJsonDepth) otfuzz::invariant("plan parsed deeper than the depth limit");
    }
    RoomPlan plan;
    const char* error = root ? RoomPlan::parse(root.get(), plan) : "invalid_json";
    Engine e;
    if (std::getenv("OTFUZZ_VERBOSE")) std::fprintf(stderr, "plan: %s\n", error ? error : "ok");
    if (!error) {
        const auto text = plan.json();
        if (text.empty()) otfuzz::invariant("parsed room plan cannot be printed");
        Json again(cJSON_Parse(text.c_str()), cJSON_Delete);
        RoomPlan back;
        if (!again || RoomPlan::parse(again.get(), back)) otfuzz::invariant("printed room plan does not parse again");
        if (back.json() != text) otfuzz::invariant("room plan changed in a JSON round trip");
        for (const auto& room : plan.rooms) {
            checkSchedule(room.schedule, room.minimumCentiC, room.maximumCentiC);
            if (room.sources.empty() || room.sources.size() > RoomDemand::maxSources) otfuzz::invariant("room sources out of range");
        }
        e.rooms.setPlan(plan);
    }
    // Inputs and 10 s control steps, like stepHeating().
    uint32_t unixTime = 1792368000u + (mode >> 1) * 3600u;
    std::size_t at = cut == std::string::npos ? all.size() : cut + 1;
    for (unsigned steps = 0; steps < 32; ++steps) {
        if (at < all.size()) {
            auto next = all.find('\0', at);
            if (next == std::string::npos) next = all.size();
            e.heatingInput(std::string_view(all).substr(at, next - at));
            at = next + 1;
        } else if (steps > 2) break;
        for (const auto& room : e.rooms.plan().rooms)
            for (const auto& source : room.sources)
                if (source.type == RoomPlan::SourceType::ble)
                    e.rooms.bleReading(source.id, int16_t(1950 + steps), e.now);
        e.now += 10000; unixTime += 10;
        const auto request = e.rooms.step(e.now, (steps & 1) ? std::optional<uint32_t>(unixTime) : std::nullopt);
        (void)request;
        for (std::size_t i = 0; i < e.rooms.plan().rooms.size(); ++i) {
            (void)e.rooms.result(i);
            (void)e.rooms.freshTemperature(i, e.now);
        }
    }
    // Time helpers used for the week program.
    const auto t = RoomSchedule::amsterdam(int64_t(unixTime) + int64_t(mode) * 86400 * 97);
    if (t.weekday > 6 || t.minute > 1439) otfuzz::invariant("amsterdam() out of range");
    return 0;
}
