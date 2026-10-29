#include "control/HeatingHistory.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <cstdlib>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
using heating::control::HeatingHistory;

namespace {
constexpr uint64_t period = HeatingHistory::periodMs;
size_t allocations = 0, releases = 0;
void* counting(size_t size) { ++allocations; return std::malloc(size); }
void counted(void* p) { ++releases; std::free(p); }
void* failing(size_t) { ++allocations; return nullptr; }

std::unique_ptr<HeatingHistory> ready() {
    auto h = std::make_unique<HeatingHistory>();
    EXPECT_TRUE(h->begin(std::malloc, std::free));
    return h;
}
void rooms(HeatingHistory& h, std::vector<const char*> ids) {
    h.syncRooms(ids.size(), [&](size_t i) { return ids[i]; });
}
HeatingHistory::Sample boiler(int16_t flowCentiC, bool burner) {
    HeatingHistory::Sample s; s.flowCentiC = flowCentiC; s.burnerOn = burner; return s;
}
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json parse(const HeatingHistory& h, uint64_t now) {
    std::ostringstream out; h.json(out, now);
    Json root(cJSON_Parse(out.str().c_str()), cJSON_Delete);
    EXPECT_TRUE(root) << out.str();
    return root;
}
const cJSON* item(const cJSON* o, const char* key) { return cJSON_GetObjectItemCaseSensitive(o, key); }
double number(const cJSON* o, const char* key) { return cJSON_GetNumberValue(item(o, key)); }
} // namespace

TEST(HeatingHistory, EmptyHistoryHasNoPointsAndNullSeries) {
    auto h = ready();
    EXPECT_EQ(h->points(), 0u);
    EXPECT_EQ(h->value(0, HeatingHistory::flow), HeatingHistory::none);
    auto root = parse(*h, 1000);
    EXPECT_TRUE(cJSON_IsTrue(item(root.get(), "available")));
    EXPECT_EQ(number(root.get(), "points"), 0);
    EXPECT_EQ(number(root.get(), "period_s"), 300);
    EXPECT_EQ(number(root.get(), "capacity"), 288);
    EXPECT_FALSE(item(root.get(), "oldest_start_ago_s"));
    for (const char* key : {"flow", "return", "burner_pct", "request", "thermostat_request"})
        EXPECT_TRUE(cJSON_IsNull(item(root.get(), key))) << key;
    EXPECT_EQ(cJSON_GetArraySize(item(root.get(), "rooms")), 0);
}

TEST(HeatingHistory, AllocationFailureLeavesTheChartUnavailableWithoutRetrying) {
    allocations = 0;
    HeatingHistory h;
    EXPECT_FALSE(h.begin(failing, counted));
    EXPECT_FALSE(h.begin(counting, counted)); // once at boot: no later heap pressure from retries
    EXPECT_EQ(allocations, 1u);
    EXPECT_FALSE(h.available());
    rooms(h, {"living"});
    h.sample(0, boiler(4500, true)); // ignored, never dereferences
    EXPECT_EQ(h.points(), 0u);
    auto root = parse(h, 5000);
    EXPECT_TRUE(cJSON_IsFalse(item(root.get(), "available")));
    EXPECT_STREQ(cJSON_GetStringValue(item(root.get(), "reason")), "memory_unavailable");
    EXPECT_EQ(number(root.get(), "points"), 0);
}

TEST(HeatingHistory, MemoryIsBoundedAllocatedOnceAndReleased) {
    allocations = releases = 0;
    {
        HeatingHistory h;
        ASSERT_TRUE(h.begin(counting, counted));
        EXPECT_TRUE(h.begin(counting, counted));
        for (uint64_t t = 0; t < 3 * 288 * period; t += 10000) h.sample(t, boiler(4000, false));
        EXPECT_EQ(h.points(), 289u); // 288 committed + the running average
    }
    EXPECT_EQ(allocations, 1u);
    EXPECT_EQ(releases, 1u);
    EXPECT_LE(HeatingHistory::bytes(), 13u * 1024u);
    EXPECT_LE(sizeof(HeatingHistory), 64u); // the object itself stays small on the internal heap
}

TEST(HeatingHistory, FiveMinuteAveragesAreQuantizedToTenthsAndRoundedSymmetrically) {
    auto h = ready();
    rooms(*h, {"living"});
    HeatingHistory::Sample s;
    s.temperatureCentiC[0] = 2014; s.targetCentiC[0] = 2000; s.flowCentiC = 4504; s.returnCentiC = -16;
    h->sample(0, s);
    s.temperatureCentiC[0] = 2017; s.flowCentiC = 4507; s.returnCentiC = -14;
    h->sample(10000, s);
    ASSERT_EQ(h->points(), 1u);
    const auto room = HeatingHistory::temperatureColumn(0);
    EXPECT_EQ(h->value(0, room), 202);      // 20.155 -> 20.2
    EXPECT_EQ(h->value(0, room + 1), 200);
    EXPECT_EQ(h->value(0, HeatingHistory::flow), 451); // 45.055 -> 45.1
    EXPECT_EQ(h->value(0, HeatingHistory::returnTemp), -2); // -0.15 -> -0.2 (away from zero)
    h->sample(period, HeatingHistory::Sample{});  // commits the first slot unchanged
    EXPECT_EQ(h->points(), 2u);
    EXPECT_EQ(h->value(0, room), 202);
    EXPECT_EQ(h->value(1, room), HeatingHistory::none);
}

TEST(HeatingHistory, BurnerIsTheShareOfSamplesOnAndRequestsAverageOnlyWhileHeating) {
    auto h = ready();
    HeatingHistory::Sample s;
    for (int i = 0; i < 4; ++i) {
        s.burnerOn = i == 0;
        s.requestFlowC = i < 2 ? uint8_t(40 + 5 * i) : uint8_t(0);
        s.thermostatFlowC = 0;
        h->sample(uint64_t(i) * 10000, s);
    }
    EXPECT_EQ(h->value(0, HeatingHistory::burner), 25);
    EXPECT_EQ(h->value(0, HeatingHistory::request), 425); // mean of 40 and 45 while heating
    EXPECT_EQ(h->value(0, HeatingHistory::thermostat), 0); // known, no heat requested
    EXPECT_EQ(h->value(0, HeatingHistory::flow), HeatingHistory::none);
}

TEST(HeatingHistory, RingWrapsKeepingTheNewest288SlotsInOrder) {
    auto h = ready();
    for (uint64_t slot = 0; slot < 300; ++slot) h->sample(slot * period, boiler(int16_t(slot * 10), false));
    ASSERT_EQ(h->points(), 289u);
    EXPECT_EQ(h->value(0, HeatingHistory::flow), 11);   // slot 11 is the oldest kept
    EXPECT_EQ(h->value(287, HeatingHistory::flow), 298);
    EXPECT_EQ(h->value(288, HeatingHistory::flow), 299); // running average
    EXPECT_EQ(h->value(289, HeatingHistory::flow), HeatingHistory::none);
    auto root = parse(*h, 299 * period + 60000);
    EXPECT_EQ(number(root.get(), "points"), 289);
    EXPECT_TRUE(cJSON_IsTrue(item(root.get(), "partial")));
    EXPECT_EQ(number(root.get(), "oldest_start_ago_s"), (288 * period + 60000) / 1000);
    const auto* flow = item(root.get(), "flow");
    ASSERT_EQ(cJSON_GetArraySize(flow), 289);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(flow, 0)), 11);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(flow, 288)), 299);
}

TEST(HeatingHistory, MissedSlotsBecomeGapsAndLongStallsAreBounded) {
    auto h = ready();
    h->sample(0, boiler(4000, true));
    h->sample(3 * period, boiler(5000, false));
    ASSERT_EQ(h->points(), 4u);
    EXPECT_EQ(h->value(0, HeatingHistory::flow), 400);
    EXPECT_EQ(h->value(1, HeatingHistory::flow), HeatingHistory::none);
    EXPECT_EQ(h->value(2, HeatingHistory::burner), HeatingHistory::none);
    EXPECT_EQ(h->value(3, HeatingHistory::flow), 500);
    h->sample(100000 * period, boiler(3000, false)); // days without a step: one pass of gaps at most
    EXPECT_EQ(h->points(), 289u);
    EXPECT_EQ(h->value(0, HeatingHistory::flow), HeatingHistory::none);
    EXPECT_EQ(h->value(288, HeatingHistory::flow), 300);
    auto root = parse(*h, 100000 * period + 400000); // the running slot ended without a new sample
    EXPECT_TRUE(cJSON_IsFalse(item(root.get(), "partial")));
    EXPECT_EQ(number(root.get(), "oldest_start_ago_s"), (288 * period + 400000) / 1000);
}

TEST(HeatingHistory, RoomColumnsFollowTheRoomIdAcrossPlanChanges) {
    auto h = ready();
    rooms(*h, {"living", "kitchen"});
    HeatingHistory::Sample s;
    s.temperatureCentiC[0] = 2000; s.temperatureCentiC[1] = 1800;
    h->sample(0, s);
    // Reordered, one removed, one added: living keeps its history, the new room starts empty.
    rooms(*h, {"bath", "living"});
    EXPECT_EQ(h->roomCount(), 2u);
    EXPECT_STREQ(h->roomId(0), "bath");
    EXPECT_STREQ(h->roomId(1), "living");
    HeatingHistory::Sample t;
    t.temperatureCentiC[0] = 2300; t.temperatureCentiC[1] = 2000;
    h->sample(period, t);
    auto root = parse(*h, period + 1000);
    const auto* list = item(root.get(), "rooms");
    ASSERT_EQ(cJSON_GetArraySize(list), 2);
    const auto* bath = cJSON_GetArrayItem(list, 0);
    const auto* living = cJSON_GetArrayItem(list, 1);
    EXPECT_STREQ(cJSON_GetStringValue(item(bath, "id")), "bath");
    const auto* bathT = item(bath, "temperature");
    ASSERT_EQ(cJSON_GetArraySize(bathT), 2); // kitchen's old value was cleared, not inherited
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetArrayItem(bathT, 0)));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(bathT, 1)), 230);
    const auto* livingT = item(living, "temperature");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(livingT, 0)), 200);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(livingT, 1)), 200);
    EXPECT_TRUE(cJSON_IsNull(item(living, "target")));
    rooms(*h, {});
    EXPECT_EQ(h->roomCount(), 0u);
    rooms(*h, {"kitchen"}); // a room that comes back later starts empty
    root = parse(*h, period + 2000);
    EXPECT_TRUE(cJSON_IsNull(item(cJSON_GetArrayItem(item(root.get(), "rooms"), 0), "temperature")));
}

TEST(HeatingHistory, FullHouseResponseStaysWellInsideTheResponseBuffer) {
    auto h = ready();
    std::vector<std::string> ids;
    for (int i = 0; i < 8; ++i) ids.push_back(std::string(32, char('a' + i)));
    h->syncRooms(ids.size(), [&](size_t i) { return ids[i].c_str(); });
    HeatingHistory::Sample s;
    for (size_t i = 0; i < 8; ++i) { s.temperatureCentiC[i] = -2345; s.targetCentiC[i] = 2150; }
    s.flowCentiC = 6543; s.returnCentiC = 5432; s.burnerOn = true; s.requestFlowC = 55; s.thermostatFlowC = 60;
    for (uint64_t t = 0; t < 290 * period; t += 10000) h->sample(t, s);
    std::ostringstream out; h->json(out, 290 * period);
    EXPECT_LT(out.str().size(), 48u * 1024u) << out.str().size(); // ResponseBuffer: 64 KB
    Json root(cJSON_Parse(out.str().c_str()), cJSON_Delete);
    ASSERT_TRUE(root);
    EXPECT_EQ(cJSON_GetArraySize(item(root.get(), "rooms")), 8);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(item(cJSON_GetArrayItem(item(root.get(), "rooms"), 7), "temperature"), 0)), -235);
}
