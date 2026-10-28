#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include <esp_partition.h>
#include "control/ControlPartitionBudget.h"
#include "control/ControlModelStorageReservation.h"
#include <string>
namespace heating {
// The room plan (control/RoomPlan.h) as one private NVS blob, like the
// Bluetooth settings: read back after every commit, never partially written.
inline constexpr const char* emptyHeatingPlan =
    R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[]})";

inline std::string readHeatingPlan() {
    nvs_handle_t handle;
    auto error = nvs_open("ot_heating", NVS_READONLY, &handle);
    if (error == ESP_ERR_NVS_NOT_FOUND) return emptyHeatingPlan; // reading creates nothing
    if (error != ESP_OK) return {};
    size_t size = 0;
    error = nvs_get_blob(handle, "plan", nullptr, &size);
    if (error == ESP_ERR_NVS_NOT_FOUND) { nvs_close(handle); return emptyHeatingPlan; }
    if (error != ESP_OK || size < 3 || size > control::ControlPartitionBudget::configBytes) { nvs_close(handle); return {}; }
    std::string raw;
    try { raw.assign(size, '\0'); } catch (...) { nvs_close(handle); return {}; }
    error = nvs_get_blob(handle, "plan", raw.data(), &size);
    nvs_close(handle);
    if (error != ESP_OK || raw.back() != '\0' || raw.find('\0') != raw.size() - 1) return {};
    raw.pop_back();
    return raw;
}
inline bool saveHeatingPlan(const std::string& raw) {
    nvs_stats_t stats{};
    const auto partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_NVS, "nvs");
    if (raw.empty() || raw.find('\0') != std::string::npos || !partition || nvs_get_stats("nvs", &stats) != ESP_OK
        || !control::ControlPartitionBudget::permitsHeatingPlanWrite(
               {partition->size, stats.total_entries, stats.used_entries, stats.free_entries, true},
               raw.size() + 1, control::controlModelStorageReservation.current()))
        return false;
    nvs_handle_t handle;
    if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
    const bool committed = nvs_set_blob(handle, "plan", raw.c_str(), raw.size() + 1) == ESP_OK && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return committed && readHeatingPlan() == raw;
}
}
#endif
