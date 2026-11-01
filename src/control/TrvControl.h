#pragma once
#include "control/FlowDemand.h"
#include "control/TrvConfig.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
namespace heating::control {
// Radiator valve control per room through Zigbee2MQTT (TrvConfig). Harmless while unused:
// without a configured valve it subscribes to nothing, sends nothing, adds nothing to the
// status and returns every boiler request unchanged (tests: TrvHarmless*).
//
// How a valve is driven: the E32 sends the room's target as the valve's setpoint and, where
// the model takes one, the room's measured temperature as its external input. The valve's own
// regulator then sets its opening, so a valve keeps working on its last setpoint when the E32,
// Home Assistant or the broker is gone. Valves that report their position (Bosch BTH-RA) feed
// back into the boiler flow: all partly closed lowers it, one fully open with its room still
// cold raises it, bounded and rate-limited; the hard flow limit and the plan's minimum stay.
//
// Commands only while the room's control is on AND the actuator output is enabled (the E32
// controls the boiler: active plan, takeover confirmed). Battery saving: a setpoint only on a
// change of at least 0.5 degC (and a 6 h refresh), the external temperature at most every
// 10 min (sooner never; a change below 0.2 degC waits up to 25 min, inside the Bosch's 30 min).
class TrvControl {
public:
    static constexpr uint64_t staleMs = 2 * 3600 * 1000ULL;      // no report this long: offline
    static constexpr uint64_t setpointRefreshMs = 6 * 3600 * 1000ULL;
    static constexpr uint64_t setpointMinGapMs = 60 * 1000ULL;
    static constexpr uint64_t externalMinGapMs = 10 * 60 * 1000ULL, externalMaxGapMs = 25 * 60 * 1000ULL;
    static constexpr int16_t externalStepCentiC = 20, setpointStepCentiC = 50;
    static constexpr int16_t frostCentiC = 800;                   // an inactive room's valve: frost protection
    static constexpr uint8_t lowBatteryPct = 20;
    static constexpr uint64_t feedbackStepMs = 10 * 60 * 1000ULL;  // flow offset changes at most this often
    static constexpr int8_t feedbackLimitC = 8;                    // |offset| <= 8 degC
    static constexpr uint8_t openPct = 90, partlyClosedPct = 40, closedPct = 5;
    static constexpr uint64_t closedHoldMs = 10 * 60 * 1000ULL;    // all closed this long: stop the boiler request
    static constexpr size_t maxPayloadBytes = 1024;

    // One room as the control sees it this step (from the room engine).
    struct Room {
        std::string_view id;
        bool active = false;                  // the room is on (not inactive)
        std::optional<int16_t> setpoint;      // the room's effective target
        std::optional<int16_t> temperature;   // fresh measured temperature (its own sources, never a valve's)
        bool demanding = false;               // usable and below its target
        int16_t errorCentiC = 0;              // target - temperature
        size_t sources = 0;                   // temperature sources configured for the room
    };
    struct Valve {
        std::optional<uint8_t> positionPct, batteryPct;
        std::optional<bool> batteryLow;
        std::optional<int16_t> localCentiC, setpointCentiC;
        uint64_t reportAt = 0;               // local receipt time of the last state; 0: none yet
        std::optional<int16_t> sentSetpoint; uint64_t sentSetpointAt = 0;
        std::optional<int16_t> sentExternal; uint64_t sentExternalAt = 0;
        bool enabledSent = false;            // the model's manual mode sent this control period
        uint64_t selectSentAt = 0;           // the sensor select sent (0: not this control period)
        std::optional<bool> remoteSelected;  // the valve reports the external sensor (after selectSentAt)
        bool legacySelect = false;           // the report uses the older Zigbee2MQTT values
        uint64_t closedSince = 0;            // reported <= closedPct since
    };
    enum class Health : uint8_t { unknown, ok, lowBattery, offline };
    using Send = std::function<bool(const std::string& topic, const std::string& payload)>;

    void setConfig(TrvConfig config) {
        std::map<std::string, Valve> kept;
        for (const auto& r : config.rooms) for (const auto& v : r.valves) {
            auto it = valves_.find(v.name);
            kept[v.name] = it != valves_.end() ? it->second : Valve{};
            kept[v.name].enabledSent = false;  // a new config re-sends the mode once
            kept[v.name].selectSentAt = 0;
        }
        valves_ = std::move(kept); config_ = std::move(config); ++generation_;
        if (config_.empty()) { offsetC_ = 0; offsetAt_ = 0; }
    }
    const TrvConfig& config() const { return config_; }
    uint32_t generation() const { return generation_; }  // bumps on every setConfig: resubscribe
    bool used() const { return !config_.empty(); }

    // The valves' state topics (<base>/<name>); empty without valves, so nothing is subscribed.
    std::vector<std::string> subscriptions() const {
        std::vector<std::string> out;
        for (const auto& r : config_.rooms) for (const auto& v : r.valves) out.push_back(config_.baseTopic + "/" + v.name);
        return out;
    }
    // A Zigbee2MQTT state message. True when the topic is one of ours (consumed), whatever its content.
    bool receive(std::string_view topic, std::string_view payload, uint64_t now) {
        const auto* found = valveFor(topic);
        if (!found) return false;
        if (payload.size() > maxPayloadBytes) return true;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        if (!root || !cJSON_IsObject(root.get())) return true;
        auto& v = valves_[found->name];
        const auto* m = found->model;
        // Back after being offline (new batteries, re-paired, Zigbee2MQTT gone for hours): it may have
        // lost its mode and setpoint, so it gets all of them again on the next step.
        if (v.reportAt && now > v.reportAt && now - v.reportAt >= staleMs) { v.enabledSent = false; v.selectSentAt = 0; v.sentSetpoint.reset(); v.sentExternal.reset(); }
        const auto num = [&](const char* key) -> std::optional<double> {
            const auto* it = key ? cJSON_GetObjectItemCaseSensitive(root.get(), key) : nullptr;
            return cJSON_IsNumber(it) && std::isfinite(it->valuedouble) ? std::optional<double>(it->valuedouble) : std::nullopt;
        };
        if (const auto p = num(m->positionKey); p && *p >= 0 && *p <= 100) {
            v.positionPct = uint8_t(std::lround(*p));
            if (*v.positionPct <= closedPct) { if (!v.closedSince) v.closedSince = now ? now : 1; }
            else v.closedSince = 0;
        }
        if (const auto b = num(m->batteryKey); b && *b >= 0 && *b <= 100) v.batteryPct = uint8_t(std::lround(*b));
        if (m->batteryLowKey) if (const auto* low = cJSON_GetObjectItemCaseSensitive(root.get(), m->batteryLowKey); cJSON_IsBool(low)) v.batteryLow = cJSON_IsTrue(low);
        if (const auto t = num("local_temperature"); t && *t > -40 && *t < 85) v.localCentiC = int16_t(std::lround(*t * 100));
        if (const auto s = num(m->setpointKey); s && *s >= 0 && *s < 50) v.setpointCentiC = int16_t(std::lround(*s * 100));
        if (const auto* sel = m->externalSelectKey ? cJSON_GetObjectItemCaseSensitive(root.get(), m->externalSelectKey) : nullptr; cJSON_IsString(sel)) {
            const std::string_view s = sel->valuestring;
            if (m->externalSelectLegacyValue) v.legacySelect = s == "internal" || s.substr(0, 8) == "external";
            // remote_source_offline: selected, the valve waits for our next external value.
            v.remoteSelected = s == selectValue(*m, v) || s == "remote_source_offline";
        }
        v.reportAt = now ? now : 1;
        return true;
    }
    Health health(const std::string& name, uint64_t now) const {
        const auto it = valves_.find(name);
        if (it == valves_.end() || !it->second.reportAt) return Health::unknown;
        const auto& v = it->second;
        if (now > v.reportAt && now - v.reportAt >= staleMs) return Health::offline;
        if ((v.batteryPct && *v.batteryPct <= lowBatteryPct) || (v.batteryLow && *v.batteryLow)) return Health::lowBattery;
        return Health::ok;
    }
    // The valves' commands for this step. Nothing unless outputEnabled and the room's control is on.
    void step(uint64_t now, const std::vector<Room>& rooms, bool outputEnabled, const Send& send) {
        outputEnabled_ = outputEnabled;
        if (!outputEnabled || !send) { for (auto& [n, v] : valves_) { v.enabledSent = false; v.selectSentAt = 0; } return; }
        for (const auto& cr : config_.rooms) {
            if (!cr.control) continue;
            const Room* room = findRoom(rooms, cr.id);
            if (!room) continue;
            int16_t target = room->active && room->setpoint ? *room->setpoint : frostCentiC;
            for (const auto& cv : cr.valves) {
                auto& v = valves_[cv.name];
                const auto* m = cv.model;
                const auto topic = config_.baseTopic + "/" + cv.name + "/set";
                const int16_t setpoint = roundHalf(std::clamp(target, m->minimumCentiC, m->maximumCentiC));
                if (!v.enabledSent && m->enableKey && send(topic, "{\"" + std::string(m->enableKey) + "\":\"" + m->enableValue + "\"}"))
                    v.enabledSent = true;
                const bool changed = !v.sentSetpoint || std::abs(*v.sentSetpoint - setpoint) >= setpointStepCentiC;
                const bool refresh = v.sentSetpoint && now - v.sentSetpointAt >= setpointRefreshMs;
                const bool gapOk = !v.sentSetpointAt || now - v.sentSetpointAt >= setpointMinGapMs;
                if ((changed && gapOk) || refresh) {
                    if (send(topic, "{\"" + std::string(m->setpointKey) + "\":" + decimal(setpoint, 1) + "}")) {
                        v.sentSetpoint = setpoint; v.sentSetpointAt = now ? now : 1;
                    }
                }
                if (m->externalKey && room->temperature) {
                    const int16_t t = *room->temperature;
                    const bool due = !v.sentExternal
                        || (now - v.sentExternalAt >= externalMinGapMs && std::abs(*v.sentExternal - t) >= externalStepCentiC)
                        || now - v.sentExternalAt >= externalMaxGapMs;
                    if (due && send(topic, "{\"" + std::string(m->externalKey) + "\":" + decimal(t, 2) + "}")) {
                        v.sentExternal = t; v.sentExternalAt = now ? now : 1;
                    }
                }
                // The sensor select only after an external value (Zigbee2MQTT refuses a remote select
                // without one), and again when the valve still reports another sensor 10 min later
                // (a refused write, older Zigbee2MQTT values, a reset valve).
                if (m->externalSelectKey && v.sentExternal) {
                    const bool due = !v.selectSentAt || (v.remoteSelected == false && now - v.selectSentAt >= externalMinGapMs);
                    if (due && send(topic, "{\"" + std::string(m->externalSelectKey) + "\":\"" + selectValue(*m, v) + "\"}")) {
                        v.selectSentAt = now ? now : 1; v.remoteSelected.reset();
                    }
                }
            }
        }
    }
    // Valve feedback on the boiler request. Unchanged without output, without a controlled room,
    // or without a position readback; never turns heat on; the caller's guard keeps the hard limit.
    FlowDemand::Request adjust(const FlowDemand::Request& request, const std::vector<Room>& rooms, bool outputEnabled,
                               uint64_t now, uint8_t minimumFlowC, uint8_t maximumFlowC) {
        reason_ = nullptr;
        if (!outputEnabled || !controlled()) { offsetC_ = 0; offsetAt_ = 0; return request; }
        // Positions of fresh valves in controlled rooms that ask for heat.
        int maxPos = -1; bool coldAtFullOpen = false; bool anyReadback = false;
        bool allDemandersClosed = true; bool anyDemander = false;
        for (const auto& room : rooms) {
            if (!room.demanding) continue;
            anyDemander = true;
            const auto* cr = config_.room(room.id);
            if (!cr || !cr->control) { allDemandersClosed = false; continue; }
            bool roomHasReadback = false, roomClosed = true;
            for (const auto& cv : cr->valves) {
                const auto it = valves_.find(cv.name);
                if (it == valves_.end() || !cv.model->positionKey || !it->second.positionPct
                    || health(cv.name, now) == Health::offline) { roomClosed = false; continue; }
                roomHasReadback = anyReadback = true;
                const auto& v = it->second;
                maxPos = std::max<int>(maxPos, *v.positionPct);
                if (*v.positionPct >= openPct && room.errorCentiC >= 50) coldAtFullOpen = true;
                if (!(v.closedSince && now - v.closedSince >= closedHoldMs)) roomClosed = false;
            }
            if (!roomHasReadback || !roomClosed) allDemandersClosed = false;
        }
        auto out = request;
        // All rooms that ask for heat have only closed valves (with readback): no circuit is open,
        // so the boiler request stops. A room without valve control (the floor) keeps it going.
        if (out.heat && anyDemander && allDemandersClosed && anyReadback) {
            out.heat = false; out.flowC = 0; reason_ = "valves_closed";
            return out;
        }
        if (anyReadback && (!offsetAt_ || now - offsetAt_ >= feedbackStepMs)) {
            if (coldAtFullOpen && offsetC_ < feedbackLimitC) { ++offsetC_; offsetAt_ = now ? now : 1; }
            else if (!coldAtFullOpen && maxPos >= 0 && maxPos <= partlyClosedPct && offsetC_ > -feedbackLimitC) { --offsetC_; offsetAt_ = now ? now : 1; }
        } else if (!anyReadback && offsetC_ != 0 && (!offsetAt_ || now - offsetAt_ >= feedbackStepMs)) {
            offsetC_ += offsetC_ > 0 ? -1 : 1; offsetAt_ = now ? now : 1;  // no readback: drift back to the rule
        }
        if (out.heat && offsetC_) {
            const int flow = std::clamp<int>(int(out.flowC) + offsetC_, minimumFlowC, maximumFlowC);
            out.flowC = uint8_t(flow); reason_ = offsetC_ > 0 ? "valves_open" : "valves_partly_closed";
        }
        return out;
    }
    // actuator.output.v1: the E32 itself drives valves (output enabled and a room's control on).
    bool actuatorOutput() const { return outputEnabled_ && controlled(); }
    int8_t offsetC() const { return offsetC_; }
    const char* reason() const { return reason_; }
    // The "trv" status object; nullptr without valves (the status then is exactly as before).
    // No ages: a retained per-room topic would then change every second; "health" says offline.
    cJSON* statusJson(uint64_t now, const std::vector<Room>& rooms) const {
        if (config_.empty()) return nullptr;
        auto* o = cJSON_CreateObject();
        if (!o) return nullptr;
        cJSON_AddBoolToObject(o, "output", actuatorOutput());
        cJSON_AddNumberToObject(o, "flow_offset_c", offsetC_);
        if (reason_) cJSON_AddStringToObject(o, "flow_reason", reason_);
        auto* list = cJSON_AddArrayToObject(o, "rooms");
        for (const auto& cr : config_.rooms) {
            if (cr.valves.empty()) continue;
            auto* ro = cJSON_CreateObject();
            if (!ro || !list) { cJSON_Delete(o); return nullptr; }
            cJSON_AddItemToArray(list, ro);
            cJSON_AddStringToObject(ro, "room", cr.id.c_str());
            cJSON_AddBoolToObject(ro, "control", cr.control);
            bool degraded = false;
            auto* vl = cJSON_AddArrayToObject(ro, "valves");
            for (const auto& cv : cr.valves) {
                auto* vo = cJSON_CreateObject();
                if (!vo || !vl) { cJSON_Delete(o); return nullptr; }
                cJSON_AddItemToArray(vl, vo);
                cJSON_AddStringToObject(vo, "name", cv.name.c_str());
                cJSON_AddStringToObject(vo, "model", cv.model->id);
                const auto h = health(cv.name, now);
                cJSON_AddStringToObject(vo, "health", h == Health::ok ? "ok" : h == Health::lowBattery ? "low_battery"
                                                      : h == Health::offline ? "offline" : "unknown");
                if (h == Health::offline || h == Health::unknown) degraded = true;
                const auto it = valves_.find(cv.name);
                if (it != valves_.end()) {
                    const auto& v = it->second;
                    if (v.positionPct) cJSON_AddNumberToObject(vo, "position_pct", *v.positionPct);
                    if (v.batteryPct) cJSON_AddNumberToObject(vo, "battery_pct", *v.batteryPct);
                    if (v.batteryLow) cJSON_AddBoolToObject(vo, "battery_low", *v.batteryLow);
                    if (v.setpointCentiC) cJSON_AddNumberToObject(vo, "setpoint_c", *v.setpointCentiC / 100.0);
                }
            }
            // A valve that is gone leaves the room counted ("degraded"): it still asks for heat on
            // its other sources ("liever iets te warm dan koud"); one source only: advise a sensor.
            cJSON_AddBoolToObject(ro, "degraded", degraded);
            const Room* room = findRoom(rooms, cr.id);
            cJSON_AddBoolToObject(ro, "single_source", room && room->sources <= 1);
        }
        return o;
    }

private:
    TrvConfig config_;
    std::map<std::string, Valve> valves_;
    uint32_t generation_ = 0;
    int8_t offsetC_ = 0; uint64_t offsetAt_ = 0;
    bool outputEnabled_ = false;
    const char* reason_ = nullptr;

    bool controlled() const {
        for (const auto& r : config_.rooms) if (r.control && !r.valves.empty()) return true;
        return false;
    }
    const TrvConfig::Valve* valveFor(std::string_view topic) const {
        if (topic.size() <= config_.baseTopic.size() + 1 || topic.substr(0, config_.baseTopic.size()) != config_.baseTopic
            || topic[config_.baseTopic.size()] != '/') return nullptr;
        const auto name = topic.substr(config_.baseTopic.size() + 1);
        for (const auto& r : config_.rooms) for (const auto& v : r.valves) if (v.name == name) return &v;
        return nullptr;
    }
    static const Room* findRoom(const std::vector<Room>& rooms, std::string_view id) {
        for (const auto& r : rooms) if (r.id == id) return &r;
        return nullptr;
    }
    static const char* selectValue(const TrvModel& m, const Valve& v) {
        return v.legacySelect && m.externalSelectLegacyValue ? m.externalSelectLegacyValue : m.externalSelectValue;
    }
    static int16_t roundHalf(int16_t c) { return int16_t(std::lround(c / 50.0) * 50); }
    static std::string decimal(int16_t centi, int digits) {
        char buf[16];
        if (digits == 1) std::snprintf(buf, sizeof buf, "%.1f", centi / 100.0);
        else std::snprintf(buf, sizeof buf, "%.2f", centi / 100.0);
        return buf;
    }
};
}
