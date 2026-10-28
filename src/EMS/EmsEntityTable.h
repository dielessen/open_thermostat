#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace heating::ems {
// The one table of passive entities beyond the 69 verified Classic boiler
// fields: what another controller asks of the boiler (0x1A), the maintenance
// message, EMS+ boilers (0xE4-0xEA) and room thermostats (RC10/20/30/35, EMS+
// HC1 monitor). Offsets and scaling follow the EMS-ESP telegram reference
// (https://emsesp.org); independent table, no copied EMS-ESP code. Values are
// observations only and never admit control. Not yet verified on hardware.
enum class EntityKind : uint8_t { u8, s16, u16, u24, bit };
enum class EntitySource : uint8_t { boiler, controller }; // controller: any non-boiler, non-service sender

struct EntitySpec {
    uint16_t type; uint8_t offset; EntityKind kind; uint8_t bit;
    uint16_t divisor; int32_t minimum, maximum; // range in raw units after sign handling
    EntitySource source; const char* id; const char* unit; uint32_t ttlMs;
};

inline constexpr uint32_t monitorTtl=180000, settingTtl=600000;
inline constexpr std::array<EntitySpec,40> entityCatalog{{
    // UBASetPoints written to the boiler by another controller (our own
    // service-address trial is excluded by the observer).
    {0x1A,0,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_flow_temperature","degC",monitorTtl},
    {0x1A,1,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_burner_power","%",monitorTtl},
    {0x1A,2,EntityKind::u8,0,1,0,100,EntitySource::controller,"thermostat_requested_pump_modulation","%",monitorTtl},
    // UBAMaintenanceStatus: message number, 0 = none, 3 = H03.
    {0x1C,5,EntityKind::u8,0,1,0,254,EntitySource::boiler,"maintenance_message","code",settingTtl},
    // Room thermostats: setpoint is half degrees, room temperature tenths.
    {0xB1,1,EntityKind::u8,0,2,0,70,EntitySource::controller,"thermostat_setpoint","degC",monitorTtl},          // RC10
    {0xB1,2,EntityKind::s16,0,10,-300,600,EntitySource::controller,"thermostat_room_temperature","degC",monitorTtl},
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
    {0xEA,6,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_dhw_selected_temperature","degC",settingTtl},
    {0xE6,1,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_heating_temperature","degC",settingTtl},
    {0xE6,4,EntityKind::u8,0,1,0,100,EntitySource::boiler,"plus_maximum_burner_power","%",settingTtl},
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
                || entityCatalog[i].source != entityCatalog[j].source)) return false;
    return true;
}
static_assert(consistentEntityFields(), "rows of one entity must share unit, scale and source");
// Whether a catalog row (telegram type) belongs to the field.
constexpr bool entityFieldType(size_t field, uint16_t type) {
    for (size_t i = 0; i < entityCatalog.size(); ++i)
        if (sameEntity(i, entityFieldRows[field]) && entityCatalog[i].type == type) return true;
    return false;
}

}
