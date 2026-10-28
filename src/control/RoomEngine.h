#pragma once
#include "control/FlowDemand.h"
#include "control/RoomDemand.h"
#include "control/RoomPlan.h"
#include "control/ZoneRegulator.h"
#include <array>
#include <optional>
#include <string>
#include <vector>
namespace heating::control {
// Runs the room plan: per room the leading source (RoomDemand), its heat
// demand (ZoneRegulator, 0.2 degC hysteresis) and one boiler flow request
// (FlowDemand). Inputs arrive from Home Assistant states and Bluetooth sensors.
// Pure and single-threaded: the caller owns timing, storage and transmission.
class RoomEngine {
public:
    static constexpr uint32_t setpointMaxAgeMs = 900000; // older HA target: use the fallback

    void setPlan(const RoomPlan& plan) {
        plan_ = plan;
        FlowDemand::Params params;
        params.minimumFlowC = plan.minimumFlowC; params.maximumFlowC = plan.maximumFlowC;
        flow_ = FlowDemand(params);
        rooms_.assign(plan.rooms.size(), {});
        request_ = {};
    }
    const RoomPlan& plan() const { return plan_; }

    // A Home Assistant entity reported its temperature and/or target (centi degC).
    void haState(const std::string& entity, std::optional<int16_t> temperature,
                 std::optional<int16_t> target, uint64_t atMs) {
        for (size_t i = 0; i < plan_.rooms.size(); ++i) {
            const auto& room = plan_.rooms[i];
            for (size_t s = 0; s < room.sources.size(); ++s)
                if (room.sources[s].type == RoomPlan::SourceType::ha && room.sources[s].id == entity)
                    rooms_[i].readings[s] = {temperature, atMs};
            if (!room.setpointEntity.empty() && room.setpointEntity == entity && target) {
                rooms_[i].target = target; rooms_[i].targetAt = atMs;
            }
        }
    }
    void bleReading(const std::string& address, std::optional<int16_t> temperature, uint64_t atMs) {
        for (size_t i = 0; i < plan_.rooms.size(); ++i) {
            const auto& room = plan_.rooms[i];
            for (size_t s = 0; s < room.sources.size(); ++s)
                if (room.sources[s].type == RoomPlan::SourceType::ble && room.sources[s].id == address)
                    rooms_[i].readings[s] = {temperature, atMs};
        }
    }

    // unixNow: wall clock for temporary pauses; nullopt while unknown (pause holds).
    FlowDemand::Request step(uint64_t now, std::optional<uint32_t> unixNow) {
        bool demand = false;
        std::optional<int16_t> error;
        for (size_t i = 0; i < plan_.rooms.size(); ++i) {
            const auto& room = plan_.rooms[i];
            auto& rt = rooms_[i];
            RoomDemand::Spec spec;
            const bool pauseEnded = room.inactiveUntil && unixNow && *unixNow >= room.inactiveUntil;
            spec.state = room.state == RoomDemand::State::active || pauseEnded ? RoomDemand::State::active : RoomDemand::State::inactive;
            spec.sources = static_cast<uint8_t>(room.sources.size());
            spec.minimumCentiC = room.minimumCentiC; spec.maximumCentiC = room.maximumCentiC;
            rt.result = RoomDemand::evaluate(spec, rt.readings, setpoint(room, rt, now), now, rt.lastUsable);
            if (rt.result.source >= 0) rt.lastUsable = rt.readings[rt.result.source];
            const auto zone = rt.regulator.step(now, rt.result.temperature, rt.result.setpoint, rt.result.usable);
            rt.demand = zone.demand;
            if (!rt.result.usable) continue;
            demand = demand || zone.demand;
            error = error ? std::max(*error, rt.result.errorCentiC) : rt.result.errorCentiC;
        }
        request_ = flow_.update(now, demand, error);
        return request_;
    }

    // {"schema":1,"mode":..,"request":{..},"rooms":[..]} for the status page and HA.
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON_AddNumberToObject(root, "schema", 1);
        cJSON_AddStringToObject(root, "mode", plan_.mode == RoomPlan::Mode::active ? "active" : "shadow");
        cJSON* request = cJSON_AddObjectToObject(root, "request");
        cJSON_AddBoolToObject(request, "heat", request_.heat);
        cJSON_AddNumberToObject(request, "flow_c", request_.flowC);
        cJSON_AddStringToObject(request, "reason", FlowDemand::name(request_.reason));
        // The HA entities this plan reads: HA forwards exactly these to ha/heating_input.
        cJSON* entities = cJSON_AddArrayToObject(root, "ha_entities");
        const auto addEntity = [&](const std::string& id) {
            for (const cJSON* e = entities->child; e; e = e->next) if (id == e->valuestring) return;
            cJSON_AddItemToArray(entities, cJSON_CreateString(id.c_str()));
        };
        for (const auto& room : plan_.rooms) {
            for (const auto& s : room.sources) if (s.type == RoomPlan::SourceType::ha) addEntity(s.id);
            if (!room.setpointEntity.empty()) addEntity(room.setpointEntity);
        }
        cJSON* rooms = cJSON_AddArrayToObject(root, "rooms");
        for (size_t i = 0; i < plan_.rooms.size(); ++i) {
            const auto& room = plan_.rooms[i];
            const auto& rt = rooms_[i];
            cJSON* r = cJSON_CreateObject();
            if (!r || !cJSON_AddItemToArray(rooms, r)) { cJSON_Delete(r); cJSON_Delete(root); return nullptr; }
            cJSON_AddStringToObject(r, "id", room.id.c_str());
            cJSON_AddStringToObject(r, "status", RoomDemand::name(rt.result.status));
            if (rt.result.source >= 0) cJSON_AddStringToObject(r, "source", room.sources[rt.result.source].id.c_str());
            else cJSON_AddNullToObject(r, "source");
            centi(r, "temperature", rt.result.temperature);
            centi(r, "setpoint", rt.result.setpoint);
            cJSON_AddBoolToObject(r, "demand", rt.demand);
        }
        return root;
    }

private:
    struct Runtime {
        std::array<RoomDemand::Reading, RoomDemand::maxSources> readings{};
        RoomDemand::Reading lastUsable{};
        std::optional<int16_t> target;
        uint64_t targetAt = 0;
        ZoneRegulator regulator{};
        RoomDemand::Result result{};
        bool demand = false;
    };
    static std::optional<int16_t> setpoint(const RoomPlan::Room& room, const Runtime& rt, uint64_t now) {
        if (rt.target && rt.targetAt <= now && now - rt.targetAt < setpointMaxAgeMs) return rt.target;
        return room.fallbackCentiC; // without HA: the room's own fallback setpoint
    }
    static void centi(cJSON* o, const char* key, std::optional<int16_t> v) {
        if (v) cJSON_AddNumberToObject(o, key, *v / 100.0); else cJSON_AddNullToObject(o, key);
    }
    RoomPlan plan_;
    std::vector<Runtime> rooms_;
    FlowDemand flow_;
    FlowDemand::Request request_{};
};
}
