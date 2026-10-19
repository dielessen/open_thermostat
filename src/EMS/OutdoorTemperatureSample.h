#pragma once
#include "EmsTelegram.h"
#include "control/Measurement.h"

namespace heating::ems {
// Observed boiler report only. This does not commission Classic/Plus writes.
inline void receiveOutdoorTemperature(control::TemperatureSample &sample, const EmsTelegram &telegram, uint64_t now) {
    if (telegram.getSenderId() != 8 || telegram.getOperationType() == EmsTelegram::READ ||
        telegram.getOperationType() == EmsTelegram::READ_WITH_DATA ||
        (telegram.getTypeId() != 0x19 && telegram.getTypeId() != 0xD1)) return;
    const auto word=telegram.wordAt(0);
    if (!word) return; // An unrelated fragment must not renew or destroy this field.
    if (*word == 0x8000 || *word == 0x7FFF) { sample.unavailable(); return; }
    control::TemperatureProfile p;
    p.minimumCentiC=-6000; p.maximumCentiC=6000; p.maximumAgeMs=180000;
    sample.observe(static_cast<int16_t>(*word)/10.0, control::TemperatureUnit::celsius,
                   control::SampleEvidence::physical_report,0,0,now,p);
}
}
