#pragma once
#include "Logging.h"

#include "config.h"
#include "EmsBusUart.h"
#include "EMS/EmsTelegram.h"
#include "EMS/EmsFrameQueue.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/OutdoorTemperatureSample.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "EMS/BoilerTestService.h"
#include <esp_system.h>
#endif
#include <esp_timer.h>

#include <atomic>
#include <functional>
#include <list>
#include <mutex>
#include <optional>
#include <ostream>
#include <sstream>
#include <string_view>
#include <unordered_map>

namespace heating::ems {

struct EmsBoilerState {
	mutable std::mutex mutex;

	// params plus
	std::optional<bool> heatingEnabled;
	//outdoor
	std::optional<int16_t> outdoorTemperature; // for 5.7 EMS telegram returns 57 but we keep in multiplied by 10 = 570
	// wwparamsplus
	std::optional<bool> warmWaterEnabled;
	std::optional<uint8_t> selectedWarmWaterTemperature;
	// monitorfast plus
	std::optional<uint8_t> selectedFlowTemperature;
	std::optional<uint16_t> currentFlowTemperature;
	std::optional<bool> burningGas;
	std::optional<bool> pumpEnabled;
	std::optional<uint8_t> pressure;
	std::optional<uint8_t> currentBurnerPower;
	std::optional<bool> heatingActive;
	std::optional<bool> warmWaterActive;
	std::optional<bool> fillingSiphon;
	std::optional<uint16_t> serviceCode;
	std::optional<std::array<char, 3>> displayCode;
	// slow plus
	std::optional<bool> fanEnabled;
	std::optional<bool> pumpVenting;

	// ww monitor

	std::optional<uint8_t> warmWaterFlow;
	std::optional<uint16_t> currentWarmWaterTemperature;

	std::optional<uint8_t> protocolVersion;

	std::string getStatus() const {
		std::ostringstream ss;
		getStatus(ss);
		return ss.str();
	}

	void getStatus(std::ostream &ss, const char *profile = nullptr) const {
		bool first = true;

		#define ADD_ITEM_TO_JSON(name, value) { if (name.has_value()) { if (!first) { ss << ","; } else { first = false; } ss << "\""#name"\": " << value; } }
		#define ADD_SITEM_TO_JSON(name, value) { if (name.has_value()) { if (!first) { ss << ","; } else { first = false; } ss << "\""#name"\": \"" << value << "\""; } }

		std::lock_guard<std::mutex> lock(mutex);

		ss << std::boolalpha << "{";
		ADD_ITEM_TO_JSON(warmWaterEnabled, warmWaterEnabled.value())
		ADD_ITEM_TO_JSON(selectedWarmWaterTemperature, static_cast<int>(selectedWarmWaterTemperature.value()))
		ADD_ITEM_TO_JSON(outdoorTemperature, outdoorTemperature.value())
		ADD_ITEM_TO_JSON(heatingEnabled, heatingEnabled.value())
		ADD_ITEM_TO_JSON(selectedFlowTemperature, static_cast<int>(selectedFlowTemperature.value()))
		ADD_ITEM_TO_JSON(currentFlowTemperature, static_cast<int>(currentFlowTemperature.value()))
		ADD_ITEM_TO_JSON(burningGas, burningGas.value())
		ADD_ITEM_TO_JSON(pumpEnabled, pumpEnabled.value())
		ADD_ITEM_TO_JSON(pressure, static_cast<int>(pressure.value()))
		ADD_ITEM_TO_JSON(currentBurnerPower, static_cast<int>(currentBurnerPower.value()))
		ADD_ITEM_TO_JSON(fanEnabled, fanEnabled.value())
		ADD_ITEM_TO_JSON(pumpVenting, pumpVenting.value())
		ADD_ITEM_TO_JSON(fillingSiphon, fillingSiphon.value())
		ADD_ITEM_TO_JSON(warmWaterFlow, static_cast<int>(warmWaterFlow.value()))
		ADD_ITEM_TO_JSON(currentWarmWaterTemperature, currentWarmWaterTemperature.value())
		ADD_ITEM_TO_JSON(heatingActive, heatingActive.value());
		ADD_ITEM_TO_JSON(warmWaterActive, warmWaterActive.value())
		ADD_ITEM_TO_JSON(serviceCode, serviceCode.value())
		ADD_SITEM_TO_JSON(displayCode, displayCode.value().data())
		ADD_ITEM_TO_JSON(protocolVersion, static_cast<int>(protocolVersion.value()))
		if (profile) {
			if (!first) ss << ',';
			ss << "\"protocolProfile\":\"" << profile << "\",\"physicalValidation\":false";
		}

		ss << "}";
	}
};

struct EmsBoilerParams {
	mutable std::mutex mutex;

	std::optional<uint8_t> heatingTemperature;
	std::optional<uint8_t> maximumHeatingTemperature;

	std::optional<uint8_t> getHeatingTemperature() {
		std::lock_guard<std::mutex> lock(mutex);
		return heatingTemperature;
	}

	std::string getJSON() const {
		std::ostringstream ss;
		getJSON(ss);
		return ss.str();
	}

	void getJSON(std::ostream &ss) const {
		bool first = true;

		std::lock_guard<std::mutex> lock(mutex);

		ss << "{";
		ADD_ITEM_TO_JSON(maximumHeatingTemperature, static_cast<int>(maximumHeatingTemperature.value()))
		ADD_ITEM_TO_JSON(heatingTemperature, static_cast<int>(heatingTemperature.value()))
		ss << "}";
	}
};


class EmsController {
public:
	ib::logger::LoggerInterface::LogFeatureType verboseFeature() const { return verboseFeature_; }
	ib::logger::LoggerInterface::LogFeatureType fatalFeature() const { return fatalFeature_; }
	static constexpr int maxTxNotConfirmed = 15;
	static constexpr unsigned long boilerParametersReadRequestIntervalSecs = 119;
	static constexpr unsigned long boilerDetailsReadRequestIntervalSecs = 179;
	static constexpr int maxTelegramQueueSize = 59;

	explicit EmsController(std::shared_ptr<ib::logger::LoggerInterface> log);

	void requestStartupData();

	void changeBoilerState(bool turnOnHeating, uint8_t heatingTemperature) {
		DBGLOGFD(log_, logFeature_, "changeBoilerState heating: %d temperature: %d\n", turnOnHeating, heatingTemperature);
		if (!emsConfig_.emsEnabled) {
			DBGLOGFD(log_, logFeature_, "bus disabled\n");
			return;
		}

		if (turnOnHeating) {
			startHeating(heatingTemperature);
		} else {
			stopHeating();
		}
	}

	void setHeatingTemperature(uint8_t temperature);


	void loop() {
		if (!emsConfig_.emsEnabled) {
			return;
		}
		if (resetRequested_.exchange(false, std::memory_order_relaxed)) {
			reset();
		}
		captureForeignTelegrams_.store(log_ && log_->isFeatureEnabled(verboseFeature()), std::memory_order_relaxed);
		processTelegrams();
		refreshClassicStatus();
#ifdef OPENTHERMOSTAT_E32V2
		{
			std::lock_guard<std::mutex> lock(telemetryMutex_);
			boilerTest_.tick(static_cast<uint64_t>(esp_timer_get_time() / 1000), boilerTestGates(), monitor_);
		}
#endif
		requestPeriodicData();

		reportStats();

	}

	void registerTelegramProcessor(uint16_t telegramId, std::function<void(EmsTelegram const &)> processor) {
		std::lock_guard<std::mutex> lock(telegramProcessorsMutex_);
		telegramProcessors_[telegramId].push_back(processor);
	}

	EmsBoilerState &getBoilerState() {
		return boilerState_;
	}
	std::optional<int16_t> getOutdoorTemperature() const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		return outdoorSample_.value(static_cast<uint64_t>(esp_timer_get_time()/1000));
	}

	void getStatus(std::ostream &ss) const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		boilerState_.getStatus(ss, monitor_.capabilities().name());
	}

	std::string getStatus() const {
		std::ostringstream ss;
		getStatus(ss);
		return ss.str();
	}
	void getTelemetryStatus(std::ostream &ss, [[maybe_unused]] std::string_view operatorSession = {}) const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		// Keep the existing field-level telemetry contract and add transport
		// diagnostics to it. These are lifetime counters, not a TX permission.
		monitor_.writeJSON(ss, static_cast<uint64_t>(esp_timer_get_time() / 1000), false);
		ss << ",\"transport\":{\"enabled\":"
		   << (emsConfig_.emsEnabled ? "true" : "false")
		   << ",\"transmit_compiled\":" << (board::emsTransmitAllowed ? "true" : "false")
		   << ",\"poll_count\":" << polls_.load(std::memory_order_relaxed)
		   << ",\"transmitted_frames\":" << txFrames_.load(std::memory_order_relaxed)
		   << ",\"receive_queue_dropped\":" << rxDropped_.load(std::memory_order_relaxed)
		   << ",\"invalid_telegrams\":" << invalidTelegrams_.load(std::memory_order_relaxed)
		   << ",\"uart_errors\":" << uart_.rxErrors.load(std::memory_order_relaxed)
		   << ",\"uart_timeouts\":" << uart_.rxTimeouts.load(std::memory_order_relaxed)
		   << ",\"uart_resets\":" << uart_.resets.load(std::memory_order_relaxed) << '}';
#ifdef OPENTHERMOSTAT_E32V2
		ss << ",\"test\":";
		boilerTest_.writeJSON(ss, static_cast<uint64_t>(esp_timer_get_time() / 1000), operatorSession, boilerTestGates(), monitor_);
#endif
		ss << '}';
	}
#ifdef OPENTHERMOSTAT_E32V2
	bool boilerTestActive() const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		return boilerTest_.active();
	}
	int boilerTestAction(std::string_view action, std::string_view body, std::string_view operatorSession, std::ostream &ss) {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
		const auto result = boilerTest_.action(action, body, operatorSession, now, boilerTestGates(), monitor_);
		ss << "{\"accepted\":" << (result.http < 300 ? "true" : "false")
		   << ",\"duplicate\":" << (result.duplicate ? "true" : "false") << ",\"error\":\"" << result.error << "\",\"test\":";
		boilerTest_.writeJSON(ss, now, operatorSession, boilerTestGates(), monitor_);
		ss << '}';
		return result.http;
	}
#endif

	void getBoilerParams(std::ostream &ss) const {
		boilerParams_.getJSON(ss);
	}

	std::string getBoilerParams() const {
		return boilerParams_.getJSON();
	}

private:
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};
	void requestPeriodicData();

	void reset();
	void enqueueTelegramToSend(EmsTelegram telegram, bool front = false);
	void reportStats();
	void decodeTelegram(uint8_t *data, uint8_t length, uint64_t receivedAtMs);
	void refreshClassicStatus();

	void processTelegrams();

	void processReadRequest(EmsTelegram const &telegram);

	// called from UART thread - don't block for too long
	void processTelegram(uint8_t *data, uint8_t length);
	bool processPoll(uint8_t deviceId);

	void pong() {
		uint8_t response = deviceId_ | emsMask_.value_or(0);
		uart_.writeToEms(&response, 1);
	}

	void startHeating(uint8_t heatingTemperature);
	void stopHeating();

	config::EmsConfig emsConfig_{config::getEmsConfig()};

	uint8_t boilerId_{0x08};
	// uint8_t deviceId_{0x0B};
	uint8_t deviceId_{0x19}; // TODO get from config/ UI
	std::optional<uint8_t> emsMask_ = {0x80};

	// Only fixed-size copies and index updates are allowed under this lock.
	portMUX_TYPE txMux_ = portMUX_INITIALIZER_UNLOCKED;
	std::array<EmsRawFrame, maxTelegramQueueSize> telegramsToSend_{};
	size_t txHead_ = 0;
	size_t txSize_ = 0;
	EmsFrameQueue<maxTelegramQueueSize> telegramsToProcess_;
	std::atomic<bool> resetRequested_{false};
	std::atomic<bool> captureForeignTelegrams_{false};
	std::atomic<uint32_t> rxDropped_{0};
	std::atomic<uint32_t> invalidTelegrams_{0};
	std::atomic<uint32_t> polls_{0};
	std::atomic<uint32_t> txFrames_{0};
	std::atomic<uint32_t> maxPollServiceUs_{0};
	unsigned long lastStatsMillis_ = 0;

	std::mutex telegramProcessorsMutex_;
	std::unordered_map<uint16_t, std::list<std::function<void(EmsTelegram const &)>>> telegramProcessors_;

	EmsBoilerState boilerState_;
	EmsBoilerParams boilerParams_;
	mutable std::mutex telemetryMutex_;
	ClassicBoilerMonitor monitor_;
#ifdef OPENTHERMOSTAT_E32V2
	// No installed reviewed test profile/poll driver yet. No request/config flag
	// can fill this in or change the board's independent physical TX lock.
	BoilerTestService boilerTest_{(static_cast<uint64_t>(esp_random()) << 32) | esp_random(), board::emsTransmitAllowed};
	static BoilerTestSession::Gates boilerTestGates() { return {}; }
#endif
	control::TemperatureSample outdoorSample_;

	std::atomic<std::optional<int16_t>> emsOutdoorTemperature_;

	std::atomic_size_t txNotConfirmed_{0};
	uint32_t uartResetsSeen_ = 0; // UART task only


	EmsBusUart uart_{log_,
		[this](uint8_t *data, uint8_t size) { processTelegram(data, size); }
		};
	ib::logger::LoggerInterface::LogFeatureType verboseFeature_{};
	ib::logger::LoggerInterface::LogFeatureType fatalFeature_{};


	unsigned long lastBoilerParametersReadRequestMillis_ = 0;
	unsigned long lastBoilerDetailsReadRequestMillis_ = 0;

};


}
