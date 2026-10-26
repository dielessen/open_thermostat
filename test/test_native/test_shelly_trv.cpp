#include "control/ShellyTrvAdvertisement.h"
#include <gtest/gtest.h>
#include <vector>
using namespace heating::control;
namespace {
auto decode(std::initializer_list<uint8_t> bytes){std::vector<uint8_t>b(bytes);return decodeShellyTrvService(b.data(),b.size());}
void empty(const BleSensorFrame& r){EXPECT_EQ(r.status,BleSensorFrameStatus::malformed);EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.targetTemperature);EXPECT_FALSE(r.externalTemperature);EXPECT_FALSE(r.battery);EXPECT_FALSE(r.stateRevision);}
}
TEST(ShellyTrv, TargetCalculatedCurrentAndOptionalExternalAreSeparateInstances) {
 auto r=decode({0x40,0,1,1,90,0x45,220,0,0x45,215,0,0x45,200,0,0x54,1,63});
 ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.targetTemperature,2200);EXPECT_EQ(r.temperature,2150);EXPECT_EQ(r.externalTemperature,2000);EXPECT_EQ(r.stateRevision,63);EXPECT_EQ(r.battery,90);EXPECT_FALSE(r.authenticated);EXPECT_FALSE(r.humidity);
}
TEST(ShellyTrv, TwoTemperaturesNeverInventAnExternalSensor) {
 auto r=decode({0x40,0x45,220,0,0x45,215,0});ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_FALSE(r.externalTemperature);EXPECT_EQ(r.temperature,2150);
}
TEST(ShellyTrv, NegativeTemperatureAndZeroAreValuesNotMissingSentinels) {
 auto r=decode({0x40,0x45,0,0,0x45,0xfb,0xff,0x45,0,0});ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.targetTemperature,0);EXPECT_EQ(r.temperature,-50);EXPECT_EQ(r.externalTemperature,0);
}
TEST(ShellyTrv, OneOrFourTemperaturesRejectTheEntireFrame) {
 empty(decode({0x40,1,90,0x45,220,0}));empty(decode({0x40,0x45,220,0,0x45,215,0,0x45,200,0,0x45,190,0}));
}
TEST(ShellyTrv, BatteryAndRevisionOnlyFramesDoNotContainMeasurements) {
 auto r=decode({0x40,1,0,0x54,1,255});ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.battery,0);EXPECT_EQ(r.stateRevision,255);EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.targetTemperature);
}
TEST(ShellyTrv, PackedRevisionMustBeExactlyOneByteAndNeverAValvePosition) {
 for(auto raw:{std::vector<uint8_t>{0x40,0x54},std::vector<uint8_t>{0x40,0x54,0},std::vector<uint8_t>{0x40,0x54,2,0,0},std::vector<uint8_t>{0x40,0x54,1}})empty(decodeShellyTrvService(raw.data(),raw.size()));
}
TEST(ShellyTrv, DuplicateOrUnsortedNonTemperatureObjectsAndUnknownObjectsAreAtomicFailures) {
 empty(decode({0x40,1,90,1,80}));empty(decode({0x40,1,90,0,4}));empty(decode({0x40,1,90,0x46,0,0}));empty(decode({0x40,1,90,0xf0,12,0}));
}
TEST(ShellyTrv, OutOfRangeOrTruncatedTemperatureNeverLeaksEarlierFields) {
 empty(decode({0x40,1,90,0x45,220,0,0x45,0x53,3}));empty(decode({0x40,1,90,0x45,220,0,0x45,0}));empty(decode({0x40,1,101}));
}
TEST(ShellyTrv, EncryptedBytesCannotBeMisreadAsPlaintext) {
 auto r=decode({0x41,0,0,0,0,0,0,0,0,0,0});EXPECT_EQ(r.status,BleSensorFrameStatus::key_required);EXPECT_FALSE(r.temperature);empty(decode({0x41,1}));empty(decode({0x60,1,90}));
}
