#include "control/ManagedDeviceSettings.h"
#include "control/HttpAccessPolicy.h"
#include <gtest/gtest.h>
#include <memory>
namespace {
using namespace heating::control;
auto json(const char* text) {
    return std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(text),cJSON_Delete);
}
TEST(ManagedSettings, EquivalentWeatherAfterSecretMergeIsPreservedRegardlessOfKeyOrder) {
    auto old=json(R"({"enabled":true,"appid":"synthetic_test_key","latitude":"0","longitude":"1","interval":60})");
    auto same=json(R"({"interval":60,"longitude":"1","latitude":"0","appid":"synthetic_test_key","enabled":true})");
    ASSERT_TRUE(old); ASSERT_TRUE(same);
    EXPECT_TRUE(managedWeatherChangeAllowed(true,old.get(),same.get()));
    auto changed=json(R"({"interval":61,"longitude":"1","latitude":"0","appid":"synthetic_test_key","enabled":true})");
    EXPECT_FALSE(managedWeatherChangeAllowed(true,old.get(),changed.get()));
    EXPECT_TRUE(managedWeatherChangeAllowed(false,old.get(),changed.get()));
}
TEST(ManagedSettings, OmissionCreationAndMalformedSectionNeverMutateManagedWeather) {
    auto value=json(R"({"enabled":false})"), bad=json("false");
    EXPECT_TRUE(managedWeatherChangeAllowed(true,nullptr,nullptr));
    EXPECT_FALSE(managedWeatherChangeAllowed(true,value.get(),nullptr));
    EXPECT_FALSE(managedWeatherChangeAllowed(true,nullptr,value.get()));
    EXPECT_FALSE(managedWeatherChangeAllowed(true,bad.get(),bad.get()));
}
TEST(ManagedSettings, AllDuplicateLegacyWritersGuardedButNativeRecoveryAndReadbackRemain) {
    for(auto route:{"/config/rooms","/config/boiler","/config/hardware","/config/program/current",
                    "/config/programs/default","/config/temporary"})
        for(auto method:{"POST","DELETE"}) EXPECT_TRUE(legacyControlWrite(route,method));
    for(auto route:{"/config/device","/config/wifi","/updates/reboot","/updates/install","/setup/reenter"})
        EXPECT_FALSE(legacyControlWrite(route,"POST"));
    for(auto route:{"/config/rooms","/config/boiler","/config/hardware","/config/programs/default"})
        EXPECT_FALSE(legacyControlWrite(route,"GET"));
}
}
