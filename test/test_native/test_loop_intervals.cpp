#include "diagnostics/LoopIntervals.h"
#include <gtest/gtest.h>
#include <cstdlib>
#include <limits>
using heating::diagnostics::LoopIntervals;

TEST(LoopIntervals, MissingFirstIntervalIsUnknownRatherThanZero) {
    LoopIntervals intervals;intervals.observe(100);
    EXPECT_EQ(intervals.snapshot().samples,0u);
    auto json=intervals.json();ASSERT_TRUE(json);
    for(const char* key:{"sampled_at_ms","last_ms","maximum_ms","window_maximum_ms"})
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(json.get(),key)));
}
TEST(LoopIntervals, ZeroMillisecondIntervalsAreRealObservations) {
    LoopIntervals intervals;intervals.observe(100);intervals.observe(100);
    const auto value=intervals.snapshot();EXPECT_EQ(value.samples,1u);
    EXPECT_EQ(value.lastMs,0u);EXPECT_EQ(value.maximumMs,0u);
    auto json=intervals.json();ASSERT_TRUE(json);
    EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(json.get(),"maximum_ms")));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(json.get(),"maximum_ms")),0);
}
TEST(LoopIntervals, DelaysIncludeExactThresholdsWithoutInventingPageOrCpuTiming) {
    LoopIntervals intervals;uint32_t now=0;intervals.observe(now);
    for(uint32_t interval:{0,99,100,499,500,999,1000}){now+=interval;intervals.observe(now);}
    const auto value=intervals.snapshot();EXPECT_EQ(value.samples,7u);
    EXPECT_EQ(value.lastMs,1000u);EXPECT_EQ(value.maximumMs,1000u);
    EXPECT_EQ(value.ge100Ms,5u);EXPECT_EQ(value.ge500Ms,3u);EXPECT_EQ(value.ge1000Ms,1u);
}
TEST(LoopIntervals, MinuteWindowRenewsWithoutErasingBootMaximumOrTotals) {
    LoopIntervals intervals;intervals.observe(1);intervals.observe(501);intervals.observe(60000);
    EXPECT_EQ(intervals.snapshot().windowMs,59999u);
    intervals.observe(60001);const auto value=intervals.snapshot();
    EXPECT_EQ(value.samples,3u);EXPECT_EQ(value.maximumMs,59499u);
    EXPECT_EQ(value.windowMs,0u);EXPECT_EQ(value.windowSamples,1u);EXPECT_EQ(value.windowMaximumMs,1u);
    EXPECT_EQ(value.ge1000Ms,1u);
}
TEST(LoopIntervals, UnsignedMillisRolloverDoesNotBecomeAnEnormousStall) {
    LoopIntervals intervals;intervals.observe(std::numeric_limits<uint32_t>::max()-99);
    intervals.observe(0);intervals.observe(1000);const auto value=intervals.snapshot();
    EXPECT_EQ(value.samples,2u);EXPECT_EQ(value.maximumMs,1000u);
    EXPECT_EQ(value.ge100Ms,2u);EXPECT_EQ(value.ge1000Ms,1u);EXPECT_EQ(value.windowMs,1100u);
}
TEST(LoopIntervals, DiagnosticReadsDoNotRenewOrResetObservation) {
    LoopIntervals intervals;intervals.observe(20);intervals.observe(150);
    for(unsigned i=0;i<50;++i){auto json=intervals.json();ASSERT_TRUE(json);}
    const auto value=intervals.snapshot();EXPECT_EQ(value.samples,1u);
    EXPECT_EQ(value.atMs,150u);EXPECT_EQ(value.maximumMs,130u);EXPECT_EQ(value.ge100Ms,1u);
}
namespace {
size_t allocations=0,live=0,failAt=0;
void* allocate(size_t size){if(allocations++==failAt)return nullptr;auto p=std::malloc(size);if(p)++live;return p;}
void release(void* value){if(value){--live;std::free(value);}}
struct RestoreJsonHooks {~RestoreJsonHooks(){cJSON_InitHooks(nullptr);}};
}
TEST(LoopIntervals, AllocationFailureCannotReturnPartialDiagnosticsOrLeak) {
    RestoreJsonHooks restore;cJSON_Hooks hooks{allocate,release};cJSON_InitHooks(&hooks);
    LoopIntervals intervals;intervals.observe(1);intervals.observe(501);bool completed=false;
    for(failAt=0;failAt<40;++failAt) {
        allocations=live=0;
        {auto json=intervals.json();
         if(json){completed=true;EXPECT_EQ(cJSON_GetArraySize(json.get()),11);}}
        EXPECT_EQ(live,0u);
    }
    EXPECT_TRUE(completed);
}
