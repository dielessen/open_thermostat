#pragma once
#include "LogSettings.h"
#include <nvs.h>
namespace heating::diagnostics {
inline std::optional<Settings> loadSettings() {
    nvs_handle_t handle;const auto error=nvs_open("ot_logging",NVS_READONLY,&handle);
    if(error==ESP_ERR_NVS_NOT_FOUND)return Settings{};
    if(error!=ESP_OK)return std::nullopt;
    char text[257]{};size_t size=sizeof(text);
    const auto read=nvs_get_str(handle,"settings",text,&size);nvs_close(handle);
    if(read==ESP_ERR_NVS_NOT_FOUND)return Settings{};
    if(read!=ESP_OK||size<2||size>sizeof(text)||text[size-1]!='\0'||std::strlen(text)+1!=size)return std::nullopt;
    return parseSettings(std::string_view(text,size-1));
}
inline bool saveSettings(const Settings& s) {
    if(!valid(s))return false;
    const auto text=settingsJson(s);nvs_handle_t handle;
    if(nvs_open("ot_logging",NVS_READWRITE,&handle)!=ESP_OK)return false;
    const bool saved=nvs_set_str(handle,"settings",text.c_str())==ESP_OK&&nvs_commit(handle)==ESP_OK;
    nvs_close(handle);
    const auto readback=saved?loadSettings():std::nullopt;
    return readback&&settingsJson(*readback)==text;
}
}
