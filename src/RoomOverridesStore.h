#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "control/RoomOverrides.h"
#include <string>
namespace heating {
// The room overrides and away (control/RoomOverrides.h) as one short versioned
// NVS string beside the room plan ("ot_heating"/"comfort"), written only by a
// command that changes it and read back after the commit. Absent or unreadable:
// nothing temporary (every room follows its plan).
struct RoomOverridesNvs {
    static constexpr const char* key = "comfort";
    static std::string read() {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return {};
        char text[control::RoomOverrides::storeBytes + 1] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        return ok ? std::string(text) : std::string();
    }
    static bool write(const std::string& record) {
        if (record.empty() || record.size() > control::RoomOverrides::storeBytes) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == record;
    }
};
}
#endif
