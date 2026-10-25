#include "control/ShellyHtDisplayAdvertisement.h"
#include "control/BleTemperatureAdvertisement.h"
#include <gtest/gtest.h>
#include <random>
#include <vector>

namespace {
using namespace heating::control;
using Bytes=std::vector<uint8_t>;
using Status=ShellyHtFrameStatus;
void appendAd(Bytes& out,uint8_t type,const Bytes& value) {
    out.push_back(static_cast<uint8_t>(value.size()+1)); out.push_back(type);
    out.insert(out.end(),value.begin(),value.end());
}
Bytes packet(const Bytes& objects,uint8_t info=0x40) {
    Bytes out{2,1,6},service{0xd2,0xfc,info};
    service.insert(service.end(),objects.begin(),objects.end()); appendAd(out,0x16,service); return out;
}
auto decode(const Bytes& bytes) {return decodeShellyHtDisplayAdvertisement(bytes.data(),bytes.size());}
void empty(const ShellyHtDisplayFrame& r) {
    EXPECT_FALSE(r.temperature); EXPECT_FALSE(r.humidity); EXPECT_FALSE(r.battery);
    EXPECT_FALSE(r.batteryLow); EXPECT_FALSE(r.light); EXPECT_FALSE(r.lightLevel);
    EXPECT_FALSE(r.packetId); EXPECT_FALSE(r.button); EXPECT_FALSE(r.declaredDeviceType);
    EXPECT_FALSE(r.firmware24); EXPECT_FALSE(r.firmware32); EXPECT_FALSE(r.triggerBased);
}

TEST(ShellyHtAdvertisement, PeriodicFrameUsesDocumentedSignedAndScaledObjects) {
    const auto r=decode(packet({0x00,255,0x01,87,0x15,0,0x1e,1,0x2e,45,0x45,0xce,0xff,0x64,2}));
    ASSERT_EQ(r.status,Status::decoded);
    EXPECT_EQ(r.packetId,255); EXPECT_EQ(r.temperature,-500); EXPECT_EQ(r.humidity,4500);
    EXPECT_EQ(r.battery,87); EXPECT_EQ(r.batteryLow,false); EXPECT_EQ(r.light,true); EXPECT_EQ(r.lightLevel,2);
    EXPECT_FALSE(r.declaredDeviceType); // normal beacons are not model identification
}
TEST(ShellyHtAdvertisement, PositiveZeroAndProjectTemperatureBoundaries) {
    for (const auto& [bytes,value]:std::vector<std::pair<Bytes,int>>{
             {{0x11,0x01},2730},{{0,0},0},{{0x70,0xfe},-4000},{{0x52,0x03},8500}}) {
        Bytes object{0x45}; object.insert(object.end(),bytes.begin(),bytes.end());
        const auto r=decode(packet(object)); ASSERT_EQ(r.status,Status::decoded); EXPECT_EQ(r.temperature,value);
    }
    for (const auto& raw:std::vector<Bytes>{{0x6f,0xfe},{0x53,0x03},{0x00,0x80},{0xff,0x7f}}) {
        Bytes object{0x45}; object.insert(object.end(),raw.begin(),raw.end());
        const auto r=decode(packet(object)); EXPECT_EQ(r.status,Status::malformed); empty(r);
    }
}
TEST(ShellyHtAdvertisement, IdentificationAndBothRawFirmwareWidthsNeverInventMeasurements) {
    const auto r=decode(packet({0x01,0,0x15,1,0xf0,0x0c,0,0xf1,1,2,3,4,0xf2,5,6,7}));
    ASSERT_EQ(r.status,Status::decoded); EXPECT_EQ(r.declaredDeviceType,12);
    EXPECT_EQ(r.firmware32,0x04030201u); EXPECT_EQ(r.firmware24,0x070605u);
    EXPECT_FALSE(r.temperature); EXPECT_FALSE(r.humidity);
}
TEST(ShellyHtAdvertisement, OtherShellyModelsAreNotAcceptedAsDisplay) {
    for (uint8_t id:{0,1,3,8,13,255}) {
        const auto r=decode(packet({0x01,70,0xf0,id,0})); EXPECT_EQ(r.status,Status::malformed); empty(r);
    }
}
TEST(ShellyHtAdvertisement, ButtonAndBatteryFramesNeverCarryEarlierTemperature) {
    ASSERT_TRUE(decode(packet({0x45,0x11,1})).temperature);
    auto r=decode(packet({0x01,50,0x15,0,0x3a,1},0x44)); ASSERT_EQ(r.status,Status::decoded);
    EXPECT_TRUE(r.triggerBased); EXPECT_EQ(r.button,1); EXPECT_FALSE(r.temperature); EXPECT_FALSE(r.humidity);
    r=decode(packet({0x01,0})); ASSERT_EQ(r.status,Status::decoded); EXPECT_EQ(r.battery,0); EXPECT_FALSE(r.temperature);
}
TEST(ShellyHtAdvertisement, UnknownTruncatedDuplicateAndOutOfOrderObjectsAreAtomicFailures) {
    for (const auto& suffix:std::vector<Bytes>{{0x64},{0x65,1},{0x45,0x10,1},{0x01,50},{0xf1,1,2,3}}) {
        Bytes objects{0x01,80,0x45,0x11,1}; objects.insert(objects.end(),suffix.begin(),suffix.end());
        const auto r=decode(packet(objects)); EXPECT_EQ(r.status,Status::malformed); empty(r);
    }
}
TEST(ShellyHtAdvertisement, PropertyRangesAreValidatedBeforeReturningAnyField) {
    for (const auto& object:std::vector<Bytes>{{0x01,101},{0x15,2},{0x1e,2},{0x2e,101},{0x3a,2},{0x64,3}}) {
        const auto r=decode(packet(object)); EXPECT_EQ(r.status,Status::malformed); empty(r);
    }
    for (uint8_t h:{0,100}) {const auto r=decode(packet({0x2e,h})); ASSERT_EQ(r.status,Status::decoded); EXPECT_EQ(r.humidity,h*100);}
}
TEST(ShellyHtAdvertisement, CompleteAdContainerIsCheckedBeforeReturningMeasurements) {
    auto bytes=packet({0x45,0x11,1});
    for (size_t n=0;n<bytes.size();++n)
        EXPECT_NE(decodeShellyHtDisplayAdvertisement(bytes.data(),n).status,Status::decoded)<<n;
    bytes.insert(bytes.end(),{9,0x16,0xd2}); const auto r=decode(bytes); EXPECT_EQ(r.status,Status::malformed); empty(r);
}
TEST(ShellyHtAdvertisement, OnlyZeroPaddingMayFollowTerminator) {
    auto bytes=packet({0x45,0x11,1}); bytes.insert(bytes.end(),{0,0,0}); EXPECT_EQ(decode(bytes).status,Status::decoded);
    bytes.push_back(1); const auto r=decode(bytes); EXPECT_EQ(r.status,Status::malformed); empty(r);
}
TEST(ShellyHtAdvertisement, DuplicateServiceAndShortServiceUuidNeverSelectPartialReport) {
    for (const Bytes& service:std::vector<Bytes>{{0xd2,0xfc,0x40,1,50},{0xd2},{}}) {
        auto bytes=packet({0x45,0x11,1}); appendAd(bytes,0x16,service);
        const auto r=decode(bytes); EXPECT_EQ(r.status,Status::malformed); empty(r);
    }
}
TEST(ShellyHtAdvertisement, LocalNameAndOtherServicesNeverEstablishModelIdentity) {
    Bytes bytes; appendAd(bytes,0x09,{'S','B','H','T','-','1','0','3','C'});
    appendAd(bytes,0x16,{0x1a,0x18,0x40,0x45,0x11,1}); EXPECT_EQ(decode(bytes).status,Status::not_present);
    const auto service=packet({0x45,0x11,1}); bytes.insert(bytes.end(),service.begin(),service.end());
    auto r=decode(bytes); ASSERT_EQ(r.status,Status::decoded); EXPECT_FALSE(r.declaredDeviceType);
}
TEST(ShellyHtAdvertisement, EncryptedFlagRequiresKeyButNeverLeaksCiphertextAsFields) {
    for (uint8_t info:{0x41,0x45}) {
        const auto r=decode(packet(Bytes(10,0x45),info)); EXPECT_EQ(r.status,Status::key_required); empty(r);
        for (size_t n=0;n<10;++n) EXPECT_EQ(decode(packet(Bytes(n,0),info)).status,Status::malformed);
    }
}
TEST(ShellyHtAdvertisement, ReservedBitsWrongVersionsEmptyAndOversizedContainersAreRejected) {
    for (uint8_t info:{0x00,0x20,0x60,0x42,0x48,0x50,0xff}) EXPECT_EQ(decode(packet({1,50},info)).status,Status::malformed);
    EXPECT_EQ(decode(packet({})).status,Status::malformed);
    EXPECT_EQ(decodeShellyHtDisplayAdvertisement(nullptr,20).status,Status::malformed);
    EXPECT_EQ(decode(Bytes(256,0)).status,Status::malformed);
}
TEST(ShellyHtAdvertisement, ParsingHasNoReplayOrCounterWrapQualification) {
    for (uint8_t sequence:{255,0,0,1}) {
        auto r=decode(packet({0,sequence,1,50})); EXPECT_EQ(r.status,Status::decoded); EXPECT_EQ(r.packetId,sequence);
        EXPECT_FALSE(r.temperature); // sequence alone can never refresh a measurement
    }
}
TEST(ShellyHtAdvertisement, ExistingReaderDoesNotSelectThePreparedProfile) {
    auto bytes=packet({0x01,50,0x45,0x11,1,0xf0,0x0c,0});
    EXPECT_EQ(decode(bytes).status,Status::decoded);
    const std::array<uint8_t,6> address{0xa4,0xc1,0x38,0x12,0x34,0x56};
    EXPECT_FALSE(decodeBleTemperatureAdvertisement(address,bytes.data(),bytes.size()));
}
TEST(ShellyHtAdvertisement, BoundedMalformedInputAndMutationsAreSafeAndAtomic) {
    std::mt19937 random(0x53424854);
    for (unsigned n=0;n<12000;++n) {
        Bytes bytes(random()%257); for (auto& b:bytes) b=static_cast<uint8_t>(random());
        const auto r=decode(bytes); if (r.status!=Status::decoded) empty(r);
    }
    const auto valid=packet({0x00,1,0x01,87,0x15,0,0x1e,1,0x2e,45,0x45,0xce,0xff,0x64,2,0xf0,0x0c,0});
    for (size_t i=0;i<valid.size();++i) for (unsigned value=0;value<256;++value) {
        auto bytes=valid; bytes[i]=static_cast<uint8_t>(value); const auto r=decode(bytes);
        if (r.status!=Status::decoded) empty(r);
        if (r.temperature) {
            EXPECT_GE(*r.temperature,-4000);
            EXPECT_LE(*r.temperature,8500);
        }
    }
}
}
