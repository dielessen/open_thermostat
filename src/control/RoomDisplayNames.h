#pragma once
#include <array>
#include <cstdint>
#include <string_view>

namespace heating::control {
inline constexpr size_t maximumRoomDisplayNameBytes=80;
inline constexpr char roomDisplayNamesCapability[]="display.room_names.v1";
// Control wire remains ASCII without escapes. Human labels travel as bounded
// UTF-8 hex, separately from configuration, observations and actuator intent.
inline bool validRoomDisplayNameHex(std::string_view hex) {
    if(hex.empty()||hex.size()>maximumRoomDisplayNameBytes*2||hex.size()%2)return false;
    auto digit=[](char c)->int {return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;};
    std::array<uint8_t,maximumRoomDisplayNameBytes> bytes{};
    const size_t size=hex.size()/2;
    for(size_t i=0;i<size;++i) {
        const int hi=digit(hex[2*i]),lo=digit(hex[2*i+1]);
        if(hi<0||lo<0)return false;
        bytes[i]=static_cast<uint8_t>((hi<<4)|lo);
    }
    bool visible=false;
    for(size_t i=0;i<size;) {
        uint32_t point=bytes[i++],minimum=0;unsigned tails=0;
        if(point<0x80) {if(point<32||point==127)return false;visible|=point!=' ';continue;}
        if(point>=0xc2&&point<=0xdf){tails=1;minimum=0x80;point&=0x1f;}
        else if(point>=0xe0&&point<=0xef){tails=2;minimum=0x800;point&=0x0f;}
        else if(point>=0xf0&&point<=0xf4){tails=3;minimum=0x10000;point&=7;}
        else return false;
        if(i+tails>size)return false;
        while(tails--) {const auto c=bytes[i++];if((c&0xc0)!=0x80)return false;point=(point<<6)|(c&0x3f);}
        if(point<minimum||point>0x10ffff||(point>=0xd800&&point<=0xdfff))return false;
        visible=true;
    }
    return visible;
}
}
