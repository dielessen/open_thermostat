#include "control/BleDeviceDiscovery.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <string>
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
TEST(BleDeviceDiscovery, StatusJsonShowsBoundedStrongestHintsFromAFullList) {
    BleDeviceDiscovery devices;
    uint8_t name[42]{};name[0]=41;name[1]=9;std::fill(name+2,name+42,'"'); // worst case: every byte escaped
    for(unsigned i=0;i<BleDeviceDiscovery::capacity;++i)ASSERT_TRUE(devices.remember({uint8_t(i)},-127+int(i%100),name,sizeof name));
    EXPECT_FALSE(devices.remember({255,255,255,255,255,255}));
    std::ostringstream out;out<<'{';devices.writeJson(out);out<<'}';
    const auto body=out.str();
    EXPECT_LT(body.size(),5000u); // was ~13.5 KB plus a 256-node cJSON tree every 5 s
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> json(cJSON_Parse(body.c_str()),cJSON_Delete);
    ASSERT_TRUE(json);
    const auto nearby=cJSON_GetObjectItem(json.get(),"nearby"),hints=cJSON_GetObjectItem(json.get(),"nearby_devices");
    ASSERT_EQ(cJSON_GetArraySize(nearby),int(BleDeviceDiscovery::shown));
    ASSERT_EQ(cJSON_GetArraySize(hints),int(BleDeviceDiscovery::shown));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json.get(),"discovery_full")));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(json.get(),"discovery_capacity")),double(BleDeviceDiscovery::shown));
    double previous=21;
    for(int i=0;i<cJSON_GetArraySize(hints);++i) {
        const auto hint=cJSON_GetArrayItem(hints,i);const auto rssi=cJSON_GetNumberValue(cJSON_GetObjectItem(hint,"rssi"));
        EXPECT_LE(rssi,previous);previous=rssi;
        EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(hint,"address")),cJSON_GetStringValue(cJSON_GetArrayItem(nearby,i)));
        EXPECT_EQ(std::string(cJSON_GetStringValue(cJSON_GetObjectItem(hint,"name"))),std::string(40,'"'));
    }
    EXPECT_EQ(previous,-127+99-31); // the 32 strongest of -127..-28
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(nearby,0)),"630000000000");
}
TEST(BleDeviceDiscovery, StatusJsonOfEmptyAndSmallListsIsNotFull) {
    BleDeviceDiscovery devices;std::ostringstream empty;empty<<'{';devices.writeJson(empty);empty<<'}';
    EXPECT_EQ(empty.str(),"{\"discovery_full\":false,\"discovery_capacity\":32,\"nearby\":[],\"nearby_devices\":[]}");
    for(uint8_t i=0;i<BleDeviceDiscovery::shown;++i)devices.remember({i},-60);
    std::ostringstream out;out<<'{';devices.writeJson(out);out<<'}';
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> json(cJSON_Parse(out.str().c_str()),cJSON_Delete);
    ASSERT_TRUE(json);EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(json.get(),"discovery_full")));
    // Equal signal keeps address order.
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(cJSON_GetObjectItem(json.get(),"nearby"),0)),"000000000000");
    devices.remember({BleDeviceDiscovery::shown},-60);
    std::ostringstream more;devices.writeJson(more);
    EXPECT_NE(more.str().find("\"discovery_full\":true"),std::string::npos);
}
