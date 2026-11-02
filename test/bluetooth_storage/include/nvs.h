#pragma once
#include <cassert>
#include <optional>
#include "../../onboarding/include/nvs.h"
struct nvs_stats_t {size_t used_entries,free_entries,total_entries,namespace_count;};
namespace testBluetoothStorage {
inline nvs_stats_t stats{40,590,630,4};
inline bool failStats=false;
inline unsigned statsCalls=0;
// Set: the statistics follow the committed records (a fixed baseline plus each record as NVS
// stores it: an index, a chunk header and its 32-byte entries), so erasing one frees room.
inline std::optional<size_t> baseline;
inline size_t usedEntries() {
    size_t n=*baseline;
    for(const auto& [space,values]:testNvs::committed) for(const auto& [key,value]:values) n+=2+(value.size()+31)/32;
    return n<630?n:630;
}
}
inline int nvs_get_stats(const char* partition,nvs_stats_t* out) {
    assert(std::string(partition)=="nvs");++testBluetoothStorage::statsCalls;
    if(testBluetoothStorage::failStats)return 2;
    if(testBluetoothStorage::baseline){const size_t used=testBluetoothStorage::usedEntries();*out={used,630-used,630,4};return ESP_OK;}
    *out=testBluetoothStorage::stats;return ESP_OK;
}
