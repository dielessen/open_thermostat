#pragma once
#include "ClassicBoilerSettingsEncoder.h"

namespace heating::ems {
// Separate UART-owned exchange for an exact setting intent. Does not extend
// ManualClassicTransaction's commissioning whitelist or register any IO route.
class ClassicSettingBusExchange {
public:
    using Setting = ClassicBoilerSettingsEncoder::Setting;
    enum class Result { none, writeClosed, readClosed, rejected, failed };
    struct Event { Result result; uint32_t revision; };
    static constexpr uint64_t replyWindowUs = 200000;
    void cancel(){state_=State::idle;}
    bool active() const { return state_ != State::idle || closing_; }
    bool begin(const EmsRawFrame& frame, Setting setting, int value,
               uint32_t revision, bool read, uint64_t now) {
        if (closing_) return false;
        if (state_ != State::idle) { state_ = State::idle; return false; }
        EmsRawFrame expected;
        if (!revision || !ClassicBoilerSettingsEncoder::encode(
                ClassicBoilerTestEncoder::Addressing::classicService(),true,setting,value,expected)) return false;
        if (read) {
            expected.data[1]=0x88; expected.data[4]=1;
            expected.data[5]=EmsTelegram::calculateCRC(expected.data.data(),5);
        }
        if (frame.length!=expected.length) return false;
        for (size_t i=0;i<expected.length;++i) if(frame.data[i]!=expected.data[i]) return false;
        read_=read; revision_=revision; offset_=expected.data[3];
        lastNow_=now; state_=State::reserved; return true;
    }
    void finish(bool emitted, uint64_t now) {
        if (state_ != State::reserved) return;
        if (!emitted || now<lastNow_) { state_=State::idle; return; }
        emittedAt_=lastNow_=now; state_=State::waiting;
    }
    // acquiredAt is captured before any completion-byte IO. Millisecond status
    // clocks cannot establish ordering inside this microsecond bus exchange.
    template<class Clock,class Gate,class Close>
    Event receive(const uint8_t* bytes,size_t length,uint64_t acquiredAt,
                  Clock clock,Gate gate,Close close) {
        if (state_==State::idle || closing_) return {Result::none,0};
        // Clock and admission callbacks share the same ownership protection
        // as completion-byte IO; none may reenter or replace this exchange.
        closing_=true;
        struct Release { bool& value; ~Release(){value=false;} } release{closing_};
        const auto revision=revision_;
        try {
            auto now=clock();
            if (now<lastNow_ || (state_==State::waiting && now-emittedAt_>=replyWindowUs)) return retire();
            lastNow_=now;
            if (state_!=State::waiting || !bytes || acquiredAt<=emittedAt_ || acquiredAt>now)
                return {Result::none,0};
            const bool status=!read_ && length==1 && (bytes[0]==1 || bytes[0]==4);
            const bool response=read_ && length==6 && bytes[0]==8 && bytes[1]==0x0b
                && bytes[2]==0x16 && bytes[3]==offset_
                && bytes[5]==EmsTelegram::calculateCRC(bytes,5);
            if (!status && !response) return {Result::none,0};
            const bool rejected=status && bytes[0]==4;
            const bool permitted=gate(); now=clock();
            if (!permitted || now<lastNow_ || now-emittedAt_>=replyWindowUs) return retire();
            state_=State::idle;
            if (!close()) return {Result::failed,revision};
            const bool stillPermitted=gate(); const auto finished=clock();
            if (!stillPermitted || finished<now || finished-emittedAt_>=replyWindowUs)
                return {Result::failed,revision};
            return {rejected?Result::rejected:read_?Result::readClosed:Result::writeClosed,revision};
        } catch (...) { state_=State::idle; return {Result::failed,revision}; }
    }
    // Called even when the bus is silent, to release ownership at the deadline.
    Event tick(uint64_t now,bool permitted) {
        if (state_==State::idle || closing_) return {Result::none,0};
        if (!permitted || now<lastNow_ || (state_==State::waiting && now-emittedAt_>=replyWindowUs)) return retire();
        lastNow_=now; return {Result::none,0};
    }
private:
    Event retire() { const auto revision=revision_; state_=State::idle; return {Result::failed,revision}; }
    enum class State { idle,reserved,waiting };
    State state_=State::idle;
    bool read_=false,closing_=false;
    uint8_t offset_=0;
    uint32_t revision_=0;
    uint64_t lastNow_=0,emittedAt_=0;
};
} // namespace heating::ems
