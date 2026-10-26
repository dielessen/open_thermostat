#pragma once
#include "BleDeviceConfig.h"
#include "BleSensorFrame.h"
#include "BthomeV2Codec.h"
#include <cmath>
#include <cstring>
#include <limits>

namespace heating::control {
// Protocol reference: Bluetooth-Devices/xiaomi-ble parser.py/devices.py.
// Explicit MJWSD05MMC product declarations: 0x2832 / 0x4c47, NOT 0x0b48.
// This decoder is prepared separately; a valid MIC is not acquisition/model
// qualification. No account access, key extraction, GATT or control command.
struct MiBeaconMonitor3Envelope {
    BleSensorFrameStatus status=BleSensorFrameStatus::not_present;
    const uint8_t* ciphertext=nullptr;
    const uint8_t* mic=nullptr;
    std::size_t size=0;
    std::array<uint8_t,12> nonce{};
    uint32_t counter=0;
    uint16_t productId=0;
    uint8_t packetId=0;
};
inline MiBeaconMonitor3Envelope inspectMiBeaconMonitor3(const ManagedBleAddress& address,
        const uint8_t* bytes,std::size_t size) noexcept {
    MiBeaconMonitor3Envelope out;
    const auto service=findBleServiceData(bytes,size,0xfe95);
    if(service.status==BleServiceStatus::absent)return out;
    out.status=BleSensorFrameStatus::malformed;
    if(service.status!=BleServiceStatus::present||service.size<5)return out;
    const auto data=service.data;
    const uint16_t control=uint16_t(data[0])|(uint16_t(data[1])<<8);
    const auto version=control>>12;
    const uint16_t product=uint16_t(data[2])|(uint16_t(data[3])<<8);
    if((version!=4&&version!=5)||(control&0x80)||!(control&0x40)
            || ((control>>10)&3)==3 || (product!=0x2832&&product!=0x4c47))return out;
    std::size_t offset=5;
    if(control&0x10) {
        if(service.size-offset<6)return out;
        for(std::size_t i=0;i<6;++i)if(data[offset+i]!=address[5-i])return out;
        offset+=6;
    }
    if(control&0x20) {
        if(offset==service.size)return out;
        const auto capability=data[offset++];
        if(capability&0x20) {if(offset==service.size)return out;++offset;}
    }
    if(!(control&8)) {out.status=BleSensorFrameStatus::encryption_required;return out;}
    // At least one one-byte object (type2+length1+value1), counter3, MIC4.
    if(service.size-offset<11)return out;
    out.size=service.size-offset-7;
    if(out.size>maximumBleCiphertextBytes)return out;
    out.ciphertext=data+offset;out.mic=data+service.size-4;
    out.productId=product;out.packetId=data[4];
    const auto extension=data+service.size-7;
    out.counter=uint32_t(data[4])|(uint32_t(extension[0])<<8)|(uint32_t(extension[1])<<16)|(uint32_t(extension[2])<<24);
    for(std::size_t i=0;i<6;++i)out.nonce[i]=address[5-i];
    out.nonce[6]=data[2];out.nonce[7]=data[3];out.nonce[8]=data[4];
    for(std::size_t i=0;i<3;++i)out.nonce[9+i]=extension[i];
    out.status=BleSensorFrameStatus::decoded; // Envelope only, NOT yet authenticated.
    return out;
}
inline BleSensorFrame decodeMiBeaconMonitor3Objects(const uint8_t* data,std::size_t size) {
    const auto fail=[] {BleSensorFrame out;out.status=BleSensorFrameStatus::malformed;return out;};
    if(!data||!size||size>maximumBleCiphertextBytes)return fail();
    BleSensorFrame out;
    const auto little=[](const uint8_t* p){return uint16_t(p[0])|(uint16_t(p[1])<<8);};
    const auto temperature=[&](const uint8_t* p) {
        const auto raw=little(p);const int32_t value=raw<0x8000?int32_t(raw):int32_t(raw)-65536;
        if(out.temperature||value < -400||value>850)return false;
        out.temperature=static_cast<int16_t>(value*10);return true;
    };
    const auto humidity=[&](const uint8_t* p) {
        const auto value=little(p);if(out.humidity||value>1000)return false;
        out.humidity=static_cast<int16_t>(value*10);return true;
    };
    const auto floating=[](const uint8_t* p,float low,float high)->std::optional<int16_t> {
        static_assert(sizeof(float)==4&&std::numeric_limits<float>::is_iec559,"MiBeacon needs IEEE binary32");
        const uint32_t bits=uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);
        float value;std::memcpy(&value,&bits,sizeof(value));
        if(!std::isfinite(value)||value<low||value>high)return std::nullopt;
        return static_cast<int16_t>(std::lround(double(value)*100));
    };
    for(std::size_t at=0;at<size;) {
        if(size-at<3)return fail();
        const auto type=little(data+at);const auto length=data[at+2];at+=3;
        if(!length||length>size-at)return fail();
        const auto p=data+at;at+=length;
        switch(type) {
            case 0x1004: if(length!=2||!temperature(p))return fail();break;
            case 0x1006: if(length!=2||!humidity(p))return fail();break;
            case 0x100d: if(length!=4||!temperature(p)||!humidity(p+2))return fail();break;
            case 0x100a: case 0x4c03:
                if(length!=1||out.battery||*p>100)return fail();
                out.battery=*p;break;
            case 0x4c01:
                if(length!=4||out.temperature)return fail();
                out.temperature=floating(p,-40,85);if(!out.temperature)return fail();break;
            case 0x4c02:
                if(length!=1||out.humidity||*p>100)return fail();
                out.humidity=int16_t(*p*100);break;
            case 0x4c08:
                if(length!=4||out.humidity)return fail();
                out.humidity=floating(p,0,100);if(!out.humidity)return fail();break;
            default:return fail(); // Unknown object sizes/meanings never guessed.
        }
    }
    out.status=BleSensorFrameStatus::decoded;return out;
}
template<class Decryptor>
BleSensorFrame decodeBoundMiBeaconMonitor3Advertisement(const ManagedBleAddress& address,
        const uint8_t* bytes,std::size_t size,const BleBindKey* key,
        Decryptor& decryptor,BthomeWorkspace& workspace) {
    const auto fail=[&](BleSensorFrameStatus status) {workspace.plaintext.fill(0);BleSensorFrame out;out.status=status;return out;};
    const auto envelope=inspectMiBeaconMonitor3(address,bytes,size);
    if(envelope.status!=BleSensorFrameStatus::decoded)return fail(envelope.status);
    if(!key)return fail(BleSensorFrameStatus::key_required);
    workspace.plaintext.fill(0);const uint8_t aad=0x11;BleCcmStatus result;
    try {result=decryptor.decrypt(*key,envelope.nonce.data(),envelope.nonce.size(),&aad,1,
        envelope.ciphertext,envelope.size,envelope.mic,workspace.plaintext.data(),workspace.plaintext.size());}
    catch(...){return fail(BleSensorFrameStatus::crypto_unavailable);}
    if(result!=BleCcmStatus::authenticated)return fail(result==BleCcmStatus::authentication_failed?
        BleSensorFrameStatus::authentication_failed:result==BleCcmStatus::invalid_argument?
        BleSensorFrameStatus::malformed:BleSensorFrameStatus::crypto_unavailable);
    auto out=decodeMiBeaconMonitor3Objects(workspace.plaintext.data(),envelope.size);
    if(out.status!=BleSensorFrameStatus::decoded)return fail(out.status);
    out.authenticated=true;out.encryptionCounter=envelope.counter;out.packetId=envelope.packetId;
    out.declaredDeviceType=envelope.productId;return out;
}
}
