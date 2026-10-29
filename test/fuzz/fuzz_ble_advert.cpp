// Bluetooth advertisement fuzzer: every decoder the E32 runs on a received
// advertisement (legacy ATC/MJ_HT_V1, BTHome v2 plain + encrypted, pvvx custom,
// Shelly H&T / BLU TRV, Xiaomi MiBeacon v4/v5) plus the discovery name hints.
//
// Input: [flags][address 6, display order][advertisement AD bytes...].
// flags bit0-1: fake CCM result (0 authenticated + copy-through plaintext,
// 1 authentication_failed, 2 invalid_argument, 3 throws), bit2: real Mbed TLS
// CCM with the public BTHome test key instead of the fake, bit3: encryption
// required, bit4: no bindkey, bits5-7: RSSI.
#include "fuzz_common.h"
#include "control/BleDeviceDiscovery.h"
#include "control/BleTemperatureAdvertisement.h"
#include "control/BthomeV2Codec.h"
#include "control/MbedTlsBleCcm.h"
#include "control/MiBeaconMonitor3Advertisement.h"
#include "control/PvvxAdvertisement.h"
#include "control/ShellyHtDisplayAdvertisement.h"
#include "control/ShellyTrvAdvertisement.h"
#include <cJSON.h>
#include <algorithm>
#include <cstring>
#include <memory>
#include <sstream>
#include <stdexcept>

namespace {
using namespace heating::control;

// Same contract checks as MbedTlsBleCcm, so the fake cannot hide a caller bug.
struct FakeCcm {
    int mode = 0;
    BleCcmStatus decrypt(const BleBindKey&, const uint8_t* nonce, std::size_t nonceSize,
            const uint8_t* aad, std::size_t aadSize, const uint8_t* ciphertext,
            std::size_t size, const uint8_t* mic, uint8_t* plaintext, std::size_t capacity) {
        if (!nonce || (nonceSize != 12 && nonceSize != 13) || aadSize > 1 || (aadSize && !aad)
                || !ciphertext || !size || size > maximumBleCiphertextBytes || !mic
                || !plaintext || capacity < size) return BleCcmStatus::invalid_argument;
        // Touch every byte the real implementation reads (ASan checks the bounds).
        volatile uint8_t sink = 0;
        for (std::size_t i = 0; i < nonceSize; ++i) sink ^= nonce[i];
        for (std::size_t i = 0; i < 4; ++i) sink ^= mic[i];
        for (std::size_t i = 0; i < aadSize; ++i) sink ^= aad[i];
        (void)sink;
        switch (mode) {
            case 0: std::memcpy(plaintext, ciphertext, size); return BleCcmStatus::authenticated;
            case 1: return BleCcmStatus::authentication_failed;
            case 2: return BleCcmStatus::invalid_argument;
            default: throw std::runtime_error("crypto");
        }
    }
    void clear() {}
};

const BleBindKey testKey{0x23,0x1d,0x39,0xc1,0xd7,0xcc,0x1a,0xb1,0xae,0xe2,0x24,0xcd,0x09,0x6d,0xb9,0x32};

bool inside(const uint8_t* p, std::size_t n, const void* lo, std::size_t span) {
    const auto* b = static_cast<const uint8_t*>(lo);
    return p >= b && p + n <= b + span;
}
void checkClosed(const BthomeWorkspace& w) {
    if (!std::all_of(w.plaintext.begin(), w.plaintext.end(), [](uint8_t b) { return !b; }))
        otfuzz::invariant("failed BLE decryption left plaintext in the workspace");
}
void use(const BleSensorFrame& f) {
    // Read every field so uninitialised/narrowed values reach UBSan.
    volatile int sink = int(f.status) + f.triggerBased + f.authenticated;
    if (f.temperature) sink += *f.temperature;
    if (f.humidity) sink += *f.humidity;
    if (f.battery) sink += *f.battery;
    if (f.encryptionCounter) sink += int(*f.encryptionCounter);
    (void)sink;
    if (f.status == BleSensorFrameStatus::decoded) {
        if (f.temperature && (*f.temperature < -4000 || *f.temperature > 8500)) otfuzz::invariant("temperature out of range");
        if (f.humidity && (*f.humidity < 0 || *f.humidity > 10000)) otfuzz::invariant("humidity out of range");
        if (f.battery && *f.battery > 100) otfuzz::invariant("battery out of range");
    }
}

template<class Ccm>
void decodeAll(const std::array<uint8_t, 6>& address, const uint8_t* bytes, std::size_t size,
               const BleBindKey* key, bool require, Ccm& ccm) {
    BthomeWorkspace w;
    const auto opened = openBthomeV2(address, bytes, size, key, require, ccm, w);
    if (opened.status == BthomeOpenStatus::opened) {
        if (!opened.data || !(inside(opened.data, opened.size, bytes, size)
                || inside(opened.data, opened.size, w.plaintext.data(), w.plaintext.size())))
            otfuzz::invariant("opened BTHome view outside its buffers");
        use(decodeBthomeThermometerService(opened.data, opened.size));
        use(decodeShellyHtDisplayService(opened.data, opened.size));
        use(decodeShellyTrvService(opened.data, opened.size));
    } else {
        if (opened.data || opened.size) otfuzz::invariant("closed BTHome result exposes data");
        checkClosed(w);
    }
    { BthomeWorkspace v; use(decodeBoundPvvxAdvertisement(address, bytes, size, key, require, ccm, v)); }
    { BthomeWorkspace v; use(decodeBoundShellyHtDisplayAdvertisement(address, bytes, size, key, require, ccm, v)); }
    { BthomeWorkspace v; use(decodeBoundShellyTrvAdvertisement(address, bytes, size, key, require, ccm, v)); }
    { BthomeWorkspace v; auto f = decodeBoundMiBeaconMonitor3Advertisement(address, bytes, size, key, ccm, v); use(f);
      if (f.status != BleSensorFrameStatus::decoded) checkClosed(v); }
}
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    static MbedTlsBleCcm real;
    if (size < 7) return 0;
    const uint8_t flags = data[0];
    std::array<uint8_t, 6> address{};
    std::copy_n(data + 1, 6, address.begin());
    // Exact-size heap copy: any read past the advertisement is an ASan error.
    const std::size_t n = size - 7;
    std::unique_ptr<uint8_t[]> owned(new uint8_t[n ? n : 1]);
    std::copy_n(data + 7, n, owned.get());
    const uint8_t* bytes = n ? owned.get() : nullptr;

    (void)decodeBleTemperatureAdvertisement(address, bytes, n);
    for (uint16_t uuid : {uint16_t(0xfcd2), uint16_t(0x181a), uint16_t(0xfe95), uint16_t(0x0000)}) {
        const auto s = findBleServiceData(bytes, n, uuid);
        if (s.status == BleServiceStatus::present && !inside(s.data, s.size, bytes, n))
            otfuzz::invariant("service data view outside the advertisement");
        if (s.status == BleServiceStatus::present) {
            use(decodeBthomeThermometerService(s.data, s.size));
            use(decodePvvxCustomService(address, s.data, s.size));
            use(decodeShellyHtDisplayService(s.data, s.size));
            use(decodeShellyTrvService(s.data, s.size));
            use(decodeMiBeaconMonitor3Objects(s.data, s.size));
        }
    }
    use(decodeShellyHtDisplayAdvertisement(bytes, n));
    (void)inspectMiBeaconMonitor3(address, bytes, n);
    use(decodeMiBeaconMonitor3Objects(bytes, n));

    const BleBindKey* key = (flags & 0x10) ? nullptr : &testKey;
    const bool require = flags & 0x08;
    if (flags & 0x04) decodeAll(address, bytes, n, key, require, real);
    else { FakeCcm fake{flags & 3}; decodeAll(address, bytes, n, key, require, fake); }

    // Discovery hints: name extraction and the status JSON built from it.
    static const int rssis[8] = {-127, -128, -90, -40, 0, 20, 21, 1000};
    BleDeviceDiscovery discovery;
    discovery.remember(address, rssis[flags >> 5], bytes, n);
    auto other = address; other[5] ^= 1;
    discovery.remember(other, -50, bytes, n);
    discovery.remember(address, -30, bytes, n); // update path
    std::ostringstream out; out << '{'; discovery.writeJson(out); out << '}';
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> json(cJSON_Parse(out.str().c_str()), cJSON_Delete);
    if (!json) otfuzz::invariant("BLE discovery status is not valid JSON");
    for (std::size_t i = 0; i < discovery.size(); ++i) {
        const auto& name = discovery.hint(i).name;
        if (std::find(name.begin(), name.end(), '\0') == name.end()) otfuzz::invariant("unterminated BLE name hint");
    }
    // Text forms of the same bytes as an address / bindkey (settings parsers).
    ManagedBleAddress parsed{}; BleBindKey parsedKey{};
    const std::string_view text(reinterpret_cast<const char*>(data + 7), n);
    (void)parseManagedBleAddress(text, parsed);
    (void)parseBleHex(text, parsedKey);
    (void)validManagedBleName(text.substr(0, 64));
    return 0;
}
