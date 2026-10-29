#pragma once

#include "Logging.h"
#include "Board.h"
#include "EmsUartWriter.h"

#include <driver/uart.h>
#include <hal/uart_types.h>
#include <soc/uart_reg.h>
#include <array>

#include <optional>
#include <atomic>
#include "EMS/EmsFrameQueue.h"

namespace heating {

namespace uart_detail {
static void uart_forwarder_event_task(void *pvParameters);
}

class EmsBusUartForwarder {
public:
	ib::logger::LoggerInterface::LogFeatureType getLogFeature() const { return logFeature_; }
	std::shared_ptr<ib::logger::LoggerInterface> getLogger() const { return log_; }
	explicit EmsBusUartForwarder(std::shared_ptr<ib::logger::LoggerInterface> log) : log_(std::move(log)) {
		if (log_) {
			logFeature_ = log_->addFeature("EmsUartFwd");
		}
		heads_.fill(-1);
		tails_.fill(-1);
		for (size_t i = 0; i < slots_.size(); ++i) {
			slots_[i].next = i + 1 < slots_.size() ? static_cast<int>(i + 1) : -1;
		}
	}
	static constexpr int EmsBusBaudrate = 9600;
	static constexpr int UartSlot = 1;
	static constexpr size_t EmsMaxTelegramSize = 33;

	static constexpr size_t MaxForwarderQueueSize = 10;

	void start(uint8_t rxPin = 13, uint8_t txPin = 5);

	bool isEnabled() {
		return enabled_.load(std::memory_order_acquire);
	}

	bool writeToEms(const std::vector<uint8_t>& data) {
        return writeToEms(data.data(), data.size());
    }

    bool writeToEms(const uint8_t* data, size_t length) {
        return uart_detail::writePaced<UartSlot, board::emsTransmitAllowed>(data, length);
    }

	std::optional<ems::EmsRawFrame> getDataToWriteToEmsBus(uint8_t id) {
		if (id >= heads_.size()) {
			return {};
		}
		std::optional<ems::EmsRawFrame> result;
		portENTER_CRITICAL(&queueMux_);
		const int index = heads_[id];
		if (index >= 0) {
			auto &slot = slots_[index];
			result = slot.frame;
			heads_[id] = slot.next;
			if (heads_[id] < 0) {
				tails_[id] = -1;
			}
			--sizes_[id];
			slot.next = freeHead_;
			freeHead_ = index;
		}
		portEXIT_CRITICAL(&queueMux_);
		return result;
	}

	// fetch_add targets: static, internal RAM (owner lives in PSRAM; see EmsBusUart).
	static inline std::atomic<uint32_t> rxErrors{0};
	static inline std::atomic<uint32_t> dropped{0};
	template<class Visit> static void visitRmwAtomics(Visit&& visit) {
		visit("forwarder.rx_errors", &rxErrors); visit("forwarder.dropped", &dropped);
	}

private:
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};
	QueueHandle_t getQueueHandle() {
		return uartQueue_;
	}

	constexpr int getUartSlot() {
		return UartSlot;
	}

	uint8_t *getDataBuffer() {
		return buffer_.data();
	}

	uint32_t getDataBufferSize() {
		return static_cast<uint32_t>(buffer_.size());
	}

	void enqueueWriteToEmsBus(const uint8_t *data, uint8_t length) {
		if (length == 0 || length > ems::EmsRawFrame::capacity) {
			return;
		}
		const uint8_t id = data[0] & 0x7F;
		bool full;
		portENTER_CRITICAL(&queueMux_);
		full = freeHead_ < 0 || sizes_[id] == MaxForwarderQueueSize;
		if (!full) {
			const int index = freeHead_;
			auto &slot = slots_[index];
			freeHead_ = slot.next;
			slot.next = -1;
			slot.frame.length = length;
			std::copy_n(data, length, slot.frame.data.begin());
			if (tails_[id] >= 0) {
				slots_[tails_[id]].next = index;
			} else {
				heads_[id] = index;
			}
			tails_[id] = index;
			++sizes_[id];
		}
		portEXIT_CRITICAL(&queueMux_);
		if (full) {
			dropped.fetch_add(1, std::memory_order_relaxed);
		}
	}

	std::atomic<bool> enabled_{false};
	QueueHandle_t uartQueue_;
	std::array<uint8_t, EmsMaxTelegramSize> buffer_;
	struct Slot {
		ems::EmsRawFrame frame;
		int next = -1;
	};
	// Bounded shared pool; per-device FIFO order and the existing limit of ten.
	std::array<Slot, 32> slots_{};
	std::array<int, 128> heads_{};
	std::array<int, 128> tails_{};
	std::array<uint8_t, 128> sizes_{};
	int freeHead_ = 0;
	portMUX_TYPE queueMux_ = portMUX_INITIALIZER_UNLOCKED;

	friend void heating::uart_detail::uart_forwarder_event_task(void *pvParameters);
};

namespace uart_detail {
static void uart_forwarder_event_task(void *pvParameters) {
	EmsBusUartForwarder *bus = static_cast<heating::EmsBusUartForwarder *>(pvParameters);
	uart_event_t event;
	uint32_t length = 0;

	for (;;) {
		if (!xQueueReceive(bus->getQueueHandle(), &event, portMAX_DELAY)) {
			continue;
		}
		switch (event.type) {
		case UART_DATA:
			length += event.size;
			break;
		case UART_BREAK: {
			const bool validSize = length > 1 && length <= bus->getDataBufferSize();
			bool complete = validSize;
			while (length > 0) {
				const auto chunk = std::min(length, bus->getDataBufferSize());
				const int read = uart_read_bytes(bus->getUartSlot(), bus->getDataBuffer(), chunk, 0);
				if (read != static_cast<int>(chunk)) {
					complete = false;
					uart_flush_input(bus->getUartSlot());
					xQueueReset(bus->getQueueHandle());
					break;
				}
				length -= chunk;
				if (complete) {
					bus->enqueueWriteToEmsBus(bus->getDataBuffer(), static_cast<uint8_t>(chunk - 1));
				}
			}
			if (!complete) {
				bus->rxErrors.fetch_add(1, std::memory_order_relaxed);
			}
			length = 0;
			break;
		}
		case UART_FIFO_OVF:
		case UART_BUFFER_FULL:
			bus->rxErrors.fetch_add(1, std::memory_order_relaxed);
			uart_flush_input(bus->getUartSlot());
			xQueueReset(bus->getQueueHandle());
			length = 0;
			break;
		case UART_PARITY_ERR:
		case UART_FRAME_ERR:
			bus->rxErrors.fetch_add(1, std::memory_order_relaxed);
			break;
		default:
			break;
		}
	}
	vTaskDelete(nullptr);
}



}

}
