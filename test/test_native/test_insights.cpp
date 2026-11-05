#include "control/Insights.h"
#include <gtest/gtest.h>
#include <cstring>
#include <memory>
#include <string>

// rc.5 (P2): Insights, yesterday against the house's own usual figures. The baselines (a plain mean
// over the first five days, then an exponential mean), the judgement from the 5th day before the
// fold, the 30 % and floor thresholds, at most four items, the stored form and a plan edit.
namespace {
using heating::control::Insights;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
using Kind = Insights::Kind;

Insights::Day day(std::optional<float> gas, std::optional<float> starts = 2, std::optional<float> hours = 1) {
    Insights::Day d;
    d.heated = true; d.gasPerDegreeDay = gas; d.startsPerHour = starts; d.hoursPerDegreeDay = hours;
    return d;
}
RoomPlan plan(size_t rooms = 3) {
    RoomPlan p;
    for (size_t i = 0; i < rooms; ++i) { RoomPlan::Room r; r.id = r.name = "room" + std::to_string(i); r.state = RoomDemand::State::active; p.rooms.push_back(r); }
    return p;
}
std::string json(const Insights& in, const RoomPlan& p) {
    Json root(cJSON_CreateObject(), cJSON_Delete);
    EXPECT_TRUE(in.addJson(root.get(), p));
    char* text = cJSON_PrintUnformatted(root.get());
    std::string s = text; cJSON_free(text);
    return s;
}
}

TEST(Insights, ABaselineIsAPlainMeanOverFiveDaysThenAnExponentialMean) {
    Insights in;
    for (const float v : {2.0f, 3.0f, 4.0f, 3.0f, 3.0f}) in.dayChange(day(v));
    EXPECT_EQ(in.baseline(0).days, 5);
    EXPECT_NEAR(in.baseline(0).value, 3.0, 1e-5) << "the first day weighs as much as the fifth";
    in.dayChange(day(3.5f));                                  // the sixth: alpha 0.2
    EXPECT_NEAR(in.baseline(0).value, 3.0 + 0.2 * 0.5, 1e-5);
    for (int i = 0; i < 10; ++i) in.dayChange(day(3.5f));
    EXPECT_EQ(in.baseline(0).days, Insights::maxDays);
    EXPECT_GT(in.baseline(0).value, 3.45f);
    EXPECT_NEAR(in.baseline(1).value, 2, 1e-6); EXPECT_NEAR(in.baseline(2).value, 1, 1e-6);
    EXPECT_EQ(in.gasPerDegreeDay(3).has_value(), true);
    EXPECT_FALSE(Insights().gasPerDegreeDay());
}

// The 5th day is the first judged, against the four before it, and only then folded in.
TEST(Insights, FromTheFifthDayYesterdayIsJudgedBeforeItIsFoldedIn) {
    Insights in;
    for (int i = 0; i < 3; ++i) in.dayChange(day(2.0f));
    in.dayChange(day(4.0f));                                  // the 4th day: no judgement yet (3 days in the baseline)
    EXPECT_EQ(in.count(), 0u);
    EXPECT_NEAR(in.baseline(0).value, 2.5, 1e-5);
    in.dayChange(day(3.5f));                                  // the 5th: 3.5 against 2.5 = +40 % and +1.0 kWh/DD
    ASSERT_EQ(in.count(), 1u);
    EXPECT_EQ(in.item(0).kind, Kind::gasPerDdUp);
    EXPECT_EQ(in.item(0).pct, 40);
    EXPECT_EQ(in.item(0).room, -1);
    EXPECT_NEAR(in.baseline(0).value, 2.7, 1e-5) << "folded in after the judgement";
    in.dayChange(day(2.7f));                                  // a usual day: the item goes
    EXPECT_EQ(in.count(), 0u);
    in.dayChange(day(1.6f));                                  // -40 %
    ASSERT_EQ(in.count(), 1u);
    EXPECT_EQ(in.item(0).kind, Kind::gasPerDdDown);
    EXPECT_EQ(json(in, plan()), R"({"insights":[{"kind":"gas_per_dd_down","pct":41}]})");
}

// More than 30 % and more than the floor: small figures do not make big percentages.
TEST(Insights, BothThirtyPercentAndTheFloorMustBeExceeded) {
    Insights in;
    for (int i = 0; i < 5; ++i) in.dayChange(day(1.0f, 1.0f, 0.5f));
    in.dayChange(day(1.45f, 1.9f, 0.95f));                    // +45 %, +90 %, +90 % but each below its floor
    EXPECT_EQ(in.count(), 0u) << json(in, plan());
    Insights big;
    for (int i = 0; i < 5; ++i) big.dayChange(day(4.0f, 3.0f, 2.0f));
    big.dayChange(day(5.1f, 3.8f, 2.55f));                    // +27.5 %, +26.7 %, +27.5 %: above the floors, not 30 %
    EXPECT_EQ(big.count(), 0u) << json(big, plan());
    big.dayChange(day(5.6f, 4.3f, 2.9f));                     // all beyond: gas, starts, hours in that order
    ASSERT_EQ(big.count(), 3u) << json(big, plan());
    EXPECT_EQ(big.item(0).kind, Kind::gasPerDdUp);
    EXPECT_EQ(big.item(1).kind, Kind::startsUp);
    EXPECT_EQ(big.item(2).kind, Kind::hoursPerDdUp);
    // Fewer starts and fewer hours are no news: only up.
    Insights fewer;
    for (int i = 0; i < 5; ++i) fewer.dayChange(day(4.0f, 4.0f, 2.0f));
    fewer.dayChange(day(4.0f, 1.0f, 0.5f));
    EXPECT_EQ(fewer.count(), 0u);
}

// A day without heating (< 1 heating hour) neither judges nor folds; it leaves no items.
TEST(Insights, ADayWithoutHeatingNeitherJudgesNorFolds) {
    Insights in;
    for (int i = 0; i < 5; ++i) in.dayChange(day(2.0f));
    in.dayChange(day(3.0f));
    ASSERT_EQ(in.count(), 1u);
    const auto before = in.baseline(0);
    Insights::Day summer = day(9.0f);
    summer.heated = false;
    in.dayChange(summer);
    EXPECT_EQ(in.count(), 0u) << "yesterday's items described the day before";
    EXPECT_EQ(in.baseline(0).days, before.days);
    EXPECT_FLOAT_EQ(in.baseline(0).value, before.value);
    // A figure unknown that day is skipped alone (no gas estimate, too mild for degree-days).
    in.dayChange(day(std::nullopt, 2, std::nullopt));
    EXPECT_EQ(in.baseline(0).days, before.days);
    EXPECT_EQ(in.baseline(1).days, before.days + 1);
}

// Per room only slower (15 min/degC floor); at most four items: the house first, then the largest room changes.
TEST(Insights, AtMostFourItemsTheHouseFirstThenTheSlowestRooms) {
    Insights in;
    const auto rooms = [](float a, float b, float c, float d) {
        Insights::Day x = day(2.0f, 2.0f, 1.0f);
        x.warmupMinPerC[0] = a; x.warmupMinPerC[1] = b; x.warmupMinPerC[2] = c; x.warmupMinPerC[5] = d;
        return x;
    };
    for (int i = 0; i < 5; ++i) in.dayChange(rooms(40, 60, 120, 30));
    Insights::Day y = rooms(60, 90, 300, 20);                 // +50 %, +50 %, +150 %, faster
    y.gasPerDegreeDay = 3.0f; y.startsPerHour = 3.5f;         // +50 %, +75 % (and 1.5 starts more)
    in.dayChange(y);
    ASSERT_EQ(in.count(), 4u);
    EXPECT_EQ(in.item(0).kind, Kind::gasPerDdUp);
    EXPECT_EQ(in.item(1).kind, Kind::startsUp);
    EXPECT_EQ(in.item(2).kind, Kind::warmupSlower); EXPECT_EQ(in.item(2).room, 2); EXPECT_EQ(in.item(2).pct, 150);
    EXPECT_EQ(in.item(3).kind, Kind::warmupSlower); EXPECT_EQ(in.item(3).pct, 50);
    const auto p = plan(6);
    const auto text = json(in, p);
    EXPECT_NE(text.find(R"({"kind":"warmup_slower","pct":150,"room":"room2"})"), std::string::npos) << text;
    // 20 min/degC slower on 40 is +50 % but a 15 min/degC floor still lets it through; 10 on 40 does not.
    Insights small;
    for (int i = 0; i < 5; ++i) small.dayChange(rooms(40, 40, 40, 40));
    small.dayChange(rooms(54, 40, 40, 40));                   // +35 %, 14 min: below the floor
    EXPECT_EQ(small.count(), 0u);
}

// The record's two packed arrays: what comes back is what was kept, anything unreadable comes back empty.
TEST(Insights, TheStoredFormComesBackAndRefusesWhatItCannotRead) {
    Insights in;
    for (int i = 0; i < 5; ++i) { Insights::Day d = day(2.35f, 1.3f, 0.85f); d.warmupMinPerC[1] = 45; in.dayChange(d); }
    Insights::Day y = day(4.0f, 1.3f, 0.85f); y.warmupMinPerC[1] = 80;
    in.dayChange(y);
    ASSERT_EQ(in.count(), 2u);
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(in.addStored(root.get(), true));
    char* text = cJSON_PrintUnformatted(root.get());
    const std::string stored = text; cJSON_free(text);
    // gas 2.35 + 0.2 x 1.65 = 2.68 kWh/DD over 6 days; starts 1.30; hours 0.85; room 0 none; room 1 45 + 0.2 x 35 = 52.
    // Items: gas +70 % (house), room 1 +78 %.
    EXPECT_EQ(stored, R"({"b":[2686,1306,856,0,526],"x":[7000,7842]})");
    Insights back;
    back.restoreStored(root.get());
    EXPECT_NEAR(back.baseline(0).value, 2.68, 1e-4); EXPECT_EQ(back.baseline(0).days, 6);
    EXPECT_EQ(back.baseline(3).days, 0);
    EXPECT_NEAR(back.baseline(4).value, 52, 1e-4);
    ASSERT_EQ(back.count(), 2u);
    EXPECT_EQ(back.item(1).kind, Kind::warmupSlower); EXPECT_EQ(back.item(1).room, 1); EXPECT_EQ(back.item(1).pct, 78);
    // Without items (the record was full): only "b".
    Json bare(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(in.addStored(bare.get(), false));
    EXPECT_FALSE(cJSON_GetObjectItem(bare.get(), "x"));
    // A record of rc.4 has neither; a damaged part comes back empty (never half loaded), the other part stays.
    const struct { const char* text; bool baselines; size_t items; } records[] = {
        {R"({})", false, 0}, {R"({"b":[1,2,"x"],"x":[3500]})", false, 1}, {R"({"b":[99999999],"x":[3501]})", false, 0},
        {R"({"b":[1,2,3,4,5,6,7,8,9,10,11,12]})", false, 0}, {R"({"b":[-5]})", false, 0}, {R"({"b":[2.5]})", false, 0},
        {R"({"b":[2354],"x":[3504]})", true, 0}, {R"({"x":[3550]})", false, 0}, {R"({"x":[1,2,3,4,5]})", false, 0},
        {R"({"b":[0,0,0,0,455],"x":[4043]})", true, 1}};
    for (const auto& r : records) {
        Json doc(cJSON_Parse(r.text), cJSON_Delete);
        Insights back2 = in;
        back2.restoreStored(doc.get());
        size_t days = 0;
        for (size_t f = 0; f < Insights::figures; ++f) days += back2.baseline(f).days;
        EXPECT_EQ(days > 0, r.baselines) << r.text;
        EXPECT_EQ(back2.count(), r.items) << r.text;
    }
}

// The widest stored form: every figure at its bound over nine days, four items with three-digit changes.
TEST(Insights, TheWidestStoredFormIsBounded) {
    Insights in;
    for (int i = 0; i < 9; ++i) {
        Insights::Day d = day(5000.0f, 500.0f, 99.0f);
        for (auto& w : d.warmupMinPerC) w = 5000.0f;
        in.dayChange(d);
    }
    Json root(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(in.addStored(root.get(), false));
    char* text = cJSON_PrintUnformatted(root.get());
    const std::string b = text; cJSON_free(text);
    EXPECT_EQ(b, R"({"b":[999999,99999,24009,9999,9999,9999,9999,9999,9999,9999,9999]})");
    EXPECT_EQ(b.size() - 2 + 1, 65u) << "as a member of the record: a comma and the member (Scoreboard::storedMaxBytes)";
    Insights items;
    for (int i = 0; i < 5; ++i) { Insights::Day d = day(1, 1, 1); for (auto& w : d.warmupMinPerC) w = 20; items.dayChange(d); }
    Insights::Day y = day(30, 30, 30);
    for (auto& w : y.warmupMinPerC) w = 999;
    items.dayChange(y);
    ASSERT_EQ(items.count(), 4u);
    Json x(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(items.addStored(x.get(), true));
    text = cJSON_PrintUnformatted(cJSON_GetObjectItem(x.get(), "x"));
    const std::string xs = text; cJSON_free(text);
    EXPECT_LE(xs.size() + 5, 30u) << xs;
}

// A plan edit: the rooms' baselines and their items follow the rooms; a room that left takes its item along.
TEST(Insights, APlanEditMovesTheRoomsBaselinesAndItems) {
    Insights in;
    for (int i = 0; i < 5; ++i) { Insights::Day d = day(2); d.warmupMinPerC[0] = 30; d.warmupMinPerC[2] = 60; in.dayChange(d); }
    Insights::Day y = day(2); y.warmupMinPerC[0] = 60; y.warmupMinPerC[2] = 120;
    in.dayChange(y);
    ASSERT_EQ(in.count(), 2u);
    std::array<int8_t, RoomPlan::maxRooms> from{};
    from.fill(-1);
    from[0] = 2; // the old third room is now the first; the old first left the plan
    in.remap(from);
    EXPECT_NEAR(in.baseline(Insights::houseFigures).value, 72, 1e-4);
    EXPECT_EQ(in.baseline(Insights::houseFigures + 2).days, 0);
    ASSERT_EQ(in.count(), 1u);
    EXPECT_EQ(in.item(0).room, 0);
    EXPECT_EQ(in.baseline(0).days, 6) << "the house's baselines stay";
}
