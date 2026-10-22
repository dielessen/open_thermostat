#include "EmsMetrics.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <sstream>
#include <map>
using namespace heating::ems;
namespace {
const std::string boot(32,'a');
struct Observation {
    uint64_t now=100000;
    std::map<uint16_t,std::function<void(const EmsTelegram&)>> callbacks;
    EmsMetrics metrics{[this](uint16_t id,auto fn){callbacks[id]=fn;},[this]{return now;},boot};
    void send(uint8_t source=8,EmsTelegram::operation_t operation=EmsTelegram::BROADCAST,
              uint8_t offset=6,std::vector<uint8_t> bytes={60,2,88,0,50,3}) {
        callbacks.at(0xE4)(EmsTelegram(operation,source,0,offset,0xE4,std::move(bytes)));
    }
    std::string json() { std::ostringstream ss;metrics.getRoomObservation(ss);return ss.str(); }
};
double number(const std::string& text,const char* key) {
    auto* root=cJSON_Parse(text.c_str());if(!root)return -1;
    const auto* item=cJSON_GetObjectItemCaseSensitive(root,key);
    double value=cJSON_IsNumber(item)?item->valuedouble:-1;cJSON_Delete(root);return value;
}
TEST(RoomHeatObservation, ActualPlusOffsetsUnitsModesAndSequence) {
    Observation h;h.send();auto s=h.json();
    EXPECT_EQ(number(s,"supply_c"),60);EXPECT_EQ(number(s,"selected_flow_c"),60);
    EXPECT_EQ(number(s,"modulation_pct"),50);EXPECT_EQ(number(s,"sequence"),1);
    EXPECT_NE(s.find("\"ch\":true,\"dhw\":false,\"flame\":true"),std::string::npos);
    h.now+=1000;h.send(8,EmsTelegram::BROADCAST,6,{0,1,244,0,0,5});
    EXPECT_NE(h.json().find("\"ch\":false,\"dhw\":true,\"flame\":true"),std::string::npos);
}
TEST(RoomHeatObservation, GetAndPartialFramesNeverRenewObservation) {
    Observation h;h.send();const auto a=h.json();EXPECT_EQ(a,h.json());
    h.now+=29000;h.send(8,EmsTelegram::BROADCAST,10,{25,3});
    EXPECT_EQ(number(h.json(),"observed_ms"),100000);EXPECT_EQ(number(h.json(),"sequence"),1);
    h.now+=1000;auto s=h.json();
    EXPECT_NE(s.find("\"valid\":false"),std::string::npos);
    EXPECT_NE(s.find("\"supply_c\":null"),std::string::npos);
}
TEST(RoomHeatObservation, WrongSourceAndReadDoNotProduceEvidence) {
    Observation h;h.send(9);h.send(8,EmsTelegram::READ);h.send(8,EmsTelegram::READ_WITH_DATA);
    EXPECT_EQ(number(h.json(),"sequence"),0);
    EXPECT_NE(h.json().find("\"valid\":false"),std::string::npos);
}
TEST(RoomHeatObservation, SentinelPowerAndTemperatureInvalidateInsteadOfClipping) {
    for(auto bytes: {std::vector<uint8_t>{60,0x80,0,0,50,3},
                     std::vector<uint8_t>{255,2,88,0,50,3},
                     std::vector<uint8_t>{60,2,88,0,255,3}}) {
        Observation h;h.send();h.now+=100;h.send(8,EmsTelegram::BROADCAST,6,bytes);
        EXPECT_NE(h.json().find("\"valid\":false"),std::string::npos);
        EXPECT_EQ(number(h.json(),"sequence"),2);
    }
}
TEST(RoomHeatObservation, ClockRollbackFailsClosedAndBootIsStrictlyEncoded) {
    Observation h;h.send();h.now=99999;h.send();
    EXPECT_NE(h.json().find("\"valid\":false"),std::string::npos);
    RoomHeatObservation absent("invalid\"boot");
    auto t=EmsTelegram(EmsTelegram::BROADCAST,8,0,6,0xE4,std::vector<uint8_t>{60,2,88,0,50,3});
    absent.receive(0,t);std::ostringstream ss;absent.write(ss,0);
    EXPECT_NE(ss.str().find("\"boot_id\":\"\""),std::string::npos);
    EXPECT_NE(ss.str().find("\"valid\":false"),std::string::npos);
}
TEST(RoomHeatObservation, ZeroIsReportedNotMissingAndContextDoesNotTouchMetricsDefinition) {
    Observation h;h.send(8,EmsTelegram::BROADCAST,6,{0,0,0,0,0,0});
    EXPECT_EQ(number(h.json(),"supply_c"),0);EXPECT_EQ(number(h.json(),"modulation_pct"),0);
    std::ostringstream context,metrics;
    h.metrics.getRoomContext(context);h.metrics.getMetrics(metrics);
    EXPECT_EQ(number(context.str(),"source_ms"),100000);
    EXPECT_EQ(number(metrics.str(),"metricsSchema"),2);
    EXPECT_EQ(number(metrics.str(),"roomEstimateObservation"),-1);
}
}
