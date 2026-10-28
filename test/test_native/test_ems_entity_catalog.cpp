#include "EMS/EmsEntityCatalog.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <set>
#include <sstream>
#include <string>

namespace {
using namespace heating::ems;
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
Json snapshot(const EmsEntityObserver& o,uint64_t now){std::ostringstream out;o.writeJSON(out,now);return Json(cJSON_Parse(out.str().c_str()),cJSON_Delete);}

TEST(EmsEntityCatalog, RowsAreUniquePerTypeOffsetAndBitAndUseKnownUnits){
    std::set<std::string> keys;
    for(const auto& spec:entityCatalog){
        ASSERT_TRUE(keys.insert(std::to_string(spec.type)+":"+std::to_string(spec.offset)+":"+std::to_string(spec.bit)+":"+spec.id).second) << spec.id;
        EXPECT_GT(spec.divisor,0);EXPECT_LE(spec.minimum,spec.maximum);EXPECT_GT(spec.ttlMs,0u);
        const std::string unit=spec.unit;
        EXPECT_TRUE(unit=="degC"||unit=="%"||unit=="bool"||unit=="bar"||unit=="uA"||unit=="starts"||unit=="min"||unit=="L/min"||unit=="code") << spec.id;
    }
}
TEST(EmsEntityCatalog, Rc10MonitorFromTheThermostatGivesSetpointAndRoomTemperature){
    EmsEntityObserver o;
    // 0x17 -> all, 0xB1: mode, setpoint 41 (20.5 C), room 0x00CD (20.5 C).
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0xB1,{0x04,41,0x00,0xCD,0,0}},100);
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_setpoint",200),20.5);
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_room_temperature",200),20.5);
    EXPECT_FALSE(o.value(0x17,"thermostat_room_temperature",100+monitorTtl).has_value());
}
TEST(EmsEntityCatalog, ThermostatRequestToTheBoilerIsReadButOurOwnTrialRequestIsNot){
    EmsEntityObserver o;
    o.observe({EmsTelegram::WRITE,0x0b,0x08,0,0x1A,{50,100,100}},100);   // our trial request
    EXPECT_FALSE(o.value(0x0b,"thermostat_requested_flow_temperature",100));
    o.observe({EmsTelegram::WRITE,0x17,0x08,0,0x1A,{42,255,60}},200);
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_requested_flow_temperature",250),42);
    EXPECT_FALSE(o.value(0x17,"thermostat_requested_burner_power",250));  // 0xFF: not set
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_requested_pump_modulation",250),60);
}
TEST(EmsEntityCatalog, MaintenanceMessageIsReadFromTheBoilerAtOffsetFive){
    EmsEntityObserver o;
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,0,0x1C,{0,0,0,0,0,0,0}},100);
    EXPECT_DOUBLE_EQ(*o.value(8,"maintenance_message",100),0);
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,5,0x1C,{3}},200);
    EXPECT_DOUBLE_EQ(*o.value(8,"maintenance_message",200),3);
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0x1C,{0,0,0,0,0,9}},300);
    EXPECT_FALSE(o.value(0x17,"maintenance_message",300));
}
TEST(EmsEntityCatalog, ThermostatRowsNeverComeFromTheBoilerOrServiceAddress){
    EmsEntityObserver o;
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,0,0xB1,{0,41,0,205}},100);
    o.observe({EmsTelegram::WRITE,0x0b,0x08,0,0xB1,{0,41,0,205}},100);
    o.observe({EmsTelegram::READ,0x17,0x08,0,0xB1,{4}},100);
    EXPECT_FALSE(o.value(0x08,"thermostat_setpoint",100));EXPECT_FALSE(o.value(0x0b,"thermostat_setpoint",100));
    EXPECT_FALSE(o.value(0x17,"thermostat_setpoint",100));
}
TEST(EmsEntityCatalog, NotSetMarkersAndOutOfRangeValuesBecomeNullNotZero){
    EmsEntityObserver o;
    // Room 0x7D00 = thermostat mounted on the boiler; setpoint 0xFF not set.
    o.observe({EmsTelegram::BROADCAST,0x10,0x00,0,0x3E,{0,0,0xFF,0x7D,0x00,0,0,0,0,0,0,0,0,0,0x58}},100);
    EXPECT_FALSE(o.value(0x10,"thermostat_room_temperature",100));EXPECT_FALSE(o.value(0x10,"thermostat_setpoint",100));
    EXPECT_DOUBLE_EQ(*o.value(0x10,"thermostat_target_flow_temperature",100),88);
    const auto j=snapshot(o,100);const auto* devices=cJSON_GetObjectItem(j.get(),"devices");ASSERT_EQ(cJSON_GetArraySize(devices),1);
    const auto* entities=cJSON_GetObjectItem(cJSON_GetArrayItem(devices,0),"entities");
    bool sawNull=false;for(int i=0;i<cJSON_GetArraySize(entities);++i)sawNull|=cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetArrayItem(entities,i),"value"));
    EXPECT_TRUE(sawNull);EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(j.get(),"verified_on_hardware")));
}
TEST(EmsEntityCatalog, EmsPlusBoilerMonitorFastDecodesFlowModulationAndFlags){
    EmsEntityObserver o;
    std::vector<uint8_t> fast(33,0);
    fast[6]=55;fast[7]=0x01;fast[8]=0xF4;fast[9]=80;fast[10]=37;fast[11]=0b101;fast[17]=0;fast[18]=0;fast[21]=15;
    o.observe({EmsTelegram::BROADCAST,0x08,0x00,0,0xE4,fast},100);
    EXPECT_DOUBLE_EQ(*o.value(8,"plus_flow_temperature",100),50.0);
    EXPECT_DOUBLE_EQ(*o.value(8,"plus_burner_modulation",100),37);
    EXPECT_DOUBLE_EQ(*o.value(8,"plus_burner_on",100),1);EXPECT_DOUBLE_EQ(*o.value(8,"plus_dhw_valve",100),1);
    EXPECT_DOUBLE_EQ(*o.value(8,"plus_pressure",100),1.5);
    EXPECT_FALSE(o.value(8,"plus_return_temperature",100)); // 0 = no sensor
    // A Plus row is never taken from a thermostat sender.
    o.observe({EmsTelegram::BROADCAST,0x10,0x00,0,0xE4,fast},100);EXPECT_FALSE(o.value(0x10,"plus_flow_temperature",100));
}
TEST(EmsEntityCatalog, PartialFrameOnlyUpdatesRowsItCoversAndOlderReportsCannotReplace){
    EmsEntityObserver o;
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0xB1,{4,40,0x00,0xC8}},200);
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,2,0xB1,{0x00,0xD2}},300);       // offset 2 only: room
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_setpoint",300),20.0);
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_room_temperature",300),21.0);
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0xB1,{4,30,0x00,0x64}},150);   // older than both rows
    EXPECT_DOUBLE_EQ(*o.value(0x17,"thermostat_setpoint",300),20.0);
}
TEST(EmsEntityCatalog, CapacityIsBoundedAndCountsDroppedRows){
    EmsEntityObserver o;
    for(uint8_t address=0x10;address<0x10+EmsEntityObserver::capacity;++address)
        o.observe({EmsTelegram::BROADCAST,address,0x00,0,0xB1,{4,40,0x00,0xC8}},100+address);
    const auto j=snapshot(o,200);
    EXPECT_GT(cJSON_GetNumberValue(cJSON_GetObjectItem(j.get(),"dropped")),0);
}
}
