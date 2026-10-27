#pragma once
#include <cstdint>
class IPAddress {
public:
    explicit IPAddress(uint32_t value=0):value_(value){}
    IPAddress(uint8_t a,uint8_t b,uint8_t c,uint8_t d) {
        auto* bytes=reinterpret_cast<uint8_t*>(&value_);bytes[0]=a;bytes[1]=b;bytes[2]=c;bytes[3]=d;
    }
    operator uint32_t()const{return value_;}
private:uint32_t value_;
};
