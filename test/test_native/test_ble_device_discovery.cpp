#include "control/BleDeviceDiscovery.h"
#include <gtest/gtest.h>
#include <algorithm>
using heating::control::BleDeviceDiscovery;

TEST(BleDeviceDiscovery, StableSortedUniqueAddressesWithoutDynamicStorage) {
    BleDeviceDiscovery devices;
    const BleDeviceDiscovery::Address high{255,2,3,4,5,6}, low{0,2,3,4,5,6};
    EXPECT_EQ(devices.begin(),devices.end());
    ASSERT_TRUE(devices.remember(high));
    ASSERT_TRUE(devices.remember(low));
    ASSERT_TRUE(devices.remember(high));
    EXPECT_EQ(devices.size(),2u);
    EXPECT_EQ(*devices.begin(),low);
    EXPECT_EQ(*(devices.end()-1),high);
    EXPECT_FALSE(devices.overflowed());
}
TEST(BleDeviceDiscovery, ThousandsOfOtherAddressesCannotGrowOrEvictOriginalHints) {
    BleDeviceDiscovery devices;
    for (unsigned i=0;i<32;++i) ASSERT_TRUE(devices.remember({0,0,0,0,0,uint8_t(i)}));
    const auto original=devices;
    for (unsigned i=32;i<65536;++i)
        EXPECT_FALSE(devices.remember({0,0,0,0,uint8_t(i>>8),uint8_t(i)}));
    EXPECT_EQ(devices.size(),32u);
    EXPECT_TRUE(devices.overflowed());
    EXPECT_TRUE(std::equal(devices.begin(),devices.end(),original.begin()));
    EXPECT_TRUE(devices.remember({0,0,0,0,0,0}));
    EXPECT_EQ(devices.size(),32u);
}
