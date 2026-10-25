#pragma once
#include <cstddef>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class ShellyHtFrameStatus { not_present, malformed, key_required, decoded };

// Prepared SBHT-103C wire subset, NOT selected by the normal BLE reader.
// No state/cache, address binding, replay/authentication or acquisition proof.
// Even F0 is a broadcast declaration, not authenticated device identity.
struct ShellyHtDisplayFrame {
    ShellyHtFrameStatus status = ShellyHtFrameStatus::not_present;
    bool triggerBased = false;
    std::optional<uint8_t> packetId, battery, lightLevel, button;
    std::optional<bool> batteryLow, light;
    std::optional<int16_t> temperature, humidity; // hundredths C / percent
    std::optional<uint16_t> declaredDeviceType;
    std::optional<uint32_t> firmware32, firmware24; // raw separate declarations
};

// Entire BLE AD container, including the 16-bit FCD2 service UUID. Local names
// are never used as model evidence. No partial data returned on parse failure.
inline ShellyHtDisplayFrame decodeShellyHtDisplayAdvertisement(const uint8_t* bytes, std::size_t size) {
    using Status = ShellyHtFrameStatus;
    const auto failure=[](Status status) { ShellyHtDisplayFrame r; r.status=status; return r; };
    if (!bytes || !size || size>255) return failure(Status::malformed);
    const uint8_t* service=nullptr;
    std::size_t serviceSize=0;
    for (std::size_t i=0; i<size;) {
        const auto length=bytes[i++];
        if (!length) {
            while (i<size) if (bytes[i++]) return failure(Status::malformed);
            break;
        }
        if (length>size-i) return failure(Status::malformed);
        if (bytes[i]==0x16) {
            if (length<3) return failure(Status::malformed);
            if (bytes[i+1]==0xd2 && bytes[i+2]==0xfc) {
                if (service) return failure(Status::malformed);
                service=bytes+i+3; serviceSize=length-3;
            }
        }
        i+=length;
    }
    if (!service) return {};
    if (serviceSize<2) return failure(Status::malformed);
    const auto info=service[0];
    // Version2, no reserved bits. Trigger flag is descriptive, not freshness.
    if ((info&0xe0)!=0x40 || (info&0x1a)) return failure(Status::malformed);
    if (info&1) {
        // Minimum object (2), counter (4), MIC (4), plus info. We cannot
        // authenticate ciphertext here; return no measurements or identity.
        return failure(serviceSize>=11 ? Status::key_required : Status::malformed);
    }
    ShellyHtDisplayFrame result;
    result.triggerBased=(info&4)!=0;
    const auto le=[](const uint8_t* p, std::size_t n) {
        uint32_t value=0;
        for (std::size_t i=0;i<n;++i) value|=uint32_t(p[i])<<(i*8);
        return value;
    };
    uint8_t previous=0;
    bool havePrevious=false;
    for (std::size_t i=1; i<serviceSize;) {
        const auto id=service[i++];
        // This device has one value per supported property. Never choose
        // arbitrarily between duplicates, and enforce BTHome object ordering.
        if (havePrevious && id<=previous) return failure(Status::malformed);
        previous=id; havePrevious=true;
        std::size_t length;
        switch (id) {
            case 0x00: case 0x01: case 0x15: case 0x1e: case 0x2e: case 0x3a: case 0x64: length=1; break;
            case 0x45: case 0xf0: length=2; break;
            case 0xf1: length=4; break;
            case 0xf2: length=3; break;
            default: return failure(Status::malformed); // no guessed object lengths
        }
        if (length>serviceSize-i) return failure(Status::malformed);
        const auto value=le(service+i,length); i+=length;
        switch (id) {
            case 0x00: result.packetId=static_cast<uint8_t>(value); break;
            case 0x01:
                if (value>100) return failure(Status::malformed);
                result.battery=static_cast<uint8_t>(value); break;
            case 0x15: case 0x1e:
                if (value>1) return failure(Status::malformed);
                (id==0x15 ? result.batteryLow : result.light)=value==1; break;
            case 0x2e:
                if (value>100) return failure(Status::malformed);
                result.humidity=static_cast<int16_t>(value*100); break;
            case 0x3a:
                if (value>1) return failure(Status::malformed); // documented single press / none
                result.button=static_cast<uint8_t>(value); break;
            case 0x45: {
                const int32_t signedValue=value<0x8000 ? int32_t(value) : int32_t(value)-65536;
                // Project diagnostic temperature bounds; check before narrowing.
                if (signedValue < -400 || signedValue>850) return failure(Status::malformed);
                result.temperature=static_cast<int16_t>(signedValue*10); break;
            }
            case 0x64:
                if (value>2) return failure(Status::malformed);
                result.lightLevel=static_cast<uint8_t>(value); break;
            case 0xf0:
                if (value!=0x000c) return failure(Status::malformed); // no other Shelly profile
                result.declaredDeviceType=static_cast<uint16_t>(value); break;
            case 0xf1: result.firmware32=value; break;
            case 0xf2: result.firmware24=value; break;
        }
    }
    result.status=Status::decoded;
    return result;
}
}
