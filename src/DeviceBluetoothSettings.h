#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <cstdint>
#include <nvs.h>
#include <esp_partition.h>
#include "control/ControlPartitionBudget.h"
#include "control/ControlModelStorageReservation.h"
#include <string>
namespace heating {
// Private bounded store, deliberately separate from ot_network/settings.
// Older rollback firmware can serialize the whole network document, so a
// bindkey must never be put there. Configuration and keys commit as ONE blob.
inline std::string readDeviceBluetoothSettings() {
    nvs_handle_t handle;
    auto error=nvs_open("ot_bluetooth",NVS_READONLY,&handle);
    if(error==ESP_ERR_NVS_NOT_FOUND)return "{\"bt\":{}}"; // Read creates nothing.
    if(error!=ESP_OK)return {};
    size_t size=0;error=nvs_get_blob(handle,"settings",nullptr,&size);
    if(error==ESP_ERR_NVS_NOT_FOUND){nvs_close(handle);return "{\"bt\":{}}";}
    if(error!=ESP_OK||size<3||size>2048){nvs_close(handle);return {};}
    std::string raw;
    try {raw.assign(size,'\0');}
    catch(...) {nvs_close(handle);return {};}
    error=nvs_get_blob(handle,"settings",raw.data(),&size);nvs_close(handle);
    if(error!=ESP_OK||raw.back()!='\0'||raw.find('\0')!=raw.size()-1)return {};
    raw.pop_back();return raw;
}
// The status page polls every 5 s while the radio scans: its GET reads flash
// once and keeps the blob in RAM. Writes and their readback still use the exact
// reader above; saveDeviceBluetoothSettings() drops the copy. Loop task only.
inline std::string& bluetoothSettingsCache() { static std::string cache; return cache; }
inline std::string cachedDeviceBluetoothSettings() {
    auto& cache = bluetoothSettingsCache();
    if (cache.empty()) cache = readDeviceBluetoothSettings(); // an error stays empty: read again next time
    return cache;
}
inline bool bluetoothStorageHasRoom(size_t bytes) {
    nvs_stats_t stats{};
    const auto partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
    return partition&&nvs_get_stats("nvs",&stats)==ESP_OK
        &&control::ControlPartitionBudget::permitsBluetoothWrite(
            {partition->size,stats.total_entries,stats.used_entries,stats.free_entries,true},bytes,control::controlModelStorageReservation.current());
}
inline bool saveDeviceBluetoothSettings(const std::string& raw) {
    if(raw.empty()||raw.size()>=2048||raw.find('\0')!=std::string::npos
            ||!bluetoothStorageHasRoom(raw.size()+1))return false;
    nvs_handle_t handle;if(nvs_open("ot_bluetooth",NVS_READWRITE,&handle)!=ESP_OK)return false;
    const bool committed=nvs_set_blob(handle,"settings",raw.c_str(),raw.size()+1)==ESP_OK&&nvs_commit(handle)==ESP_OK;
    nvs_close(handle);
    bluetoothSettingsCache().clear();
    return committed&&readDeviceBluetoothSettings()==raw;
}
}
#endif
