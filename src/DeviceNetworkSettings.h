#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include <SPIFFS.h>
#include <string>
namespace heating {
// Persist network/broker settings outside replaceable filesystem slots. Missing
// NVS migrates read-only from current SPIFFS; corrupt NVS NEVER falls back to
// packaged defaults and silently replaces the configured owner/broker.
inline String readDeviceNetworkSettings() {
    nvs_handle_t h;
    auto error=nvs_open("ot_network",NVS_READONLY,&h);
    if(error==ESP_ERR_NVS_NOT_FOUND) { auto file=SPIFFS.open("/cfg/cfgnetwork.json",FILE_READ); return file?file.readString():String(); }
    if(error!=ESP_OK) return {};
    size_t size=0; error=nvs_get_blob(h,"settings",nullptr,&size);
    if(error==ESP_ERR_NVS_NOT_FOUND) { nvs_close(h); auto file=SPIFFS.open("/cfg/cfgnetwork.json",FILE_READ); return file?file.readString():String(); }
    if(error!=ESP_OK||size<3||size>2048) { nvs_close(h); return {}; }
    std::string raw(size,'\0'); error=nvs_get_blob(h,"settings",raw.data(),&size); nvs_close(h);
    if(error!=ESP_OK||raw.back()!='\0') return {};
    return String(raw.c_str());
}
inline bool saveDeviceNetworkSettings(const String &raw) {
    if(raw.length()==0||raw.length()+1>2048) return false;
    nvs_handle_t h; if(nvs_open("ot_network",NVS_READWRITE,&h)!=ESP_OK) return false;
    const bool ok=nvs_set_blob(h,"settings",raw.c_str(),raw.length()+1)==ESP_OK&&nvs_commit(h)==ESP_OK;
    nvs_close(h); return ok&&readDeviceNetworkSettings()==raw;
}
}
#endif
