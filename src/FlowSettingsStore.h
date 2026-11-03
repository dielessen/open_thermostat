#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "control/AutoTuner.h"
#include "control/BoundedJson.h"
#include "control/FlowPolicy.h"
#include "control/OptionalRecordPriority.h"
#include "NvsOptionalRecords.h"
#include <cstring>
#include <memory>
#include <new>
#include <string>
namespace heating {
// The beta.19 flow options (control/FlowPolicy.h FlowSettings) as one short NVS
// string beside the room plan ("ot_heating"/"flow"), read back after the commit.
// Absent or unreadable: the defaults (Smart warm-up and the weather curve on).
// rc.3: FlowSettings::stored(), which rc.2 still reads after a rollback; a record
// of rc.2 or older reads apply_learned and weather_curve as on (FlowSettings::readStored()).
struct FlowSettingsNvs {
    static constexpr const char* key = "flow";
    static control::FlowSettings read() {
        control::FlowSettings settings;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return settings;
        char text[control::FlowSettings::maxBytes + 1] = {};
        size_t size = sizeof(text);
        const bool ok = nvs_get_str(handle, key, text, &size) == ESP_OK;
        nvs_close(handle);
        if (!ok) return settings;
        control::FlowSettings parsed;
        return control::FlowSettings::readStored(text, std::strlen(text), parsed) ? parsed : settings;
    }
    static bool write(const control::FlowSettings& settings) {
        const auto record = settings.stored();
        if (record.size() > control::FlowSettings::rc2StoredMaxBytes) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed && read() == settings;
    }
};
// The automatic knobs and their change log (control/AutoTuner.h) beside it
// ("ot_heating"/"autotune"): written when a day changed them (at most daily) or
// on "back to start values". Absent or unreadable: the built-in values. Only while
// control's records keep their room: the values with as many of the newest log
// entries as fit (ControlPartitionBudget::permitsOptionalWrite; the log after what
// was learned, control/OptionalRecordPriority.h: `learnedPending`, the entries the
// learned record still needs); none: false.
struct AutoTunerNvs {
    static constexpr const char* key = "autotune";
    static void read(control::AutoTuner& tuner) {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return;
        std::unique_ptr<char[]> text(new (std::nothrow) char[control::AutoTuner::storedMaxBytes + 1]());
        size_t size = control::AutoTuner::storedMaxBytes + 1;
        const bool ok = text && nvs_get_str(handle, key, text.get(), &size) == ESP_OK;
        nvs_close(handle);
        if (ok) tuner.restore(text.get());
    }
    static bool write(const control::AutoTuner& tuner, size_t learnedPending = 0) {
        std::string record;
        for (size_t log = control::AutoTuner::logSize + 1; log-- > 0 && record.empty();) {
            record = tuner.stored(log);
            if (record.size() > control::AutoTuner::storedMaxBytes
                || !optionalHeatingRecordFits(key, record.size() + 1, log ? control::OptionalRecordPriority::tuningLog(learnedPending) : 0)) record.clear();
        }
        if (record.empty()) return false;
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_str(handle, key, record.c_str()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return committed;
    }
};
}
#endif
