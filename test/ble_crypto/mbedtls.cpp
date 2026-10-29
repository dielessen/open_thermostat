// Real Mbed TLS, public BTHome vector + independent Python AESCCM fixtures.
// No radio, credentials, device commands or physical acquisition qualification.
#include "control/BthomeV2Codec.h"
#include "control/ManagedBleObserver.h"
#include "control/MbedTlsBleCcm.h"
#include "control/ShellyHtDisplayAdvertisement.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace { bool failCryptoAllocation = false; unsigned failedCryptoAllocations = 0; }
extern "C" void* __real_calloc(std::size_t, std::size_t);
extern "C" void* __wrap_calloc(std::size_t count, std::size_t size) {
    if (failCryptoAllocation) { ++failedCryptoAllocations; return nullptr; }
    return __real_calloc(count, size);
}

namespace {
using namespace heating::control;
using Bytes = std::vector<uint8_t>;
Bytes hex(const std::string& text) {
    Bytes out;
    for (std::size_t i = 0; i < text.size(); i += 2)
        out.push_back(static_cast<uint8_t>(std::stoul(text.substr(i, 2), nullptr, 16)));
    return out;
}
Bytes packet(const Bytes& service) {
    Bytes out{static_cast<uint8_t>(service.size() + 1), 0x16};
    out.insert(out.end(), service.begin(), service.end()); return out;
}
struct Fixture {
    std::array<uint8_t, 6> address{0x54,0x48,0xe6,0x8f,0x80,0xa5};
    BleBindKey key{};
    BthomeWorkspace workspace;
    MbedTlsBleCcm cipher;
    Bytes bytes = packet(hex("d2fc41e445f3c9962b332211006c7c4519"));
    Fixture() {
        const auto data = hex("231d39c1d7cc1ab1aee224cd096db932");
        std::copy(data.begin(), data.end(), key.begin());
    }
    auto open() { return openBthomeV2(address, bytes.data(), bytes.size(), &key, true, cipher, workspace); }
    void closed(const BthomeOpenedService& result) {
        EXPECT_NE(result.status, BthomeOpenStatus::opened);
        EXPECT_EQ(result.data, nullptr); EXPECT_EQ(result.size, 0u);
        EXPECT_FALSE(result.counter); EXPECT_FALSE(result.authenticated);
        EXPECT_TRUE(std::all_of(workspace.plaintext.begin(), workspace.plaintext.end(), [](auto b){return !b;}));
    }
};
TEST(BleCrypto, OfficialBthomeVectorUsesDisplayOrderMacAndNoLegacyAad) {
    Fixture f; const auto result = f.open();
    ASSERT_EQ(result.status, BthomeOpenStatus::opened); ASSERT_TRUE(result.authenticated);
    EXPECT_EQ(result.counter, 1122867u);
    EXPECT_EQ(Bytes(result.data, result.data + result.size), hex("4002ca0903bf13"));
}
TEST(BleCrypto, IncorrectKeyAndAddressExposeNoPlaintextAndDoNotPoisonNextPacket) {
    Fixture f; f.key[0] ^= 1; f.workspace.plaintext.fill(0xa5);
    auto result = f.open(); EXPECT_EQ(result.status, BthomeOpenStatus::authentication_failed); f.closed(result);
    f.key[0] ^= 1; std::reverse(f.address.begin(), f.address.end());
    result = f.open(); EXPECT_EQ(result.status, BthomeOpenStatus::authentication_failed); f.closed(result);
    std::reverse(f.address.begin(), f.address.end()); EXPECT_EQ(f.open().status, BthomeOpenStatus::opened);
}
TEST(BleCrypto, EveryCiphertextCounterMicAndAuthenticatedInfoMutationIsRejected) {
    Fixture f;
    for (std::size_t i = 4; i < f.bytes.size(); ++i) {
        f.bytes[i] ^= i == 4 ? 4 : 1;
        const auto result = f.open(); EXPECT_EQ(result.status, BthomeOpenStatus::authentication_failed) << i; f.closed(result);
        f.bytes[i] ^= i == 4 ? 4 : 1;
    }
}
TEST(BleCrypto, EveryContainerTruncationAndInvalidSuffixProducesNoPartialResult) {
    Fixture f;
    for (std::size_t n = 0; n < f.bytes.size(); ++n)
        f.closed(openBthomeV2(f.address, f.bytes.data(), n, &f.key, true, f.cipher, f.workspace));
    f.bytes.insert(f.bytes.end(), {7,0x16,0xd2}); f.closed(f.open());
}
TEST(BleCrypto, MissingKeyNeverAttemptsAuthenticationOrReturnsCounter) {
    Fixture f; f.workspace.plaintext.fill(0xa5);
    const auto result = openBthomeV2(f.address, f.bytes.data(), f.bytes.size(), nullptr, true, f.cipher, f.workspace);
    EXPECT_EQ(result.status, BthomeOpenStatus::key_required); f.closed(result);
}
TEST(BleCrypto, PlaintextCannotDowngradeAnEncryptedBinding) {
    Fixture f; f.bytes = packet(hex("d2fc400164452a00"));
    auto result = f.open(); EXPECT_EQ(result.status, BthomeOpenStatus::encryption_required); f.closed(result);
    result = openBthomeV2(f.address, f.bytes.data(), f.bytes.size(), nullptr, false, f.cipher, f.workspace);
    ASSERT_EQ(result.status, BthomeOpenStatus::opened); EXPECT_FALSE(result.authenticated); EXPECT_FALSE(result.counter);
    EXPECT_EQ(Bytes(result.data, result.data + result.size), hex("400164452a00"));
}
TEST(BleCrypto, DuplicateServiceAndNonzeroBytesAfterTerminatorAreRejectedBeforeOpening) {
    Fixture f; const auto original = f.bytes;
    f.bytes.insert(f.bytes.end(), original.begin(), original.end()); f.closed(f.open());
    f.bytes = original; f.bytes.insert(f.bytes.end(), {0,0,1}); f.closed(f.open());
    f.bytes = original; f.bytes.insert(f.bytes.end(), {0,0}); EXPECT_EQ(f.open().status, BthomeOpenStatus::opened);
}
TEST(BleCrypto, IndependentShellyFixturesCoverZeroNormalAndMaximumCounterWithoutNarrowing) {
    Fixture f;
    const std::vector<std::pair<uint32_t,std::string>> cases{
        {0,"d2fc41dc8cbd69cd75c264f0af4bc93b8686000000006f90f59e"},
        {1122868,"d2fc413c5e24a0bd4c72a7e0f33fdba22cb534221100920226c2"},
        {UINT32_MAX,"d2fc41b8c1b81d44e534ecee7b377b471cdfffffffff398e7fc5"}};
    for (const auto& value : cases) {
        f.bytes = packet(hex(value.second)); const auto result = f.open();
        ASSERT_EQ(result.status, BthomeOpenStatus::opened);
        EXPECT_EQ(result.counter, value.first);
        EXPECT_EQ(Bytes(result.data, result.data + result.size), hex("400007016415001e012e2d45eb006402"));
    }
}
TEST(BleCrypto, LegacyAadDoesNotAuthenticateTheV2Vector) {
    Fixture f; const auto service = hex("d2fc41e445f3c9962b332211006c7c4519");
    const auto nonce = hex("5448e68f80a5d2fc4133221100");
    std::array<uint8_t,6> out{}; const uint8_t aad = 0x11;
    EXPECT_EQ(f.cipher.decrypt(f.key, nonce.data(), nonce.size(), &aad, 1,
        service.data() + 3, 6, service.data() + service.size() - 4, out.data(), out.size()), BleCcmStatus::authentication_failed);
    EXPECT_EQ(f.open().status, BthomeOpenStatus::opened);
}
TEST(BleCrypto, InvalidCryptoArgumentsDoNotWritePastTheSuppliedOutput) {
    Fixture f; const auto nonce = hex("5448e68f80a5d2fc4133221100");
    std::array<uint8_t,3> out{1,2,3}; const std::array<uint8_t,4> mic{};
    EXPECT_EQ(f.cipher.decrypt(f.key, nonce.data(), nonce.size(), nullptr, 0,
        f.bytes.data(), 4, mic.data(), out.data(), out.size()), BleCcmStatus::invalid_argument);
    EXPECT_EQ(out, (std::array<uint8_t,3>{1,2,3}));
}
TEST(BleCrypto, CryptoFailureAndExceptionClearPreviousWorkspace) {
    struct Throw { BleCcmStatus decrypt(const BleBindKey&,const uint8_t*,std::size_t,
        const uint8_t*,std::size_t,const uint8_t*,std::size_t,const uint8_t*,uint8_t*,std::size_t) {throw std::runtime_error("fixture");} } throwing;
    Fixture f; ASSERT_EQ(f.open().status, BthomeOpenStatus::opened);
    const auto result = openBthomeV2(f.address, f.bytes.data(), f.bytes.size(), &f.key, true, throwing, f.workspace);
    EXPECT_EQ(result.status, BthomeOpenStatus::crypto_unavailable); f.closed(result);
}
TEST(BleCrypto, BoundedRandomContainersCannotYieldUnboundedViewsOrStaleFailureData) {
    Fixture f; std::mt19937 random(5011);
    for (unsigned test = 0; test < 10000; ++test) {
        Bytes bytes(random() % 257); for (auto& byte : bytes) byte = static_cast<uint8_t>(random());
        const auto result = openBthomeV2(f.address, bytes.data(), bytes.size(), &f.key, true, f.cipher, f.workspace);
        if (result.status != BthomeOpenStatus::opened) f.closed(result);
        else { EXPECT_TRUE(result.authenticated); EXPECT_LE(result.size, maximumBleCiphertextBytes + 1); }
    }
}
}

TEST(BleCryptoResources, ActualCipherAllocationFailureReturnsNoDataAndDoesNotRetry) {
    Fixture f; failedCryptoAllocations = 0;
    failCryptoAllocation = true;
    const auto result = f.open();
    failCryptoAllocation = false;
    EXPECT_EQ(result.status, heating::control::BthomeOpenStatus::crypto_unavailable);
    EXPECT_EQ(failedCryptoAllocations, 1u);
    f.closed(result);
    EXPECT_EQ(f.open().status, heating::control::BthomeOpenStatus::opened);
}
TEST(BleCryptoResources, LargestSupportedAdvertisementUsesExactlyTheBoundedWorkspace) {
    Fixture f;
    Bytes plaintext(heating::control::maximumBleCiphertextBytes);
    for (std::size_t i = 0; i < plaintext.size(); ++i) plaintext[i] = static_cast<uint8_t>(i);
    const auto nonce = hex("5448e68f80a5d2fc4133221100");
    Bytes ciphertext(plaintext.size()); std::array<uint8_t,4> mic{};
    mbedtls_ccm_context context; mbedtls_ccm_init(&context);
    const auto keyed = mbedtls_ccm_setkey(&context, MBEDTLS_CIPHER_ID_AES, f.key.data(), 128);
    const auto encrypted = keyed ? keyed : mbedtls_ccm_encrypt_and_tag(&context, plaintext.size(),
        nonce.data(), nonce.size(), nullptr, 0, plaintext.data(), ciphertext.data(), mic.data(), mic.size());
    mbedtls_ccm_free(&context); ASSERT_EQ(encrypted, 0);
    Bytes service{0xd2,0xfc,0x41}; service.insert(service.end(), ciphertext.begin(), ciphertext.end());
    service.insert(service.end(), nonce.end()-4, nonce.end()); service.insert(service.end(), mic.begin(), mic.end());
    f.bytes = packet(service); ASSERT_EQ(f.bytes.size(), 255u);
    const auto result = f.open(); ASSERT_EQ(result.status, heating::control::BthomeOpenStatus::opened);
    ASSERT_EQ(result.size, plaintext.size()+1);
    EXPECT_EQ(Bytes(result.data+1, result.data+result.size), plaintext);
    f.bytes.push_back(0); f.closed(f.open());
}

TEST(BleCryptoProfile, AuthenticatedShellyFieldsUseTheSameStrictProfileParser) {
    Fixture f; f.bytes = packet(hex("d2fc413c5e24a0bd4c72a7e0f33fdba22cb534221100920226c2"));
    const auto result = heating::control::decodeBoundShellyHtDisplayAdvertisement(f.address,
        f.bytes.data(), f.bytes.size(), &f.key, true, f.cipher, f.workspace);
    ASSERT_EQ(result.status, heating::control::ShellyHtFrameStatus::decoded);
    EXPECT_TRUE(result.authenticated); EXPECT_EQ(result.encryptionCounter, 1122868u);
    EXPECT_EQ(result.temperature, 2350); EXPECT_EQ(result.humidity, 4500);
    EXPECT_EQ(result.battery, 100); EXPECT_EQ(result.packetId, 7);
    EXPECT_EQ(result.batteryLow, false); EXPECT_EQ(result.light, true); EXPECT_EQ(result.lightLevel, 2);
    EXPECT_FALSE(result.declaredDeviceType); // A valid beacon is not hardware-model evidence.
}
TEST(BleCryptoProfile, AuthenticatedGenericBthomeDataDoesNotBecomeAShellyReading) {
    Fixture f;
    const auto result = heating::control::decodeBoundShellyHtDisplayAdvertisement(f.address,
        f.bytes.data(), f.bytes.size(), &f.key, true, f.cipher, f.workspace);
    EXPECT_EQ(result.status, heating::control::ShellyHtFrameStatus::malformed);
    EXPECT_FALSE(result.temperature); EXPECT_FALSE(result.humidity); EXPECT_FALSE(result.authenticated);
}
TEST(BleCryptoProfile, ShorterBatteryAndTriggerMessagesCannotInheritOldTemperature) {
    Fixture f;
    const auto decode = [&] { return heating::control::decodeBoundShellyHtDisplayAdvertisement(f.address,
        f.bytes.data(), f.bytes.size(), &f.key, true, f.cipher, f.workspace); };
    f.bytes = packet(hex("d2fc413c5e24a0bd4c72a7e0f33fdba22cb534221100920226c2"));
    ASSERT_EQ(decode().temperature, 2350);
    f.bytes = packet(hex("d2fc41528e35221100d090aaa5"));
    auto result = decode(); ASSERT_EQ(result.status, heating::control::ShellyHtFrameStatus::decoded);
    EXPECT_TRUE(result.authenticated); EXPECT_EQ(result.battery, 100);
    EXPECT_FALSE(result.temperature); EXPECT_FALSE(result.humidity); EXPECT_FALSE(result.button);
    f.bytes = packet(hex("d2fc45b7a484a135d7362211003b17bb9c"));
    result = decode(); ASSERT_EQ(result.status, heating::control::ShellyHtFrameStatus::decoded);
    EXPECT_TRUE(result.authenticated); EXPECT_TRUE(result.triggerBased);
    EXPECT_EQ(result.button, 1); EXPECT_FALSE(result.temperature); EXPECT_FALSE(result.humidity);
}

namespace { uint64_t actualObserverClockValue=1000; uint64_t actualObserverClock(){return actualObserverClockValue;} }
TEST(BleCryptoObserver, RealAuthenticationQueueAgeAndReplayAreConnected) {
    Fixture f;
    heating::control::ManagedBleBindings bindings; bindings.count=1;
    auto& device=bindings.devices[0];device.address=f.address;device.key=f.key;device.hasKey=true;
    device.profile=heating::control::ManagedBleProfile::shellyHtDisplay;
    device.encryption=heating::control::ManagedBleEncryption::bthomeV2;
    heating::control::ManagedBleObserver<heating::control::MbedTlsBleCcm> observer(f.cipher,actualObserverClock);
    actualObserverClockValue=1000; ASSERT_TRUE(observer.initialize(bindings));
    f.bytes=packet(hex("d2fc413c5e24a0bd4c72a7e0f33fdba22cb534221100920226c2"));
    observer.capture(f.address,-61,f.bytes.data(),f.bytes.size(),1000);
    actualObserverClockValue=2000;observer.processOne();
    auto value=observer.snapshot(f.address);EXPECT_EQ(value.temperature,2350);EXPECT_EQ(value.temperatureAgeMs,1000);
    EXPECT_TRUE(value.authenticated);EXPECT_EQ(value.counter,1122868u);EXPECT_FALSE(value.measurementQualified);
    observer.capture(f.address,-61,f.bytes.data(),f.bytes.size(),2000);observer.processOne();
    EXPECT_EQ(observer.snapshot(f.address).oldCounterDrops,1u);
    actualObserverClockValue=900999;f.bytes=packet(hex("d2fc41528e35221100d090aaa5"));
    observer.capture(f.address,-61,f.bytes.data(),f.bytes.size(),900999);observer.processOne();
    EXPECT_EQ(observer.snapshot(f.address).battery,100);EXPECT_EQ(observer.snapshot(f.address).temperatureAgeMs,899999);
    actualObserverClockValue=901000;EXPECT_FALSE(observer.snapshot(f.address).temperature);
    f.bytes=packet(hex("d2fc45b7a484a135d7362211003b17bb9c"));f.bytes.back()^=1;
    observer.capture(f.address,-61,f.bytes.data(),f.bytes.size(),901000);observer.processOne();
    // beta.18: a forged/failed frame no longer withdraws the still valid battery
    // value (15 min lifetime); it is reported as the last rejection instead.
    EXPECT_EQ(observer.snapshot(f.address).status,heating::control::BleObservationStatus::received);
    EXPECT_EQ(observer.snapshot(f.address).lastRejection,heating::control::BleObservationStatus::authentication_failed);
    EXPECT_EQ(observer.snapshot(f.address).framesRejected,1u);
    EXPECT_EQ(observer.snapshot(f.address).battery,100);EXPECT_EQ(observer.snapshot(f.address).counter,1122869u);
}

TEST(BleCrypto, TrvSeparateInstancesUseRealCcmAndWrongKeyLeaksNoPartialReport) {
    Fixture f;f.bytes=packet(hex("d2fc41e9455a571cd6008b709d2256955c467d14000000b1547ebc"));
    auto r=decodeBoundShellyTrvAdvertisement(f.address,f.bytes.data(),f.bytes.size(),&f.key,true,f.cipher,f.workspace);
    ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_TRUE(r.authenticated);EXPECT_EQ(r.encryptionCounter,20u);
    EXPECT_EQ(r.targetTemperature,2200);EXPECT_EQ(r.temperature,2150);EXPECT_EQ(r.externalTemperature,2000);EXPECT_EQ(r.stateRevision,63);
    f.key[0]^=1;r=decodeBoundShellyTrvAdvertisement(f.address,f.bytes.data(),f.bytes.size(),&f.key,true,f.cipher,f.workspace);
    EXPECT_EQ(r.status,BleSensorFrameStatus::authentication_failed);EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.targetTemperature);EXPECT_FALSE(r.externalTemperature);EXPECT_FALSE(r.stateRevision);
}
