#include "EMS/OutdoorTemperatureSample.h"
#include "control/WeatherObservation.h"
#include <gtest/gtest.h>
#include <memory>

namespace {
using namespace heating;
ems::EmsTelegram report(uint16_t type,std::vector<uint8_t> bytes,uint8_t offset=0,
                       ems::EmsTelegram::operation_t op=ems::EmsTelegram::BROADCAST,uint8_t source=8) {
    return {op,source,0,offset,type,std::move(bytes)};
}

TEST(OutdoorSources, ClassicAndD1ReportsAreSignedAgeLimitedAndNeverRefreshedByReadback) {
    control::TemperatureSample sample;
    ems::receiveOutdoorTemperature(sample,report(0x19,{0xFF,0xCE}),1000); // -5.0 C
    EXPECT_EQ(sample.value(1000),-500);
    EXPECT_EQ(sample.value(180999),-500);
    EXPECT_FALSE(sample.value(181000));
    EXPECT_FALSE(sample.value(1000+(1ULL<<32)));
    ems::receiveOutdoorTemperature(sample,report(0xD1,{0,0}),200000);
    EXPECT_EQ(sample.value(200000),0);
    ems::receiveOutdoorTemperature(sample,report(0x19,{0x80,0}),200001);
    EXPECT_FALSE(sample.value(200001));
}

TEST(OutdoorSources, ForeignRequestsAndUnrelatedPartialFieldsDoNotRenewOrReplaceOutside) {
    control::TemperatureSample sample;
    ems::receiveOutdoorTemperature(sample,report(0x19,{0,100}),1000);
    ems::receiveOutdoorTemperature(sample,report(0xD1,{0,200},0,ems::EmsTelegram::READ),100000);
    ems::receiveOutdoorTemperature(sample,report(0x19,{0,200},0,ems::EmsTelegram::BROADCAST,9),100001);
    ems::receiveOutdoorTemperature(sample,report(0x19,{0,200},10),100002);
    ems::receiveOutdoorTemperature(sample,report(0x18,{0,200}),100003);
    EXPECT_EQ(sample.value(180999),1000);
    EXPECT_FALSE(sample.value(181000));
    ems::receiveOutdoorTemperature(sample,report(0xD1,{0x7F,0xFF}),181001);
    EXPECT_FALSE(sample.value(181001));
    ems::receiveOutdoorTemperature(sample,report(0x19,{0x03,0xE8}),181002); // 100 C outlier
    EXPECT_FALSE(sample.value(181002));
}

TEST(OutdoorSources, WeatherKeepsActualObservationAgeAndRejectsBoolMissingOrStaleData) {
    constexpr int64_t utc=1792450000;
    const auto receive=[&](control::TemperatureSample &s,const char *text,uint64_t mono) {
        std::unique_ptr<cJSON,decltype(&cJSON_Delete)> doc(cJSON_Parse(text),cJSON_Delete);
        return control::receiveWeatherObservation(s,doc.get(),utc,mono);
    };
    control::TemperatureSample sample;
    ASSERT_TRUE(receive(sample,R"({"main":{"temp":6.34},"dt":1792448200})",1000));
    EXPECT_EQ(sample.value(1000),634);
    EXPECT_EQ(sample.age(1000),1800000);
    EXPECT_FALSE(sample.value(1801000)); // original observation, not an extra hour from HTTP.
    const char *bad[]{R"({"main":{"temp":true},"dt":1792450000})",
        R"({"main":{"temp":"6.34"},"dt":1792450000})",
        R"({"main":{},"dt":1792450000})",R"({"main":{"temp":6.34}})",
        R"({"main":{"temp":6.34},"dt":1792450001})",
        R"({"main":{"temp":6.34},"dt":1792446400})",
        R"({"main":{"temp":6.34},"dt":1792449999.5})",
        R"({"main":{"temp":1000},"dt":1792450000})","null"};
    for(auto text:bad) {
        EXPECT_FALSE(receive(sample,text,1000)) << text;
        EXPECT_FALSE(sample.value(1000));
    }
}

TEST(OutdoorSources, WeatherCannotBeAcceptedWithAnUnestablishedUtcClock) {
    auto doc=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(R"({"main":{"temp":6.34},"dt":1792450000})"),cJSON_Delete);
    control::TemperatureSample s;
    EXPECT_FALSE(control::receiveWeatherObservation(s,doc.get(),0,1000));
    EXPECT_FALSE(control::receiveWeatherObservation(s,doc.get(),4102444800,1000));
}
}
