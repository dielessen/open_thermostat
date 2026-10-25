#pragma once
#include <nvs.h>
#include "BoilerDisplayModels.h"
#include <optional>
#include <string>
#include <string_view>

namespace heating {
// Presentation only. No controller, EMS address, limits or driver dependency.
inline bool validBoilerDisplayModel(std::string_view model) {
    for (const auto id : boilerDisplayModelIds) if (model == id) return true;
    return false;
}
inline std::optional<std::string> readBoilerDisplayModel() {
    nvs_handle_t handle;
    const auto opened = nvs_open("ot_display", NVS_READONLY, &handle);
    if (opened == ESP_ERR_NVS_NOT_FOUND) return "none";
    if (opened != ESP_OK) return std::nullopt;
    char model[64]{};
    size_t size = sizeof(model);
    const auto result = nvs_get_str(handle, "boiler", model, &size);
    nvs_close(handle);
    if (result == ESP_ERR_NVS_NOT_FOUND) return "none";
    if (result != ESP_OK || size < 2 || size > sizeof(model)
            || model[size-1] != '\0' || !validBoilerDisplayModel(model)) return std::nullopt;
    return std::string(model);
}
inline bool saveBoilerDisplayModel(const std::string& model) {
    if (!validBoilerDisplayModel(model)) return false;
    nvs_handle_t handle;
    if (nvs_open("ot_display", NVS_READWRITE, &handle) != ESP_OK) return false;
    const bool saved = nvs_set_str(handle, "boiler", model.c_str()) == ESP_OK
        && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    const auto readback = saved ? readBoilerDisplayModel() : std::nullopt;
    return readback && *readback == model;
}
}
