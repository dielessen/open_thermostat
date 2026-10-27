#pragma once
#include <cstddef>
#include <cstdint>
class Print {
public:
    virtual ~Print()=default;
    virtual size_t write(uint8_t)=0;
    virtual size_t write(const uint8_t* bytes,size_t size){size_t done=0;while(done<size&&write(bytes[done]))++done;return done;}
};
