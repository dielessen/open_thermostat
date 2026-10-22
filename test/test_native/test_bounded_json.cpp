#include "control/BoundedJson.h"
#include "control/ScheduleDocument.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::control;

TEST(ControlJson, ExactDocumentAndStrictNumericSyntaxBeforeSchemaValidation) {
    auto good=parseControlJson(R"({"a":-20.3,"b":1e+3,"c":true,"d":null})");
    ASSERT_TRUE(good);
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItemCaseSensitive(good.get(),"a")->valuedouble,-20.3);
    const char *bad[]{"", "01", "-01", "1.", "1e", "+1", "NaN", "1e309", "true false", "{}x",
        "{]", "[}", R"({"a":1,"a":2})",R"({"a":{"b":1,"b":2}})",R"({"a":truejunk})"};
    for(auto text:bad) EXPECT_FALSE(parseControlJson(text)) << text;
}

TEST(ControlJson, NulAliasesEscapedKeysUnicodeAndTrailingGarbageAreRejected) {
    EXPECT_FALSE(parseControlJson(R"({"timezone\u0000x":"UTC"})"));
    EXPECT_FALSE(parseControlJson(R"({"t\u0069mezone":"UTC"})"));
    EXPECT_FALSE(parseControlJson(R"({"text":"a\\b"})"));
    EXPECT_FALSE(parseControlJson("{\"text\":\"\xc3\xa9\"}"));
    std::string nul="{}"; nul.push_back('\0'); nul+="{}";
    EXPECT_FALSE(parseControlJson(nul));
    EXPECT_FALSE(parseControlJson("{\"text\":\"line\nwrap\"}"));
    EXPECT_TRUE(parseControlJson("{\"text\":\"Europe/Amsterdam\"}\n "));
}

TEST(ControlJson, ByteDepthStringAndNodeBudgetsAreBoundedBeforeTreeAllocation) {
    EXPECT_FALSE(parseControlJson(std::string(8193,' ')));
    EXPECT_FALSE(parseControlJson(std::string(9,'[')+"0"+std::string(9,']')));
    EXPECT_TRUE(parseControlJson(std::string(8,'[')+"0"+std::string(8,']')));
    EXPECT_TRUE(parseControlJson("\""+std::string(64,'a')+"\""));
    EXPECT_FALSE(parseControlJson("\""+std::string(65,'a')+"\""));
    std::string wide="[0";
    for(int i=1;i<512;++i) wide+=",0";
    wide+="]";
    EXPECT_FALSE(parseControlJson(wide));
}

TEST(ControlJson, FullMaximumScheduleFitsBoundedWireAndWholeCandidateValidation) {
    std::string raw=R"({"timezone":"Europe/Amsterdam","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[)";
    for(int i=0;i<128;++i) {
        if(i) raw+=",";
        raw+="["+std::to_string(1792368000+i*60)+","+std::to_string(i%2?2100:1700)+"]";
    }
    raw+="]}";
    auto doc=parseControlJson(raw); ASSERT_TRUE(doc);
    UtcSchedule s; EXPECT_TRUE(configureScheduleDocument(s,doc.get()));
    EXPECT_EQ(s.target(1792368000+127*60,true).temperatureCentiC,2100);
    EXPECT_LT(raw.size(),8192u);
}
TEST(ControlJson, DeviceSettingsUseSameBudgetsButSupportEscapedAndUnicodeCredentials) {
    EXPECT_TRUE(parseControlJson(R"({"password":"quote\"and\\slash","ssid":"K\u0065uken"})",true));
    EXPECT_TRUE(parseControlJson("{\"ssid\":\"caf\xc3\xa9\"}",true));
    EXPECT_FALSE(parseControlJson(R"({"password":"secret\u0000suffix"})",true));
    EXPECT_FALSE(parseControlJson(R"({"password":"one","passwo\u0072d":"two"})",true));
    EXPECT_FALSE(parseControlJson(std::string(9,'[')+"0"+std::string(9,']'),true));
    EXPECT_FALSE(parseControlJson("{\"password\":\""+std::string(513,'a')+"\"}",true));
}
}
