#pragma once
#include "Logging.h"

#include "config.h"
#include "EmsBusUart.h"
#include "EMS/EmsTelegram.h"
#include "EMS/EmsFrameQueue.h"
#include "EMS/EmsPoll.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/EmsDeviceInventory.h"
#include "EMS/EmsEntityCatalog.h"
#include "EMS/BoilerProfileReport.h"
#if __has_include(<nvs.h>)
#include "EMS/BoilerProfileStore.h"
#endif
#include "control/BoilerFieldTelemetry.h"
#include "control/BurnerCycleMonitor.h"
#include "control/DhwEpisodes.h"
#include "EMS/OutdoorTemperatureSample.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "EMS/BoilerTestService.h"
#include "EMS/BoilerTestPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "EMS/ManualBusIdentity.h"
#include "EMS/ClassicHeatTrialEnvelope.h"
#include "EMS/EcomlineCommissioningProfile.h"
#include "EMS/ClassicConfigurationRead.h"
#include "EMS/ClassicBoilerSettingsService.h"
#include "EMS/ClassicSettingsRuntimeGate.h"
#include "EMS/ManualClassicTransaction.h"
#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/BoilerLimitRead.h"
#include "EMS/ForeignBoilerRequest.h"
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

	// Every read-modify-write atomic of the EMS route (boot placement check).
	template<class Visit> static void visitRmwAtomics(Visit&& visit) {
		visit("ems.reset_requested", &resetRequested_); visit("ems.rx_dropped", &rxDropped_);
		visit("ems.invalid_telegrams", &invalidTelegrams_); visit("ems.polls", &polls_);
		visit("ems.tx_frames", &txFrames_); visit("ems.max_poll_service", &maxPollServiceUs_);
		visit("ems.tx_not_confirmed", &txNotConfirmed_);
#ifdef OPENTHERMOSTAT_E32V2
		visit("ems.manual_completions", &manualCompletions_); visit("ems.manual_rejections", &manualRejections_);
		visit("ems.manual_reply_errors", &manualReplyErrors_); visit("ems.transport_fault", &boilerTestTransportFault_);
#endif
		EmsBusUart::visitRmwAtomics(visit);
	}

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
		loadBoilerProfile();
		processTelegrams();
		saveBoilerProfile();
#ifndef OPENTHERMOSTAT_E32V2
		refreshClassicStatus();
#endif
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
#ifdef OPENTHERMOSTAT_E32V2
        if(monitor_.capabilities().profile()!=BoilerProtocol::plus) {
            const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
            const bool classic=monitor_.capabilities().profile()==BoilerProtocol::classic;
            monitor_.writeLegacyStatus(ss,now,!classic);
            if(classic) {
                ss << ",\"controller_request\":";
                boilerTest_.writeCommandJSON(ss,now);
                ss << '}';
            }
            return;
        }
#endif
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
        const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        if(group==control::boilerProfileGroup){writeBoilerProfileTopic(out,profile_);return;} // fw/config/boiler_profile
        if(group<control::boilerFieldGroupCount){monitor_.writeFieldGroup(out,now,group);return;}
        // Groups 7..: the entity catalog (boiler.fields.v2), same field shape.
        if(group>=control::boilerFieldGroupCountV2)return;
        out<<"{\"schema\":1,\"sampled_at_ms\":"<<now<<",\"profile\":\""<<monitor_.capabilities().name()<<"\",\"fields\":[";
        const size_t begin=group*control::boilerFieldsPerGroup;
        const size_t end=std::min(begin+control::boilerFieldsPerGroup,control::catalogFieldBase+ems::entityFieldCount);
        for(size_t i=begin;i<end;++i) {
            const auto f=entities_.field(i-control::catalogFieldBase,now);
            out<<(i==begin?"":",")<<'['<<i<<',';
            if(f&&f->valid)out<<f->raw;else out<<"null";
            out<<',';if(f)out<<f->observedMs;else out<<"null";
            out<<','<<(f?unsigned(control::catalogFieldQuality):0u)<<','<<(f?f->type:0)<<']';
        }
        out<<"]}";
    }
    // The other controller's (tado) requested flow from 0x1A, for the shadow
    // comparison; nullopt when unknown or older than the table's lifetime.
    std::optional<uint8_t> thermostatRequestedFlowC() const {
        static_assert(std::string_view(ems::entityCatalog[ems::entityFieldRows[0]].id)=="thermostat_requested_flow_temperature");
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto f=entities_.field(0,static_cast<uint64_t>(esp_timer_get_time()/1000));
        if(!f||!f->valid||f->raw<0||f->raw>100)return std::nullopt;
        return static_cast<uint8_t>(f->raw);
    }
    // GET /status/boiler/profile: which boiler fields this boiler has.
    void getBoilerProfile(std::ostream& out) const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        writeBoilerProfileJSON(out,profile_,static_cast<uint64_t>(esp_timer_get_time()/1000));
    }
    // The owner's "show anyway" for a not_fitted field (wire index); false: not allowed.
    bool setBoilerProfileShown(size_t wireIndex,bool show) {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto slot=BoilerProfile::slotOf(wireIndex);
        return slot&&profile_.setShown(*slot,show,static_cast<uint64_t>(esp_timer_get_time()/1000));
    }
    control::BurnerCycleMonitor::Summary burnerCycles() const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        return burnerCycles_.summary(static_cast<uint64_t>(esp_timer_get_time()/1000));
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
		// One coherent UI snapshot: devices, received fields and scoped operation
		// metadata share the same lock/time. Consumers never re-read the bus.
		ss << ",\"inventory\":";
		deviceInventory_.writeJSON(ss,snapshotMs);
		ss << ",\"ems_entities\":";
		entities_.writeJSON(ss,snapshotMs);
		ss << ",\"burner_cycles\":";
		burnerCycles_.writeJSON(ss,snapshotMs);
		ss << ",\"dhw_episodes\":";
		dhwEpisodes_.writeJSON(ss,snapshotMs);
		ss << ",\"transport\":{\"enabled\":"
		   << (emsConfig_.emsEnabled ? "true" : "false")
		   << ",\"transmit_compiled\":" << ((board::emsTransmitAllowed || board::emsManualTestTransmitAllowed) ? "true" : "false")
		   << ",\"poll_count\":" << polls_.load(std::memory_order_relaxed)
		   << ",\"transmitted_frames\":" << txFrames_.load(std::memory_order_relaxed)
		   << ",\"receive_queue_dropped\":" << rxDropped_.load(std::memory_order_relaxed)
		   << ",\"invalid_telegrams\":" << invalidTelegrams_.load(std::memory_order_relaxed)
		   << ",\"uart_errors\":" << uart_.rxErrors.load(std::memory_order_relaxed)
		   << ",\"uart_timeouts\":" << uart_.rxTimeouts.load(std::memory_order_relaxed)
		   << ",\"uart_resets\":" << uart_.resets.load(std::memory_order_relaxed)
		   << ",\"echo_break_recoveries\":" << uart_.echoBreakRecoveries.load(std::memory_order_relaxed)
		   << ",\"break_realignments\":" << uart_.breakRealignments.load(std::memory_order_relaxed);
        const auto uartError=uart_.lastRxError();
        ss << ",\"last_uart_error\":{\"reason\":\"" << uartError.reason
           << "\",\"observed_at_ms\":" << uartError.observedAtMs;
#ifdef OPENTHERMOSTAT_E32V2
        ss << ",\"echo_fault\":";
        uart_.lastEchoFault().writeJSON(ss);
#endif
        ss << "}}";
#ifdef OPENTHERMOSTAT_E32V2
        ss<<",\"settings_policy\":{\"transmit_compiled\":"<<(board::emsSettingsTransmitAllowed?"true":"false")
          <<",\"installation_reviewed\":"<<(settingsInstallationReviewed_?"true":"false")<<'}';
        ss<<",\"settings\":";
        boilerSettings_.writeJSON(ss,snapshotMs,boilerSettingsPermitted(),operatorSession);
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
        ss << ",\"heat_trial\":{\"mode\":\"" << EcomlineCommissioningProfile::mode
           << "\",\"profile_id\":\"" << ClassicHeatTrialEnvelope::profileId(manualHeatPressureSource_)
           << "\",\"installation_reviewed\":" << (manualHeatInstallationReviewed_ ? "true" : "false")
           << ",\"digital_pressure_required\":"
           << (manualHeatPressureSource_ == ClassicHeatTrialEnvelope::PressureSource::reportedSensor ? "true" : "false")
           << ",\"separate_pressure_method_reviewed\":"
           << (manualPressureMethodReviewed_ ? "true" : "false")
           << ",\"operator_gauge_reading_required\":true"
           << ",\"telemetry_ready\":" << (heat.ready ? "true" : "false")
           << ",\"reason\":\"" << heat.reason << "\",\"physical_validation\":false,\"limits\":{"
           << "\"minimum_flow_c\":" << static_cast<unsigned>(ClassicHeatTrialEnvelope::profile().minimumFlowC)
           << ",\"maximum_flow_c\":" << static_cast<unsigned>(ClassicHeatTrialEnvelope::profile().maximumFlowC)
           << ",\"maximum_duration_s\":" << ClassicHeatTrialEnvelope::profile().maximumHeatMs / 1000
           << ",\"minimum_pressure_decibar\":" << BoilerTestService::minimumManualPressureDecibar
           << ",\"maximum_pressure_decibar\":" << ClassicHeatTrialEnvelope::maximumPressureDecibar
           << ",\"minimum_measured_flow_centi\":" << ClassicHeatTrialEnvelope::minimumMeasuredFlowCenti
           << ",\"maximum_measured_flow_centi\":" << ClassicHeatTrialEnvelope::maximumMeasuredFlowCenti << "}},\"controller_request\":";
        boilerTest_.writeCommandJSON(ss,snapshotMs);
#endif
		ss << '}';
	}
#ifdef OPENTHERMOSTAT_E32V2
    void boilerSettingsSynchronize(const control::WebAuthSession& sessions,uint64_t now,bool updateAllowed){
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        settingsUpdateAllowed_=updateAllowed;
        boilerSettings_.synchronizeSessions(sessions,now);
        configurationRead_.synchronizeSessions(sessions,now);
        settingsOwnsBus_.store(boilerSettings_.active(),std::memory_order_release);
    }
    void boilerSettingsStatus(std::ostream& out,std::string_view requester={}) const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        boilerSettings_.writeJSON(out,static_cast<uint64_t>(esp_timer_get_time()/1000),boilerSettingsPermitted(),requester);
    }
    int boilerSettingsWrite(std::string_view body,std::string_view owner,const control::WebAuthSession& sessions,std::ostream& out) {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        if(activeHeat_.claimed()){out<<"{\"accepted\":false,\"error\":\"active_heat_owns_boiler\"}";return 409;}
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
    // Active heating (control/ActiveHeatGuard): one locked view per 10 s step,
    // then the step's command for the boiler's next poll of 0x0B.
    struct ActiveHeatView {
        std::optional<ForeignBoilerRequest::Record> foreign;
        std::optional<uint8_t> limitC;
        std::optional<bool> burnerOn;
        std::optional<int16_t> flowCentiC;
        bool routeReady = false;
        std::optional<ActiveHeatPollDriver::Result> last;
        // For FlowLearner (report only). hotWater: the 0x18 DHW bit (3-way valve
        // on hot water, with or without flame), the same bit DhwEpisodes counts.
        std::optional<bool> hotWater;
        std::optional<uint8_t> modulationPct;
        std::optional<int16_t> returnCentiC;
        std::optional<uint64_t> limitAtMs; // when the boiler reported limitC (0x16)
        uint32_t limitReads = 0;           // the E32's own 0x16 read requests this boot
        std::optional<uint64_t> boilerHeardAtMs; // the latest boiler report (proof the bus is heard)
    };
    ActiveHeatView activeHeatView() const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
        const auto modulation = monitor_.value(BoilerField::modulation, now);
        const auto flow = monitor_.value(BoilerField::flow, now);
        const auto state = monitor_.value(BoilerField::rawState, now);
        const auto ret = monitor_.value(BoilerField::returnTemp, now);
        return {foreignRequest_.last, ActiveHeatEnvelope::limitC(monitor_),
            modulation ? std::optional<bool>(*modulation > 0) : std::nullopt,
            flow ? std::optional<int16_t>(static_cast<int16_t>(*flow)) : std::nullopt,
            board::emsActiveHeatAllowed && activeHeatRouteReady(), activeHeat_.last(),
            state ? std::optional<bool>((*state & 0x02) != 0) : std::nullopt,
            modulation && *modulation >= 0 && *modulation <= 100 ? std::optional<uint8_t>(static_cast<uint8_t>(*modulation)) : std::nullopt,
            ret ? std::optional<int16_t>(static_cast<int16_t>(*ret)) : std::nullopt,
            ActiveHeatEnvelope::reportedAtMs(monitor_), limitRead_.sent(), monitor_.lastReportMs()};
    }
    // Today's and the last 7 days' hot water for /status/heating (nullptr: no memory).
    cJSON* dhwSummaryJson() const {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        return dhwEpisodes_.summaryJson();
    }
    uint32_t activeHeatPost(std::optional<uint8_t> flowC, bool heatAllowed, bool claim) {
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        return activeHeat_.post(static_cast<uint64_t>(esp_timer_get_time() / 1000), flowC, heatAllowed, claim);
    }
	int boilerTestAction(std::string_view action, std::string_view body, std::string_view operatorSession,
                        const control::WebAuthSession& sessions, std::ostream &ss) {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
        if(boilerSettings_.active()&&action!="stop"&&action!="close_fault"){
            ss<<"{\"accepted\":false,\"error\":\"settings_write_active\"}";return 409;
        }
        // The active guard owns the boiler or withdraws its request: no trial or read.
        if(activeHeat_.claimed()&&action!="stop"&&action!="close_fault"&&action!="keepalive"){
            ss<<"{\"accepted\":false,\"error\":\"active_heat_owns_boiler\"}";return 409;
        }
        if(action=="read_configuration"||action=="read_identity") {
            const auto kind=action=="read_identity"?ClassicConfigurationRead::Kind::identity:ClassicConfigurationRead::Kind::configuration;
            // Inventory is read under the telemetry lock held above.
            const auto result=configurationRead_.request(body,operatorSession,now,configurationReadPermitted(),boilerTest_.active(),sessions,kind,
                [this](uint8_t address){return deviceInventory_.contains(address);});
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
#ifdef OPENTHERMOSTAT_E32V2
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        if(monitor_.capabilities().profile()!=BoilerProtocol::plus) {
            ss<<'{';
            if(monitor_.capabilities().profile()==BoilerProtocol::classic) {
                if(const auto limit=monitor_.value(BoilerField::heatingLimit,static_cast<uint64_t>(esp_timer_get_time()/1000)))
                    ss<<"\"heatingTemperature\":"<<*limit/100;
            }
            ss<<'}';return;
        }
#endif
		boilerParams_.getJSON(ss);
	}

	std::string getBoilerParams() const {
		std::ostringstream ss;getBoilerParams(ss);return ss.str();
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
	// Read-modify-write atomics (exchange, fetch_add, CAS) are static: the
	// controller lives in PSRAM, where the ESP32's S32C1I is not atomic; .bss
	// is internal RAM. One EMS bus per device (diagnostics/AtomicPlacement.h).
	static inline std::atomic<bool> resetRequested_{false};
	std::atomic<bool> captureForeignTelegrams_{false};
	static inline std::atomic<uint32_t> rxDropped_{0};
	static inline std::atomic<uint32_t> invalidTelegrams_{0};
	static inline std::atomic<uint32_t> polls_{0};
	static inline std::atomic<uint32_t> txFrames_{0};
	static inline std::atomic<uint32_t> maxPollServiceUs_{0};
	unsigned long lastStatsMillis_ = 0;

	std::mutex telegramProcessorsMutex_;
	std::unordered_map<uint16_t, std::list<std::function<void(EmsTelegram const &)>>> telegramProcessors_;

	EmsBoilerState boilerState_;
	EmsBoilerParams boilerParams_;
	mutable std::mutex telemetryMutex_;
	ClassicBoilerMonitor monitor_;
    EmsDeviceInventory deviceInventory_;
    EmsEntityObserver entities_; // passive EMS+/thermostat table, telemetry mutex
    BoilerProfile profile_; // which fields this boiler has (fed by monitor_ and entities_), telemetry mutex
    bool profileLoaded_ = false; // loop() only
    // Once, before the first decoded frame of the boot; then debounced writes,
    // NVS IO outside the telemetry lock.
    void loadBoilerProfile() {
        if(profileLoaded_)return;
        profileLoaded_=true;
#if __has_include(<nvs.h>)
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        BoilerProfileStore::load(profile_,static_cast<uint64_t>(esp_timer_get_time()/1000));
#endif
    }
    void saveBoilerProfile() {
#if __has_include(<nvs.h>)
        std::optional<BoilerProfile::Record> record;
        {
            std::lock_guard<std::mutex> lock(telemetryMutex_);
            record=profile_.takeWrite(static_cast<uint64_t>(esp_timer_get_time()/1000));
        }
        if(!record)return;
        const bool ok=BoilerProfileStore::write(*record);
        std::lock_guard<std::mutex> lock(telemetryMutex_);
        profile_.written(ok);
#endif
    }
    control::BurnerCycleMonitor burnerCycles_; // short-cycling from the 0x18 flame bit, telemetry mutex
    control::DhwEpisodes dhwEpisodes_; // tapping vs keeping warm from 0x18/0x34, telemetry mutex
#ifdef OPENTHERMOSTAT_E32V2
	// A real, restricted attended commissioning route. Its pressure reading and
    // site declarations are scoped to each accepted preparation, not persisted.
	BoilerTestService boilerTest_{EcomlineCommissioningProfile::service(
        (static_cast<uint64_t>(esp_random()) << 32) | esp_random(), board::emsManualTestTransmitAllowed)};
    ManualClassicTransaction manualTransaction_; // UART task only, never HTTP/loop.
    static inline std::atomic<uint32_t> manualCompletions_{0},manualRejections_{0},manualReplyErrors_{0}; // internal RAM, see resetRequested_
    template<bool Read>
    bool transmitManualFrame(const EmsRawFrame& frame){
        if(!manualTransaction_.begin(frame.data.data(),frame.length,static_cast<uint64_t>(esp_timer_get_time())))return false;
        bool sent=false;
        try{sent=uart_.writeManualTestToEms<Read>(frame.data.data(),frame.length);}catch(...){sent=false;}
        manualTransaction_.finish(sent,static_cast<uint64_t>(esp_timer_get_time()));
        if(sent)txFrames_.fetch_add(1,std::memory_order_relaxed);
        return sent;
    }
    void processManualReply(const uint8_t* data,size_t length,uint64_t acquiredAtUs){
        if constexpr(!board::emsManualTestTransmitAllowed)return;
        else {
            const auto result=manualTransaction_.receive(data,length,acquiredAtUs,
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
            && monitor_.capabilities().profile()==BoilerProtocol::classic && settingsUpdateAllowed_;
    }
    static constexpr bool manualHeatInstallationReviewed_ = false;
    // Fixed target installation: the user's Ecomline Classic has no digital
    // pressure sensor. These flags record completed physical qualification;
    // the attended commissioning profile requires a new local gauge reading
    // instead. Neither a catalogue photo nor commissioning qualifies the site.
    static constexpr auto manualHeatPressureSource_ = ClassicHeatTrialEnvelope::PressureSource::separateCheck;
    static constexpr bool manualPressureMethodReviewed_ = false;
    ClassicHeatTrialEnvelope::Check heatTrialEnvelope(uint64_t now) const {
        return EcomlineCommissioningProfile::inspect(monitor_, now, boilerTest_.heating());
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
        return EcomlineCommissioningProfile::gates(monitor_, static_cast<uint64_t>(esp_timer_get_time() / 1000),
            manualTransportReviewed() && !configurationRead_.active() && !boilerSettings_.active() && settingsUpdateAllowed_, boilerTest_.heating());
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
    // Active heating shares the trial's identity, encoder, write and gates;
    // it never runs beside the trial, a configuration read or a settings write.
    ForeignBoilerRequest foreignRequest_; // telemetry mutex
    ActiveHeatPollDriver activeHeat_{boilerTest_.bootId(), board::emsActiveHeatAllowed}; // telemetry mutex
    // The boiler's own limit for active heating: read-only 0x16, same route and gates.
    BoilerLimitRead limitRead_{board::emsBoilerLimitReadAllowed}; // telemetry mutex
    bool activeHeatRouteReady() const {
        return manualTransportReviewed() && monitor_.capabilities().profile()==BoilerProtocol::classic
            && !boilerTest_.active() && !configurationRead_.active() && !boilerSettings_.active();
    }
	static inline std::atomic<bool> boilerTestTransportFault_{false}; // internal RAM, see resetRequested_
	uint32_t boilerTestUartErrorsSeen_ = 0; // UART task only
#endif
	control::TemperatureSample outdoorSample_;

	std::atomic<std::optional<int16_t>> emsOutdoorTemperature_;

	static inline std::atomic_size_t txNotConfirmed_{0}; // internal RAM, see resetRequested_
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
