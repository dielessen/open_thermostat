#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "control/BoundedJson.h"
#include "control/TrvConfig.h"
#include "NvsOptionalRecords.h"
#include <cstring>
#include <memory>
#include <string>
namespace heating {
// The radiator valves (control/TrvConfig.h) as one NVS string beside the room plan
// ("ot_heating"/"trv"), read back after the commit. Absent or unreadable: no valves,
// so nothing subscribes, sends or changes. Firmware before this record ignores it.
struct TrvNvs {
    static constexpr const char* key = "trv";
    static control::TrvConfig read() {
        control::TrvConfig config;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return config;
        std::unique_ptr<char[]> text(new (std::nothrow) char[control::TrvConfig::maxBytes + 1]());
        size_t size = control::TrvConfig::maxBytes + 1;
        const bool ok = text && nvs_get_str(handle, key, text.get(), &size) == ESP_OK;
        nvs_close(handle);
        if (!ok) return config;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(control::parseNestedJson(text.get(), std::strlen(text.get())));
        control::TrvConfig parsed;
        return root && !control::TrvConfig::parse(root.get(), parsed) ? parsed : config;
    }
    // rc.4 (R1-06): a record is written only while control's room stays free after it
    // (userHeatingRecordFits, NvsOptionalRecords.h); erasing it needs no room.
    static bool write(const control::TrvConfig& config) {
        const auto record = config.rooms.empty() ? std::string() : config.json();
        if (!config.rooms.empty() && (record.empty() || record.size() > control::TrvConfig::maxBytes
                                      || !userHeatingRecordFits(key, record.size() + 1))) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        bool committed;
        if (config.rooms.empty()) {  // no valves at all: the record goes, as if never written
            const auto erased = nvs_erase_key(handle, key);
            committed = (erased == ESP_OK || erased == ESP_ERR_NVS_NOT_FOUND) && nvs_commit(handle) == ESP_OK;
        } else {
            committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        }
        nvs_close(handle);
        return committed && read() == config;
    }
};
}
#endif
