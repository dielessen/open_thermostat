#include "control/ArrivalLearner.h"
#include "control/LearnedState.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <memory>

// rc.4 (L2): the arrival-time feedback. Each judged morning moves a room's lead factor:
// late (> 10 min) +10 %, early (> 15 min) -8 %, within 0.5..2.0; only a start the policy
// applied teaches; a room that never arrives counts as late; a plan edit keeps the factor by id.
namespace {
using heating::control::ArrivalLearner;
using heating::control::LeadFactor;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr int64_t t0 = 1'800'000'000;                   // some morning, 00:00 of the rise's day in the test's reckoning
const ArrivalLearner::Rise rise{t0 + 8 * 3600, t0 + 6 * 3600, 2100}; // switch 08:00, planned start 06:00, 21 degC

RoomPlan plan(std::initializer_list<const char*> ids = {"woonkamer"}) {
    RoomPlan p;
    for (const char* id : ids) { RoomPlan::Room r; r.id = r.name = id; r.state = RoomDemand::State::active; p.rooms.push_back(r); }
    return p;
}
// A morning: the room sits at `night` until the start, then warms linearly to be within the
// margin of the target at `arriveAt` (0: never) and at the target from then on; the start is
// `applied` from its planned time. Observed once a minute from `from` (default: an hour before
// the start) to `until` (default: 4 h after the switch).
void morning(ArrivalLearner& a, size_t room, ArrivalLearner::Rise r, int16_t night, int64_t arriveAt, bool applied = true, int64_t from = 0, int64_t until = 0) {
    const int64_t begin = from ? from : r.startUtc - 3600, end = until ? until : r.atUtc + 4 * 3600;
    const int16_t arrived = int16_t(r.toCentiC - 10);
    for (int64_t t = begin; t <= end; t += 60) {
        int16_t temp = night;
        if (arriveAt && t >= arriveAt) temp = r.toCentiC;
        else if (arriveAt && t >= r.startUtc) temp = int16_t(night + int64_t(arrived - night) * (t - r.startUtc) / std::max<int64_t>(1, arriveAt - r.startUtc));
        a.observe(room, t, r, applied && t >= r.startUtc, temp);
    }
}
}

TEST(ArrivalLearner, LateMorningsRaiseTheFactorEarlyOnesLowerIt) {
    ArrivalLearner a; a.setPlan(plan());
    EXPECT_FLOAT_EQ(a.lead(0).factor, 1.0f); EXPECT_FALSE(a.lead(0).trusted);
    morning(a, 0, rise, 1850, rise.atUtc + 15 * 60);            // 15 min late
    EXPECT_EQ(a.events(0), 1u);
    EXPECT_NEAR(a.lead(0).factor, 1.10f, 1e-5);
    ASSERT_TRUE(a.lastErrorMin(0)); EXPECT_EQ(*a.lastErrorMin(0), 15);
    ArrivalLearner::Rise next = rise; next.atUtc += 86400; next.startUtc += 86400;
    morning(a, 0, next, 1850, next.atUtc - 25 * 60);           // 25 min early
    EXPECT_NEAR(a.lead(0).factor, 1.10f * 0.92f, 1e-5);
    EXPECT_EQ(*a.lastErrorMin(0), -25);
    next.atUtc += 86400; next.startUtc += 86400;
    morning(a, 0, next, 1850, next.atUtc + 5 * 60);            // on time (within 10 min): unchanged, now trusted
    EXPECT_NEAR(a.lead(0).factor, 1.10f * 0.92f, 1e-5);
    EXPECT_EQ(a.events(0), 3u); EXPECT_TRUE(a.lead(0).trusted);
    // Bounded: many late mornings stop at 2.0.
    for (int d = 0; d < 20; ++d) { next.atUtc += 86400; next.startUtc += 86400; morning(a, 0, next, 1850, next.atUtc + 30 * 60); }
    EXPECT_FLOAT_EQ(a.lead(0).factor, 2.0f);
    // The events for the scoreboard, oldest first, the newest kept when the queue overflows.
    ArrivalLearner::Event ev; size_t n = 0;
    while (a.pop(ev)) { ++n; EXPECT_EQ(ev.room, 0); EXPECT_EQ(ev.errorMin, 30); }
    EXPECT_EQ(n, ArrivalLearner::eventQueue);
    EXPECT_FALSE(a.pop(ev));
    Json j(a.json(0), cJSON_Delete);
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItem(j.get(), "factor")->valuedouble, 2.0);
    EXPECT_EQ(cJSON_GetObjectItem(j.get(), "events")->valueint, 23);
    EXPECT_EQ(cJSON_GetObjectItem(j.get(), "last_error_min")->valueint, 30);
    EXPECT_DOUBLE_EQ(cJSON_GetObjectItem(j.get(), "last_at_utc")->valuedouble, double(next.atUtc));
}

// LEREN-PLAN-RC4 L2: a default lead twice too long or too short is within 15 min of the true
// warm-up within eight judged mornings. The lead follows the planner: default x factor, in
// 5-minute steps, capped at 3 h (floor) until three mornings were judged.
TEST(ArrivalLearner, ADefaultLeadTwiceOffIsWithinFifteenMinutesAfterEightMornings) {
    for (const int trueMin : {90, 300}) {                      // the default lead is 180 min
        ArrivalLearner a; a.setPlan(plan());
        int64_t at = rise.atUtc; int errorMin = 999; int mornings = 0;
        while (mornings < 8 && std::abs(errorMin) > 15) {
            const LeadFactor f = a.lead(0);
            uint32_t lead = uint32_t(180 * 60 * std::clamp(f.factor, 0.5f, 2.0f));
            if (!f.trusted) lead = std::min<uint32_t>(lead, 3 * 3600);
            lead = (lead + 299) / 300 * 300;
            const ArrivalLearner::Rise r{at, at - lead, 2100};
            morning(a, 0, r, 1850, r.startUtc + trueMin * 60);
            ++mornings; at += 86400;
            ASSERT_EQ(a.events(0), unsigned(mornings));
            errorMin = *a.lastErrorMin(0);
        }
        EXPECT_LE(std::abs(errorMin), 15) << "true warm-up " << trueMin << " min: " << errorMin << " min after " << mornings << " mornings";
        std::printf("[ arrival ] default 180 min, true %d min: within 15 min after %d mornings (last error %d min, factor %.2f)\n",
                    trueMin, mornings, errorMin, double(a.lead(0).factor));
    }
}

TEST(ArrivalLearner, NoShortfallOrAdviceTeachesNothing) {
    ArrivalLearner a; a.setPlan(plan());
    morning(a, 0, rise, 2095, rise.atUtc + 30 * 60);           // already warm at the start: nothing to warm up
    EXPECT_EQ(a.events(0), 0u);
    morning(a, 0, rise, 1850, rise.atUtc + 30 * 60, false);    // advice only: cannot be judged
    EXPECT_EQ(a.events(0), 0u);
    EXPECT_FLOAT_EQ(a.lead(0).factor, 1.0f);
    Json j(a.json(0), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsNull(j.get()));
    EXPECT_FLOAT_EQ(a.lead(5).factor, 1.0f);                   // no such room: neutral
}

TEST(ArrivalLearner, NoArrivalWithinTheWindowCountsAsLate) {
    ArrivalLearner a; a.setPlan(plan());
    morning(a, 0, rise, 1850, 0);                              // never arrives
    EXPECT_EQ(a.events(0), 1u);
    EXPECT_NEAR(a.lead(0).factor, 1.10f, 1e-5);
    EXPECT_EQ(*a.lastErrorMin(0), 180);
    // A judged morning is not judged again when the same rise is still reported.
    a.observe(0, rise.atUtc + 4 * 3600, rise, false, int16_t(2100));
    EXPECT_EQ(a.events(0), 1u);
}

TEST(ArrivalLearner, AChangedProgramBeforeTheSwitchDropsTheWatchedRise) {
    ArrivalLearner a; a.setPlan(plan());
    for (int64_t t = rise.startUtc - 3600; t < rise.startUtc + 1800; t += 60) a.observe(0, t, rise, t >= rise.startUtc, int16_t(1850));
    ArrivalLearner::Rise other = rise; other.atUtc += 3600;    // the program moved the switch before it came
    a.observe(0, rise.startUtc + 1860, other, true, int16_t(1850));
    morning(a, 0, other, 1850, other.atUtc + 15 * 60, true, rise.startUtc + 1920);
    EXPECT_EQ(a.events(0), 1u) << "only the new rise is judged";
    EXPECT_EQ(*a.lastErrorMin(0), 15);
}

// From the switch on the planner reports the next rise (tomorrow's): the morning is still judged
// on its arrival; without any reading since the switch nothing is known, so nothing is learned.
TEST(ArrivalLearner, TheNextRiseAtTheSwitchDoesNotEndTheJudgement) {
    ArrivalLearner a; a.setPlan(plan());
    ArrivalLearner::Rise tomorrow = rise; tomorrow.atUtc += 86400; tomorrow.startUtc += 86400;
    for (int64_t t = rise.startUtc - 3600; t < rise.atUtc; t += 60) a.observe(0, t, rise, t >= rise.startUtc, int16_t(1850));
    for (int64_t t = rise.atUtc; t <= rise.atUtc + 3600; t += 60) {
        const int16_t temp = t < rise.atUtc + 20 * 60 ? 1850 : 2100;   // arrives 20 min after the switch
        a.observe(0, t, tomorrow, false, temp);
    }
    EXPECT_EQ(a.events(0), 1u);
    EXPECT_EQ(*a.lastErrorMin(0), 20);
    EXPECT_NEAR(a.lead(0).factor, 1.10f, 1e-5);
    // The sensor fell silent at the switch: no lesson, and tomorrow's rise is watched afterwards.
    for (int64_t t = tomorrow.startUtc - 3600; t < tomorrow.atUtc; t += 60) a.observe(0, t, tomorrow, t >= tomorrow.startUtc, int16_t(1850));
    ArrivalLearner::Rise after = tomorrow; after.atUtc += 86400; after.startUtc += 86400;
    for (int64_t t = tomorrow.atUtc; t <= tomorrow.atUtc + 4 * 3600; t += 60) a.observe(0, t, after, false, std::nullopt);
    EXPECT_EQ(a.events(0), 1u) << "unknown is no lesson";
    morning(a, 0, after, 1850, after.atUtc + 30 * 60, true, tomorrow.atUtc + 4 * 3600 + 60);
    EXPECT_EQ(a.events(0), 2u);
}

TEST(ArrivalLearner, APlanEditKeepsTheFactorById) {
    ArrivalLearner a; a.setPlan(plan({"woonkamer", "keuken"}));
    ArrivalLearner::Rise k = rise; k.toCentiC = 2000;
    morning(a, 1, k, 1800, k.atUtc + 20 * 60);
    morning(a, 1, {k.atUtc + 86400, k.startUtc + 86400, 2000}, 1800, k.atUtc + 86400 + 20 * 60);
    EXPECT_NEAR(a.lead(1).factor, 1.21f, 1e-4);
    a.setPlan(plan({"keuken", "woonkamer", "zolder"}));        // reordered, one added
    EXPECT_NEAR(a.lead(0).factor, 1.21f, 1e-4);
    EXPECT_FLOAT_EQ(a.lead(1).factor, 1.0f); EXPECT_FLOAT_EQ(a.lead(2).factor, 1.0f);
    a.setPlan(plan({"woonkamer"}));                            // removed: gone
    EXPECT_EQ(a.rooms(), 1u); EXPECT_FLOAT_EQ(a.lead(0).factor, 1.0f);
}
