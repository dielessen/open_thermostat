#pragma once
#include "ClassicBoilerTestEncoder.h"
#include "ClassicBoilerSettingSpec.h"

namespace heating::ems {

// Independent protocol encoder, deliberately not connected to UART/HTTP.
// Protocol facts: EMS-ESP32 v3.8.6 src/devices/boiler.cpp,
// set_heating_activated/temp, set_burn_period, set_pump_delay.
// These are persistent settings, not the temporary 0x1A trial setpoint.
class ClassicBoilerSettingsEncoder {
public:
    using Setting = ClassicBoilerSettingSpec::Setting;
    using Definition = ClassicBoilerSettingSpec::Definition;
    static constexpr bool definition(Setting setting,Definition& result){
        return ClassicBoilerSettingSpec::definition(setting,result);
    }
    // classicQualified is a caller-owned capability decision, never derived
    // from the selected illustration, reference metadata or absence of EMS+.
    static bool encode(const ClassicBoilerTestEncoder::Addressing& address,
                       bool classicQualified, Setting setting, int value, EmsRawFrame& frame) {
        frame = {};
        Definition spec; uint8_t wire=0;
        if (!classicQualified || !address.valid() || !definition(setting, spec)
            || !ClassicBoilerSettingSpec::wireValue(setting,value,wire)) return false;
        frame.data[0] = address.source | address.sourceMask;
        frame.data[1] = address.boiler;
        frame.data[2] = 0x16;
        frame.data[3] = spec.offset;
        frame.data[4] = wire;
        frame.data[5] = EmsTelegram::calculateCRC(frame.data.data(), 5);
        frame.length = 6;
        return true;
    }
    // Checks only protocol evidence. The transaction owner must separately
    // enforce boot/revision/session, original RX time, deadline and authority.
    // A write echo, broadcast or report to another client is not readback.
    static bool readbackMatches(const ClassicBoilerTestEncoder::Addressing& address,
                                bool classicQualified, Setting setting, int value,
                                const EmsTelegram& report) {
        EmsRawFrame expected;
        if (!encode(address, classicQualified, setting, value, expected)
            || report.getOperationType() != EmsTelegram::WRITE
            || report.getSenderId() != address.boiler
            || report.getDestinationId() != address.source
            || report.getTypeId() != 0x16) return false;
        const auto byte = report.byteAt(expected.data[3]);
        return byte && *byte == expected.data[4];
    }
};
} // namespace heating::ems
