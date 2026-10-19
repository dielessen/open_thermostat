#include "Logging.h"
#include "Board.h"
#include "Network.h"
#include <Arduino.h>
#include <Wire.h>
#include <time.h>
#include <atomic>
#include <esp_sntp.h>

#include <WiFi.h>
#include <SPIFFS.h>
#include <ESPmDNS.h>
#include <TimeHelpers.h>
#include <logger/Logger.h>
#include <logger/LoggerSerialSink.h>
#include <logger/LoggerSocketSink.h>

#include "config.h"
#include "Filesystem.h"
#include "HeatingController.h"
#include "REST.h"
#include "RTCTimeHelpers.h"

#define ONBOARD_LED 2

namespace {
std::atomic<bool> ntpTimeUpdated{false};

ib::logger::LoggerInterface::LogFeatureType appLogFeature() {
	static const auto id = heating::logger->addFeature("App");
	return id;
}
}


namespace heating {

HeatingController *controller = nullptr;
std::shared_ptr<ib::logger::LoggerInterface> logger;

std::unique_ptr<REST> rest;

bool wifiAPMode = false;
}

void WiFiGotIP(arduino_event_id_t event, arduino_event_info_t info) {
#ifndef OPENTHERMOSTAT_E32V2
	DBGLOGFI(heating::logger, appLogFeature(), "WiFI IP address %s hostname: %s\n", IPAddress(info.got_ip.ip_info.ip.addr).toString().c_str(), WiFi.getHostname());
#endif

#ifdef OPENTHERMOSTAT_E32V2
	if (heating::networkConnected()) {
#else
	if (WiFi.isConnected()) {
#endif
		if (heating::rest) {
			heating::rest->restart();
		}

		// SNTP retains the hostname pointer for asynchronous retries and updates.
		// Device settings take effect after reboot; keep this storage alive until then.
		static const auto networkConfig = config::getNetworkConfig();
		if (networkConfig.ntpEnabled) {
			sntp_set_time_sync_notification_cb([](struct timeval *) {
				// Runs in the network task: defer logging and RTC I/O to loop().
				ntpTimeUpdated.store(true, std::memory_order_relaxed);
			});
			if (!networkConfig.timeZone.empty()) {
				DBGLOGFI(heating::logger, appLogFeature(), "Configuring timezone time '%s' server: '%s' ", networkConfig.timeZone.c_str(), networkConfig.ntpHost.c_str());
				configTzTime(networkConfig.timeZone.c_str(), networkConfig.ntpHost.c_str());
			} else {
				configTime(networkConfig.ntpUtcOffset, networkConfig.ntpDaylightUtcOffset, networkConfig.ntpHost.c_str());
			}
		} else {
			DBGLOGFI(heating::logger, appLogFeature(), "NTP disabled\n");
		}

		struct tm timeinfo;
		if (!getLocalTime(&timeinfo)) {
			DBGLOGFI(heating::logger, appLogFeature(), "Failed to obtain network time. Setting up from RTC\n");
			heating::setLocalTimeFromRTC(networkConfig.timeZone, networkConfig.ntpUtcOffset, networkConfig.ntpDaylightUtcOffset);
		}

#ifdef OPENTHERMOSTAT_E32V2
		MDNS.end();
		if (!MDNS.begin(networkConfig.hostname.c_str())) {
#else
		if (!MDNS.begin(WiFi.getHostname())) {
#endif //CONFIG_MDNS_TASK_STACK_SIZE 4096
			DBGLOGFI(heating::logger, appLogFeature(), "Error starting mDNS\n");
		} else {
			MDNS.addService(networkConfig.hostname.c_str(), "http", networkConfig.listenPort);
		}
	}

}

void WifiSetUp(config::WiFiConfig const &wifiConfig, config::NetworkConfig const &networkConfig, config::APConfig const &apConfig, bool startAP) {
	if (startAP) {
		DBGLOGFI(heating::logger, appLogFeature(), "Starting Access Point\n");
#ifndef OPENTHERMOSTAT_E32V2
		if (heating::controller) {
			heating::controller->stopBluetoothScan();
			heating::controller->waitUntilBluetoothScanFinishAndDeinitBLE();
			DBGLOGFI(heating::logger, appLogFeature(), "Starting Access Point. Stopped bluetooth scan\n");
		}
#endif

		WiFi.mode(WIFI_AP);
		WiFi.setSleep(WIFI_PS_NONE);

		bool softAPResult = WiFi.softAP(apConfig.ssid.c_str(), apConfig.password.c_str(), apConfig.channel);

		DBGLOGFI(heating::logger, appLogFeature(), "Soft AP start: %d\n", softAPResult);

#ifdef OPENTHERMOSTAT_E32V2
		IPAddress ip, gateway, mask;
		ip.fromString(apConfig.ip.c_str());
		gateway.fromString(apConfig.gateway.c_str());
		mask.fromString(apConfig.subnetMask.c_str());
		WiFi.softAPConfig(ip, gateway, mask);
		WiFi.softAPsetHostname(apConfig.hostname.c_str());
		heating::wifiAPMode = true;
		if (heating::rest) heating::rest->restart();
		MDNS.begin(apConfig.hostname.c_str());
		MDNS.addService("http", "tcp", apConfig.listenPort);
#else
		WiFi.onEvent(
			[apConfig](arduino_event_id_t event, arduino_event_info_t info) {
				IPAddress ip, gateway, subnetMask;
				ip.fromString(apConfig.ip.c_str());
				gateway.fromString(apConfig.gateway.c_str());
				subnetMask.fromString(apConfig.subnetMask.c_str());

				bool configResult = WiFi.softAPConfig(ip, gateway, subnetMask);
				WiFi.softAPsetHostname(apConfig.hostname.c_str());

				DBGLOGFI(heating::logger, appLogFeature(), "Started Access Point. Hostname: '%s'. IP address: %s. config: %d\n", WiFi.softAPgetHostname(), WiFi.softAPIP().toString().c_str(), configResult);

				heating::setLocalTimeFromRTC(apConfig.timeZone, apConfig.ntpUtcOffset, apConfig.ntpDaylightUtcOffset);

				if (heating::rest) {
					DBGLOGFI(heating::logger, appLogFeature(), "Restarting REST service\n");
					heating::rest->restart();
				}
				heating::wifiAPMode = true;

				if (!MDNS.begin("heating")) {
					DBGLOGFI(heating::logger, appLogFeature(), "Error starting mDNS\n");
				} else {
					MDNS.addService(apConfig.hostname.c_str(), "http", apConfig.listenPort);
				}
			}, arduino_event_id_t::ARDUINO_EVENT_WIFI_AP_START);
#endif



		WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t info) { DBGLOGFI(heating::logger, appLogFeature(), "AccessPoint client IP assigned: '%s'\n", IPAddress(info.got_ip.ip_info.ip.addr).toString().c_str()); }, arduino_event_id_t::ARDUINO_EVENT_WIFI_AP_STAIPASSIGNED);

		WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t info) { DBGLOGFI(heating::logger, appLogFeature(), "AccessPoint client connected MAC: " MACSTR "\n",MAC2STR(info.wifi_ap_staconnected.mac)); }, arduino_event_id_t::ARDUINO_EVENT_WIFI_AP_STACONNECTED);

	} else {
		DBGLOGFI(heating::logger, appLogFeature(), "networkConfig\n"
							   "  host: %s\n"
							   "  ssid: %s\n", networkConfig.hostname.c_str(), wifiConfig.ssid.c_str());

		heating::wifiAPMode = false;

		const char *pass = nullptr;
		if (!wifiConfig.password.empty()) {
			pass = wifiConfig.password.c_str();
		}

		WiFi.setHostname(networkConfig.hostname.c_str());
		WiFi.begin(wifiConfig.ssid.c_str(), pass);

		WiFi.setHostname(networkConfig.hostname.c_str());
		WiFi.setAutoConnect(true);
		WiFi.setAutoReconnect(true);

#ifndef OPENTHERMOSTAT_E32V2
		WiFi.onEvent(WiFiGotIP, arduino_event_id_t::ARDUINO_EVENT_WIFI_STA_GOT_IP);
#endif
	}

	if (networkConfig.loggerEnabled && !networkConfig.loggerHost.empty()) {
		heating::logger->attachSink(std::make_shared<ib::logger::LoggerSocketSink>(
		ib::logger::LoggerInterface::LogLevel::TRACE, networkConfig.loggerHost, networkConfig.loggerPort));
	}
}

void setup() {
	delay(2500); // wait for monitor
	Serial.begin(115200);
	heating::logger = std::make_shared<ib::logger::Logger>(
		std::vector<std::shared_ptr<ib::logger::LoggerSinkInterface>>{
			std::make_shared<ib::logger::LoggerSerialSink>(ib::logger::LoggerInterface::LogLevel::TRACE)});
	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d STARTUP\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());

#ifndef OPENTHERMOSTAT_E32V2
	pinMode(ONBOARD_LED, OUTPUT);
	digitalWrite(ONBOARD_LED, HIGH);
	digitalWrite(ONBOARD_LED, LOW);
#endif

	delay(500);

	const esp_app_desc_t *app = esp_ota_get_app_description();
	const esp_partition_t *partition = esp_ota_get_running_partition();

	DBGLOGFI(heating::logger, appLogFeature(), "Project: %s, version: %s\n", app->project_name, app->version);
	DBGLOGFI(heating::logger, appLogFeature(), "Build: %s %s\n", app->date, app->time);
	DBGLOGFI(heating::logger, appLogFeature(), "IDF: %s\n", app->idf_ver);
	DBGLOGFI(heating::logger, appLogFeature(), "Firmware sha256: %s\n", app->app_elf_sha256);
	DBGLOGFI(heating::logger, appLogFeature(), "Partition: %s, size: %d, encrypted: %d\n", partition->label, partition->size, partition->encrypted);
	DBGLOGFI(heating::logger, appLogFeature(), "-----------------------");
	DBGLOGFI(heating::logger, appLogFeature(), "Starting up");

#ifdef CONFIG_BT_CLASSIC_ENABLED
	DBGLOGFI(heating::logger, appLogFeature(), "CLASSIC BT ENABLED\n");
#else
	DBGLOGFI(heating::logger, appLogFeature(), "BLE BT ENABLED\n");
#endif


#if SOC_UART_NUM > 1
	DBGLOGFI(heating::logger, appLogFeature(), "SERIAL 1 ENABLED\n");
#endif

	if (!heating::filesystem.mount()) {
		DBGLOGFI(heating::logger, appLogFeature(), "An Error has occurred while mounting SPIFFS");
	} else {
		DBGLOGFI(heating::logger, appLogFeature(), "Mounted SPIFFS partition '%s', dual slots: %d, fallback slot used: %d\n", heating::filesystem.activeLabel().c_str(), heating::filesystem.hasDualPartitions(), heating::filesystem.usedFallbackSlot());
	}

	config::readDebugOptions();

	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d SPIFFS\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());

	auto networkConfig = config::getNetworkConfig();

	if constexpr (heating::board::auxiliaryGpioAllowed) {
		auto rtcpins = config::getRTCPins();
		DBGLOGFI(heating::logger, appLogFeature(), "Configuring i2c on sda %d scl %d\n", rtcpins.sda, rtcpins.scl);
		Wire.begin(rtcpins.sda, rtcpins.scl);
	}
	if (heating::board::auxiliaryGpioAllowed && networkConfig.rtcEnabled) {
		heating::startRTC(networkConfig.rtcEnabled);
	} else {
		DBGLOGFI(heating::logger, appLogFeature(), "RTC battery clock disabled\n");
	}

	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d RTC\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());

	auto wifiConfig = config::getWiFiConfig();
	auto apConfig = config::getAPConfig();

	bool startAP = wifiConfig.ssid.empty() /*|| TODO PUSHBUTTON PRESSED */;

	heating::controller = new heating::HeatingController(heating::logger);
	heating::rest = std::make_unique<heating::REST>(heating::logger, *heating::controller, startAP ? apConfig.listenPort : networkConfig.listenPort);
	config::readDebugOptions();

	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d STUFF\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());

	WifiSetUp(wifiConfig, networkConfig, apConfig, startAP);
#ifdef OPENTHERMOSTAT_E32V2
	heating::startBoardEthernet();
	DBGLOGFI(heating::logger, appLogFeature(), "E32V2 EXPERIMENTAL: EMS TX/forwarder/GPIO outputs blocked. PSRAM: %u bytes\n", ESP.getPsramSize());
#endif
	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d WIFI\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());
	config::readDebugOptions();
}

void loop() {
#ifdef OPENTHERMOSTAT_E32V2
	if (heating::pollBoardNetwork()) {
		// Common REST/NTP/mDNS startup, once per route/IP change, not in event task.
		WiFiGotIP(ARDUINO_EVENT_ETH_GOT_IP, {});
	}
#endif
	static unsigned long lastMillis = 0;
	if (ntpTimeUpdated.exchange(false, std::memory_order_relaxed)) {
		DBGLOGFI(heating::logger, appLogFeature(), "NTP synchronized, updating RTC\n");
		heating::setRTCfromLocalTime();
	}

	auto now = millis();
	if (ib::millisDurationPassed(now, lastMillis, 10000)) {
		lastMillis = now;

		heating::controller->operate();
		DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d MinPeekStack: %d boxTemp: %f, UpTime: %lds SPIFFS: %zu/%zu\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap(), uxTaskGetStackHighWaterMark(nullptr), heating::rtcGetTemp(), esp_timer_get_time()/1000000, SPIFFS.usedBytes(), SPIFFS.totalBytes());

		if (!WiFi.isConnected()
#ifdef OPENTHERMOSTAT_E32V2
			&& !heating::wifiAPMode
#endif
		) {
			DBGLOGFI(heating::logger, appLogFeature(), "WiFi not connected. Reconnecting.\n");
			WiFi.reconnect();
		} else {
			DBGLOGFI(heating::logger, appLogFeature(), "WiFi IP Address: %s\n", WiFi.localIP().toString().c_str());
		}
	}

	heating::controller->loop();

#ifdef OPENTHERMOSTAT_E32V2
	if (heating::wifiAPMode || heating::networkConnected()) {
#else
	if (heating::wifiAPMode || WiFi.isConnected()) {
#endif
		heating::rest->handle();
	}
}
