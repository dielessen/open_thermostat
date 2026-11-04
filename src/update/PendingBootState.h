#pragma once
#include <atomic>
#include <cstdint>

namespace heating::update {
// Whether this boot still waits for its confirmation (the running image is
// ESP_OTA_IMG_PENDING_VERIFY), read once (review R2-01): esp_ota_get_state_partition maps and
// unmaps the otadata partition, which suspends the flash cache of both CPUs, and REST asked it
// about 2000 times a second through update::mutationBlocked(). The running slot's state changes
// only when this firmware confirms itself (confirmed()); a rollback restarts. Any task may ask:
// the first answer is kept unless the confirmation came first.
class PendingBootState {
public:
    // read(): true while the running image is pending verification (called at most once).
    template<class Read> bool pending(Read&& read) {
        int8_t state = state_.load(std::memory_order_acquire);
        if (state < 0) {
            int8_t unknown = -1;
            state_.compare_exchange_strong(unknown, read() ? int8_t(1) : int8_t(0), std::memory_order_acq_rel);
            state = state_.load(std::memory_order_acquire);
        }
        return state == 1;
    }
    void confirmed() { state_.store(0, std::memory_order_release); }

private:
    std::atomic<int8_t> state_{-1}; // -1 not read yet, 1 pending, 0 confirmed (or never an OTA boot)
};
}
