#include "control/ControllerRequestTelemetry.h"
#include <gtest/gtest.h>

namespace {
const std::string command=R"({"schema":1,"profile_id":"ecomline-classic-separate-pressure-v1","source":"controller_uart_transmit","boot_id":"000000000000002a","observed_at_ms":10000,"known":true,"boiler_readback":false,"value_c":50,"emitted_at_ms":9000,"sequence":2})";
TEST(ControllerRequestTelemetry, ProjectsOnlyTheExistingControllerRecordAndKeepsBoilerValuesSeparate) {
    const auto original=R"({"protocolProfile":"classic","selectedFlowTemperature":0,"currentFlowTemperature":660,"unrelated":"not forwarded","controller_request":)"+command+"}";
    const auto bytes=heating::control::controllerRequestTelemetry(original);
    const auto parsed=heating::control::parseControlJson(bytes);ASSERT_TRUE(parsed);
    EXPECT_EQ(cJSON_GetArraySize(parsed.get()),2);
    EXPECT_FALSE(cJSON_GetObjectItemCaseSensitive(parsed.get(),"selectedFlowTemperature"));
    EXPECT_FALSE(cJSON_GetObjectItemCaseSensitive(parsed.get(),"unrelated"));
    const auto* row=cJSON_GetObjectItemCaseSensitive(parsed.get(),"controller_request");ASSERT_TRUE(row);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"value_c")),50);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"emitted_at_ms")),9000);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(row,"sequence")),2);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(row,"boiler_readback")));
}
TEST(ControllerRequestTelemetry, UnknownAndPlusProfilesMissingRecordsAndMalformedSnapshotsEmitNothing) {
    for(const auto& value:{std::string{},std::string("[]"),std::string("{}"),std::string("{"),std::string(8193,' '),
        std::string(R"({"protocolProfile":"classic"})"),
        std::string(R"({"protocolProfile":"classic","controller_request":{}})"),
        std::string(R"({"protocolProfile":"plus","controller_request":)")+command+"}",
        std::string(R"({"protocolProfile":"unknown","controller_request":)")+command+"}"})
        EXPECT_TRUE(heating::control::controllerRequestTelemetry(value).empty());
}
}
