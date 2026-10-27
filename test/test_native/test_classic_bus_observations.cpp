#include "EMS/ClassicBusObservations.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>

namespace {
using namespace heating::ems;
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
Json snapshot(const ClassicBusObservations& o,uint64_t now){std::ostringstream out;o.writeJSON(out,now);return Json(cJSON_Parse(out.str().c_str()),cJSON_Delete);}
const cJSON* get(const cJSON* j,const char* key){return cJSON_GetObjectItemCaseSensitive(j,key);}
double number(const cJSON* j,const char* key){return cJSON_GetNumberValue(get(j,key));}

TEST(ClassicBusObservations, NothingObservedIsExplicitNull){
    const auto j=snapshot(ClassicBusObservations{},0);ASSERT_TRUE(j);
    EXPECT_TRUE(cJSON_IsNull(get(j.get(),"thermostat_setpoint")));
    EXPECT_TRUE(cJSON_IsNull(get(j.get(),"maintenance")));EXPECT_TRUE(cJSON_IsNull(get(j.get(),"last_error")));
    EXPECT_TRUE(cJSON_IsFalse(get(j.get(),"control_qualified")));
}
TEST(ClassicBusObservations, ThermostatSetpointIsRecordedButOurOwnAndBoilerFramesAreNot){
    ClassicBusObservations o;
    o.observe({EmsTelegram::WRITE,0x0b,0x08,0,0x1A,{50,100,100}},100);   // our trial request
    o.observe({EmsTelegram::WRITE,0x08,0x00,0,0x1A,{50,100,100}},100);   // not to the boiler
    o.observe({EmsTelegram::READ,0x17,0x08,0,0x1A,{3}},100);             // read request
    o.observe({EmsTelegram::WRITE,0x17,0x08,1,0x1A,{100}},100);          // partial at offset 1
    EXPECT_TRUE(cJSON_IsNull(get(snapshot(o,100).get(),"thermostat_setpoint")));
    o.observe({EmsTelegram::WRITE,0x17,0x08,0,0x1A,{42,255,60}},200);
    o.observe({EmsTelegram::WRITE,0x17,0x08,0,0x1A,{0,0,0}},150);        // older report cannot replace
    const auto j=snapshot(o,250);const auto* s=get(j.get(),"thermostat_setpoint");ASSERT_TRUE(cJSON_IsObject(s));
    EXPECT_EQ(number(s,"source_address"),0x17);EXPECT_EQ(number(s,"flow_c"),42);
    EXPECT_TRUE(cJSON_IsNull(get(s,"burner_power_percent")));EXPECT_EQ(number(s,"pump_percent"),60);
    EXPECT_EQ(number(s,"reports"),1);EXPECT_EQ(number(s,"age_ms"),50);
}
TEST(ClassicBusObservations, MaintenanceMessageUsesOffsetFive){
    ClassicBusObservations o;
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,0,0x1C,{0,0,0,0,0,0,0}},100);
    auto j=snapshot(o,100);const auto* m=get(j.get(),"maintenance");ASSERT_TRUE(cJSON_IsObject(m));
    EXPECT_TRUE(cJSON_IsNull(get(m,"message")));EXPECT_EQ(number(m,"code"),0);
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,5,0x1C,{3}},200);
    j=snapshot(o,200);EXPECT_STREQ(cJSON_GetStringValue(get(get(j.get(),"maintenance"),"message")),"H03");
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0x1C,{0,0,0,0,0,9}},300);
    j=snapshot(o,300);EXPECT_STREQ(cJSON_GetStringValue(get(get(j.get(),"maintenance"),"message")),"H03");
}
TEST(ClassicBusObservations, LastErrorKeepsTheNewestValidRecord){
    ClassicBusObservations o;
    // "6A" no. 227, 2026-10-27 14:05, 12 minutes.
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x10,{'6','A',0,227,26,10,14,27,5,0,12}},100);
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x11,{'2','E',0,207,25,1,9,3,0,0,1}},110);   // older: ignored
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x10,{'C','6',0,215,26,13,10,1,0,0,1}},120); // month 13: invalid
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x10,{0x01,'X',0,1,26,10,15,27,0,0,1}},130);  // not printable
    const auto j=snapshot(o,140);const auto* e=get(j.get(),"last_error");ASSERT_TRUE(cJSON_IsObject(e));
    EXPECT_STREQ(cJSON_GetStringValue(get(e,"code")),"6A");EXPECT_EQ(number(e,"number"),227);
    EXPECT_STREQ(cJSON_GetStringValue(get(e,"started")),"2026-10-27T14:05");EXPECT_EQ(number(e,"duration_min"),12);
}
}
