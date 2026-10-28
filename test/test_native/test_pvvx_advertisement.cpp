#include "control/PvvxAdvertisement.h"
#include <gtest/gtest.h>
#include <vector>

namespace {
using namespace heating::control;
using Status = BleSensorFrameStatus;
// Plain reports never reach the decryptor.
struct NoCrypto {
    BleCcmStatus decrypt(const BleBindKey&, const uint8_t*, std::size_t, const uint8_t*, std::size_t,
                         const uint8_t*, std::size_t, const uint8_t*, uint8_t*, std::size_t) { return BleCcmStatus::unavailable; }
};
// The owner's MJWSD05MMC with pvvx firmware 5.9, "BTE_A3E8DB".
const std::array<uint8_t, 6> address{0xa4, 0xc1, 0x38, 0xa3, 0xe8, 0xdb};

BleSensorFrame decode(const std::vector<uint8_t>& ad, bool requireEncryption = false) {
    NoCrypto crypto; BthomeWorkspace workspace;
    return decodeBoundPvvxAdvertisement(address, ad.data(), ad.size(), nullptr, requireEncryption, crypto, workspace);
}

TEST(PvvxAdvertisement, BthomeV2ReportGivesTemperatureHumidityAndBattery) {
    // flags; service data 0xFCD2: info 0x40, id 7, battery 87 %, 21.43 degC, 48.50 %, 2950 mV
    const std::vector<uint8_t> ad{0x02, 0x01, 0x06, 0x11, 0x16, 0xd2, 0xfc, 0x40,
        0x00, 0x07, 0x01, 0x57, 0x02, 0x5f, 0x08, 0x03, 0xf2, 0x12, 0x0c, 0x86, 0x0b};
    const auto r = decode(ad);
    ASSERT_EQ(r.status, Status::decoded);
    EXPECT_EQ(*r.temperature, 2143); EXPECT_EQ(*r.humidity, 4850); EXPECT_EQ(*r.battery, 87); EXPECT_EQ(*r.packetId, 7);
    EXPECT_FALSE(r.authenticated);
}
TEST(PvvxAdvertisement, NegativeTemperatureAndEventsOnlyPacketIsIgnored) {
    const std::vector<uint8_t> cold{0x09, 0x16, 0xd2, 0xfc, 0x40, 0x00, 0x08, 0x02, 0x0c, 0xfe}; // -5.00 degC
    EXPECT_EQ(*decode(cold).temperature, -500);
    const std::vector<uint8_t> events{0x08, 0x16, 0xd2, 0xfc, 0x40, 0x00, 0x09, 0x2d, 0x01}; // window only
    EXPECT_EQ(decode(events).status, Status::not_present); // no reading: ignored, keeps the last value
}
TEST(PvvxAdvertisement, EncryptedReportWithoutBindkeyAsksForTheKey) {
    std::vector<uint8_t> ad{0x10, 0x16, 0xd2, 0xfc, 0x41, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
    EXPECT_EQ(decode(ad).status, Status::key_required);
}
TEST(PvvxAdvertisement, OlderPvvxCustomFormatIsReadForTheRightDeviceOnly) {
    // service 0x181A: MAC lo..hi, 22.05 degC, 51.00 %, 3001 mV, 90 %, counter 3, flags 0
    std::vector<uint8_t> ad{0x12, 0x16, 0x1a, 0x18, 0xdb, 0xe8, 0xa3, 0x38, 0xc1, 0xa4,
        0x9d, 0x08, 0xec, 0x13, 0xb9, 0x0b, 0x5a, 0x03, 0x00};
    const auto r = decode(ad);
    ASSERT_EQ(r.status, Status::decoded);
    EXPECT_EQ(*r.temperature, 2205); EXPECT_EQ(*r.humidity, 5100); EXPECT_EQ(*r.battery, 90);
    EXPECT_EQ(decode(ad, true).status, Status::encryption_required); // custom format is never encrypted
    ad[4] = 0x00; // another device's MAC
    EXPECT_EQ(decode(ad).status, Status::malformed);
}
TEST(PvvxAdvertisement, OriginalXiaomiReportIsNotPresentForThisProfile) {
    const std::vector<uint8_t> mibeacon{0x05, 0x16, 0x95, 0xfe, 0x58, 0x58};
    EXPECT_EQ(decode(mibeacon).status, Status::not_present);
}
TEST(PvvxAdvertisement, UnknownObjectIsMalformedNotGuessed) {
    const std::vector<uint8_t> ad{0x08, 0x16, 0xd2, 0xfc, 0x40, 0x00, 0x01, 0x7f, 0x00};
    EXPECT_EQ(decode(ad).status, Status::malformed);
}
}
