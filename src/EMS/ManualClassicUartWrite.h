#pragma once
#include <cstddef>
#include <cstdint>
namespace heating::ems {
// Only the finite commissioning owner may call this path. Its encoder supplies
// the CRC; this boundary independently checks it before touching the TX pin.
// Other telegram families/settings are also rejected.
// Mapping lasts one attempted frame. A failed release is never called success.
struct ManualClassicUartWrite {
    struct Result {
        bool writeCompleted=false,detached=true,touched=false;
        bool succeeded()const{return writeCompleted&&detached;}
    };
    template<bool Enabled,class IO>
    static Result write(const uint8_t* data,size_t length,IO& io){
        if constexpr(!Enabled)return {};
        else {
            if(!data||length!=6||(data[0]&0x7f)==0||(data[0]&0x7f)==8
                ||data[1]!=8||data[2]!=0x1a||data[3]!=0
                ||(data[4]!=0&&(data[4]<5||data[4]>90))||!validChecksum(data))return {};
            return execute(data,length,io);
        }
    }
    // Separate fixed READ boundary. The setpoint writer above still rejects it.
    template<bool Enabled,class IO>
    static Result readConfiguration(const uint8_t* data,size_t length,IO& io){
        if constexpr(!Enabled)return {};
        else {
            if(!data||length!=6||data[0]!=0x0b||data[1]!=0x88||data[3]!=0||!validChecksum(data))return {};
            if(!((data[2]==0x16&&data[4]==2)||(data[2]==0x02&&data[4]==10)))return {};
            return execute(data,length,io);
        }
    }
    // Only a matching finite transaction may request this one-byte completion.
    // This is NOT the legacy/general pong route and has no CRC payload.
    template<bool Enabled,class IO>
    static Result completeTransaction(const uint8_t* data,size_t length,IO& io){
        if constexpr(!Enabled)return {};
        else {
            if(!data||length!=1||data[0]!=0x0b)return {};
            return execute(data,length,io);
        }
    }
private:
    template<class IO>
    static Result execute(const uint8_t* data,size_t length,IO& io){
            // Read-only preflight cannot acquire the pin. Refusal/exception
            // must therefore not run cleanup that would itself alter GPIO.
            try{if(!io.ready())return {};}catch(...){return {};}
            Result result;result.touched=true;
            try{if(io.attach())result.writeCompleted=io.write(data,length);}catch(...){result.writeCompleted=false;}
            // An attachment that reports failure can still have touched the pin.
            try{result.detached=io.detach();}catch(...){result.detached=false;}
            return result;
    }

    static bool validChecksum(const uint8_t* data) {
        // Same EMS recurrence as EmsTelegram's 256-entry lookup table, expressed
        // directly so this SDK boundary needs no logger/vector/parser linkage.
        uint8_t crc=0;
        for(size_t i=0;i<5;++i)
            crc=static_cast<uint8_t>((unsigned(crc)<<1) ^ ((crc&0x80)?0x19u:0u) ^ data[i]);
        return crc==data[5];
    }
};
}
