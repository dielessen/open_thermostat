#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "HeatingPlanStore.h"
#include "control/ControlPartitionBudget.h"
#include "control/RoomOverrides.h"
#include <string>
namespace heating {
// rc.4: the planned holidays and the holiday temperature (RoomOverrides::holidaysStored()) as
// their own short record beside the comfort record ("ot_heating"/"holidays"), so the comfort
// record keeps the form an older firmware reads after a rollback. Gated like an optional record,
// with the room the ledger keeps for it (ControlPartitionBudget::holidayEntries()); read back
// after the commit. Absent: no holidays (or the dated away of the comfort record, see restore()).
struct HolidaysNvs {
    using B = control::ControlPartitionBudget;
    static_assert(control::RoomOverrides::holidayStoreBytes < B::holidayRecordBytes, "the holidays record with its NUL");
    static_assert(B::holidayRecordBytes <= HeatingNoteNvs::largestBytes, "a note HeatingNoteNvs can read");
    static constexpr const char* key = "holidays";
    static std::string read() { return HeatingNoteNvs{key, B::holidayRecordBytes}.read(); }
    static bool write(const std::string& record) {
        return HeatingNoteNvs{key, B::holidayRecordBytes, B::holidayEntries()}.writeGated(record);
    }
};
// The room overrides and away (control/RoomOverrides.h) as one short versioned
// NVS string beside the room plan ("ot_heating"/"comfort"), written only by a
// command that changes it and read back after the commit. Absent or unreadable:
// nothing temporary (every room follows its plan).
struct RoomOverridesNvs {
    static constexpr const char* key = "comfort";
    static std::string read() {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return {};
        char text[control::RoomOverrides::storeBytes + 1] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        return ok ? std::string(text) : std::string();
    }
    static bool write(const std::string& record) {
        if (record.empty() || record.size() > control::RoomOverrides::storeBytes) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == record;
    }
};
}
#endif
