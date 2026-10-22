#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace heating::control {

struct BleTemperatureReport {
    std::optional<int16_t> temperature, humidity; // hundredths C / percent
    std::optional<int8_t> battery; // percent
};

// Legacy supported profiles only: ATC custom (181A), unencrypted MJ_HT_V1
// (FE95, product 01AA, MAC present, one object, no capability extension).
// An advertisement/counter is NOT proof of a new physical measurement.
// The caller supplies the advertiser address in conventional display order.
inline std::optional<BleTemperatureReport> decodeBleTemperatureAdvertisement(
        const std::array<uint8_t,6> &address, const uint8_t *bytes, std::size_t size) {
    if (!bytes || !size || size > 255) return {};
    std::string_view name;
    // Validate the ENTIRE AD container before inspecting or delivering a sample.
    // A zero length terminates the container; only zero padding may follow.
    for (std::size_t i=0; i<size;) {
        const auto length=bytes[i++];
        if (!length) {
            while (i<size) if (bytes[i++]) return {};
            break;
        }
        if (length > size-i) return {};
        if (bytes[i]==0x08 || bytes[i]==0x09) {
            const std::string_view candidate(reinterpret_cast<const char*>(bytes+i+1),length-1);
            if (!name.empty() && name != candidate) return {}; // ambiguous identity
            name=candidate;
        }
        i+=length;
    }
    const bool atc=name.size()>4 && name.substr(0,4)=="ATC_";
    if (!atc && name!="MJ_HT_V1") return {};
    const uint16_t wantedUuid=atc ? 0x181a : 0xfe95;
    const uint8_t *data=nullptr;
    std::size_t length=0;
    for (std::size_t i=0; i<size;) {
        const auto adLength=bytes[i++];
        if (!adLength) break;
        if (bytes[i]==0x16) {
            if (adLength<3) return {}; // type plus complete 16-bit service UUID
            const uint16_t uuid=bytes[i+1] | (uint16_t(bytes[i+2])<<8);
            if (uuid==wantedUuid) {
                if (data) return {}; // never choose arbitrarily between two samples
                data=bytes+i+3; length=adLength-3;
            }
        }
        i+=adLength;
    }
    if (!data) return {};
    BleTemperatureReport result;
    const auto temperature=[&](uint16_t raw) {
        // Convert signed wire value explicitly before multiplying/narrowing.
        const int32_t signedValue=raw<0x8000 ? int32_t(raw) : int32_t(raw)-65536;
        if (signedValue < -400 || signedValue > 850) return false;
        result.temperature=static_cast<int16_t>(signedValue*10);
        return true;
    };
    const auto humidity=[&](uint16_t raw) {
        if (raw>1000) return false;
        result.humidity=static_cast<int16_t>(raw*10);
        return true;
    };
    const auto le=[](const uint8_t *p)->uint16_t { return p[0] | (uint16_t(p[1])<<8); };
    if (atc) {
        if (length!=13) return {}; // MAC6, temp2 BE, RH1, battery1, mV2, counter1
        for (std::size_t i=0;i<6;++i) if (data[i]!=address[i]) return {};
        if (!temperature((uint16_t(data[6])<<8)|data[7]) || data[8]>100 || data[9]>100) return {};
        result.humidity=static_cast<int16_t>(data[8]*100);
        result.battery=static_cast<int8_t>(data[9]);
    } else {
        if (length<14 || (data[0]&0x78)!=0x50 || le(data+2)!=0x01aa) return {};
        for (std::size_t i=0;i<6;++i) if (data[5+i]!=address[5-i]) return {};
        if (data[13]!=length-14) return {}; // one complete, exact-length object
        switch (le(data+11)) {
            case 0x1004:
                if (data[13]!=2 || !temperature(le(data+14))) return {};
                break;
            case 0x1006:
                if (data[13]!=2 || !humidity(le(data+14))) return {};
                break;
            case 0x100a:
                if (data[13]!=1 || data[14]>100) return {};
                result.battery=static_cast<int8_t>(data[14]);
                break;
            case 0x100d:
                if (data[13]!=4 || !temperature(le(data+14)) || !humidity(le(data+16))) return {};
                break;
            default: return {};
        }
    }
    return result;
}
}
