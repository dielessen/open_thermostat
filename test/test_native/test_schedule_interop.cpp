#include "control/ScheduleDocument.h"
#include <gtest/gtest.h>
#include <fstream>
#include <memory>
#include <sstream>

namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json parse(const char *text) { return Json(cJSON_Parse(text), cJSON_Delete); }

TEST(ScheduleInterop, SharedHaCompilerFixturesReplayEverySecondInProductionFirmwareEvaluator) {
    std::ifstream input("test/fixtures/compiled-schedule-cases.json");
    ASSERT_TRUE(input.good());
    std::ostringstream buffer; buffer << input.rdbuf();
    auto cases = parse(buffer.str().c_str());
    ASSERT_TRUE(cJSON_IsArray(cases.get()));
    ASSERT_EQ(cJSON_GetArraySize(cases.get()), 2);
    for (auto fixture = cases->child; fixture; fixture = fixture->next) {
        SCOPED_TRACE(cJSON_GetObjectItemCaseSensitive(fixture,"case")->valuestring);
        auto doc = cJSON_GetObjectItemCaseSensitive(fixture,"output");
        UtcSchedule schedule; ASSERT_TRUE(configureScheduleDocument(schedule,doc));
        const int64_t start=cJSON_GetObjectItemCaseSensitive(doc,"valid_from_utc")->valuedouble;
        const int64_t end=cJSON_GetObjectItemCaseSensitive(doc,"valid_until_utc")->valuedouble;
        const bool spring=start==1774742400;
        for(int64_t now=start;now<end;++now) {
            // Independent expected wall-clock membership for these two exact
            // three-hour DST windows, not values read from the transition list.
            const auto elapsed=now-start;
            const int expected=(!spring && ((elapsed>=1800 && elapsed<3600) ||
                                            (elapsed>=5400 && elapsed<7200))) ? 2100:1700;
            ASSERT_EQ(schedule.target(now,true).temperatureCentiC,expected) << now;
        }
        EXPECT_FALSE(schedule.target(start,false).temperatureCentiC);
        EXPECT_FALSE(schedule.target(end,true).temperatureCentiC);
        EXPECT_EQ(schedule.target(end,true).state,ScheduleState::expired);
    }
}

TEST(ScheduleInterop, InvalidWireDocumentNeverPartiallyReplacesExistingSchedule) {
    constexpr const char *valid=R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,2100]]})";
    auto doc=parse(valid); UtcSchedule s;
    ASSERT_TRUE(configureScheduleDocument(s,doc.get()));
    const char *bad[]{
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,true]]})",
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,2200],[1792368000,2300]]})",
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,2200]],"base_centi_c":1800})",
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,2200]],"extra":1})",
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000.5,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,2200]]})",
        R"({"timezone":"UTC","policy":"wall-clock-membership/v1","valid_from_utc":1792368000,"valid_until_utc":1792454400,"base_centi_c":1700,"transitions":[[1792368000,"2200"]]})"
    };
    for(auto text:bad) {
        auto rejected=parse(text); ASSERT_TRUE(rejected);
        EXPECT_FALSE(configureScheduleDocument(s,rejected.get())) << text;
        EXPECT_EQ(s.baseCentiC(),1700);
        EXPECT_EQ(s.target(1792368000,true).temperatureCentiC,2100);
    }
    auto missing=parse("{}"); EXPECT_FALSE(configureScheduleDocument(s,missing.get()));
    auto extra=cJSON_GetObjectItemCaseSensitive(doc.get(),"transitions")->child;
    cJSON_AddItemToArray(extra,cJSON_CreateNumber(0));
    EXPECT_FALSE(configureScheduleDocument(s,doc.get()));
}

TEST(ScheduleInterop, CompilerAndFirmwareShareExactSupportedUtcRange) {
    UtcSchedule s;
    const ScheduleTransition end[]{{UtcSchedule::maximumUtcSecond-1,2000}};
    EXPECT_TRUE(s.configure(UtcSchedule::maximumUtcSecond-1,UtcSchedule::maximumUtcSecond,1700,end,1));
    EXPECT_FALSE(s.configure(UtcSchedule::maximumUtcSecond-1,UtcSchedule::maximumUtcSecond+1,1700,end,1));
    const ScheduleTransition start[]{{UtcSchedule::minimumUtcSecond,2000}};
    EXPECT_TRUE(s.configure(UtcSchedule::minimumUtcSecond,UtcSchedule::minimumUtcSecond+1,1700,start,1));
}
}
