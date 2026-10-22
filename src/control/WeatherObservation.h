#pragma once
#include "Measurement.h"
#include "UtcSchedule.h"
#include <cJSON.h>

namespace heating::control {
// OpenWeather's dt is the observation time, NOT HTTP arrival time. The reader
// must not turn a repeated cached response into a new physical observation.
inline bool receiveWeatherObservation(TemperatureSample &sample, const cJSON *root,
                                      int64_t utcNow, uint64_t monotonicNow) {
    sample.unavailable();
    if (utcNow < UtcSchedule::minimumUtcSecond || utcNow >= UtcSchedule::maximumUtcSecond ||
        !cJSON_IsObject(root)) return false;
    auto main=cJSON_GetObjectItemCaseSensitive(root,"main");
    auto value=cJSON_GetObjectItemCaseSensitive(main,"temp");
    auto observed=cJSON_GetObjectItemCaseSensitive(root,"dt");
    if (!cJSON_IsNumber(value) || !std::isfinite(value->valuedouble) || !cJSON_IsNumber(observed) ||
        !std::isfinite(observed->valuedouble) || observed->valuedouble < UtcSchedule::minimumUtcSecond ||
        observed->valuedouble > utcNow || std::floor(observed->valuedouble) != observed->valuedouble) return false;
    TemperatureProfile p;
    p.minimumCentiC=-6000; p.maximumCentiC=6000; p.maximumAgeMs=3600000;
    const auto sourceAge=static_cast<uint64_t>(utcNow-static_cast<int64_t>(observed->valuedouble))*1000;
    return sample.observe(value->valuedouble, TemperatureUnit::celsius, SampleEvidence::physical_report,
                          sourceAge,0,monotonicNow,p);
}
}
