#include "EMS/ClassicHeatTrialEnvelope.h"
#include "EMS/BoilerTestService.h"
#include "EMS/BoilerTestPollDriver.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include "BoilerTestIoFixture.h"
#include <gtest/gtest.h>
namespace {
using namespace heating::ems;
struct HeatEnvelope:testing::Test {
    ClassicBoilerMonitor monitor;
    void fast(uint64_t at,uint16_t tenths=200,uint8_t pressure=15) {
        std::vector<uint8_t> data(18,0);data[1]=tenths>>8;data[2]=tenths&255;data[3]=80;data[17]=pressure;
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,std::move(data)},at);
    }
    void settings(uint64_t at,uint8_t enabled=255,uint8_t limit=80) {
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x16,{enabled,limit}},at);
    }
    void SetUp()override{fast(100);settings(100);}
    auto check(uint64_t at){return ClassicHeatTrialEnvelope::inspect(monitor,at);}
};
TEST_F(HeatEnvelope, ConcreteProfileKeepsExistingZeroPolicyAndBoundsHeatRequests){
    const auto p=ClassicHeatTrialEnvelope::profile();const auto z=BoilerTestSession::Profile::supervisedZeroOnly();
    EXPECT_TRUE(p.valid());EXPECT_EQ(p.minimumFlowC,40);EXPECT_EQ(p.maximumFlowC,45);EXPECT_EQ(p.maximumHeatMs,60000u);
    EXPECT_EQ(p.stopTimeoutMs,z.stopTimeoutMs);EXPECT_EQ(p.reportTtlMs,z.reportTtlMs);
    EXPECT_EQ(p.operatorLeaseMs,z.operatorLeaseMs);EXPECT_EQ(p.writeIntervalMs,z.writeIntervalMs);
    EXPECT_TRUE(check(101).ready);
    for(int target:{39,46}){BoilerTestSession s{42,p};EXPECT_EQ(s.prepare(42,1,target,1000,101,{true,true,true,true,true},monitor),BoilerTestSession::Reply::refused);}
    BoilerTestSession s{42,p};EXPECT_EQ(s.prepare(42,1,40,60001,101,{true,true,true,true,true},monitor),BoilerTestSession::Reply::refused);
}
TEST_F(HeatEnvelope, UnknownPlusAndConflictingFamiliesNeverUseClassicLimits){
    ClassicBoilerMonitor unknown;EXPECT_FALSE(ClassicHeatTrialEnvelope::inspect(unknown,101).ready);
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0xe4,{0}},101);EXPECT_FALSE(check(101).ready);
}
TEST_F(HeatEnvelope, TemperatureLimitsAreAppliedToMeasuredWaterNotRequestedSetpoint){
    for(uint16_t value:{uint16_t(49),uint16_t(500),uint16_t(600)}){fast(101+value,value);EXPECT_FALSE(check(101+value).ready);}
    for(uint16_t value:{uint16_t(50),uint16_t(499)}){ClassicBoilerMonitor fresh;monitor=std::move(fresh);settings(100);fast(101,value);EXPECT_TRUE(check(101).ready);}
}
TEST_F(HeatEnvelope, PressureBoundsRejectZeroLowHighAndMissingSentinel){
    for(uint8_t pressure:{0,9,26,254,255}){fast(101+pressure,200,pressure);EXPECT_FALSE(check(101+pressure).ready);}
    for(uint8_t pressure:{10,25}){ClassicBoilerMonitor fresh;monitor=std::move(fresh);settings(100);fast(101,200,pressure);EXPECT_TRUE(check(101).ready);}
}
TEST_F(HeatEnvelope, AbsentPressureAndInvalidTemperatureNeverBecomeUsableZeroes){
    ClassicBoilerMonitor absent;
    absent.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,0,200,80,0,0}},100);
    EXPECT_STREQ(ClassicHeatTrialEnvelope::inspect(absent,101).reason,"pressure_unavailable");
    fast(101,0x7fff);EXPECT_STREQ(check(101).reason,"flow_unavailable");
}
TEST_F(HeatEnvelope, FutureOrExpiredLiveReportsRemovePermissionAtBoundary){
    EXPECT_FALSE(check(99).ready);EXPECT_TRUE(check(15099).ready);EXPECT_FALSE(check(15100).ready);
    fast(15101);EXPECT_TRUE(check(15101).ready);
}
TEST_F(HeatEnvelope, HeatingEnabledAndConfiguredLimitMustBeReportedAndFresh){
    settings(101,0);EXPECT_STREQ(check(101).reason,"heating_disabled");
    settings(102,1);EXPECT_STREQ(check(102).reason,"heating_setting_unavailable");
    settings(103,255,44);EXPECT_STREQ(check(103).reason,"heating_limit_outside_trial_limits");
    settings(104,255,45);EXPECT_TRUE(check(104).ready);
    settings(105,255,91);EXPECT_FALSE(check(105).ready);
    settings(106,255,255);EXPECT_STREQ(check(106).reason,"heating_limit_unavailable");
}
TEST_F(HeatEnvelope, ConfiguredLimitExpiryIsIndependentOfFreshFastReports){
    fast(600099);EXPECT_TRUE(check(600099).ready);
    fast(600100);EXPECT_FALSE(check(600100).ready);
    settings(600101);EXPECT_TRUE(check(600101).ready);
}
// Actual passive Ecomline snapshot: type16 offset1 with one byte (55C).
// A temperature response says nothing about byte0 or its acquisition time.
TEST_F(HeatEnvelope, ObservedPartialConfigurationCannotInventHeatingEnable) {
    monitor = ClassicBoilerMonitor{};
    fast(100);
    ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE,8,0x17,1,0x16,{55}},100));
    EXPECT_EQ(monitor.sample(BoilerField::heatingLimit).raw,5500);
    EXPECT_FALSE(monitor.sample(BoilerField::heatingEnabled).observed);
    EXPECT_STREQ(check(101).reason,"heating_setting_unavailable");
}
TEST_F(HeatEnvelope, RepeatedPartialConfigurationDoesNotRenewOldEnable) {
    fast(600100);
    ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE,8,0x17,1,0x16,{55}},600100));
    EXPECT_EQ(monitor.sample(BoilerField::heatingEnabled).observedMs,100u);
    EXPECT_EQ(monitor.sample(BoilerField::heatingLimit).observedMs,600100u);
    EXPECT_STREQ(check(600100).reason,"heating_setting_unavailable");
    // A real full boiler report, addressed to another bus participant, can
    // complete the passive picture; it does not grant installation permission.
    ASSERT_TRUE(monitor.receive({EmsTelegram::WRITE,8,0x17,0,0x16,{255,55}},600101));
    EXPECT_TRUE(check(600101).ready);
}
TEST_F(HeatEnvelope, ConfigurationReadRequestIsNotBoilerResponse) {
    monitor = ClassicBoilerMonitor{};
    fast(100);
    EXPECT_FALSE(monitor.receive({EmsTelegram::READ,8,0x17,0,0x16,{255,55}},100));
    EXPECT_FALSE(monitor.sample(BoilerField::heatingEnabled).observed);
    EXPECT_STREQ(check(101).reason,"heating_setting_unavailable");
}
TEST_F(HeatEnvelope, SameTimestampConflictingPressureCannotRestorePermission){
    fast(101,200,15);ASSERT_TRUE(check(101).ready);
    fast(101,200,0);EXPECT_FALSE(check(101).ready);
    fast(101,200,15);EXPECT_FALSE(check(101).ready);
    fast(102,200,15);EXPECT_TRUE(check(102).ready);
}
TEST_F(HeatEnvelope, ProfileAndHealthyNumbersCannotOverrideUnreviewedInstallation){
    const auto p=ClassicHeatTrialEnvelope::profile();BoilerTestService service{42,true,p,true,true};
    const std::string owner(64,'a');
    const auto heat=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":60,"exclusive_owner_confirmed":true,"independent_stop_confirmed":true,"heat_path_confirmed":true})";
    const BoilerTestSession::Gates gates{true,false,false,check(101).ready,false};
    EXPECT_EQ(service.action("prepare",heat,owner,101,gates,monitor).http,409);
    EXPECT_FALSE(service.active());
}
struct HeatEnvelopeIo:HeatEnvelope {
    uint64_t now=101;BoilerTestService service{42,true,ClassicHeatTrialEnvelope::profile(),true};
    const std::string owner=std::string(64,'a');
    const std::string scope=R"({"schema":1,"boot_id":"000000000000002a","revision":1})";
    BoilerTestSession::Gates gates(){return {true,true,true,check(now).ready,true};} // explicitly qualified fake setup
    void heat(){
        const auto body=R"({"schema":1,"boot_id":"000000000000002a","revision":1,"flow_c":40,"duration_s":60})";
        ASSERT_EQ(service.action("prepare",body,owner,now,gates(),monitor).http,202);
        auto zero=service.next(now,gates(),monitor);ASSERT_TRUE(testing_detail::instantTransmission(service,zero,now,true,gates(),monitor));
        ++now;fast(now);service.tick(now,gates(),monitor);
        ASSERT_EQ(service.action("start",scope,owner,now,gates(),monitor).http,202);
    }
    static bool encode(const BoilerTestSession::Intent& intent,EmsRawFrame& frame){return ClassicBoilerTestEncoder::encode(ClassicBoilerTestEncoder::Addressing::classicService(),intent,frame);}
};
TEST_F(HeatEnvelopeIo, PressureLossAtFinalAdmissionBlocksPositiveButAllowsZero){
    heat();int writes=0;
    // Mutate telemetry between selection and the final serialized admission.
    unsigned reads=0;
    const auto gate=[&]{if(++reads==2){++now;fast(now,200,0);}return gates();};
    auto result=BoilerTestPollDriver::poll(service,monitor,[&]{return now;},gate,encode,[&](const EmsRawFrame&){++writes;return true;});
    EXPECT_EQ(result,BoilerTestPollDriver::Result::rejected);EXPECT_EQ(writes,0);
    result=BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{return gates();},encode,[&](const EmsRawFrame& frame){++writes;EXPECT_EQ(frame.data[4],0);return true;});
    EXPECT_EQ(result,BoilerTestPollDriver::Result::sent);EXPECT_EQ(writes,1);
}
TEST_F(HeatEnvelopeIo, OvertemperatureDuringPositiveWriteCannotDelayImmediateWithdrawal){
    heat();int writes=0;
    auto result=BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{return gates();},encode,[&](const EmsRawFrame& frame){++writes;EXPECT_EQ(frame.data[4],40);++now;fast(now,500);return true;});
    EXPECT_EQ(result,BoilerTestPollDriver::Result::sent);
    result=BoilerTestPollDriver::poll(service,monitor,[&]{return now;},[&]{return gates();},encode,[&](const EmsRawFrame& frame){++writes;EXPECT_EQ(frame.data[4],0);return true;});
    EXPECT_EQ(result,BoilerTestPollDriver::Result::sent);EXPECT_EQ(writes,2);
}
}
