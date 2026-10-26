#pragma once
#include <cstddef>
#include <cstdint>

namespace heating::ems {
// EMS 1.0 timing facts: pinned EMS-ESP32 6e9ed5e uart header/driver.
// 9600 baud: 104us bit, 13us echo polls, at most 160 polls, 10-bit BREAK.
// Every echoed byte must match before writing the next one. This is not a bus
// ACK or boiler-response proof. The UART owner accounts for consumed RX events.
struct ClassicEchoUartWrite {
    static constexpr size_t maximumFrameSize=32;
    static constexpr unsigned maximumEchoPolls=160;
    static constexpr uint32_t echoPollUs=13, breakUs=1040;
    template<bool Enabled,class IO>
    static bool write(const uint8_t* data,size_t length,IO& io) {
        if constexpr(!Enabled) return false;
        else {
            if(!data||!length||length>maximumFrameSize)return false;
            bool breakAttempted=false;
            try {
                size_t count=0;
                // Do not transmit over bytes already awaiting the RX owner.
                if(!io.buffered(count)||count!=0)return false;
                for(size_t i=0;i<length;++i) {
                    if(io.writeByte(data[i])!=1)return false;
                    bool echoed=false;
                    for(unsigned poll=0;poll<maximumEchoPolls;++poll) {
                        io.delayUs(echoPollUs);
                        if(!io.buffered(count)||count>1)return false;
                        if(count==1){echoed=true;break;}
                    }
                    uint8_t received=0;
                    if(!echoed||io.readEcho(received)!=1||received!=data[i])return false;
                }
                if(!io.idle())return false;
                // Even a failed inversion may have touched the physical line.
                breakAttempted=true;
                if(!io.invert(true)){io.invert(false);return false;}
                io.delayUs(breakUs);
                return io.invert(false);
            } catch(...) {
                if(breakAttempted){try{io.invert(false);}catch(...){}}
                return false;
            }
        }
    }
};
}
