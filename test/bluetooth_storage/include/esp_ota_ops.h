#pragma once
#include "esp_partition.h"
// The running image's OTA state (NvsOptionalRecords.h nvsBootUnconfirmed).
enum esp_ota_img_states_t { ESP_OTA_IMG_NEW = 0, ESP_OTA_IMG_PENDING_VERIFY = 1, ESP_OTA_IMG_VALID = 2, ESP_OTA_IMG_INVALID = 3 };
namespace testBluetoothStorage { inline bool bootPending = false; }
inline const esp_partition_t* esp_ota_get_running_partition() { static esp_partition_t running{0x380000}; return &running; }
inline int esp_ota_get_state_partition(const esp_partition_t* partition, esp_ota_img_states_t* state) {
    if (!partition || !state) return 2;
    *state = testBluetoothStorage::bootPending ? ESP_OTA_IMG_PENDING_VERIFY : ESP_OTA_IMG_VALID;
    return ESP_OK;
}
