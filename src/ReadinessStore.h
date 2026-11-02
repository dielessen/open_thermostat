#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "NvsOptionalRecords.h"
#include "control/TakeoverReadiness.h"
#include <cstring>
namespace heating {
// The takeover readiness counters (control/TakeoverReadiness.h) as one blob
// beside the room plan ("ot_heating"/"readiness", ~200 bytes): written at a day
// change, every 6 hours and before a planned restart, read back after the
// commit. Absent or of another version: counting starts again. Only while
// control's records keep their room (ControlPartitionBudget::permitsOptionalWrite).
struct ReadinessNvs {
    static constexpr const char* key = "readiness";
    static bool read(control::TakeoverReadiness::Stored& out) {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return false;
        control::TakeoverReadiness::Stored s;
        size_t size = sizeof(s);
        const bool ok = nvs_get_blob(handle, key, &s, &size) == ESP_OK && size == sizeof(s)
            && s.version == control::TakeoverReadiness::Stored::currentVersion && s.size == sizeof(s);
        nvs_close(handle);
        if (ok) out = s;
        return ok;
    }
    static bool write(const control::TakeoverReadiness::Stored& s) {
        if (!optionalHeatingRecordFits(key, sizeof(s))) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_blob(handle, key, &s, sizeof(s)) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        control::TakeoverReadiness::Stored back;
        return committed && read(back) && std::memcmp(&back, &s, sizeof(s)) == 0;
    }
};
}
#endif
