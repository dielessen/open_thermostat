#pragma once
#include <string>

namespace heating::update {
// A requested rollback (POST /updates/rollback; review R2-04) in an order that never loses what
// was learned for nothing. The other slot can be marked valid in otadata while its image is gone
// (a failed or aborted update erases it sector by sector), so first its app description must read
// back (magic word, a version), then the bootloader must accept it (esp_ota_set_boot_partition
// verifies the image), and only then are the optional NVS records frozen and erased for the
// previous firmware. A failure leaves NVS as it was.
// Backend: bool describe(std::string& version); bool select(); void prepareNvs().
template<class Backend> bool runRollback(Backend& backend) {
    std::string version;
    if (!backend.describe(version) || version.empty()) return false;
    if (!backend.select()) return false;
    backend.prepareNvs();
    return true;
}
}
