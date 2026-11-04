#pragma once
#include "control/ArrivalLearner.h"
#include "control/BoilerResponseStub.h"
#include "control/FlowLearner.h"
#include "control/HouseModel.h"
#include "control/Insights.h"
#include "control/RoomPlan.h"
#include "control/WeatherCurve.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
namespace heating::control {
// Knowing what it does not know (rc.5, P2; owner: the thermostat must say what it knows): one
// figure, 0..100 %, for how much of what the E32 learns about this house it has learned, and
// what is still missing as keys the pages and Home Assistant turn into sentences. Weights:
//  - warm-up rates ready 25: per active plan room, the warm-up time is known (FlowLearner's
//    readiness for timing, one filled flow bin: what Smart warm-up needs); key warmup:<room id>;
//  - cooling rate known 15: per active room, the heat-loss rate (FlowLearner's heat model b);
//    key cooling:<room id>;
//  - curve slope learned 15: CurveLearner has its six steady periods; key curve;
//  - arrival trusted 15: per active room whose E32 week program has a rise, three judged mornings
//    (ArrivalLearner); rooms without a rise, or Smart warm-up off, have nothing to judge and are
//    left out (none left: the part counts as known); key arrival:<room id>;
//  - boiler minimum learned 10: BoilerMinimumFlow found the lowest water temperature the boiler
//    heats at, or the E32 drives the boiler (BoilerResponse's state is not "not_driving"): a boiler
//    that does not fire at the asked temperature is then found out within 15 minutes, so none was
//    found means the plan's lowest works; key boiler_minimum;
//  - boiler response learned 10: BoilerResponse's state "learned"; key boiler_response;
//  - house model learned 10: HouseModel's state "learned"; key house.
// The room parts are the share of the active plan rooms (none: those parts count 0). The figure
// is rounded down: 100 % only when nothing is missing. Missing keys in this order (the weights'),
// rooms in plan order. Derived each time from the learners (nothing stored). Pure.
class Knowledge {
public:
    enum class Part : uint8_t { warmup, cooling, curve, arrival, boilerMinimum, boilerResponse, house };
    static constexpr size_t partCount = 7;
    static constexpr uint8_t weights[partCount] = {25, 15, 15, 15, 10, 10, 10};
    static const char* key(Part p) {
        static constexpr const char* keys[partCount] = {"warmup", "cooling", "curve", "arrival", "boiler_minimum", "boiler_response", "house"};
        return keys[uint8_t(p)];
    }
    struct Missing { Part part = Part::curve; int8_t room = -1; };  // room: plan index for the room parts
    struct Result {
        uint8_t pct = 0;
        std::array<Missing, 3 * RoomPlan::maxRooms + 4> missing{};
        size_t count = 0;
    };
    // boiler: P1's BoilerResponse (or any class with state()); nullptr: none (its parts stay missing,
    // the boiler minimum counts only when learned).
    template <class Boiler>
    static Result percent(const FlowLearner& l, const CurveLearner& curve, const ArrivalLearner& arrival, const Boiler* boiler,
                          const HouseModel& house, const RoomPlan& plan) {
        Result r;
        const size_t rooms = std::min(plan.rooms.size(), RoomPlan::maxRooms);
        const auto active = [&](size_t i) { return plan.rooms[i].state == RoomDemand::State::active; };
        const auto add = [&](Part p, int room = -1) { r.missing[r.count++] = {p, int8_t(room)}; };
        size_t count = 0, warm = 0, cool = 0, judged = 0, trusted = 0;
        for (size_t i = 0; i < rooms; ++i) if (active(i)) ++count;
        for (size_t i = 0; i < rooms; ++i)
            if (active(i)) { if (i < l.rooms() && !std::strcmp(l.readinessTiming(i), "ready")) ++warm; else add(Part::warmup, int(i)); }
        for (size_t i = 0; i < rooms; ++i)
            if (active(i)) { if (i < l.rooms() && l.heatModel(i).lossPerHour) ++cool; else add(Part::cooling, int(i)); }
        const bool slope = curve.slope().has_value();
        if (!slope) add(Part::curve);
        for (size_t i = 0; i < rooms; ++i) {
            if (!active(i) || !l.applied() || !hasRise(plan.rooms[i].schedule)) continue;
            ++judged;
            if (i < arrival.rooms() && arrival.lead(i).trusted) ++trusted; else add(Part::arrival, int(i));
        }
        const bool minimum = l.boilerMinimum().learnedC() > 0 || (boiler && std::strcmp(boiler->state(), "not_driving"));
        const bool response = boiler && !std::strcmp(boiler->state(), "learned");
        const bool model = !std::strcmp(house.state(), "learned");
        if (!minimum) add(Part::boilerMinimum);
        if (!response) add(Part::boilerResponse);
        if (!model) add(Part::house);
        const auto share = [](size_t n, size_t of) { return of ? double(n) / of : 0.0; };
        const double score = weights[0] * share(warm, count) + weights[1] * share(cool, count) + weights[2] * slope
            + weights[3] * (count ? (judged ? share(trusted, judged) : 1.0) : 0.0)
            + weights[4] * minimum + weights[5] * response + weights[6] * model;
        r.pct = r.count ? uint8_t(std::clamp(std::floor(score + 1e-6), 0.0, 99.0)) : 100;
        return r;
    }
    static Result percent(const FlowLearner& l, const CurveLearner& curve, const ArrivalLearner& arrival, std::nullptr_t,
                          const HouseModel& house, const RoomPlan& plan) {
        return percent<BoilerResponse>(l, curve, arrival, nullptr, house, plan);
    }
    // A week program with a higher temperature after a lower one (a morning rise): only then is
    // there an arrival to judge.
    static bool hasRise(const RoomSchedule& s) {
        std::optional<int16_t> last, first;
        bool rise = false;
        for (const auto& d : s.days)
            for (uint8_t k = 0; k < d.count; ++k) {
                if (last && d.points[k].centiC > *last) rise = true;
                if (!first) first = d.points[k].centiC;
                last = d.points[k].centiC;
            }
        return rise || (first && last && *first > *last); // the week wraps around
    }
    // "warmup:woonkamer", "curve", ..: one missing key.
    static std::string text(const Missing& m, const RoomPlan& plan) {
        std::string out = key(m.part);
        if (m.room >= 0 && size_t(m.room) < plan.rooms.size()) out += ':' + plan.rooms[size_t(m.room)].id;
        return out;
    }
};

// fw/telemetry/insight (rc.5): what the E32 knows about the house, its boiler and yesterday:
//   {"schema":1,"knowledge":{"pct":70,"missing":[..],"more":0},"house":{..},"boiler":{..},"insights":[..]}
// added to `parent` as "insight":{knowledge, house, boiler, insights} (TelemetryPublisher::summary()
// publishes its members with the schema, /status/heating keeps it for the page). At most `maxKeys`
// missing keys, and only as many as keep the document with its schema within `maxBytes`; "more"
// counts the rest. With the bounds below the worst case (eight rooms with 32-character ids, four
// room insights, P1's widest boiler of 140 B) stays within 700 B (test_knowledge.cpp,
// test_heating_telemetry.cpp). boiler nullptr: "boiler": null. false: no memory.
inline constexpr size_t insightMaxBytes = 700, insightMaxKeys = 8;
template <class Boiler>
bool addInsightJson(cJSON* parent, const Knowledge::Result& k, const HouseModel& house, const Boiler* boiler, const Insights& insights,
                    const RoomPlan& plan, size_t maxKeys = insightMaxKeys, size_t maxBytes = insightMaxBytes) {
    cJSON* o = cJSON_AddObjectToObject(parent, "insight");
    cJSON* knowledge = o ? cJSON_AddObjectToObject(o, "knowledge") : nullptr;
    cJSON* missing = knowledge && cJSON_AddNumberToObject(knowledge, "pct", k.pct) ? cJSON_AddArrayToObject(knowledge, "missing") : nullptr;
    cJSON* more = missing ? cJSON_AddNumberToObject(knowledge, "more", double(k.count)) : nullptr;
    if (!more || !house.addJson(o) || !(boiler ? boiler->addJson(o) : cJSON_AddNullToObject(o, "boiler") != nullptr) || !insights.addJson(o, plan)) return false;
    char* text = cJSON_PrintUnformatted(o);
    if (!text) return false;
    size_t size = std::strlen(text) + std::strlen("\"schema\":1,"); // the published document: {"schema":1,..}
    cJSON_free(text);
    size_t shown = 0;
    for (; shown < k.count && shown < maxKeys; ++shown) {
        const auto key = Knowledge::text(k.missing[shown], plan);
        if (size + key.size() + 3 > maxBytes) break; // its quotes and a comma
        cJSON* item = cJSON_CreateString(key.c_str());
        if (!item || !cJSON_AddItemToArray(missing, item)) { cJSON_Delete(item); return false; }
        size += key.size() + 3;
    }
    cJSON_SetNumberValue(more, double(k.count - shown));
    return true;
}
inline bool addInsightJson(cJSON* parent, const Knowledge::Result& k, const HouseModel& house, std::nullptr_t, const Insights& insights,
                           const RoomPlan& plan, size_t maxKeys = insightMaxKeys, size_t maxBytes = insightMaxBytes) {
    return addInsightJson<BoilerResponse>(parent, k, house, nullptr, insights, plan, maxKeys, maxBytes);
}
}
