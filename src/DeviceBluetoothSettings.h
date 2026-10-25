#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <cstdint>
#include <nvs.h>
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
    std::string raw(size,'\0');error=nvs_get_blob(handle,"settings",raw.data(),&size);nvs_close(handle);
    if(error!=ESP_OK||raw.back()!='\0'||raw.find('\0')!=raw.size()-1)return {};
    raw.pop_back();return raw;
}
inline bool saveDeviceBluetoothSettings(const std::string& raw) {
    if(raw.empty()||raw.size()+1>2048||raw.find('\0')!=std::string::npos)return false;
    nvs_handle_t handle;if(nvs_open("ot_bluetooth",NVS_READWRITE,&handle)!=ESP_OK)return false;
    const bool committed=nvs_set_blob(handle,"settings",raw.c_str(),raw.size()+1)==ESP_OK&&nvs_commit(handle)==ESP_OK;
    nvs_close(handle);return committed&&readDeviceBluetoothSettings()==raw;
}
}
#endif
