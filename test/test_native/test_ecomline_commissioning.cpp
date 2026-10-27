#include "EMS/EcomlineCommissioningProfile.h"
#include "EMS/ClassicBoilerTestEncoder.h"
#include <gtest/gtest.h>
#include <sstream>

namespace {
using namespace heating::ems;
struct EcomlineCommissioning:testing::Test {
    ClassicBoilerMonitor monitor;
    BoilerTestService service=EcomlineCommissioningProfile::service(42,true);
    std::string owner=std::string(64,'a');uint64_t now=100;
    void fast(uint64_t at,uint16_t tenths=200) {
        // No digital pressure byte. Reported zero flow demand, modulation and
        // CV/DHW state; the measured water temperature is 20 C.
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,uint8_t(tenths>>8),uint8_t(tenths),80,0,0}},at);
    }
    void SetUp()override{fast(now);monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x16,{255,80}},now);}
    auto gates(){return EcomlineCommissioningProfile::gates(monitor,now,true,service.heating());}
    std::string scope(){return "{\"schema\":1,\"boot_id\":\"000000000000002a\",\"revision\":1";}
    std::string heat(std::string pressure="15", int target=40, int seconds=10) {
        return scope()+",\"flow_c\":"+std::to_string(target)+",\"duration_s\":"+std::to_string(seconds)+",\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true,\"heat_path_confirmed\":true,\"pressure_check_confirmed\":true,\"pressure_decibar\":"+pressure+"}";
    }
    auto action(const char* name,const std::string& body){return service.action(name,body,owner,now,gates(),monitor);}
    auto transmit(BoilerTestSession::Command expected) {
        const auto intent=service.next(now,gates(),monitor);EXPECT_EQ(intent.command,expected);
        EmsRawFrame frame;EXPECT_TRUE(ClassicBoilerTestEncoder::encode(ClassicBoilerTestEncoder::Addressing::classicService(),intent,frame));
        EXPECT_EQ(frame.length,6);EXPECT_EQ(frame.data[2],0x1a);
        EXPECT_TRUE(service.beginTransmit(intent,now,gates(),monitor));++now;
        EXPECT_TRUE(service.finishTransmit(intent,now,true,gates(),monitor));return intent;
    }
    void ready() {
        ASSERT_EQ(action("prepare",heat()).http,202);transmit(BoilerTestSession::Command::zero);
        ++now;fast(now);service.tick(now,gates(),monitor);
    }
};
TEST_F(EcomlineCommissioning, RealReleaseProfileCanPrepareBaselineHeatAndStopWithoutDigitalPressure) {
    ASSERT_TRUE(EcomlineCommissioningProfile::inspect(monitor,now).ready);
    ASSERT_FALSE(monitor.sample(BoilerField::pressure).raw);
    ready();ASSERT_EQ(action("start",scope()+"}").http,202);
    const auto positive=transmit(BoilerTestSession::Command::positive);EXPECT_EQ(positive.flowC,40);
    ASSERT_EQ(action("stop",scope()+"}").http,202);transmit(BoilerTestSession::Command::zero);
    ++now;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
    std::ostringstream out;service.writeJSON(out,now,owner,gates(),monitor);
    const auto json=heating::control::parseControlJson(out.str());ASSERT_TRUE(json);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json.get(),"reported_stop_confirmed")));
    const auto* observation=cJSON_GetObjectItemCaseSensitive(json.get(),"operator_pressure_observation");
    ASSERT_TRUE(cJSON_IsObject(observation));EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(observation,"value_decibar")->valuedouble,15);
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(observation,"physical_validation")));
    EXPECT_FALSE(monitor.sample(BoilerField::pressure).observed);
}
TEST_F(EcomlineCommissioning, EachHeatPreparationRequiresBoundedNumericGaugeAndAllDeclarations) {
    for(const auto* value:{"10","26","0","1.5","true","null","\"15\""}) {
        EXPECT_EQ(action("prepare",heat(value)).http,400)<<value;EXPECT_FALSE(service.active());
    }
    auto missing=heat();missing.erase(missing.find(",\"pressure_decibar\""),std::string::npos);missing+='}';
    EXPECT_EQ(action("prepare",missing).http,400);
    for(const auto* name:{"exclusive_owner_confirmed","independent_stop_confirmed","heat_path_confirmed","pressure_check_confirmed"}) {
        auto body=heat();body.replace(body.find("true",body.find(name)),4,"false");
        EXPECT_EQ(action("prepare",body).http,400);EXPECT_FALSE(service.active());
    }
    EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
}
TEST_F(EcomlineCommissioning, ZeroTrialDoesNotRequireGaugeButStillNeedsOwnerAndIndependentStop) {
    EXPECT_EQ(action("prepare_zero",scope()+",\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":false}").http,400);
    ASSERT_EQ(action("prepare_zero",scope()+",\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true}").http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());EXPECT_NE(action("start",scope()+"}").http,202);
}
TEST_F(EcomlineCommissioning, GaugeExpiresDespiteKeepalivesAndDuplicateRequestsNeverRenewIt) {
    ready();EXPECT_TRUE(action("prepare",heat()).duplicate);
    EXPECT_EQ(action("prepare",heat("16")).http,409);
    while(now<120099) {
        now=std::min<uint64_t>(now+4000,120099);fast(now);
        ASSERT_EQ(action("keepalive",scope()+"}").http,202);
    }
    ++now;fast(now);
    EXPECT_NE(action("start",scope()+"}").http,202);
    EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::zero);
}

struct EcomlineWaterTemperature:EcomlineCommissioning,testing::WithParamInterface<uint16_t> {};
TEST_P(EcomlineWaterTemperature, FiftyDegreesIsRepeatedEveryMinuteForTenMinutesWithImmediateDeadlineZero) {
    // Settings almost ten minutes old are admitted once, then retained only
    // for this finite run. Live feedback and supervision stay fresh throughout.
    now=599000;fast(now,GetParam());
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now,GetParam());service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    const auto started=now;uint64_t lastCompletion=0;unsigned positives=0;
    for(uint64_t elapsed=1;elapsed<600000;elapsed+=1000) {
        now=started+elapsed;fast(now,GetParam());
        ASSERT_EQ(action("keepalive",scope()+"}").http,202);
        ASSERT_TRUE(service.heating())<<elapsed;
        if(!positives || now-lastCompletion>=60000) {
            const auto intent=transmit(BoilerTestSession::Command::positive);
            EXPECT_EQ(intent.flowC,50);lastCompletion=now;++positives;
        } else EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none)<<elapsed;
    }
    EXPECT_EQ(positives,10u);
    now=started+600000;fast(now,GetParam());service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.heating());
    transmit(BoilerTestSession::Command::zero);
    EXPECT_TRUE(service.active()); // Transmission is not later stop feedback.
    ++now;fast(now,GetParam());service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());
    EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
    EXPECT_NE(action("start",scope()+"}").http,202); // No restart/extension.
}
TEST_F(EcomlineCommissioning, MinuteRefreshDoesNotDelayManualStop) {
    ready();ASSERT_EQ(action("start",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::positive);
    now+=1000;fast(now);ASSERT_EQ(action("keepalive",scope()+"}").http,202);
    EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
    ASSERT_EQ(action("stop",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::zero);
    ++now;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());
}
TEST_F(EcomlineCommissioning, MinuteRefreshDoesNotDelayWithdrawalOnLostSupervision) {
    ready();ASSERT_EQ(action("start",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::positive);
    now+=5000;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.heating());transmit(BoilerTestSession::Command::zero);
    ++now;fast(now);service.tick(now,gates(),monitor);EXPECT_FALSE(service.active());
}
TEST_F(EcomlineCommissioning, SameFiftyDegreeValueIsActuallyTransmittedAgainAfterOneMinute) {
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now);service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::positive);const auto completion=now;
    for(unsigned elapsed=1000;elapsed<60000;elapsed+=1000) {
        now=completion+elapsed;fast(now);
        ASSERT_EQ(action("keepalive",scope()+"}").http,202);
        EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
    }
    now=completion+59999;fast(now);ASSERT_EQ(action("keepalive",scope()+"}").http,202);
    EXPECT_EQ(service.next(now,gates(),monitor).command,BoilerTestSession::Command::none);
    now=completion+60000;fast(now);
    EXPECT_EQ(transmit(BoilerTestSession::Command::positive).flowC,50);
    const auto latest=service.next(now,gates(),monitor);EXPECT_EQ(latest.command,BoilerTestSession::Command::none);
}
TEST_F(EcomlineCommissioning, StatusAdvertisesTheActualMinuteRefreshIndependentlyOfOperatorLease) {
    std::ostringstream out;service.writeJSON(out,now,owner,gates(),monitor);
    const auto json=heating::control::parseControlJson(out.str());ASSERT_TRUE(json);
    const auto* limits=cJSON_GetObjectItemCaseSensitive(json.get(),"limits");ASSERT_TRUE(cJSON_IsObject(limits));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(limits,"heat_request_interval_ms")),60000);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(limits,"operator_lease_ms")),5000);
}
INSTANTIATE_TEST_SUITE_P(ColdAndAlreadyWarmWater,EcomlineWaterTemperature,testing::Values(uint16_t(200),uint16_t(660),uint16_t(850)));
TEST_F(EcomlineCommissioning, TenMinuteRequestStillStopsOnLostSupervision) {
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now);service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    const auto started=now;
    for(unsigned elapsed=1000;elapsed<=180000;elapsed+=1000) {
        now=started+elapsed;fast(now,500);
        ASSERT_EQ(action("keepalive",scope()+"}").http,202);
    }
    ASSERT_TRUE(service.heating()); // Gauge does not abort an admitted run at2min.
    now+=5000;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.heating());
    transmit(BoilerTestSession::Command::zero);
    ++now;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());
}

TEST_F(EcomlineCommissioning, ExplicitStopWithdrawsLongDemandBeforeDeadline) {
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now);service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::positive);
    ASSERT_EQ(action("stop",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::zero);
    ++now;fast(now);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.active());
}
TEST_F(EcomlineCommissioning, WarmWaterWithinTrialWindowCanReceiveLowerTargetButCutoffStillWithdraws) {
    ++now;fast(now,660);ASSERT_TRUE(EcomlineCommissioningProfile::inspect(monitor,now).ready);
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    transmit(BoilerTestSession::Command::zero);++now;fast(now,660);service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    transmit(BoilerTestSession::Command::positive);
    ++now;fast(now,900);service.tick(now,gates(),monitor);
    EXPECT_FALSE(service.heating());
    transmit(BoilerTestSession::Command::zero);
}

TEST_F(EcomlineCommissioning, LongTrialRejectsExcessDurationAndTemperature) {
    EXPECT_EQ(action("prepare",heat("20",50,601)).http,400);
    EXPECT_EQ(action("prepare",heat("20",51,600)).http,409);
    EXPECT_FALSE(service.active());
}

TEST_F(EcomlineCommissioning, CompiledOffTransportLossAndWrongFamilyRemainClosed) {
    auto disabled=EcomlineCommissioningProfile::service(42,false);
    EXPECT_EQ(disabled.action("prepare",heat(),owner,now,gates(),monitor).http,409);
    auto lost=EcomlineCommissioningProfile::gates(monitor,now,false);
    EXPECT_EQ(service.action("prepare",heat(),owner,now,lost,monitor).http,409);
    ClassicBoilerMonitor unknown;
    EXPECT_FALSE(EcomlineCommissioningProfile::gates(unknown,now,true).allowsZero());
    EXPECT_FALSE(EcomlineCommissioningProfile::inspect(unknown,now).ready);
}
TEST_F(EcomlineCommissioning, SentRequestIsSeparateFromReceivedTargetAndUpdatesOnlyAfterUartCompletion) {
    const auto command=[&]{std::ostringstream out;service.writeCommandJSON(out,now);return heating::control::parseControlJson(out.str());};
    auto initial=command();ASSERT_TRUE(initial);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(initial.get(),"known")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(initial.get(),"value_c")));
    fast(++now,660);ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    auto queued=command();EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(queued.get(),"value_c")));
    transmit(BoilerTestSession::Command::zero);
    fast(++now,660);service.tick(now,gates(),monitor);
    ASSERT_EQ(action("start",scope()+"}").http,202);
    auto before=command();EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(before.get(),"value_c")->valuedouble,0);
    transmit(BoilerTestSession::Command::positive);
    auto sent=command();EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(sent.get(),"value_c")->valuedouble,50);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(sent.get(),"boiler_readback")));
    EXPECT_EQ(monitor.sample(BoilerField::selectedFlow).raw,0); // actual received fields stay separate
    EXPECT_EQ(monitor.sample(BoilerField::flow).raw,6600);
    ASSERT_EQ(action("stop",scope()+"}").http,202);
    auto stopping=command();EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(stopping.get(),"value_c")->valuedouble,50);
    transmit(BoilerTestSession::Command::zero);
    auto stopped=command();EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(stopped.get(),"value_c")->valuedouble,0);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(stopped.get(),"sequence")->valuedouble,3);
}
TEST_F(EcomlineCommissioning, FailedTransmissionDoesNotInventACommandValue) {
    ASSERT_EQ(action("prepare",heat("20",50,600)).http,202);
    const auto intent=service.next(now,gates(),monitor);ASSERT_TRUE(service.beginTransmit(intent,now,gates(),monitor));
    EXPECT_FALSE(service.finishTransmit(intent,++now,false,gates(),monitor));
    std::ostringstream out;service.writeCommandJSON(out,now);const auto value=heating::control::parseControlJson(out.str());
    ASSERT_TRUE(value);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(value.get(),"value_c")));
}

TEST_F(EcomlineCommissioning, ATransportFaultDuringWithdrawalRetainsTheInitiatingOperatorStop) {
    ready();ASSERT_EQ(action("start",scope()+"}").http,202);transmit(BoilerTestSession::Command::positive);
    ASSERT_EQ(action("stop",scope()+"}").http,202);
    service.transportFault(++now);
    std::ostringstream out;service.writeJSON(out,now,owner,gates(),monitor);
    const auto value=heating::control::parseControlJson(out.str());ASSERT_TRUE(value);
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(value.get(),"reason")->valuestring,"test_transport_unavailable");
    const auto* progress=cJSON_GetObjectItemCaseSensitive(value.get(),"progress");
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(progress,"end_reason")->valuestring,"explicit_stop");
    transmit(BoilerTestSession::Command::zero);
}

}
