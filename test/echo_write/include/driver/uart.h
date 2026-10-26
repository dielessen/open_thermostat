#pragma once
#include <cstddef>
#include <cstdint>
constexpr int ESP_OK=0,UART_SIGNAL_TXD_INV=1,UART_PIN_NO_CHANGE=-1;
int uart_write_bytes(int,const void*,size_t);
int uart_read_bytes(int,void*,size_t,uint32_t);
int uart_get_buffered_data_len(int,size_t*);
int uart_wait_tx_done(int,uint32_t);
int uart_set_line_inverse(int,int);
int uart_set_pin(int,int,int,int,int);
