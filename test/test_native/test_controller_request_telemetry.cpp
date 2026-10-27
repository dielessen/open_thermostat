#include "control/ControllerRequestTelemetry.h"
#include "EMS/ClassicBoilerMonitor.h"
#include <gtest/gtest.h>
#include <sstream>

namespace {
const std::string command=R"({"schema":1,"profile_id":"ecomline-classic-separate-pressure-v1","source":"controller_uart_transmit","boot_id":"000000000000002a","observed_at_ms":10000,"known":true,"boiler_readback":false,"value_c":50,"emitted_at_ms":9000,"sequence":2})";
TEST(ControllerRequestTelemetry, ProjectsOnlyTheExistingControllerRecordAndKeepsBoilerValuesSeparate) {
    const auto original=R"({"protocolProfile":"classic_observed","selectedFlowTemperature":0,"currentFlowTemperature":660,"unrelated":"not forwarded","controller_request":)"+command+"}";
    const auto bytes=heating::control::controllerRequestTelemetry(original);
    const auto parsed=heating::control::parseControlJson(bytes);ASSERT_TRUE(parsed);
    EXPECT_EQ(cJSON_GetArraySize(parsed.get()),2);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(parsed.get(),"protocolProfile")),"classic");
    EXPECT_FALSE(cJSON_GetObjectItemCaseSensitive(parsed.get(),"selectedFlowTemperature"));
    EXPECT_FALSE(cJSON_GetObjectItemCaseSensitive(parsed.get(),"unrelated"));
    const auto* row=cJSON_GetObjectItemCaseSensitive(parsed.get(),"controller_request");ASSERT_TRUE(row);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"value_c")),50);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"emitted_at_ms")),9000);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"sequence")),2);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(row,"boiler_readback")));
}
// The device status is produced by the actual Classic monitor, not a fixture.
// Beta10 only accepted "classic", which the real snapshot never contains.
TEST(ControllerRequestTelemetry, ProjectsTheActualClassicMonitorSnapshot) {
    using namespace heating::ems;
    ClassicBoilerMonitor monitor;
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,1,172,0,0,0,0,0}},100);
    std::ostringstream status;monitor.writeLegacyStatus(status,200,false);
    status<<",\"controller_request\":"<<command<<'}';
    const auto bytes=heating::control::controllerRequestTelemetry(status.str());
    ASSERT_FALSE(bytes.empty()) << status.str();
    const auto parsed=heating::control::parseControlJson(bytes);ASSERT_TRUE(parsed);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(parsed.get(),"protocolProfile")),"classic");
}
TEST(ControllerRequestTelemetry, UnknownAndPlusProfilesMissingRecordsAndMalformedSnapshotsEmitNothing) {
    for(const auto& value:{std::string{},std::string("[]"),std::string("{}"),std::string("{"),std::string(8193,' '),
        std::string(R"({"protocolProfile":"classic_observed"})"),
        std::string(R"({"protocolProfile":"classic_observed","controller_request":{}})"),
        std::string(R"({"protocolProfile":"plus_observed","controller_request":)")+command+"}",
        std::string(R"({"protocolProfile":"unknown","controller_request":)")+command+"}"})
        EXPECT_TRUE(heating::control::controllerRequestTelemetry(value).empty());
}
}
