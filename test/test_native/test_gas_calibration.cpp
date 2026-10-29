#include "control/GasCalibration.h"
#include "control/WeatherCurve.h"
#include <gtest/gtest.h>
#include <memory>

namespace {
using heating::control::CurveLearner;
using heating::control::GasCalibration;
using heating::control::WeatherCurve;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
constexpr float kwhPerM3 = 9.77f;

// A boiler at a steady modulation; the real gas is `scale` x modulation x 22 kW.
struct Meter {
    GasCalibration gas;
    uint64_t now = 0;
    double totalM3 = 1000, scale = 1.1;
    uint8_t modulation = 40;
    bool hotWater = false;
    // 10 s burner steps for `ms`; a meter reading every `everyMs` (the total
    // as the meter last counted it, `stepM3` resolution: DSMR 4 sends hourly).
    void run(uint64_t ms, uint64_t everyMs, uint64_t meterStepMs = 0) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            gas.burner(10 * second, modulation, hotWater, 22);
            exact_ += modulation / 100.0 * 22 * scale * 10 / 3600.0 / kwhPerM3;
            if (!meterStepMs || now % meterStepMs == 0) counted_ = exact_;
            if (now % everyMs == 0) gas.meter(totalM3 + counted_, now, kwhPerM3);
        }
    }
    double exact_ = 0, counted_ = 0;
};

TEST(GasCalibration, WithoutAMeterTheEstimateStaysRoughAndSaysSo) {
    GasCalibration gas;
    for (int i = 0; i < 100; ++i) gas.burner(10 * second, 50, false, 22);
    EXPECT_STREQ(gas.status(hour, 2 * hour), "no_meter");
    EXPECT_STREQ(gas.confidence(), "none");
    EXPECT_EQ(gas.factor(), 1.0f);
    Json o(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(gas.json(o.get(), hour, 2 * hour, 22));
    EXPECT_STREQ(cJSON_GetObjectItem(o.get(), "kw_source")->valuestring, "boiler_kw");
    EXPECT_EQ(cJSON_GetObjectItem(o.get(), "kw_at_full_modulation")->valuedouble, 22);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(o.get(), "spread")));
}

// DSMR 5 meters (and HA's 5-minute refresh) report far more often than the
// 55-minute interval: the interval runs on instead of restarting each time.
TEST(GasCalibration, FrequentReadingsStillCalibrate) {
    Meter m;
    m.run(8 * hour, 5 * minute);
    EXPECT_GE(m.gas.intervals(), 6);
    EXPECT_STREQ(m.gas.status(m.now, 2 * hour), "calibrated");
    EXPECT_NEAR(m.gas.factor(), 1.1, 0.01);
    EXPECT_STRNE(m.gas.confidence(), "none");
    Json o(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(m.gas.json(o.get(), m.now, 2 * hour, 22));
    EXPECT_STREQ(cJSON_GetObjectItem(o.get(), "kw_source")->valuestring, "meter");
    EXPECT_NEAR(cJSON_GetObjectItem(o.get(), "kw_at_full_modulation")->valuedouble, 24.2, 0.15);
}

// DSMR 4: the total changes once an hour, HA repeats it every 5 minutes; a
// repeat must not end an interval (it would compare zero gas with real heat).
TEST(GasCalibration, HourlyMeterWithRepeatsCalibrates) {
    Meter m;
    m.run(14 * hour, 5 * minute, hour);
    EXPECT_GE(m.gas.intervals(), 10);
    EXPECT_EQ(m.gas.rejected(), 0);
    EXPECT_NEAR(m.gas.factor(), 1.1, 0.02);
    EXPECT_STREQ(m.gas.confidence(), "high"); // consistent intervals
}

TEST(GasCalibration, HotWaterAndGapsSpoilOnlyTheirInterval) {
    Meter m;
    m.run(3 * hour, 5 * minute);
    const auto before = m.gas.intervals();
    m.hotWater = true; m.run(10 * minute, 5 * minute); m.hotWater = false;
    EXPECT_STREQ(m.gas.last(), "hot_water");
    m.run(50 * minute, 5 * minute);
    EXPECT_EQ(m.gas.intervals(), before);     // the hot water interval is not compared
    m.run(2 * hour, 5 * minute);
    EXPECT_GT(m.gas.intervals(), before);     // the next ones are
    EXPECT_GT(m.gas.hotWaterKwh(), 0);
    const auto counted = m.gas.intervals();
    m.gas.burner(0, 40, false, 22);           // a gap
    m.run(50 * minute, 5 * minute);
    EXPECT_EQ(m.gas.intervals(), counted);
    EXPECT_NEAR(m.gas.factor(), 1.1, 0.01);
}

TEST(GasCalibration, ImplausibleIntervalsAreRejected) {
    Meter m;
    m.scale = 5;                               // a meter in the wrong unit or another appliance
    m.run(5 * hour, 5 * minute);
    EXPECT_EQ(m.gas.intervals(), 0);
    EXPECT_GE(m.gas.rejected(), 3);
    EXPECT_STREQ(m.gas.last(), "ratio_out_of_range");
    EXPECT_EQ(m.gas.factor(), 1.0f);
    // A replaced meter (lower total) starts again.
    m.gas.meter(10, m.now + minute, kwhPerM3);
    EXPECT_STREQ(m.gas.last(), "meter_reset");
    EXPECT_EQ(*m.gas.meterM3(), 10);
}

TEST(GasCalibration, ConfidenceFollowsAgreement) {
    GasCalibration gas;
    uint64_t now = 0; double total = 0;
    // Intervals of 1 h at 9.77 kWh estimated; measured alternates 0.6 and 1.4 x.
    for (int i = 0; i < 14; ++i) {
        gas.meter(total, now, kwhPerM3);
        for (int k = 0; k < 360; ++k) gas.burner(10 * second, 44, false, 22.2f);
        now += hour; total += (i % 2 ? 0.6 : 1.4) * 0.9768;
    }
    gas.meter(total, now, kwhPerM3);
    EXPECT_GE(gas.intervals(), 12);
    EXPECT_GT(*gas.spread(), 0.2f);
    EXPECT_STREQ(gas.confidence(), "low");
    EXPECT_STREQ(gas.status(now + 3 * hour, 2 * hour), "meter_stale");
}

TEST(WeatherCurve, DesignFlowsGiveTheSlope) {
    EXPECT_NEAR(WeatherCurve::slopeFor(40), 0.667f, 0.001f);
    EXPECT_NEAR(WeatherCurve::slopeFor(55), 1.167f, 0.001f);
    EXPECT_EQ(WeatherCurve::slopeFor(20), WeatherCurve::minSlope);
    EXPECT_EQ(WeatherCurve::baseCentiC(WeatherCurve::slopeFor(40), 2000, -1000), 4000);
    EXPECT_EQ(WeatherCurve::baseCentiC(WeatherCurve::slopeFor(55), 2000, -1000), 5500);
    EXPECT_EQ(WeatherCurve::baseCentiC(0.667f, 2000, 2500), 2000);   // warmer outside: the room itself
    EXPECT_EQ(WeatherCurve::baseCentiC(0.5f, 2100, 1100), 2600);
    EXPECT_EQ(WeatherCurve::baseCentiC(10, 2000, 1000), 2000 + 2500);       // slope at most 2.5
    EXPECT_EQ(WeatherCurve::baseCentiC(2.5f, 2000, -6000), 9000);         // never above 90 degC
}

// A window opens at its first sample: 3 h of samples after it.
constexpr uint64_t window = 3 * hour + 10 * second;
// A room held at its setpoint at 5 degC outdoor with the burner at 40 degC half
// of the time: Feq = 20 + 0.5 x (40 - 20) = 30, slope (30 - 20) / 15 = 0.67.
struct Holding {
    CurveLearner learner;
    uint64_t now = 0;
    int16_t room = 2000, setpoint = 2000, outdoor = 500, flow = 4000;
    bool hotWater = false;
    double duty = 0.5;
    void run(uint64_t ms, int16_t driftPerHour = 0) {
        const uint64_t end = now + ms, from = now;
        while (now < end) {
            now += 10 * second;
            CurveLearner::Sample s;
            s.room = 0; s.setpointCentiC = setpoint; s.outdoorCentiC = outdoor;
            s.roomCentiC = int16_t(room + int64_t(driftPerHour) * int64_t(now - from) / int64_t(hour));
            s.hotWater = hotWater;
            s.burnerOn = (now / (10 * second)) % 100 < uint64_t(duty * 100);
            s.flowCentiC = *s.burnerOn ? flow : int16_t(2500);
            learner.sample(now, s);
        }
    }
};

TEST(CurveLearner, HoldingWindowsGiveTheSlope) {
    Holding h;
    h.run(5 * window);
    EXPECT_EQ(h.learner.windows(), 5);
    EXPECT_FALSE(h.learner.slope());           // six windows first
    h.outdoor = -500; h.duty = 0.75;           // colder: 20 + 0.75 x 20 = 35 at 25 K -> 0.6
    h.run(3 * window);
    ASSERT_TRUE(h.learner.slope());
    EXPECT_GT(*h.learner.slope(), 0.6f); EXPECT_LT(*h.learner.slope(), 0.667f);
    EXPECT_STREQ(h.learner.last(), "window_learned");
}

TEST(CurveLearner, UnsteadyOrUnclearWindowsAreRejected) {
    Holding h;
    h.run(window, 30);                       // 0.9 degC rise in the window
    EXPECT_STREQ(h.learner.last(), "room_not_steady");
    h.room = 1900; h.run(window);            // 1 degC below its setpoint
    EXPECT_STREQ(h.learner.last(), "not_at_setpoint");
    h.room = 2000; h.outdoor = 1700; h.run(window);
    EXPECT_STREQ(h.learner.last(), "too_mild");
    h.outdoor = 500; h.duty = 0; h.run(window);
    EXPECT_STREQ(h.learner.last(), "no_heat");  // internal gains hold it: nothing to learn
    h.duty = 0.5; h.hotWater = true; h.run(window);
    EXPECT_STREQ(h.learner.last(), "hot_water");
    EXPECT_EQ(h.learner.windows(), 0);
    EXPECT_EQ(h.learner.rejected(), 5);
    h.hotWater = false;
    h.run(hour); h.setpoint = 2100; h.run(10 * second);
    EXPECT_STREQ(h.learner.last(), "window_interrupted");
    h.now += 5 * minute; h.run(10 * second);   // a gap interrupts too
    EXPECT_EQ(h.learner.rejected(), 5);
}
}
