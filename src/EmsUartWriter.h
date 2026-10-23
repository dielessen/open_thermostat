#pragma once
#include "EMS/PacedUartWrite.h"
#include <driver/uart.h>
#include <Arduino.h>

namespace heating::uart_detail {

// Both bus routes use identical checked SDK operations. The existing IDF write
// primitive may take its internal mutex; this is not a total execution bound.
// The installation still needs its own timing/arbitration qualification.
template<int Slot, bool Enabled>
bool writePaced(const uint8_t* data, size_t length) {
    struct SDK {
        int writeByte(uint8_t byte) { return uart_write_bytes(Slot, &byte, 1); }
        bool idle() { return uart_wait_tx_done(Slot, 0) == ESP_OK; }
        bool invert(bool active) {
            return uart_set_line_inverse(Slot, active ? UART_SIGNAL_TXD_INV : 0) == ESP_OK;
        }
        void delayUs(uint32_t us) { delayMicroseconds(us); }
    } sdk;
    return ems::PacedUartWrite::write<Enabled>(data, length, sdk);
}

} // namespace heating::uart_detail
