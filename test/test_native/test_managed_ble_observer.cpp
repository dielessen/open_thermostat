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
    observerNow=900999; receive(packet({0x01,99}),900999);
    EXPECT_EQ(status().temperature,2350); EXPECT_EQ(status().temperatureAgeMs,899999);
    EXPECT_EQ(status().status,BleObservationStatus::received);
    observerNow=901000; EXPECT_FALSE(status().temperature); EXPECT_EQ(status().battery,99);
    EXPECT_FALSE(status().measurementQualified); EXPECT_FALSE(status().authorizesActuation);
}
TEST_F(ObserverTest, QueueIsBoundedAndDoesNotProcessWhilePausedOrReviveExpiredFrames) {
    ASSERT_TRUE(observer.initialize(bindings)); auto b=packet({0x45,235,0});
    for(unsigned i=0;i<10;++i) observer.capture(bindings.devices[0].address,-60,b.data(),b.size(),1000);
    EXPECT_EQ(observer.queueDrops(),6u); observer.processOne(true); EXPECT_FALSE(status().temperature);
    observerNow=901000; for(unsigned i=0;i<4;++i) observer.processOne(); EXPECT_FALSE(status().temperature);
}
TEST_F(ObserverTest, RepeatedCounterNeverDecryptsAgainOrRefreshesAndFailureKeepsHighWater) {
    bindings=config(true); ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0},10));
    ASSERT_EQ(status().temperature,2350); EXPECT_TRUE(status().authenticated); EXPECT_EQ(crypto.calls,1u);
    observerNow=2000; receive(packet({0x45,240,0},10),2000);
    EXPECT_EQ(crypto.calls,1u); EXPECT_EQ(status().temperatureAgeMs,1000); EXPECT_EQ(status().oldCounterDrops,1u);
    // A failed (or forged) frame keeps the accepted reading; it is reported, not obeyed.
    crypto.result=BleCcmStatus::authentication_failed; receive(packet({0x45,240,0},11),2000);
    EXPECT_EQ(status().temperature,2350); EXPECT_EQ(status().status,BleObservationStatus::received); EXPECT_EQ(status().counter,10);
    EXPECT_EQ(status().lastRejection,BleObservationStatus::authentication_failed); EXPECT_EQ(status().framesRejected,1u);
    crypto.result=BleCcmStatus::authenticated; receive(packet({0x45,250,0},9),2000); EXPECT_EQ(status().temperature,2350);
    receive(packet({0x45,240,0},11),2000); EXPECT_EQ(status().temperature,2400); EXPECT_EQ(status().counter,11);
}
TEST_F(ObserverTest, ClockRollbackWithdrawsAndRecoversOnTheNextValidClock) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0})); ASSERT_TRUE(status().temperature);
    auto queued=packet({0x45,230,0}); observer.capture(bindings.devices[0].address,-60,queued.data(),queued.size(),1000);
    observerNow=999; auto s=status(); EXPECT_EQ(s.status,BleObservationStatus::clock_invalid); EXPECT_FALSE(s.temperature);
    observer.processOne(); s=status(); EXPECT_EQ(s.status,BleObservationStatus::clock_invalid); EXPECT_FALSE(s.temperature); // queued frame was discarded
    // Formerly a permanent stop until the E32 restarted.
    observerNow=3000; receive(packet({0x45,240,0}),3000); EXPECT_EQ(status().temperature,2400);
    EXPECT_EQ(status().status,BleObservationStatus::received); EXPECT_FALSE(observer.initialize(bindings));
}
TEST_F(ObserverTest, FutureCallbackTimeFailsClosedAndConfigurationChangeDiscardsQueue) {
    ASSERT_TRUE(observer.initialize(bindings)); receive(packet({0x45,235,0}),1001);
    EXPECT_EQ(status().status,BleObservationStatus::clock_invalid); EXPECT_FALSE(status().temperature);
    observerNow=2000; receive(packet({0x45,235,0}),2000); EXPECT_EQ(status().temperature,2350);
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
TEST_F(ObserverTest, CaptureReportsBoundSensorsOnly) {
    ASSERT_TRUE(observer.initialize(bindings)); auto b=packet({0x45,235,0}); auto other=bindings.devices[0].address; ++other[5];
    EXPECT_TRUE(observer.capture(bindings.devices[0].address,-60,b.data(),b.size(),1000));
    EXPECT_FALSE(observer.capture(other,-60,b.data(),b.size(),1000));
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
TEST_F(ObserverTest, TrvTemperatureInstancesStaySeparateAndMissingExternalWithdrawsOnlyThatField) {
    bindings.devices[0].profile=ManagedBleProfile::shellyTrv;ASSERT_TRUE(observer.initialize(bindings));
    receive(packet({0x45,220,0,0x45,215,0,0x45,200,0,0x54,1,63}));
    auto s=status();ASSERT_EQ(s.temperature,2150);EXPECT_EQ(s.targetTemperature,2200);EXPECT_EQ(s.externalTemperature,2000);EXPECT_EQ(s.stateRevision,63);
    observerNow=2000;receive(packet({1,90}),2000);s=status();EXPECT_EQ(s.temperatureAgeMs,1000);EXPECT_EQ(s.targetTemperatureAgeMs,1000);EXPECT_EQ(s.externalTemperatureAgeMs,1000);
    observerNow=3000;receive(packet({0x45,225,0,0x45,216,0}),3000);s=status();EXPECT_EQ(s.targetTemperature,2250);EXPECT_EQ(s.temperature,2160);EXPECT_FALSE(s.externalTemperature);EXPECT_FALSE(s.externalTemperatureAgeMs);EXPECT_EQ(s.stateRevisionAgeMs,2000);
    // Reported TRV state expires after 3 min; the measured temperature lasts 15 min.
    observerNow=183000;s=status();EXPECT_EQ(s.temperature,2160);EXPECT_FALSE(s.targetTemperature);EXPECT_FALSE(s.stateRevision);EXPECT_FALSE(s.authorizesActuation);EXPECT_FALSE(s.measurementQualified);
    observerNow=903000;s=status();EXPECT_FALSE(s.temperature);EXPECT_EQ(s.status,BleObservationStatus::stale);
}
TEST_F(ObserverTest, TrvMalformedReportKeepsEveryFieldWithoutRenewingTheOldCounter) {
    bindings=config(true);bindings.devices[0].profile=ManagedBleProfile::shellyTrv;ASSERT_TRUE(observer.initialize(bindings));
    receive(packet({0x45,220,0,0x45,215,0},10));ASSERT_EQ(status().temperature,2150);
    observerNow=2000;receive(packet({0x45,225,0},11),2000);auto s=status();EXPECT_EQ(s.status,BleObservationStatus::received);
    EXPECT_EQ(s.lastRejection,BleObservationStatus::malformed);EXPECT_EQ(s.temperature,2150);EXPECT_EQ(s.temperatureAgeMs,1000);EXPECT_EQ(s.targetTemperature,2200);EXPECT_EQ(s.counter,10u);
    observerNow=3000;receive(packet({0x45,221,0,0x45,216,0},10),3000);EXPECT_EQ(status().temperature,2150);EXPECT_EQ(status().counter,10u);
    // Values still end with their own lifetime.
    observerNow=901000;EXPECT_FALSE(status().temperature);EXPECT_EQ(status().status,BleObservationStatus::stale);
}
TEST_F(ObserverTest, FailureBeforeAnyAcceptedFrameIsTheStatus) {
    bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
    crypto.result=BleCcmStatus::authentication_failed;receive(packet({0x45,235,0},5));
    EXPECT_EQ(status().status,BleObservationStatus::authentication_failed);EXPECT_FALSE(status().temperature);
}
TEST_F(ObserverTest, RestartedCounterIsReanchoredAfterQuietPeriodAndThreeRisingFrames) {
    bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
    receive(packet({0x45,235,0},5000));ASSERT_EQ(status().counter,5000u);ASSERT_EQ(crypto.calls,1u);
    constexpr uint64_t quiet=ManagedBleObserver<ObserverCrypto>::reanchorQuietMs;
    // Sensor battery swapped: its counter starts again at 1.
    uint64_t t=2000;uint32_t c=1;
    const auto send=[&](uint32_t counter,uint8_t lo){observerNow=t;receive(packet({0x45,lo,0},counter),t);};
    send(c++,240);EXPECT_EQ(status().temperature,2350);EXPECT_EQ(crypto.calls,1u); // too soon: no decrypt at all
    // Within the quiet period every old counter stays rejected without AES work.
    for(t=60000;t<1000+quiet;t+=60000)send(c++,240);
    EXPECT_EQ(crypto.calls,1u);EXPECT_EQ(status().counter,5000u);
    t=1000+quiet;
    send(c++,241);EXPECT_EQ(status().counter,5000u);EXPECT_EQ(crypto.calls,2u);
    t+=1000;send(c++,242);EXPECT_EQ(status().counter,5000u);EXPECT_EQ(crypto.calls,2u); // spaced: one decrypt per 5 s
    t+=5000;send(c++,243);EXPECT_EQ(status().counter,5000u);
    t+=5000;send(c++,244);EXPECT_EQ(status().counter,c-1);EXPECT_EQ(status().counterResets,1u);
    EXPECT_EQ(status().status,BleObservationStatus::received);EXPECT_EQ(status().temperatureAgeMs,0u);
    // The new sequence is protected again: an old frame is rejected before AES.
    const auto calls=crypto.calls;t+=1000;send(c-3,245);EXPECT_EQ(crypto.calls,calls);
}
TEST_F(ObserverTest, ReplayedOldFramesOutOfOrderNeverReanchor) {
    bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
    receive(packet({0x45,235,0},5000));
    uint64_t t=1000+ManagedBleObserver<ObserverCrypto>::reanchorQuietMs;
    for(uint32_t counter:{10u,9u,11u,8u,12u,7u,13u,6u}){observerNow=t;receive(packet({0x45,200,0},counter),t);t+=6000;}
    EXPECT_EQ(status().counter,5000u);EXPECT_EQ(status().counterResets,0u);
}
TEST_F(ObserverTest, ReplayOfTheHighWaterFrameNeverCompletesAReanchor) {
    bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
    const auto last=packet({0x45,235,0},5000);receive(last);ASSERT_EQ(status().counter,5000u);
    // The sensor restarted its counter; after the quiet period it starts a run.
    uint64_t t=1000+ManagedBleObserver<ObserverCrypto>::reanchorQuietMs;
    const auto send=[&](const std::vector<uint8_t>& b){observerNow=t;receive(b,t);};
    send(packet({0x45,240,0},10));t+=5000;send(packet({0x45,240,0},11));
    // A replay of the last accepted frame is never the third frame of the run,
    // never decrypted and never a fresh reading.
    t+=5000;const auto calls=crypto.calls,drops=status().oldCounterDrops;send(last);
    auto s=status();EXPECT_EQ(s.counter,5000u);EXPECT_EQ(s.counterResets,0u);EXPECT_EQ(crypto.calls,calls);
    EXPECT_EQ(s.oldCounterDrops,drops+1);EXPECT_EQ(s.temperature,2350);EXPECT_EQ(s.temperatureAgeMs,t-1000);
    // It neither breaks the run nor uses up the spacing: the real sensor's next frame re-anchors at once.
    send(packet({0x45,241,0},12));s=status();
    EXPECT_EQ(s.counter,12u);EXPECT_EQ(s.counterResets,1u);EXPECT_EQ(s.temperature,2410);EXPECT_EQ(s.temperatureAgeMs,0u);
    t+=5000;send(packet({0x45,242,0},13));EXPECT_EQ(status().counter,13u);EXPECT_EQ(status().temperature,2420);
}
TEST_F(ObserverTest, ReanchorRunNeedsSmallStepsSoOldFramesCannotCompleteIt) {
    bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
    receive(packet({0x45,235,0},5000));
    constexpr uint32_t step=ManagedBleObserver<ObserverCrypto>::reanchorMaxStep;
    uint64_t t=1000+ManagedBleObserver<ObserverCrypto>::reanchorQuietMs;
    const auto send=[&](uint32_t counter,uint8_t lo){observerNow=t;receive(packet({0x45,lo,0},counter),t);t+=5000;};
    // Two genuine frames, then an authenticated frame from the old sequence (below the high-water mark).
    send(10,240);send(11,240);send(4990,200);
    EXPECT_EQ(status().counter,5000u);EXPECT_EQ(status().counterResets,0u);EXPECT_EQ(status().temperature,2350);
    // The real sensor starts a new run and re-anchors on its third frame; missed adverts up to the step are fine.
    send(12,241);EXPECT_EQ(status().counter,5000u);
    send(12+step+1,242);EXPECT_EQ(status().counter,5000u); // too big a jump: the run starts again here
    send(12+step+2,243);EXPECT_EQ(status().counter,5000u);
    send(12+2*step+2,244);EXPECT_EQ(status().counter,12+2*step+2);EXPECT_EQ(status().counterResets,1u);EXPECT_EQ(status().temperature,2440);
}
// Re-anchored from the old sequence (high-water 5000) to the real sensor's 10, 11, 12.
struct RetiredSequenceTest:ObserverTest {
    static constexpr uint64_t quiet=ManagedBleObserver<ObserverCrypto>::reanchorQuietMs;
    static constexpr uint32_t step=ManagedBleObserver<ObserverCrypto>::reanchorMaxStep;
    uint64_t t=0;
    void send(uint32_t counter,uint8_t lo){observerNow=t;receive(packet({0x45,lo,0},counter),t);}
    void reanchorTo12(){
        bindings=config(true);ASSERT_TRUE(observer.initialize(bindings));
        receive(packet({0x45,235,0},5000));ASSERT_EQ(status().counter,5000u);
        t=1000+quiet;send(10,240);t+=5000;send(11,240);t+=5000;send(12,240);
        ASSERT_EQ(status().counter,12u);ASSERT_EQ(status().counterResets,1u);ASSERT_EQ(status().temperatureAgeMs,0u);
    }
};
TEST_F(RetiredSequenceTest, ReplaysFromTheOldSequenceAreDroppedWithoutLockout) {
    reanchorTo12();const uint64_t anchoredAt=t;
    const auto calls=crypto.calls;
    t+=1000;send(5000,235);t+=1000;send(4999,230);
    auto s=status();EXPECT_EQ(s.counter,12u);EXPECT_EQ(s.temperature,2400);EXPECT_EQ(s.temperatureAgeMs,2000u);
    EXPECT_EQ(crypto.calls,calls); // within the quiet period: rejected before AES
    t+=1000;send(13,241);EXPECT_EQ(status().counter,13u);EXPECT_EQ(status().temperature,2410);
    t+=1000;send(14,242);EXPECT_EQ(status().counter,14u);EXPECT_EQ(status().temperatureAgeMs,0u);
    // Even after a quiet period one replay is decrypted but never accepted, and
    // the real sensor's next frame is accepted at once.
    t=anchoredAt+5000+quiet;send(5000,235);s=status();
    EXPECT_EQ(crypto.calls,calls+3);EXPECT_EQ(s.counter,14u);EXPECT_EQ(s.counterResets,1u);EXPECT_FALSE(s.temperature==2350);
    t+=1000;send(15,243);EXPECT_EQ(status().counter,15u);EXPECT_EQ(status().temperature,2430);EXPECT_EQ(status().temperatureAgeMs,0u);
}
TEST_F(RetiredSequenceTest, NewSequenceClimbingPastTheRetiredMarkRestoresNormalChecks) {
    reanchorTo12();
    // A jump beyond the step is not news while the old sequence could be replayed...
    t+=1000;send(12+step+1,250);EXPECT_EQ(status().counter,12u);
    // ...but small steps are, all the way past the old high-water mark.
    uint32_t c=12;
    while(c<=5000){c+=step;t+=1000;send(c,241);ASSERT_EQ(status().counter,c);}
    EXPECT_EQ(status().temperatureAgeMs,0u);EXPECT_EQ(status().counterResets,1u);
    // Past it, a large forward jump (a sensor that was out of range) is accepted again as before.
    t+=1000;send(c+100000,244);EXPECT_EQ(status().counter,c+100000);EXPECT_EQ(status().temperature,2440);
}
TEST_F(RetiredSequenceTest, RealJumpWhileRetiredReanchorsAfterQuietPeriodAndKeepsOldSequenceRetired) {
    reanchorTo12();
    // The real sensor was out of range for hours and comes back far ahead (still below 5000).
    t+=quiet;send(2000,245);EXPECT_EQ(status().counter,12u);
    t+=5000;send(2001,246);EXPECT_EQ(status().counter,12u);
    t+=5000;send(2002,247);EXPECT_EQ(status().counter,2002u);EXPECT_EQ(status().temperature,2470);EXPECT_EQ(status().counterResets,2u);
    // The old sequence above it is still retired.
    t+=1000;send(5000,235);EXPECT_EQ(status().counter,2002u);EXPECT_EQ(status().temperature,2470);
    t+=1000;send(2003,248);EXPECT_EQ(status().counter,2003u);
}
