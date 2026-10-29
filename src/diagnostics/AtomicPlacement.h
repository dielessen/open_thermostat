#pragma once
#include <cstdint>
#ifdef ESP_PLATFORM
#include <soc/soc_memory_types.h>
#endif

namespace heating::diagnostics {
// On the ESP32 the read-modify-write atomics (exchange, fetch_add,
// compare_exchange, shared_ptr reference counts) compile to S32C1I retry
// loops, and S32C1I is not atomic on external RAM: ESP-IDF's own spinlocks
// switch to a locked software path there (compare_and_set_extram). Plain
// atomic loads and stores are fine in PSRAM. With CONFIG_SPIRAM_USE_MALLOC an
// object over 4096 bytes (the heating controller) is allocated in PSRAM, so
// its RMW atomics are static members (.bss, internal RAM). Checked at boot;
// the count is reported as runtime.atomics_in_psram in /status/logs.
inline bool inExternalRam([[maybe_unused]] const void* p) {
#ifdef ESP_PLATFORM
    return esp_ptr_external_ram(p);
#else
    return false;
#endif
}

// visitAll(visit) calls visit(name, address) once per RMW atomic; report(name,
// address) runs for each one in external RAM. Returns how many are there.
template<class VisitAll, class IsExternal, class Report>
uint32_t countAtomicsInPsram(VisitAll&& visitAll, IsExternal&& isExternal, Report&& report) {
    uint32_t count = 0;
    visitAll([&](const char* name, const void* address) {
        if (!isExternal(address)) return;
        if (count != UINT32_MAX) ++count;
        report(name, address);
    });
    return count;
}

// Written once in setup(), read by the /status/logs handler (both loop task).
inline uint32_t atomicsInPsram = 0;
}
