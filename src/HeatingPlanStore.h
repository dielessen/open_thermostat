#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include <esp_partition.h>
#include "control/ControlPartitionBudget.h"
#include "control/ControlModelStorageReservation.h"
#include "control/RoomPlan.h"
#include "NvsOptionalRecords.h"
#include <algorithm>
#include <string>
namespace heating {
// The room plan (control/RoomPlan.h) as one private NVS blob, like the
// Bluetooth settings: read back after every commit, never partially written.
// Without a stored plan: an empty new plan, whose mode then follows the boiler bus
// (control/NewPlanDefault.h); `stored` tells which.
inline std::string emptyHeatingPlan() { return control::RoomPlan{}.documentJson(); }

inline std::string readHeatingPlan(bool* stored = nullptr) {
    if (stored) *stored = true;
    nvs_handle_t handle;
    auto error = nvs_open("ot_heating", NVS_READONLY, &handle);
    if (error == ESP_ERR_NVS_NOT_FOUND) { if (stored) *stored = false; return emptyHeatingPlan(); } // reading creates nothing
    if (error != ESP_OK) return {};
    size_t size = 0;
    error = nvs_get_blob(handle, "plan", nullptr, &size);
    if (error == ESP_ERR_NVS_NOT_FOUND) { nvs_close(handle); if (stored) *stored = false; return emptyHeatingPlan(); }
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
// Bluetooth settings), even after the optional records (learned, readiness,
// autotune; NvsOptionalRecords.h) made room for it; failed: the write or its
// readback did not succeed.
enum class HeatingPlanSave { saved, storage_full, failed };
inline HeatingPlanSave saveHeatingPlan(const std::string& raw) {
    if (raw.empty() || raw.find('\0') != std::string::npos || !nvsPartitionStats().valid) return HeatingPlanSave::failed;
    const auto models = control::controlModelStorageReservation.current();
    const size_t control = controlReplacementEntries(); // the stored control record's replacement
    if (!makeNvsRoom([&](control::ControlPartitionStats s) {
            return control::ControlPartitionBudget::permitsHeatingPlanWrite(s, raw.size() + 1, models, control); }))
        return HeatingPlanSave::storage_full;
    nvs_handle_t handle;
    if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return HeatingPlanSave::failed;
    const bool committed = nvs_set_blob(handle, "plan", raw.c_str(), raw.size() + 1) == ESP_OK && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return committed && readHeatingPlan() == raw ? HeatingPlanSave::saved : HeatingPlanSave::failed;
}
// A short text beside the plan, written only when it changes: "takeover_test" (the guided
// boiler test's result, control/TakeoverTest.h) and "owned" (the E32 took over the boiler once).
struct HeatingNoteNvs {
    const char* key;
    std::string read() const {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return {};
        char text[64] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        return ok ? std::string(text) : std::string();
    }
    bool write(const std::string& text) const {
        if (text.empty() || text.size() >= 64) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, text.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == text;
    }
    // rc.3: the boiler test's record is written more often (each step, the owner's mark, the
    // first foreign controller) and on installations that never ran the test, so it is gated
    // like the optional records: written only while the handover, the flow record, a plan save,
    // a 2 KB Bluetooth save and the control record's replacement keep their room after it
    // (NvsOptionalRecords.h). The same key and size bound as rc.2 (< 64 bytes: 3 entries). It is
    // not in ControlPartitionBudget::optionalKeys: never erased to make room. rc.4 (R1-06): the
    // "owned" note is written the same way.
    bool writeGated(const std::string& text) const {
        return !text.empty() && text.size() < 64 && optionalHeatingRecordFits(key, text.size() + 1) && write(text);
    }
};
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
