#pragma once
#include <string>
#include <string_view>
namespace heating::control {
// The owner's "thermostat disconnected" confirmation survives a restart
// (owner, 29 Oct): stored with the firmware it was given under, so a firmware
// change asks again. Restored once at boot; erased as soon as the guard drops
// it (a foreign 0x1A, the hand-back, the plan back to shadow). After a restore
// the guard still listens bootHoldoffMs for a foreign 0x1A before it heats.
// beta.23: a confirmation of other firmware becomes the record "reconfirm":
// the E32 owned the boiler before the update, so it sends a boot zero, keeps
// frost protection and HA asks the owner to confirm again; the hand-back, the
// plan back to shadow or a foreign 0x1A erase it. Older firmware erases it as
// a record of other firmware.
// Store: std::string read() ("" = none), bool write(std::string_view), bool erase().
template<class Store>
class HandoverConfirmation {
public:
    enum class Restored { none, confirmed, reconfirm };
    static constexpr std::string_view reconfirmRecord = "reconfirm";
    HandoverConfirmation(Store& store, std::string firmware) : store_(store), firmware_(std::move(firmware)) {}
    // At boot: confirmed under this firmware, owned the boiler under other
    // firmware (reconfirm), or none. Without a firmware identity nothing binds:
    // a record is erased and nothing is restored.
    Restored restoreState() {
        const std::string record = store_.read();
        stored_ = pending_ = false;
        if (record.empty()) return Restored::none;
        if (firmware_.empty()) { store_.erase(); return Restored::none; }
        if (record == firmware_) { stored_ = true; return Restored::confirmed; }
        // A confirmation of other firmware, or already waiting for a new one. A failed
        // write still waits for this boot; sync() writes it again.
        pending_ = record == reconfirmRecord || store_.write(reconfirmRecord);
        return Restored::reconfirm;
    }
    // The older form: true when confirmed under this firmware (a reconfirm stays stored).
    bool restore() { return restoreState() == Restored::confirmed; }
    // After each guard step: the store follows the guard. A failed write retries next step.
    // reconfirm: the guard waits for a new confirmation after a firmware change.
    void sync(bool confirmed, bool reconfirm = false) {
        if (confirmed) {
            if (stored_ || firmware_.empty()) return;
            if (store_.write(firmware_)) { stored_ = true; pending_ = false; }
            return;
        }
        if (reconfirm) {
            if (pending_ && !stored_) return;
            if (store_.write(reconfirmRecord)) { pending_ = true; stored_ = false; }
            return;
        }
        if (!stored_ && !pending_) return;
        if (store_.erase()) stored_ = pending_ = false;
    }
    bool stored() const { return stored_; }
    bool pending() const { return pending_; }

private:
    Store& store_;
    std::string firmware_;
    bool stored_ = false, pending_ = false;
};
}
