#include "EMS/ClassicBoilerMonitor.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>
using namespace heating::ems;
namespace {
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
Json projection(const ClassicBoilerMonitor& monitor,uint64_t now) {
    std::ostringstream out;monitor.writeLegacyStatus(out,now);
    return Json(cJSON_Parse(out.str().c_str()),cJSON_Delete);
}
const cJSON *field(const Json& json,const char *name){return cJSON_GetObjectItemCaseSensitive(json.get(),name);}
EmsTelegram fast(uint8_t offset,std::vector<uint8_t> bytes) {
    return {EmsTelegram::BROADCAST,8,0,offset,0x18,std::move(bytes)};
}
}
TEST(BoilerLegacyProjection, HomeUsesTheSameDecodedValuesAndExplicitUnitConversion) {
    ClassicBoilerMonitor monitor;
    monitor.receive(fast(0,{50,1,172,80,37,9,0,0x25}),100);
    monitor.receive(fast(17,{20}),100);
    monitor.receive(fast(13,{1,200}),100);
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x19,{0xff,0xc9}},100);
    const auto json=projection(monitor,200);ASSERT_TRUE(json);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"currentFlowTemperature")),428);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"currentReturnTemperature")),456);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"selectedFlowTemperature")),50);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"currentBurnerPower")),37);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"pressure")),20);
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"outdoorTemperature")),-550);
    EXPECT_TRUE(cJSON_IsTrue(field(json,"heatingActive")));
    EXPECT_TRUE(cJSON_IsFalse(field(json,"warmWaterActive")));
    EXPECT_TRUE(cJSON_IsNull(field(json,"burningGas"))); // Unreliable adapter bit.
    EXPECT_TRUE(cJSON_IsNull(field(json,"pumpEnabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(json,"physicalValidation")));
}
TEST(BoilerLegacyProjection, APartialReportDoesNotRenewAnOlderTemperature) {
    ClassicBoilerMonitor monitor;monitor.receive(fast(0,{50,1,172}),100);
    monitor.receive(fast(4,{30}),30100);
    const auto json=projection(monitor,30101);ASSERT_TRUE(json);
    EXPECT_TRUE(cJSON_IsNull(field(json,"currentFlowTemperature")));
    EXPECT_TRUE(cJSON_IsNull(field(json,"selectedFlowTemperature")));
    EXPECT_DOUBLE_EQ(cJSON_GetNumberValue(field(json,"currentBurnerPower")),30);
}
TEST(BoilerLegacyProjection, UnknownAndConflictingProtocolsDoNotPublishAClassicMeasurement) {
    ClassicBoilerMonitor monitor;auto json=projection(monitor,0);ASSERT_TRUE(json);
    EXPECT_EQ(field(json,"currentFlowTemperature"),nullptr);
    monitor.receive(fast(0,{50,1,172}),100);
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0xe4,{50}},200);
    json=projection(monitor,201);ASSERT_TRUE(json);
    EXPECT_EQ(field(json,"currentFlowTemperature"),nullptr);
    EXPECT_STREQ(cJSON_GetStringValue(field(json,"protocolProfile")),"conflicting_families");
}
TEST(BoilerLegacyProjection, DisplayCodesRemainValidJsonAndExpireWithTheirSource) {
    ClassicBoilerMonitor monitor;monitor.receive(fast(18,{'"','\\'}),100);
    auto json=projection(monitor,101);ASSERT_TRUE(json);
    EXPECT_STREQ(cJSON_GetStringValue(field(json,"displayCode")),"\"\\");
    json=projection(monitor,30100);ASSERT_TRUE(json);
    EXPECT_EQ(field(json,"displayCode"),nullptr);
}
