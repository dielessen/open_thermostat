#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
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
// An optional record of `bytes` may be written: the handover confirmation, the flow
// record and a plan or Bluetooth save of their stored size keep their room.
inline bool optionalHeatingRecordFits(size_t bytes, size_t priority = 0) {
    using B = control::ControlPartitionBudget;
    return B::permitsOptionalWrite(nvsPartitionStats(), bytes, storedNvsBlobBytes("ot_heating", "plan", B::configBytes),
                                   storedNvsBlobBytes("ot_bluetooth", "settings", B::bluetoothBytes),
                                   control::controlModelStorageReservation.current(), priority);
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
}
#endif
