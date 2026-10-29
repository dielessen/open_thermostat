#include <esp_heap_caps.h>
#include <cJSON.h>
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
#include "update/GitHubUpdate.h"
#include "update/RestartTimer.h"
#include <TimeHelpers.h>
#include <logger/Logger.h>
#include <logger/LoggerSerialSink.h>
#include <logger/LoggerSocketSink.h>
#ifdef OPENTHERMOSTAT_E32V2
#include "diagnostics/LogRuntime.h"
#include "diagnostics/BufferedLogger.h"
#include "diagnostics/NativeLogCapture.h"
#include "diagnostics/LoopIntervals.h"
#include "diagnostics/BlackBox.h"
#include "diagnostics/GatewayProbe.h"
#include "diagnostics/RuntimeHealth.h"
#include "diagnostics/ReconnectBackoff.h"
#include <esp_attr.h>
#include <hal/wdt_hal.h>
#include <soc/rtc.h>
#endif

#include "config.h"
#include "Filesystem.h"
#include "HeatingController.h"
#include "REST.h"
#include "SetupNetwork.h"
#include "control/NetworkBootPlan.h"
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
bool networkTimeTrusted = false;
}

#ifdef OPENTHERMOSTAT_E32V2
namespace {
// Supervisor inputs, written by the loop and read by the supervisor task.
RTC_NOINIT_ATTR heating::diagnostics::BlackBoxRecord blackBoxRecord;
RTC_NOINIT_ATTR heating::diagnostics::LoopPhaseRecord loopPhaseRecord;
// Seconds since boot + 1 (0 = not set): 32-bit atomics, so the ESP32 needs no
// software 64-bit atomics (a vendor object outside the reviewed link inputs).
std::atomic<uint32_t> loopAtS{0}, wifiDownSinceS{0}, brokerDownSinceS{0}, networkQuietSinceS{0}, gatewayProbeFailures{0};
std::atomic<uint32_t> supervisorBeatS{0}, bluetoothQuietSinceS{0};
std::atomic<bool> wifiExpected{false}, brokerExpected{false}, gatewayProbeArmed{false};
std::atomic<bool> bluetoothExpected{false}, restartDeferred{false};
heating::diagnostics::GatewayProbe gatewayProbe; // loop only
// Boot confirmation evidence (loop only, latched): since boot an IP address
// plus a gateway probe reply, an MQTT session or a routed HTTP request; without
// a configured broker also the IP held long enough (BootConfirmation::networkProven).
bool networkProven = false, brokerConfigured = false;

uint64_t monotonicMs() { return static_cast<uint64_t>(esp_timer_get_time() / 1000); }
uint32_t monotonicS() { return static_cast<uint32_t>(esp_timer_get_time() / 1000000) + 1; }
uint64_t secondsMs(uint32_t s) { return static_cast<uint64_t>(s) * 1000; }

// Last resort if setup() or the supervisor stops running: the RTC watchdog
// resets the system after 120 s but keeps RTC memory, so the black box
// survives (reset 7). Armed as the first statement of setup(); the supervisor
// feeds it from then on. OTA erases sector by sector; the supervisor keeps
// running then. The HAL layer (not rtc_wdt) keeps the link within the
// reviewed SDK objects.
wdt_hal_context_t rtcWdt;
void armRtcWatchdog() {
	wdt_hal_init(&rtcWdt, WDT_RWDT, 0, false);
	wdt_hal_write_protect_disable(&rtcWdt);
	wdt_hal_config_stage(&rtcWdt, WDT_STAGE0, rtc_clk_slow_freq_get_hz() * 120, WDT_STAGE_ACTION_RESET_SYSTEM);
	// Like IDF's restart path: if the system reset does not take (10 s after
	// stage 0), reset the whole chip, RTC included (the black box is lost then).
	wdt_hal_config_stage(&rtcWdt, WDT_STAGE1, rtc_clk_slow_freq_get_hz() * 10, WDT_STAGE_ACTION_RESET_RTC);
	wdt_hal_enable(&rtcWdt);
	wdt_hal_write_protect_enable(&rtcWdt);
}
void feedRtcWatchdog() {
	wdt_hal_write_protect_disable(&rtcWdt);
	wdt_hal_feed(&rtcWdt);
	wdt_hal_write_protect_enable(&rtcWdt);
}

// Restarts a device that stopped serving (2026-10-28: "WiFi connected", no
// ping/HTTP, no automatic recovery). Not during a firmware update, unless that
// update itself has been running for more than 20 minutes.
void supervisorTask(void*) {
	using heating::diagnostics::SupervisorPolicy;
	uint64_t updateSince = 0;
	for (;;) {
		feedRtcWatchdog();
		supervisorBeatS.store(monotonicS());
		vTaskDelay(pdMS_TO_TICKS(5000));
		feedRtcWatchdog();
		SupervisorPolicy::Inputs in;
		in.now = secondsMs(monotonicS()); in.loopAt = secondsMs(loopAtS.load()); in.updateRunning = heating::update::busy() || heating::update::httpUploadActive.load();
		if (!in.updateRunning) updateSince = 0;
		else if (!updateSince) updateSince = in.now;
		in.updateSince = updateSince;
		in.wifiLostRestarts = heating::diagnostics::blackBox.wifiLostRestarts();
		in.networkDeadRestarts = heating::diagnostics::blackBox.networkDeadRestarts();
		in.bluetoothExpected = bluetoothExpected.load(); in.bluetoothQuietSince = secondsMs(bluetoothQuietSinceS.load());
		in.bluetoothRestarts = heating::diagnostics::blackBox.bluetoothRestarts(); in.restartDeferred = restartDeferred.load();
		in.wifiExpected = wifiExpected.load(); in.wifiDownSince = secondsMs(wifiDownSinceS.load());
		in.brokerExpected = brokerExpected.load(); in.brokerDownSince = secondsMs(brokerDownSinceS.load());
		in.gatewayProbeArmed = gatewayProbeArmed.load(); in.gatewayProbeFailures = gatewayProbeFailures.load();
		in.networkQuietSince = secondsMs(networkQuietSinceS.load());
		const auto reason = SupervisorPolicy::decide(in);
		if (reason == SupervisorPolicy::Reason::none) continue;
		heating::diagnostics::blackBox.restartReason(reason);
		DBGLOGFI(heating::logger, appLogFeature(), "Supervisor restart: %s\n", SupervisorPolicy::name(reason));
		vTaskDelay(pdMS_TO_TICKS(200));
		esp_restart();
	}
}

// Restarts the networkDead clock: the IP path worked (or Wi-Fi was down, which
// wifiLost covers) at this moment.
void networkQuietRestart() { networkQuietSinceS.store(monotonicS()); }

// Every loop pass, without waiting: an ICMP echo every 30 s to the gateway of
// the active route, Ethernet or Wi-Fi.
void probeGateway(uint64_t now) {
	using Result = heating::diagnostics::GatewayProbe::Result;
	auto result = gatewayProbe.poll(now);
	if (result == Result::none && gatewayProbe.due(now)) {
		if (heating::ethernetConnected()) result = gatewayProbe.start(now, heating::ethernetGateway());
		else if (wifiExpected.load() && WiFi.isConnected()) result = gatewayProbe.start(now, static_cast<uint32_t>(WiFi.gatewayIP()));
	}
	if (result == Result::none) return;
	gatewayProbeFailures.store(gatewayProbe.failures());
	if (result == Result::ok) { gatewayProbeArmed.store(true); networkQuietRestart(); heating::diagnostics::blackBox.networkWorked(now); }
	else if (gatewayProbeArmed.load())
		DBGLOGFI(heating::logger, appLogFeature(), "Gateway probe: no reply (%u in a row)\n", gatewayProbe.failures());
}

// Every 10 s on the loop: supervisor inputs and the black-box record.
void observeHealth(uint64_t now) {
	const bool wifi = !heating::wifiAPMode && !heating::setupAttemptUntil && WiFi.getMode() != WIFI_OFF;
	wifiExpected.store(wifi);
	if (!wifi || WiFi.isConnected()) wifiDownSinceS.store(0);
	else if (!wifiDownSinceS.load()) wifiDownSinceS.store(monotonicS());
	if (wifi && WiFi.isConnected()) heating::diagnostics::blackBox.wifiRecovered();
	// Bluetooth: bound sensors and scanning wanted; quiet since boot or the last advert.
	const bool bluetooth = heating::controller && heating::controller->managedBleExpected();
	const uint32_t heard = heating::controller ? heating::controller->managedBleHeardS() : 0;
	if (heard) heating::diagnostics::blackBox.bluetoothHeard();
	if (!bluetooth || !bluetoothQuietSinceS.load()) bluetoothQuietSinceS.store(monotonicS());
	else if (heard > bluetoothQuietSinceS.load()) bluetoothQuietSinceS.store(heard);
	bluetoothExpected.store(bluetooth);
	restartDeferred.store(heating::controller && (heating::controller->boilerTestActive() || heating::controller->boilerSettingsActive()));
	const bool broker = heating::controller && heating::controller->brokerConnected();
	if (broker) brokerExpected.store(true);
	if (broker || !brokerExpected.load()) brokerDownSinceS.store(0);
	else if (!brokerDownSinceS.load()) brokerDownSinceS.store(monotonicS());
	// Positive evidence besides the probe: an MQTT session (PubSubClient drops
	// it after a missed keep-alive) or any HTTP request routed since last time.
	static uint32_t requests = 0;
	const uint32_t seen = heating::diagnostics::blackBox.requests();
	const bool ethernet = heating::ethernetConnected(); // probed too; networkDead stays Wi-Fi only
	if (!ethernet && (!wifi || !WiFi.isConnected())) {
		gatewayProbe.cancel(); gatewayProbe.resetFailures(); gatewayProbeFailures.store(0);
		networkQuietRestart();
	} else if (broker || seen != requests) { networkQuietRestart(); heating::diagnostics::blackBox.networkWorked(now); }
	requests = seen;
	// Since when the network has held an IP without a break (sampled every 10 s).
	static uint64_t linkSince = 0;
	if (!heating::networkConnected() || heating::wifiAPMode) linkSince = 0;
	else if (!linkSince) linkSince = now;
	if (!networkProven && (heating::networkConnected() || heating::wifiAPMode))
		networkProven = heating::update::BootConfirmation::networkProven(gatewayProbeArmed.load() || broker || seen != 0,
			brokerConfigured, linkSince ? static_cast<uint32_t>(std::min<uint64_t>(now - linkSince, UINT32_MAX)) : 0);
	heating::diagnostics::blackBox.note(static_cast<uint32_t>(now / 1000), ESP.getMinFreeHeap(), uxTaskGetStackHighWaterMark(nullptr),
		heating::diagnostics::loopIntervals.snapshot().windowMaximumMs, static_cast<int8_t>(WiFi.RSSI()), WiFi.isConnected(), broker);
	const auto stacks = heating::diagnostics::taskStackMarks();
	heating::diagnostics::blackBox.noteResources(heating::diagnostics::largestInternalBlock(), stacks.supervisor, stacks.emsUart, stacks.bluetoothHost);
}
heating::diagnostics::ReconnectBackoff wifiReconnect; // loop only
}
#endif

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
#ifdef OPENTHERMOSTAT_E32V2
			if(!heating::wifiAPMode)
#endif
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
#ifdef OPENTHERMOSTAT_E32V2
		// Never hold up setup/status HTTP for the default five-second NTP wait.
		if (!getLocalTime(&timeinfo,0)) {
#else
		if (!getLocalTime(&timeinfo)) {
#endif
			DBGLOGFI(heating::logger, appLogFeature(), "Failed to obtain network time. Setting up from RTC\n");
			heating::setLocalTimeFromRTC(networkConfig.timeZone, networkConfig.ntpUtcOffset, networkConfig.ntpDaylightUtcOffset);
		}

#ifdef OPENTHERMOSTAT_E32V2
		// Once per boot: the SDK responder follows later IP/interface changes
		// itself (got-IP events); a restart on every change dropped announcements.
		static bool mdnsStarted = false;
		if (mdnsStarted) return;
		MDNS.end(); // the setup access point may have started it
		mdnsStarted = MDNS.begin(networkConfig.hostname.c_str());
		if (!mdnsStarted) {
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
#ifdef OPENTHERMOSTAT_E32V2
	if(!startAP&&networkConfig.interfaceMode=="ethernet") { WiFi.mode(WIFI_OFF); return; }
#endif
	if (startAP) {
#ifdef OPENTHERMOSTAT_E32V2
		if(!heating::startSetupWifi()) return;
		if(heating::rest) heating::rest->restart();
		return;
#endif
		DBGLOGFI(heating::logger, appLogFeature(), "Starting Access Point\n");
#ifndef OPENTHERMOSTAT_E32V2
		if (heating::controller) {
			heating::controller->stopBluetoothAndDeinitBLE();
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

#ifndef OPENTHERMOSTAT_E32V2
	// The TCP log sink resolves, connects and writes synchronously under the
	// logger mutex: it would block every logging task (Bluetooth host and
	// supervisor included). The E32 uses the nonblocking UDP syslog instead.
	if (networkConfig.loggerEnabled && !networkConfig.loggerHost.empty()) {
		heating::logger->attachSink(std::make_shared<ib::logger::LoggerSocketSink>(
		ib::logger::LoggerInterface::LogLevel::TRACE, networkConfig.loggerHost, networkConfig.loggerPort));
	}
#endif
}

void setup() {
#ifdef OPENTHERMOSTAT_E32V2
	armRtcWatchdog(); // a hang in setup() resets (and rolls back an unconfirmed OTA image)
	// Arduino's PSRAM threshold for plain malloc/new stays (4096 B): a lower
	// one moved many small objects with std::atomic or mutex members into
	// PSRAM, where the ESP32's S32C1I atomic read-modify-write is not reliable.
	// Known atomic-free data (cJSON nodes, response buffers) goes there explicitly.
	// Log lines leave through a 1 KiB driver buffer instead of blocking the
	// caller on the 128-byte UART FIFO at 115200 Bd.
	Serial.setTxBufferSize(1024);
#endif
	delay(2500); // wait for monitor
	Serial.begin(115200);
#ifdef OPENTHERMOSTAT_E32V2
	// JSON trees (status pages, settings, MQTT) live in PSRAM: thousands of small
	// nodes would otherwise come from the internal heap that Wi-Fi needs.
	static cJSON_Hooks psramJson{[](size_t size) { return heap_caps_malloc_prefer(size, 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT, MALLOC_CAP_DEFAULT); }, free};
	cJSON_InitHooks(&psramJson);
	WiFi.persistent(false);
	if(heating::deviceAccess.begin()) {
		// Physical USB console only. Never use network logger sinks for secrets.
		// Never print a changed password: only the factory default is shown.
		Serial.printf("Local setup WiFi password: %s\nWeb sign-in: user admin, password %s\nType setup + Enter over USB to reboot into WiFi-only setup for 15 minutes; password-reset + Enter restores the web password admin.\n",
			heating::deviceAccess.setupPassword().c_str(),
			heating::deviceAccess.defaultPassword()?"admin (factory default; change it under System)":
			heating::deviceAccess.passwordState()==heating::DeviceAccess::PasswordState::stored?"(changed by the owner)":"(stored password unreadable; use password-reset)");
	}
#endif
#ifdef OPENTHERMOSTAT_E32V2
    heating::diagnostics::runtime.begin();
    heating::logger = std::make_shared<heating::diagnostics::BufferedLogger>(
        std::vector<std::shared_ptr<ib::logger::LoggerSinkInterface>>{
            std::make_shared<ib::logger::LoggerSerialSink>(ib::logger::LoggerInterface::LogLevel::TRACE)},
        heating::diagnostics::runtime.log,heating::diagnostics::uptimeMs);
#else
	heating::logger = std::make_shared<ib::logger::Logger>(
		std::vector<std::shared_ptr<ib::logger::LoggerSinkInterface>>{
			std::make_shared<ib::logger::LoggerSerialSink>(ib::logger::LoggerInterface::LogLevel::TRACE)});
#endif
#ifdef OPENTHERMOSTAT_E32V2
    heating::diagnostics::installNativeLogCapture();
#endif
	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d STARTUP\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());
#ifdef OPENTHERMOSTAT_E32V2
    DBGLOGFI(heating::logger,appLogFeature(),"Reset reason: %d; recent logs are RAM-only\n",int(esp_reset_reason()));
    heating::diagnostics::blackBox.begin(blackBoxRecord,loopPhaseRecord,int(esp_reset_reason()));
    if(heating::diagnostics::blackBox.havePrevious()) {
        const auto& p=heating::diagnostics::blackBox.previous();
        DBGLOGFI(heating::logger,appLogFeature(),"Previous boot: uptime %us, min heap %u, loop stack min %u, last request %.39s, supervisor %s\n",
            p.uptimeS,p.minFreeHeap,p.loopStackMin,p.lastRequest,
            heating::diagnostics::SupervisorPolicy::name(heating::diagnostics::blackBox.previousRestart()));
    }
#endif

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
	char elfSha256[65]{};
	esp_ota_get_app_elf_sha256(elfSha256, sizeof(elfSha256));
	DBGLOGFI(heating::logger, appLogFeature(), "Firmware sha256: %s\n", elfSha256);
	DBGLOGFI(heating::logger, appLogFeature(), "Partition: %s, size: %d, encrypted: %d\n", partition->label, partition->size, partition->encrypted);
	DBGLOGFI(heating::logger, appLogFeature(), "-----------------------");
	DBGLOGFI(heating::logger, appLogFeature(), "Starting up");

#ifdef CONFIG_BT_CLASSIC_ENABLED
	// SDK compile option only: the BLE reader releases the Classic BT controller
	// memory before NimBLE starts, so no Classic BT stack runs.
	DBGLOGFI(heating::logger, appLogFeature(), "BLE only; Classic BT memory released at BLE start\n");
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
#ifdef OPENTHERMOSTAT_E32V2
	const auto networkPlan=heating::control::networkBootPlan(networkConfig.interfaceMode=="ethernet",!wifiConfig.ssid.empty(),heating::consumeSetupBoot());
	startAP=networkPlan.setupAp;
	{ const auto mqtt = config::getMqttConfig(); brokerConfigured = mqtt.enabled && !mqtt.brokerAddress.empty(); }
#endif

	heating::controller = new heating::HeatingController(heating::logger);
	heating::rest = std::make_unique<heating::REST>(heating::logger, *heating::controller, startAP ? apConfig.listenPort : networkConfig.listenPort);
#ifdef OPENTHERMOSTAT_E32V2
	{
		// S32C1I read-modify-write is not atomic in PSRAM (diagnostics/AtomicPlacement.h).
		uint32_t checked = 0;
		heating::diagnostics::atomicsInPsram = heating::diagnostics::countAtomicsInPsram(
			[&checked](auto&& visit) {
				auto counted = [&](const char* name, const void* address) { ++checked; visit(name, address); };
				heating::ems::EmsController::visitRmwAtomics(counted);
				heating::BeaconTemperatureReader::visitRmwAtomics(counted);
			},
			heating::diagnostics::inExternalRam,
			[](const char* name, const void* address) {
				DBGLOGFE(heating::logger, appLogFeature(), "Atomic %s is in PSRAM (%p): read-modify-write is unreliable there\n", name, address);
			});
		DBGLOGFI(heating::logger, appLogFeature(), "Atomic placement: %u of %u read-modify-write atomics in PSRAM; controller in %s\n",
			unsigned(heating::diagnostics::atomicsInPsram), unsigned(checked),
			heating::diagnostics::inExternalRam(heating::controller) ? "PSRAM" : "internal RAM");
	}
#endif
	config::readDebugOptions();

	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d STUFF\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());

	WifiSetUp(wifiConfig, networkConfig, apConfig, startAP);
#ifdef OPENTHERMOSTAT_E32V2
	if(networkPlan.ethernet) heating::startBoardEthernet();
	loopAtS.store(monotonicS());
	networkQuietRestart();
	// Above loop (1): a busy loop or HTTP handler cannot starve the supervisor.
	xTaskCreate(supervisorTask, "supervisor", 3072, nullptr, 5, nullptr);
	DBGLOGFI(heating::logger, appLogFeature(), "E32V2 EXPERIMENTAL: EMS TX/forwarder/GPIO outputs blocked. PSRAM: %u bytes\n", ESP.getPsramSize());
#endif
	DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d WIFI\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap());
	config::readDebugOptions();
}

void loop() {
#ifdef OPENTHERMOSTAT_E32V2
	heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::update);
	{
		const uint32_t beat = supervisorBeatS.load(), nowS = monotonicS();
		heating::update::loop(heating::controller && !heating::controller->boilerTestActive() && !heating::controller->boilerSettingsActive(),
			beat && nowS - beat <= 15, networkProven);
	}
	heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::network);
	// Only while asked: bootPending() reads the OTA state from flash.
	heating::setupRestartHeld = heating::setupRebootRequested && (heating::update::busy() || heating::update::bootPending());
	heating::pollSetupWifi();
	if (heating::pollBoardNetwork()) {
		// Common REST/NTP/mDNS startup, once per route/IP change, not in event task.
		WiFiGotIP(ARDUINO_EVENT_ETH_GOT_IP, {});
	}
#endif
	static unsigned long lastMillis = 0;
	if (ntpTimeUpdated.exchange(false, std::memory_order_relaxed)) {
		heating::networkTimeTrusted = true;
		DBGLOGFI(heating::logger, appLogFeature(), "NTP synchronized, updating RTC\n");
		heating::setRTCfromLocalTime();
	}

	auto now = millis();
#ifdef OPENTHERMOSTAT_E32V2
    heating::diagnostics::loopIntervals.observe(now);
    loopAtS.store(monotonicS());
#endif
	if (ib::millisDurationPassed(now, lastMillis, 10000)) {
		lastMillis = now;

#ifdef OPENTHERMOSTAT_E32V2
		heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::operate);
#endif
		heating::controller->operate();
#ifdef OPENTHERMOSTAT_E32V2
		heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::health);
		observeHealth(monotonicMs());
#endif
		DBGLOGFI(heating::logger, appLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d MinPeekStack: %d boxTemp: %f, UpTime: %lds\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap(), uxTaskGetStackHighWaterMark(nullptr), heating::rtcGetTemp(), esp_timer_get_time()/1000000);
		DBGLOGFD(heating::logger, appLogFeature(), "SPIFFS: %zu/%zu\n", SPIFFS.usedBytes(), SPIFFS.totalBytes());

#ifdef OPENTHERMOSTAT_E32V2
		heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::wifi_reconnect);
#endif
#ifdef OPENTHERMOSTAT_E32V2
		const bool stationDown = !WiFi.isConnected() && !heating::wifiAPMode && !heating::setupAttemptUntil && WiFi.getMode()!=WIFI_OFF;
		// 10, 20, 40, then every 60 s: a reconnect aborts a connect in progress
		// and races the SDK's own automatic reconnect.
		if (wifiReconnect.due(monotonicMs(), !stationDown)) {
			DBGLOGFI(heating::logger, appLogFeature(), "WiFi not connected. Reconnecting.\n");
			WiFi.reconnect();
		} else if (!stationDown) {
#else
		if (!WiFi.isConnected()) {
			DBGLOGFI(heating::logger, appLogFeature(), "WiFi not connected. Reconnecting.\n");
			WiFi.reconnect();
		} else {
#endif
			DBGLOGFI(heating::logger, appLogFeature(), "WiFi IP Address: %s\n", WiFi.localIP().toString().c_str());
		}
	}

#ifdef OPENTHERMOSTAT_E32V2
	heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::controller);
#endif
	heating::controller->loop();
#ifdef OPENTHERMOSTAT_E32V2
	heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::telemetry);
    // At most one nonblocking UDP datagram per 100 ms, after controller work.
    static const auto logHostname=config::getNetworkConfig().hostname;
    heating::diagnostics::runtime.poll(heating::diagnostics::runtime.log.syslogEnabled()&&heating::networkConnected()&&!heating::wifiAPMode,logHostname.c_str());
    heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::network_probe);
    probeGateway(monotonicMs()); // gateway ICMP echo, never waits
#endif

#ifdef OPENTHERMOSTAT_E32V2
	if (heating::wifiAPMode || heating::networkConnected()) {
#else
	if (heating::wifiAPMode || WiFi.isConnected()) {
#endif
#ifdef OPENTHERMOSTAT_E32V2
		heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::http);
#endif
		heating::rest->handle();
	}
#ifdef OPENTHERMOSTAT_E32V2
	else {
		// No network: without HTTP nothing in this pass waits, and the loop
		// would spin (and contend for the telemetry mutex). One tick of rest.
		vTaskDelay(1);
	}
#endif
#ifdef OPENTHERMOSTAT_E32V2
	heating::diagnostics::blackBox.loopPhase(heating::diagnostics::LoopPhase::idle);
#endif
}
