#include "control/ManagedBleObserver.h"
#include <gtest/gtest.h>
#include <vector>
using namespace heating::control;
namespace {
uint64_t observerNow;
uint64_t observerClock() { return observerNow; }
// State-machine seam only. Real AES/MIC vectors are tested separately with Mbed TLS.
struct ObserverCrypto {
    unsigned calls=0, clears=0;
    BleCcmStatus result=BleCcmStatus::authenticated;
    void clear() noexcept { ++clears; }
    BleCcmStatus decrypt(const BleBindKey&, const uint8_t*,std::size_t,const uint8_t*,std::size_t,
        const uint8_t* in,std::size_t size,const uint8_t*,uint8_t* out,std::size_t) {
        ++calls; if(result==BleCcmStatus::authenticated) std::copy_n(in,size,out); return result;
    }
};
ManagedBleBindings config(bool encrypted=false) {
    ManagedBleBindings b; b.count=1; b.devices[0].address={0x54,0x48,0xe6,0x8f,0x80,0xa5};
    b.devices[0].profile=ManagedBleProfile::shellyHtDisplay;
    if(encrypted) { b.devices[0].encryption=ManagedBleEncryption::bthomeV2; b.devices[0].hasKey=true; }
    return b;
}
std::vector<uint8_t> packet(std::initializer_list<uint8_t> objects, std::optional<uint32_t> counter={}) {
    std::vector<uint8_t> b={0,0x16,0xd2,0xfc,static_cast<uint8_t>(counter?0x41:0x40)};
    b.insert(b.end(),objects);
    if(counter) { for(unsigned i=0;i<4;++i) b.push_back(*counter>>(8*i)); b.insert(b.end(),4,0); }
    b[0]=b.size()-1; return b;
}
struct ObserverTest:testing::Test {
    ObserverCrypto crypto; ManagedBleBindings bindings=config(); ManagedBleObserver<ObserverCrypto> observer{crypto,observerClock};
    void SetUp() override { observerNow=1000; }
    void receive(const std::vector<uint8_t>& b,uint64_t at=1000) { observer.capture(bindings.devices[0].address,-60,b.data(),b.size(),at); observer.processOne(); }
    auto status() { return observer.snapshot(bindings.devices[0].address); }
};
TEST_F(ObserverTest, QueuedAgeIsOriginalAndPartialPacketsNeverRenewTemperature) {
    ASSERT_TRUE(observer.initialize(bindings));
    observerNow=1100; receive(packet({0x2e,45,0x45,235,0}));
    EXPECT_EQ(status().temperature,2350); EXPECT_EQ(status().temperatureAgeMs,100); EXPECT_EQ(status().humidity,4500);
    observerNow=180999; receive(packet({0x01,99}),180999);
    EXPECT_EQ(status().temperature,2350); EXPECT_EQ(status().temperatureAgeMs,179999);
    observerNow=181000; EXPECT_FALSE(status().temperature); EXPECT_EQ(status().battery,99);
    EXPECT_FALSE(status().measurementQualified); EXPECT_FALSE(status().authorizesActuation);
}
TEST_F(ObserverTest, QueueIsBoundedAndDoesNotProcessWhilePausedOrReviveExpiredFrames) {
    ASSERT_TRUE(observer.initialize(bindings)); auto b=packet({0x45,235,0});
    for(unsigned i=0;i<10;++i) observer.capture(bindings.devices[0].address,-60,b.data(),b.size(),1000);
    EXPECT_EQ(observer.queueDrops(),6u); observer.processOne(true); EXPECT_FALSE(status().temperature);
    observerNow=181000; for(unsigned i=0;i<4;++i) observer.processOne(); EXPECT_FALSE(status().temperature);
}
TEST_F(ObserverTest, RepeatedCounterNeverDecryptsAgainOrRefreshesAndFailureKeepsHighWater) {
    bindings=config(true); ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0},10));
    ASSERT_EQ(status().temperature,2350); EXPECT_TRUE(status().authenticated); EXPECT_EQ(crypto.calls,1u);
    observerNow=2000; receive(packet({0x45,240,0},10),2000);
    EXPECT_EQ(crypto.calls,1u); EXPECT_EQ(status().temperatureAgeMs,1000); EXPECT_EQ(status().oldCounterDrops,1u);
    crypto.result=BleCcmStatus::authentication_failed; receive(packet({0x45,240,0},11),2000);
    EXPECT_FALSE(status().temperature); EXPECT_EQ(status().status,BleObservationStatus::authentication_failed); EXPECT_EQ(status().counter,10);
    crypto.result=BleCcmStatus::authenticated; receive(packet({0x45,240,0},9),2000); EXPECT_FALSE(status().temperature);
    receive(packet({0x45,240,0},11),2000); EXPECT_EQ(status().temperature,2400); EXPECT_EQ(status().counter,11);
}
TEST_F(ObserverTest, ClockRollbackWithdrawsAndCannotBeReopened) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0})); ASSERT_TRUE(status().temperature);
    observerNow=999; EXPECT_EQ(status().status,BleObservationStatus::clock_invalid); EXPECT_FALSE(status().temperature);
    observerNow=3000; receive(packet({0x45,240,0}),3000); EXPECT_FALSE(status().temperature); EXPECT_FALSE(observer.initialize(bindings));
}
TEST_F(ObserverTest, FutureCallbackTimeFailsClosedAndConfigurationChangeDiscardsQueue) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0}),1001);
    EXPECT_EQ(status().status,BleObservationStatus::clock_invalid);
}
TEST_F(ObserverTest, DisableDiscardsQueuedAndPublishedValuesWithoutAutomaticRestart) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0}));
    auto b=packet({0x45,240,0}); observer.capture(bindings.devices[0].address,-60,b.data(),b.size(),1000);
    observer.disable(BleObserverStop::configuration_changed); observer.processOne();
    EXPECT_FALSE(status().temperature); EXPECT_EQ(status().status,BleObservationStatus::pending_restart); EXPECT_FALSE(observer.wantsAutomaticScan());
}
TEST_F(ObserverTest, MissingKeyAndPlaintextDowngradeNeverProduceValues) {
    bindings=config(true); bindings.devices[0].hasKey=false; ASSERT_TRUE(observer.initialize(bindings));
    EXPECT_EQ(status().status,BleObservationStatus::key_required); receive(packet({0x45,235,0},1));
    EXPECT_EQ(status().status,BleObservationStatus::key_required); EXPECT_EQ(crypto.calls,0u);
    receive(packet({0x45,235,0})); EXPECT_EQ(status().status,BleObservationStatus::encryption_required); EXPECT_FALSE(status().temperature);
}
TEST_F(ObserverTest, ForeignAddressAndUnrelatedServiceDoNotChangePublishedValues) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0}));
    auto b=packet({0x45,240,0}); auto other=bindings.devices[0].address; ++other[5];
    observer.capture(other,-60,b.data(),b.size(),1000); observer.processOne(); EXPECT_EQ(status().temperature,2350);
    receive({4,0x16,0x95,0xfe,0}); EXPECT_EQ(status().temperature,2350);
}
TEST_F(ObserverTest, PubliclyConstructedInvalidDTOsCannotBeEnabled) {
    bindings.devices[0].name.fill('x'); EXPECT_FALSE(observer.initialize(bindings)); EXPECT_FALSE(observer.enabled());
}
TEST_F(ObserverTest, ButtonAndIdentityHaveTheirOwnLifetime) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x3a,1,0xf0,0x0c,0,0xf1,1,2,3,4,0xf2,5,6,7}));
    EXPECT_EQ(status().button,1); EXPECT_EQ(status().declaredDeviceType,12);
    EXPECT_EQ(status().firmware32,0x04030201u); EXPECT_EQ(status().firmware24,0x070605u);
    observerNow=3000; EXPECT_FALSE(status().button); EXPECT_EQ(status().declaredDeviceType,12);
    observerNow=3901000; EXPECT_FALSE(status().declaredDeviceType); EXPECT_FALSE(status().firmware32); EXPECT_FALSE(status().firmware24);
}
static_assert(sizeof(ManagedBleObserver<ObserverCrypto>)<=4096,"observer resident budget changed");
}
