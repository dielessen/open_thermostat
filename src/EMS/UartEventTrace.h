#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <ostream>

namespace heating::ems {
// Diagnostic only, never an admission input. The UART task records recent SDK
// events and its own echo writes; an accounting fault freezes a copy BEFORE the
// reset clears the echo debt, so the event order that caused it stays readable.
class UartEventTrace {
public:
    enum class Kind : uint8_t { data, brk, overflow, parity, framing, other, writeStart, writeEnd, timeout, breakRecovered };
    struct Event { Kind kind; uint16_t size; uint32_t atUs; };
    struct EchoState { size_t consumed, trailing; bool echoFrame, broken; uint32_t length; };
    static constexpr size_t capacity=16;

    // Plain value: the status reader receives its own copy under the owner's lock.
    struct Snapshot {
        std::array<Event,capacity> events{};
        size_t count=0;
        EchoState state{};
        uint32_t atUs=0;
        bool valid=false;

        void writeJSON(std::ostream& out) const {
            if(!valid){out<<"null";return;}
            out<<"{\"frozen_at_us\":"<<atUs<<",\"echo_consumed\":"<<state.consumed
               <<",\"echo_trailing\":"<<state.trailing<<",\"echo_frame\":"<<(state.echoFrame?"true":"false")
               <<",\"echo_broken\":"<<(state.broken?"true":"false")<<",\"pending_length\":"<<state.length
               <<",\"events\":[";
            for(size_t i=0;i<count;++i)
                out<<(i?",":"")<<"[\""<<name(events[i].kind)<<"\","<<events[i].size<<','<<events[i].atUs<<']';
            out<<"]}";
        }
    };

    void record(Kind kind,size_t size,uint32_t atUs) {
        events_[next_%capacity]={kind,static_cast<uint16_t>(size>65535?65535:size),atUs};
        ++next_;
    }
    // Oldest first. Called by the same task that records.
    Snapshot freeze(const EchoState& state,uint32_t atUs) const {
        Snapshot s;s.count=next_<capacity?next_:capacity;
        for(size_t i=0;i<s.count;++i)s.events[i]=events_[(next_-s.count+i)%capacity];
        s.state=state;s.atUs=atUs;s.valid=true;
        return s;
    }

    static const char* name(Kind kind) {
        switch(kind) {
            case Kind::data:return "data"; case Kind::brk:return "break";
            case Kind::overflow:return "overflow"; case Kind::parity:return "parity";
            case Kind::framing:return "framing"; case Kind::writeStart:return "write_start";
            case Kind::writeEnd:return "write_end"; case Kind::timeout:return "timeout";
            case Kind::breakRecovered:return "break_recovered";
            default:return "other";
        }
    }
private:
    std::array<Event,capacity> events_{};
    size_t next_=0;
};
}
