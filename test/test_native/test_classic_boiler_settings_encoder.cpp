#include "EMS/ClassicBoilerSettingsEncoder.h"
#include <gtest/gtest.h>
using namespace heating::ems;
namespace {
using Encoder = ClassicBoilerSettingsEncoder;
using Setting = Encoder::Setting;
const auto address = ClassicBoilerTestEncoder::Addressing::classicService();
TEST(ClassicSettingsEncoder, EveryAcceptedValueProducesOneByteAtTheDeclaredOffset) {
    for (const auto setting : {Setting::heatingActivated, Setting::heatingTemperature,
                              Setting::burnerMinimumPeriod, Setting::pumpDelay}) {
        Encoder::Definition spec;
        ASSERT_TRUE(Encoder::definition(setting, spec));
        for (int value = -256; value <= 512; ++value) {
            EmsRawFrame frame;
            const bool accepted = Encoder::encode(address, true, setting, value, frame);
            ASSERT_EQ(accepted, value >= spec.minimum && value <= spec.maximum);
            if (!accepted) { EXPECT_EQ(frame.length, 0); continue; }
            const auto decoded = EmsTelegram::fromRawData(frame.data.data(), frame.length);
            EXPECT_EQ(decoded.getSenderId(), 0x0B);
            EXPECT_EQ(decoded.getDestinationId(), 8);
            EXPECT_EQ(decoded.getTypeId(), 0x16);
            EXPECT_EQ(decoded.getOffset(), spec.offset);
            EXPECT_EQ(decoded.dataSize(), 1u);
            EXPECT_EQ(*decoded.byteAt(spec.offset), setting == Setting::heatingActivated
                      ? (value ? 255 : 0) : value);
        }
    }
}
TEST(ClassicSettingsEncoder, RequiresQualifiedClassicAndReviewedAddressAndClearsOutput) {
    EmsRawFrame frame;
    ASSERT_TRUE(Encoder::encode(address,true,Setting::heatingTemperature,45,frame));
    EXPECT_FALSE(Encoder::encode(address,false,Setting::heatingTemperature,45,frame));
    EXPECT_EQ(frame.length,0);
    auto bad = address; bad.reviewed = false;
    EXPECT_FALSE(Encoder::encode(bad,true,Setting::heatingTemperature,45,frame));
    EXPECT_FALSE(Encoder::encode(address,true,static_cast<Setting>(255),45,frame));
    EXPECT_EQ(frame.length,0);
}
TEST(ClassicSettingsEncoder, ReadbackMustBeAddressedBoilerResponseContainingTheExactByte) {
    for (const auto setting : {Setting::heatingActivated,Setting::heatingTemperature,
                              Setting::burnerMinimumPeriod,Setting::pumpDelay}) {
        Encoder::Definition spec; ASSERT_TRUE(Encoder::definition(setting,spec));
        const uint8_t value = setting == Setting::heatingActivated ? 255 : 1;
        const auto report = EmsTelegram(EmsTelegram::WRITE,8,11,spec.offset,0x16,{value});
        EXPECT_TRUE(Encoder::readbackMatches(address,true,setting,1,report));
        EXPECT_FALSE(Encoder::readbackMatches(address,false,setting,1,report));
        EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,0,report));
        for (const auto op : {EmsTelegram::BROADCAST,EmsTelegram::READ,EmsTelegram::READ_WITH_DATA})
            EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                         EmsTelegram(op,8,11,spec.offset,0x16,{value})));
        for (const auto source : {0,11,16})
            EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                         EmsTelegram(EmsTelegram::WRITE,source,11,spec.offset,0x16,{value})));
        for (const auto destination : {0,8,16})
            EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                         EmsTelegram(EmsTelegram::WRITE,8,destination,spec.offset,0x16,{value})));
        EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                     EmsTelegram(EmsTelegram::WRITE,8,11,spec.offset,0xE6,{value})));
        EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                     EmsTelegram(EmsTelegram::WRITE,8,11,spec.offset,0x16,std::vector<uint8_t>{})));
        EXPECT_FALSE(Encoder::readbackMatches(address,true,setting,1,
                     EmsTelegram(EmsTelegram::WRITE,8,11,spec.offset+1,0x16,{value})));
    }
}
}
