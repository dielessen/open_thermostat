#pragma once
#include "ClassicBoilerSettingSpec.h"
#include "ManualClassicUartWrite.h"
namespace heating::ems {
// Final SDK boundary for persistent settings. It independently verifies the
// checksum and compares every wire byte with the explicit admitted intent.
// It cannot borrow the commissioning setpoint/configuration-read whitelist.
struct ClassicSettingUartWrite {
    using Setting=ClassicBoilerSettingSpec::Setting;
    using Result=ManualClassicUartWrite::Result;
    template<bool Enabled,bool Read=false,class IO>
    static Result write(const uint8_t* data,size_t length,Setting setting,int value,IO& io){
        if constexpr(!Enabled)return {};
        else {
            ClassicBoilerSettingSpec::Definition spec{};uint8_t wire=0;
            if(!data||length!=6||!ClassicBoilerSettingSpec::definition(setting,spec)
                ||!ClassicBoilerSettingSpec::wireValue(setting,value,wire)
                ||data[0]!=0x0b||data[1]!=(Read?0x88:8)||data[2]!=0x16
                ||data[3]!=spec.offset||data[4]!=(Read?1:wire))return {};
            uint8_t crc=0;
            for(size_t i=0;i<5;++i)crc=static_cast<uint8_t>((unsigned(crc)<<1)^((crc&0x80)?0x19u:0u)^data[i]);
            if(crc!=data[5])return {};
            // A failed read-only preflight must not acquire or clean up a pin.
            try{if(!io.ready())return {};}catch(...){return {};}
            Result result;result.touched=true;
            try{if(io.attach())result.writeCompleted=io.write(data,length);}catch(...){result.writeCompleted=false;}
            try{result.detached=io.detach();}catch(...){result.detached=false;}
            return result;
        }
    }
};
}
