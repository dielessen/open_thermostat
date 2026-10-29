// Bluetooth device settings fuzzer: the REST /bluetooth flow. Stored settings
// (flash) and the POST body both go through parseControlJson(deviceSettings),
// then readManagedBleBindings / prepareManagedBleSettings, the public and
// committed projections, and the boot path (readManagedBleBindings of the
// saved candidate + ManagedBleObserver::initialize).
//
// Input: [n lo][n hi][n bytes previous settings JSON][request body JSON].
#include "fuzz_common.h"
#include "control/BleDeviceSettings.h"
#include "control/BleObservationJson.h"
#include "control/ManagedBleObserver.h"
#include <cstring>

namespace {
using namespace heating::control;
struct NoCcm {
    BleCcmStatus decrypt(const BleBindKey&, const uint8_t*, std::size_t, const uint8_t*, std::size_t,
            const uint8_t*, std::size_t, const uint8_t*, uint8_t*, std::size_t) { return BleCcmStatus::unavailable; }
    void clear() {}
};
uint64_t clock1() { return 5000; }
std::string print(const cJSON* j) {
    std::unique_ptr<char, decltype(&cJSON_free)> t(cJSON_PrintUnformatted(j), cJSON_free);
    return t ? t.get() : "";
}
void checkBindings(const ManagedBleBindings& b, const char* where) {
    if (b.count > b.capacity) otfuzz::invariant(where);
    for (std::size_t i = 0; i < b.count; ++i)
        if (!validManagedBleBinding(b.devices[i])) otfuzz::invariant(where);
    NoCcm ccm; ManagedBleObserver<NoCcm> observer(ccm, clock1);
    if (!observer.initialize(b)) otfuzz::invariant("accepted Bluetooth bindings refused by the observer at boot");
    for (std::size_t i = 0; i < b.count; ++i) {
        auto row = ControlJson(cJSON_CreateObject(), cJSON_Delete);
        (void)addBleObservation(row.get(), observer.snapshot(b.devices[i].address));
    }
}
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    otfuzz::Reader in(data, size);
    const std::size_t n = in.u16();
    const auto savedText = in.bytes(n);
    const auto body = in.rest();

    auto previous = parseControlJson(savedText, true);
    auto bindings = std::make_unique<ManagedBleBindings>();
    if (previous) {
        const auto stored = readManagedBleBindings(previous.get(), *bindings);
        (void)bleSettingsErrorName(stored);
        if (stored == BleSettingsError::none) {
            checkBindings(*bindings, "stored Bluetooth bindings invalid");
            auto pub = publicManagedBleBindings(*bindings);
            auto committed = committedManagedBleBindings(*bindings);
            if (bindings->count && (!pub || !committed)) otfuzz::invariant("valid bindings could not be projected");
            if (pub) { const auto text = print(pub.get()); if (text.find("\"key\"") != std::string::npos) otfuzz::invariant("bindkey in public projection"); }
        }
        (void)networkSettingsContainManagedBleBindings(previous.get());
        auto copy = ControlJson(cJSON_Duplicate(previous.get(), true), cJSON_Delete);
        if (copy) {
            (void)retainManagedBleSettings(previous.get(), copy.get());
            redactManagedBleSettings(copy.get());
            if (networkSettingsContainManagedBleBindings(copy.get())) otfuzz::invariant("redacted settings still carry bindings");
            (void)retainManagedBleSettings(previous.get(), copy.get());
        }
    }
    if (!previous || !cJSON_IsObject(previous.get())) return 0; // REST answers 503 here

    auto request = parseControlJson(body, true);
    ControlJson candidate(nullptr, cJSON_Delete);
    bool changed = false;
    auto next = std::make_unique<ManagedBleBindings>();
    const auto error = prepareManagedBleSettings(previous.get(), request.get(), *next, candidate, changed);
    (void)bleSettingsErrorName(error);
    if (error != BleSettingsError::none) {
        if (candidate || changed || next->count) otfuzz::invariant("failed Bluetooth settings left a candidate");
        return 0;
    }
    if (!changed) return 0;
    if (!candidate) otfuzz::invariant("changed without candidate");
    // Boot path: the saved candidate must read back to the same bindings.
    const auto encoded = print(candidate.get());
    auto reread = parseControlJson(encoded, true);
    if (!reread) otfuzz::invariant("saved Bluetooth settings are not readable by parseControlJson");
    auto back = std::make_unique<ManagedBleBindings>();
    if (readManagedBleBindings(reread.get(), *back) != BleSettingsError::none) otfuzz::invariant("saved Bluetooth bindings do not read back");
    if (!back->same(*next)) otfuzz::invariant("saved Bluetooth bindings changed on read back");
    checkBindings(*back, "saved Bluetooth bindings invalid");
    return 0;
}
