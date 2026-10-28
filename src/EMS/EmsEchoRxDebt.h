#pragma once
#include <cstddef>
#include <cstdint>
namespace heating::ems {
// UART task only: a checked synchronous echo read consumes ring-buffer bytes,
// while their already queued UART_DATA events still arrive. Retire those counts
// exactly once; never subtract the BREAK byte or the next device's data.
class EmsEchoRxDebt {
public:
    static constexpr size_t capacity=32;
    bool hasRoom() const {return consumed_<capacity;}
    bool consumedByte(){if(!hasRoom())return false;++consumed_;echoFrame_=true;return true;}
    size_t dataEvent(size_t bytes){
        const auto covered=bytes<consumed_?bytes:consumed_;consumed_-=covered;
        const auto remaining=bytes-covered;
        // Normally only our 0x00 BREAK delimiter remains before this echo's
        // BREAK event. If more bytes follow, the UART did not report our own
        // BREAK (attended trial 2026-10-27: echo, then 00 01 00 in one event):
        // the first byte must be that delimiter, checked by acceptDelimiter()
        // when read, and the rest is the next frame. A lost echo DATA event
        // still leaves debt at BREAK.
        if(echoFrame_&&remaining&&!coalesced_) {
            if(trailing_+remaining>1)coalesced_=true;else trailing_+=remaining;
        }
        return remaining;
    }
    // Called with the first byte read at BREAK when coalesced(). No valid EMS
    // frame starts with 0x00 (sender or poll byte), so anything else means a
    // later device's bytes moved into our frame.
    bool acceptDelimiter(uint8_t first){
        if(coalesced_&&first!=0)broken_=true;
        return !broken_;
    }
    bool atBreak() const {return consumed_==0&&!broken_;}
    bool idle() const {return !echoFrame_&&atBreak();}
    void reset(){consumed_=trailing_=0;echoFrame_=broken_=coalesced_=false;}
    // Diagnostic reads only.
    size_t consumed() const {return consumed_;}
    size_t trailing() const {return trailing_;}
    bool echoFrame() const {return echoFrame_;}
    bool broken() const {return broken_;}
    bool coalesced() const {return coalesced_;}
private:
    size_t consumed_=0,trailing_=0;
    bool echoFrame_=false,broken_=false,coalesced_=false;
};
}
