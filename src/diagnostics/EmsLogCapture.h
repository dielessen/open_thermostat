#pragma once
#include "SystemLog.h"

namespace heating::diagnostics {
// Only called from deferred decode after a frame has been parsed. Never from
// UART/ISR, never allocate/network here, never change receive admission or TX.
inline void captureEmsRx(SystemLog& log,const uint8_t* bytes,size_t length,
        uint8_t sender,uint8_t destination,uint16_t type,uint8_t offset,uint64_t receivedAtMs) {
    if(!bytes||length<7||length>33)return;
    char message[193]{};
    const int prefix=std::snprintf(message,sizeof(message),
        "RX src=%02X dst=%02X type=%04X offset=%u len=%u frame=",
        unsigned(sender),unsigned(destination),unsigned(type),unsigned(offset),unsigned(length));
    if(prefix<0||size_t(prefix)+length*3>=sizeof(message))return;
    constexpr char hex[]="0123456789ABCDEF";size_t cursor=size_t(prefix);
    for(size_t i=0;i<length;++i){
        if(i)message[cursor++]=' ';
        message[cursor++]=hex[bytes[i]>>4];message[cursor++]=hex[bytes[i]&15];
    }
    log.append(3,"EMS",std::string_view(message,cursor),receivedAtMs);
}
}
