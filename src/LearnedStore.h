#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include "control/LearnedState.h"
#include <cstring>
#include <string>
#include <string_view>
namespace heating {
// The learned state (control/LearnedState.h) beside the room plan:
// "ot_heating"/"learned" (global, ~0.25 KB) and "learned0".."learned7" (one per
// plan room, 0.1..0.95 KB), each blob read back after the commit. When to
// write: control::LearnedStore. NVS full or a failed write: false, the old
// blob stays.
struct LearnedNvs final : control::LearnedStore::Backend {
    static void key(size_t slot, char (&k)[10]) {
        std::memcpy(k, "learned", 8);
        if (slot) { k[7] = char('0' + slot - 1); k[8] = 0; }
    }
    bool read(size_t slot, std::string& out) override {
        char k[10]; key(slot, k);
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READONLY, &handle) != ESP_OK) return false;
        size_t size = 0;
        bool found = nvs_get_blob(handle, k, nullptr, &size) == ESP_OK;
        // Too large for a frame: present (erased at the next save), never loaded.
        out.assign(found && size <= control::LearnedState::maxFrame ? size : 0, '\0');
        if (found && !out.empty() && nvs_get_blob(handle, k, out.data(), &size) != ESP_OK) out.clear();
        nvs_close(handle);
        return found;
    }
    bool write(size_t slot, std::string_view bytes) override {
        char k[10]; key(slot, k);
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const bool committed = nvs_set_blob(handle, k, bytes.data(), bytes.size()) == ESP_OK && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        std::string back;
        return committed && read(slot, back) && back == bytes;
    }
    bool erase(size_t slot) override {
        char k[10]; key(slot, k);
        nvs_handle_t handle;
        if (nvs_open("ot_heating", NVS_READWRITE, &handle) != ESP_OK) return false;
        const esp_err_t e = nvs_erase_key(handle, k);
        const bool ok = (e == ESP_OK || e == ESP_ERR_NVS_NOT_FOUND) && nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
        return ok;
    }
};
}
#endif
