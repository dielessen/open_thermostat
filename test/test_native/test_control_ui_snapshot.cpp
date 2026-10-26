#include "control/ControlUiSnapshot.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <atomic>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
namespace {
using heating::control::ControlUiSnapshot;
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
Json read(const ControlUiSnapshot& cache,uint64_t now,bool connected=true) {
    std::ostringstream out;cache.write(out,now,connected);
    return Json(cJSON_Parse(out.str().c_str()),cJSON_Delete);
}
const cJSON* field(const Json& value,const char* name) {return cJSON_GetObjectItemCaseSensitive(value.get(),name);}
const char* sample=R"({"zones":[{"zone_id":"014005ea","demand":true}],"boiler_output_enabled":false})";
TEST(ControlUiSnapshot, MissingReadbackDoesNotInventDemandOrAuthority) {
    ControlUiSnapshot cache;auto value=read(cache,100);
    ASSERT_TRUE(value);EXPECT_TRUE(cJSON_IsFalse(field(value,"available")));
    EXPECT_TRUE(cJSON_IsFalse(field(value,"fresh")));EXPECT_TRUE(cJSON_IsNull(field(value,"state")));
    EXPECT_LE(sizeof(cache),4200u);
}
TEST(ControlUiSnapshot, OnlyExistingOwnerStateIsCopiedAndOtherTopicsCannotRenewItsAge) {
    ControlUiSnapshot cache;
    ASSERT_TRUE(cache.capture("fw/state/zones",sample,100));
    EXPECT_FALSE(cache.capture("fw/session",R"({"grant_id":"not_a_dashboard_field"})",4000));
    auto value=read(cache,4999);ASSERT_TRUE(value);
    EXPECT_TRUE(cJSON_IsTrue(field(value,"fresh")));
    EXPECT_EQ(cJSON_GetNumberValue(field(value,"age_ms")),4899);
    const auto state=field(value,"state");ASSERT_TRUE(cJSON_IsObject(state));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(state,"boiler_output_enabled")));
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(state,"zones")),1);
}
TEST(ControlUiSnapshot, ExactDeadlineAndDisconnectSuppressOldState) {
    ControlUiSnapshot cache;ASSERT_TRUE(cache.capture("fw/state/zones",sample,100));
    auto before=read(cache,5099);EXPECT_TRUE(cJSON_IsTrue(field(before,"fresh")));
    auto exact=read(cache,5100);ASSERT_TRUE(exact);
    EXPECT_TRUE(cJSON_IsFalse(field(exact,"fresh")));EXPECT_TRUE(cJSON_IsNull(field(exact,"state")));
    EXPECT_STREQ(cJSON_GetStringValue(field(exact,"reason")),"stale");
    auto offline=read(cache,101,false);EXPECT_TRUE(cJSON_IsNull(field(offline,"state")));
    EXPECT_STREQ(cJSON_GetStringValue(field(offline,"reason")),"source_disconnected");
}
TEST(ControlUiSnapshot, ClockReversalAndSourceReplacementDoNotReviveOldDemand) {
    ControlUiSnapshot cache;ASSERT_TRUE(cache.capture("fw/state/zones",sample,UINT64_MAX-1));
    auto reversed=read(cache,0);ASSERT_TRUE(reversed);
    EXPECT_STREQ(cJSON_GetStringValue(field(reversed,"reason")),"clock_reset");
    EXPECT_TRUE(cJSON_IsNull(field(reversed,"state")));EXPECT_TRUE(cJSON_IsNull(field(reversed,"age_ms")));
    cache.clear();auto cleared=read(cache,UINT64_MAX);
    EXPECT_TRUE(cJSON_IsFalse(field(cleared,"available")));EXPECT_TRUE(cJSON_IsNull(field(cleared,"state")));
}
TEST(ControlUiSnapshot, PayloadBudgetIsFixedAndOverflowDoesNotExposeTheEarlierSnapshot) {
    ControlUiSnapshot cache;
    const std::string prefix="{\"payload\":\"",suffix="\"}";
    auto bytes=prefix+std::string(ControlUiSnapshot::maximumBytes-prefix.size()-suffix.size(),'x')+suffix;
    ASSERT_EQ(bytes.size(),ControlUiSnapshot::maximumBytes);
    ASSERT_TRUE(cache.capture("fw/state/zones",bytes,10));ASSERT_TRUE(read(cache,11));
    bytes.insert(12,"x");EXPECT_FALSE(cache.capture("fw/state/zones",bytes,12));
    auto overflow=read(cache,13);ASSERT_TRUE(overflow);
    EXPECT_TRUE(cJSON_IsFalse(field(overflow,"available")));EXPECT_TRUE(cJSON_IsNull(field(overflow,"state")));
    EXPECT_STREQ(cJSON_GetStringValue(field(overflow,"reason")),"snapshot_too_large");
}
TEST(ControlUiSnapshot, EmptyOrTruncatedTrustedMessagesCannotExposePreviousDemand) {
    ControlUiSnapshot cache;
    for(const auto invalid:{"","[1,2]","{\"zones\":["}) {
        ASSERT_TRUE(cache.capture("fw/state/zones",sample,10));
        EXPECT_FALSE(cache.capture("fw/state/zones",invalid,11));
        auto value=read(cache,12);EXPECT_TRUE(cJSON_IsNull(field(value,"state")));
    }
}
TEST(ControlUiSnapshot, ConcurrentDashboardReadsNeverObserveAPartialOwnerMessage) {
    ControlUiSnapshot cache;std::atomic<bool> failed{false};
    const std::string one=R"({"zones":[],"marker":"first"})",two=R"({"zones":[],"marker":"second"})";
    std::thread writer([&]{for(unsigned i=0;i<1000;++i)cache.capture("fw/state/zones",i%2?one:two,i);});
    for(unsigned i=0;i<1000;++i) {
        auto value=read(cache,1000);if(!value) {failed=true;continue;}
        const auto state=field(value,"state");
        if(cJSON_IsObject(state)) {
            const auto marker=cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(state,"marker"));
            if(!marker||(std::string(marker)!="first"&&std::string(marker)!="second"))failed=true;
        }
    }
    writer.join();EXPECT_FALSE(failed);
}
}
