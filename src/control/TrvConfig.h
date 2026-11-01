#pragma once
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <string_view>
#include <vector>
namespace heating::control {
// Radiator valves (TRVs) per room, reached through Zigbee2MQTT on the same MQTT
// broker (beta.24, prepared in beta.23; owner 1 Nov 2026). Its own record beside
// the room plan ("ot_heating"/"trv"), never inside it, so a rollback and the plan's
// store budget are untouched. Absent record = no valves: nothing subscribes, sends
// or changes (TrvControl). Every room's valve control is off until switched on.
//
// The Zigbee2MQTT keys per model come from its device pages (exposes) and are to be
// confirmed on real hardware before a release enables them by default.
struct TrvModel {
    const char* id;            // our model id, also what the API takes
    const char* label;
    const char* setpointKey;   // the setpoint the valve regulates to (0.5 degC steps)
    const char* externalKey;   // external room temperature input, nullptr: none
    const char* positionKey;   // valve position readback 0..100 %, nullptr: none
    const char* batteryKey;    // battery in %, nullptr: only a low flag
    const char* batteryLowKey; // low-battery flag, nullptr: none
    const char* enableKey;     // sent once when control starts (manual mode), nullptr: none
    const char* enableValue;
    const char* externalSelectKey;   // e.g. the TRVZB's temperature_sensor_select, nullptr: none
    const char* externalSelectValue;
    const char* externalSelectLegacyValue;  // the same choice in older Zigbee2MQTT, nullptr: none
    int16_t minimumCentiC, maximumCentiC;
};
inline constexpr TrvModel trvModels[] = {
    // Bosch BTH-RA: position set and readback (pi_heating_demand), remote temperature, battery %.
    {"bosch_bth_ra", "Bosch BTH-RA", "occupied_heating_setpoint", "remote_temperature", "pi_heating_demand",
     "battery", nullptr, "operating_mode", "manual", nullptr, nullptr, nullptr, 500, 3000},
    // Sonoff TRVZB: external temperature input, no position readback (opening degree is a limit).
    // system_mode heat: "auto" would follow the valve's own week schedule. The sensor select is
    // remote_temperature in current Zigbee2MQTT (local/remote/remote_source_offline), external in
    // older versions (internal/external/external_2/external_3); the valve's report tells which.
    {"sonoff_trvzb", "Sonoff TRVZB", "occupied_heating_setpoint", "external_temperature_input", nullptr,
     "battery", nullptr, "system_mode", "heat", "temperature_sensor_select", "remote_temperature", "external", 400, 3500},
    // Sonoff TRV Gen2 (TRV-ZBT): as the TRVZB, 5-30 degC; heating/idle_valve_position are limits, no readback.
    {"sonoff_trv_zbt", "Sonoff TRV Gen2 (TRV-ZBT)", "occupied_heating_setpoint", "external_temperature_input", nullptr,
     "battery", nullptr, "system_mode", "heat", "temperature_sensor_select", "remote_temperature", nullptr, 500, 3000},
    // Tuya TV02: setpoint only, a low-battery flag.
    {"tuya_tv02", "Tuya TV02", "current_heating_setpoint", nullptr, nullptr,
     nullptr, "battery_low", "preset", "manual", nullptr, nullptr, nullptr, 500, 2950},
    // Any other Zigbee2MQTT thermostat with the standard setpoint key.
    {"generic", "Other (setpoint only)", "occupied_heating_setpoint", nullptr, nullptr,
     "battery", "battery_low", nullptr, nullptr, nullptr, nullptr, nullptr, 500, 3000},
};
inline const TrvModel* trvModel(std::string_view id) {
    for (const auto& m : trvModels) if (id == m.id) return &m;
    return nullptr;
}

struct TrvConfig {
    static constexpr size_t maxRooms = 8, maxValvesPerRoom = 4, maxNameBytes = 64, maxBaseBytes = 48;
    static constexpr size_t maxBytes = 2048;  // the stored record (NVS string) and the POST body bound
    struct Valve { std::string name; const TrvModel* model = nullptr; };
    struct Room { std::string id; bool control = false; std::vector<Valve> valves; };
    std::string baseTopic = "zigbee2mqtt";
    std::vector<Room> rooms;

    bool empty() const {
        for (const auto& r : rooms) if (!r.valves.empty()) return false;
        return true;
    }
    const Room* room(std::string_view id) const {
        for (const auto& r : rooms) if (r.id == id) return &r;
        return nullptr;
    }
    // A Zigbee2MQTT friendly name: printable ASCII without the MQTT wildcards, quotes or
    // backslashes, no leading/trailing '/' or space, no "//". Also the base topic (no spaces).
    static bool validName(std::string_view s, size_t max, bool spaces) {
        if (s.empty() || s.size() > max || s.front() == '/' || s.back() == '/' || s.front() == ' ' || s.back() == ' ') return false;
        if (s.find("//") != std::string_view::npos || s == "bridge" || s.substr(0, 7) == "bridge/") return false;
        for (const unsigned char c : s)
            if (c < 0x20 || c > 0x7e || c == '#' || c == '+' || c == '"' || c == '\\' || (!spaces && c == ' ')) return false;
        return true;
    }
    // {"schema":1,"base_topic":"zigbee2mqtt","rooms":[{"room":"woonkamer","control":false,
    //  "valves":[{"name":"Bedroom valve","model":"bosch_bth_ra"}]}]}. nullptr or an error name.
    static const char* parse(const cJSON* root, TrvConfig& out) {
        TrvConfig c;
        if (!cJSON_IsObject(root)) return "invalid_json";
        const auto* schema = cJSON_GetObjectItemCaseSensitive(root, "schema");
        if (!cJSON_IsNumber(schema) || schema->valuedouble != 1) return "invalid_schema";
        if (const auto* base = cJSON_GetObjectItemCaseSensitive(root, "base_topic")) {
            if (!cJSON_IsString(base) || !validName(base->valuestring, maxBaseBytes, false)) return "invalid_base_topic";
            c.baseTopic = base->valuestring;
        }
        const auto* rooms = cJSON_GetObjectItemCaseSensitive(root, "rooms");
        if (!cJSON_IsArray(rooms) || cJSON_GetArraySize(rooms) > int(maxRooms)) return "invalid_rooms";
        size_t total = 0;
        for (const cJSON* r = rooms->child; r; r = r->next) {
            Room room;
            const auto* id = cJSON_GetObjectItemCaseSensitive(r, "room");
            const auto* control = cJSON_GetObjectItemCaseSensitive(r, "control");
            const auto* valves = cJSON_GetObjectItemCaseSensitive(r, "valves");
            if (!cJSON_IsObject(r) || !cJSON_IsString(id) || !*id->valuestring || std::strlen(id->valuestring) > 32) return "invalid_room";
            if (control && !cJSON_IsBool(control)) return "invalid_control";
            if (!cJSON_IsArray(valves) || cJSON_GetArraySize(valves) > int(maxValvesPerRoom)) return "invalid_valves";
            room.id = id->valuestring; room.control = cJSON_IsTrue(control);
            for (const cJSON* v = valves->child; v; v = v->next) {
                const auto* name = cJSON_GetObjectItemCaseSensitive(v, "name");
                const auto* model = cJSON_GetObjectItemCaseSensitive(v, "model");
                if (!cJSON_IsObject(v) || !cJSON_IsString(name) || !validName(name->valuestring, maxNameBytes, true)) return "invalid_valve_name";
                const TrvModel* m = cJSON_IsString(model) ? trvModel(model->valuestring) : nullptr;
                if (!m) return "invalid_valve_model";
                for (const auto& other : c.rooms) for (const auto& o : other.valves) if (o.name == name->valuestring) return "duplicate_valve";
                for (const auto& o : room.valves) if (o.name == name->valuestring) return "duplicate_valve";
                room.valves.push_back({name->valuestring, m});
                ++total;
            }
            // Control without a valve means nothing; keep the record honest.
            if (room.valves.empty()) room.control = false;
            for (const auto& other : c.rooms) if (other.id == room.id) return "duplicate_room";
            c.rooms.push_back(std::move(room));
        }
        if (total > maxRooms * 2) return "too_many_valves";
        out = std::move(c);
        return nullptr;
    }
    std::string json() const {
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_CreateObject(), cJSON_Delete);
        if (!root) return {};
        cJSON_AddNumberToObject(root.get(), "schema", 1);
        cJSON_AddStringToObject(root.get(), "base_topic", baseTopic.c_str());
        auto* list = cJSON_AddArrayToObject(root.get(), "rooms");
        for (const auto& r : rooms) {
            auto* o = cJSON_CreateObject();
            if (!o || !list) return {};
            cJSON_AddItemToArray(list, o);
            cJSON_AddStringToObject(o, "room", r.id.c_str());
            cJSON_AddBoolToObject(o, "control", r.control);
            auto* valves = cJSON_AddArrayToObject(o, "valves");
            for (const auto& v : r.valves) {
                auto* vo = cJSON_CreateObject();
                if (!vo || !valves) return {};
                cJSON_AddItemToArray(valves, vo);
                cJSON_AddStringToObject(vo, "name", v.name.c_str());
                cJSON_AddStringToObject(vo, "model", v.model->id);
            }
        }
        char* text = cJSON_PrintUnformatted(root.get());
        std::string out = text ? text : "";
        cJSON_free(text);
        return out;
    }
    bool operator==(const TrvConfig& o) const { return json() == o.json(); }
};
}
