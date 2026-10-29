#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "control/FlowPolicy.h"
#include <memory>
#include <string>
namespace heating {
// The beta.19 flow options (control/FlowPolicy.h FlowSettings) as one short NVS
// string beside the room plan ("ot_heating"/"flow"), read back after the commit.
// Absent or unreadable: the defaults (everything off, advice only).
struct FlowSettingsNvs {
    static constexpr const char* key = "flow";
    static control::FlowSettings read() {
        control::FlowSettings settings;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return settings;
        char text[control::FlowSettings::maxBytes + 1] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        if (!ok) return settings;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(text), cJSON_Delete);
        control::FlowSettings parsed;
        return root && !control::FlowSettings::parse(root.get(), parsed) ? parsed : settings;
    }
    static bool write(const control::FlowSettings& settings) {
        const auto record = settings.json();
        if (record.size() > control::FlowSettings::maxBytes) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == settings;
    }
};
}
#endif
