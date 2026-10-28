#pragma once
#include "BleDeviceSettings.h"
#include "ManagedBleObserver.h"
namespace heating::control {
inline const char* bleObservationStatusName(BleObservationStatus status) noexcept {
    switch(status) {
        case BleObservationStatus::waiting: return "waiting";
        case BleObservationStatus::key_required: return "key_required";
        case BleObservationStatus::received: return "received";
        case BleObservationStatus::stale: return "stale";
        case BleObservationStatus::malformed: return "malformed";
        case BleObservationStatus::authentication_failed: return "authentication_failed";
        case BleObservationStatus::encryption_required: return "encryption_required";
        case BleObservationStatus::crypto_unavailable: return "crypto_unavailable";
        case BleObservationStatus::configuration_invalid: return "configuration_invalid";
        case BleObservationStatus::clock_invalid: return "clock_invalid";
        default: return "pending_restart";
    }
}
template<class T> bool addBleOptional(cJSON* root,const char* name,const std::optional<T>& value) {
    return value ? cJSON_AddNumberToObject(root,name,static_cast<double>(*value)) != nullptr
        : cJSON_AddNullToObject(root,name) != nullptr;
}
inline bool addBleOptionalBool(cJSON* root,const char* name,const std::optional<bool>& value) {
    return value ? cJSON_AddBoolToObject(root,name,*value) != nullptr : cJSON_AddNullToObject(root,name) != nullptr;
}
inline bool addBleObservation(cJSON* row,const BleObservationSnapshot& value) {
    return cJSON_AddStringToObject(row,"status",bleObservationStatusName(value.status))
        && cJSON_AddBoolToObject(row,"message_integrity",value.authenticated)
        && cJSON_AddBoolToObject(row,"measurement_qualified",false)
        && cJSON_AddNumberToObject(row,"frames_received",value.framesReceived)
        && cJSON_AddNumberToObject(row,"frames_ignored",value.framesIgnored)
        && addBleOptional(row,"temperature",value.temperature)
        && addBleOptional(row,"target_temperature",value.targetTemperature)
        && addBleOptional(row,"external_temperature",value.externalTemperature)
        && addBleOptional(row,"state_revision",value.stateRevision)
        && addBleOptional(row,"target_temperature_age_ms",value.targetTemperatureAgeMs)
        && addBleOptional(row,"external_temperature_age_ms",value.externalTemperatureAgeMs)
        && addBleOptional(row,"state_revision_age_ms",value.stateRevisionAgeMs)
        && addBleOptional(row,"humidity",value.humidity)
        && addBleOptional(row,"battery",value.battery)
        && addBleOptionalBool(row,"battery_low",value.batteryLow)
        && addBleOptionalBool(row,"light",value.light)
        && addBleOptional(row,"light_level",value.lightLevel)
        && addBleOptional(row,"button",value.button)
        && addBleOptional(row,"firmware_32",value.firmware32)
        && addBleOptional(row,"firmware_24",value.firmware24)
        && addBleOptional(row,"temperature_age_ms",value.temperatureAgeMs)
        && addBleOptional(row,"humidity_age_ms",value.humidityAgeMs)
        && addBleOptional(row,"battery_age_ms",value.batteryAgeMs)
        && addBleOptional(row,"last_accepted_age_ms",value.lastAcceptedAgeMs)
        && addBleOptional(row,"counter",value.counter)
        && addBleOptional(row,"rssi",value.rssi)
        && addBleOptional(row,"declared_device_type",value.declaredDeviceType)
        && cJSON_AddNumberToObject(row,"old_counter_drops",value.oldCounterDrops);
}
}
