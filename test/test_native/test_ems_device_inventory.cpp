#include "EMS/EmsDeviceInventory.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>

namespace {
using namespace heating::ems;
using JSON=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
JSON snapshot(const EmsDeviceInventory &inventory,uint64_t now){std::ostringstream out;inventory.writeJSON(out,now);return JSON(cJSON_Parse(out.str().c_str()),cJSON_Delete);}
EmsTelegram report(uint8_t source,uint16_t type=0x18,std::vector<uint8_t> bytes={1},uint8_t offset=0){return {EmsTelegram::BROADCAST,source,0,offset,type,std::move(bytes)};}
cJSON *first(const JSON &j){return cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(),"devices"),0);}
double number(cJSON *j,const char *key){return cJSON_GetObjectItem(j,key)->valuedouble;}
TEST(EmsDevices, OnlyReportSendersAppearAndAddressesRemainIndependent){
 EmsDeviceInventory i;i.observe({EmsTelegram::READ,0x10,8,0,0x18,{1}},100);i.observe({EmsTelegram::READ_WITH_DATA,0x11,8,0,0x18,{1}},100);i.observe(report(8,0x18,{}),100);i.observe(report(0),100);
 auto empty=snapshot(i,100);ASSERT_TRUE(empty);EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(empty.get(),"devices")),0);
 i.observe(report(8),100);i.observe(report(0x10,0x02,{123,1,2,0,0,0,0,0,0,5}),110);
 auto j=snapshot(i,120);ASSERT_TRUE(j);auto devices=cJSON_GetObjectItem(j.get(),"devices");ASSERT_EQ(cJSON_GetArraySize(devices),2);EXPECT_EQ(number(first(j),"address"),8);auto second=cJSON_GetArrayItem(devices,1);EXPECT_EQ(number(second,"address"),16);EXPECT_EQ(number(second,"product_id"),123);EXPECT_STREQ(cJSON_GetObjectItem(second,"version")->valuestring,"1.2");EXPECT_EQ(number(second,"brand_id"),5);EXPECT_EQ(number(second,"age_ms"),10);
}
TEST(EmsDevices, ContainsOnlyAddressesThatSentAValidatedReport){
 EmsDeviceInventory i;i.observe({EmsTelegram::READ,0x17,8,0,0x18,{1}},100);i.observe(report(0x10,0x18,{}),100);
 EXPECT_FALSE(i.contains(0x17));EXPECT_FALSE(i.contains(0x10));
 i.observe(report(0x17,0x1A,{0,0,0}),110);EXPECT_TRUE(i.contains(0x17));EXPECT_FALSE(i.contains(8));
}
TEST(EmsDevices, FragmentedVersionCannotAssembleAnInventedIdentity){
 EmsDeviceInventory i;i.observe(report(8,2,{123}),100);i.observe(report(8,2,{1,2},1),110);auto j=snapshot(i,120);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(first(j),"product_id")));
 i.observe(report(8,2,{123,1,2}),130);j=snapshot(i,140);EXPECT_EQ(number(first(j),"product_id"),123);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(first(j),"brand_id")));
 i.observe(report(8,2,{255,9,9}),150);j=snapshot(i,150);EXPECT_STREQ(cJSON_GetObjectItem(first(j),"version")->valuestring,"1.2");
}
TEST(EmsDevices, ReorderedReportCannotRefreshDeviceOrReplaceVersion){
 EmsDeviceInventory i;i.observe(report(8,2,{123,1,2}),100);i.observe(report(8,2,{99,9,9}),99);auto j=snapshot(i,120);EXPECT_EQ(number(first(j),"frames"),1);EXPECT_EQ(number(first(j),"age_ms"),20);EXPECT_EQ(number(first(j),"product_id"),123);auto future=snapshot(i,99);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(first(future),"age_ms")));
}
TEST(EmsDevices, DeviceAndTypeCapacityAreBoundedWithoutEvictingEvidence){
 EmsDeviceInventory i;for(unsigned a=1;a<=17;++a)i.observe(report(a),a);auto j=snapshot(i,30);EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j.get(),"devices")),16);EXPECT_EQ(number(j.get(),"untracked_frames"),1);
 for(unsigned type=0;type<EmsDeviceInventory::typesPerDevice+2;++type)i.observe(report(1,0x100+type),100+type);j=snapshot(i,120);EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(first(j),"telegram_types")),EmsDeviceInventory::typesPerDevice);EXPECT_EQ(number(first(j),"untracked_types"),3);i.observe(report(1),130);j=snapshot(i,130);EXPECT_EQ(number(first(j),"untracked_types"),3);
 EXPECT_LE(sizeof(EmsDeviceInventory),3072u);
}
}

TEST(EmsDevices, EmptyLeadingVersionTupleRequiresACompleteAlternativeTuple) {
 EmsDeviceInventory i;i.observe(report(0x17,2,{0,0,0}),100);
 auto j=snapshot(i,100);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(first(j),"product_id")));
 i.observe(report(0x17,2,{0,0,0,77,1}),110);
 j=snapshot(i,110);EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(first(j),"product_id")));
 i.observe(report(0x17,2,{0,0,0,77,1,2,0,0,0,4}),120);
 j=snapshot(i,120);EXPECT_EQ(number(first(j),"product_id"),77);
 EXPECT_STREQ(cJSON_GetObjectItem(first(j),"version")->valuestring,"1.2");
 EXPECT_EQ(number(first(j),"brand_id"),4);
}

TEST(EmsDevices, FullInventoryRemainsBoundedForTheHttpSnapshot) {
 EmsDeviceInventory inventory;
 for(unsigned address=1;address<=EmsDeviceInventory::capacity;++address)
  for(unsigned type=0;type<EmsDeviceInventory::typesPerDevice;++type)
   inventory.observe(report(uint8_t(address),uint16_t(0x100+type)),type+1);
 std::ostringstream out;inventory.writeJSON(out,1000);
 EXPECT_LT(out.str().size(),12000u);
 auto j=snapshot(inventory,1000);ASSERT_TRUE(j);
 EXPECT_EQ(number(j.get(),"types_per_device"),64);
 auto devices=cJSON_GetObjectItem(j.get(),"devices");
 ASSERT_EQ(cJSON_GetArraySize(devices),16);
 for(int index=0;index<16;++index) {
  auto device=cJSON_GetArrayItem(devices,index);
  EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(device,"telegram_types")),64);
  EXPECT_EQ(number(device,"untracked_types"),0);
 }
}
