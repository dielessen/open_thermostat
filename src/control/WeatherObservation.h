#pragma once
#include "Measurement.h"
#include "UtcSchedule.h"
#include <cJSON.h>

namespace heating::control {
// State in the EXISTING OpenWeather owner/mutex, no client, task or storage.
// Current Weather dt is provider calculation time, not proven sensor acquisition.
// A repeated calculation cannot restart this owner's original monotone lifetime.
class WeatherObservation {
public:
    bool receive(const cJSON *root,int64_t utcNow,uint64_t monotonicNow) {
        if(!time(monotonicNow))return false;
        if(utcNow<UtcSchedule::minimumUtcSecond || utcNow>=UtcSchedule::maximumUtcSecond ||
            !cJSON_IsObject(root))return reject();
        const auto main=cJSON_GetObjectItemCaseSensitive(root,"main");
        const auto value=cJSON_GetObjectItemCaseSensitive(main,"temp");
        const auto calculated=cJSON_GetObjectItemCaseSensitive(root,"dt");
        if(!cJSON_IsNumber(value)||!std::isfinite(value->valuedouble)||
            !cJSON_IsNumber(calculated)||!std::isfinite(calculated->valuedouble)||
            calculated->valuedouble<UtcSchedule::minimumUtcSecond||
            calculated->valuedouble>utcNow||std::floor(calculated->valuedouble)!=calculated->valuedouble)
            return reject();
        const auto stamp=static_cast<int64_t>(calculated->valuedouble);
        const auto sourceAge=static_cast<uint64_t>(utcNow-stamp)*1000;
        TemperatureProfile p;
        p.minimumCentiC=-6000;p.maximumCentiC=6000;p.maximumAgeMs=3600000;
        p.acceptsValidatedIntegrationReport=true; // Provider data, not a physical sensor report.
        if(sourceAge>=p.maximumAgeMs||stamp<calculatedAt_)return reject();
        if(stamp==calculatedAt_) {
            if(value->valuedouble!=temperature_||!sample_.value(monotonicNow))return reject();
            const auto age=sample_.age(monotonicNow);
            if(!age)return reject();
            // Forward UTC corrections may shorten the remaining lifetime.
            // Backward UTC corrections and duplicates must never extend it.
            if(sourceAge>*age)
                return sample_.observe(temperature_,TemperatureUnit::celsius,SampleEvidence::validated_integration_report,
                    sourceAge,0,monotonicNow,p);
            return true;
        }
        if(!sample_.observe(value->valuedouble,TemperatureUnit::celsius,SampleEvidence::validated_integration_report,
                sourceAge,0,monotonicNow,p))return false;
        calculatedAt_=stamp;temperature_=value->valuedouble;return true;
    }
    void unavailable(){sample_.unavailable();} // Replay watermark deliberately survives.
    std::optional<int16_t> value(uint64_t now){return time(now)?sample_.value(now):std::nullopt;}
    std::optional<uint64_t> age(uint64_t now){return time(now)?sample_.age(now):std::nullopt;}
private:
    bool reject(){sample_.unavailable();return false;}
    bool time(uint64_t now) {
        if(clockFailed_||(haveTime_&&now<lastNow_)){clockFailed_=true;return reject();}
        haveTime_=true;lastNow_=now;return true;
    }
    TemperatureSample sample_;
    int64_t calculatedAt_=0;
    double temperature_=0;
    uint64_t lastNow_=0;
    bool haveTime_=false,clockFailed_=false;
};
static_assert(sizeof(WeatherObservation)<=128,"Weather receipt state must remain bounded");
inline bool receiveWeatherObservation(WeatherObservation &sample,const cJSON *root,
                                      int64_t utcNow,uint64_t monotonicNow) {
    return sample.receive(root,utcNow,monotonicNow);
}
}
