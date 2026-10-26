#pragma once
#include "BthomeV2Codec.h"
#include "BleSensorFrame.h"
namespace heating::control {
// SBTR-001AEU documented BTHome declarations only. Temperature instances are
// target, calculated current, optional external, in that order. Neither an
// advertisement nor the packed status revision confirms a command or flow.
// https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/trv/
inline BleSensorFrame decodeShellyTrvService(const uint8_t* service,size_t size) {
    using Status=BleSensorFrameStatus;
    const auto fail=[](Status status){BleSensorFrame r;r.status=status;return r;};
    if(!service||size<2||size>251)return fail(Status::malformed);
    const auto info=service[0];
    if((info&0xe0)!=0x40||(info&0x1a))return fail(Status::malformed);
    if(info&1)return fail(size>=11?Status::key_required:Status::malformed);
    BleSensorFrame r;r.triggerBased=(info&4)!=0;
    unsigned temperatures=0;uint8_t previous=0;bool havePrevious=false;
    for(size_t i=1;i<size;) {
        const auto id=service[i++];
        if(havePrevious&&(id<previous||(id==previous&&id!=0x45)))return fail(Status::malformed);
        previous=id;havePrevious=true;
        if(id==0x45) {
            if(size-i<2||temperatures>=3)return fail(Status::malformed);
            const uint16_t raw=uint16_t(service[i])|(uint16_t(service[i+1])<<8);i+=2;
            const int32_t value=raw<0x8000?int32_t(raw):int32_t(raw)-65536;
            if(value < -400||value>850)return fail(Status::malformed);
            const auto centi=static_cast<int16_t>(value*10);
            if(temperatures==0)r.targetTemperature=centi;
            else if(temperatures==1)r.temperature=centi;
            else r.externalTemperature=centi;
            ++temperatures;
        } else {
            if(i>=size)return fail(Status::malformed);
            const auto value=service[i++];
            switch(id) {
                case 0x00:r.packetId=value;break;
                case 0x01:if(value>100)return fail(Status::malformed);r.battery=value;break;
                // Published hold identifier/example differ; preserve the raw
                // documented forms without executing an event or inferring heat.
                case 0x3a:if(value!=0&&value!=1&&value!=0x80&&value!=0xfe)return fail(Status::malformed);r.button=value;break;
                case 0x54:
                    if(value!=1||i>=size)return fail(Status::malformed);
                    r.stateRevision=service[i++];break;
                default:return fail(Status::malformed);
            }
        }
    }
    // One temperature is ambiguous/incomplete; never label the target as room.
    if(temperatures==1)return fail(Status::malformed);
    r.status=Status::decoded;return r;
}

template<class Decryptor>
BleSensorFrame decodeBoundShellyTrvAdvertisement(const std::array<uint8_t,6>& address,
        const uint8_t* bytes, std::size_t size, const BleBindKey* key, bool requireEncryption,
        Decryptor& decryptor, BthomeWorkspace& workspace) {
    const auto opened = openBthomeV2(address, bytes, size, key, requireEncryption, decryptor, workspace);
    if (opened.status == BthomeOpenStatus::opened) {
        auto result = decodeShellyTrvService(opened.data, opened.size);
        if (result.status == BleSensorFrameStatus::decoded) {
            result.authenticated = opened.authenticated;
            result.encryptionCounter = opened.counter;
        }
        return result;
    }
    BleSensorFrame result;
    switch (opened.status) {
        case BthomeOpenStatus::not_present: result.status = BleSensorFrameStatus::not_present; break;
        case BthomeOpenStatus::key_required: result.status = BleSensorFrameStatus::key_required; break;
        case BthomeOpenStatus::encryption_required: result.status = BleSensorFrameStatus::encryption_required; break;
        case BthomeOpenStatus::authentication_failed: result.status = BleSensorFrameStatus::authentication_failed; break;
        case BthomeOpenStatus::crypto_unavailable: result.status = BleSensorFrameStatus::crypto_unavailable; break;
        default: result.status = BleSensorFrameStatus::malformed; break;
    }
    return result;
}
}
