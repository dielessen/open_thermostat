// Independent Python AESCCM protocol fixtures, not captured Monitor3 packets.
#include "control/MiBeaconMonitor3Advertisement.h"
#include "control/MbedTlsBleCcm.h"
#include "control/ManagedBleObserver.h"
#include <gtest/gtest.h>
#include <vector>
#include <string>
using namespace heating::control;
namespace {
using Bytes=std::vector<uint8_t>;
Bytes hex(const std::string& s){Bytes b;for(std::size_t i=0;i<s.size();i+=2)b.push_back(std::stoul(s.substr(i,2),nullptr,16));return b;}
struct MiFixture {
 ManagedBleAddress address{0x54,0x48,0xe6,0x8f,0x80,0xa5};BleBindKey key{};BthomeWorkspace workspace;MbedTlsBleCcm crypto;
 Bytes bytes=hex("241695fe5858474c44a5808fe6485408418c05be8fa6caaafb3969456f33332211d3627020");
 MiFixture(){auto source=hex("231d39c1d7cc1ab1aee224cd096db932");std::copy(source.begin(),source.end(),key.begin());}
 auto decode(){return decodeBoundMiBeaconMonitor3Advertisement(address,bytes.data(),bytes.size(),&key,crypto,workspace);}
 void closed(const BleSensorFrame& r){EXPECT_NE(r.status,BleSensorFrameStatus::decoded);EXPECT_FALSE(r.temperature);EXPECT_FALSE(r.humidity);EXPECT_FALSE(r.battery);EXPECT_FALSE(r.encryptionCounter);EXPECT_FALSE(r.authenticated);EXPECT_TRUE(std::all_of(workspace.plaintext.begin(),workspace.plaintext.end(),[](auto b){return !b;}));}
};
TEST(MiBeaconCrypto, RealCcmSupportsBothDeclaredMonitor3IdsAndFullCounterWithoutAadConfusion){
 MiFixture f;auto r=f.decode();ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_TRUE(r.authenticated);EXPECT_EQ(r.temperature,2375);EXPECT_EQ(r.humidity,4500);EXPECT_EQ(r.battery,100);EXPECT_EQ(r.encryptionCounter,0x11223344u);EXPECT_EQ(r.declaredDeviceType,0x4c47);
 f.bytes=hex("201695fe5858322800a5808fe648547a2c1ddc7533fdc0ed4dfb000000369af651");r=f.decode();ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.encryptionCounter,0u);EXPECT_EQ(r.declaredDeviceType,0x2832);EXPECT_EQ(r.temperature,2350);EXPECT_EQ(r.humidity,4500);
 f.bytes=hex("211695fe78583228ffa5808fe6485420003c535de4327b84e8ac46ffffff30f3389a");r=f.decode();ASSERT_EQ(r.status,BleSensorFrameStatus::decoded);EXPECT_EQ(r.encryptionCounter,UINT32_MAX);EXPECT_EQ(r.temperature,-4000);EXPECT_EQ(r.humidity,10000);EXPECT_FALSE(r.battery);
}
TEST(MiBeaconCrypto, WrongKeyOrMacAndEveryCipherCounterMicMutationExposeNoPartialData){
 MiFixture f;f.key[0]^=1;f.closed(f.decode());f.key[0]^=1;f.address[0]^=1;f.closed(f.decode());f.address[0]^=1;
 for(std::size_t i=15;i<f.bytes.size();++i){f.bytes[i]^=1;f.closed(f.decode());f.bytes[i]^=1;}
 f.bytes[6]^=1;f.closed(f.decode());f.bytes[6]^=1;EXPECT_EQ(f.decode().status,BleSensorFrameStatus::decoded);
}
TEST(MiBeaconCrypto, BthomeNonceOrderAndMissingMiBeaconAadCannotAuthenticate){
 MiFixture f;const auto e=inspectMiBeaconMonitor3(f.address,f.bytes.data(),f.bytes.size());ASSERT_EQ(e.status,BleSensorFrameStatus::decoded);
 std::array<uint8_t,243> output{};
 EXPECT_EQ(f.crypto.decrypt(f.key,e.nonce.data(),e.nonce.size(),nullptr,0,e.ciphertext,e.size,e.mic,output.data(),output.size()),BleCcmStatus::authentication_failed);
 auto nonce=e.nonce;std::reverse(nonce.begin(),nonce.begin()+6);const uint8_t aad=0x11;
 EXPECT_EQ(f.crypto.decrypt(f.key,nonce.data(),nonce.size(),&aad,1,e.ciphertext,e.size,e.mic,output.data(),output.size()),BleCcmStatus::authentication_failed);
 EXPECT_EQ(f.decode().status,BleSensorFrameStatus::decoded);
}
TEST(MiBeaconCrypto, MissingKeyAndPlaintextNeverYieldUnauthenticatedFallback){
 MiFixture f;auto r=decodeBoundMiBeaconMonitor3Advertisement(f.address,f.bytes.data(),f.bytes.size(),nullptr,f.crypto,f.workspace);EXPECT_EQ(r.status,BleSensorFrameStatus::key_required);f.closed(r);
 f.bytes[4]&=~uint8_t(8);r=f.decode();EXPECT_EQ(r.status,BleSensorFrameStatus::encryption_required);f.closed(r);
}
TEST(MiBeaconCrypto, TruncationCannotReusePreviouslyOpenedWorkspace){
 MiFixture f;for(std::size_t n=0;n<f.bytes.size();++n){ASSERT_EQ(f.decode().status,BleSensorFrameStatus::decoded);const auto r=decodeBoundMiBeaconMonitor3Advertisement(f.address,f.bytes.data(),n,&f.key,f.crypto,f.workspace);f.closed(r);}
}
}

namespace {uint64_t monitorClockValue=1000;uint64_t monitorClock(){return monitorClockValue;}}
TEST(MiBeaconCryptoObserver, RealLoopReceptionRetainsOriginalFieldAgeAndItsAuthenticatedCounter) {
 MiFixture f;ManagedBleBindings bindings;bindings.count=1;auto& b=bindings.devices[0];b.address=f.address;b.profile=ManagedBleProfile::xiaomiMonitor3;b.encryption=ManagedBleEncryption::miBeaconV4V5;b.key=f.key;b.hasKey=true;
 ManagedBleObserver<MbedTlsBleCcm> observer(f.crypto,monitorClock);monitorClockValue=1000;ASSERT_TRUE(observer.initialize(bindings));
 observer.capture(f.address,-60,f.bytes.data(),f.bytes.size(),1000);monitorClockValue=1500;observer.processOne();
 auto value=observer.snapshot(f.address);ASSERT_EQ(value.temperature,2375);EXPECT_EQ(value.temperatureAgeMs,500u);EXPECT_EQ(value.counter,0x11223344u);EXPECT_TRUE(value.authenticated);EXPECT_FALSE(value.measurementQualified);
 observer.capture(f.address,-60,f.bytes.data(),f.bytes.size(),1500);observer.processOne();EXPECT_EQ(observer.snapshot(f.address).oldCounterDrops,1u);EXPECT_EQ(observer.snapshot(f.address).temperatureAgeMs,500u);
 monitorClockValue=900999;f.bytes=hex("191695fe5858474c45a5808fe64854048a9a1e332211cfe012a1");observer.capture(f.address,-60,f.bytes.data(),f.bytes.size(),900999);observer.processOne();
 value=observer.snapshot(f.address);EXPECT_EQ(value.battery,100);EXPECT_EQ(value.counter,0x11223345u);EXPECT_EQ(value.temperatureAgeMs,899999u);
 monitorClockValue=901000;EXPECT_FALSE(observer.snapshot(f.address).temperature);
 f.bytes=hex("211695fe78583228ffa5808fe6485420003c535de4327b84e8ac46ffffff30f3389a");f.bytes.back()^=1;observer.capture(f.address,-60,f.bytes.data(),f.bytes.size(),901000);observer.processOne();value=observer.snapshot(f.address);
 // beta.18: the failed frame is reported (last_rejection); the valid battery value stays.
 EXPECT_EQ(value.status,BleObservationStatus::received);EXPECT_EQ(value.lastRejection,BleObservationStatus::authentication_failed);EXPECT_EQ(value.battery,100);EXPECT_EQ(value.counter,0x11223345u);
 f.bytes.back()^=1;observer.capture(f.address,-60,f.bytes.data(),f.bytes.size(),901000);observer.processOne();EXPECT_EQ(observer.snapshot(f.address).temperature,-4000);EXPECT_EQ(observer.snapshot(f.address).counter,UINT32_MAX);
}
