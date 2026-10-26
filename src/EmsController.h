#pragma once
#include "Logging.h"

#include "config.h"
#include "EmsBusUart.h"
#include "EMS/EmsTelegram.h"
#include "EMS/EmsFrameQueue.h"
#include "EMS/EmsPoll.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/EmsDeviceInventory.h"
#include "EMS/OutdoorTemperatureSample.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "EMS/BoilerTestService.h"
#include "EMS/BoilerTestPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "EMS/ManualBusIdentity.h"
#include "EMS/ClassicHeatTrialEnvelope.h"
#include "EMS/ClassicConfigurationRead.h"
#include "EMS/ClassicBoilerSettingsService.h"
#include "EMS/ClassicSettingsRuntimeGate.h"
#include "EMS/ManualClassicTransaction.h"
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
            if (boilerTestTransportFault_.exchange(false, std::memory_order_acq_rel)) {
                boilerTest_.transportFault(static_cast<uint64_t>(esp_timer_get_time() / 1000));
                configurationRead_.fail("transport_fault");
                boilerSettings_.failTransport();
            }
            boilerSettings_.tick([]{return static_cast<uint64_t>(esp_timer_get_time());},
                [this](std::string_view){return boilerSettingsPermitted();});
            settingsOwnsBus_.store(boilerSettings_.active(),std::memory_order_release);
            configurationRead_.tick(static_cast<uint64_t>(esp_timer_get_time()/1000),configurationReadPermitted());
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
    void getBoilerFieldGroup(std::ostream& out,size_t group) const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        if(!emsConfig_.emsEnabled)return;
        monitor_.writeFieldGroup(out,static_cast<uint64_t>(esp_timer_get_time()/1000),group);
    }
    void getDeviceStatus(std::ostream &ss) const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        ss<<"{\"enabled\":"<<(emsConfig_.emsEnabled?"true":"false")<<",\"inventory\":";
        deviceInventory_.writeJSON(ss,now);ss<<",\"boiler\":";monitor_.writeJSON(ss,now);ss<<'}';
    }
	void getTelemetryStatus(std::ostream &ss, [[maybe_unused]] std::string_view operatorSession = {}) const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto snapshotMs = static_cast<uint64_t>(esp_timer_get_time() / 1000);
		// Keep the existing field-level telemetry contract and add transport
		// diagnostics to it. These are lifetime counters, not a TX permission.
		monitor_.writeJSON(ss, snapshotMs, false);
		ss << ",\"transport\":{\"enabled\":"
		   << (emsConfig_.emsEnabled ? "true" : "false")
		   << ",\"transmit_compiled\":" << ((board::emsTransmitAllowed || board::emsManualTestTransmitAllowed) ? "true" : "false")
		   << ",\"poll_count\":" << polls_.load(std::memory_order_relaxed)
		   << ",\"transmitted_frames\":" << txFrames_.load(std::memory_order_relaxed)
		   << ",\"receive_queue_dropped\":" << rxDropped_.load(std::memory_order_relaxed)
		   << ",\"invalid_telegrams\":" << invalidTelegrams_.load(std::memory_order_relaxed)
		   << ",\"uart_errors\":" << uart_.rxErrors.load(std::memory_order_relaxed)
		   << ",\"uart_timeouts\":" << uart_.rxTimeouts.load(std::memory_order_relaxed)
		   << ",\"uart_resets\":" << uart_.resets.load(std::memory_order_relaxed) << '}';
#ifdef OPENTHERMOSTAT_E32V2
        ss<<",\"manual_transaction\":{\"completed_exchanges\":"<<manualCompletions_.load(std::memory_order_relaxed)
            <<",\"rejected_writes\":"<<manualRejections_.load(std::memory_order_relaxed)
            <<",\"reply_errors\":"<<manualReplyErrors_.load(std::memory_order_relaxed)<<'}';
		ss << ",\"manual_bus_identity\":{\"source_address\":" << static_cast<unsigned>(deviceId_)
           << ",\"source_conflict\":" << (manualSourceConflict_.load(std::memory_order_acquire) ? "true" : "false")
           << ",\"matches_reviewed_address\":" << (manualBusIdentityMatches() ? "true" : "false") << '}';
		ss << ",\"test\":";
		boilerTest_.writeJSON(ss, snapshotMs, operatorSession, boilerTestGates(), monitor_);
        ss<<",\"configuration_read\":";configurationRead_.writeJSON(ss,snapshotMs,configurationReadPermitted(),boilerTest_.active());
        const auto heat = heatTrialEnvelope(snapshotMs);
        ss << ",\"heat_trial\":{\"profile_id\":\"" << ClassicHeatTrialEnvelope::profileId(manualHeatPressureSource_)
           << "\",\"installation_reviewed\":" << (manualHeatInstallationReviewed_ ? "true" : "false")
           << ",\"digital_pressure_required\":"
           << (manualHeatPressureSource_ == ClassicHeatTrialEnvelope::PressureSource::reportedSensor ? "true" : "false")
           << ",\"separate_pressure_method_reviewed\":"
           << (manualPressureMethodReviewed_ ? "true" : "false")
           << ",\"telemetry_ready\":" << (heat.ready ? "true" : "false")
           << ",\"reason\":\"" << heat.reason << "\",\"physical_validation\":false,\"limits\":{"
           << "\"minimum_flow_c\":" << static_cast<unsigned>(ClassicHeatTrialEnvelope::profile().minimumFlowC)
           << ",\"maximum_flow_c\":" << static_cast<unsigned>(ClassicHeatTrialEnvelope::profile().maximumFlowC)
           << ",\"maximum_duration_s\":" << ClassicHeatTrialEnvelope::profile().maximumHeatMs / 1000
           << ",\"minimum_pressure_decibar\":" << ClassicHeatTrialEnvelope::minimumPressureDecibar
           << ",\"maximum_pressure_decibar\":" << ClassicHeatTrialEnvelope::maximumPressureDecibar
           << ",\"minimum_measured_flow_centi\":" << ClassicHeatTrialEnvelope::minimumMeasuredFlowCenti
           << ",\"maximum_measured_flow_centi\":" << ClassicHeatTrialEnvelope::maximumMeasuredFlowCenti << "}}";
#endif
		ss << '}';
	}
#ifdef OPENTHERMOSTAT_E32V2
    void boilerSettingsSynchronize(const control::WebAuthSession& sessions,uint64_t now,bool updateAllowed){
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        settingsUpdateAllowed_=updateAllowed;
        boilerSettings_.synchronizeSessions(sessions,now);
        settingsOwnsBus_.store(boilerSettings_.active(),std::memory_order_release);
    }
    void boilerSettingsStatus(std::ostream& out,std::string_view requester={}) const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        boilerSettings_.writeJSON(out,static_cast<uint64_t>(esp_timer_get_time()/1000),boilerSettingsPermitted(),requester);
    }
    int boilerSettingsWrite(std::string_view body,std::string_view owner,const control::WebAuthSession& sessions,std::ostream& out) {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        const auto result=boilerSettings_.request(body,owner,now,boilerSettingsPermitted());
        boilerSettings_.synchronizeSessions(sessions,now);
        settingsOwnsBus_.store(boilerSettings_.active(),std::memory_order_release);
        out<<"{\"accepted\":"<<(result.http<300?"true":"false")<<",\"duplicate\":"<<(result.duplicate?"true":"false")
           <<",\"error\":\""<<result.error<<"\",\"settings\":";
        boilerSettings_.writeJSON(out,now,boilerSettingsPermitted(),owner);out<<'}';return result.http;
    }
    bool boilerSettingsActive()const{std::lock_guard<std::mutex> lock(telemetryMutex_);return boilerSettings_.active();}
	bool boilerTestActive() const {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		return boilerTest_.active() || configurationRead_.active();
	}
	int boilerTestAction(std::string_view action, std::string_view body, std::string_view operatorSession, std::ostream &ss) {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
        if(boilerSettings_.active()&&action!="stop"&&action!="close_fault"){
            ss<<"{\"accepted\":false,\"error\":\"settings_write_active\"}";return 409;
        }
        if(action=="read_configuration") {
            const auto result=configurationRead_.request(body,operatorSession,now,configurationReadPermitted(),boilerTest_.active());
            ss<<"{\"accepted\":"<<(result.http<300?"true":"false")<<",\"duplicate\":"<<(result.duplicate?"true":"false")
                <<",\"error\":\""<<result.error<<"\",\"configuration_read\":";
            configurationRead_.writeJSON(ss,now,configurationReadPermitted(),boilerTest_.active());ss<<'}';return result.http;
        }
        if(configurationRead_.active() && (action=="prepare"||action=="prepare_zero"||action=="start")) {
            ss<<"{\"accepted\":false,\"error\":\"configuration_read_active\"}";return 409;
        }
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
#ifdef OPENTHERMOSTAT_E32V2
    uint8_t deviceId_{ClassicBoilerTestEncoder::Addressing::classicService().source};
#else
	uint8_t deviceId_{0x19}; // TODO get from config/ UI
#endif
	std::optional<uint8_t> emsMask_ = {0x80};
#ifdef OPENTHERMOSTAT_E32V2
    // Set only by a decoded, CRC-valid boiler broadcast; never from a poll.
    std::atomic<uint8_t> observedSourceMask_{EmsPoll::unknown};
#endif

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
    EmsDeviceInventory deviceInventory_;
#ifdef OPENTHERMOSTAT_E32V2
	// Concrete supervised software envelope. Physical installation qualification
    // and TX permission remain separate source decisions, never HTTP settings.
	BoilerTestService boilerTest_{(static_cast<uint64_t>(esp_random()) << 32) | esp_random(), board::emsManualTestTransmitAllowed,
        ClassicHeatTrialEnvelope::profile(), true, true,
        manualHeatPressureSource_ == ClassicHeatTrialEnvelope::PressureSource::separateCheck};
    ManualClassicTransaction manualTransaction_; // UART task only, never HTTP/loop.
    std::atomic<uint32_t> manualCompletions_{0},manualRejections_{0},manualReplyErrors_{0};
    template<bool Read>
    bool transmitManualFrame(const EmsRawFrame& frame){
        if(!manualTransaction_.begin(frame.data.data(),frame.length,static_cast<uint64_t>(esp_timer_get_time())))return false;
        bool sent=false;
        try{sent=uart_.writeManualTestToEms<Read>(frame.data.data(),frame.length);}catch(...){sent=false;}
        manualTransaction_.finish(sent,static_cast<uint64_t>(esp_timer_get_time()));
        if(sent)txFrames_.fetch_add(1,std::memory_order_relaxed);
        return sent;
    }
    void processManualReply(const uint8_t* data,size_t length){
        if constexpr(!board::emsManualTestTransmitAllowed)return;
        else {
            const auto result=manualTransaction_.receive(data,length,
                []{return static_cast<uint64_t>(esp_timer_get_time());},
                [this]{return manualTransportReviewed();},[this]{
                    const uint8_t completion=0x0b;
                    return uart_.writeManualTestToEms<false,true>(&completion,1);
                });
            if(result==ManualClassicTransaction::Result::closed||result==ManualClassicTransaction::Result::rejected)
                manualCompletions_.fetch_add(1,std::memory_order_relaxed);
            if(result==ManualClassicTransaction::Result::rejected)manualRejections_.fetch_add(1,std::memory_order_relaxed);
            if(result==ManualClassicTransaction::Result::failed)manualReplyErrors_.fetch_add(1,std::memory_order_relaxed);
            if(result==ManualClassicTransaction::Result::failed||result==ManualClassicTransaction::Result::rejected)
                boilerTestTransportFault_.store(true,std::memory_order_release);
        }
    }
    // Persistent-settings IO has independent source/installation gates. Both
    // remain closed; manual heat-trial flags grant no settings permission.
    static constexpr bool settingsInstallationReviewed_=false;
    std::atomic<bool> settingsOwnsBus_{false};
    bool settingsUpdateAllowed_=false; // HTTP/update owner publishes under telemetryMutex_.
    ClassicBoilerSettingsService boilerSettings_{boilerTest_.bootId(),board::emsSettingsTransmitAllowed&&settingsInstallationReviewed_};
    bool boilerSettingsPermitted()const{
        return ClassicSettingsRuntimeGate::permitted({board::emsSettingsTransmitAllowed,settingsInstallationReviewed_,
            emsConfig_.emsEnabled,monitor_.capabilities().profile()==BoilerProtocol::classic,
            manualTransportReviewed(),boilerTest_.active(),configurationRead_.active(),settingsUpdateAllowed_});
    }
    bool processBoilerSettingsPoll();
    void processBoilerSettingsReply(const uint8_t* data,size_t length,uint64_t acquiredAtUs);
    ClassicConfigurationRead configurationRead_{boilerTest_.bootId(),board::emsManualTestTransmitAllowed};
    bool configurationReadPermitted() const {
        return manualTransportReviewed() && !boilerTest_.active() && !boilerSettings_.active()
            && monitor_.capabilities().profile()==BoilerProtocol::classic;
    }
    static constexpr bool manualHeatInstallationReviewed_ = false;
    // Fixed target installation: the user's Ecomline Classic has no digital
    // pressure sensor. Reviewing a separate local pressure-check method is an
    // additional source gate; selecting a catalogue photo cannot change it.
    static constexpr auto manualHeatPressureSource_ = ClassicHeatTrialEnvelope::PressureSource::separateCheck;
    static constexpr bool manualPressureMethodReviewed_ = false;
    ClassicHeatTrialEnvelope::Check heatTrialEnvelope(uint64_t now) const {
        return ClassicHeatTrialEnvelope::inspect(monitor_, now, manualHeatPressureSource_, manualPressureMethodReviewed_);
    }
    std::atomic<bool> manualSourceConflict_{false}; // Never cleared by UART reset.
    bool manualBusIdentityMatches() const {
        return ManualBusIdentity::matches(boilerTestAddressing_, deviceId_,
            observedSourceMask_.load(std::memory_order_acquire),
            manualSourceConflict_.load(std::memory_order_acquire));
    }
    bool manualTransportReviewed() const {
        return manualBusIdentityMatches() && uart_.manualTestTransportHealthy()
            && !boilerTestTransportFault_.load(std::memory_order_acquire)
            && !resetRequested_.load(std::memory_order_relaxed);
    }
    BoilerTestSession::Gates boilerTestGates() const {
        BoilerTestSession::Gates gates{}; // Physical heat-path review remains separate.
        gates.transmitterReviewed = manualTransportReviewed() && !configurationRead_.active() && !boilerSettings_.active();
        gates.pathReady = manualHeatInstallationReviewed_;
        gates.limitsSafe = heatTrialEnvelope(static_cast<uint64_t>(esp_timer_get_time() / 1000)).ready;
        return gates;
    }
    // Fixed Classic service identity; observed mask and conflicts must still
    // match at final admission. No HTTP/config address selection or TX unlock.
	static constexpr auto boilerTestAddressing_ = ClassicBoilerTestEncoder::Addressing::classicService();
    static_assert(boilerTestAddressing_.source==0x0b && boilerTestAddressing_.boiler==8
        && boilerTestAddressing_.sourceMask==0,"Configuration read requires the same reviewed Classic identity");
	static bool encodeBoilerTest(const BoilerTestSession::Intent& intent, EmsRawFrame& frame) {
		return ClassicBoilerTestEncoder::encode(boilerTestAddressing_, intent, frame)
            && ClassicBoilerTestEncoder::matches(boilerTestAddressing_, intent, frame);
	}
	static constexpr BoilerTestPollDriver::Encoder boilerTestEncoder_ = &encodeBoilerTest;
	bool processBoilerTestPoll();
	std::atomic<bool> boilerTestTransportFault_{false};
	uint32_t boilerTestUartErrorsSeen_ = 0; // UART task only
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
