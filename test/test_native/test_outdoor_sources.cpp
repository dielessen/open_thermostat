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

TEST(OutdoorSources, WeatherKeepsProviderCalculationAgeAndRejectsBoolMissingOrStaleData) {
    constexpr int64_t utc=1792450000;
    const auto receive=[&](control::WeatherObservation &s,const char *text,uint64_t mono) {
        std::unique_ptr<cJSON,decltype(&cJSON_Delete)> doc(cJSON_Parse(text),cJSON_Delete);
        return control::receiveWeatherObservation(s,doc.get(),utc,mono);
    };
    control::WeatherObservation sample;
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
    uint64_t now=1801000;
    for(auto text:bad) {
        ++now;
        EXPECT_FALSE(receive(sample,text,now)) << text;
        EXPECT_FALSE(sample.value(now));
    }
}

TEST(OutdoorSources, WeatherCannotBeAcceptedWithAnUnestablishedUtcClock) {
    auto doc=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(R"({"main":{"temp":6.34},"dt":1792450000})"),cJSON_Delete);
    control::WeatherObservation s;
    EXPECT_FALSE(control::receiveWeatherObservation(s,doc.get(),0,1000));
    EXPECT_FALSE(control::receiveWeatherObservation(s,doc.get(),4102444800,1000));
}

bool weather(control::WeatherObservation &s,int64_t utc,uint64_t mono,int64_t stamp,const char* temperature="6.34") {
    const auto raw=std::string("{\"main\":{\"temp\":")+temperature+"},\"dt\":"+std::to_string(stamp)+"}";
    auto doc=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(raw.c_str()),cJSON_Delete);
    return control::receiveWeatherObservation(s,doc.get(),utc,mono);
}
TEST(OutdoorSources, DuplicateWeatherAndBackwardUtcCorrectionCannotRenewOriginalLifetime) {
    constexpr int64_t utc=1792450000;control::WeatherObservation s;
    ASSERT_TRUE(weather(s,utc,1000,utc-1800));
    ASSERT_TRUE(weather(s,utc+600,601000,utc-1800));
    EXPECT_EQ(s.age(601000),2400000u);
    ASSERT_TRUE(weather(s,utc,901000,utc-1800)); // Wall clock corrected backwards.
    EXPECT_EQ(s.age(901000),2700000u);
    EXPECT_TRUE(s.value(1800999));EXPECT_FALSE(s.value(1801000));
    EXPECT_FALSE(weather(s,utc,1801000,utc-1800));
    EXPECT_FALSE(s.value(1801000));
    ASSERT_TRUE(weather(s,utc+1000,1801001,utc+100)); // Genuinely newer calculation.
    EXPECT_EQ(s.age(1801001),900000u);
}
TEST(OutdoorSources, ForwardUtcCorrectionMayOnlyShortenTheRemainingWeatherLifetime) {
    constexpr int64_t utc=1792450000;control::WeatherObservation s;
    ASSERT_TRUE(weather(s,utc,1000,utc));
    ASSERT_TRUE(weather(s,utc+1800,2000,utc));
    EXPECT_EQ(s.age(2000),1800000u);
    ASSERT_TRUE(weather(s,utc+1,3000,utc));
    EXPECT_EQ(s.age(3000),1801000u);
    EXPECT_TRUE(s.value(1801999));EXPECT_FALSE(s.value(1802000));
}
TEST(OutdoorSources, ConflictingOrReorderedWeatherCannotRecoverThroughAnOldDuplicate) {
    constexpr int64_t utc=1792450000;control::WeatherObservation s;
    ASSERT_TRUE(weather(s,utc,1000,utc));
    EXPECT_FALSE(weather(s,utc,2000,utc,"6.35"));EXPECT_FALSE(s.value(2000));
    EXPECT_FALSE(weather(s,utc,3000,utc));
    ASSERT_TRUE(weather(s,utc+1,4000,utc+1));
    EXPECT_FALSE(weather(s,utc+1,5000,utc));
    EXPECT_FALSE(weather(s,utc+1,6000,utc+1));
    ASSERT_TRUE(weather(s,utc+2,7000,utc+2));
}
TEST(OutdoorSources, WithdrawnWeatherNeedsNewProviderDataAndClockFailureNeedsANewOwner) {
    constexpr int64_t utc=1792450000;control::WeatherObservation s;
    ASSERT_TRUE(weather(s,utc,1000,utc));s.unavailable();
    EXPECT_FALSE(weather(s,utc,2000,utc));
    ASSERT_TRUE(weather(s,utc+1,3000,utc+1));
    EXPECT_FALSE(s.value(2999));
    EXPECT_FALSE(weather(s,utc+2,4000,utc+2));
    EXPECT_FALSE(s.value(4000));
    control::WeatherObservation replacement;
    ASSERT_TRUE(weather(replacement,utc+2,4000,utc+2));
    EXPECT_EQ(replacement.value(4000),634);
}
}
