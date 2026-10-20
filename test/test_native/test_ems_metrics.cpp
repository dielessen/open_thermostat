#include "EmsMetrics.h"
#include <gtest/gtest.h>
#include <map>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <string>

namespace {
using namespace heating::ems;

TEST(EmsMetricTotals, ObservationsIntegratePreviousModeNotNewModeAndReadsDoNotConsume) {
    EmsMetricTotals m;
    m.nominal(0, 24); m.power(0, 50); m.modes(0, true, false, true);
    auto before = m.snapshot(10000);
    EXPECT_EQ(before.energyKwh, 0); // reads are not synthetic observations
    m.power(10000, 25);
    m.modes(10000, false, true, true);
    m.power(20000, 0);
    const auto a = m.snapshot(20000), b = m.snapshot(30000);
    EXPECT_DOUBLE_EQ(a.energyKwh, 18.0 * 10000 / 3600000);
    EXPECT_DOUBLE_EQ(a.heatingKwh, 12.0 * 10000 / 3600000);
    EXPECT_DOUBLE_EQ(a.dhwKwh, 6.0 * 10000 / 3600000);
    EXPECT_DOUBLE_EQ(a.energyKwh, b.energyKwh);
    EXPECT_DOUBLE_EQ(a.burnerSeconds, 20);
}

TEST(EmsMetricTotals, StalePowerAndModesStopAtDeadlineWithoutIntegratingLongGap) {
    EmsMetricTotals m;
    m.nominal(100, 24); m.power(100, 50); m.modes(100, true, false, true);
    m.power(3600100, 0);
    auto s = m.snapshot(3600100);
    EXPECT_DOUBLE_EQ(s.energyKwh, 12.0 * 30000 / 3600000);
    EXPECT_DOUBLE_EQ(s.heatingKwh, s.energyKwh);
    EXPECT_DOUBLE_EQ(s.burnerSeconds, 30);
    EXPECT_TRUE(s.powerFresh); // received new zero, not the old 50%
    EXPECT_FALSE(m.snapshot(3630100).powerFresh);
}

TEST(EmsMetricTotals, FlowUnitsObservedAverageNotHardcodedZeroAndNoReadReset) {
    EmsMetricTotals m;
    m.flow(0, 12); // 1.2L/min
    m.flow(10000, 0);
    auto a = m.snapshot(10000);
    ASSERT_TRUE(a.averageFlow);
    EXPECT_DOUBLE_EQ(a.waterLitres, .2);
    EXPECT_DOUBLE_EQ(*a.averageFlow, 1.2);
    ASSERT_TRUE(a.currentFlow);
    EXPECT_DOUBLE_EQ(*a.currentFlow, 0);
    EXPECT_DOUBLE_EQ(m.snapshot(12000).waterLitres, .2);
    m.flow(20000, 0);
    EXPECT_DOUBLE_EQ(*m.snapshot(20000).averageFlow, .6);
}

TEST(EmsMetricTotals, MissingNominalInvalidPowerUnknownModeAndClockBackwardsAreNotMeasurements) {
    EmsMetricTotals m;
    m.power(0, 50); m.power(10000, 50);
    EXPECT_FALSE(m.snapshot(10000).energyObserved);
    m.nominal(10000, 24);
    m.modes(10000, false, false, true);
    m.power(20000, 255);
    auto s = m.snapshot(20000);
    EXPECT_DOUBLE_EQ(s.energyKwh, 12.0 * 10000 / 3600000);
    EXPECT_DOUBLE_EQ(s.unattributedKwh, s.energyKwh);
    m.power(30000, 50);
    EXPECT_DOUBLE_EQ(m.snapshot(30000).energyKwh, s.energyKwh);
    m.flow(1, 12); // backwards clock invalidates old intervals, retains totals
    m.flow(10001, 0);
    EXPECT_DOUBLE_EQ(m.snapshot(10001).energyKwh, s.energyKwh);
}

TEST(EmsMetricTotals, SameTimestampDoesNotDoubleCountOrAttributeConflictingModes) {
    EmsMetricTotals m;
    m.nominal(0, 24); m.power(0, 50); m.modes(0, true, true, true);
    m.power(10000, 50);
    auto s = m.snapshot(10000);
    m.power(10000, 50);
    EXPECT_DOUBLE_EQ(m.snapshot(10000).energyKwh, s.energyKwh);
    EXPECT_EQ(s.heatingKwh, 0); EXPECT_EQ(s.dhwKwh, 0);
    EXPECT_DOUBLE_EQ(s.unattributedKwh, s.energyKwh);
}

struct MetricsHarness {
    uint64_t now = 0;
    std::map<uint16_t, std::function<void(const EmsTelegram&)>> processors;
    EmsMetrics metrics{[this](uint16_t type, auto fn) { processors[type] = fn; }, [this] { return now; }};
    void send(uint16_t type, uint8_t offset, std::vector<uint8_t> data,
              uint8_t source=8, EmsTelegram::operation_t operation=EmsTelegram::BROADCAST) {
        processors.at(type)(EmsTelegram(operation, source, 0, offset, type, std::move(data)));
    }
    std::string json() { std::ostringstream out; metrics.getMetrics(out); return out.str(); }
};

TEST(EmsMetrics, VersionedWireNeverFeedsNumericalTotalsToRetainedLegacyDiscovery) {
    MetricsHarness h;h.send(4,4,{24});h.send(0xE4,10,{50,3});h.send(0xE9,11,{12});
    h.now=10000;h.send(0xE4,10,{0,0});h.send(0xE9,11,{0});
    const auto bytes=h.json();
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> root(cJSON_Parse(bytes.c_str()),cJSON_Delete);
    ASSERT_TRUE(root);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(root.get(),"counterDefinition")),"observation-total-v2");
    for(auto field:{"totalEnergyUsedKwh","heatingEnergyUsedKwh","warmWaterEnergyUsedKwh","unattributedEnergyUsedKwh",
                    "warmWaterUsage","warmWaterAvgFlow","warmWaterFlow","observedBurnerSeconds"})
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(root.get(),field)));
    auto energy=cJSON_GetObjectItemCaseSensitive(root.get(),"totalEnergyUsedKwhV2");
    ASSERT_TRUE(cJSON_IsNumber(energy));EXPECT_NEAR(energy->valuedouble,12.0*10000/3600000,1e-7);
    auto volume=cJSON_GetObjectItemCaseSensitive(root.get(),"warmWaterUsageV2");
    ASSERT_TRUE(cJSON_IsNumber(volume));EXPECT_DOUBLE_EQ(volume->valuedouble,.2);
    auto flow=cJSON_GetObjectItemCaseSensitive(root.get(),"warmWaterAvgFlowV2");
    ASSERT_TRUE(cJSON_IsNumber(flow));EXPECT_DOUBLE_EQ(flow->valuedouble,1.2);
    EXPECT_LT(bytes.size(),size_t(1024)); // Explicit bounded metric payload, not a transport/board claim.
}

TEST(EmsMetrics, RealTelegramOffsetsFragmentsSentinelsAndSourceAdmission) {
    MetricsHarness h;
    EXPECT_NE(h.json().find("\"totalEnergyUsedKwh\":null"), std::string::npos);
    h.send(4,4,{24});
    h.send(0xE4,10,{50,3}); // heating, gas+circulation
    h.send(0xE9,11,{12});
    h.now=10000;
    h.send(0xE4,10,{0,0});
    h.send(0xE9,11,{0});
    auto a = h.metrics.getGasBurnedKwh(), b = h.metrics.getGasBurnedKwh();
    EXPECT_EQ(a,b);
    EXPECT_DOUBLE_EQ(std::get<0>(a), 12.0 * 10000 / 3600000);
    EXPECT_DOUBLE_EQ(std::get<1>(a), std::get<0>(a));
    EXPECT_DOUBLE_EQ(std::get<0>(h.metrics.getWarmWaterUsage()), .2);
    EXPECT_DOUBLE_EQ(std::get<1>(h.metrics.getWarmWaterUsage()), 1.2);
    EXPECT_EQ(h.json(), h.json());
    h.send(0xE4,10,{100,3},16); // not boiler
    h.send(0xE4,10,{100,3},8,EmsTelegram::READ);
    h.send(0xE4,10,{100,3},8,EmsTelegram::READ_WITH_DATA);
    h.now=20000;
    h.send(0xE4,10,{255,0}); // unavailable; previous zero must not become100%
    EXPECT_EQ(h.metrics.getGasBurnedKwh(),a);
    EXPECT_NE(h.json().find("\"metricsSchema\":2"),std::string::npos);
    EXPECT_NE(h.json().find("estimated_nominal_modulation"),std::string::npos);
}

TEST(EmsMetricTotals, UnknownFlameDoesNotInventEnergyAndReportedOffStopsEstimate) {
    EmsMetricTotals m;
    m.nominal(0, 24); m.power(0, 50);
    m.power(10000, 50);
    EXPECT_FALSE(m.snapshot(10000).energyObserved);
    m.modes(10000, true, false, true);
    m.modes(20000, true, false, false); // power unchanged, flame explicitly off
    m.power(30000, 50);
    EXPECT_DOUBLE_EQ(m.snapshot(30000).energyKwh, 12.0 * 10000 / 3600000);
}

TEST(EmsMetricTotals, FlowGapAndExplicitUnavailableNeverExtendToNextHour) {
    EmsMetricTotals m;
    m.flow(0, 12); m.flow(3600000, 255);
    auto s = m.snapshot(3600000);
    EXPECT_DOUBLE_EQ(s.waterLitres, .6);
    ASSERT_TRUE(s.averageFlow);
    EXPECT_DOUBLE_EQ(*s.averageFlow, 1.2);
    EXPECT_FALSE(s.currentFlow);
}

TEST(EmsMetrics, OutdoorSignedZeroInvalidAndStaleNeverPersistAsCurrent) {
    MetricsHarness h;
    h.send(UBAOutdoorTemp::predefinedTypeId,0,{0,0});
    ASSERT_TRUE(h.metrics.getOutdoorTemperature());
    EXPECT_DOUBLE_EQ(*h.metrics.getOutdoorTemperature(),0);
    h.send(0xD1,0,{0xFF,0xEA});
    EXPECT_DOUBLE_EQ(*h.metrics.getOutdoorTemperature(),-2.2);
    h.now=180000;
    EXPECT_FALSE(h.metrics.getOutdoorTemperature());
    h.send(0xD1,0,{0x80,0x00});
    EXPECT_FALSE(h.metrics.getOutdoorTemperature());
    h.send(0xD1,0,{0x01}); // incomplete word cannot invent a new value
    EXPECT_FALSE(h.metrics.getOutdoorTemperature());
}
}
