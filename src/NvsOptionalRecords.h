#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include "control/ControlPartitionBudget.h"
#include "control/ControlModelStorageReservation.h"
#include <algorithm>
#include <atomic>
#include <cstdint>
namespace heating {
// The rc.2 optional NVS records (learned, autotune, readiness) against what
// control needs (control/ControlPartitionBudget.h permitsOptionalWrite).

// Fresh partition statistics (invalid when unreadable).
inline control::ControlPartitionStats nvsPartitionStats() {
    nvs_stats_t stats{};
    const auto partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_NVS, "nvs");
    if (!partition || nvs_get_stats("nvs", &stats) != ESP_OK) return {};
    return {partition->size, stats.total_entries, stats.used_entries, stats.free_entries, true};
}
// A stored blob's size (0: none), at most `cap`.
inline size_t storedNvsBlobBytes(const char* space, const char* key, size_t cap) {
    nvs_handle_t handle;
    if (nvs_open(space, NVS_READONLY, &handle) != ESP_OK) return 0;
    size_t size = 0;
    if (nvs_get_blob(handle, key, nullptr, &size) != ESP_OK) size = 0;
    nvs_close(handle);
    return std::min(size, cap);
}
// A stored blob's or string's size (0: none), at most `cap`.
inline size_t storedNvsRecordBytes(const char* space, const char* key, size_t cap) {
    if (const size_t blob = storedNvsBlobBytes(space, key, cap)) return blob;
    nvs_handle_t handle;
    if (nvs_open(space, NVS_READONLY, &handle) != ESP_OK) return 0;
    size_t size = 0;
    if (nvs_get_str(handle, key, nullptr, &size) != ESP_OK) size = 0;
    nvs_close(handle);
    return std::min(size, cap);
}
// The control record's replacement kept free (ControlPartitionBudget::controlReplacementEntries):
// its stored size plus an edit, a full one while a graph/native control profile is configured.
inline size_t controlReplacementEntries() {
    return control::ControlPartitionBudget::controlReplacementEntries(
        storedNvsBlobBytes("ot_control", "config", control::ControlPartitionBudget::configBytes),
        control::graphControlStorage.load());
}
// Set before a requested rollback (prepareNvsForPreviousFirmware): no optional record is written
// any more this boot; the previous firmware finds the room its own gates expect.
inline std::atomic<bool>& optionalRecordsFrozen() { static std::atomic<bool> frozen{false}; return frozen; }
// This boot is not confirmed yet: the bootloader may still return to the previous firmware.
inline bool nvsBootUnconfirmed() {
    esp_ota_img_states_t state;
    const auto running = esp_ota_get_running_partition();
    return running && esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY;
}
// What control needs kept free after an optional record: this firmware's ledger, or while the boot
// is unconfirmed the previous firmware's (ControlPartitionBudget::previousFirmwareReserveEntries).
// `reserved`: entries this firmware's ledger keeps for the record being written itself (the
// holidays record), not charged again; the previous firmware's ledger keeps nothing for it.
inline size_t optionalRecordReserve(size_t reserved = 0) {
    using B = control::ControlPartitionBudget;
    const size_t plan = storedNvsBlobBytes("ot_heating", "plan", B::configBytes);
    if (nvsBootUnconfirmed())
        return B::previousFirmwareReserveEntries(plan, storedNvsBlobBytes("ot_bluetooth", "settings", B::bluetoothBytes));
    const size_t reserve = B::controlReserveEntries(plan, controlReplacementEntries(), control::controlModelStorageReservation.current());
    return reserve == SIZE_MAX ? reserve : reserve - std::min(reserve, reserved);
}
// An optional record of `bytes` may replace "ot_heating"/`key`: the handover confirmation, the flow
// record, a plan save, a 2 KB Bluetooth save and the control record's replacement keep their room.
inline bool optionalHeatingRecordFits(const char* key, size_t bytes, size_t priority = 0, size_t reserved = 0) {
    using B = control::ControlPartitionBudget;
    if (optionalRecordsFrozen().load()) return false;
    return B::permitsOptionalWrite(nvsPartitionStats(), bytes, storedNvsRecordBytes("ot_heating", key, B::configBytes),
                                   optionalRecordReserve(reserved), priority);
}
// Counts the optional records erased to make room; their owner writes again what fits.
inline std::atomic<uint32_t>& optionalRecordEvictions() { static std::atomic<uint32_t> count{0}; return count; }
// Control first: erases optional records, the least useful first, until permits(stats)
// holds (ControlPartitionBudget::makeRoom). Without the namespace nothing is created.
template <class Permits> bool makeNvsRoom(Permits&& permits) {
    const auto stats = nvsPartitionStats();
    if (permits(stats)) return true;
    nvs_handle_t read, write = 0;
    if (!stats.valid || nvs_open("ot_heating", NVS_READONLY, &read) != ESP_OK) return false;
    bool writable = false;
    const auto bytes = [&](const char* key) -> size_t {
        size_t n = 0;
        if (nvs_get_blob(read, key, nullptr, &n) == ESP_OK) return n;
        n = 0;
        return nvs_get_str(read, key, nullptr, &n) == ESP_OK ? n : 0; // "autotune" is a string
    };
    const bool room = control::ControlPartitionBudget::makeRoom(permits, nvsPartitionStats, bytes, [&](const char* key) {
        if (!writable) writable = nvs_open("ot_heating", NVS_READWRITE, &write) == ESP_OK;
        if (writable && nvs_erase_key(write, key) == ESP_OK && nvs_commit(write) == ESP_OK) optionalRecordEvictions().fetch_add(1);
    });
    if (writable) nvs_close(write);
    nvs_close(read);
    return room;
}
// Before a requested rollback (update::requestRollback): the previous firmware (beta.22, rc.1)
// reads none of the learned or tuning records and gates its plan and Bluetooth saves with a full
// control replacement. Freeze the optional records and erase them, the least useful first, until
// that firmware's ledger holds. False: still short (a plan save there may answer storage_full).
inline bool prepareNvsForPreviousFirmware() {
    using B = control::ControlPartitionBudget;
    optionalRecordsFrozen().store(true);
    const size_t plan = storedNvsBlobBytes("ot_heating", "plan", B::configBytes);
    const size_t ble = storedNvsBlobBytes("ot_bluetooth", "settings", B::bluetoothBytes);
    return makeNvsRoom([&](control::ControlPartitionStats s) {
        return s.valid && s.freeEntries >= B::previousFirmwareReserveEntries(plan, ble); });
}
// Keys no firmware since the first tagged release (alpha.1) reads: the generated access
// secret of the untagged October builds ("ot_access"/"secret", 32 bytes; DeviceAccess.h
// ignores it). Erased once at boot when present; true: one was erased (logged by the caller).
inline bool eraseStaleNvsKeys() {
    nvs_handle_t handle;
    if (nvs_open("ot_access", NVS_READONLY, &handle) != ESP_OK) return false;
    size_t size = 0;
    const bool present = nvs_get_blob(handle, "secret", nullptr, &size) == ESP_OK;
    nvs_close(handle);
    if (!present || nvs_open("ot_access", NVS_READWRITE, &handle) != ESP_OK) return false;
    const bool erased = nvs_erase_key(handle, "secret") == ESP_OK && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return erased;
}
}
#endif
