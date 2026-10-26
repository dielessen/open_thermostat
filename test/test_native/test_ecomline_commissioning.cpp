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
    void fast(uint64_t at) {
        // No digital pressure byte. Reported zero flow demand, modulation and
        // CV/DHW state; the measured water temperature is 20 C.
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,0,200,80,0,0}},at);
    }
    void SetUp()override{fast(now);monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x16,{255,80}},now);}
    auto gates(){return EcomlineCommissioningProfile::gates(monitor,now,true);}
    std::string scope(){return "{\"schema\":1,\"boot_id\":\"000000000000002a\",\"revision\":1";}
    std::string heat(std::string pressure="15") {
        return scope()+",\"flow_c\":40,\"duration_s\":10,\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true,\"heat_path_confirmed\":true,\"pressure_check_confirmed\":true,\"pressure_decibar\":"+pressure+"}";
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
TEST_F(EcomlineCommissioning, CompiledOffTransportLossAndWrongFamilyRemainClosed) {
    auto disabled=EcomlineCommissioningProfile::service(42,false);
    EXPECT_EQ(disabled.action("prepare",heat(),owner,now,gates(),monitor).http,409);
    auto lost=EcomlineCommissioningProfile::gates(monitor,now,false);
    EXPECT_EQ(service.action("prepare",heat(),owner,now,lost,monitor).http,409);
    ClassicBoilerMonitor unknown;
    EXPECT_FALSE(EcomlineCommissioningProfile::gates(unknown,now,true).allowsZero());
    EXPECT_FALSE(EcomlineCommissioningProfile::inspect(unknown,now).ready);
}
}
