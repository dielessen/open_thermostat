#pragma once
#include "EmsTelegram.h"
#include <cstdint>
#include <optional>
#include <ostream>
#include <string>

namespace heating::ems {
// Passive Classic bus facts outside the 69 fixed boiler field IDs. Read only:
// observing these never transmits, admits a request or changes a setting.
// Owned by EmsController's existing telemetry mutex.
// Wire layout: https://emsesp.org/EMS-bus and the EMS-ESP telegram reference;
// independent implementation, no copied EMS-ESP code.
class ClassicBusObservations {
public:
    static constexpr uint8_t boilerAddress=0x08,serviceAddress=0x0b;
    void observe(const EmsTelegram& t,uint64_t now) {
        if(!t.dataSize()||t.getOperationType()==EmsTelegram::READ||t.getOperationType()==EmsTelegram::READ_WITH_DATA)return;
        switch(t.getTypeId()) {
            // UBASetPoints written to the boiler by another controller, such as
            // the room thermostat. Our own service-address trial is recorded separately.
            case 0x1A:
                if(t.getDestinationId()!=boilerAddress||t.getSenderId()==boilerAddress
                   ||t.getSenderId()==serviceAddress||t.getOffset()!=0)return;
                if(const auto flow=t.byteAt(0)) {
                    if(setpoint_.observed&&now<setpoint_.observedMs)return;
                    const auto power=t.byteAt(1),pump=t.byteAt(2);
                    setpoint_={t.getSenderId(),*flow,limited(power),limited(pump),now,setpoint_.count+1,true};
                }
                return;
            // UBAMaintenanceStatus: offset 5 holds the maintenance message number (0 = none).
            case 0x1C:
                if(t.getSenderId()!=boilerAddress)return;
                if(const auto code=t.byteAt(5);code&&*code!=0xFF) {
                    if(maintenance_.observed&&now<maintenance_.observedMs)return;
                    maintenance_={*code,now,true};
                }
                return;
            // UBAErrorMessage1/2: first record = 2 ASCII code characters, number,
            // year/month/hour/day/minute and duration. Keep the newest valid record.
            case 0x10: case 0x11:
                if(t.getSenderId()==boilerAddress&&t.getOffset()==0&&t.dataSize()>=11)error(t,now);
                return;
            default:return;
        }
    }
    void writeJSON(std::ostream& out,uint64_t now) const {
        out<<"{\"schema\":1,\"thermostat_setpoint\":";
        if(!setpoint_.observed)out<<"null";
        else {
            out<<"{\"source_address\":"<<unsigned(setpoint_.sender)<<",\"flow_c\":"<<unsigned(setpoint_.flowC)
               <<",\"burner_power_percent\":";optional(out,setpoint_.power);
            out<<",\"pump_percent\":";optional(out,setpoint_.pump);
            out<<",\"reports\":"<<setpoint_.count<<",\"age_ms\":";age(out,now,setpoint_.observedMs);
            out<<",\"observed_at_ms\":"<<setpoint_.observedMs<<'}';
        }
        out<<",\"maintenance\":";
        if(!maintenance_.observed)out<<"null";
        else {
            out<<"{\"message\":";
            if(maintenance_.code)out<<"\"H"<<(maintenance_.code<10?"0":"")<<unsigned(maintenance_.code)<<'"';else out<<"null";
            out<<",\"code\":"<<unsigned(maintenance_.code)<<",\"age_ms\":";age(out,now,maintenance_.observedMs);out<<'}';
        }
        out<<",\"last_error\":";
        if(!lastError_.observed)out<<"null";
        else {
            out<<"{\"code\":\""<<lastError_.code[0]<<lastError_.code[1]<<"\",\"number\":"<<lastError_.number
               <<",\"started\":\""<<2000+lastError_.year<<'-'<<two(lastError_.month)<<'-'<<two(lastError_.day)
               <<'T'<<two(lastError_.hour)<<':'<<two(lastError_.minute)<<"\",\"duration_min\":"<<lastError_.duration
               <<",\"age_ms\":";age(out,now,lastError_.observedMs);out<<'}';
        }
        out<<",\"control_qualified\":false}";
    }
private:
    struct Setpoint{uint8_t sender=0,flowC=0;std::optional<uint8_t> power,pump;uint64_t observedMs=0;uint32_t count=0;bool observed=false;};
    struct Maintenance{uint8_t code=0;uint64_t observedMs=0;bool observed=false;};
    struct Error{char code[2]{};uint16_t number=0,duration=0;uint8_t year=0,month=0,day=0,hour=0,minute=0;
        uint32_t sortKey=0;uint64_t observedMs=0;bool observed=false;};
    static std::optional<uint8_t> limited(std::optional<uint8_t> v){return v&&*v<=100?v:std::nullopt;}
    static void optional(std::ostream& out,std::optional<uint8_t> v){if(v)out<<unsigned(*v);else out<<"null";}
    static void age(std::ostream& out,uint64_t now,uint64_t at){if(now>=at)out<<now-at;else out<<"null";}
    static std::string two(unsigned v){return std::string(v<10?"0":"")+std::to_string(v);}
    static bool printable(uint8_t c){return c>=32&&c<=126&&c!='"'&&c!='\\';}
    void error(const EmsTelegram& t,uint64_t now) {
        uint8_t b[11];
        for(uint8_t i=0;i<11;++i){const auto v=t.byteAt(i);if(!v)return;b[i]=*v;}
        const uint8_t year=b[4]&0x7F,month=b[5],hour=b[6],day=b[7],minute=b[8];
        if(!printable(b[0])||!printable(b[1])||!month||month>12||!day||day>31||hour>23||minute>59)return;
        const uint32_t key=((((uint32_t(year)*13+month)*32+day)*24+hour)*60)+minute;
        if(lastError_.observed&&key<lastError_.sortKey)return; // Records arrive newest-first; keep the newest.
        lastError_={{char(b[0]),char(b[1])},uint16_t(b[2]<<8|b[3]),uint16_t(b[9]<<8|b[10]),year,month,day,hour,minute,key,now,true};
    }
    Setpoint setpoint_;Maintenance maintenance_;Error lastError_;
};
}
