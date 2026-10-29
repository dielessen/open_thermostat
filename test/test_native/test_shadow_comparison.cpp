#include "control/ShadowComparison.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <functional>
#include <memory>

namespace {
using heating::control::FlowDemand;
using heating::control::ShadowComparison;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60 * second;
constexpr uint32_t day = 86400;
// 2026-10-28 00:00 CET (23:00 UTC the day before); the day tests set the Amsterdam TZ.
const uint32_t midnight = uint32_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * day - 3600;

FlowDemand::Request e32(uint8_t flowC) { return {flowC > 0, flowC, flowC > 0 ? FlowDemand::Reason::heating : FlowDemand::Reason::idle}; }

// Samples every 10 s over [fromMs, toMs); the functions give each side's flow at t (0 = off).
void run(ShadowComparison& c, uint64_t fromMs, uint64_t toMs, uint32_t unixAtZero,
         const std::function<uint8_t(uint64_t)>& e32Flow, const std::function<std::optional<uint8_t>(uint64_t)>& tadoFlow) {
    for (uint64_t t = fromMs; t < toMs; t += 10 * second)
        c.sample(t, unixAtZero + uint32_t(t / 1000), e32(e32Flow(t)), tadoFlow(t));
}
uint8_t between(uint64_t t, uint64_t on, uint64_t off, uint8_t flowC) { return t >= on && t < off ? flowC : 0; }
double num(const cJSON* o, const char* key) { return cJSON_GetNumberValue(cJSON_GetObjectItem(o, key)); }

TEST(ShadowComparison, IdenticalDecisionsAgreeFully) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    const auto both = [](uint64_t t) { return between(t, 10 * minute, 70 * minute, 38); };
    run(c, 0, 90 * minute, midnight + 3600, both, both);
    const auto& d = c.today();
    EXPECT_EQ(d.s, 90 * 60 - 10u); // the first sample has no interval before it
    EXPECT_EQ(d.bothS, 3600u); EXPECT_EQ(d.e32OnlyS, 0u); EXPECT_EQ(d.tadoOnlyS, 0u);
    EXPECT_EQ(d.e32.starts, 1u); EXPECT_EQ(d.tado.starts, 1u);
    EXPECT_EQ(d.paired, 1u); EXPECT_EQ(d.close, 1u); EXPECT_EQ(d.offsetMaxS, 0u);
    Json j(c.json(), cJSON_Delete);
    const auto* today = cJSON_GetObjectItem(j.get(), "today");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(today, "day")), "2026-10-28");
    EXPECT_EQ(num(today, "agree_s"), num(today, "s"));
    EXPECT_EQ(num(today, "flow_diff_mean_c"), 0);
    EXPECT_EQ(num(today, "start_offset_mean_s"), 0);
    EXPECT_EQ(num(cJSON_GetObjectItem(today, "tado"), "flow_mean_c"), 38);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j.get(), "days")), 0);
}
TEST(ShadowComparison, ThreeMinuteLaterStartIsPairedWithItsOffset) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    run(c, 0, 90 * minute, midnight + 3600,
        [](uint64_t t) { return between(t, 13 * minute, 70 * minute, 41); },
        [](uint64_t t) -> std::optional<uint8_t> { return between(t, 10 * minute, 70 * minute, 35); });
    const auto& d = c.today();
    EXPECT_EQ(d.tadoOnlyS, 180u);
    EXPECT_EQ(d.paired, 1u); EXPECT_EQ(d.close, 1u);
    EXPECT_EQ(d.offsetSumS, 180); EXPECT_EQ(d.offsetMaxS, 180u); // > 0: the E32 is later
    Json j(c.json(), cJSON_Delete);
    const auto* today = cJSON_GetObjectItem(j.get(), "today");
    EXPECT_EQ(num(today, "start_offset_mean_s"), 180);
    EXPECT_EQ(num(today, "flow_diff_mean_c"), 6);
    EXPECT_EQ(num(cJSON_GetObjectItem(today, "e32"), "flow_max_c"), 41);
}
TEST(ShadowComparison, StartsMoreThanThirtyMinutesApartDoNotPair) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    run(c, 0, 120 * minute, midnight + 3600,
        [](uint64_t t) { return between(t, 50 * minute, 100 * minute, 40); },
        [](uint64_t t) -> std::optional<uint8_t> { return between(t, 10 * minute, 40 * minute, 40); });
    EXPECT_EQ(c.today().e32.starts, 1u); EXPECT_EQ(c.today().tado.starts, 1u);
    EXPECT_EQ(c.today().paired, 0u);
    Json j(c.json(), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "today"), "start_offset_mean_s")));
}
TEST(ShadowComparison, UnknownTadoIsCountedApartAndKeepsItsLastState) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    // tado known off, unknown 10-15 min, then heating: the observed edge is a start.
    run(c, 0, 30 * minute, midnight + 3600, [](uint64_t) { return uint8_t(0); },
        [](uint64_t t) -> std::optional<uint8_t> {
            if (t >= 10 * minute && t < 15 * minute) return std::nullopt;
            return between(t, 15 * minute, 30 * minute, 33);
        });
    const auto& d = c.today();
    EXPECT_EQ(d.tadoUnknownS, 300u);
    EXPECT_EQ(d.tado.starts, 1u);
    EXPECT_EQ(d.bothS + d.neitherS + d.e32OnlyS + d.tadoOnlyS + d.tadoUnknownS, d.s);
    EXPECT_EQ(d.tadoOnlyS, 15 * 60u);
}
TEST(ShadowComparison, TadoZeroOrLowFlowMeansNoHeat) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    c.sample(0, midnight, e32(0), uint8_t(0));
    c.sample(10 * second, midnight + 10, e32(0), uint8_t(ShadowComparison::tadoHeatFromC - 1));
    c.sample(20 * second, midnight + 20, e32(0), uint8_t(ShadowComparison::tadoHeatFromC));
    EXPECT_EQ(c.today().neitherS, 10u); EXPECT_EQ(c.today().tadoOnlyS, 10u);
    EXPECT_EQ(c.today().tado.starts, 1u);
}
TEST(ShadowComparison, GapsAreNotFilledIn) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    c.sample(0, midnight, e32(40), uint8_t(40));
    c.sample(10 * minute, midnight + 600, e32(40), uint8_t(40)); // ten minutes without samples
    EXPECT_EQ(c.today().s, ShadowComparison::maxCreditMs / 1000);
    EXPECT_EQ(c.today().bothS, 30u);
    c.sample(10 * minute, midnight + 600, e32(40), uint8_t(40)); // repeated time: no credit
    EXPECT_EQ(c.today().s, 30u);
    for (uint64_t t = 10 * minute + 9999; t <= 10 * minute + 100 * 9999; t += 9999) // jittery cadence
        c.sample(t, midnight + 600 + uint32_t((t - 10 * minute) / 1000), e32(40), uint8_t(40));
    EXPECT_EQ(c.today().s, 30u + 999u); // 100 x 9.999 s
}
TEST(ShadowComparison, CyclingIsCountedPerSide) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    // E32 10 min on / 10 min off for two hours, tado one long period.
    run(c, 0, 120 * minute, midnight + 3600,
        [](uint64_t t) { return (t / (10 * minute)) % 2 ? uint8_t(45) : uint8_t(0); },
        [](uint64_t t) -> std::optional<uint8_t> { return between(t, 5 * minute, 120 * minute, 37); });
    EXPECT_EQ(c.today().e32.starts, 6u);
    EXPECT_EQ(c.today().tado.starts, 1u);
    EXPECT_EQ(c.today().paired, 1u); // the tado start pairs with the E32 start 5 min later
    EXPECT_EQ(c.today().offsetSumS, 300);
    EXPECT_EQ(c.today().close, 1u);
}
TEST(ShadowComparison, LocalMidnightMovesTodayIntoTheHistory) {
    ScopedTz tz(ScopedTz::amsterdam);
    ShadowComparison c;
    const auto heat = [](uint64_t) { return uint8_t(35); };
    const auto tado = [](uint64_t) -> std::optional<uint8_t> { return uint8_t(35); };
    run(c, 0, 20 * minute, midnight + day - 600, heat, tado); // 23:50 -> 00:10 CET
    ASSERT_EQ(c.completedDays(), 1u);
    EXPECT_EQ(c.completed(0).bothS, 590u); // 23:50:10 .. 23:59:50
    EXPECT_EQ(c.today().bothS, 600u);
    EXPECT_EQ(c.today().e32.starts, 0u); // state carries over midnight: no new start
    Json j(c.json(), cJSON_Delete);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(), "today"), "day")), "2026-10-29");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(j.get(), "days"), 0), "day")), "2026-10-28");
}
TEST(ShadowComparison, HistoryKeepsTheLastSevenDays) {
    ScopedTz tz(ScopedTz::amsterdam);
    ShadowComparison c;
    for (uint32_t i = 0; i < 10; ++i) {
        const uint64_t t = uint64_t(i) * day * 1000;
        c.sample(t, midnight + i * day + 3600, e32(0), uint8_t(0));
        c.sample(t + 10 * second, midnight + i * day + 3610, e32(0), uint8_t(0));
    }
    ASSERT_EQ(c.completedDays(), ShadowComparison::history);
    EXPECT_EQ(c.today().day, ShadowComparison::localDay(midnight + 9 * day));
    EXPECT_EQ(c.completed(0).day, c.today().day - 1);
    EXPECT_EQ(c.completed(6).day, c.today().day - 7);
    Json j(c.json(), cJSON_Delete);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(j.get(), "days")), 7);
}
TEST(ShadowComparison, BootTimeWithoutClockJoinsTheFirstKnownDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    ShadowComparison c;
    c.sample(0, std::nullopt, e32(0), uint8_t(0));
    c.sample(10 * second, std::nullopt, e32(0), uint8_t(0));
    Json early(c.json(), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(early.get(), "today"), "day")));
    c.sample(20 * second, midnight + 7200, e32(0), uint8_t(0));
    EXPECT_EQ(c.today().day, ShadowComparison::localDay(midnight));
    EXPECT_EQ(c.today().s, 20u);
    EXPECT_EQ(c.completedDays(), 0u);
    c.sample(30 * second, midnight - 7200, e32(0), uint8_t(0)); // clock stepped back a day: stays today
    EXPECT_EQ(c.completedDays(), 0u);
}
TEST(ShadowComparison, LocalDayFollowsTheDeviceTimeZone) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto at = [](int y, unsigned m, unsigned d, uint32_t utcSeconds) {
        return uint32_t(ShadowComparison::daysFromCivil(y, m, d)) * day + utcSeconds;
    };
    const auto local = [](int y, unsigned m, unsigned d) { return ShadowComparison::daysFromCivil(y, m, d); };
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 1, 22 * 3600 - 1)), local(2026, 7, 1)); // 23:59:59 CEST
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 1, 22 * 3600)), local(2026, 7, 2));
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 12, 1, 23 * 3600 - 1)), local(2026, 12, 1)); // 23:59:59 CET
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 12, 1, 23 * 3600)), local(2026, 12, 2));
    // 2026-10-25 01:00 UTC summer time ends; 2026-03-29 01:00 UTC it starts.
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 10, 24, 22 * 3600)), local(2026, 10, 25));
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 10, 25, 22 * 3600 + 1800)), local(2026, 10, 25));
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 3, 28, 23 * 3600)), local(2026, 3, 29));
    EXPECT_EQ(ShadowComparison::localDay(at(2026, 3, 29, 22 * 3600)), local(2026, 3, 30));
    {
        ScopedTz other(ScopedTz::newYork); // midnight at 04:00 UTC in summer (EDT), 05:00 UTC in winter (EST)
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 2, 4 * 3600 - 1)), local(2026, 7, 1));
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 2, 4 * 3600)), local(2026, 7, 2));
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 12, 2, 5 * 3600 - 1)), local(2026, 12, 1));
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 12, 2, 5 * 3600)), local(2026, 12, 2));
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 11, 2, 5 * 3600 - 1)), local(2026, 11, 1)); // first EST midnight
    }
    {
        ScopedTz other(ScopedTz::london);
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 1, 23 * 3600 - 1)), local(2026, 7, 1)); // 23:59:59 BST
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 7, 1, 23 * 3600)), local(2026, 7, 2));
        EXPECT_EQ(ShadowComparison::localDay(at(2026, 12, 1, 23 * 3600 + 1800)), local(2026, 12, 1)); // 23:30 GMT
    }
}
TEST(ShadowComparison, DayWithoutHeatReportsNullFlows) {
    ScopedTz tz(ScopedTz::amsterdam); // fixture times are Amsterdam days
    ShadowComparison c;
    c.sample(0, midnight, e32(0), std::nullopt);
    c.sample(10 * second, midnight + 10, e32(0), std::nullopt);
    Json j(c.json(), cJSON_Delete);
    const auto* today = cJSON_GetObjectItem(j.get(), "today");
    EXPECT_EQ(num(today, "tado_unknown_s"), 10);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(today, "e32"), "flow_mean_c")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(today, "flow_diff_mean_c")));
}
}
