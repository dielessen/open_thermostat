#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <cstdio>
#include <stdexcept>
struct String : std::string {
    using std::string::string;
    String()=default;
    String(const std::string &s):std::string(s){}
    size_t length() const {return size();}
};
struct IPAddress {
    uint32_t value=0;
    IPAddress()=default;
    IPAddress(uint8_t a,uint8_t b,uint8_t c,uint8_t d):value((a<<24)|(b<<16)|(c<<8)|d){}
    operator uint32_t() const {return value;}
};
inline uint64_t testNow=1000;
inline void delay(unsigned){}
struct {std::string input; int available(){return input.size();} int read(){int c=input[0];input.erase(0,1);return c;} int printf(const char*,...){return 0;}} inline Serial;
struct {uint64_t getEfuseMac(){return 0x123456;} void restart(){throw std::runtime_error("restart");}} inline ESP;
