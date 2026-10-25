#pragma once

#include "config.h"
#include "Logging.h"
#include "BeaconBleAddress.h"
#include "control/BleTemperatureAdvertisement.h"
#include "control/BleScanLifecycle.h"

#include <NimBLEDevice.h>
#include <NimBLEAdvertisedDevice.h>
#include <esp_gap_ble_api.h>

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
		NimBLEScan *pBLEScan = NimBLEDevice::getScan();
		if (!pBLEScan) { scanLifecycle_.close(); return; }

		pBLEScan->setMaxResults(0); // Callback-only: do not retain every nearby advertiser.
		pBLEScan->setScanCallbacks(this, true);
		pBLEScan->setActiveScan(true);
		pBLEScan->setInterval(100); // 100ms
		pBLEScan->setWindow(80);    // 80ms

		DBGLOGFD(log_, logFeature_, "BLE initialized successfully.\n");
	}

	void shutDownBLE() {
		scanLifecycle_.close(); // Late callbacks cannot enable scanning again.
		NimBLEDevice::deinit(true);
	}

	bool isScanPending() { return scanLifecycle_.pending(); }

	void triggerScan() {
		// Zero means unlimited scanning in NimBLE, not a disabled scan.
		if (!config_.scanTime) return;
		const auto now = static_cast<uint32_t>(millis());
		if (!scanLifecycle_.begin(now, uint32_t(config_.scanInterval) * 1000u)) return;
		DBGLOGFD(log_, logFeature_, "Scan start %ds\n", config_.scanTime);
		auto scan = NimBLEDevice::getScan();
		const bool started = scan && scan->start(uint32_t(config_.scanTime) * 1000u, false, false);
		if (!started) {
			// Failed start has no guaranteed onScanEnd callback. Release ownership
			// with a cooldown instead of leaving all later scans permanently blocked.
			scanLifecycle_.complete(static_cast<uint32_t>(millis()), [] {}, true);
		}
		DBGLOGFD(log_, logFeature_, "Scan start result: %d\n", started);
	}

	void scanFinished() {
		scanLifecycle_.complete(static_cast<uint32_t>(millis()), [] {
			if (auto scan = NimBLEDevice::getScan()) scan->clearResults();
		});
		DBGLOGFD(log_, logFeature_, "Scan finished\n");
	}

	void onResult(NimBLEAdvertisedDevice const *advertisedDevice) final {
		if (!advertisedDevice || !scanLifecycle_.acceptsReports()) return;
		auto payload = advertisedDevice->getPayload();
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

	void parseAdvertisment(uint8_t const *bda, int rssi, uint8_t *payload, size_t payloadSize) {
		(void)rssi;
		if (!bda) return;
		const BleAddress_t address{bda[5], bda[4], bda[3], bda[2], bda[1], bda[0]};
		const auto report = control::decodeBleTemperatureAdvertisement(address, payload, payloadSize);
		if (report) pushTemperature_(address, report->temperature, report->humidity, report->battery);
	}

private:
	static BeaconTemperatureReader *stReader_;
	ReportTemperature_t pushTemperature_;
	control::BleScanLifecycle scanLifecycle_;
	config::BluetoothConfig config_ = config::getBluetoothConfig();
};
}

heating::BeaconTemperatureReader *heating::BeaconTemperatureReader::stReader_ = nullptr;
