#include "diagnostics/ResponseBuffer.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/EmsDeviceInventory.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <cstdlib>
#include <memory>
#include <ostream>
#include <string>
using heating::diagnostics::ResponseBuffer;
namespace {
size_t allocations=0,releases=0,requested=0;
bool refuse=false;
void *allocate(size_t size){++allocations;requested=size;return refuse?nullptr:std::malloc(size);}
void release(void *bytes){++releases;std::free(bytes);}
void resetCounters(){allocations=releases=requested=0;refuse=false;}
}
TEST(ResponseBuffer, ReusesOneAllocationWithoutGrowingOrCopyingBetweenResponses) {
    resetCounters();
    {
        ResponseBuffer buffer(4096,allocate,release);const char *address=nullptr;
        for(int i=0;i<20;++i) {
            ASSERT_TRUE(buffer.reset());std::ostream out(&buffer);
            out<<"{\"value\":"<<i<<'}';out.flush();ASSERT_TRUE(out.good());
            const auto view=buffer.view();
            if(!address)address=view.data();
            EXPECT_EQ(view.data(),address);
            EXPECT_EQ(view,"{\"value\":"+std::to_string(i)+'}');
            EXPECT_EQ(allocations,1u);EXPECT_EQ(requested,4096u);EXPECT_EQ(releases,0u);
        }
    }
    EXPECT_EQ(releases,1u);
}
TEST(ResponseBuffer, ExactCapacitySucceedsButOneExtraByteInvalidatesTheWholeBody) {
    resetCounters();ResponseBuffer buffer(8,allocate,release);ASSERT_TRUE(buffer.reset());
    std::ostream out(&buffer);out<<"12345678";ASSERT_TRUE(out.good());EXPECT_EQ(buffer.view(),"12345678");
    out.put('9');EXPECT_FALSE(out.good());EXPECT_TRUE(buffer.failed());EXPECT_TRUE(buffer.view().empty());
    ASSERT_TRUE(buffer.reset());std::ostream retry(&buffer);retry<<"{}";EXPECT_TRUE(retry.good());
    EXPECT_EQ(buffer.view(),"{}");EXPECT_EQ(allocations,1u);
}
TEST(ResponseBuffer, OversizedBulkWritesAndInvalidSourcesNeverExposePartialJson) {
    resetCounters();ResponseBuffer buffer(8,allocate,release);ASSERT_TRUE(buffer.reset());
    std::ostream out(&buffer);out<<"{";out.write("0123456789",10);
    EXPECT_FALSE(out.good());EXPECT_TRUE(buffer.failed());EXPECT_TRUE(buffer.view().empty());
    ASSERT_TRUE(buffer.reset());EXPECT_EQ(buffer.sputn(nullptr,1),0);EXPECT_TRUE(buffer.failed());
    EXPECT_TRUE(buffer.view().empty());
}
TEST(ResponseBuffer, AllocationFailureIsExplicitAndRetryDoesNotLeakOrUseAnInternalFallback) {
    resetCounters();refuse=true;
    {
        ResponseBuffer buffer(ResponseBuffer::maximumCapacity,allocate,release);
        EXPECT_FALSE(buffer.reset());EXPECT_TRUE(buffer.failed());EXPECT_TRUE(buffer.view().empty());
        EXPECT_EQ(allocations,1u);EXPECT_EQ(requested,65536u);EXPECT_EQ(releases,0u);
        refuse=false;ASSERT_TRUE(buffer.reset());EXPECT_EQ(allocations,2u);
        std::ostream out(&buffer);out<<"{}";EXPECT_EQ(buffer.view(),"{}");
    }
    EXPECT_EQ(releases,1u);
}
TEST(ResponseBuffer, InvalidCapacityOrCallbacksNeverAllocate) {
    resetCounters();
    for(const auto size:{size_t(0),ResponseBuffer::maximumCapacity+1}) {
        ResponseBuffer buffer(size,allocate,release);EXPECT_FALSE(buffer.reset());
    }
    ResponseBuffer noAllocate(64,nullptr,release),noRelease(64,allocate,nullptr);
    EXPECT_FALSE(noAllocate.reset());EXPECT_FALSE(noRelease.reset());EXPECT_EQ(allocations,0u);
}
TEST(ResponseBuffer, AllMonitorFieldsAndMaximumDeviceTelegramInventoryFitWithHeadroom) {
    using namespace heating::ems;
    resetCounters();ResponseBuffer buffer(65536,allocate,release);ASSERT_TRUE(buffer.reset());
    ClassicBoilerMonitor monitor;EmsDeviceInventory inventory;
    for(auto type:{0x18,0x19,0x16,0x33,0x34})
        monitor.receive({EmsTelegram::BROADCAST,8,0,0,uint16_t(type),std::vector<uint8_t>(27,0)},100);
    for(uint8_t address=1;address<=16;++address)
        for(uint16_t type=0xf000;type<0xf040;++type)
            inventory.observe({EmsTelegram::BROADCAST,address,0,0,type,{1}},100);
    std::ostream out(&buffer);monitor.writeJSON(out,200,false);
    out<<",\"inventory\":";inventory.writeJSON(out,200);
    // Extra capacity for test/settings/transport metadata is bounded separately.
    out<<",\"additional_metadata_fixture\":\""<<std::string(8192,'p')<<"\"}";
    ASSERT_TRUE(out.good());EXPECT_FALSE(buffer.failed());
    EXPECT_LT(buffer.view().size(),32768u);EXPECT_EQ(allocations,1u);
    using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
    Json json(cJSON_Parse(std::string(buffer.view()).c_str()),cJSON_Delete);ASSERT_TRUE(json);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(json.get(),"fields")),69);
    auto devices=cJSON_GetObjectItem(cJSON_GetObjectItem(json.get(),"inventory"),"devices");
    ASSERT_EQ(cJSON_GetArraySize(devices),16);
    for(auto device=devices->child;device;device=device->next)
        EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(device,"telegram_types")),64);
}
