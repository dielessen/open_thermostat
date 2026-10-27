#pragma once
#include <cstddef>
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
        // Only the delimiter byte may remain before this echo's BREAK. Lost
        // echo/BREAK events must not shift a later device's payload into a frame.
        if(echoFrame_){if(remaining>1||trailing_>1-remaining)broken_=true;else trailing_+=remaining;}
        return remaining;
    }
    bool atBreak() const {return consumed_==0&&!broken_;}
    bool idle() const {return !echoFrame_&&atBreak();}
    void reset(){consumed_=trailing_=0;echoFrame_=broken_=false;}
    // Diagnostic reads only.
    size_t consumed() const {return consumed_;}
    size_t trailing() const {return trailing_;}
    bool echoFrame() const {return echoFrame_;}
    bool broken() const {return broken_;}
private:
    size_t consumed_=0,trailing_=0;
    bool echoFrame_=false,broken_=false;
};
}
