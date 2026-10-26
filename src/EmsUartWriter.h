#pragma once
#include "EMS/PacedUartWrite.h"
#include "EMS/ClassicEchoUartWrite.h"
#include "EMS/EmsEchoRxDebt.h"
#include "EMS/ManualClassicUartWrite.h"
#include <driver/gpio.h>
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

// Separate E32 Classic route; physical permission still comes from Board.h.
// The UART owner retires queued DATA counts for bytes synchronously consumed.
template<int Slot,bool Enabled>
bool writeClassic(const uint8_t* data,size_t length,ems::EmsEchoRxDebt& debt) {
    if constexpr(Enabled) {if(!debt.idle())return false;}
    struct SDK {
        ems::EmsEchoRxDebt& debt;
        int readEcho(uint8_t& byte){
            if(!debt.hasRoom())return -1;
            const int read=uart_read_bytes(Slot,&byte,1,0);
            if(read==1&&!debt.consumedByte())return -1;
            return read;
        }
        int writeByte(uint8_t byte){return uart_write_bytes(Slot,&byte,1);}
        bool buffered(size_t& bytes){return uart_get_buffered_data_len(Slot,&bytes)==ESP_OK;}
        bool idle(){return uart_wait_tx_done(Slot,0)==ESP_OK;}
        bool invert(bool active){return uart_set_line_inverse(Slot,active?UART_SIGNAL_TXD_INV:0)==ESP_OK;}
        void delayUs(uint32_t us){delayMicroseconds(us);}
    } sdk{debt};
    return ems::ClassicEchoUartWrite::write<Enabled>(data,length,sdk);
}

// GPIO reset explicitly disconnects the peripheral matrix in IDF4.4. All
// cleanup operations are attempted even if an earlier one reports a failure.
template<int TxPin>
bool releaseManualTx(){
    const auto pin=static_cast<gpio_num_t>(TxPin);
    const bool reset=gpio_reset_pin(pin)==ESP_OK;
    const bool input=gpio_set_direction(pin,GPIO_MODE_INPUT)==ESP_OK;
    const bool floating=gpio_set_pull_mode(pin,GPIO_FLOATING)==ESP_OK;
    return reset&&input&&floating;
}
template<int Slot,int TxPin,bool Enabled,bool ConfigurationRead=false,bool Completion=false>
ems::ManualClassicUartWrite::Result writeManualClassic(const uint8_t* data,size_t length,ems::EmsEchoRxDebt& debt){
    static_assert(!ConfigurationRead||!Completion,"Separate fixed manual operations");
    static_assert(Slot==2&&TxPin==5,"Manual route is restricted to the reviewed E32 wiring");
    if constexpr(Enabled){if(!debt.idle())return {};}
    struct SDK {
        ems::EmsEchoRxDebt& debt;
        bool ready(){
            size_t bytes=0;
            return debt.idle() && uart_get_buffered_data_len(Slot,&bytes)==ESP_OK
                && bytes==0 && uart_wait_tx_done(Slot,0)==ESP_OK;
        }
        bool attach(){
            return uart_wait_tx_done(Slot,0)==ESP_OK
                &&uart_set_line_inverse(Slot,0)==ESP_OK
                &&uart_set_pin(Slot,TxPin,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE)==ESP_OK;
        }
        bool write(const uint8_t* bytes,size_t size){return writeClassic<Slot,true>(bytes,size,debt);}
        bool detach(){return releaseManualTx<TxPin>();}
    }sdk{debt};
    if constexpr(Completion)return ems::ManualClassicUartWrite::completeTransaction<Enabled>(data,length,sdk);
    else if constexpr(ConfigurationRead)return ems::ManualClassicUartWrite::readConfiguration<Enabled>(data,length,sdk);
    else return ems::ManualClassicUartWrite::write<Enabled>(data,length,sdk);
}

} // namespace heating::uart_detail
