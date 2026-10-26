#include <gtest/gtest.h>
#include <limits>
#include "control/DeviceDiagnostics.h"
#include <cJSON.h>
using heating::control::deviceDiagnosticsJson;
TEST(DeviceDiagnostics, OwnResourcesAndLongUptimeAreValidJson) {
    auto raw=deviceDiagnosticsJson(95000,65000,81000,48.5,5000000);
    auto root=cJSON_Parse(raw.c_str()); ASSERT_NE(root,nullptr);
    EXPECT_EQ(cJSON_GetArraySize(root),6);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(root,"mem_free")->valuedouble,95000);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(root,"uptime")->valuedouble,5000000);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(root,"cpu_temperature")->valuedouble,48.5);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(root,"temperature")));
    cJSON_Delete(root);
}
TEST(DeviceDiagnostics, UnsupportedCpuNeverCorruptsOtherMeasurements) {
    for(float cpu:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),151.f,-41.f}) {
        auto raw=deviceDiagnosticsJson(90000,60000,80000,cpu,0);
        auto root=cJSON_Parse(raw.c_str()); ASSERT_NE(root,nullptr);
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(root,"cpu_temperature")));
        EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(root,"mem_free")->valuedouble,90000);
        cJSON_Delete(root);
    }
}
