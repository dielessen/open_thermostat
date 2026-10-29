#include <gtest/gtest.h>
#include <limits>
#include "control/DeviceDiagnostics.h"
#include "DeviceIdentity.h"
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
// A new install is named after the end of its MAC address, as printed, so two
// controllers differ on the network and on the MQTT broker.
TEST(DeviceIdentity, DefaultNameUsesTheLastThreeMacBytes) {
    // MAC 24:6f:28:a1:b2:c3: ESP.getEfuseMac() keeps byte 0 in the lowest bits.
    const uint64_t efuse = 0x24ull | 0x6full << 8 | 0x28ull << 16 | 0xa1ull << 24 | 0xb2ull << 32 | 0xc3ull << 40;
    EXPECT_EQ(heating::defaultDeviceName(efuse), "openthermostat-a1b2c3");
    EXPECT_NE(heating::defaultDeviceName(efuse), heating::defaultDeviceName(efuse ^ (1ull << 40)));
    EXPECT_EQ(heating::defaultDeviceName(efuse & 0xffffff), "openthermostat-000000"); // same vendor prefix only
    EXPECT_LE(heating::defaultDeviceName(~0ull).size(), 21u); // within the 32-char hostname/clientId limits
}

// esp32dev/esp32s3 without a stored access point: the E32 setup Wi-Fi name and
// documented password, never the old shared "IntuiBaseHeating" pair.
TEST(DeviceIdentity, SetupWifiMatchesTheE32SetupNetwork) {
    const uint64_t efuse = 0x24ull | 0x6full << 8 | 0x28ull << 16 | 0xa1ull << 24 | 0xb2ull << 32 | 0xc3ull << 40;
    EXPECT_EQ(heating::setupWifiName(efuse), "OpenThermostat-a1b2c3");
    EXPECT_NE(heating::setupWifiName(efuse), heating::setupWifiName(efuse ^ (1ull << 24)));
    EXPECT_LE(heating::setupWifiName(~0ull).size(), 31u); // the E32 formats it into char[32]
    EXPECT_STREQ(heating::setupWifiPassword, "openthermostat");
    EXPECT_GE(std::string(heating::setupWifiPassword).size(), 8u); // WPA2 minimum: softAP refuses shorter
}
