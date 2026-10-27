#pragma once
#include "EmsTelegram.h"
#include <cstddef>
#include <cstdint>
namespace heating::ems {
// Finite UART-owner transaction, separate from heating permission/stop proof.
// EMS-ESP pinned core/emsesp.cpp incoming_telegram closes the bus AFTER a
// matching read reply or write status. No idle pong or automatic retransmission.
class ManualClassicTransaction {
public:
    enum class Result { none, closed, rejected, failed };
    // Engineering reply window, not a measured adapter or physical stop limit.
    static constexpr uint64_t replyWindowUs=200000;
    bool begin(const uint8_t* frame,size_t length,uint64_t now){
        if(closing_)return false;
        if(state_!=State::idle){state_=State::idle;return false;}
        if(!frame||length!=6||frame[0]!=0x0b||frame[3]!=0
            ||frame[5]!=EmsTelegram::calculateCRC(frame,5))return false;
        const bool read=frame[1]==0x88&&((frame[2]==0x16&&frame[4]==2)||(frame[2]==0x02&&frame[4]==10));
        const bool write=frame[1]==8&&frame[2]==0x1a&&(frame[4]==0||(frame[4]>=5&&frame[4]<=90));
        if(!read&&!write)return false;
        read_=read;readType_=read?frame[2]:0;state_=State::reserved;lastNow_=now;return true;
    }
    void finish(bool emitted,uint64_t now){
        if(state_!=State::reserved)return;
        if(!emitted||now<lastNow_){state_=State::idle;return;}
        emittedAt_=lastNow_=now;state_=State::waiting;
    }
    template<class Clock,class Gate,class Close>
    Result receive(const uint8_t* bytes,size_t length,uint64_t acquiredAt,Clock clock,Gate gate,Close close){
        if(state_==State::idle||closing_)return Result::none;
        // Reserve before any external callback, including clock/admission.
        // Nested receive/begin must not consume or replace this exchange.
        closing_=true;
        struct Release{bool& value;~Release(){value=false;}}release{closing_};
        try{
            auto now=clock();
            if(now<lastNow_||(state_==State::waiting&&now-emittedAt_>=replyWindowUs))return retire();
            lastNow_=now;
            // Processing time cannot make an old/equal/future acquisition a
            // reply to this emission. The UART owner captures this before IO.
            if(state_!=State::waiting||!bytes||acquiredAt<=emittedAt_||acquiredAt>now)return Result::none;
            const bool writeStatus=!read_&&length==1&&(bytes[0]==1||bytes[0]==4);
            const bool readLength=readType_==0x16?length==7:readType_==0x02&&length>=8&&length<=15;
            const bool readResponse=read_&&readLength&&bytes[0]==8&&bytes[1]==0x0b
                &&bytes[2]==readType_&&bytes[3]==0&&bytes[length-1]==EmsTelegram::calculateCRC(bytes,length-1);
            if(!writeStatus&&!readResponse)return Result::none;
            const bool rejected=writeStatus&&bytes[0]==4;
            // Retire BEFORE IO: no exception, second status or replay may send
            // another completion byte. Recheck time and transport after match.
            const bool permitted=gate();now=clock();
            if(!permitted||now<lastNow_||now-emittedAt_>=replyWindowUs)return retire();
            state_=State::idle;
            if(!close())return Result::failed;
            const bool stillPermitted=gate();const auto finished=clock();
            if(!stillPermitted||finished<now||finished-emittedAt_>=replyWindowUs)return Result::failed;
            return rejected?Result::rejected:Result::closed;
        }catch(...){return retire();}
    }
private:
    Result retire(){state_=State::idle;return Result::failed;}
    enum class State {idle,reserved,waiting};
    State state_=State::idle;bool read_=false,closing_=false;uint8_t readType_=0;uint64_t emittedAt_=0,lastNow_=0;
};
}
