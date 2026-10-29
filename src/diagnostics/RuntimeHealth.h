#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <cJSON.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <nvs.h>
#include <cstdint>
#include "AtomicPlacement.h"

namespace heating::diagnostics {
// Live resource figures for /status/logs and the black box. Stack values are
// high-water marks in bytes (ESP-IDF StackType_t is a byte): the smallest
// amount of stack a task has had left since it started. 0 = task not found.
struct TaskStackMarks { uint32_t loop = 0, supervisor = 0, emsUart = 0, bluetoothHost = 0; };
inline uint32_t stackMark(const char* name) {
    const TaskHandle_t task = xTaskGetHandle(name);
    return task ? static_cast<uint32_t>(uxTaskGetStackHighWaterMark(task)) : 0;
}
inline TaskStackMarks taskStackMarks() {
    TaskStackMarks marks;
    marks.loop = stackMark("loopTask");
    marks.supervisor = stackMark("supervisor");
    marks.emsUart = stackMark("EmsBusUart");
    marks.bluetoothHost = stackMark("nimble_host");
    return marks;
}
inline uint32_t largestInternalBlock() {
    return static_cast<uint32_t>(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
}
// {"free_internal_bytes":..,"minimum_free_internal_bytes":..,"largest_internal_block_bytes":..,
//  "stack_minimum_bytes":{...},"nvs":{"used_entries":..,"free_entries":..,"total_entries":..}|null}
inline cJSON* runtimeHealthJson() {
    cJSON* root = cJSON_CreateObject();
    if (!root) return nullptr;
    cJSON_AddNumberToObject(root, "free_internal_bytes", heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    cJSON_AddNumberToObject(root, "minimum_free_internal_bytes", heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    cJSON_AddNumberToObject(root, "largest_internal_block_bytes", largestInternalBlock());
    cJSON_AddNumberToObject(root, "free_psram_bytes", heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    cJSON_AddNumberToObject(root, "atomics_in_psram", atomicsInPsram); // 0 expected, see AtomicPlacement.h
    const auto marks = taskStackMarks();
    if (cJSON* stacks = cJSON_AddObjectToObject(root, "stack_minimum_bytes")) {
        cJSON_AddNumberToObject(stacks, "loop", marks.loop);
        cJSON_AddNumberToObject(stacks, "supervisor", marks.supervisor);
        cJSON_AddNumberToObject(stacks, "ems_uart", marks.emsUart);
        cJSON_AddNumberToObject(stacks, "bluetooth_host", marks.bluetoothHost);
    }
    nvs_stats_t stats{};
    if (nvs_get_stats("nvs", &stats) == ESP_OK) {
        if (cJSON* nvs = cJSON_AddObjectToObject(root, "nvs")) {
            cJSON_AddNumberToObject(nvs, "used_entries", stats.used_entries);
            cJSON_AddNumberToObject(nvs, "free_entries", stats.free_entries);
            cJSON_AddNumberToObject(nvs, "total_entries", stats.total_entries);
            cJSON_AddNumberToObject(nvs, "namespaces", stats.namespace_count);
        }
    } else cJSON_AddNullToObject(root, "nvs");
    return root;
}
}
#endif
