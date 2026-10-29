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

    // An edit keeps what is known per room (readings, demand) and the burner
    // timers; only changed flow limits restart the flow demand.
    void setPlan(const RoomPlan& plan) {
        std::vector<Runtime> next(plan.rooms.size());
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            const auto& room = plan.rooms[i];
            const auto* old = plan_.find(room.id);
            next[i].active = room.state == RoomDemand::State::active; // until the next step
            if (!old) continue;
            const auto& oldRt = rooms_[old - plan_.rooms.data()];
            next[i] = oldRt;
            next[i].active = room.state == RoomDemand::State::active;
            next[i].readings = {};
            int8_t lead = -1;  // the leading source's index in the edited list
            for (size_t s = 0; s < room.sources.size(); ++s)
                for (size_t o = 0; o < old->sources.size(); ++o)
                    if (old->sources[o].type == room.sources[s].type && old->sources[o].id == room.sources[s].id) {
                        next[i].readings[s] = oldRt.readings[o];
                        if (int(o) == oldRt.result.source) lead = int8_t(s);
                    }
            next[i].result.source = lead;
            if (oldRt.result.source >= 0 && lead < 0) { next[i].result = {}; next[i].lastUsable = {}; } // its sensor was removed
            if (old->setpointEntity != room.setpointEntity) next[i].target.reset();
        }
        if (!configured_ || plan.minimumFlowC != plan_.minimumFlowC || plan.maximumFlowC != plan_.maximumFlowC) {
            FlowDemand::Params params;
            params.minimumFlowC = plan.minimumFlowC; params.maximumFlowC = plan.maximumFlowC;
            flow_ = FlowDemand(params);
            request_ = {};
        }
        configured_ = true;
        plan_ = plan;
        rooms_ = std::move(next);
    }
    const RoomPlan& plan() const { return plan_; }
    // Per plan room after step(): its demand result, and its leading fresh
    // reading whatever its state (frost protection also covers inactive rooms).
    const RoomDemand::Result& result(size_t room) const { return rooms_[room].result; }
    std::optional<int16_t> freshTemperature(size_t room, uint64_t now) const { return fresh(room, now).temperature; }
    // The leading fresh reading and its source index (-1: none), never a held value.
    RoomDemand::Result fresh(size_t room, uint64_t now) const {
        RoomDemand::Spec spec;
        spec.state = RoomDemand::State::active; spec.sources = static_cast<uint8_t>(plan_.rooms[room].sources.size());
        return RoomDemand::evaluate(spec, rooms_[room].readings, std::nullopt, now, {});
    }

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

    // A room's comfort adjustment (RoomOverrides.h), per plan room: setpoint replaces
    // the plan's, ceiling caps it (away), pause: setpoint is the frost floor, also
    // below the room minimum. Never more than a target: the flow limits stay.
    struct Adjust { std::optional<int16_t> setpoint, ceiling; bool pause = false; };
    // unixNow: wall clock for temporary pauses; nullopt while unknown (pause holds).
    // The boiler's own heating limit (0x16) for the flow request; nullopt: unknown.
    void setBoilerLimit(std::optional<uint8_t> limitC) { boilerLimitC_ = limitC; }
    FlowDemand::Request step(uint64_t now, std::optional<uint32_t> unixNow, const Adjust* adjust = nullptr) {
        bool demand = false;
        std::optional<int16_t> error;
        for (size_t i = 0; i < plan_.rooms.size(); ++i) {
            const auto& room = plan_.rooms[i];
            auto& rt = rooms_[i];
            RoomDemand::Spec spec;
            const bool pauseEnded = room.inactiveUntil && unixNow && *unixNow >= room.inactiveUntil;
            spec.state = room.state == RoomDemand::State::active || pauseEnded ? RoomDemand::State::active : RoomDemand::State::inactive;
            rt.active = spec.state == RoomDemand::State::active;
            spec.sources = static_cast<uint8_t>(room.sources.size());
            spec.minimumCentiC = room.minimumCentiC; spec.maximumCentiC = room.maximumCentiC;
            rt.setpointSource = setpointSource(room, rt, now, unixNow);
            auto target = setpoint(room, rt, rt.setpointSource, unixNow);
            if (adjust) {
                const auto& a = adjust[i];
                if (a.pause && a.setpoint) spec.minimumCentiC = std::min(spec.minimumCentiC, *a.setpoint);
                if (a.setpoint) target = a.setpoint;
                else if (a.ceiling && (!target || *target > *a.ceiling)) target = a.ceiling;
            }
            rt.result = RoomDemand::evaluate(spec, rt.readings, target, now, rt.lastUsable);
            if (rt.result.source >= 0) rt.lastUsable = rt.readings[rt.result.source];
            const auto zone = rt.regulator.step(now, rt.result.temperature, rt.result.setpoint, rt.result.usable);
            rt.demand = zone.demand;
            if (!rt.result.usable) continue;
            demand = demand || zone.demand;
            error = error ? std::max(*error, rt.result.errorCentiC) : rt.result.errorCentiC;
        }
        flow_.setBoilerLimit(boilerLimitC_);
        request_ = flow_.update(now, demand, error);
        return request_;
    }

    // {"schema":1,"mode":..,"request":{..},"rooms":[..]} for the status page and HA.
    // nullptr: no memory.
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        cJSON_AddNumberToObject(root, "schema", 1);
        cJSON_AddNumberToObject(root, "revision", plan_.revision);
        cJSON_AddStringToObject(root, "mode", plan_.mode == RoomPlan::Mode::active ? "active" : "shadow");
        cJSON* request = cJSON_AddObjectToObject(root, "request");
        cJSON_AddBoolToObject(request, "heat", request_.heat);
        cJSON_AddNumberToObject(request, "flow_c", request_.flowC);
        cJSON_AddStringToObject(request, "reason", FlowDemand::name(request_.reason));
        if (request_.capped) cJSON_AddStringToObject(request, "capped_by", "boiler_limit"); else cJSON_AddNullToObject(request, "capped_by");
        // The HA entities this plan reads: HA forwards exactly these to ha/heating_input.
        cJSON* entities = cJSON_AddArrayToObject(root, "ha_entities");
        if (!entities) { cJSON_Delete(root); return nullptr; }
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
            cJSON_AddStringToObject(r, "name", room.name.c_str());
            // The effective state: active again once a temporary pause has ended.
            cJSON_AddStringToObject(r, "state", rt.active ? "active" : "inactive");
            cJSON_AddNumberToObject(r, "inactive_until", room.inactiveUntil);
            cJSON_AddNumberToObject(r, "fallback_centi_c", room.fallbackCentiC);
            cJSON_AddNumberToObject(r, "minimum_centi_c", room.minimumCentiC);
            cJSON_AddNumberToObject(r, "maximum_centi_c", room.maximumCentiC);
            cJSON_AddStringToObject(r, "status", RoomDemand::name(rt.result.status));
            if (rt.result.source >= 0) cJSON_AddStringToObject(r, "source", room.sources[rt.result.source].id.c_str());
            else cJSON_AddNullToObject(r, "source");
            centi(r, "temperature", rt.result.temperature);
            centi(r, "setpoint", rt.result.setpoint);
            cJSON_AddStringToObject(r, "setpoint_source", rt.setpointSource == SetpointSource::ha ? "ha"
                : rt.setpointSource == SetpointSource::schedule ? "schedule" : "fallback");
            cJSON_AddBoolToObject(r, "demand", rt.demand);
        }
        return root;
    }

private:
    enum class SetpointSource : uint8_t { ha, schedule, fallback };
    struct Runtime {
        std::array<RoomDemand::Reading, RoomDemand::maxSources> readings{};
        RoomDemand::Reading lastUsable{};
        std::optional<int16_t> target;
        uint64_t targetAt = 0;
        ZoneRegulator regulator{};
        RoomDemand::Result result{};
        bool demand = false;
        bool active = false;  // effective state of the last step
        SetpointSource setpointSource = SetpointSource::fallback;
    };
    // A fresh HA target, else the E32 week program (needs the clock), else the fixed fallback.
    static SetpointSource setpointSource(const RoomPlan::Room& room, const Runtime& rt, uint64_t now, std::optional<uint32_t> unixNow) {
        if (rt.target && rt.targetAt <= now && now - rt.targetAt < setpointMaxAgeMs) return SetpointSource::ha;
        if (unixNow && !room.schedule.empty()) return SetpointSource::schedule;
        return SetpointSource::fallback;
    }
    static std::optional<int16_t> setpoint(const RoomPlan::Room& room, const Runtime& rt, SetpointSource source, std::optional<uint32_t> unixNow) {
        if (source == SetpointSource::ha) return rt.target;
        if (source == SetpointSource::schedule) return room.schedule.at(RoomSchedule::localAt(*unixNow));
        return room.fallbackCentiC;
    }
    static void centi(cJSON* o, const char* key, std::optional<int16_t> v) {
        if (v) cJSON_AddNumberToObject(o, key, *v / 100.0); else cJSON_AddNullToObject(o, key);
    }
    RoomPlan plan_;
    std::vector<Runtime> rooms_;
    FlowDemand flow_;
    std::optional<uint8_t> boilerLimitC_;
    FlowDemand::Request request_{};
    bool configured_ = false;
};
}
