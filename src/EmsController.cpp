#include "Logging.h"
#include "EmsController.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "diagnostics/LogRuntime.h"
#include "diagnostics/EmsLogCapture.h"
#endif

#include "EMS/UBADeviceVersion.h"
#include "EMS/UBAFactory.h"
#include "EMS/UBAInternalWeatherCompensatedMode.h"
#include "EMS/UBAMonitorFastPlus.h"
#include "EMS/UBAMonitorSlowPlus.h"
#include "EMS/UBAMonitorSlowPlus2.h"
#include "EMS/UBAMonitorWWPlus.h"
#include "EMS/UBAOutdoorTemp.h"
#include "EMS/UBAParametersPlus.h"
#include "EMS/UBAParametersWWPlus.h"
#include "EMS/UBAProtocolVersion.h"

#include <TimeHelpers.h>
#include <esp_timer.h>

namespace heating::ems {

EmsController::EmsController(std::shared_ptr<ib::logger::LoggerInterface> log) : log_(std::move(log)) {
	if (log_) {
		logFeature_ = log_->addFeature("EmsControl");
		verboseFeature_ = log_->addFeature("EmsVerbose");
		fatalFeature_ = log_->addFeature("Fatal");
	}
	DBGLOGFD(log_, logFeature_, "emsEnabled: %d emsForwarderEnabled: %d\n", emsConfig_.emsEnabled, emsConfig_.emsForwarderEnabled);

	if (!emsConfig_.emsEnabled) {
		return;
	}
	config::EmsPins emsPins{config::getEmsPins()};

	captureForeignTelegrams_.store(log_ && log_->isFeatureEnabled(verboseFeature()), std::memory_order_relaxed);
	uart_.start(emsPins.rx, emsPins.tx);

	if (emsConfig_.emsForwarderEnabled) {
		std::optional<config::EmsForwarderPins> emsForwarderPins{config::getEmsForwarderPins()};
		if (emsForwarderPins.has_value()) {
			uart_.startForwarder(emsForwarderPins.value().rx, emsForwarderPins.value().tx);
		}
	}

	#define UPDATE_IF_SET(field, func) { auto _uis__val = telegram->func(); if (_uis__val.has_value()) { field = _uis__val.value();  } }

	registerTelegramProcessor(UBAMonitorFastPlus::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		UBAMonitorFastPlus const *telegram = reinterpret_cast<UBAMonitorFastPlus const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		UPDATE_IF_SET(s.selectedFlowTemperature, getSelectedFlowTemperature)
		UPDATE_IF_SET(s.currentFlowTemperature, getCurrentFlowTemperature)
		UPDATE_IF_SET(s.burningGas, getBurningGas)
		UPDATE_IF_SET(s.pumpEnabled, getPumpEnabled)
		UPDATE_IF_SET(s.pressure, getPressure)
		UPDATE_IF_SET(s.currentBurnerPower, getCurrentBurnerPower)
		UPDATE_IF_SET(s.heatingActive, getHeatingActive)
		UPDATE_IF_SET(s.warmWaterActive, getWarmWaterActive)
		UPDATE_IF_SET(s.fillingSiphon, getSiphonFilling)
		UPDATE_IF_SET(s.serviceCode, getServiceCode);
		UPDATE_IF_SET(s.displayCode, getDisplayCode);
	});

	registerTelegramProcessor(UBAMonitorSlowPlus::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		UBAMonitorSlowPlus const *telegram = reinterpret_cast<UBAMonitorSlowPlus const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		UPDATE_IF_SET(s.fanEnabled, getFanEnabled)
	});

	registerTelegramProcessor(UBAMonitorSlowPlus2::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAMonitorSlowPlus2 const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		UPDATE_IF_SET(s.pumpVenting, getPumpVenting)
	});

	registerTelegramProcessor(UBAParametersWWPlus::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAParametersWWPlus const *>(&t);
		telegram->logData(*log_, logFeature_);

		auto enabled = telegram->getWarmWaterEnabled();
		std::lock_guard<std::mutex> lock(s.mutex);
		if (enabled.has_value()) {
			s.warmWaterEnabled = enabled.value();
		}
		UPDATE_IF_SET(s.selectedWarmWaterTemperature, getSelectedWarmWaterTemperature)
	});

	registerTelegramProcessor(UBAParametersPlus::predefinedTypeId, [this, &s = boilerState_, &p = boilerParams_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAParametersPlus const *>(&t);
		telegram->logData(*log_, logFeature_);

		{
		std::lock_guard<std::mutex> lock(s.mutex);
		auto enabled = telegram->getHeatingEnabled();
		if (enabled.has_value()) {
			s.heatingEnabled = enabled.value();
		}
		}

		std::lock_guard<std::mutex> lock(p.mutex);
		UPDATE_IF_SET(p.maximumHeatingTemperature, getMaximumHeatingTemperature);
		UPDATE_IF_SET(p.heatingTemperature, getHeatingTemperature);
	});

	registerTelegramProcessor(UBAOutdoorTemp::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAOutdoorTemp const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		s.outdoorTemperature = telegram->getOutdoorTemperature();
		if (s.outdoorTemperature.has_value()) {
			s.outdoorTemperature.value() *= 10;
		}
	});

	registerTelegramProcessor(UBAMonitorWWPlus::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAMonitorWWPlus const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		UPDATE_IF_SET(s.warmWaterFlow, getFlow)
		UPDATE_IF_SET(s.currentWarmWaterTemperature, getCurrentTemperature)
	});

	registerTelegramProcessor(UBAProtocolVersion::predefinedTypeId, [this, &s = boilerState_](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAProtocolVersion const *>(&t);
		telegram->logData(*log_, logFeature_);
		std::lock_guard<std::mutex> lock(s.mutex);
		UPDATE_IF_SET(s.protocolVersion, getProtocolVersion)
	});


	registerTelegramProcessor(UBAInternalWeatherCompensatedMode::predefinedTypeId, [this](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAInternalWeatherCompensatedMode const *>(&t);
		telegram->logData(*log_, logFeature_);
	});

	registerTelegramProcessor(UBADeviceVersion::predefinedTypeId, [this](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBADeviceVersion const *>(&t);
		telegram->logData(*log_, logFeature_);
	});

	registerTelegramProcessor(UBAFactory::predefinedTypeId, [this](EmsTelegram const &t) {
		auto telegram = reinterpret_cast<UBAFactory const *>(&t);
		telegram->logData(*log_, logFeature_);
	});

	requestStartupData();
}

void EmsController::requestStartupData() {
	enqueueTelegramToSend(UBAParametersWWPlus::getRequest(deviceId_, boilerId_));
	enqueueTelegramToSend(UBAParametersPlus::getRequest(deviceId_, boilerId_));
	enqueueTelegramToSend(UBADeviceVersion::getRequest(deviceId_, boilerId_));
	enqueueTelegramToSend(UBAProtocolVersion::getRequest(deviceId_, boilerId_));
	enqueueTelegramToSend(UBAFactory::getRequest(deviceId_, boilerId_));
	enqueueTelegramToSend(EmsTelegram{EmsTelegram::operation_t::READ, deviceId_, boilerId_, 0, 0x04, {EmsTelegram::maxEmsDataLength}}); //ubafactory
	enqueueTelegramToSend(EmsTelegram(EmsTelegram::operation_t::WRITE, deviceId_, 0x08, 0, 0x00E7, {0x00, 0x02, 0x00}), true); // enable external EMS controller
}

void EmsController::requestPeriodicData() {
	if (!emsConfig_.emsEnabled) {
		return;
	}

	auto now = millis();
	if (lastBoilerParametersReadRequestMillis_ == 0 || ib::millisDurationPassed(now, lastBoilerParametersReadRequestMillis_, 1000ul * boilerParametersReadRequestIntervalSecs)) {
		DBGLOGFD(log_, logFeature_, "requestPeriodicData - outdoor temp and external EMS\n");
		enqueueTelegramToSend(EmsTelegram(EmsTelegram::operation_t::WRITE, deviceId_, 0x08, 0, 0x00E7, {0x00, 0x02, 0x00}), true); // enable external EMS controller
		lastBoilerParametersReadRequestMillis_ = now;
	}

	if (lastBoilerDetailsReadRequestMillis_ == 0 || ib::millisDurationPassed(now, lastBoilerDetailsReadRequestMillis_, 1000ul * boilerDetailsReadRequestIntervalSecs)) {
		DBGLOGFD(log_, logFeature_, "requestPeriodicData - heating and ww params\n");
		enqueueTelegramToSend(UBAParametersWWPlus::getRequest(deviceId_, boilerId_));
		enqueueTelegramToSend(UBAParametersPlus::getRequest(deviceId_, boilerId_));
		enqueueTelegramToSend(UBAOutdoorTemp::getRequest(deviceId_, boilerId_));
		enqueueTelegramToSend(UBAFactory::getRequest(deviceId_, boilerId_));
		// enqueueTelegramToSend(UBAInternalWeatherCompensatedMode::getRequest(deviceId_, boilerId_));
		lastBoilerDetailsReadRequestMillis_ = now;
	}
}

void EmsController::reset() {
#ifdef OPENTHERMOSTAT_E32V2
	boilerTestTransportFault_.store(true, std::memory_order_release);
#endif
	size_t dropped;
	portENTER_CRITICAL(&txMux_);
	dropped = txSize_;
	txHead_ = 0;
	txSize_ = 0;
	portEXIT_CRITICAL(&txMux_);
	// UART recovery is performed by its owner, never concurrently with RX/TX.
	uart_.requestReset();
	DBGLOGFD(log_, fatalFeature(), "EmsController::reset %zu TX dropped\n", dropped);
	requestStartupData();
}

void EmsController::enqueueTelegramToSend(EmsTelegram telegram, bool front) {
	if constexpr (!board::emsTransmitAllowed) return; // no pending commands in RX-only mode
	if (telegram.getOperationType() == EmsTelegram::WRITE) {
		std::lock_guard<std::mutex> lock(telemetryMutex_);
		// Never send legacy EMS+ controls/startup writes onto unknown/Classic buses.
		if (!monitor_.capabilities().allowsLegacyPlusWrites()) return;
	}
	// Encode and allocate before taking the TX lock; poll only copies ready bytes.
	auto encoded = telegram.encodeToRawDataWithCRC();
	if (encoded.empty() || encoded.size() > EmsRawFrame::capacity) {
		DBGLOGFD(log_, fatalFeature(), "Invalid EMS TX size: %zu\n", encoded.size());
		return;
	}
	EmsRawFrame frame;
	frame.length = static_cast<uint8_t>(encoded.size());
	std::copy(encoded.begin(), encoded.end(), frame.data.begin());
	bool full;
	{
#ifdef OPENTHERMOSTAT_E32V2
	// Recheck AFTER encoding and hold through queue insertion, so a preparation
	// racing an older producer cannot leave a command for after test completion.
	std::lock_guard<std::mutex> testOwner(telemetryMutex_);
	if (boilerTest_.active() || (telegram.getOperationType() == EmsTelegram::WRITE
		&& !monitor_.capabilities().allowsLegacyPlusWrites())) return;
#endif
	portENTER_CRITICAL(&txMux_);
	full = txSize_ == telegramsToSend_.size();
	if (!full) {
		// Preserve the existing ordering: front=true appends; default prepends.
		if (!front) {
			txHead_ = (txHead_ + telegramsToSend_.size() - 1) % telegramsToSend_.size();
		}
		telegramsToSend_[(txHead_ + (front ? txSize_ : 0)) % telegramsToSend_.size()] = frame;
		++txSize_;
	}
	portEXIT_CRITICAL(&txMux_);
	}
	if (full) {
		resetRequested_.store(true, std::memory_order_relaxed);
		DBGLOGFD(log_, fatalFeature(), "EMS TX queue full\n");
	} else if (log_) {
		telegram.logDebug(*log_, verboseFeature());
	}
}

#ifdef OPENTHERMOSTAT_E32V2
bool EmsController::processBoilerTestPoll() {
	if constexpr (!board::emsTransmitAllowed) return false;
	// UART must never wait for a web/status owner. A busy owner suppresses this
	// poll, including legacy queue/pong, rather than dispatching an old command.
	std::unique_lock<std::mutex> lock(telemetryMutex_, std::try_to_lock);
	if (!lock.owns_lock()) return true;
	if (boilerTestTransportFault_.exchange(false, std::memory_order_acq_rel))
		boilerTest_.transportFault(static_cast<uint64_t>(esp_timer_get_time() / 1000));
	if (boilerTest_.active()) {
		// Discard legacy commands from BEFORE ownership as well as excluding new
		// producers. They must not escape when reported completion releases us.
		portENTER_CRITICAL(&txMux_);
		txHead_ = 0;
		txSize_ = 0;
		portEXIT_CRITICAL(&txMux_);
	}
	const auto result = BoilerTestPollDriver::poll(boilerTest_, monitor_,
		[] { return static_cast<uint64_t>(esp_timer_get_time() / 1000); },
		[this] {
			auto gates = boilerTestGates();
			if (boilerTestTransportFault_.load(std::memory_order_acquire)
				|| resetRequested_.load(std::memory_order_relaxed)) gates.transmitterReviewed = false;
			return gates;
		}, boilerTestEncoder_,
		[this](const EmsRawFrame& frame) {
			const bool sent = uart_.writeToEms(frame.data.data(), frame.length);
			if (sent) {
				txNotConfirmed_.fetch_add(1, std::memory_order_relaxed);
				txFrames_.fetch_add(1, std::memory_order_relaxed);
			}
			return sent;
		});
	return result != BoilerTestPollDriver::Result::unowned;
}
#endif

bool EmsController::processPoll(uint8_t deviceId) {
	if (deviceId != deviceId_) {
		return false;
	}
	const auto started = esp_timer_get_time();
	polls_.fetch_add(1, std::memory_order_relaxed);
	if (txNotConfirmed_.load(std::memory_order_relaxed) > maxTxNotConfirmed) {
		resetRequested_.store(true, std::memory_order_relaxed);
#ifdef OPENTHERMOSTAT_E32V2
		boilerTestTransportFault_.store(true, std::memory_order_release);
#endif
	}
#ifdef OPENTHERMOSTAT_E32V2
	const bool testHandled = processBoilerTestPoll();
#else
	constexpr bool testHandled = false;
#endif
	if (!testHandled) {
		EmsRawFrame frame;
		portENTER_CRITICAL(&txMux_);
		if (txSize_ != 0) {
			frame = telegramsToSend_[txHead_];
			txHead_ = (txHead_ + 1) % telegramsToSend_.size();
			--txSize_;
		}
		portEXIT_CRITICAL(&txMux_);
		if (frame.length == 0) {
			pong();
		} else if (uart_.writeToEms(frame.data.data(), frame.length)) {
			txNotConfirmed_.fetch_add(1, std::memory_order_relaxed);
			txFrames_.fetch_add(1, std::memory_order_relaxed);
		}
	}
	// Includes the intentionally paced UART write, from poll recognition to return.
	const auto elapsed = static_cast<uint32_t>(esp_timer_get_time() - started);
	auto maximum = maxPollServiceUs_.load(std::memory_order_relaxed);
	while (maximum < elapsed && !maxPollServiceUs_.compare_exchange_weak(maximum, elapsed, std::memory_order_relaxed)) {}
	return true;
}

void EmsController::processTelegram(uint8_t *data, uint8_t length) {
#ifdef OPENTHERMOSTAT_E32V2
	const auto errors = uart_.rxErrors.load(std::memory_order_relaxed);
	if (boilerTestUartErrorsSeen_ != errors) {
		boilerTestUartErrorsSeen_ = errors;
		boilerTestTransportFault_.store(true, std::memory_order_release);
	}
#endif
	// Only the UART task updates confirmation accounting, including recovery.
	const auto resets = uart_.resets.load(std::memory_order_relaxed);
	if (uartResetsSeen_ != resets) {
#ifdef OPENTHERMOSTAT_E32V2
		boilerTestTransportFault_.store(true, std::memory_order_release);
#endif
		uartResetsSeen_ = resets;
		txNotConfirmed_.store(0, std::memory_order_relaxed);
	}
	// UART context: answer polls immediately; copy ordinary frames without waiting.
	if (length == 2 && !(data[0] & 0x80)) {
		processPoll(data[0]);
		return;
	}
	if (length < 7) {
		return;
	}
	// Echo accounting must not depend on loop()/the diagnostic logger keeping up.
	if (data[1] != 0 && (data[1] & 0x7F) != deviceId_) {
		if ((data[0] & 0x7F) == deviceId_ && txNotConfirmed_.load(std::memory_order_relaxed) > 0) {
			txNotConfirmed_.fetch_sub(1, std::memory_order_relaxed);
		}
		// Cache the diagnostic setting in loop(); never call the logger here.
		const bool boilerData = (data[0] & 0x7F) == boilerId_ && !(data[1] & 0x80);
		if (!boilerData && !captureForeignTelegrams_.load(std::memory_order_relaxed)) {
			return;
		}
	}
	if (!telegramsToProcess_.push(data, length, static_cast<uint64_t>(esp_timer_get_time() / 1000))) {
		rxDropped_.fetch_add(1, std::memory_order_relaxed);
#ifdef OPENTHERMOSTAT_E32V2
		boilerTestTransportFault_.store(true, std::memory_order_release);
#endif
	}
}

void EmsController::decodeTelegram(uint8_t *data, uint8_t length, uint64_t receivedAtMs) {
    try {
        if (length == 0) return;
        const auto telegram = [this, data, length]() {
            try {
                return EmsTelegram::fromRawData(data, length - 1);
            } catch (const std::exception &) {
                invalidTelegrams_.fetch_add(1, std::memory_order_relaxed);
#ifdef OPENTHERMOSTAT_E32V2
                boilerTestTransportFault_.store(true, std::memory_order_release);
#endif
                throw;
            }
        }();
        {
            std::lock_guard<std::mutex> lock(telemetryMutex_);
            // A queued pre-command report must never become post-command stop
            // evidence simply because loop() decodes it after the command.
            deviceInventory_.observe(telegram, receivedAtMs);
            monitor_.receive(telegram, receivedAtMs);
            receiveOutdoorTemperature(outdoorSample_, telegram, receivedAtMs);
        }
#ifdef OPENTHERMOSTAT_E32V2
        diagnostics::captureEmsRx(diagnostics::runtime.log,data,length,
            telegram.getSenderId(),telegram.getDestinationId(),telegram.getTypeId(),
            telegram.getOffset(),receivedAtMs);
#endif
        // Passive monitor also sees boiler reports addressed to another master.
        // Legacy registered callbacks retain their original destination admission.
        if (data[1] != 0 && telegram.getDestinationId() != deviceId_) {
            if (log_ && log_->isFeatureEnabled(verboseFeature()))
                telegram.logDebug(*log_, verboseFeature_);
            return;
        }
        if (log_) telegram.logDebug(*log_, verboseFeature_);
        if (telegram.getOperationType() == EmsTelegram::READ) {
            processReadRequest(telegram);
        } else if (telegram.getSenderId() == boilerId_) {
            std::list<std::function<void(EmsTelegram const &)>> processors;
            {
                std::lock_guard<std::mutex> lock(telegramProcessorsMutex_);
                const auto found = telegramProcessors_.find(telegram.getTypeId());
                if (found != telegramProcessors_.end()) processors = found->second;
            }
            for (const auto &processor : processors) processor(telegram);
        }
    } catch (const std::exception &e) {
        DBGLOGFD(log_, fatalFeature(), "EmsController: rejected raw telegram: %s\n", e.what());
    }
}

void EmsController::refreshClassicStatus() {
    std::lock_guard<std::mutex> monitorLock(telemetryMutex_);
    if (monitor_.capabilities().profile() != BoilerProtocol::classic) return;
    const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
    const auto project = [&](auto &target, BoilerField field, int divisor = 1) {
        using Value = typename std::decay_t<decltype(target)>::value_type;
        if (const auto v = monitor_.value(field, now)) target = static_cast<Value>(*v / divisor);
        else target.reset();
    };
    {
        std::lock_guard<std::mutex> stateLock(boilerState_.mutex);
        auto &s = boilerState_;
        project(s.selectedFlowTemperature, BoilerField::selectedFlow, 100);
        project(s.currentFlowTemperature, BoilerField::flow, 10);
        project(s.outdoorTemperature, BoilerField::outdoor);
        project(s.currentBurnerPower, BoilerField::modulation);
        project(s.pressure, BoilerField::pressure);
        project(s.heatingActive, BoilerField::heatingActive);
        project(s.warmWaterActive, BoilerField::dhwActive);
        project(s.warmWaterEnabled, BoilerField::dhwEnabled);
        project(s.selectedWarmWaterTemperature, BoilerField::selectedDhw, 100);
        project(s.currentWarmWaterTemperature, BoilerField::dhwTemp, 10);
        project(s.warmWaterFlow, BoilerField::dhwFlow);
        project(s.heatingEnabled, BoilerField::heatingEnabled);
        project(s.serviceCode, BoilerField::serviceNumber);
        s.burningGas.reset(); s.pumpEnabled.reset(); s.fanEnabled.reset();
        if (const auto code = monitor_.value(BoilerField::displayCode, now))
            s.displayCode = std::array<char, 3>{static_cast<char>(*code >> 8), static_cast<char>(*code & 255), 0};
        else s.displayCode.reset();
    }
    {
        std::lock_guard<std::mutex> paramLock(boilerParams_.mutex);
        project(boilerParams_.heatingTemperature, BoilerField::heatingLimit, 100);
        boilerParams_.maximumHeatingTemperature.reset(); // not provided by Classic0x16
    }
}

void EmsController::processTelegrams() {
	EmsRawFrame frame;
	uint64_t receivedAtMs;
	// Bound the work per loop even when the UART producer stays busy.
	for (int i = 0; i < maxTelegramQueueSize && telegramsToProcess_.pop(frame, &receivedAtMs); ++i) {
		decodeTelegram(frame.data.data(), frame.length, receivedAtMs);
	}
}

void EmsController::reportStats() {
	const auto now = millis();
	if (!ib::millisDurationPassed(now, lastStatsMillis_, 30000ul)) {
		return;
	}
	lastStatsMillis_ = now;
	DBGLOGFD(log_, logFeature_, "EMS totals: poll=%lu tx=%lu unconfirmed=%zu rx_drop=%lu uart_err=%lu timeout=%lu resets=%lu fwd_err=%lu fwd_drop=%lu poll_service_max_us=%lu\n",
		static_cast<unsigned long>(polls_.load(std::memory_order_relaxed)),
		static_cast<unsigned long>(txFrames_.load(std::memory_order_relaxed)),
		txNotConfirmed_.load(std::memory_order_relaxed),
		static_cast<unsigned long>(rxDropped_.load(std::memory_order_relaxed)),
		static_cast<unsigned long>(uart_.rxErrors.load(std::memory_order_relaxed)),
		static_cast<unsigned long>(uart_.rxTimeouts.load(std::memory_order_relaxed)),
		static_cast<unsigned long>(uart_.resets.load(std::memory_order_relaxed)),
		static_cast<unsigned long>(uart_.forwarderErrors()),
		static_cast<unsigned long>(uart_.forwarderDropped()),
		static_cast<unsigned long>(maxPollServiceUs_.exchange(0, std::memory_order_relaxed)));
}

void EmsController::processReadRequest(EmsTelegram const &telegram) {
	DBGLOGFD(log_, logFeature_, "processReadRequest, from: 0x%2.2X\n", telegram.getSenderId());

	if (telegram.getTypeId() == UBADeviceVersion::predefinedTypeId) {
		reinterpret_cast<UBADeviceVersion const *>(&telegram)->logData(*log_, logFeature_);
		enqueueTelegramToSend(UBADeviceVersion::getResponse(deviceId_, telegram.getSenderId(), telegram.getOffset(), telegram.getRequestedDataSize()));
	} else { // reply empty message
		DBGLOGFD(log_, logFeature_, "processReadRequest, unknown telegram 0x%4.4X from: 0x%2.2X. Replying with empty msg\n", telegram.getTypeId(), telegram.getSenderId());
		enqueueTelegramToSend(EmsTelegram{EmsTelegram::operation_t::WRITE, deviceId_, telegram.getSenderId(), 0, telegram.getTypeId(), {}});
	}
}

void EmsController::startHeating(uint8_t heatingTemperature) {
	// 1 - always 01
	// 2 - heating temperature
	// 3 - always 0x64 - probably burner power percentage of max burner power
	// 4 - 00 ? heating enabled?
	// 5 - always 01
	// disable heating if:
	// [EmsControl] (0x88) -W-> (0x18), type: 0x02E0, offset: 0, dataLen: 5 data: 01 FF 00 01 01

	DBGLOGFD(log_, logFeature_, "startHeating, temp: %d\n", heatingTemperature);

	enqueueTelegramToSend(EmsTelegram(EmsTelegram::operation_t::WRITE, deviceId_, 0x08, 0, 0x02e0, {0x01, heatingTemperature, 0x64, 0x00, 0x01}), true); // 0x64 - burner power 100%
}

void EmsController::stopHeating() {
	DBGLOGFD(log_, logFeature_, "stopHeating\n");
	enqueueTelegramToSend(EmsTelegram(EmsTelegram::operation_t::WRITE, deviceId_, 0x08, 0, 0x02e0, {0x01, 0x00, 0x00, 0x00, 0x01}), true); // stop heating
}

void EmsController::setHeatingTemperature(uint8_t temperature) {
	auto currentHeatingTemp = boilerParams_.getHeatingTemperature();
	DBGLOGFD(log_, logFeature_, "setHeatingTemperature, temp: %d, current: %d\n", temperature, currentHeatingTemp.value_or(0));

	if (currentHeatingTemp.has_value() && currentHeatingTemp.value() == temperature) {
		DBGLOGFD(log_, logFeature_, "setHeatingTemperature already set, skipping\n");
		return;
	}

	enqueueTelegramToSend(UBAParametersPlus::setHeatingTemperature(deviceId_, boilerId_, temperature));
}

} // namespace heating::ems

//processTelegram (9): 98 08 FF 00 01 EA 00 FA 00
// [EmsControl] (0x98) -W-> (0x8), type: 0x02EA, offset: 0, dataLen: 1 data: 00
