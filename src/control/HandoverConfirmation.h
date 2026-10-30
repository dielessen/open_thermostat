#pragma once
#include <string>
#include <string_view>
namespace heating::control {
// The owner's "thermostat disconnected" confirmation survives a restart
// (owner, 29 Oct): stored with the firmware it was given under, so a firmware
// change asks again. Restored once at boot; erased as soon as the guard drops
// it (a foreign 0x1A, the hand-back, the plan back to shadow). After a restore
// the guard still listens bootHoldoffMs for a foreign 0x1A before it heats.
// Store: std::string read() ("" = none), bool write(std::string_view), bool erase().
template<class Store>
class HandoverConfirmation {
public:
    HandoverConfirmation(Store& store, std::string firmware) : store_(store), firmware_(std::move(firmware)) {}
    // At boot. True: confirmed under this firmware. A record of other firmware is erased.
    bool restore() {
        const std::string record = store_.read();
        stored_ = !record.empty();
        if (stored_ && (firmware_.empty() || record != firmware_)) stored_ = !store_.erase();
        return stored_;
    }
    // After each guard step: the store follows the guard. A failed write retries next step.
    void sync(bool confirmed) {
        if (confirmed == stored_ || (confirmed && firmware_.empty())) return;
        if (confirmed ? store_.write(firmware_) : store_.erase()) stored_ = confirmed;
    }
    bool stored() const { return stored_; }

private:
    Store& store_;
    std::string firmware_;
    bool stored_ = false;
};
}
