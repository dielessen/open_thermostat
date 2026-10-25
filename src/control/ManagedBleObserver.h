#pragma once
#include "BleDeviceConfig.h"
#include "ShellyHtDisplayAdvertisement.h"
#include "MiBeaconMonitor3Advertisement.h"
#include "ShellyTrvAdvertisement.h"
#include <atomic>
#include <mutex>

namespace heating::control {
enum class BleObserverStop { none, configuration_changed, configuration_invalid, clock_invalid };
enum class BleObservationStatus { waiting, key_required, received, stale, malformed, authentication_failed,
    encryption_required, crypto_unavailable, pending_restart, configuration_invalid, clock_invalid };
struct BleObservationSnapshot {
    BleObservationStatus status = BleObservationStatus::waiting;
    std::optional<int16_t> temperature, humidity, targetTemperature, externalTemperature;
    std::optional<uint8_t> stateRevision;
    std::optional<uint32_t> targetTemperatureAgeMs, externalTemperatureAgeMs, stateRevisionAgeMs;
    std::optional<uint8_t> battery, lightLevel, button;
    std::optional<bool> batteryLow, light;
    std::optional<uint32_t> temperatureAgeMs, humidityAgeMs, batteryAgeMs, lastAcceptedAgeMs, counter;
    std::optional<uint16_t> declaredDeviceType;
    std::optional<uint32_t> firmware32, firmware24;
    std::optional<uint32_t> declaredDeviceAgeMs;
    std::optional<int8_t> rssi;
    uint32_t oldCounterDrops = 0;
    bool authenticated = false; // integrity of accepted messages, NOT acquisition qualification
    static constexpr bool measurementQualified = false;
    static constexpr bool authorizesActuation = false;
};

// Same existing main loop processes at most one bounded frame per invocation.
// SDK callback only copies selected addresses into a fixed queue; no AES/JSON/IO
// runs there. Configuration is immutable until restart, with an irreversible stop.
template<class Decryptor>
class ManagedBleObserver {
public:
    using Clock = uint64_t(*)();
    static constexpr std::size_t queueCapacity = 4;
    static constexpr uint64_t valueLifetimeMs = 180000, identityLifetimeMs = 3900000;
    static constexpr uint64_t maximumClockMs = 9007199254740991ULL;
    ManagedBleObserver(Decryptor& decryptor, Clock clock) : decryptor_(decryptor), clock_(clock) {}
    ~ManagedBleObserver() { disable(BleObserverStop::configuration_changed); }
    ManagedBleObserver(const ManagedBleObserver&) = delete;
    ManagedBleObserver& operator=(const ManagedBleObserver&) = delete;

    bool initialize(const ManagedBleBindings& bindings) {
        if (initialized_) { disable(BleObserverStop::configuration_changed); return false; }
        initialized_ = true;
        if (bindings.count > bindings.capacity) { disable(BleObserverStop::configuration_invalid); return false; }
        for (std::size_t i = 0; i < bindings.count; ++i) {
            const auto& value = bindings.devices[i];
            if (!validManagedBleBinding(value)) {
                disable(BleObserverStop::configuration_invalid); return false;
            }
            for (std::size_t j = 0; j < i; ++j) if (bindings.devices[j].address == value.address) {
                disable(BleObserverStop::configuration_invalid); return false;
            }
        }
        bindings_ = bindings;
        bindings_.sort();
        enabled_.store(true, std::memory_order_release);
        return true;
    }
    void disable(BleObserverStop reason) noexcept {
        enabled_.store(false, std::memory_order_release);
        if (stop_ == BleObserverStop::none) stop_ = reason;
        auto generation = generation_.load(std::memory_order_relaxed);
        if (generation != UINT32_MAX) generation_.store(generation + 1, std::memory_order_release);
        {
            std::lock_guard<std::mutex> lock(queueMutex_);
            queued_ = 0; head_ = 0;
        }
        for (auto& binding : bindings_.devices) { wipeBleKey(binding.key); binding.hasKey = false; }
        for (auto& value : values_) withdraw(value);
        workspace_.plaintext.fill(0);
        decryptor_.clear();
    }
    bool enabled() const noexcept { return enabled_.load(std::memory_order_acquire); }
    bool wantsAutomaticScan() const noexcept { return enabled() && bindings_.count; }
    BleObserverStop stopReason() const noexcept { return stop_; }
    bool matches(const ManagedBleBindings& bindings) const noexcept { return bindings_.same(bindings); }

    void capture(const ManagedBleAddress& address, int rssi, const uint8_t* bytes,
            std::size_t size, uint64_t receivedAt) {
        if (!enabled_.load(std::memory_order_acquire) || !bytes || !size || size > 255) return;
        const auto generation = generation_.load(std::memory_order_acquire);
        std::size_t index = bindings_.count;
        for (std::size_t i = 0; i < bindings_.count; ++i) if (bindings_.devices[i].address == address) { index = i; break; }
        if (index == bindings_.count) return;
        std::lock_guard<std::mutex> lock(queueMutex_);
        if (!enabled() || generation != generation_.load(std::memory_order_acquire)) return;
        if (queued_ == queueCapacity) { if (queueDrops_ != UINT32_MAX) ++queueDrops_; return; }
        auto& frame = queue_[(head_ + queued_) % queueCapacity];
        std::copy_n(bytes, size, frame.bytes.begin());
        frame.size = static_cast<uint16_t>(size); frame.device = static_cast<uint8_t>(index);
        frame.rssiKnown = rssi >= -127 && rssi <= 20;
        frame.rssi = frame.rssiKnown ? static_cast<int8_t>(rssi) : 0;
        frame.at = receivedAt; frame.generation = generation; ++queued_;
    }
    uint32_t queueDrops() const {
        std::lock_guard<std::mutex> lock(queueMutex_); return queueDrops_;
    }
    void processOne(bool paused = false) {
        if (!enabled() || paused) return;
        {
            std::lock_guard<std::mutex> lock(queueMutex_);
            if (!queued_) return;
            processing_ = queue_[head_]; head_ = (head_ + 1) % queueCapacity; --queued_;
        }
        const auto now = readClock();
        if (!now || !enabled() || processing_.generation != generation_.load(std::memory_order_acquire)) return;
        auto& frame = processing_;
        if (frame.at > *now || frame.at > maximumClockMs) { disable(BleObserverStop::clock_invalid); return; }
        if (*now - frame.at >= valueLifetimeMs || frame.device >= bindings_.count) return;
        auto& value = values_[frame.device];
        if (value.haveAccepted && frame.at < value.acceptedAt) return;
        const auto& binding = bindings_.devices[frame.device];
        // Rejection-only prefilter: unverified old counters never refresh values,
        // advance the high-water mark, or claim a newly authenticated replay.
        if (value.haveCounter) {
            std::optional<uint32_t> sequence;
            if(binding.encryption==ManagedBleEncryption::bthomeV2) {
                const auto raw=findBleServiceData(frame.bytes.data(),frame.size,0xfcd2);
                if(raw.status==BleServiceStatus::present&&raw.size>=11&&(raw.data[0]&1)) {
                    const auto p=raw.data+raw.size-8;
                    sequence=uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);
                }
            } else if(binding.encryption==ManagedBleEncryption::miBeaconV4V5) {
                const auto raw=inspectMiBeaconMonitor3(binding.address,frame.bytes.data(),frame.size);
                if(raw.status==BleSensorFrameStatus::decoded)sequence=raw.counter; // Rejection only, no authentication claim.
            }
            if(sequence&&*sequence<=value.highestCounter) {
                if(value.oldCounterDrops!=UINT32_MAX)++value.oldCounterDrops;
                return;
            }
        }
        const auto decoded=binding.profile==ManagedBleProfile::xiaomiMonitor3
            ? decodeBoundMiBeaconMonitor3Advertisement(binding.address,frame.bytes.data(),frame.size,
                binding.hasKey?&binding.key:nullptr,decryptor_,workspace_)
            : binding.profile==ManagedBleProfile::shellyTrv
            ? decodeBoundShellyTrvAdvertisement(binding.address,frame.bytes.data(),frame.size,
                binding.hasKey?&binding.key:nullptr,binding.encryption==ManagedBleEncryption::bthomeV2,decryptor_,workspace_)
            : decodeBoundShellyHtDisplayAdvertisement(binding.address,frame.bytes.data(),frame.size,
                binding.hasKey?&binding.key:nullptr,binding.encryption==ManagedBleEncryption::bthomeV2,decryptor_,workspace_);
        if (!readClock() || !enabled() || frame.generation != generation_.load(std::memory_order_acquire)) return;
        if (decoded.status == ShellyHtFrameStatus::not_present) return;
        if (decoded.status != ShellyHtFrameStatus::decoded) {
            withdraw(value);
            switch (decoded.status) {
                case ShellyHtFrameStatus::key_required: value.status = BleObservationStatus::key_required; break;
                case ShellyHtFrameStatus::encryption_required: value.status = BleObservationStatus::encryption_required; break;
                case ShellyHtFrameStatus::authentication_failed: value.status = BleObservationStatus::authentication_failed; break;
                case ShellyHtFrameStatus::crypto_unavailable: value.status = BleObservationStatus::crypto_unavailable; break;
                default: value.status = BleObservationStatus::malformed; break;
            }
            return;
        }
        if (decoded.encryptionCounter) {
            if (!decoded.authenticated || (value.haveCounter && *decoded.encryptionCounter <= value.highestCounter)) return;
            value.highestCounter = *decoded.encryptionCounter; value.haveCounter = true;
        }
        assign(value.frame.temperature, value.at[0], decoded.temperature, frame.at);
        assign(value.frame.humidity, value.at[1], decoded.humidity, frame.at);
        assign(value.frame.battery, value.at[2], decoded.battery, frame.at);
        assign(value.frame.batteryLow, value.at[3], decoded.batteryLow, frame.at);
        assign(value.frame.light, value.at[4], decoded.light, frame.at);
        assign(value.frame.lightLevel, value.at[5], decoded.lightLevel, frame.at);
        assign(value.frame.button, value.at[6], decoded.button, frame.at);
        assign(value.frame.firmware32, value.at[7], decoded.firmware32, frame.at);
        assign(value.frame.firmware24, value.at[8], decoded.firmware24, frame.at);
        assign(value.frame.declaredDeviceType, value.identityAt, decoded.declaredDeviceType, frame.at);
        assign(value.frame.targetTemperature,value.at[9],decoded.targetTemperature,frame.at);
        // A complete TRV temperature report without the optional external value
        // explicitly withdraws its prior external reading, not its age/TTL only.
        if(binding.profile==ManagedBleProfile::shellyTrv&&decoded.temperature&&!decoded.externalTemperature)
            value.frame.externalTemperature.reset();
        assign(value.frame.externalTemperature,value.at[10],decoded.externalTemperature,frame.at);
        assign(value.frame.stateRevision,value.at[11],decoded.stateRevision,frame.at);
        value.acceptedAt = frame.at; value.haveAccepted = true; value.authenticated = decoded.authenticated;
        value.rssi = frame.rssiKnown ? std::optional<int8_t>(frame.rssi) : std::nullopt;
        value.status = BleObservationStatus::received;
    }
    BleObservationSnapshot snapshot(const ManagedBleAddress& address) {
        BleObservationSnapshot out;
        const auto now = readClock();
        if (stop_ != BleObserverStop::none || !now || !enabled()) {
            out.status = stop_ == BleObserverStop::clock_invalid ? BleObservationStatus::clock_invalid
                : stop_ == BleObserverStop::configuration_invalid ? BleObservationStatus::configuration_invalid
                : BleObservationStatus::pending_restart;
            return out;
        }
        std::size_t index = bindings_.count;
        for (std::size_t i = 0; i < bindings_.count; ++i) if (bindings_.devices[i].address == address) { index = i; break; }
        if (index == bindings_.count) { out.status = BleObservationStatus::pending_restart; return out; }
        const auto& value = values_[index];
        const auto& binding = bindings_.devices[index];
        out.status = value.status;
        if (!value.haveAccepted && value.status == BleObservationStatus::waiting
                && binding.encryption != ManagedBleEncryption::plain && !binding.hasKey) out.status = BleObservationStatus::key_required;
        if (value.haveAccepted) {
            out.lastAcceptedAgeMs = age(*now, value.acceptedAt);
            if (out.status == BleObservationStatus::received && *now - value.acceptedAt >= valueLifetimeMs) out.status = BleObservationStatus::stale;
        }
        out.temperature = fresh(value.frame.temperature, value.at[0], *now, valueLifetimeMs);
        out.humidity = fresh(value.frame.humidity, value.at[1], *now, valueLifetimeMs);
        out.battery = fresh(value.frame.battery, value.at[2], *now, valueLifetimeMs);
        out.batteryLow = fresh(value.frame.batteryLow, value.at[3], *now, valueLifetimeMs);
        out.light = fresh(value.frame.light, value.at[4], *now, valueLifetimeMs);
        out.lightLevel = fresh(value.frame.lightLevel, value.at[5], *now, valueLifetimeMs);
        out.button = fresh(value.frame.button, value.at[6], *now, 2000);
        if (value.frame.temperature) out.temperatureAgeMs = age(*now, value.at[0]);
        if (value.frame.humidity) out.humidityAgeMs = age(*now, value.at[1]);
        if (value.frame.battery) out.batteryAgeMs = age(*now, value.at[2]);
        out.declaredDeviceType = fresh(value.frame.declaredDeviceType, value.identityAt, *now, identityLifetimeMs);
        if (value.frame.declaredDeviceType) out.declaredDeviceAgeMs = age(*now, value.identityAt);
        out.firmware32 = fresh(value.frame.firmware32, value.at[7], *now, identityLifetimeMs);
        out.firmware24 = fresh(value.frame.firmware24, value.at[8], *now, identityLifetimeMs);
        out.targetTemperature=fresh(value.frame.targetTemperature,value.at[9],*now,valueLifetimeMs);
        out.externalTemperature=fresh(value.frame.externalTemperature,value.at[10],*now,valueLifetimeMs);
        out.stateRevision=fresh(value.frame.stateRevision,value.at[11],*now,valueLifetimeMs);
        if(value.frame.targetTemperature)out.targetTemperatureAgeMs=age(*now,value.at[9]);
        if(value.frame.externalTemperature)out.externalTemperatureAgeMs=age(*now,value.at[10]);
        if(value.frame.stateRevision)out.stateRevisionAgeMs=age(*now,value.at[11]);
        out.rssi = value.rssi; out.authenticated = value.authenticated;
        if (value.haveCounter) out.counter = value.highestCounter;
        out.oldCounterDrops = value.oldCounterDrops;
        return out;
    }
private:
    struct QueuedFrame {
        std::array<uint8_t, 255> bytes{};
        uint64_t at = 0;
        uint32_t generation = 0;
        uint16_t size = 0;
        uint8_t device = 0;
        int8_t rssi = 0;
        bool rssiKnown = false;
    };
    struct Value {
        ShellyHtDisplayFrame frame;
        std::array<uint64_t, 12> at{};
        uint64_t identityAt = 0, acceptedAt = 0;
        uint32_t highestCounter = 0, oldCounterDrops = 0;
        std::optional<int8_t> rssi;
        BleObservationStatus status = BleObservationStatus::waiting;
        bool haveCounter = false, haveAccepted = false, authenticated = false;
    };
    static void withdraw(Value& value) noexcept {
        value.frame = {}; value.at.fill(0); value.identityAt = 0;
        value.rssi.reset(); value.authenticated = false;
        // Original accepted counter/time remains historical, never a new report.
    }
    template<class T>
    static void assign(std::optional<T>& value, uint64_t& at, const std::optional<T>& next, uint64_t receivedAt) {
        if (next) { value = next; at = receivedAt; }
    }
    template<class T>
    static std::optional<T> fresh(const std::optional<T>& value, uint64_t at, uint64_t now, uint64_t lifetime) noexcept {
        return value && now >= at && now - at < lifetime ? value : std::nullopt;
    }
    static uint32_t age(uint64_t now, uint64_t at) noexcept {
        return now >= at ? static_cast<uint32_t>(std::min<uint64_t>(now - at, UINT32_MAX)) : UINT32_MAX;
    }
    std::optional<uint64_t> readClock() {
        uint64_t now = maximumClockMs + 1;
        try { if (clock_) now = clock_(); } catch (...) {}
        if (now > maximumClockMs || (haveClock_ && now < clockAt_)) { disable(BleObserverStop::clock_invalid); return std::nullopt; }
        if (stop_ == BleObserverStop::clock_invalid) return std::nullopt;
        haveClock_ = true; clockAt_ = now; return now;
    }
    Decryptor& decryptor_;
    Clock clock_;
    ManagedBleBindings bindings_;
    std::array<Value, ManagedBleBindings::capacity> values_{};
    std::array<QueuedFrame, queueCapacity> queue_{};
    QueuedFrame processing_;
    BthomeWorkspace workspace_;
    mutable std::mutex queueMutex_;
    std::atomic<bool> enabled_{false};
    std::atomic<uint32_t> generation_{1};
    uint64_t clockAt_ = 0;
    std::size_t head_ = 0, queued_ = 0;
    uint32_t queueDrops_ = 0;
    BleObserverStop stop_ = BleObserverStop::none;
    bool initialized_ = false, haveClock_ = false;
};
}
