#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace heating::ems {
// The one table of passive entities beyond the 69 verified Classic boiler
// fields: what another controller asks of the boiler (0x1A), the maintenance
// message, Classic error/uptime records, EMS+ boilers (0xE4-0xEA) and room thermostats (RC10/20/30/35, EMS+
// HC1 monitor). Offsets and scaling follow the EMS-ESP telegram reference
// (https://emsesp.org); independent table, no copied EMS-ESP code. Values are
// observations only and never admit control. Rows marked verified were decoded
// from the owner's real frames (tado RC10-type at 0x17 on a Nefit EcomLine HRC
// behind an EasyControl adapter) with plausible values; the others follow the
// reference only and are not yet verified on hardware.
// u24 rows are EMS 3-byte lifetime counters (HA: total_increasing); text is
// two printable ASCII characters (a display or error code).
enum class EntityKind : uint8_t { u8, s16, u16, u24, bit, text };
enum class EntitySource : uint8_t { boiler, controller }; // controller: any non-boiler, non-service sender

// Lifetimes (ttlMs): a value a device sends on its own lives monitorTtl (monitors, what another
// controller writes) or statusTtl (the maintenance status). requestOnlyTtl (0) marks a value the
// boiler sends only when a controller asks for it (0xE6/0xEA settings, 0x10/0x11 error records,
// 0x14 uptime): the last one read this boot stays valid until a newer report replaces it; it never
// expires (rc.5, the owner: show what is read only at start-up or once, with a remark), as the
// Classic settings of 0x16/0x33 (ClassicBoilerMonitor.h). scripts/generate_ems_fields.py writes it
// into Home Assistant's catalog as REQUEST_ONLY.
inline constexpr uint32_t monitorTtl=180000, statusTtl=600000, requestOnlyTtl=0;
struct EntitySpec {
    uint16_t type; uint8_t offset; EntityKind kind; uint8_t bit;
    uint16_t divisor; int32_t minimum, maximum; // range in raw units after sign handling
    EntitySource source; const char* id; const char* unit; uint32_t ttlMs;
    bool verified = false; // decoded from real frames with plausible values
    constexpr bool requestOnly() const { return ttlMs == requestOnlyTtl; }
    // Whether a report that arrived at observedMs is still valid at now (never before it arrived).
    constexpr bool fresh(uint64_t observedMs, uint64_t now) const {
        return now >= observedMs && (requestOnly() || now - observedMs < ttlMs);
    }
};
inline constexpr bool verified = true;

inline constexpr std::array<EntitySpec,46> entityCatalog{{
    // UBASetPoints written to the boiler by another controller (our own
    // service-address trial is excluded by the observer). tado: every ~40 s,
    // 00 00 00 idle or flow 31-43 degC with 100 % power and pump.
    {0x1A,0,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_flow_temperature","degC",monitorTtl,verified},
    {0x1A,1,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_burner_power","%",monitorTtl,verified},
    {0x1A,2,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_pump_modulation","%",monitorTtl,verified},
    // UBAMaintenanceStatus: message number, 0 = none, 3 = H03.
    {0x1C,5,EntityKind::u8,0,1,0,254,EntitySource::boiler,"maintenance_message","code",statusTtl},
    // Room thermostats: setpoint is half degrees, room temperature tenths.
    // RC10 0xB1 from the tado every ~20 s: setpoint 19.0/21.0, room 20.9-21.4 degC.
    {0xB1,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl,verified}, // RC10
    {0xB1,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl,verified},
    {0x91,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC20
    {0x91,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0xAE,2,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC20 (new)/RC25
    {0xAE,3,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x41,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC30
    {0x41,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x3E,2,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC35 HC1
    {0x3E,3,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x3E,14,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_target_flow_temperature","degC",monitorTtl},
    // EMS+ HC1 monitor: the setpoint offset differs per model; room and target flow agree.
    {0x02A5,0,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
    {0x02A5,4,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_target_flow_temperature","degC",monitorTtl},
    // EMS+ boiler monitors and parameters.
    {0xE4,6,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_selected_flow_temperature","degC",monitorTtl},
    {0xE4,7,EntityKind::u16,0,10,0,1300,EntitySource::boiler,"plus_flow_temperature","degC",monitorTtl},
    {0xE4,9,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_requested_burner_power","%",monitorTtl},
    {0xE4,10,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_burner_modulation","%",monitorTtl},
    {0xE4,11,EntityKind::bit,0,1,0,1,EntitySource::boiler,"plus_burner_on","bool",monitorTtl},
    {0xE4,11,EntityKind::bit,2,1,0,1,EntitySource::boiler,"plus_dhw_valve","bool",monitorTtl},
    {0xE4,17,EntityKind::u16,0,10,1,1300,EntitySource::boiler,"plus_return_temperature","degC",monitorTtl},  // 0 = no sensor
    {0xE4,19,EntityKind::u16,0,10,0,1000,EntitySource::boiler,"plus_flame_current","uA",monitorTtl},
    {0xE4,21,EntityKind::u8,0,10,1,40,EntitySource::boiler,"plus_pressure","bar",monitorTtl},                // 0 = no sensor
    {0xE4,31,EntityKind::u16,0,10,0,5000,EntitySource::boiler,"plus_exhaust_temperature","degC",monitorTtl},
    {0xE5,2,EntityKind::bit,5,1,0,1,EntitySource::boiler,"plus_heating_pump","bool",monitorTtl},
    {0xE5,10,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_burner_starts","starts",monitorTtl},
    {0xE5,13,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_burner_runtime","min",monitorTtl},
    {0xE5,19,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_heating_runtime","min",monitorTtl},
    {0xE5,25,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_heating_pump_modulation","%",monitorTtl},
    {0xE9,0,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_dhw_target","degC",monitorTtl},
    {0xE9,1,EntityKind::u16,0,10,0,1000,EntitySource::boiler,"plus_dhw_temperature","degC",monitorTtl},
    {0xE9,11,EntityKind::u8,0,10,0,250,EntitySource::boiler,"plus_dhw_flow","L/min",monitorTtl},
    {0xE9,14,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_dhw_runtime","min",monitorTtl},
    {0xE9,17,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"plus_dhw_starts","starts",monitorTtl},
    // EMS+ settings (UBAParameterWWPlus, UBAParametersPlus): sent only when asked, as Classic 0x33/0x16.
    {0xEA,6,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_dhw_selected_temperature","degC",requestOnlyTtl},
    {0xE6,1,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_heating_temperature","degC",requestOnlyTtl},
    {0xE6,4,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_maximum_burner_power","%",requestOnlyTtl},
    // Classic UBA records, appended so earlier field indexes stay stable. The
    // Nefit chain sends them only when asked (EasyControl, a one-shot read) or,
    // for 0x10/0x11, on a fault: no such frame in the live logs yet, unverified.
    // Offset 0 is the newest record: display code, then error number. Starts
    // and runtimes are already Classic fields 18-23 (0x19/0x34; 0 on this chain).
    {0x10,0,EntityKind::text,0,1,8224,32382,EntitySource::boiler,"last_locking_error_code","text",requestOnlyTtl},  // UBAErrorMessage1
    {0x10,2,EntityKind::u16,0,1,0,9999,EntitySource::boiler,"last_locking_error_number","code",requestOnlyTtl},
    {0x11,0,EntityKind::text,0,1,8224,32382,EntitySource::boiler,"last_blocking_error_code","text",requestOnlyTtl}, // UBAErrorMessage2
    {0x11,2,EntityKind::u16,0,1,0,9999,EntitySource::boiler,"last_blocking_error_number","code",requestOnlyTtl},
    {0x14,0,EntityKind::u24,0,1,0,16777214,EntitySource::boiler,"boiler_uptime","min",requestOnlyTtl},          // UBATotalUptime
    // UBAParameterWW selected DHW temperature as another controller writes it
    // (tado: 17 08 33 02 37 = 55 degC every ~20 s). The boiler's own 0x33
    // broadcast is already Classic field 13 (selected_dhw_temperature).
    {0x33,2,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_dhw_temperature","degC",monitorTtl,verified},
}};

// One field per entity id, after the 69 Classic boiler fields on the boiler
// fields route (boiler.fields.v2), in catalog order. Rows sharing an id (the
// same value in another thermostat's telegram) must agree on unit and scale.
constexpr bool sameEntity(size_t a, size_t b) { return std::string_view(entityCatalog[a].id) == entityCatalog[b].id; }
constexpr bool firstEntityRow(size_t row) {
    for (size_t i = 0; i < row; ++i) if (sameEntity(i, row)) return false;
    return true;
}
constexpr size_t countEntityFields() {
    size_t n = 0;
    for (size_t i = 0; i < entityCatalog.size(); ++i) n += firstEntityRow(i);
    return n;
}
inline constexpr size_t entityFieldCount = countEntityFields();
constexpr std::array<uint8_t, entityFieldCount> listEntityFieldRows() {
    std::array<uint8_t, entityFieldCount> rows{};
    size_t n = 0;
    for (size_t i = 0; i < entityCatalog.size(); ++i) if (firstEntityRow(i)) rows[n++] = static_cast<uint8_t>(i);
    return rows;
}
inline constexpr auto entityFieldRows = listEntityFieldRows(); // first catalog row of each field
constexpr bool consistentEntityFields() {
    for (size_t i = 0; i < entityCatalog.size(); ++i)
        for (size_t j = 0; j < i; ++j)
            if (sameEntity(i, j) && (entityCatalog[i].divisor != entityCatalog[j].divisor
                || std::string_view(entityCatalog[i].unit) != entityCatalog[j].unit
                || entityCatalog[i].source != entityCatalog[j].source
                || entityCatalog[i].ttlMs != entityCatalog[j].ttlMs)) return false;
    return true;
}
static_assert(consistentEntityFields(), "rows of one entity must share unit, scale, source and lifetime");
// The request-only rows are exactly the boiler's telegrams it sends only when asked: the EMS+ settings
// (0xE6, 0xEA), the error records (0x10, 0x11) and the uptime (0x14). Monitors, the maintenance status
// (0x1C) and what another controller writes (0x1A, 0x33, room thermostats) keep their lifetime.
constexpr bool requestOnlyRowsAreTheAskedTelegrams() {
    for (const auto& spec : entityCatalog) {
        const bool asked = spec.source == EntitySource::boiler && (spec.type == 0xE6 || spec.type == 0xEA
            || spec.type == 0x10 || spec.type == 0x11 || spec.type == 0x14);
        if (spec.requestOnly() != asked) return false;
    }
    return true;
}
static_assert(requestOnlyRowsAreTheAskedTelegrams(), "request-only marks exactly the telegrams sent only when asked");
// Whether a catalog row (telegram type) belongs to the field.
constexpr bool entityFieldType(size_t field, uint16_t type) {
    for (size_t i = 0; i < entityCatalog.size(); ++i)
        if (sameEntity(i, entityFieldRows[field]) && entityCatalog[i].type == type) return true;
    return false;
}

}
