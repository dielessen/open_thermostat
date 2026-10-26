#include "control/MiBeaconMonitor3Advertisement.h"
#include "control/BleTemperatureAdvertisement.h"
#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <random>
using namespace heating::control;
namespace {
using Bytes=std::vector<uint8_t>;
Bytes hex(const std::string& s){Bytes b;for(std::size_t i=0;i<s.size();i+=2)b.push_back(std::stoul(s.substr(i,2),nullptr,16));return b;}
ManagedBleAddress address{0x54,0x48,0xe6,0x8f,0x80,0xa5};
Bytes encrypted(){return hex("241695fe5858474c44a5808fe6485408418c05be8fa6caaafb3969456f33332211d3627020");}
TEST(MiBeaconMonitor3, HeaderUsesExactProductAndDisplayMacReverseNonceWithFull32BitCounter){
 auto b=encrypted();auto r=inspectMiBeaconMonitor3(address,b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);
 EXPECT_EQ(r.productId,0x4c47);EXPECT_EQ(r.counter,0x11223344u);EXPECT_EQ(r.packetId,0x44);EXPECT_EQ(Bytes(r.nonce.begin(),r.nonce.end()),hex("a5808fe64854474c44332211"));
 EXPECT_EQ(r.size,15u);EXPECT_EQ(r.mic,b.data()+b.size()-4);
}
TEST(MiBeaconMonitor3, SimilarCgg1ProductAndForeignEmbeddedAddressAreRejected){
 auto b=encrypted();b[6]=0x48;b[7]=0x0b;EXPECT_EQ(inspectMiBeaconMonitor3(address,b.data(),b.size()).status,BleSensorFrameStatus::malformed);
 b=encrypted();b[9]^=1;EXPECT_EQ(inspectMiBeaconMonitor3(address,b.data(),b.size()).status,BleSensorFrameStatus::malformed);
 b=encrypted();auto other=address;other[0]^=1;EXPECT_EQ(inspectMiBeaconMonitor3(other,b.data(),b.size()).status,BleSensorFrameStatus::malformed);
}
TEST(MiBeaconMonitor3, EveryTruncationAndDuplicateOrMalformedSuffixIsRejected){
 auto b=encrypted();for(std::size_t size=0;size<b.size();++size)EXPECT_NE(inspectMiBeaconMonitor3(address,b.data(),size).status,BleSensorFrameStatus::decoded)<<size;
 auto duplicate=b;duplicate.insert(duplicate.end(),b.begin(),b.end());EXPECT_EQ(inspectMiBeaconMonitor3(address,duplicate.data(),duplicate.size()).status,BleSensorFrameStatus::malformed);
 b.insert(b.end(),{4,0x16,0x95});EXPECT_EQ(inspectMiBeaconMonitor3(address,b.data(),b.size()).status,BleSensorFrameStatus::malformed);
}
TEST(MiBeaconMonitor3, PlaintextMeshWrongVersionAndMissingObjectsAreNotAccepted){
 for(auto mask:{8,0x80,0x40}){auto b=encrypted();b[4]^=mask;EXPECT_NE(inspectMiBeaconMonitor3(address,b.data(),b.size()).status,BleSensorFrameStatus::decoded);}
 for(auto version:{0,1,2,3,6,15}){auto b=encrypted();b[5]=(b[5]&15)|(version<<4);EXPECT_EQ(inspectMiBeaconMonitor3(address,b.data(),b.size()).status,BleSensorFrameStatus::malformed);}
}
TEST(MiBeaconMonitor3, CombinedAndSeparateLegacyObjectsScaleWithoutInventedFields){
 auto b=hex("0d1004eb00c2010a100164");auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.temperature,2350);EXPECT_EQ(r.humidity,4500);EXPECT_EQ(r.battery,100);EXPECT_FALSE(r.authenticated);EXPECT_FALSE(r.encryptionCounter);
 b=hex("04100270fe061002e803");r=decodeMiBeaconMonitor3Objects(b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.temperature,-4000);EXPECT_EQ(r.humidity,10000);EXPECT_FALSE(r.battery);
}
TEST(MiBeaconMonitor3, FloatObjectsAndZeroAreRealValues){
 auto b=hex("014c040000be41024c012d034c0164");auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.temperature,2375);EXPECT_EQ(r.humidity,4500);EXPECT_EQ(r.battery,100);
 b=hex("014c0400000000084c0400000000");r=decodeMiBeaconMonitor3Objects(b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.temperature,0);EXPECT_EQ(r.humidity,0);
}
TEST(MiBeaconMonitor3, NonfiniteAndOutOfRangeFloatsProduceNoPartialData){
 for(auto bits:{"0000c07f","0000807f","000080ff","ffff7f7f","0000ac42"}){auto b=hex(std::string("0a100164014c04")+bits);auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());EXPECT_EQ(r.status,BleSensorFrameStatus::malformed);EXPECT_FALSE(r.battery);EXPECT_FALSE(r.temperature);}
}
TEST(MiBeaconMonitor3, DuplicateSemanticFieldsUnknownObjectsAndPartialValuesAreAtomicFailures){
 for(auto s:{"041002eb000d1004eb00c201","014c040000be41041002eb00","0a100164034c0164","061002e903","0a100165","0a100164ff","01100100","041000","041003000000"}){
  auto b=hex(s);auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());EXPECT_EQ(r.status,BleSensorFrameStatus::malformed)<<s;EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.humidity);EXPECT_FALSE(r.battery);
 }
}
TEST(MiBeaconMonitor3, PartialBatteryPacketCannotInheritPreviousTemperature){
 auto b=hex("014c040000be41");ASSERT_EQ(decodeMiBeaconMonitor3Objects(b.data(),b.size()).temperature,2375);
 b=hex("034c0164");auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.battery,100);EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.humidity);
}
TEST(MiBeaconMonitor3, BoundedRandomObjectsNeverReturnOutOfRangeMeasurements){
 std::mt19937 random(2832);for(unsigned i=0;i<10000;++i){Bytes b(random()%257);for(auto& byte:b)byte=uint8_t(random());auto r=decodeMiBeaconMonitor3Objects(b.data(),b.size());if(r.status!=BleSensorFrameStatus::decoded){EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.humidity);EXPECT_FALSE(r.battery);}else{if(r.temperature){EXPECT_GE(*r.temperature,-4000);EXPECT_LE(*r.temperature,8500);}if(r.humidity){EXPECT_GE(*r.humidity,0);EXPECT_LE(*r.humidity,10000);}}}
}
}

TEST(MiBeaconMonitor3, AnOldAdvertisedNameCannotPromoteTheEncryptedFrameIntoTheLegacyRoomReader) {
 auto b=encrypted();Bytes prefixed{9,0x09,'M','J','_','H','T','_','V','1'};prefixed.insert(prefixed.end(),b.begin(),b.end());
 EXPECT_FALSE(decodeBleTemperatureAdvertisement(address,prefixed.data(),prefixed.size()));
}
