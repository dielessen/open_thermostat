#pragma once
#include <cassert>
#include "../../onboarding/include/nvs.h"
struct nvs_stats_t {size_t used_entries,free_entries,total_entries,namespace_count;};
namespace testBluetoothStorage {
inline nvs_stats_t stats{40,590,630,4};
inline bool failStats=false;
inline unsigned statsCalls=0;
}
inline int nvs_get_stats(const char* partition,nvs_stats_t* out) {
    assert(std::string(partition)=="nvs");++testBluetoothStorage::statsCalls;
    if(testBluetoothStorage::failStats)return 2;
    *out=testBluetoothStorage::stats;return ESP_OK;
}
