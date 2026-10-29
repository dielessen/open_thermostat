// Stateful Bluetooth fuzzer: ManagedBleObserver as HeatingController uses it
// (capture from the scan callback, processOne from the loop, snapshot for the
// room engine / status page), with five bindings covering every profile.
//
// Input: [mode] then records [op][dt][len][len bytes]. mode bit0-1 = fake CCM
// result (see fuzz_ble_advert.cpp), bit2 = real Mbed TLS CCM. op bits0-2 =
// binding index (5..7 = an unbound address), bit3 = processOne afterwards,
// bit4 = snapshot every binding, bit5 = odd RSSI, bits6-7 = clock event
// (1 = frame stamped in the future, 2 = clock steps back, 3 = large jump).
#include "fuzz_common.h"
#include "control/ManagedBleObserver.h"
#include "control/MbedTlsBleCcm.h"
#include <cstring>
#include <stdexcept>

namespace {
using namespace heating::control;
struct FakeCcm {
    int mode = 0;
    BleCcmStatus decrypt(const BleBindKey&, const uint8_t* nonce, std::size_t nonceSize,
            const uint8_t* aad, std::size_t aadSize, const uint8_t* ciphertext,
            std::size_t size, const uint8_t* mic, uint8_t* plaintext, std::size_t capacity) {
        if (!nonce || (nonceSize != 12 && nonceSize != 13) || aadSize > 1 || (aadSize && !aad)
                || !ciphertext || !size || size > maximumBleCiphertextBytes || !mic
                || !plaintext || capacity < size) return BleCcmStatus::invalid_argument;
        volatile uint8_t sink = mic[0] ^ mic[3] ^ nonce[nonceSize - 1];
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
uint64_t clockNow = 1000;
uint64_t readClock() { return clockNow; }

ManagedBleBindings bindings() {
    ManagedBleBindings b;
    const BleBindKey key{0x23,0x1d,0x39,0xc1,0xd7,0xcc,0x1a,0xb1,0xae,0xe2,0x24,0xcd,0x09,0x6d,0xb9,0x32};
    const struct { ManagedBleAddress a; ManagedBleProfile p; ManagedBleEncryption e; bool k; } rows[] = {
        {{0xa4,0xc1,0x38,0xa3,0xe8,0xdb}, ManagedBleProfile::pvvxThermometer, ManagedBleEncryption::plain, false},
        {{0x54,0x48,0xe6,0x8f,0x80,0xa5}, ManagedBleProfile::xiaomiMonitor3, ManagedBleEncryption::miBeaconV4V5, true},
        {{0x54,0x48,0xe6,0x8f,0x80,0xa6}, ManagedBleProfile::shellyHtDisplay, ManagedBleEncryption::bthomeV2, true},
        {{0x3c,0x2e,0xf5,0x00,0x00,0x01}, ManagedBleProfile::shellyTrv, ManagedBleEncryption::plain, false},
        {{0xa4,0xc1,0x38,0x00,0x00,0x02}, ManagedBleProfile::pvvxThermometer, ManagedBleEncryption::bthomeV2, true},
    };
    for (const auto& r : rows) {
        auto& d = b.devices[b.count++];
        d.address = r.a; d.profile = r.p; d.encryption = r.e; d.hasKey = r.k;
        if (r.k) d.key = key;
        std::strcpy(d.name.data(), "fuzz");
    }
    return b;
}

template<class Ccm>
void run(Ccm& ccm, otfuzz::Reader& in) {
    clockNow = 1000;
    ManagedBleObserver<Ccm> observer(ccm, readClock);
    const auto b = bindings();
    if (!observer.initialize(b)) otfuzz::invariant("valid fixed bindings refused");
    uint64_t at = clockNow;
    for (unsigned r = 0; !in.empty() && r < 64; ++r) {
        const uint8_t op = in.u8(), dt = in.u8(), len = in.u8();
        const auto bytes = in.bytes(len);
        clockNow += uint64_t(dt) * 1000;
        at = clockNow;
        switch (op >> 6) {
            case 1: at = clockNow + 5; break;
            case 2: clockNow -= std::min<uint64_t>(clockNow, 7); break;
            case 3: clockNow += 1000000; break;
        }
        const std::size_t index = op & 7;
        ManagedBleAddress address = index < b.count ? b.devices[index].address : ManagedBleAddress{1, 2, 3, 4, 5, uint8_t(index)};
        observer.capture(address, (op & 0x20) ? 99 : -60, reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size(), at);
        if (op & 0x08) observer.processOne(false);
        if (op & 0x10) for (std::size_t i = 0; i < b.count; ++i) {
            const auto s = observer.snapshot(b.devices[i].address);
            if (s.temperature && (*s.temperature < -4000 || *s.temperature > 8500)) otfuzz::invariant("snapshot temperature out of range");
            if (s.humidity && (*s.humidity < 0 || *s.humidity > 10000)) otfuzz::invariant("snapshot humidity out of range");
            if (s.battery && *s.battery > 100) otfuzz::invariant("snapshot battery out of range");
        }
    }
    for (int i = 0; i < 4; ++i) observer.processOne(false);
    for (std::size_t i = 0; i < b.count; ++i) (void)observer.snapshot(b.devices[i].address);
    (void)observer.queueDrops();
}
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    static MbedTlsBleCcm real;
    otfuzz::Reader in(data, size);
    const uint8_t mode = in.u8();
    if (mode & 4) run(real, in);
    else { FakeCcm fake{mode & 3}; run(fake, in); }
    return 0;
}
