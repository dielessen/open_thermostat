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
    for (unsigned i=0;i<BleDeviceDiscovery::capacity;++i) ASSERT_TRUE(devices.remember({0,0,0,0,0,uint8_t(i)}));
    const auto original=devices;
    for (unsigned i=BleDeviceDiscovery::capacity;i<65536;++i)
        EXPECT_FALSE(devices.remember({0,0,0,0,uint8_t(i>>8),uint8_t(i)}));
    EXPECT_EQ(devices.size(),BleDeviceDiscovery::capacity);
    EXPECT_TRUE(devices.overflowed());
    EXPECT_TRUE(std::equal(devices.begin(),devices.end(),original.begin()));
    EXPECT_TRUE(devices.remember({0,0,0,0,0,0}));
    EXPECT_EQ(devices.size(),BleDeviceDiscovery::capacity);
}

TEST(BleDeviceDiscovery, NamesAndSignalFollowSortedAddressAndSurviveNamelessReports) {
    BleDeviceDiscovery devices;
    const BleDeviceDiscovery::Address high{9},low{1};
    const uint8_t name[]={6,9,'S','h','e','l','l',2,1,6};
    ASSERT_TRUE(devices.remember(high,-58,name,sizeof name));
    ASSERT_TRUE(devices.remember(low,-90));
    EXPECT_STREQ(devices.hint(1).name.data(),"Shell");
    EXPECT_STREQ(devices.hint(0).name.data(),"");
    ASSERT_TRUE(devices.remember(high,-63));
    EXPECT_STREQ(devices.hint(1).name.data(),"Shell");
    EXPECT_EQ(devices.hint(1).rssi,-63);
}
TEST(BleDeviceDiscovery, MalformedNamesAreBoundedAndUtf8IsNotSplit) {
    BleDeviceDiscovery devices; const BleDeviceDiscovery::Address address{1};
    const uint8_t invalid[]={255,9,'x'};
    devices.remember(address,-999,invalid,sizeof invalid);
    EXPECT_STREQ(devices.hint(0).name.data(),""); EXPECT_EQ(devices.hint(0).rssi,-127);
    const uint8_t controls[]={10,9,'Z',0xc3,0xab,0,'\n',0xff,'x',0xc0,0x80};
    devices.remember(address,999,controls,sizeof controls);
    EXPECT_STREQ(devices.hint(0).name.data(),"Z\xc3\xabx"); EXPECT_EQ(devices.hint(0).rssi,20);
    uint8_t longName[46]{};longName[0]=45;longName[1]=9;std::fill(longName+2,longName+41,'a');
    longName[41]=0xe2;longName[42]=0x82;longName[43]=0xac;longName[44]='b';longName[45]='c';
    devices.remember(address,-50,longName,sizeof longName);
    EXPECT_EQ(std::char_traits<char>::length(devices.hint(0).name.data()),39u);
}

TEST(BleDeviceDiscovery, ShortenedNameCannotReplaceCompleteNameButCompleteRenameIsAccepted) {
    BleDeviceDiscovery devices;const BleDeviceDiscovery::Address address{1};
    const uint8_t full[]={6,9,'S','h','e','l','l'},shortName[]={3,8,'S','h'},rename[]={5,9,'R','o','o','m'};
    devices.remember(address,-50,full,sizeof full);devices.remember(address,-60,shortName,sizeof shortName);
    EXPECT_STREQ(devices.hint(0).name.data(),"Shell");EXPECT_EQ(devices.hint(0).rssi,-60);
    devices.remember(address,-70,rename,sizeof rename);EXPECT_STREQ(devices.hint(0).name.data(),"Room");
}
TEST(BleDeviceDiscovery, WhitespaceOnlyAdvertisementCannotOverwriteUsableName) {
    BleDeviceDiscovery devices;const BleDeviceDiscovery::Address address{1};
    const uint8_t full[]={3,9,'O','K'},spaces[]={4,9,' ',' ',' '};
    devices.remember(address,-50,full,sizeof full);devices.remember(address,-50,spaces,sizeof spaces);
    EXPECT_STREQ(devices.hint(0).name.data(),"OK");
}
TEST(BleDeviceDiscovery, NewDiscoveryReclaimsFullListAndClearsOldNames) {
    BleDeviceDiscovery devices;
    const uint8_t name[]={3,9,'O','K'};
    for(uint8_t i=0;i<BleDeviceDiscovery::capacity;++i)ASSERT_TRUE(devices.remember({i},-50,name,sizeof name));
    EXPECT_FALSE(devices.remember({255,255,255,255,255,255}));ASSERT_TRUE(devices.overflowed());
    devices.clear();EXPECT_EQ(devices.size(),0u);EXPECT_FALSE(devices.overflowed());
    ASSERT_TRUE(devices.remember({255,255,255,255,255,255},-60));EXPECT_STREQ(devices.hint(0).name.data(),"");
    EXPECT_FALSE(devices.hint(0).completeName);EXPECT_EQ(devices.hint(0).rssi,-60);
}
