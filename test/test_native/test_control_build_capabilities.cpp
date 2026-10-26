#include "control/ControlBuildCapabilities.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <string>

namespace {
using namespace heating::control;
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
Json capabilities() {
    std::ostringstream out;writeControlBuildCapabilities(out);
    return Json(cJSON_Parse(out.str().c_str()),cJSON_Delete);
}
const cJSON* field(const cJSON* value,const char* name) {return cJSON_GetObjectItemCaseSensitive(value,name);}

TEST(ControlBuildCapabilities, DiscoveryNeverClaimsCurrentSelectionOrPhysicalAuthority) {
    auto value=capabilities();ASSERT_TRUE(value);
    EXPECT_STREQ(cJSON_GetStringValue(field(value.get(),"scope")),"compiled_support_only");
    EXPECT_TRUE(cJSON_IsTrue(field(value.get(),"requires_local_source_selection")));
    EXPECT_TRUE(cJSON_IsFalse(field(value.get(),"authorizes_physical_outputs")));
    for(auto key:{"controller_id","adapter_id","profile_digest","grant_id","config_digest","selected","ready","enabled","password"})
        EXPECT_EQ(field(value.get(),key),nullptr);
    EXPECT_EQ(cJSON_GetNumberValue(field(value.get(),"config_bytes")),ShadowController::maximumConfigBytes);
}
TEST(ControlBuildCapabilities, AdvertisedSettingsBoundaryIsTheActualSavedSettingsBoundary) {
    auto value=capabilities();ASSERT_TRUE(value);
    const auto bound=static_cast<size_t>(cJSON_GetNumberValue(field(value.get(),"settings_bytes_exclusive")));
    ASSERT_EQ(bound,2048u);
    EXPECT_FALSE(nativeNetworkSettingsBytesFit(""));
    EXPECT_TRUE(nativeNetworkSettingsBytesFit(std::string(bound-1,' ')));
    EXPECT_FALSE(nativeNetworkSettingsBytesFit(std::string(bound,' ')));
}
TEST(ControlBuildCapabilities, NativeAndWeekLimitsRemainDistinctAndDoNotAdvertiseEightZoneProductGoal) {
    auto value=capabilities();ASSERT_TRUE(value);
    const auto plans=field(value.get(),"plans");ASSERT_EQ(cJSON_GetArraySize(plans),2);
    const auto native=cJSON_GetArrayItem(plans,0),week=cJSON_GetArrayItem(plans,1);
    EXPECT_STREQ(cJSON_GetStringValue(field(native,"contract")),NativePlanInstallationSource::contract);
    EXPECT_STREQ(cJSON_GetStringValue(field(week,"contract")),NativePlanInstallationSource::weekContract);
    EXPECT_EQ(cJSON_GetNumberValue(field(native,"minimum_zones")),2);
    EXPECT_EQ(cJSON_GetNumberValue(field(native,"maximum_zones")),2);
    EXPECT_EQ(cJSON_GetNumberValue(field(native,"maximum_total_transitions")),8);
    EXPECT_EQ(cJSON_GetNumberValue(field(week,"minimum_zones")),1);
    EXPECT_EQ(cJSON_GetNumberValue(field(week,"maximum_zones")),2);
    EXPECT_EQ(cJSON_GetNumberValue(field(week,"maximum_transitions_per_zone")),128);
    EXPECT_EQ(cJSON_GetNumberValue(field(week,"maximum_total_transitions")),256);
    EXPECT_EQ(cJSON_GetNumberValue(field(week,"maximum_horizon_seconds")),16*86400);
    const auto formats=field(value.get(),"source_formats");ASSERT_EQ(cJSON_GetArraySize(formats),3);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(formats,0)),nativeLocalSourceFormat);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(formats,1)),nativeWeekSourceFormat);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetArrayItem(formats,2)),nativeEvolutionSourceFormat);
}
}
