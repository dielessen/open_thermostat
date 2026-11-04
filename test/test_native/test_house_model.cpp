#include "control/HouseModel.h"
#include "control/ShadowComparison.h"
#include "ScopedTz.h"
#include "SyntheticHouse.h"
#include <gtest/gtest.h>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

// rc.5 (P2): HouseModel, the house's heat loss per K (UA) and the emitters' output per K of flow,
// and the weather curve slope they imply, on the synthetic house of SyntheticHouse.h whose answers
// are known (floor slope 0.02 / 0.035 = 0.571, radiator 0.05 / 0.1 = 0.5).
namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

std::string print(const cJSON* o) { char* t = cJSON_PrintUnformatted(o); std::string s = t; cJSON_free(t); return s; }
std::string json(const HouseModel& h) { Json root(cJSON_CreateObject(), cJSON_Delete); EXPECT_TRUE(h.addJson(root.get())); return print(root.get()); }
// A Scoreboard whose Insights hold `days` days of gas per degree-day: 8 degC all day (10 DD), 40 kWh a day.
Scoreboard gasBoard(int days) {
    Scoreboard board;
    const int64_t start = int64_t(ShadowComparison::daysFromCivil(2026, 11, 2)) * 86400 - 3600; // Monday 00:00 CET
    double kwh = 0;
    for (int64_t t = start + 60; t <= start + days * 86400 + 60; t += 60) {
        kwh += 40.0 / 1440;
        if (board.step(t, 60, int16_t(800), kwh)) {
            AutoTuner::Day tuned; tuned.day = board.yesterday()->day; tuned.hours = 0xFFFFF; tuned.starts = 40;
            board.judge(tuned, nullptr, 0);
        }
    }
    return board;
}
}

TEST(HouseModel, TwoRoomsWithALearnedHeatLossGiveTheCurvesSlope) {
    SyntheticHouse s(2);
    s.learn();
    std::vector<float> ua;
    for (size_t i = 0; i < 2; ++i) { const auto m = s.learner.heatModel(i); ASSERT_TRUE(m.uaKwPerK) << i; ua.push_back(*m.uaKwPerK); }
    HouseModel h;
    h.update({&s.learner, nullptr, std::nullopt, &s.plan});
    ASSERT_STREQ(h.state(), "learned") << json(h);
    EXPECT_STREQ(h.uaSource(), "rooms"); EXPECT_STREQ(h.kwSource(), "rooms");
    EXPECT_NEAR(*h.uaKwPerK(), (ua[0] + ua[1]) / 2, 1e-6) << "the median of two rooms";
    const double k = s.k(), slope = (0.02 / 0.035 + 0.05 / 0.1) / 2;
    std::printf("[ house model ] synthetic 2 rooms: UA %.4f kW/K (rooms %.4f, %.4f), k %.4f kW/K (true %.4f), slope %.3f (true %.3f)\n",
                *h.uaKwPerK(), ua[0], ua[1], *h.kwPerFlowK(), k, *h.slope(), slope);
    EXPECT_NEAR(*h.kwPerFlowK(), k, 0.1 * k);
    EXPECT_NEAR(*h.slope(), slope, 0.1 * slope);
    EXPECT_NEAR(*h.slope(), *h.uaKwPerK() / *h.kwPerFlowK(), 1e-5);
    const auto text = json(h);
    EXPECT_EQ(text.find(R"("state":"learned")"), text.size() - 19) << text;
}

// One room (the owner's first release: the living room only): its UA alone does not count; three local
// days of gas per degree-day do, through the degree-day method.
TEST(HouseModel, OneRoomNeedsThreeDaysOfGasPerDegreeDay) {
    ScopedTz tz(ScopedTz::amsterdam);
    SyntheticHouse s(1);
    s.learn();
    ASSERT_TRUE(s.learner.heatModel(0).uaKwPerK);
    HouseModel h;
    h.update({&s.learner, nullptr, std::nullopt, &s.plan});
    EXPECT_STREQ(h.state(), "collecting");
    EXPECT_FALSE(h.uaKwPerK());
    ASSERT_TRUE(h.kwPerFlowK()) << "the room's own model gives the emitters' output";
    EXPECT_NEAR(*h.kwPerFlowK(), s.k(), 0.1 * s.k());
    const auto two = gasBoard(2), three = gasBoard(3);
    ASSERT_EQ(two.insights().baseline(0).days, 2);
    h.update({&s.learner, &two, std::nullopt, &s.plan});
    EXPECT_STREQ(h.state(), "collecting");
    h.update({&s.learner, &three, std::nullopt, &s.plan});
    ASSERT_STREQ(h.state(), "learned");
    EXPECT_STREQ(h.uaSource(), "gas");
    // 4 kWh of gas per degree-day x the condensing efficiency at a 40 degC return / 24 h.
    EXPECT_NEAR(*three.insights().gasPerDegreeDay(3), 4.0, 0.01);
    EXPECT_NEAR(*h.uaKwPerK(), 4.0 * FlowLearner::efficiency(40) / 24, 0.002);
    EXPECT_NEAR(*h.slope(), *h.uaKwPerK() / *h.kwPerFlowK(), 1e-5);
}

// The boiler's measured output per K (P1's BoilerResponse) wins over the rooms' estimate.
TEST(HouseModel, TheBoilersMeasuredOutputPerKWins) {
    SyntheticHouse s(2);
    s.learn();
    HouseModel h;
    h.update({&s.learner, nullptr, 0.5f, &s.plan});
    EXPECT_STREQ(h.kwSource(), "boiler");
    EXPECT_FLOAT_EQ(*h.kwPerFlowK(), 0.5f);
    EXPECT_NEAR(*h.slope(), *h.uaKwPerK() / 0.5f, 1e-5);
    h.update({&s.learner, nullptr, 0.0f, &s.plan});            // not a value: the rooms' again
    EXPECT_STREQ(h.kwSource(), "rooms");
    h.update({&s.learner, nullptr, 0.001f, &s.plan});          // a slope beyond the curve's bounds is bounded
    EXPECT_FLOAT_EQ(*h.slope(), WeatherCurve::maxSlope);
    h.update({&s.learner, nullptr, 1000.0f, &s.plan});
    EXPECT_FLOAT_EQ(*h.slope(), WeatherCurve::minSlope);
}

// Universal: without burner power or an outdoor temperature nothing is modelled; the design slope stays.
TEST(HouseModel, WithoutBurnerPowerOrOutdoorItStaysCollecting) {
    for (const bool modulation : {false, true}) {
        SyntheticHouse s(2);
        s.modulation = modulation; s.outdoorKnown = !modulation;
        s.learn();
        HouseModel h;
        h.update({&s.learner, nullptr, std::nullopt, &s.plan});
        EXPECT_STREQ(h.state(), "collecting") << modulation;
        EXPECT_FALSE(h.uaKwPerK()); EXPECT_FALSE(h.kwPerFlowK()); EXPECT_FALSE(h.slope());
    }
    HouseModel none;
    none.update({});
    EXPECT_EQ(json(none), R"({"house":{"ua_kw_per_k":null,"kw_per_flow_k":null,"slope":null,"state":"collecting"}})");
}

// The JSON at its widest stays within the contract's 110 B.
TEST(HouseModel, TheJsonStaysWithinItsBound) {
    SyntheticHouse s(2);
    s.learn();
    HouseModel h;
    h.update({&s.learner, nullptr, 0.123456f, &s.plan});
    const auto text = json(h);
    std::printf("[ house model ] %zu B: %s\n", text.size(), text.c_str());
    EXPECT_LE(text.size() - 2 + 1, 110u) << "as a member: a comma and the member";
}
