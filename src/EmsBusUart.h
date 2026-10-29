#pragma once

#include "Logging.h"
#include "Board.h"
#include "EmsUartWriter.h"
#include "EMS/BreakFrameReader.h"
#include "EMS/EmsFrameQueue.h"
#include "EMS/UartEventTrace.h"

#include <driver/uart.h>
#include <esp_timer.h>
#include <hal/uart_types.h>
#include <soc/uart_reg.h>
#include <array>
#include <atomic>

#include <functional>

#include "EmsBusUartForwarder.h"

namespace heating {


namespace uart_detail {
static void uart_event_task(void *pvParameters);
}

namespace ems {class EmsController;}

class EmsBusUart {
public:
	ib::logger::LoggerInterface::LogFeatureType getLogFeature() const { return logFeature_; }
	std::shared_ptr<ib::logger::LoggerInterface> getLogger() const { return log_; }
	using processTelegram_t = std::function<void(uint8_t *, uint8_t)>;
	static constexpr int EmsBusBaudrate = 9600;
	static constexpr int UartSlot = 2;
	static constexpr size_t EmsMaxTelegramSize = 33;

	EmsBusUart(std::shared_ptr<ib::logger::LoggerInterface> log, processTelegram_t processTelegram) : log_(log), processTelegram_(processTelegram), forwarder_(std::move(log)) {
		if (log_) {
			logFeature_ = log_->addFeature("EmsUart");
		}
	}

	void start(uint8_t rxPin, uint8_t txPin) {
#ifdef OPENTHERMOSTAT_E32V2
		// RX only: no UART output route, including at startup/reset.
		// Runtime cfgpins cannot change board wiring.
		rxPin = board::emsRx;
		txPin = board::emsTx;
		gpio_reset_pin(static_cast<gpio_num_t>(txPin));
		gpio_set_direction(static_cast<gpio_num_t>(txPin), GPIO_MODE_INPUT);
		gpio_set_pull_mode(static_cast<gpio_num_t>(txPin), GPIO_FLOATING);
#endif
		// params copied from EMS-ESP32
		rxPin_ = rxPin;
		txPin_ = txPin;

		uart_config_t uart_config = {
			.baud_rate  = EmsBusBaudrate,
			.data_bits  = UART_DATA_8_BITS,
			.parity     = UART_PARITY_DISABLE,
			.stop_bits  = UART_STOP_BITS_1,
			.flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
			.source_clk = UART_SCLK_APB,
		};

		uart_param_config(UartSlot, &uart_config);
#ifdef OPENTHERMOSTAT_E32V2
		uart_set_line_inverse(UartSlot, 0); // official E32V2: normal UART polarity
#endif
		uart_set_pin(UartSlot, board::emsTransmitAllowed ? txPin : UART_PIN_NO_CHANGE, rxPin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
		uart_driver_install(UartSlot, 129, 0, (EmsMaxTelegramSize + 1) * 2, &uartQueue_, 0);
		uart_set_rx_full_threshold(UartSlot, 1);
		uart_set_rx_timeout(UartSlot, 0);

		// 4096 (was 2560): the frame path has try/catch and logging; the high-water
		// mark is reported in /status/logs (runtime.stack_minimum_bytes.ems_uart).
		xTaskCreate(heating::uart_detail::uart_event_task, "EmsBusUart", 4096, this, configMAX_PRIORITIES - 1, NULL);
		uart_enable_intr_mask(UartSlot, UART_BRK_DET_INT_ENA | UART_RXFIFO_FULL_INT_ENA);

		DBGLOGFD(log_, logFeature_, "Started rx: %d tx: %d\n", rxPin, txPin);
	}

	void startForwarder(uint8_t rxPin, uint8_t txPin) {
		if constexpr (!board::emsTransmitAllowed) return;
		forwarder_.start(rxPin, txPin);
	}

	bool writeToEms(const std::vector<uint8_t>& data) {
        return writeToEms(data.data(), data.size());
    }

    bool writeToEms([[maybe_unused]] const uint8_t* data, [[maybe_unused]] size_t length) {
#ifdef OPENTHERMOSTAT_E32V2
        return false; // E32 legacy/pong/forwarder routes never borrow manual permission.
#else
        return uart_detail::writePaced<UartSlot, board::emsTransmitAllowed>(data, length);
#endif
    }

#ifdef OPENTHERMOSTAT_E32V2
    bool manualTestTransportHealthy()const{return !manualTxFault_.load(std::memory_order_acquire);}
#endif
	void requestReset() { resetRequested_.store(true, std::memory_order_relaxed); }

	uint32_t forwarderErrors() const { return forwarder_.rxErrors.load(std::memory_order_relaxed); }
	uint32_t forwarderDropped() const { return forwarder_.dropped.load(std::memory_order_relaxed); }
    enum class RxError : uint8_t { none, echoAccounting, shortFrame, overflow, parity, framing };
    struct RxErrorInfo { const char* reason; uint64_t observedAtMs; };
    RxErrorInfo lastRxError() const {
        portENTER_CRITICAL(&rxErrorMux_);
        const auto kind=lastRxErrorKind_;
        const auto at=lastRxErrorAtMs_;
        portEXIT_CRITICAL(&rxErrorMux_);
        const char* reason="none";
        switch(kind) {
            case RxError::echoAccounting:reason="echo_event_accounting";break;
            case RxError::shortFrame:reason="incomplete_rx_frame";break;
            case RxError::overflow:reason="rx_buffer_overflow";break;
            case RxError::parity:reason="rx_parity_error";break;
            case RxError::framing:reason="rx_framing_error";break;
            default:break;
        }
        return {reason,at};
    }
#ifdef OPENTHERMOSTAT_E32V2
    ems::UartEventTrace::Snapshot lastEchoFault() const {
        portENTER_CRITICAL(&rxErrorMux_);
        const auto copy=lastEchoFault_;
        portEXIT_CRITICAL(&rxErrorMux_);
        return copy;
    }
#endif
    void recordRxError(RxError kind) {
        rxErrors.fetch_add(1,std::memory_order_relaxed);
        const auto at=static_cast<uint64_t>(esp_timer_get_time()/1000);
        portENTER_CRITICAL(&rxErrorMux_);
        lastRxErrorAtMs_=at;lastRxErrorKind_=kind;
        portEXIT_CRITICAL(&rxErrorMux_);
    }
	// fetch_add/exchange targets are static (internal RAM .bss): this object is
	// part of the PSRAM-resident controller, where S32C1I is not atomic. One
	// EMS UART per device (diagnostics/AtomicPlacement.h).
	static inline std::atomic<uint32_t> rxErrors{0};
	static inline std::atomic<uint32_t> rxTimeouts{0};
	static inline std::atomic<uint32_t> resets{0};
	static inline std::atomic<uint32_t> echoBreakRecoveries{0}; // own BREAK unreported, delimiter dropped, reply kept
	static inline std::atomic<uint32_t> breakRealignments{0}; // stale 0x00 before a frame dropped, stream realigned
	template<class Visit> static void visitRmwAtomics(Visit&& visit) {
		visit("uart.rx_errors", &rxErrors); visit("uart.rx_timeouts", &rxTimeouts); visit("uart.resets", &resets);
		visit("uart.echo_break_recoveries", &echoBreakRecoveries); visit("uart.break_realignments", &breakRealignments);
		visit("uart.reset_requested", &resetRequested_);
		EmsBusUartForwarder::visitRmwAtomics(visit);
	}

private:
    // UART task and status reader share a short existing ESP critical-section
    // primitive. Avoid non-lock-free64-bit atomics and an extra SDK archive.
    mutable portMUX_TYPE rxErrorMux_=portMUX_INITIALIZER_UNLOCKED;
    RxError lastRxErrorKind_=RxError::none;
    uint64_t lastRxErrorAtMs_=0; // diagnostic only, never an admission input
#ifdef OPENTHERMOSTAT_E32V2
    friend class ems::EmsController;
    template<bool Read>
    ems::ManualClassicUartWrite::Result writeBoilerSettingToEms(const ems::EmsRawFrame& frame,
        ems::ClassicBoilerSettingSpec::Setting setting,int value){
        if constexpr(!board::emsSettingsTransmitAllowed)return {};
        else{
            if(!manualTestTransportHealthy())return {};
            traceEvent(ems::UartEventTrace::Kind::writeStart,frame.length);
            const auto result=uart_detail::writeClassicSetting<UartSlot,board::emsTx,true,Read>(
                frame.data.data(),frame.length,setting,value,echoRxDebt_);
            traceEvent(ems::UartEventTrace::Kind::writeEnd,result.succeeded());
            if(!result.detached)manualTxFault_.store(true,std::memory_order_release);
            return result;
        }
    }
    ems::ManualClassicUartWrite::Result completeBoilerSettingTransaction(){
        if constexpr(!board::emsSettingsTransmitAllowed)return {};
        else{
            if(!manualTestTransportHealthy())return {};
            const uint8_t completion=0x0b;
            traceEvent(ems::UartEventTrace::Kind::writeStart,1);
            const auto result=uart_detail::writeManualClassic<UartSlot,board::emsTx,true,false,true>(&completion,1,echoRxDebt_);
            traceEvent(ems::UartEventTrace::Kind::writeEnd,result.succeeded());
            if(!result.detached)manualTxFault_.store(true,std::memory_order_release);
            return result;
        }
    }
    // Only called after the commissioning owner's final admission, in UART task.
    template<bool ConfigurationRead=false,bool Completion=false>
    bool writeManualTestToEms(const uint8_t* data,size_t length){
        if constexpr(!board::emsManualTestTransmitAllowed)return false;
        else {
            if(!manualTestTransportHealthy())return false;
            traceEvent(ems::UartEventTrace::Kind::writeStart,length);
            const auto result=uart_detail::writeManualClassic<UartSlot,board::emsTx,true,ConfigurationRead,Completion>(data,length,echoRxDebt_);
            traceEvent(ems::UartEventTrace::Kind::writeEnd,result.succeeded());
            if(!result.detached)manualTxFault_.store(true,std::memory_order_release);
            return result.succeeded();
        }
    }
#endif
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};
	QueueHandle_t getQueueHandle() {
		return uartQueue_;
	}

	constexpr int getUartSlot() {
		return UartSlot;
	}

	void processTelegram(size_t size) {
		bool performProcess = true;
#ifdef OPENTHERMOSTAT_E32V2
		if (size == 0) return;
#endif

		if (forwarder_.isEnabled() && size == 2 && !(buffer_[0] & 0x80) ) { // polling if 0 byte is not masked, if masked then it is poll response
			// DBGLOGFD(log_, logFeature_, "Polling device %d\n", buffer_[0]);
			auto data = forwarder_.getDataToWriteToEmsBus(buffer_[0]); // we have data from that id, send
			if (data) {
				writeToEms(data->data.data(), data->length);
				performProcess = false; // it was a poll to forwarded device, we responded, so this poll is definitely not for us
			}
		}

		if (performProcess) {
			processTelegram_(buffer_.data(), size);
		}

		if (forwarder_.isEnabled() && size > 1) {
			forwarder_.writeToEms(buffer_.data(), size - 1);
		}
	}

	uint8_t *getDataBuffer() {
		return buffer_.data();
	}

	uint32_t getDataBufferSize() {
		return static_cast<uint32_t>(buffer_.size());
	}

	// Recovery runs only in the UART task, between complete event handlers.
	// Queue first: a byte arriving in between then has a count but no data,
	// which costs one short frame instead of shifting every later frame.
	void performReset() {
		xQueueReset(uartQueue_);
		uart_flush_input(UartSlot);
#ifdef OPENTHERMOSTAT_E32V2
        echoRxDebt_.reset();
        if constexpr(board::emsManualTestTransmitAllowed){
            if(!uart_detail::releaseManualTx<board::emsTx>())manualTxFault_.store(true,std::memory_order_release);
        }
#endif
		if constexpr (board::emsTransmitAllowed) uart_send_break(UartSlot);
		resets.fetch_add(1, std::memory_order_relaxed);
	}

#ifdef OPENTHERMOSTAT_E32V2
    std::atomic<bool> manualTxFault_{false}; // failed release requires a new boot/review
    ems::EmsEchoRxDebt echoRxDebt_; // accessed only by the UART task
    ems::UartEventTrace trace_; // UART task only; diagnostic, never an admission input
    ems::UartEventTrace::Snapshot lastEchoFault_; // guarded by rxErrorMux_
    void traceEvent(ems::UartEventTrace::Kind kind,size_t size) {
        trace_.record(kind,size,static_cast<uint32_t>(esp_timer_get_time()));
    }
    // Before performReset() clears the debt that explains the fault.
    void freezeEchoFault(uint32_t pendingLength) {
        const auto snapshot=trace_.freeze({echoRxDebt_.consumed(),echoRxDebt_.trailing(),
            echoRxDebt_.echoFrame(),echoRxDebt_.broken(),pendingLength},static_cast<uint32_t>(esp_timer_get_time()));
        portENTER_CRITICAL(&rxErrorMux_);
        lastEchoFault_=snapshot;
        portEXIT_CRITICAL(&rxErrorMux_);
    }
#endif
	static inline std::atomic<bool> resetRequested_{false}; // exchange() in the UART task: internal RAM
	QueueHandle_t uartQueue_;
	std::array<uint8_t, EmsMaxTelegramSize> buffer_;
	processTelegram_t processTelegram_;
	uint8_t rxPin_;
	uint8_t txPin_;

	EmsBusUartForwarder forwarder_;

	friend void heating::uart_detail::uart_event_task(void *pvParameters);
};

namespace uart_detail {
static void uart_event_task(void *pvParameters) {
	EmsBusUart *bus = static_cast<heating::EmsBusUart *>(pvParameters);
	uart_event_t event;
	uint32_t length = 0;

	constexpr auto rxTimeoutMs = 5000;

	for (;;) {
		if (bus->resetRequested_.exchange(false, std::memory_order_relaxed)) {
			bus->performReset();
			length = 0;
		}
		if (!xQueueReceive(bus->getQueueHandle(), &event, pdMS_TO_TICKS(rxTimeoutMs))) {
			bus->rxTimeouts.fetch_add(1, std::memory_order_relaxed);
#ifdef OPENTHERMOSTAT_E32V2
			bus->traceEvent(ems::UartEventTrace::Kind::timeout,0);
#endif
			bus->requestReset();
			continue;
		}
#ifdef OPENTHERMOSTAT_E32V2
		bus->traceEvent(event.type==UART_DATA?ems::UartEventTrace::Kind::data
			:event.type==UART_BREAK?ems::UartEventTrace::Kind::brk
			:(event.type==UART_FIFO_OVF||event.type==UART_BUFFER_FULL)?ems::UartEventTrace::Kind::overflow
			:event.type==UART_PARITY_ERR?ems::UartEventTrace::Kind::parity
			:event.type==UART_FRAME_ERR?ems::UartEventTrace::Kind::framing
			:ems::UartEventTrace::Kind::other,event.size);
#endif
		switch (event.type) {
		case UART_DATA:
#ifdef OPENTHERMOSTAT_E32V2
            length += bus->echoRxDebt_.dataEvent(event.size);
#else
			length += event.size;
#endif
			break;
		case UART_BREAK: {
#ifdef OPENTHERMOSTAT_E32V2
            // Missing echo DATA events must not eat counts from a later frame.
            if(!bus->echoRxDebt_.atBreak()) {
                bus->freezeEchoFault(length);
                bus->recordRxError(EmsBusUart::RxError::echoAccounting);
                bus->performReset();length=0;break;
            }
            // Our own BREAK went unreported and the reply followed in the same
            // buffer: drop exactly our 0x00 delimiter, keep the reply frame.
            if(bus->echoRxDebt_.coalesced()) {
                uint8_t first=0xFF;
                const int read=length?uart_read_bytes(bus->getUartSlot(),&first,1,0):0;
                if(read!=1||!bus->echoRxDebt_.acceptDelimiter(first)) {
                    bus->freezeEchoFault(length);
                    bus->recordRxError(EmsBusUart::RxError::echoAccounting);
                    bus->performReset();length=0;break;
                }
                --length;
                bus->echoBreakRecoveries.fetch_add(1,std::memory_order_relaxed);
                bus->traceEvent(ems::UartEventTrace::Kind::breakRecovered,length);
            }
            bus->echoRxDebt_.reset();
#endif
			// Events describe bytes already buffered by the driver. Never wait for
			// missing bytes and never flush here: a bad frame is dropped and the
			// counts stay matched to the buffer for the next BREAK.
			struct Io {
				size_t read(uint8_t* dst, size_t n) {
					const int got = uart_read_bytes(EmsBusUart::UartSlot, dst, n, 0);
					return got > 0 ? static_cast<size_t>(got) : 0;
				}
			} io;
			size_t size = 0;
			const auto result = ems::BreakFrameReader::read(io, bus->getDataBuffer(), bus->getDataBufferSize(), length, size);
			if (ems::BreakFrameReader::deliverable(result)) {
				if (result == ems::BreakFrameReader::Result::realigned)
					bus->breakRealignments.fetch_add(1, std::memory_order_relaxed);
				bus->processTelegram(size);
			} else if (result != ems::BreakFrameReader::Result::empty) {
				bus->recordRxError(EmsBusUart::RxError::shortFrame);
			}
			length = 0;
			break;
		}
		case UART_FIFO_OVF:
		case UART_BUFFER_FULL:
			bus->recordRxError(EmsBusUart::RxError::overflow);
			xQueueReset(bus->getQueueHandle());
			uart_flush_input(bus->getUartSlot());
#ifdef OPENTHERMOSTAT_E32V2
            bus->echoRxDebt_.reset();
#endif
			length = 0;
			break;
		case UART_PARITY_ERR:
            bus->recordRxError(EmsBusUart::RxError::parity);
            break;
		case UART_FRAME_ERR:
			bus->recordRxError(EmsBusUart::RxError::framing);
			break;
		default:
			break;
		}
	}
	vTaskDelete(nullptr);
}



}

}
