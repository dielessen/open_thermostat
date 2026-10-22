#pragma once

#include "config.h"
#include "Logging.h"
#include "BeaconBleAddress.h"
#include "control/BleTemperatureAdvertisement.h"

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

		if (NimBLEDevice::init("HeatingController")) {
			DBGLOGFD(log_, logFeature_, "NimBLEDevice initialized successfully.\n");
		}
		NimBLEScan *pBLEScan = NimBLEDevice::getScan();

		pBLEScan->setScanCallbacks(this, true);
		pBLEScan->setActiveScan(true);
		pBLEScan->setInterval(100); // 100ms
		pBLEScan->setWindow(80);    // 80ms

		DBGLOGFD(log_, logFeature_, "BLE initialized successfully.\n");
	}

	void shutDownBLE() { NimBLEDevice::deinit(true); }

	bool isScanPending() { return bluetoothScanPending_; }

	void triggerScan() {
		if (bluetoothScanPending_) {
			DBGLOGFD(log_, logFeature_, "Scan pending\n");
			return;
		}

		auto now = millis();
		if (lastScanFinishedMillis_ != 0 && !ib::millisDurationPassed(now, lastScanFinishedMillis_, 1000ul * config_.scanInterval)) {
			DBGLOGFD(log_, logFeature_, "Scan interval %ds didn't pass yet\n", config_.scanInterval);
			return;
		}

		bluetoothScanPending_ = true;
		DBGLOGFD(log_, logFeature_, "Scan start %ds\n", config_.scanTime);

		NimBLEScan *pBLEScan = NimBLEDevice::getScan();
		auto res = pBLEScan->start(config_.scanTime * 1000, false, true);

		DBGLOGFD(log_, logFeature_, "Scan start  result: %d\n", res);
	}

	void scanFinished() {
		bluetoothScanPending_ = false;
		lastScanFinishedMillis_ = millis();
		NimBLEDevice::getScan()->clearResults();
		DBGLOGFD(log_, logFeature_, "Scan finished\n");
	}

	void onResult(NimBLEAdvertisedDevice const *advertisedDevice) final {
		auto payload = advertisedDevice->getPayload();
		auto addr = advertisedDevice->getAddress();

		// DBGLOGFD(log_, logFeature_, "ON RESULT SERVICE DATA COUNT %zu / %s, payload size: %zu address: %s\n", advertisedDevice->getServiceDataCount(), advertisedDevice->getName().c_str(), payload.size(), advertisedDevice->getAddress().toString().c_str());

		parseAdvertisment(addr.getBase()->val, advertisedDevice->getRSSI(), payload.data(), payload.size());
	}

	void onDiscovered(const NimBLEAdvertisedDevice *advertisedDevice) final {
		// DBGLOGFD(log_, logFeature_, "ON DISCOVERED  SERVICE DATA COUNT %zu / %s, payload size: %zu\n", advertisedDevice->getServiceDataCount(), advertisedDevice->getName().c_str(), payload.size());
	}
	void onScanEnd(const NimBLEScanResults &scanResults, int reason) {
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
	std::atomic_bool bluetoothScanPending_ = false;
	config::BluetoothConfig config_ = config::getBluetoothConfig();
	unsigned long lastScanFinishedMillis_ = 0;
};
}

heating::BeaconTemperatureReader *heating::BeaconTemperatureReader::stReader_ = nullptr;
