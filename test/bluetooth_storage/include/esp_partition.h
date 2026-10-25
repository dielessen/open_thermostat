#pragma once
#include <cassert>
#include <string>
#include "nvs.h"
constexpr int ESP_PARTITION_TYPE_DATA=1,ESP_PARTITION_SUBTYPE_DATA_NVS=2;
struct esp_partition_t {size_t size;};
namespace testBluetoothStorage {inline bool missingPartition=false;inline size_t partitionBytes=20480;}
inline const esp_partition_t* esp_partition_find_first(int type,int subtype,const char* label) {
    assert(type==ESP_PARTITION_TYPE_DATA&&subtype==ESP_PARTITION_SUBTYPE_DATA_NVS&&std::string(label)=="nvs");
    static esp_partition_t partition;
    if(testBluetoothStorage::missingPartition)return nullptr;
    partition.size=testBluetoothStorage::partitionBytes;return &partition;
}
