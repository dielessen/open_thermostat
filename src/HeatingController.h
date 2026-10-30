#pragma once
#include "Logging.h"

#include "BeaconBleAddress.h"
#include "BoilerController.h"
#include "BuiltinGpioPort.h"
#include "PcfGpioPort.h"
#include "BeaconTemperatureReader.h"
#include "control/BleDeviceDiscovery.h"
#include "OpenWeather.h"
#include "PeriodicCounter.h"
#include "EmsController.h"
#include "EmsMetrics.h"
#include "MQTT.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "control/ControlBuildCapabilities.h"
#include "control/BleDeviceSettings.h"
#include "control/ManagedBleObserver.h"
#include "control/MbedTlsBleCcm.h"
#include "DeviceBluetoothSettings.h"
#include "HeatingPlanStore.h"
#include "FlowSettingsStore.h"
#include "RoomOverridesStore.h"
#include "control/ShadowComparison.h"
#include "control/RoomEngine.h"
#include "control/ActiveHeatGuard.h"
#include "control/HandoverConfirmation.h"
#include "control/HeatingInput.h"
#include "control/HeatingTelemetry.h"
#include "control/HeatingHistory.h"
#include <esp_heap_caps.h>
#include "diagnostics/BlackBox.h"
#include <cmath>
#include <cstring>
#include <ctime>
#include <esp_timer.h>
#include <esp_ota_ops.h>
#include "update/GitHubUpdate.h"
#include "update/RestartTimer.h"
#endif
#include <esp_system.h>
#include "Room.h"

#include <logger/LoggerInterface.h>
#include <algorithm>
#include <atomic>
#include <functional>
#include <memory>
#include <set>
#include <unordered_map>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace heating {
#ifdef OPENTHERMOSTAT_E32V2
extern bool networkTimeTrusted; // main.cpp: NTP synchronized this boot
#endif

// Build label -> PcfDevice map from config so all pins on the same extender share one shadow register.
using PcfDeviceMap = std::unordered_map<std::string, std::shared_ptr<gpio::PcfDevice>>;

inline PcfDeviceMap buildPcfDeviceMap() {
	PcfDeviceMap map;
	for (auto const &ext : config::getGpioExtenders()) {
		bool wide = (ext.type == "pcf8575" || ext.type == "mcp23017");
		map[ext.label] = std::make_shared<gpio::PcfDevice>(ext.address, wide);
	}
	return map;
}

inline std::unique_ptr<gpio::GpioPort> createGpioPort(std::shared_ptr<ib::logger::LoggerInterface> const &log, ib::logger::LoggerInterface::LogFeatureType feature, config::PinConfig const &pinCfg, PcfDeviceMap const &pcfDevices) {
	if (pinCfg.source == "builtin") {
		return std::make_unique<gpio::BuiltinGpioPort>(pinCfg.pin);
	}
	// source = "ext:<label>"
	if (pinCfg.source.rfind("ext:", 0) == 0) {
		std::string label = pinCfg.source.substr(4);
		auto it = pcfDevices.find(label);
		if (it != pcfDevices.end()) {
			return std::make_unique<gpio::PcfGpioPort>(it->second, pinCfg.pin);
		}
		DBGLOGFI(log, feature, "createGpioPort: extender '%s' not found in config\n", label.c_str());
	}
	return std::make_unique<gpio::NullGpioPort>();
}

inline std::unique_ptr<gpio::GpioPort> createBoilerPort(std::shared_ptr<ib::logger::LoggerInterface> const &log, ib::logger::LoggerInterface::LogFeatureType feature, PcfDeviceMap const &pcfDevices) {
	auto pin = config::getBoilerPin();
	if (!pin)
		return std::make_unique<gpio::NullGpioPort>();
	return createGpioPort(log, feature, *pin, pcfDevices);
}

inline std::vector<std::unique_ptr<gpio::GpioPort>> createValvePorts(std::shared_ptr<ib::logger::LoggerInterface> const &log, ib::logger::LoggerInterface::LogFeatureType feature, PcfDeviceMap const &pcfDevices) {
	auto pins = config::getValvePins();
	std::vector<std::unique_ptr<gpio::GpioPort>> ports;
	ports.reserve(pins.size());
	for (auto const &p : pins) {
		ports.push_back(createGpioPort(log, feature, p, pcfDevices));
	}
	return ports;
}

inline std::vector<std::string> createValveLabels() {
	auto pins = config::getValvePins();
	std::vector<std::string> labels;
	labels.reserve(pins.size());
	for (uint8_t i = 0; i < pins.size(); ++i) {
		labels.push_back(pins[i].label.empty() ? std::to_string(i) : pins[i].label);
	}
	return labels;
}

inline std::unordered_map<std::string, uint8_t> buildValveLabelMap() {
	auto pins = config::getValvePins();
	std::unordered_map<std::string, uint8_t> map;
	for (uint8_t i = 0; i < pins.size(); ++i) {
		map[std::to_string(i)] = i; // backward compat: "0" → 0
		if (!pins[i].label.empty()) {
			map[pins[i].label] = i;
		}
	}
	return map;
}

class HeatingController {
public:
	using boilerHeatingTemperatureOverride_t = BoilerController::boilerHeatingTemperatureOverride_t;

	explicit HeatingController(std::shared_ptr<ib::logger::LoggerInterface> log) : log_(std::move(log)), logFeature_(log_ ? log_->addFeature("HeatCtrl") : 0), openWeather_(log_, config::getOpenWeatherConfig()), currentProgram_(config::getCurrentProgram()), rooms_(buildRoomsFromConfig()) {
		DBGLOGFI(log_, logFeature_, "HeatingController constructed\n");
		bluetoothScan_ = true;
#ifdef OPENTHERMOSTAT_E32V2
        const auto raw = readDeviceBluetoothSettings();
        auto root = control::parseControlJson({raw.c_str(), raw.length()}, true);
        std::unique_ptr<control::ManagedBleBindings> bindings(new(std::nothrow) control::ManagedBleBindings);
        if (bindings && control::readManagedBleBindings(root.get(), *bindings) == control::BleSettingsError::none)
            managedBle_.initialize(*bindings);
        else managedBle_.disable(control::BleObserverStop::configuration_invalid);
        tempReader_.setRawObserver([this](const BleAddress_t& address, int rssi, const uint8_t* data, size_t size) {
            const auto now = bleReceiptClock();
            // Seconds since boot + 1: the supervisor's proof that the NimBLE host
            // still delivers adverts. ANY advert counts: one bound sensor with a
            // dead battery must not restart the E32 (30 min .. 4 h); its room
            // shows the stale reading instead. Only a host that hears nothing
            // at all is restarted.
            bleAdvertHeardS_.store(static_cast<uint32_t>(now / 1000) + 1, std::memory_order_relaxed);
            managedBle_.capture(address, rssi, data, size, now);
            // Nearby hints only while the user's Search runs: automatic scans never fill the list.
            if (!tempReader_.discovering()) return;
            std::lock_guard<std::mutex> lock(roomsAccessMutex_);
            bleDiscovery_.remember(address, rssi, data, size);
        });
        loadHeatingPlan();
        // 24 h charts (GET /status/history): once, PSRAM only; without it the chart is unavailable.
        history_.begin([](size_t size) { return heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT); }, heap_caps_free);
        loadFlowSettings();
        overrides_.restore(RoomOverridesNvs::read()); // waits for a trusted clock before it applies
        // A stored "thermostat disconnected" (same firmware) resumes active heat
        // after 2 min of bus reception without a foreign 0x1A, which clears it.
        if (handover_.restore()) activeGuard_.restore(bleReceiptClock());
        mqtt_.setHeatingRoute([this](std::string_view payload) { heatingInput(payload); }, [this] {
            // The compact form, split into the small MQTT topics (HeatingStateTopics.h): no past
            // days, static plan fields, learned or hot water (summary and learned/<id> carry those).
            cJSON* status = heatingStatusJson(true);
            if (status) control::compactHeatingTelemetry(status);
            return status;
        }, [this] { return roomEngine_.plan().rooms.size(); }, [this](size_t room, std::string& id) {
            const auto& plan = roomEngine_.plan();
            if (room >= plan.rooms.size()) return std::string();
            id = plan.rooms[room].id;
            std::array<std::optional<int16_t>, control::RoomPlan::maxRooms> temperatures{};
            const auto context = learnedContext(bleReceiptClock(), temperatures);
            return control::learnedRoomTelemetry(flowLearner_, plan, room, context);
        }, [this] {
            std::array<std::optional<int16_t>, control::RoomPlan::maxRooms> temperatures{};
            return control::heatingSummaryTelemetry(flowLearner_, learnedContext(bleReceiptClock(), temperatures), ems_.dhwSummaryJson(), &flowPolicy_);
        });
#endif
	}

	~HeatingController() { stopBluetoothAndDeinitBLE(); }

	void operate() {
#ifdef OPENTHERMOSTAT_E32V2
		stepHeating();
#endif
		// Modern shadow runtime owns its targets. Never execute the old room
		// scheduler/boiler writer alongside it, even if provisioning is invalid.
		if(mqtt_.modernMode()) return;
		bool shouldStartBoiler = false;
		bool shouldBoilerContinue = false;
		boilerHeatingTemperatureOverride_t boilerHeatingTempOverride;

		std::set<uint8_t> valvesWhichShouldBeClosed;

		{ // mutex scope
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		for (auto const &room : rooms_) {
			if (room->isEnabled()) {
				auto [roomStatus, roomBoilerHeatingTempOverride] = room->shouldStartBoilerAndHeat();

				shouldStartBoiler = shouldStartBoiler || roomStatus == Room::TemperatureStatus::START_HEATING;
				shouldBoilerContinue = shouldBoilerContinue || roomStatus == Room::TemperatureStatus::CONTINUE_HEATING;

				if (roomBoilerHeatingTempOverride.has_value()) {
					boilerHeatingTempOverride = std::max(boilerHeatingTempOverride.value_or(0), roomBoilerHeatingTempOverride.value()); // use highest boiler supply temperature from overrides
				}

				// valve should be closed only if temperature is in upper/lower margin - in case of no samples, valve should remain open but should not trigger or continue heating
				if (roomStatus == Room::TemperatureStatus::TEMPERATURE_OK) {
					auto valves = room->getValves();
					if (log_->isFeatureEnabled(logFeature_)) {
						DBGLOGFD(log_, logFeature_, "  adding valves to close for room %s valves: ", room->getName().c_str());
						for (auto const &valve : valves) {
							DBGLOGFI(log_, logFeature_, "'%s' ", valve.c_str());
						}
						DBGLOGFI(log_, logFeature_, "");
					}

					for (auto const &valve : valves) {
						auto it = valveLabelMap_.find(valve);
						if (it != valveLabelMap_.end()) {
							valvesWhichShouldBeClosed.insert(it->second);
						}
					}
				}
			} else { // room is diabled - let's heat it because we don't know what happened
					 //				valvesWhichShouldBeOpened.insert(room.valves_.begin(), room.valves_.end());
			}

		}
		}

		boiler_.handleValves(valvesWhichShouldBeClosed);
		boiler_.startBoilerOrContinue(shouldStartBoiler, shouldBoilerContinue, boilerHeatingTempOverride);


		DBGLOGFD(log_, logFeature_, "%s\n", boiler_.getStatus().c_str());

		if (bluetoothScan_ && !bleDiscoveryRequested_) {
			tempReader_.triggerScan();
		}

		openWeather_.operate();
	}

	void loop() {
#ifdef OPENTHERMOSTAT_E32V2
        diagnostics::blackBox.loopPhase(diagnostics::LoopPhase::bluetooth);
        managedBle_.processOne(update::busy());
        // A requested Search goes first at the next scan boundary; automatic scans wait.
        if (bleDiscoveryRequested_) {
            if (!bluetoothScan_ || uint32_t(millis() - bleDiscoveryRequestedAt_) > 120000u) bleDiscoveryRequested_ = false;
            else if (!update::busy() && tempReader_.triggerScan(30000, [this] {
                std::lock_guard<std::mutex> lock(roomsAccessMutex_); bleDiscovery_.clear();
            })) bleDiscoveryRequested_ = false;
        } else if (mqtt_.modernMode() && bluetoothScan_ && managedBle_.wantsAutomaticScan() && !update::busy()) tempReader_.triggerScan(0, {}, true);
        diagnostics::blackBox.loopPhase(diagnostics::LoopPhase::mqtt);
#endif
		mqtt_.loop();
#ifdef OPENTHERMOSTAT_E32V2
        diagnostics::blackBox.loopPhase(diagnostics::LoopPhase::ems);
#endif
		ems_.loop();
	}
	bool modernMode() const { return mqtt_.modernMode(); }
#ifdef OPENTHERMOSTAT_E32V2
    void historyJson(std::ostream& out) const { history_.json(out, bleReceiptClock()); } // GET /status/history
    void stopManagedBle() { managedBle_.disable(control::BleObserverStop::configuration_changed); }
    // The room plan is the single room list of the heating control. Shadow
    // mode computes and reports the request; active mode (only with the
    // firmware gate) lets ActiveHeatGuard send it after the owner's handover.
    std::string heatingPlanJson() const { return roomEngine_.plan().json(); }
    const char* setHeatingPlan(const cJSON* root) {
        control::RoomPlan plan;
        if (const char* error = control::RoomPlan::parse(root, plan)) return error;
        if (plan.mode == control::RoomPlan::Mode::active && !board::emsActiveHeatAllowed) return "active_mode_not_released";
        // Edited from HA and from the web page: a write based on an older plan is refused.
        if (!cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(root, "revision"))
            || plan.revision != roomEngine_.plan().revision) return "plan_changed";
        // Unchanged except for the revision (HA automations resend the plan):
        // no flash write and no new revision; the caller answers the stored plan.
        if (plan.json() == roomEngine_.plan().json()) return nullptr;
        plan.revision = roomEngine_.plan().revision + 1;
        // The stored form: week programs packed only when the API form does not fit.
        const auto raw = plan.storedJson();
        if (raw.size() + 1 > control::RoomPlan::storeBytes) return "plan_too_large";
        if (raw.empty()) return "save_unconfirmed";
        const auto saved = saveHeatingPlan(raw);
        if (saved == HeatingPlanSave::storage_full) return "storage_full";
        if (saved != HeatingPlanSave::saved) return "save_unconfirmed";
        roomEngine_.setPlan(plan);
        flowLearner_.setPlan(plan);
        return nullptr;
    }
    // The owner's handover on the page: true = "the tado is disconnected from
    // the boiler", false withdraws it ("back to the thermostat"). Stored in NVS
    // at once; cleared by a foreign 0x1A, the hand-back or new firmware.
    const char* setHeatingHandover(bool tadoDisconnected) {
        if (tadoDisconnected && !board::emsActiveHeatAllowed) return "active_mode_not_released";
        if (tadoDisconnected && roomEngine_.plan().mode != control::RoomPlan::Mode::active) return "plan_not_active";
        activeGuard_.confirm(bleReceiptClock(), tadoDisconnected);
        handover_.sync(activeGuard_.confirmed());
        return nullptr;
    }
    // The beta.19 flow options (GET/POST /config/heating/flow), stored in NVS.
    std::string flowSettingsJson() const { return flowPolicy_.settings().json(); }
    const char* setFlowSettings(const cJSON* root) {
        auto settings = flowPolicy_.settings();
        if (const char* error = control::FlowSettings::parse(root, settings)) return error;
        if (settings == flowPolicy_.settings()) return nullptr;
        if (!FlowSettingsNvs::write(settings)) return "save_unconfirmed";
        flowPolicy_.setSettings(settings); flowLearner_.setApplied(settings.applyLearned);
        return nullptr;
    }
    // GET/POST /config/heating/comfort (control/RoomOverrides.h): overrides and away,
    // stored in NVS only when the record changes; the state is kept only once saved.
    cJSON* heatingComfortJson() const { return overrides_.json(roomEngine_.plan(), bleReceiptClock()); }
    const char* setHeatingComfort(const cJSON* root) {
        std::unique_ptr<control::RoomOverrides> next(new (std::nothrow) control::RoomOverrides(overrides_));
        if (!next) return "save_unconfirmed";
        std::optional<uint32_t> utc;
        if (networkTimeTrusted) utc = static_cast<uint32_t>(std::time(nullptr));
        bool persist = false;
        if (const char* error = next->command(root, roomEngine_.plan(), bleReceiptClock(), utc, persist)) return error;
        if (persist && !RoomOverridesNvs::write(next->stored())) return "save_unconfirmed";
        overrides_ = *next;
        return nullptr;
    }
    cJSON* activeHeatJson() const {
        const auto now = bleReceiptClock();
        cJSON* active = activeGuard_.json(now);
        if (!active) return nullptr;
        cJSON_AddBoolToObject(active, "enabled", board::emsActiveHeatAllowed); // the firmware gate
        cJSON_AddBoolToObject(active, "confirmation_stored", handover_.stored());
        // Today's boiler maximum: its own 0x16 heating limit, the active ceiling.
        cJSON* limit = cJSON_AddObjectToObject(active, "boiler_limit");
        if (limitC_) cJSON_AddNumberToObject(limit, "flow_c", *limitC_); else cJSON_AddNullToObject(limit, "flow_c");
        if (limitAtMs_ && now >= *limitAtMs_) cJSON_AddNumberToObject(limit, "age_s", double((now - *limitAtMs_) / 1000));
        else cJSON_AddNullToObject(limit, "age_s");
        cJSON_AddNumberToObject(limit, "reads", limitReads_);
        return active;
    }
    // The room engine status plus the E32's own Bluetooth sensors, so HA can
    // show them and offer them as room sources (they stay paired here).
    // mqtt: for the fw/state/* topics, without learned and dhw (not computed).
    cJSON* heatingStatusJson(bool mqtt = false) {
        cJSON* root = roomEngine_.json();
        // Overrides, window pauses and away per room, and the house's away (control/RoomOverrides.h).
        if (root && !overrides_.addStatus(root, roomEngine_.plan(), bleReceiptClock())) { cJSON_Delete(root); return nullptr; }
        cJSON* sensors = root ? cJSON_AddArrayToObject(root, "ble_sensors") : nullptr;
        // Burner starts in the last hour from the flame bit (the adapter's own counters read 0).
        if (root) control::addBurnerJson(root, ems_.burnerCycles());
        cJSON* shadow = sensors ? shadowComparison_.json() : nullptr;
        if (!shadow || !cJSON_AddItemToObject(root, "shadow", shadow)) { cJSON_Delete(shadow); cJSON_Delete(root); return nullptr; }
        cJSON* active = activeHeatJson();
        if (!active || !cJSON_AddItemToObject(root, "active", active)) { cJSON_Delete(active); cJSON_Delete(root); return nullptr; }
        // The applied request and its source (rule, curve, learned, optimum start); details not on MQTT.
        if (!flowPolicy_.addStatus(root, mqtt)) { cJSON_Delete(root); return nullptr; }
        const auto& bindings = managedBle_.bindings();
        for (size_t i = 0; i < bindings.count; ++i) {
            const auto& binding = bindings.devices[i];
            const auto value = managedBle_.snapshot(binding.address);
            cJSON* s = cJSON_CreateObject();
            if (!s || !cJSON_AddItemToArray(sensors, s)) { cJSON_Delete(s); cJSON_Delete(root); return nullptr; }
            const auto scaled = [&](const char* key, auto v, double divisor) {
                if (v) cJSON_AddNumberToObject(s, key, *v / divisor); else cJSON_AddNullToObject(s, key);
            };
            cJSON_AddStringToObject(s, "id", control::printBleHex(binding.address).data());
            cJSON_AddStringToObject(s, "name", binding.name.data());
            cJSON_AddStringToObject(s, "profile", control::managedBleProfileName(binding.profile));
            scaled("temperature", value.temperature, 100.0);
            scaled("humidity", value.humidity, 100.0);
            scaled("battery", value.battery, 1.0);
            scaled("age_s", value.temperatureAgeMs ? std::optional<uint32_t>(*value.temperatureAgeMs / 1000) : std::nullopt, 1.0);
        }
        const auto now = bleReceiptClock();
        // The HA route's freshness for the rooms page banner.
        if (!control::addHaLink(root, haInput_.lastAcceptedMs(), now, brokerConnected())) { cJSON_Delete(root); return nullptr; }
        if (mqtt) return root;
        // What the learner found (report only) and, with a trusted clock, its plans.
        std::array<std::optional<int16_t>, control::RoomPlan::maxRooms> temperatures{};
        cJSON* learned = control::learnedJson(flowLearner_, roomEngine_.plan(), learnedContext(now, temperatures));
        if (!learned || !cJSON_AddItemToObject(root, "learned", learned)) { cJSON_Delete(learned); cJSON_Delete(root); return nullptr; }
        cJSON* dhw = ems_.dhwSummaryJson();
        if (!dhw || !cJSON_AddItemToObject(root, "dhw", dhw)) { cJSON_Delete(dhw); cJSON_Delete(root); return nullptr; }
        return root;
    }
    // A Home Assistant state (temperature and/or target) for a plan source.
    void heatingHaState(const std::string& entity, std::optional<int16_t> temperature, std::optional<int16_t> target) {
        roomEngine_.haState(entity, temperature, target, bleReceiptClock());
    }
    auto managedBleSnapshot(const control::ManagedBleAddress& address) { return managedBle_.snapshot(address); }
    bool managedBlePending() const { return !managedBle_.enabled(); }
    // Bound sensors and automatic scanning: their adverts are expected.
    bool managedBleExpected() const { return mqtt_.modernMode() && bluetoothScan_ && managedBle_.wantsAutomaticScan() && tempReader_.scanEnabled(); }
    uint32_t bleAdvertHeardS() const { return bleAdvertHeardS_.load(std::memory_order_relaxed); }
    // The E32 owns the boiler or still withdraws its request (loop task): the
    // supervisor then restarts only for a real hang.
    bool claimsBoiler() const { return activeGuard_.claimsBoiler(); }
    // A restart is about to happen (update::loop, loop task): the guard stops
    // and takes no new control this boot; true once no positive request can
    // still be held, or after BoilerReleaseHold::maxMs. Shadow mode: at once.
    bool releaseBoilerForRestart() {
        activeGuard_.withdraw(bleReceiptClock());
        return restartHold_.ready(static_cast<uint32_t>(bleReceiptClock()), activeGuard_.released());
    }
    uint32_t managedBleQueueDrops() const { return managedBle_.queueDrops(); }
    // Queued, not refused: a running automatic scan ends first (loop() starts the Search).
    bool requestBleDiscovery() {
        if (!bluetoothScan_ || !tempReader_.scanEnabled() || tempReader_.discovering()) return false;
        if (!bleDiscoveryRequested_) bleDiscoveryRequestedAt_ = static_cast<uint32_t>(millis());
        return bleDiscoveryRequested_ = true;
    }
    bool bleScanPending() { return bleDiscoveryRequested_ || tempReader_.isScanPending(); }
    // Bounded hints written straight into the (PSRAM) response; no copy, no cJSON tree.
    void writeBleDiscovery(std::ostream& out) const {
        std::lock_guard<std::mutex> lock(roomsAccessMutex_); bleDiscovery_.writeJson(out);
    }
    bool brokerConnected() const {return mqtt_.brokerConnected();}
    bool nativeSourceCurrent(std::string_view expected,std::string_view savedSettings) const {return mqtt_.nativeSourceCurrent(expected,savedSettings);}
    bool nativeSourceHotReady(std::string_view expected,std::string_view savedSettings) const {return mqtt_.nativeSourceHotReady(expected,savedSettings);}
    bool nativeSourceCanApply(std::string_view expected,std::string_view next,std::string_view saved) const {return mqtt_.nativeSourceCanApply(expected,next,saved);}
    bool applyNativeSource(std::string_view expected,std::string_view next,std::string_view previousSettings) {return mqtt_.applyNativeSource(expected,next,previousSettings);}
    void inhibitNativeSourceMutation() {mqtt_.inhibitNativeSourceMutation();}
#endif

	void getBoilerStatus(std::ostream &ss) const {
		boiler_.getStatus(ss);
	}

	std::string getBoilerStatus() const {
		return boiler_.getStatus();
	}

	void getEMSStatus(std::ostream &ss) const {
		const auto status = ems_.getStatus();
		if (status.empty() || status.back()!='}') { ss << "{}"; return; }
		ss << status.substr(0,status.size()-1) << ",\"roomEstimateObservation\":";
		emsMetrics_.getRoomObservation(ss);
		ss << "}";
	}
	void getEMSDeviceStatus(std::ostream &ss) const { ems_.getDeviceStatus(ss); }
	void getBoilerProfile(std::ostream &ss) const { ems_.getBoilerProfile(ss); }
	bool setBoilerProfileShown(size_t wireIndex, bool show) { return ems_.setBoilerProfileShown(wireIndex, show); }
	void getEMSTelemetryStatus(std::ostream &ss, std::string_view operatorSession = {}) const {
		ems_.getTelemetryStatus(ss, operatorSession);
	}
#ifdef OPENTHERMOSTAT_E32V2
    void boilerSettingsSynchronize(const control::WebAuthSession& sessions,uint64_t now,bool updateAllowed){ems_.boilerSettingsSynchronize(sessions,now,updateAllowed);}
    bool boilerSettingsActive()const{return ems_.boilerSettingsActive();}
    void boilerSettingsStatus(std::ostream& out,std::string_view requester={}) const { ems_.boilerSettingsStatus(out,requester); }
    int boilerSettingsWrite(std::string_view body,std::string_view owner,const control::WebAuthSession& sessions,std::ostream& out) {
        return ems_.boilerSettingsWrite(body,owner,sessions,out);
    }
	bool boilerTestActive() const { return ems_.boilerTestActive(); }
	int boilerTestAction(std::string_view action, std::string_view body, std::string_view operatorSession,
                        const control::WebAuthSession& sessions, std::ostream &ss) {
		return ems_.boilerTestAction(action, body, operatorSession, sessions, ss);
	}
#endif

	std::string getEMSStatus() const {
		std::ostringstream ss; getEMSStatus(ss); return ss.str();
	}

	void getEMSBoilerParams(std::ostream &ss) const {
		ems_.getBoilerParams(ss);
	}

	std::string getEMSBoilerParams() const {
		return ems_.getBoilerParams();
	}

	void getFullStatus(std::ostream &ss) const {
		ss << "{";
		ss << "\"rooms\": ";
		if(modernMode()) ss << "[]";
		else getRoomsStatus(ss);
		ss << ",\"controlMode\":\"" << (modernMode()?"shadow":"legacy") << "\"";
		ss << ",";
#ifdef OPENTHERMOSTAT_E32V2
        ss << "\"firmware_update\":" << update::availability() << ",";
        ss << "\"control_build\":";
        control::writeControlBuildCapabilities(ss);
        // Read-only SDK counters also remain available in modern mode, where
        // the legacy MQTT device reporter is deliberately not started.
        ss << ",\"resources\":{\"internal_heap\":{\"free_bytes\":" << ESP.getFreeHeap()
           << ",\"minimum_free_bytes_sdk\":" << ESP.getMinFreeHeap()
           << ",\"largest_free_block_bytes\":" << ESP.getMaxAllocHeap()
           << "},\"psram\":{\"free_bytes\":" << ESP.getFreePsram()
           << ",\"minimum_free_bytes_sdk\":" << ESP.getMinFreePsram()
           << ",\"largest_free_block_bytes\":" << ESP.getMaxAllocPsram() << "},\"history\":{\"bytes\":"
           << (history_.available() ? control::HeatingHistory::bytes() : 0) << ",\"available\":" << (history_.available() ? "true" : "false") << "}},";
#endif
        if(modernMode()) ss << "\"activeProgram\":null,\"boiler\":null,";
        else {
            {
                std::lock_guard<std::mutex> lock(roomsAccessMutex_);
                ss << "\"activeProgram\": \"" << currentProgram_ << "\",";
            }
            ss << "\"boiler\":";
            boiler_.getStatus(ss);ss << ',';
        }
		ss << "\"ems\": "; ems_.getStatus(ss); ss << ",";
        if(modernMode()) {ss << "\"control\":";mqtt_.getControlUiStatus(ss);ss << ',';}
		ss << "\"openweather\": " << openWeather_.getStatus() << ",";

		struct tm timeinfo{};
		if(getLocalTime(&timeinfo,0)) {

		ss << "\"time\": \"" << std::setfill('0') << std::setw(2) << timeinfo.tm_hour << ":"
			<< std::setfill('0') << std::setw(2) << timeinfo.tm_min << ":"
			<< std::setfill('0') << std::setw(2) << timeinfo.tm_sec << "\",";
		ss << "\"date\": \"" << std::setfill('0') << std::setw(4) << timeinfo.tm_year + 1900 << "-"
			<< std::setfill('0') << std::setw(2) << timeinfo.tm_mon + 1 << "-"
			<< std::setfill('0') << std::setw(2) << timeinfo.tm_mday << "\",";

		ss << "\"weekDay\": " << timeinfo.tm_wday << ",";
		} else ss << "\"time\":null,\"date\":null,\"weekDay\":null,";
		ss << "\"uptime\": " << millis()/1000;


		ss << "}";
	}


	std::string getFullStatus() const {
		std::ostringstream ss;
		getFullStatus(ss);
		return ss.str();
	}

	std::string getRoomsStatus() const {
		std::ostringstream ss;
		getRoomsStatus(ss);
		return ss.str();
	}

	size_t getRoomsStatus(std::ostream &ss) const {
		ss << "[";
		size_t r = 0;
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		bool boilerStarted = boiler_.isBoilerStarted();

		for (auto const &room : rooms_) {
			bool isBeingHeated = false;
			if (boilerStarted && room->isEnabled()) {
				for (auto const &valve : room->getValves()) {
					auto valveIt = valveLabelMap_.find(valve);
					if (valveIt != valveLabelMap_.end() && boiler_.isValveOpen(valveIt->second)) {
						isBeingHeated = true;
						break;
					}
				}
			}

			room->getStatus(ss, isBeingHeated);
			r++;
			if (r != rooms_.size()) {
				ss << ",";
			}
		}
		ss << "]";

		return rooms_.size();
	}

	size_t getRoomsCount() {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		return rooms_.size();
	}

	std::vector<std::string> getRoomIds() const {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		std::vector<std::string> ids;
		ids.reserve(rooms_.size());
		for (auto const &room : rooms_) ids.emplace_back(room->getId());
		return ids;
	}

	std::string getActiveProgram() const {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		return currentProgram_;
	}

	bool setRoomTemporaryTemperature(std::string const &name, int16_t temperature, uint32_t validSeconds) {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);

		for (auto &room : rooms_) {
			if (room->getName() == name) {
				room->createTemporaryOverride(temperature, validSeconds);
				return true;
			}
		}
		DBGLOGFD(log_, logFeature_, "setRoomTemporaryTemperature. No room '%s' found\n", name.c_str());

		return false;
	}

	void startManualGpioTest(bool boilerState, std::vector<bool> const &valveStates, uint32_t durationSeconds) { boiler_.startManualTest(boilerState, valveStates, durationSeconds); }

	void stopManualGpioTest() { boiler_.stopManualTest(); }

	void getDevicesFound(std::ostream &ss) {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);

		DBGLOGFD(log_, logFeature_, "getDevicesFound %zu\n", devicesFound_.size());

		ss << "[";
		for (auto it = devicesFound_.begin(); it != devicesFound_.end(); ++it) {
			if (it != devicesFound_.begin()) {
				ss << ", ";
			}
		    #define GETHEX_STR(val) std::hex  << std::setfill('0') << std::setw(2) << (int)val
			ss << "\"" << GETHEX_STR(it->at(0)) << ':' << GETHEX_STR(it->at(1)) << ':' << GETHEX_STR(it->at(2)) << ':' << GETHEX_STR(it->at(3)) << ':' << GETHEX_STR(it->at(4)) << ':' << GETHEX_STR(it->at(5)) << "\"";
		}
		ss << "]";
	}

	void stopBluetoothScan() {
		bluetoothScan_ = false;
	}

	void stopBluetoothAndDeinitBLE() {
		bluetoothScan_ = false;
#ifdef OPENTHERMOSTAT_E32V2
        stopManagedBle();
#endif
		// NimBLE deinit stops its host/scan through the SDK. Do not wait for
		// onScanEnd first: a missing callback could prevent AP recovery forever.
		// The reader closes report admission BEFORE asking the SDK to stop.
		tempReader_.shutDownBLE();
	}

	void reloadConfiguration() {
		DBGLOGFD(log_, logFeature_, "reloadConfiguration%s\n", "");
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);
		currentProgram_ = config::getCurrentProgram();
		rooms_ = buildRoomsFromConfig();
	}

private:
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};

	void pushTemperatureData(BleAddress_t address, std::optional<int16_t> temperature, std::optional<int16_t> humidity, std::optional<int8_t> battery) {
		std::lock_guard<std::mutex> lock(roomsAccessMutex_);

		devicesFound_.remember(address); // Discovery cap never skips configured-room updates.

		auto room = std::find_if(std::begin(rooms_), std::end(rooms_), [&adr = address](auto const &room) { return (adr == room->getSensorAddress()); });
		if (room == std::end(rooms_)) {
#ifndef OPENTHERMOSTAT_E32V2
			DBGLOGFD(log_, logFeature_, "No room for address '" PRiBleAddress "'\n", PRaBleAddress(address));
#endif
			return;
		}

#ifndef OPENTHERMOSTAT_E32V2
		// Runs in the Bluetooth host task: on the E32 no logging here (the logger
		// takes a mutex and formats; every nearby advert would pass through it).
		DBGLOGFD(log_, logFeature_, "push '%s', " PRiBleAddress " temp: %d battery: %d%% BTC MinPeekStack: %d\n", (*room)->getName().c_str(), PRaBleAddress(address), temperature.value_or(std::numeric_limits<decltype(temperature)::value_type>::min()), battery.value_or(std::numeric_limits<decltype(battery)::value_type>::min()), uxTaskGetStackHighWaterMark(nullptr));
#endif

		if (temperature.has_value()) {
			(*room)->storeTemperature(temperature.value());
		}

		if (humidity.has_value()) {
			(*room)->storeHumidity(humidity.value());
		}

		if (battery.has_value()) {
			(*room)->storeBattery(battery.value());
		}

	}

	std::optional<int16_t> getOutdoorTemperature() {
		// Only the explicitly configured source may supply the curve. Substitution
		// and source-specific degraded fallback need an accepted profile, not a guess.
		if (boilerConfig_.boiler.outdoorSensor == config::BoilerConfig::outdoorSensor_t::openweather) {
			return openWeather_.getTemperature();
		} else if (boilerConfig_.boiler.outdoorSensor == config::BoilerConfig::outdoorSensor_t::ems) {
			return ems_.getOutdoorTemperature();
		}
		return {};
	}

	std::vector<std::shared_ptr<heating::Room>> buildRoomsFromConfig() {
		auto configs = config::getRoomsConfig(currentProgram_);
		std::vector<std::shared_ptr<heating::Room>> rooms;
		for (const auto config : configs) {
			rooms.emplace_back(std::make_shared<heating::Room>(log_, std::move(config)));
		}
		return rooms;
	}

	std::atomic_bool bluetoothScan_;
	bool bleDiscoveryRequested_ = false; // loop task only: REST and loop() share it
	uint32_t bleDiscoveryRequestedAt_ = 0;
#ifdef OPENTHERMOSTAT_E32V2
    static uint64_t bleReceiptClock() { return static_cast<uint64_t>(esp_timer_get_time()) / 1000; }
    control::MbedTlsBleCcm bleCrypto_;
    control::ManagedBleObserver<control::MbedTlsBleCcm> managedBle_{bleCrypto_, bleReceiptClock};
    std::atomic<uint32_t> bleAdvertHeardS_{0};
    control::BleDeviceDiscovery bleDiscovery_;
    static_assert(sizeof(decltype(managedBle_)) <= 4096, "BLE observer resident budget changed");
    control::RoomEngine roomEngine_;
    control::RoomOverrides overrides_; // beta.19: temporary overrides, window pauses, away (targets only)
    control::ShadowComparison shadowComparison_; // E32 decision vs the tado's 0x1A, per day
    control::ActiveHeatGuard activeGuard_;
    update::BoilerReleaseHold restartHold_;
    // Per room how fast it warms per flow (report only; ~1.15 KB heap per room, PSRAM extmem).
    control::FlowLearner flowLearner_;
    control::FlowPolicy flowPolicy_; // beta.19 options: weather curve, learned flow, optimum start (default: advice)
    control::HeatingHistory history_; // 24 h of 5-minute averages, ~12.5 KB PSRAM, RAM only
    control::HeatingInputRoute haInput_;  // ha/heating_input: rooms, gas, price, outdoor, boiler power
    uint32_t activePosted_ = 0; uint64_t activePostedAt_ = 0; // the last command handed to the EMS route
    std::optional<uint8_t> limitC_; std::optional<uint64_t> limitAtMs_; uint32_t limitReads_ = 0; // last step's 0x16 view
    // The owner's confirmation over restarts, bound to this firmware build.
    static std::string firmwareIdentity() {
        const esp_app_desc_t* app = esp_ota_get_app_description();
        if (!app) return {};
        std::string id(app->version, strnlen(app->version, sizeof(app->version)));
        id += '/';
        for (size_t i = 0; i < 8; ++i) { id += "0123456789abcdef"[app->app_elf_sha256[i] >> 4]; id += "0123456789abcdef"[app->app_elf_sha256[i] & 15]; }
        return id;
    }
    HandoverNvs handoverStore_;
    control::HandoverConfirmation<HandoverNvs> handover_{handoverStore_, firmwareIdentity()};
    void loadHeatingPlan() {
        const auto raw = readHeatingPlan();
        const auto root = control::parseNestedJson(raw);
        control::RoomPlan plan;
        if (root && !control::RoomPlan::parse(root.get(), plan)) { roomEngine_.setPlan(plan); flowLearner_.setPlan(plan); }
        else DBGLOGFI(log_, logFeature_, "Room plan unreadable; heating control has no rooms\n");
    }
    // ha/heating_input: room states and the learner's gas, price, outdoor and
    // boiler power (control/HeatingInput.h). Anything else is ignored.
    void heatingInput(std::string_view payload) {
        if (overrides_.input(payload, roomEngine_.plan(), bleReceiptClock())) return; // window/door contacts, presence
        haInput_.accept(payload, bleReceiptClock(), roomEngine_, flowLearner_);
    }
    // The learner's outdoor: the boiler's (0x19/0xD1) while fresh, else HA's for 15 min.
    control::HeatingInputRoute::Outdoor learnerOutdoor(uint64_t now) const { return haInput_.outdoor(ems_.getOutdoorTemperature(), now); }
    // Clock, fresh room readings (filled into `temperatures`) and outdoor for the learned status.
    control::LearnedContext learnedContext(uint64_t now, std::array<std::optional<int16_t>, control::RoomPlan::maxRooms>& temperatures) const {
        const auto& plan = roomEngine_.plan();
        for (size_t i = 0; i < plan.rooms.size() && i < temperatures.size(); ++i) temperatures[i] = roomEngine_.freshTemperature(i, now);
        const auto outdoor = learnerOutdoor(now);
        control::LearnedContext context;
        if (networkTimeTrusted) context.utc = static_cast<int64_t>(std::time(nullptr));
        context.temperatures = temperatures.data();
        context.outdoorCentiC = outdoor.centiC; context.outdoorSource = outdoor.source; context.now = now;
        return context;
    }
    // Every 10 s: feed the Bluetooth sources, then compute the (shadow) request.
    void stepHeating() {
        const auto now = bleReceiptClock();
        for (const auto& room : roomEngine_.plan().rooms)
            for (const auto& source : room.sources) {
                control::ManagedBleAddress address{};
                if (source.type != control::RoomPlan::SourceType::ble || !control::parseBleHex(source.id, address)) continue;
                const auto snapshot = managedBle_.snapshot(address);
                if (snapshot.temperature && snapshot.temperatureAgeMs && *snapshot.temperatureAgeMs <= now)
                    roomEngine_.bleReading(source.id, snapshot.temperature, now - *snapshot.temperatureAgeMs);
            }
        std::optional<uint32_t> unixNow;
        if (networkTimeTrusted) unixNow = static_cast<uint32_t>(std::time(nullptr));
        // Overrides, window pauses and away change room targets only; the away end
        // starts warming up by the learner's (or the default) lead.
        const auto* adjust = overrides_.step(roomEngine_.plan(), now, unixNow, [&](size_t i, uint32_t until, int16_t away, int16_t target) {
            return control::RoomOverrides::returnLeadS(flowLearner_, i, until, away, target, roomEngine_.freshTemperature(i, now),
                                                      *unixNow, learnerOutdoor(now).centiC);
        });
        // The boiler's own limit (0x16) caps the rule too, so the calculated request
        // never exceeds what the boiler accepts; unknown: the plan's ceiling.
        const auto ems = ems_.activeHeatView();
        roomEngine_.setBoilerLimit(ems.limitC);
        const auto rule = roomEngine_.step(now, unixNow, adjust);
        const auto tadoFlowC = ems_.thermostatRequestedFlowC();
        const auto request = applyFlowPolicy(now, rule, ems); // the rule itself while the options are off
        shadowComparison_.sample(now, unixNow, request, tadoFlowC);
        stepFlowLearner(now, ems, tadoFlowC);
        stepActiveHeat(now, request, ems);
        sampleHistory(now, request, ems, tadoFlowC);
    }
    // Charts only: fresh readings, effective targets, the boiler and both requests.
    void sampleHistory(uint64_t now, const control::FlowDemand::Request& request, const ems::EmsController::ActiveHeatView& ems, std::optional<uint8_t> tadoFlowC) {
        if (!history_.available()) return;
        const auto& plan = roomEngine_.plan();
        const size_t count = std::min(plan.rooms.size(), control::HeatingHistory::rooms);
        history_.syncRooms(count, [&](size_t i) { return plan.rooms[i].id.c_str(); });
        control::HeatingHistory::Sample s;
        for (size_t i = 0; i < count; ++i) { s.temperatureCentiC[i] = roomEngine_.freshTemperature(i, now); s.targetCentiC[i] = roomEngine_.result(i).setpoint; }
        s.flowCentiC = ems.flowCentiC; s.returnCentiC = ems.returnCentiC; s.burnerOn = ems.burnerOn;
        s.requestFlowC = request.heat ? request.flowC : uint8_t(0); s.thermostatFlowC = tadoFlowC;
        history_.sample(now, s);
    }
    // Report only: the boiler view and per room the fresh leading reading.
    void stepFlowLearner(uint64_t now, const ems::EmsController::ActiveHeatView& ems, std::optional<uint8_t> tadoFlowC) {
        const auto& plan = roomEngine_.plan();
        control::FlowLearner::Boiler boiler{ems.flowCentiC, ems.burnerOn, ems.hotWater, tadoFlowC,
            learnerOutdoor(now).centiC, ems.modulationPct, ems.returnCentiC};
        std::array<control::FlowLearner::RoomInput, control::RoomPlan::maxRooms> rooms{};
        const size_t count = std::min(plan.rooms.size(), rooms.size());
        for (size_t i = 0; i < count; ++i) {
            const auto fresh = roomEngine_.fresh(i, now);
            rooms[i] = {fresh.temperature, roomEngine_.result(i).setpoint, fresh.source};
        }
        flowLearner_.sample(now, boiler, rooms.data(), count);
    }
    void loadFlowSettings() {
        const auto settings = FlowSettingsNvs::read();
        flowPolicy_.setSettings(settings); flowLearner_.setApplied(settings.applyLearned);
    }
    // The options between the room engine's rule and the guard (control/FlowPolicy.h).
    control::FlowDemand::Request applyFlowPolicy(uint64_t now, const control::FlowDemand::Request& rule, const ems::EmsController::ActiveHeatView& ems) {
        const auto& plan = roomEngine_.plan();
        std::array<control::RoomDemand::Result, control::RoomPlan::maxRooms> rooms{};
        for (size_t i = 0; i < plan.rooms.size() && i < rooms.size(); ++i) {
            rooms[i] = roomEngine_.result(i);
            // Away or an open window: no optimum start towards the program's next rise.
            if (overrides_.holdsProgram(i)) rooms[i].status = control::RoomDemand::Status::inactive;
        }
        control::FlowPolicy::Inputs in;
        in.now = now; in.rule = rule; in.plan = &plan; in.rooms = rooms.data();
        if (networkTimeTrusted) in.utc = static_cast<int64_t>(std::time(nullptr));
        in.outdoorCentiC = learnerOutdoor(now).centiC; in.boilerLimitC = ems.limitC;
        in.flowCentiC = ems.flowCentiC; in.burnerOn = ems.burnerOn; in.hotWater = ems.hotWater;
        return flowPolicy_.apply(in, flowLearner_);
    }
    // Active mode: the guard decides; the EMS route sends at the boiler's next
    // poll of 0x0B and reports {seq, ok}, read back at the following step.
    void stepActiveHeat(uint64_t now, const control::FlowDemand::Request& request, const ems::EmsController::ActiveHeatView& ems) {
        if (ems.last && ems.last->seq == activePosted_) activeGuard_.transmitted(activePostedAt_, ems.last->ok);
        const auto& plan = roomEngine_.plan();
        control::ActiveHeatGuard::Inputs in;
        in.mode = board::emsActiveHeatAllowed ? plan.mode : control::RoomPlan::Mode::shadow;
        in.request = request;
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            in.rooms.add(roomEngine_.result(i));
            in.rooms.measured(roomEngine_.freshTemperature(i, now));
        }
        if (ems.foreign) in.foreign = control::ActiveHeatGuard::Foreign{ems.foreign->address, ems.foreign->receivedAtMs};
        in.uptimeMs = now; in.routeReady = ems.routeReady; in.boilerLimitC = ems.limitC;
        in.boiler = {ems.burnerOn, ems.flowCentiC}; in.boilerHeardAtMs = ems.boilerHeardAtMs;
        activeGuard_.setFlowLimits(plan.minimumFlowC, plan.maximumFlowC);
        const auto c = activeGuard_.step(now, in);
        handover_.sync(activeGuard_.confirmed()); // a foreign 0x1A or shadow mode erases the stored one
        activePosted_ = ems_.activeHeatPost(c.send ? std::optional<uint8_t>(c.flowC) : std::nullopt,
            in.mode == control::RoomPlan::Mode::active && activeGuard_.confirmed(), activeGuard_.claimsBoiler());
        activePostedAt_ = now;
        limitC_ = ems.limitC; limitAtMs_ = ems.limitAtMs; limitReads_ = ems.limitReads;
    }
#endif
	BeaconTemperatureReader tempReader_{log_, [this](BleAddress_t address, std::optional<int16_t> temperature, std::optional<int16_t> humidity, std::optional<int8_t> battery) { pushTemperatureData(std::move(address), temperature, humidity, battery); }};
	OpenWeather openWeather_;
	ems::EmsController ems_{log_};
	config::BoilerConfig boilerConfig_{config::getBoilerConfig()};

	PcfDeviceMap pcfDevices_{buildPcfDeviceMap()};
	BoilerController boiler_{log_, boilerConfig_, [this]() { return getOutdoorTemperature(); }, [&ems = ems_](bool enabled, uint8_t flowTempSet) {
			ems.changeBoilerState(enabled, flowTempSet); }, [&ems = ems_](uint8_t heatingTemperature) {
			ems.setHeatingTemperature(heatingTemperature); }, createBoilerPort(log_, logFeature_, pcfDevices_), createValvePorts(log_, logFeature_, pcfDevices_), createValveLabels()};
	std::string currentProgram_;
	std::vector<std::shared_ptr<heating::Room>> rooms_;
	std::unordered_map<std::string, uint8_t> valveLabelMap_{buildValveLabelMap()};
	control::BleDeviceDiscovery devicesFound_;
	mutable std::mutex roomsAccessMutex_;

	// Informational observation epoch only, never an authentication token / NVS value.
	static std::string observationBootId() {
		unsigned char bytes[16]; esp_fill_random(bytes,sizeof(bytes));
		static constexpr char hex[]="0123456789abcdef";
		std::string id(32,'0');
		for(size_t i=0;i<16;++i) { id[2*i]=hex[bytes[i]>>4];id[2*i+1]=hex[bytes[i]&15]; }
		return id;
	}
	ems::EmsMetrics emsMetrics_{[this](uint16_t telegramId, std::function<void(heating::ems::EmsTelegram const &)> processor) { ems_.registerTelegramProcessor(telegramId, processor); },
		[] { return ib::getTimeMillis(); }, observationBootId()};

	MQTT mqtt_{
		log_,
		[this]() { return getRoomIds(); },
		[this](std::ostream &ss) { getRoomsStatus(ss);},
		[this]() { return getActiveProgram(); },
		[this]() { return boiler_.isBoilerStarted(); },
		[this](std::ostream &ss) { emsMetrics_.getMetrics(ss);},
		[this](std::ostream &ss) { getEMSStatus(ss);},
		[this](std::string const &name, int16_t temperature, uint32_t seconds) {
			return setRoomTemporaryTemperature(name, temperature, seconds);
		},
		[this](std::ostream &ss) { emsMetrics_.getRoomContext(ss); },
#ifdef OPENTHERMOSTAT_E32V2
        [this](std::ostream& ss,size_t group) { ems_.getBoilerFieldGroup(ss,group); }
#else
        {}
#endif
		};
};



}
