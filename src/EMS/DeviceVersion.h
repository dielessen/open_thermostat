#pragma once
#include "EmsTelegram.h"

namespace heating::ems {
struct DeviceVersion {
    uint8_t product=0,major=0,minor=0;
    std::optional<uint8_t> brand;
};
// Product/version must come from one complete tuple in the same report, never
// assembled across fragments or inferred from a source address/profile setting.
inline std::optional<DeviceVersion> readDeviceVersion(const EmsTelegram& telegram) {
    if(telegram.getTypeId()!=0x02 || telegram.getOperationType()==EmsTelegram::READ
        || telegram.getOperationType()==EmsTelegram::READ_WITH_DATA)return {};
    auto product=telegram.byteAt(0);
    if(!product)return {};
    const uint8_t start=*product==0?3:0;
    product=telegram.byteAt(start);
    const auto major=telegram.byteAt(start+1),minor=telegram.byteAt(start+2);
    if(!product||!major||!minor||!*product||*product==0xFF||*major==0xFF||*minor==0xFF)return {};
    auto brand=telegram.byteAt(9);
    if(brand&&*brand==0xFF)brand.reset();
    return DeviceVersion{*product,*major,*minor,brand};
}
}
