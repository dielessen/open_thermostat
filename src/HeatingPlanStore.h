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
// storage_full: the partition budget refuses the write (HTTP 507, as for the
// Bluetooth settings); failed: the write or its readback did not succeed.
enum class HeatingPlanSave { saved, storage_full, failed };
inline HeatingPlanSave saveHeatingPlan(const std::string& raw) {
    nvs_stats_t stats{};
    const auto partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_NVS, "nvs");
    if (raw.empty() || raw.find('\0') != std::string::npos || !partition || nvs_get_stats("nvs", &stats) != ESP_OK)
        return HeatingPlanSave::failed;
    if (!control::ControlPartitionBudget::permitsHeatingPlanWrite(
               {partition->size, stats.total_entries, stats.used_entries, stats.free_entries, true},
               raw.size() + 1, control::controlModelStorageReservation.current()))
        return HeatingPlanSave::storage_full;
    nvs_handle_t handle;
    if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return HeatingPlanSave::failed;
    const bool committed = nvs_set_blob(handle, "plan", raw.c_str(), raw.size() + 1) == ESP_OK && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return committed && readHeatingPlan() == raw ? HeatingPlanSave::saved : HeatingPlanSave::failed;
}
// The owner's handover confirmation (control/HandoverConfirmation.h): one short
// string beside the plan, written only when the confirmation changes.
struct HandoverNvs {
    static constexpr const char* key = "handover";
    std::string read() const {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return {};
        char text[64] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        return ok ? std::string(text) : std::string();
    }
    bool write(std::string_view record) {
        if (record.empty() || record.size() >= 64) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, std::string(record).c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == record;
    }
    bool erase() {
        nvs_handle_t handle;
        const auto opened = nvs_open("ot_heating", NVS_READWRITE, &handle);
        if (opened == ESP_ERR_NVS_NOT_FOUND) return true;
        if (opened != ESP_OK) return false;
        const auto error = nvs_erase_key(handle, key);
        const bool erased = (error == ESP_OK && nvs_commit(handle) == ESP_OK) || error == ESP_ERR_NVS_NOT_FOUND;
        nvs_close(handle);
        return erased;
    }
};
}
#endif
