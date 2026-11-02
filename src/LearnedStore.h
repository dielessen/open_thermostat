#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "NvsOptionalRecords.h"
#include "control/LearnedState.h"
#include "control/OptionalRecordPriority.h"
#include <cstring>
#include <string>
#include <string_view>
namespace heating {
// The learned state (control/LearnedState.h) beside the room plan as one packed
// record of at most two blobs: "ot_heating"/"learned_a" (the global frame and
// the first rooms, ~1.8 KB for 8 rooms of 6 bins) and "learned_b" (rooms that
// do not fit 4000 bytes). Each blob is read back after the commit. When to
// write: control::LearnedStore. NVS short of room or a failed write: false, the
// old blob stays. Written only while control's records keep their room
// (ControlPartitionBudget::permitsOptionalWrite) and, before these bulky frames,
// the automatic knobs (without their log) and the readiness counters theirs.
// Earlier rc.2 builds kept one key per frame ("learned", "learned0".."learned7"):
// read when no part exists, erased by control::LearnedStore once migrated.
struct LearnedNvs final : control::LearnedStore::Backend {
    static constexpr const char* partKeys[control::LearnedStore::parts] = {"learned_a", "learned_b"};
    static void legacyKey(size_t slot, char (&k)[10]) {
        std::memcpy(k, "learned", 8);
        if (slot) { k[7] = char('0' + slot - 1); k[8] = 0; }
    }
    static bool readKey(const char* key, std::string& out, size_t cap) {
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return false;
        size_t size = 0;
        bool found = nvs_get_blob(handle, key, nullptr, &size) == ESP_OK;
        // Too large: present (replaced or erased at the next save), never loaded.
        out.assign(found && size <= cap ? size : 0, '\0');
        if (found && !out.empty() && nvs_get_blob(handle, key, out.data(), &size) != ESP_OK) out.clear();
        nvs_close(handle);
        return found;
    }
    static bool eraseKey(const char* key) {
        nvs_handle_t handle;
        const auto opened = nvs_open("ot_heating", NVS_READWRITE, &handle);
        if (opened == ESP_ERR_NVS_NOT_FOUND) return true;
        if (opened != ESP_OK) return false;
        const esp_err_t e = nvs_erase_key(handle, key);
        const bool ok = (e == ESP_OK || e == ESP_ERR_NVS_NOT_FOUND) && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return ok;
    }
    bool read(size_t part, std::string& out) override {
        return part < control::LearnedStore::parts && readKey(partKeys[part], out, control::LearnedStore::partBytes);
    }
    bool write(size_t part, std::string_view bytes) override {
        if (part >= control::LearnedStore::parts) return false;
        const char* key = partKeys[part];
        const size_t priority = control::OptionalRecordPriority::learned(
            storedNvsRecordBytes("ot_heating", "autotune", control::ControlPartitionBudget::configBytes) != 0,
            storedNvsBlobBytes("ot_heating", "readiness", control::ControlPartitionBudget::configBytes) != 0);
        if (!optionalHeatingRecordFits(key, bytes.size(), priority)) return false; // logged by the caller
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_blob(handle, key, bytes.data(), bytes.size()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        std::string back;
        return committed && read(part, back) && back == bytes;
    }
    bool erase(size_t part) override { return part < control::LearnedStore::parts && eraseKey(partKeys[part]); }
    bool readLegacy(size_t slot, std::string& out) override {
        char k[10]; legacyKey(slot, k);
        return slot < control::LearnedStore::legacySlots && readKey(k, out, control::LearnedState::maxFrame);
    }
    bool eraseLegacy(size_t slot) override {
        char k[10]; legacyKey(slot, k);
        return slot < control::LearnedStore::legacySlots && eraseKey(k);
    }
};
}
#endif
