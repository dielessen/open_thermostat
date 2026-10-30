// Room plan fuzzer: POST /config/heating and the flash copy (cJSON +
// RoomPlan::parse incl. RoomSchedule::parse), the plan's own JSON round trip,
// the MQTT ha/heating_input route (control/HeatingInput.h, as HeatingController
// uses it), RoomEngine steps over the plan and the FlowLearner fed from them.
//
// Input: [mode][plan JSON] 0x00 [heating_input payload] 0x00 [payload] ...
// mode bit0: parse like REST (cJSON_ParseWithLengthOpts, NUL required) else
// like loadHeatingPlan (cJSON_Parse); bits1-7: start time offset (hours).
#include "fuzz_common.h"
#include "control/RoomEngine.h"
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include "control/BoundedJson.h"
#include "control/HeatingInput.h"
#include "control/HeatingTelemetry.h"
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
    FlowLearner learner;
    HeatingInputRoute input;
    uint64_t now = 0;
    void heatingInput(std::string_view payload) { input.accept(payload, now, rooms, learner); }
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
        // The NVS form (packed week programs when large) loads back as the same plan.
        const auto stored = plan.storedJson();
        Json reloaded(cJSON_Parse(stored.c_str()), cJSON_Delete);
        RoomPlan boot;
        if (!reloaded || RoomPlan::parse(reloaded.get(), boot) || boot.json() != text)
            otfuzz::invariant("stored room plan does not load back as the same plan");
        if (stored.size() > text.size()) otfuzz::invariant("stored room plan larger than its API form");
        for (const auto& room : plan.rooms) {
            checkSchedule(room.schedule, room.minimumCentiC, room.maximumCentiC);
            if (room.sources.empty() || room.sources.size() > RoomDemand::maxSources) otfuzz::invariant("room sources out of range");
        }
        e.rooms.setPlan(plan);
        e.learner.setPlan(plan);
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
        std::array<FlowLearner::RoomInput, RoomPlan::maxRooms> in{};
        const std::size_t count = std::min(e.rooms.plan().rooms.size(), in.size());
        for (std::size_t i = 0; i < count; ++i) {
            const auto fresh = e.rooms.fresh(i, e.now);
            in[i] = {fresh.temperature, e.rooms.result(i).setpoint, fresh.source};
        }
        const auto outdoor = e.input.outdoor(std::nullopt, e.now);
        FlowLearner::Boiler boiler{int16_t(4000 + steps), request.heat, false, request.flowC, outdoor.centiC, uint8_t(steps * 3), int16_t(3500)};
        e.learner.sample(e.now, boiler, in.data(), count);
    }
    // The status and its MQTT form over whatever the inputs left.
    LearnedContext context;
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{};
    for (std::size_t i = 0; i < e.rooms.plan().rooms.size() && i < temperatures.size(); ++i) temperatures[i] = e.rooms.freshTemperature(i, e.now);
    context.utc = int64_t(unixTime);
    context.temperatures = temperatures.data(); context.now = e.now;
    context.outdoorCentiC = e.input.outdoor(std::nullopt, e.now).centiC;
    if (Json learned{learnedJson(e.learner, e.rooms.plan(), context), cJSON_Delete})
        if (!cJSON_IsObject(cJSON_GetObjectItemCaseSensitive(learned.get(), "inputs"))) otfuzz::invariant("learned without inputs");
    // The MQTT forms: summary and every room's payload stay within their budgets.
    if (heatingSummaryTelemetry(e.learner, context, cJSON_CreateObject()).size() > 600) otfuzz::invariant("heating summary over 600 B");
    for (std::size_t i = 0; i < e.rooms.plan().rooms.size(); ++i) {
        if (!topicSafeRoomId(e.rooms.plan().rooms[i].id)) otfuzz::invariant("room id not topic safe");
        if (learnedRoomTelemetry(e.learner, e.rooms.plan(), i, context).size() > 900) otfuzz::invariant("learned room over 900 B");
    }
    // Time helpers used for the week program.
    const auto t = RoomSchedule::localAt(int64_t(unixTime) + int64_t(mode) * 86400 * 97);
    if (t.weekday > 6 || t.minute > 1439) otfuzz::invariant("localAt() out of range");
    return 0;
}
