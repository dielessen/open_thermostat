#include "control/LearnedState.h"
#include "control/WarmupPlanner.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <map>
#include <memory>

namespace {
using heating::control::FlowDemand;
using heating::control::FlowLearner;
using heating::control::FlowPolicy;
using heating::control::FlowCompare;
using heating::control::LearnedState;
using heating::control::LearnedStore;
using heating::control::RoomDemand;
using heating::control::RoomPlan;
using heating::control::RoomSchedule;
using heating::control::ShadowComparison;
using heating::control::WarmupPlanner;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
const int64_t wednesday23 = int64_t(ShadowComparison::daysFromCivil(2026, 10, 28)) * 86400 + 22 * 3600;

RoomSchedule program() {
    RoomSchedule s;
    for (auto& d : s.days) { d.points[0] = {390, 2100}; d.points[1] = {1350, 1850}; d.count = 2; }
    return s;
}
RoomPlan plan() {
    RoomPlan p; p.rooms.resize(2);
    p.rooms[0].id = "woonkamer"; p.rooms[0].emitter = RoomPlan::Emitter::floor;
    p.rooms[1].id = "slaapkamer"; p.rooms[1].emitter = RoomPlan::Emitter::radiator;
    for (auto& r : p.rooms) { r.state = RoomDemand::State::active; r.schedule = program(); }
    return p;
}

// Two rooms of the learner's synthetic house (test_flow_learner.cpp): rate =
// a (flow - room) - b (room - outdoor), a floor slab and radiators, outdoor known.
struct House {
    struct Room { double a, b, capacity, coastHours, T = 20, coast = 0; };
    std::vector<Room> rooms{{0.035, 0.02, 10, 1.5}, {0.1, 0.05, 3, 0.2}};
    double outdoor = 5, gasKwh = 0;
    uint64_t now = 0;
    FlowLearner learner;
    House() { learner.setPlan(plan()); }
    void run(uint64_t ms, std::optional<double> flowC) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            const double dt = 10.0 / 3600;
            double heatKw = 0;
            for (auto& r : rooms) {
                const double emit = flowC ? r.a * (*flowC - r.T) : 0;
                if (flowC) r.coast = emit; else r.coast *= std::exp(-dt / r.coastHours);
                r.T += (flowC ? emit : r.coast) * dt - r.b * (r.T - outdoor) * dt;
                heatKw += r.capacity * emit;
            }
            FlowLearner::Boiler b;
            const double flow = flowC ? *flowC + ((now / (5 * minute)) % 2 ? 1 : -1) : rooms[0].T + 3;
            b.flowCentiC = int16_t(std::lround(flow * 100));
            b.returnCentiC = int16_t(std::lround((flow - 5) * 100));
            b.burnerOn = flowC.has_value();
            b.requestedFlowC = flowC ? uint8_t(*flowC) : uint8_t(0);
            b.hotWater = false;
            b.outdoorCentiC = int16_t(std::lround(outdoor * 100));
            b.modulationPct = uint8_t(std::clamp(std::lround(heatKw / FlowLearner::efficiency(flow - 5) / 22 * 100), 0L, 100L));
            gasKwh += *b.modulationPct / 100.0 * 22 * 1.1 * dt;
            FlowLearner::RoomInput in[2];
            for (size_t i = 0; i < 2; ++i) {
                in[i].temperatureCentiC = int16_t(std::lround(rooms[i].T * 10) * 10);
                in[i].setpointCentiC = 2100; in[i].source = 0;
            }
            learner.sample(now, b, in, 2);
        }
    }
    void learn() {
        for (int c = 0; c < 3; ++c)
            for (const double o : {0.0, 10.0})
                for (const double f : {32, 36, 40, 44, 48, 52}) {
                    outdoor = o;
                    for (auto& r : rooms) r.T = 20;
                    for (int k = 0; k < 4; ++k) { learner.gasMeter(gasKwh / 9.77, now); run(hour, f); }
                    learner.gasMeter(gasKwh / 9.77, now);
                    run(8 * hour, std::nullopt);
                }
        outdoor = 5;
    }
};
// The learned house plus a policy that compared a day and measured a night.
struct Learned {
    House h;
    FlowPolicy policy;
    RoomPlan p = plan();
    Learned() {
        h.learn();
        std::array<RoomDemand::Result, RoomPlan::maxRooms> rooms{};
        FlowPolicy::Inputs in;
        in.plan = &p; in.rooms = rooms.data(); in.outdoorCentiC = 500;
        double total = 1000;
        for (int64_t utc = wednesday23 - 26 * 3600; utc <= wednesday23 + 14 * 3600; utc += 60) {
            in.now = h.now += minute;
            if (utc % 3600 == 0) { total += 0.25; h.learner.gasMeter(total, in.now); }
            for (size_t i = 0; i < 2; ++i) {
                auto& r = rooms[i];
                r.status = RoomDemand::Status::ok; r.source = 0; r.usable = true;
                r.temperature = int16_t(1850 + (utc / 60) % 50); r.setpoint = 2100; r.errorCentiC = int16_t(2100 - *r.temperature);
            }
            in.utc = utc; in.rule = FlowDemand::Request{true, 40, FlowDemand::Reason::heating};
            policy.apply(in, h.learner);
        }
    }
};
// Everything the overview, the advice and the planners derive from what was learned
// ("advice" in json() uses the last sample's outdoor: compared below at fixed ones).
std::string derived(const FlowLearner& l, const FlowPolicy& p) {
    std::string out;
    const auto add = [&](cJSON* o) { char* t = cJSON_PrintUnformatted(o); out += t ? t : "<null>"; out += '\n'; cJSON_free(t); cJSON_Delete(o); };
    cJSON* root = l.json();
    for (cJSON* r = cJSON_GetObjectItem(root, "rooms")->child; r; r = r->next)
        for (const char* transient : {"last", "now", "segment_open", "advice"}) cJSON_DeleteItemFromObject(r, transient);
    for (const char* transient : {"status", "outdoor_c"}) cJSON_DeleteItemFromObject(root, transient);
    add(root);
    const auto rp = plan();
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{int16_t(1900), int16_t(1950)};
    add(WarmupPlanner::json(l, rp, wednesday23, temperatures.data(), int16_t(300)));
    for (size_t i = 0; i < l.rooms(); ++i)
        for (const int16_t outdoor : {-500, 500, 1200})
            for (const int16_t s : {0, 50, 100, 300}) {
                const auto a = l.advise(i, s, outdoor);
                out += std::to_string(a.flowC.value_or(0)) + a.reason + a.rule + std::to_string(a.warmupS.value_or(0)) + ' ';
            }
    cJSON* nights = cJSON_CreateObject();
    p.nights().json(nights);
    add(nights);
    const auto& c = p.curveLearner();
    out += std::to_string(c.windows()) + '/' + std::to_string(c.rejected()) + '/' + std::to_string(c.slope().value_or(-1)) + '\n';
    return out;
}

TEST(LearnedState, RoundTripGivesIdenticalLearnedValues) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    ASSERT_STREQ(a.h.learner.readiness(0), "ready");
    ASSERT_STREQ(a.h.learner.readiness(1), "ready");
    ASSERT_TRUE(a.h.learner.heatModel(0).capacityKwhPerK);
    ASSERT_GE(a.h.learner.gasIntervals(), 3);
    ASSERT_TRUE(a.policy.nights().last());
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy);
    const auto r0 = LearnedState::roomFrame(a.h.learner, 0), r1 = LearnedState::roomFrame(a.h.learner, 1);
    std::printf("[ learned ] global %zu B, floor %zu B, radiator %zu B\n", g.size(), r0.size(), r1.size());
    EXPECT_LE(g.size(), 300u);
    EXPECT_LE(r0.size(), LearnedState::maxFrame); EXPECT_LE(r1.size(), LearnedState::maxFrame);
    // A "reboot": a fresh learner with the same plan, then the frames.
    FlowLearner l; l.setPlan(plan());
    FlowPolicy p;
    EXPECT_NE(derived(l, p), derived(a.h.learner, a.policy));
    uint32_t done = 0;
    ASSERT_TRUE(LearnedState::restoreGlobal(g, l, p));
    ASSERT_TRUE(LearnedState::restoreRoom(r1, l, done));
    ASSERT_TRUE(LearnedState::restoreRoom(r0, l, done));
    EXPECT_EQ(done, 3u);
    EXPECT_EQ(derived(l, p), derived(a.h.learner, a.policy));
    EXPECT_STREQ(l.readiness(0), "ready");
    EXPECT_EQ(l.calibration(), a.h.learner.calibration());
    EXPECT_EQ(l.heatingPeriods(), a.h.learner.heatingPeriods());
    EXPECT_EQ(p.nights().nights(), a.policy.nights().nights());
    // The comparison of today and yesterday comes back as well.
    Json x(cJSON_CreateObject(), cJSON_Delete), y(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(a.policy.addSummary(x.get())); ASSERT_TRUE(p.addSummary(y.get()));
    const auto day = [](const cJSON* o) {
        auto f = cJSON_GetObjectItem(o, "flow");
        char* t = cJSON_PrintUnformatted(cJSON_GetObjectItem(f, "yesterday"));
        std::string s = t ? t : ""; cJSON_free(t); return s;
    };
    EXPECT_FALSE(day(x.get()).empty());
    EXPECT_EQ(day(x.get()), day(y.get()));
    // Byte for byte: what the restored state would store again.
    EXPECT_EQ(LearnedState::globalFrame(l, p), g);
    EXPECT_EQ(LearnedState::roomFrame(l, 0), r0);
    EXPECT_EQ(LearnedState::roomFrame(l, 1), r1);
    // A room that learned nothing needs no frame.
    FlowLearner empty; empty.setPlan(plan());
    EXPECT_TRUE(LearnedState::roomFrame(empty, 0).empty());
    EXPECT_TRUE(LearnedState::roomFrame(empty, 2).empty());
}

TEST(LearnedState, CorruptOldOrImplausibleFramesAreIgnoredWhole) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy), r = LearnedState::roomFrame(a.h.learner, 0);
    FlowLearner l; l.setPlan(plan());
    FlowPolicy p;
    const auto fresh = derived(l, p);
    uint32_t done = 0;
    for (size_t i = 0; i < r.size(); ++i)
        for (const uint8_t flip : {0x01, 0x80}) {
            auto bad = r; bad[i] = char(bad[i] ^ flip);
            EXPECT_FALSE(LearnedState::restoreRoom(bad, l, done)) << i;
        }
    for (size_t i = 0; i < g.size(); ++i) { auto bad = g; bad[i] = char(bad[i] ^ 0x10); EXPECT_FALSE(LearnedState::restoreGlobal(bad, l, p)) << i; }
    for (size_t n = 0; n < r.size(); ++n) EXPECT_FALSE(LearnedState::restoreRoom(r.substr(0, n), l, done));
    EXPECT_FALSE(LearnedState::restoreRoom(r + "x", l, done));
    EXPECT_FALSE(LearnedState::restoreRoom(g, l, done));    // another kind
    EXPECT_FALSE(LearnedState::restoreGlobal(r, l, p));
    // An older (or newer) version with a valid CRC.
    const auto resealed = [](std::string f) {
        const uint32_t c = LearnedState::crc(f.data(), f.size() - 4);
        std::memcpy(&f[f.size() - 4], &c, 4);
        return f;
    };
    auto old = r; old[0] = char(LearnedState::version + 1);
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(old), l, done));
    // Not finite, with a valid CRC: the first heat sum (after id, emitter and six counts).
    auto nan = r; const double q = std::nan("");
    std::memcpy(&nan[4 + 1 + 9 + 1 + 12], &q, sizeof q);
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(nan), l, done));
    EXPECT_TRUE(LearnedState::restoreRoom(resealed(r), l, done)); // the helper itself keeps a valid frame valid
    l.setPlan(RoomPlan{}); l.setPlan(plan());                      // forget it again (removed, then a new room)
    EXPECT_EQ(done, 1u);
    EXPECT_EQ(derived(l, p), fresh);
}

TEST(LearnedState, OnlyRoomsOfThePlanWithTheSameEmitterComeBack) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto r0 = LearnedState::roomFrame(a.h.learner, 0), r1 = LearnedState::roomFrame(a.h.learner, 1);
    // Reordered, one room renamed (removed), one added: by id.
    RoomPlan q = plan();
    std::swap(q.rooms[0], q.rooms[1]);
    q.rooms[0].id = "zolder";
    q.rooms.push_back(q.rooms[1]); q.rooms[2].id = "keuken";
    FlowLearner l; l.setPlan(q);
    uint32_t done = 0;
    EXPECT_FALSE(LearnedState::restoreRoom(r1, l, done));  // slaapkamer left the plan
    EXPECT_TRUE(LearnedState::restoreRoom(r0, l, done));   // woonkamer, now the second room
    EXPECT_FALSE(LearnedState::restoreRoom(r0, l, done));  // an older duplicate does not win
    EXPECT_EQ(done, 2u);
    EXPECT_STREQ(l.readiness(1), "ready");
    EXPECT_STREQ(l.readiness(0), "collecting");
    EXPECT_STREQ(l.readiness(2), "collecting");
    // Floor became radiator: that room starts fresh.
    RoomPlan e = plan(); e.rooms[0].emitter = RoomPlan::Emitter::radiator;
    FlowLearner m; m.setPlan(e);
    done = 0;
    EXPECT_FALSE(LearnedState::restoreRoom(r0, m, done));
    EXPECT_TRUE(LearnedState::restoreRoom(r1, m, done));
    EXPECT_STREQ(m.readiness(0), "collecting");
    EXPECT_EQ(m.segments(0), 0);
}

TEST(LearnedState, BundleForTheSettingsBackup) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto all = LearnedState::bundle(a.h.learner, a.policy, 4096);
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy);
    EXPECT_EQ(all, g + LearnedState::roomFrame(a.h.learner, 0) + LearnedState::roomFrame(a.h.learner, 1));
    EXPECT_TRUE(LearnedState::validBundle(all));
    FlowLearner l; l.setPlan(plan());
    FlowPolicy p;
    EXPECT_EQ(LearnedState::restoreBundle(all, l, p), 2);
    EXPECT_EQ(derived(l, p), derived(a.h.learner, a.policy));
    // A budget: the rooms that do not fit stay out, the global frame always comes.
    const auto r0 = LearnedState::roomFrame(a.h.learner, 0);
    EXPECT_EQ(LearnedState::bundle(a.h.learner, a.policy, all.size() - 1), g + r0);
    // One bad byte or a cut: nothing is applied.
    FlowLearner m; m.setPlan(plan());
    FlowPolicy n;
    for (size_t i : {size_t(0), g.size() + 7, all.size() - 1}) {
        auto bad = all; bad[i] = char(bad[i] ^ 0x04);
        EXPECT_FALSE(LearnedState::validBundle(bad)) << i;
        EXPECT_EQ(LearnedState::restoreBundle(bad, m, n), -1);
    }
    EXPECT_FALSE(LearnedState::validBundle(all.substr(0, all.size() - 3)));
    EXPECT_FALSE(LearnedState::validBundle(""));
    EXPECT_STREQ(m.readiness(0), "collecting");
    EXPECT_EQ(m.heatingPeriods(), 0);
}

// A restored "today" of days ago (the E32 was off) is not shown as yesterday.
TEST(LearnedState, AnOldRestoredDayIsNotYesterday) {
    ScopedTz tz(ScopedTz::amsterdam);
    const FlowDemand::Request heat{true, 40, FlowDemand::Reason::heating};
    const auto day = uint32_t(wednesday23 - 20 * 3600);  // Wednesday 03:00 local
    FlowCompare c;
    c.sample(0, day, heat, heat, std::nullopt, std::nullopt);
    c.sample(10 * second, day + 10, heat, heat, std::nullopt, std::nullopt);
    FlowCompare next = c;
    next.sample(20 * second, day + 86400, heat, heat, std::nullopt, std::nullopt);
    ASSERT_TRUE(next.yesterday());
    EXPECT_EQ(next.yesterday()->heatS, 10u);
    c.sample(20 * second, day + 3 * 86400, heat, heat, std::nullopt, std::nullopt);
    EXPECT_FALSE(c.yesterday());
    EXPECT_EQ(c.today().heatS, 10u);
}

// NVS on the E32: slots with a byte budget (the partition's free entries), failures on request.
struct Backend final : LearnedStore::Backend {
    std::map<size_t, std::string> slots;
    size_t writes = 0, erases = 0, capacity = 1 << 20;
    bool fail = false;
    bool read(size_t slot, std::string& out) override {
        const auto at = slots.find(slot);
        if (at == slots.end()) return false;
        out = at->second; return true;
    }
    bool write(size_t slot, std::string_view bytes) override {
        size_t used = bytes.size();
        for (const auto& [s, v] : slots) if (s != slot) used += v.size();
        if (fail || used > capacity) return false;   // NVS full: the old value stays
        ++writes; slots[slot] = std::string(bytes); return true;
    }
    bool erase(size_t slot) override { if (fail) return false; ++erases; slots.erase(slot); return true; }
};

TEST(LearnedStore, WritesAtMostEverySixHoursADayChangeAndBeforeARestart) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h;
    FlowPolicy p;
    Backend nvs;
    LearnedStore store;
    EXPECT_EQ(store.restore(nvs, h.learner, p, h.now), 0u);
    // Learning for 5 h 50 min (a sample every 10 s, from Wednesday 03:00 local): no write.
    uint32_t utc = uint32_t(wednesday23 - 20 * 3600);
    const auto steps = [&](uint64_t ms, std::optional<double> flow) {
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            h.run(10 * second, flow); utc += 10;
            if (store.due(h.now, utc)) store.save(nvs, h.learner, p, h.now);
        }
    };
    for (int k = 0; k < 5; ++k) { steps(60 * minute, 40); steps(10 * minute, std::nullopt); }
    ASSERT_GT(h.learner.segments(0), 0);
    EXPECT_EQ(nvs.writes, 0u);
    steps(20 * minute, 40);
    EXPECT_EQ(nvs.writes, 3u);                    // 6 h: global and both rooms, once
    EXPECT_EQ(nvs.slots[1], LearnedState::roomFrame(h.learner, 0));
    // Nothing learned since: the next 6 h writes nothing (the global frame did not change either).
    const auto before = nvs.writes;
    for (int k = 0; k < 6 * 360; ++k) { utc += 10; h.now += 10 * second; if (store.due(h.now, utc)) store.save(nvs, h.learner, p, h.now); }
    EXPECT_EQ(nvs.writes, before);
    // A local day change saves what changed, at once.
    steps(2 * hour, 44);
    const auto midnight = uint32_t(wednesday23 + 3600 - 30);    // Thursday 00:00 local, 30 s ahead
    utc = midnight - 300;
    const auto atDay = nvs.writes;
    steps(4 * minute, 44);
    EXPECT_EQ(nvs.writes, atDay);
    steps(2 * minute, 44);
    EXPECT_GT(nvs.writes, atDay);
    // Before a planned restart (releaseBoilerForRestart): the changed slots, whatever the clock.
    steps(30 * minute, std::nullopt);                          // the heating segment ends: learned
    const auto atRestart = nvs.writes;
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_GT(nvs.writes, atRestart);
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));          // unchanged: no second write
    // The reboot: a new learner and store read it back before the first step.
    FlowLearner l; l.setPlan(plan());
    FlowPolicy q;
    LearnedStore next;
    EXPECT_EQ(next.restore(nvs, l, q, 0), 2u);
    EXPECT_EQ(derived(l, q), derived(h.learner, p));
    const auto restored = nvs.writes;
    EXPECT_TRUE(next.save(nvs, l, q, 0));
    EXPECT_EQ(nvs.writes, restored);                            // restored = stored: nothing to write
}

TEST(LearnedStore, FullNvsCorruptEntriesAndPlanChangesAreHandled) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h; h.learn();
    FlowPolicy p;
    Backend nvs;
    nvs.slots[0] = "garbage";                                   // e.g. an interrupted older format
    nvs.slots[5] = std::string(40, '\xff');
    LearnedStore store;
    EXPECT_EQ(store.restore(nvs, h.learner, p, h.now), 0u);    // ignored, nothing half loaded
    EXPECT_STREQ(h.learner.readiness(0), "ready");             // RAM untouched
    // NVS full: false (the caller logs it), RAM keeps everything, retried at the next save.
    nvs.capacity = 100;
    EXPECT_FALSE(store.save(nvs, h.learner, p, h.now));
    EXPECT_STREQ(h.learner.readiness(0), "ready");
    nvs.fail = true;
    EXPECT_FALSE(store.save(nvs, h.learner, p, h.now));
    nvs.fail = false; nvs.capacity = 1 << 20;
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_FALSE(nvs.slots.count(5));                           // a slot without a plan room is erased
    EXPECT_EQ(nvs.slots[0], LearnedState::globalFrame(h.learner, p));
    ASSERT_EQ(nvs.slots.size(), 3u);
    // A room removed from the plan: its slot goes at the next save; the other keeps its model.
    RoomPlan one = plan(); one.rooms.erase(one.rooms.begin());
    h.learner.setPlan(one);
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(nvs.slots.size(), 2u);
    EXPECT_EQ(nvs.slots[1], LearnedState::roomFrame(h.learner, 0));
    FlowLearner l; l.setPlan(plan());
    FlowPolicy q;
    LearnedStore next;
    EXPECT_EQ(next.restore(nvs, l, q, 0), 1u);
    EXPECT_STREQ(l.readiness(0), "collecting");                 // woonkamer was removed
    EXPECT_STREQ(l.readiness(1), "ready");
    // The emitter changed after the save: the stored model is not used for it.
    RoomPlan e = plan(); e.rooms[1].emitter = RoomPlan::Emitter::floor;
    FlowLearner m; m.setPlan(e);
    LearnedStore third;
    EXPECT_EQ(third.restore(nvs, m, q, 0), 0u);
    EXPECT_STREQ(m.readiness(1), "collecting");
}

// rc.2: the global frame is version 2 with the boiler's learned minimum flow at its end; a
// version 1 global frame (firmware before rc.2) is still read, with the minimum unlearned.
TEST(LearnedState, TheBoilerMinimumIsKeptAndAnOldGlobalFrameStillReads) {
    FlowLearner l; l.setPlan(plan());
    FlowLearner::Boiler b;
    b.flowCentiC = 3800; b.burnerOn = false; b.hotWater = false; b.modulationPct = 0;
    b.requestedFlowC = 34; b.ownRequest = true; b.productId = 0x7b;
    const FlowLearner::RoomInput in[2] = {{int16_t(2000), int16_t(2100), 0}, {int16_t(2100), int16_t(2100), 0}};
    uint64_t now = 0;
    for (int k = 0; k < 6 * 16; ++k) { now += 10 * second; l.sample(now, b, in, 2); }
    ASSERT_EQ(l.effectiveMinimumC(70), 40);
    const auto g = LearnedState::globalFrame(l, FlowPolicy{});
    EXPECT_EQ(uint8_t(g[0]), LearnedState::globalVersion);
    EXPECT_EQ(uint8_t(LearnedState::roomFrame(Learned().h.learner, 0)[0]), LearnedState::version); // rooms stay version 1
    FlowLearner back; back.setPlan(plan());
    FlowPolicy p;
    ASSERT_TRUE(LearnedState::restoreGlobal(g, back, p));
    EXPECT_EQ(back.effectiveMinimumC(70), 40);
    EXPECT_EQ(back.boilerMinimum().raises(), 1);
    EXPECT_EQ(back.heatingPeriods(), l.heatingPeriods());
    // The same frame as version 1 wrote it: without the last 8 payload bytes.
    const auto seal = [](std::string f, uint8_t v) {
        f[0] = char(v);
        const size_t n = f.size() - 8; f[2] = char(n & 0xFF); f[3] = char(n >> 8);
        const uint32_t c = LearnedState::crc(f.data(), f.size() - 4);
        std::memcpy(&f[f.size() - 4], &c, 4);
        return f;
    };
    const auto v1 = seal(g.substr(0, g.size() - 12) + g.substr(g.size() - 4), 1);
    ASSERT_TRUE(LearnedState::restoreGlobal(v1, back, p));
    EXPECT_EQ(back.boilerMinimum().learnedC(), 0);  // an old frame has no minimum: it starts over
    EXPECT_EQ(back.effectiveMinimumC(70), 30);
    EXPECT_EQ(back.heatingPeriods(), l.heatingPeriods());
    EXPECT_TRUE(LearnedState::validBundle(v1));
    // Version 2 without the minimum, version 3, or a minimum it can never learn: refused whole.
    EXPECT_FALSE(LearnedState::restoreGlobal(seal(v1, 2), back, p));
    EXPECT_FALSE(LearnedState::restoreGlobal(seal(g, 3), back, p));
    auto high = g; high[g.size() - 12] = char(90);  // learnedC_, the first of the 8 bytes
    EXPECT_FALSE(LearnedState::restoreGlobal(seal(high, 2), back, p));
    EXPECT_TRUE(LearnedState::restoreGlobal(seal(g, 2), back, p));
    EXPECT_EQ(back.effectiveMinimumC(70), 40);
}

// Fuzz findings (soak run on 043e228): an edited settings backup with CRC-valid room frames
// whose bins or heat sums FlowLearner::finish() can never produce. Before: accepted, then
// NaN advice (a NaN cast to uint8_t), NaN/inf in the JSON and an infinite capacity.
std::string fromHex(const std::string& hex) {
    std::string out;
    for (size_t i = 0; i + 1 < hex.size(); i += 2) out += char(std::stoi(hex.substr(i, 2), nullptr, 16));
    return out;
}
// The fuzzer's reseal: every frame gets the current version and a valid CRC.
std::string reseal(std::string b) {
    for (size_t at = 0; b.size() - at >= 8;) {
        const size_t n = (uint8_t(b[at + 2]) | size_t(uint8_t(b[at + 3])) << 8) + 8;
        if (n > b.size() - at) break;
        b[at] = char(LearnedState::version);
        const uint32_t c = LearnedState::crc(&b[at], n - 4);
        std::memcpy(&b[at + n - 4], &c, 4);
        at += n;
    }
    return b;
}
template <class T> void put(std::string& f, T v) { f.append(reinterpret_cast<const char*>(&v), sizeof v); }
// Everything derived from a restored learner stays finite and within the plan.
void expectFinite(const FlowLearner& l) {
    const auto text = [](cJSON* o) { char* t = cJSON_PrintUnformatted(o); std::string s = t ? t : ""; cJSON_free(t); cJSON_Delete(o); return s; };
    const auto rp = plan();
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{int16_t(1900), int16_t(1950)};
    for (const auto& s : {text(l.json()), text(WarmupPlanner::json(l, rp, wednesday23, temperatures.data(), int16_t(300)))}) {
        EXPECT_EQ(s.find("nan"), std::string::npos) << s;
        EXPECT_EQ(s.find("inf"), std::string::npos) << s;
        Json back(cJSON_Parse(s.c_str()), cJSON_Delete);
        EXPECT_TRUE(back);
    }
    for (size_t i = 0; i < l.rooms(); ++i) {
        const auto m = l.heatModel(i);
        if (m.capacityKwhPerK) { EXPECT_GT(*m.capacityKwhPerK, 0); EXPECT_LE(*m.capacityKwhPerK, 1000); }
        for (const int16_t o : {-2000, -500, 500, 1200})
            for (const int16_t s : {0, 50, 100, 300, 2000}) {
                const auto a = l.advise(i, s, o);
                if (a.flowC) { EXPECT_GE(*a.flowC, rp.minimumFlowC); EXPECT_LE(*a.flowC, rp.maximumFlowC); }
            }
    }
}

TEST(LearnedState, ImplausibleBinsAndSumsFromAnEditedBackupAreRefused) {
    ScopedTz tz(ScopedTz::amsterdam);
    // repro_learned_nan: a normal bin and one with a subnormal weight (its flow and rate overflow).
    std::string f{char(LearnedState::version), LearnedState::roomKind, 0, 0};
    f += char(9); f += "woonkamer"; f += char(0);
    for (const uint16_t v : {6, 3, 3, 0, 0, 0}) put(f, v);
    for (int i = 0; i < 9; ++i) put(f, 0.0);
    put(f, uint32_t(1u << 6 | 1u << 7));
    const auto bin = [&](float w, float wf, float wr) {
        f += char(3); f += char(2); f += char(0); put(f, uint16_t(3));
        for (const float x : {w, wf, wr, 0.1f}) put(f, x);
    };
    bin(1.0f, 32.0f, 0.3f);
    bin(1e-40f, 34.0f, 0.5f);
    const auto n = uint16_t(f.size() - 4); f[2] = char(n & 0xFF); f[3] = char(n >> 8);
    put(f, LearnedState::crc(f.data(), f.size()));
    EXPECT_FALSE(LearnedState::validBundle(f));
    FlowLearner l; l.setPlan(plan());
    FlowPolicy p;
    EXPECT_EQ(LearnedState::restoreBundle(f, l, p), -1);
    expectFinite(l);
    // The fuzzer's minimised inputs (selector byte 0, then the bundle): a NaN minimum and an infinite capacity.
    for (const char* hex : {
             "000152590109776f6f6e6b616d65720048002400240000002300486910000066665c4e4082450bb9866d71409001d49ec2c1ce4009111111111d5640"
             "07f572a58a47824016bfce71eda2d440d3af95a0e9b560408d3d0b92a7249a40283d6e1d7d20dc40405501000c060c1f00bcbbb741bcbb3744046afa"
             "40c4965b40bcbbb741abaae542ab8a8f44b54b6e42046afa400c060c2000bcbbb74135b34e440e366841f3ce2041bcbbb741abaae542ab8a8f44663a"
             "bb420e3668410cff4b0732c6710000abaa65447625aa41ecbca541bcbb666666665c4e4082450bb9866d71409001d49ec2c1ce4009111111111d5640"
             "07f572a58a47824016bfce71cf89d24017faa0d02e952143f775e0410c060c2300bcbbb741cecc894475570b42a81d5942bcbbb741abaae542ab8a8f"
             "44087f434375570b420c060c2400bcbbb74188489544007826429d479a42bcbbb741abaae5428b8f448aab6e654300782642ba3270be",
             "0001525a010a736c6161706b616d657201480224002400000047004800489ff4499f02524017d143c945be8c40d27e42b43200d24009111111111d56"
             "40cd2d2bd1546d656173aa2ac5eda2d440d3af95a0e9b560408d3d0b92a7249a40283d6e1d7d20dc40405501000c060c1f00bcbbb741bcbb3744046a"
             "fa40c4965b40bcbbb741abaae542ab8a8f44b54b6e42046afa400c060c2000bcbbb74135b34e440e366841f3ce2041bcbbb741abaae542ab8a8f4466"
             "3abb420e3668410c060c2100bcbbb741abaa65447625aa41ecbca541bcbbb741abaae542ab8a8f44bb21ff427625aa410c060c2200bcbbb74122a27c"
             "44f775e041e7ee0d42bcbbb741abaae542ab8a8f44d1952143000077b5d4ff18c500bcbbb741cecc894075570b42a8e39d42bcbbb741abaae542ab8a"
             "8f44087f434375570b420c060c2400bcbbb74188489544007826429d479a42bcbbb741abaae542ab8a8f448b6e654300782642ba3270be"}) {
        const auto b = reseal(fromHex(hex).substr(1));
        FlowLearner m; m.setPlan(plan());
        FlowPolicy q;
        const int rooms = LearnedState::restoreBundle(b, m, q);
        EXPECT_EQ(rooms >= 0, LearnedState::validBundle(b));
        expectFinite(m);
    }
    // The JSON helper never writes a non-finite number.
    Json o(cJSON_CreateObject(), cJSON_Delete);
    FlowLearner::number(o.get(), "x", std::nanf(""), 10);
    FlowLearner::number(o.get(), "y", HUGE_VALF, 10);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(o.get(), "x")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(o.get(), "y")));
}
}
