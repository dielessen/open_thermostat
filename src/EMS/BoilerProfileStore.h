#pragma once
#include "BoilerProfile.h"
#include <nvs.h>

namespace heating::ems {
// The boiler profile as one small NVS blob ("ot_boiler"/"profile", ~50 bytes),
// written only by EmsController::loop after a debounced change.
struct BoilerProfileStore {
    static constexpr const char* space = "ot_boiler";
    static constexpr const char* key = "profile";
    static bool load(BoilerProfile& profile, uint64_t now) {
        nvs_handle_t handle;
        if (nvs_open(space, NVS_READONLY, &handle) != ESP_OK) return false;
        uint8_t data[BoilerProfile::recordBytes] = {};
        size_t size = sizeof(data);
        const bool ok = nvs_get_blob(handle, key, data, &size) == ESP_OK;
        nvs_close(handle);
        return ok && profile.restore(data, size, now);
    }
    static bool write(const BoilerProfile::Record& record) {
        nvs_handle_t handle;
        if (nvs_open(space, NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool ok = nvs_set_blob(handle, key, record.data(), record.size()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return ok;
    }
};
}
