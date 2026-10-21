#pragma once
#include "ZoneRegulator.h"
#include <array>
#include <functional>
#include <string>
#include <string_view>

namespace heating::control {
// Reviewed SOURCE bundle, never decoded from config/telemetry/GUI. Qualifies only
// logical SHADOW policy selection, not physical source/protection/readiness.
struct SeasonalZoneSource {
    std::string zoneId,sensorId,actuatorId;
    ZoneControlProfile control;
    SeasonalProfile seasonal;
};
struct SeasonalSafetySnapshot {
    uint64_t sampledAt=0;
    bool limitsKnownSafe=false,dhwStateKnown=false,dhwActive=false;
    bool summer=false,allOff=false,preempted=false;
};
struct SeasonalControllerSource {
    std::string controllerId,configDigest;
    std::array<SeasonalZoneSource,8> zones;
    size_t count=0;
    uint32_t maximumSafetyAgeMs=0;
    using Safety=std::function<SeasonalSafetySnapshot()>;
    bool valid() const {
        if(controllerId.empty()||controllerId.size()>64||configDigest.size()!=64
            ||!count||count>zones.size()||maximumSafetyAgeMs<1000||maximumSafetyAgeMs>120000)return false;
        for(char ch:configDigest)if(!((ch>='0'&&ch<='9')||(ch>='a'&&ch<='f')))return false;
        for(size_t i=0;i<count;++i) {
            const auto& z=zones[i];
            if(z.zoneId.size()!=8||z.sensorId.empty()||z.sensorId.size()>64||z.actuatorId.size()>64
                ||!z.control.valid()||!z.seasonal.valid())return false;
            for(char ch:z.zoneId)if(!((ch>='0'&&ch<='9')||(ch>='a'&&ch<='f')))return false;
            for(size_t j=0;j<i;++j)if(z.zoneId==zones[j].zoneId)return false;
        }
        return true;
    }
    const SeasonalZoneSource* zone(std::string_view id) const {
        for(size_t i=0;i<count;++i)if(zones[i].zoneId==id)return &zones[i];
        return nullptr;
    }
};
}
