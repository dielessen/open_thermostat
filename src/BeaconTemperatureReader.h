#pragma once

#include "config.h"
#include "Logging.h"
#include "BeaconBleAddress.h"
#include "control/BleTemperatureAdvertisement.h"
#include "control/BleScanLifecycle.h"

#include <NimBLEDevice.h>
#include <NimBLEAdvertisedDevice.h>
#include <esp_gap_ble_api.h>
#include <esp_coexist.h>

#include <atomic>
#include <functional>
#include <optional>
#include <set>
#include <string_view>
#include <vector>


namespace heating {

class BeaconTemperatureReader : public NimBLEScanCallbacks {
private:
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};

public:
	using BleDevices_t = std::set<BleAddress_t>;

	using ReportTemperature_t = std::function<void(BleAddress_t, std::optional<int16_t> temperature, std::optional<int16_t> humidity, std::optional<int8_t> battery)>;

	BeaconTemperatureReader(std::shared_ptr<ib::logger::LoggerInterface> log, ReportTemperature_t pushTemperature) : log_(std::move(log)), pushTemperature_(pushTemperature) {
		if (log_) {
			logFeature_ = log_->addFeature("TempReader");
		}
		stReader_ = this;

		esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT);

		if (!NimBLEDevice::init("HeatingController")) {
			scanLifecycle_.close();
			DBGLOGFD(log_, logFeature_, "NimBLE initialization failed.\n");
			return;
		}
		DBGLOGFD(log_, logFeature_, "NimBLEDevice initialized successfully.\n");
		// The radio is shared: when Wi-Fi and Bluetooth compete, Wi-Fi wins. A
		// sensor repeats its report every few seconds; lost HTTP or MQTT traffic
		// can leave the device unreachable.
		const auto coex = esp_coex_preference_set(ESP_COEX_PREFER_WIFI);
		DBGLOGFI(log_, logFeature_, "Bluetooth coexistence prefers Wi-Fi: %s\n", esp_err_to_name(coex));
		NimBLEScan *pBLEScan = NimBLEDevice::getScan();
		if (!pBLEScan) { scanLifecycle_.close(); return; }

		pBLEScan->setMaxResults(0); // Callback-only: do not retain every nearby advertiser.
		pBLEScan->setScanCallbacks(this, true);
		pBLEScan->setInterval(control::BleScanPlan::intervalMs); // duty cycle is set per scan in triggerScan()

		DBGLOGFD(log_, logFeature_, "BLE initialized successfully.\n");
	}

	void shutDownBLE() {
		scanLifecycle_.close(); // Late callbacks cannot enable scanning again.
		NimBLEDevice::deinit(true);
	}

	bool isScanPending() { return scanLifecycle_.pending(); }
	bool discovering() const { return scanLifecycle_.discovering(); }
	template<class Visit> static void visitRmwAtomics(Visit&& visit) { visit("ble.scan_lifecycle", &scanLifecycle_); }
	bool scanEnabled() const { return config_.scanTime != 0; }

	// durationMs > 0: a requested Search. continuous: managed sensors are bound.
	bool triggerScan(uint32_t durationMs = 0, const std::function<void()>& onAdmitted = {}, bool continuous = false) {
		// Zero means unlimited scanning in NimBLE, not a disabled scan.
		if (!config_.scanTime) return false;
		const auto now = static_cast<uint32_t>(millis());
		const auto plan = control::BleScanPlan::of(durationMs, config_.scanTime, config_.scanInterval, continuous);
		if (!scanLifecycle_.begin(now, plan.cooldownMs, durationMs != 0)) return false;
        // Before SDK start: the first new report must enter the new discovery list.
        try { if (onAdmitted) onAdmitted(); }
        catch (...) {
            scanLifecycle_.complete(now, [] {}, true);
            return false;
        }
		DBGLOGFD(log_, logFeature_, "Scan start %ds\n", config_.scanTime);
		auto scan = NimBLEDevice::getScan();
		// Sensor readings are in plain advertisements (BleScanPlan). The former
		// 80% active scan is the suspected cause of "WiFi connected" but
		// unreachable (2026-10-28).
		if (scan) {
			scan->setActiveScan(plan.active);
			scan->setWindow(plan.windowMs);
		}
		const bool started = scan && scan->start(plan.durationMs, false, false);
		if (!started) {
			// Failed start has no guaranteed onScanEnd callback. Release ownership
			// with a cooldown instead of leaving all later scans permanently blocked.
			scanLifecycle_.complete(static_cast<uint32_t>(millis()), [] {}, true);
		}
		DBGLOGFD(log_, logFeature_, "Scan start result: %d\n", started);
        return started;
	}

    using RawObserver = std::function<void(const BleAddress_t&, int, const uint8_t*, size_t)>;
    // Set once during construction, before the existing scanner can start.
    void setRawObserver(RawObserver observer) { rawObserver_ = std::move(observer); }
	void scanFinished() {
		scanLifecycle_.complete(static_cast<uint32_t>(millis()), [] {
			if (auto scan = NimBLEDevice::getScan()) scan->clearResults();
		});
		DBGLOGFD(log_, logFeature_, "Scan finished\n");
	}

	void onResult(NimBLEAdvertisedDevice const *advertisedDevice) final {
		if (!advertisedDevice || !scanLifecycle_.acceptsReports()) return;
		const auto& payload = advertisedDevice->getPayload();
		auto addr = advertisedDevice->getAddress();

		// DBGLOGFD(log_, logFeature_, "ON RESULT SERVICE DATA COUNT %zu / %s, payload size: %zu address: %s\n", advertisedDevice->getServiceDataCount(), advertisedDevice->getName().c_str(), payload.size(), advertisedDevice->getAddress().toString().c_str());

		parseAdvertisment(addr.getBase()->val, advertisedDevice->getRSSI(), payload.data(), payload.size());
	}

	void onDiscovered(const NimBLEAdvertisedDevice *advertisedDevice) final {
		// DBGLOGFD(log_, logFeature_, "ON DISCOVERED  SERVICE DATA COUNT %zu / %s, payload size: %zu\n", advertisedDevice->getServiceDataCount(), advertisedDevice->getName().c_str(), payload.size());
	}
	void onScanEnd(const NimBLEScanResults &scanResults, int reason) override {
		DBGLOGFD(log_, logFeature_, "onScanEnd %d / %d\n", scanResults.getCount(), reason);
		scanFinished();
	}

	void parseAdvertisment(uint8_t const *bda, int rssi, uint8_t const *payload, size_t payloadSize) {

		if (!bda) return;
		const BleAddress_t address{bda[5], bda[4], bda[3], bda[2], bda[1], bda[0]};
		if (rawObserver_) rawObserver_(address, rssi, payload, payloadSize);
		const auto report = control::decodeBleTemperatureAdvertisement(address, payload, payloadSize);
		if (report) pushTemperature_(address, report->temperature, report->humidity, report->battery);
	}

private:
	static BeaconTemperatureReader *stReader_;
	ReportTemperature_t pushTemperature_;
    RawObserver rawObserver_;
	// compare_exchange between loop and Bluetooth host task: static, so internal
	// RAM (this reader is part of the PSRAM-resident controller; one per device).
	static inline control::BleScanLifecycle scanLifecycle_;
	config::BluetoothConfig config_ = config::getBluetoothConfig();
};
}

heating::BeaconTemperatureReader *heating::BeaconTemperatureReader::stReader_ = nullptr;
