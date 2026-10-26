#pragma once
#include <cstdint>
namespace heating::ems {
// Protocol metadata only. These bounds are not installation approval.
struct ClassicBoilerSettingSpec {
    enum class Setting : uint8_t { heatingActivated, heatingTemperature, burnerMinimumPeriod, pumpDelay };
    struct Definition { const char* entity; uint8_t offset; int minimum,maximum; };
    static constexpr bool definition(Setting setting,Definition& result){
        result={};
        switch(setting){
            case Setting::heatingActivated:result={"heatingactivated",0,0,1};return true;
            case Setting::heatingTemperature:result={"heatingtemp",1,0,90};return true;
            case Setting::burnerMinimumPeriod:result={"burnminperiod",6,0,120};return true;
            case Setting::pumpDelay:result={"pumpdelay",8,0,60};return true;
        }
        return false;
    }
    static constexpr bool wireValue(Setting setting,int value,uint8_t& wire){
        wire=0;Definition spec{};
        if(!definition(setting,spec)||value<spec.minimum||value>spec.maximum)return false;
        wire=setting==Setting::heatingActivated?(value?0xff:0):static_cast<uint8_t>(value);
        return true;
    }
};
}
