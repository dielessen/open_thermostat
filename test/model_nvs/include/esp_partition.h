#pragma once
#include "nvs.h"
constexpr int ESP_PARTITION_TYPE_DATA=1,ESP_PARTITION_SUBTYPE_DATA_NVS=2;
struct esp_partition_t {size_t size;};
inline const esp_partition_t* esp_partition_find_first(int,int,const char*){
 static esp_partition_t partition;
 if(modelNvsFixture::missingPartition)return nullptr;
 partition.size=modelNvsFixture::partitionBytes;return &partition;
}
