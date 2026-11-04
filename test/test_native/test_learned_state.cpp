#include "control/LearnedState.h"
#include "control/AutoTuner.h"
#include "control/OptionalRecordPriority.h"
#include "control/WarmupPlanner.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <initializer_list>
#include <map>
#include <tuple>
#include <memory>
#include <random>
#include <vector>

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

template <class T> void put(std::string& f, T v) { f.append(reinterpret_cast<const char*>(&v), sizeof v); }
// The used bins of a version 1 room frame (its documented layout): counts and the nine sums.
struct BinView { uint8_t segments = 0, periods = 0, outdoorSegments = 0; std::array<float, 9> v{}; };
std::vector<BinView> bins(const std::string& f) {
    std::vector<BinView> out;
    size_t at = 4;
    at += 1 + uint8_t(f[at]) + 1 + 12 + 72;
    uint32_t used; std::memcpy(&used, &f[at], 4); at += 4;
    for (size_t i = 0; i < FlowLearner::binCount; ++i) {
        if (!(used >> i & 1)) continue;
        BinView b;
        b.segments = uint8_t(f[at]); b.periods = uint8_t(f[at + 1]); b.outdoorSegments = uint8_t(f[at + 2]); at += 5;
        const size_t n = b.outdoorSegments ? 9 : 4;
        std::memcpy(b.v.data(), &f[at], 4 * n); at += 4 * n;
        out.push_back(b);
    }
    return out;
}
// After a version 2 round trip: the same text, each number within the fixed point's effect
// (the JSON's 0.01 rounding, 0.5 % of a warm-up time or a sum).
void expectSameLearned(const std::string& a, const std::string& b) {
    const auto split = [](const std::string& s) {
        std::vector<std::string> text;
        std::vector<double> numbers;
        std::string t;
        for (size_t i = 0; i < s.size();) {
            const bool digit = std::isdigit(static_cast<unsigned char>(s[i]))
                || (s[i] == '-' && i + 1 < s.size() && std::isdigit(static_cast<unsigned char>(s[i + 1])));
            if (digit && (i == 0 || s[i - 1] != '_')) {
                char* end = nullptr;
                numbers.push_back(std::strtod(s.c_str() + i, &end));
                text.push_back(t); t.clear();
                i = size_t(end - s.c_str());
            } else t += s[i++];
        }
        text.push_back(t);
        return std::make_pair(text, numbers);
    };
    const auto [ta, na] = split(a);
    const auto [tb, nb] = split(b);
    ASSERT_EQ(ta, tb);
    ASSERT_EQ(na.size(), nb.size());
    for (size_t i = 0; i < na.size(); ++i)
        EXPECT_NEAR(na[i], nb[i], 0.011 + 0.005 * std::max(std::fabs(na[i]), std::fabs(nb[i]))) << "number " << i << " after: " << ta[i].substr(ta[i].size() > 60 ? ta[i].size() - 60 : 0);
}

// Version 2 room frames (the default): about half the bytes, the same learned values.
TEST(LearnedState, CompactRoomFramesKeepTheLearnedValues) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy);
    const auto r0 = LearnedState::roomFrame(a.h.learner, 0), r1 = LearnedState::roomFrame(a.h.learner, 1);
    const auto v0 = LearnedState::roomFrame(a.h.learner, 0, LearnedState::version), v1 = LearnedState::roomFrame(a.h.learner, 1, LearnedState::version);
    ASSERT_EQ(uint8_t(r0[0]), LearnedState::roomVersion);
    ASSERT_EQ(uint8_t(r1[0]), LearnedState::roomVersion);
    std::printf("[ learned ] version 2: floor %zu B (version 1: %zu), radiator %zu B (%zu)\n", r0.size(), v0.size(), r1.size(), v1.size());
    EXPECT_LE(r0.size() * 100, v0.size() * 60);
    EXPECT_LE(r1.size() * 100, v1.size() * 60);
    // 8 rooms like these with the globals: one NVS blob well under 2 KB.
    EXPECT_LE(g.size() + 4 * (r0.size() + r1.size()), 2048u);
    FlowLearner l; l.setPlan(plan());
    FlowPolicy p;
    uint32_t done = 0;
    ASSERT_TRUE(LearnedState::restoreGlobal(g, l, p));
    ASSERT_TRUE(LearnedState::restoreRoom(r1, l, done));
    ASSERT_TRUE(LearnedState::restoreRoom(r0, l, done));
    EXPECT_STREQ(l.readiness(0), "ready");
    EXPECT_STREQ(l.readiness(1), "ready");
    EXPECT_EQ(l.segments(0), a.h.learner.segments(0));
    expectSameLearned(derived(l, p), derived(a.h.learner, a.policy));
    // The restored state stores the same bytes again (the fixed point is stable).
    EXPECT_EQ(LearnedState::roomFrame(l, 0), r0);
    EXPECT_EQ(LearnedState::roomFrame(l, 1), r1);
    // Each bin's means within the fixed point's half step (read from the lossless version 1 form).
    for (size_t i = 0; i < 2; ++i) {
        const auto x = bins(LearnedState::roomFrame(a.h.learner, i, LearnedState::version));
        const auto y = bins(LearnedState::roomFrame(l, i, LearnedState::version));
        ASSERT_EQ(x.size(), y.size());
        ASSERT_GE(x.size(), 4u);
        for (size_t k = 0; k < x.size(); ++k) {
            const auto& b = x[k];
            const auto& c = y[k];
            ASSERT_EQ(b.segments, c.segments);
            ASSERT_EQ(b.outdoorSegments, c.outdoorSegments);
            EXPECT_NEAR(c.v[0], b.v[0], 0.5 / 600 + 1e-6);                         // weight, h
            EXPECT_NEAR(c.v[1] / c.v[0], b.v[1] / b.v[0], 0.005 + 1e-4);            // mean flow
            EXPECT_NEAR(c.v[2] / c.v[0], b.v[2] / b.v[0], 0.0005 + 1e-5);           // mean rate
            if (b.outdoorSegments) {
                EXPECT_EQ(c.v[4], c.v[0]) << "every segment had the outdoor: its own weight";
                EXPECT_NEAR(c.v[5] / c.v[4], b.v[5] / b.v[4], 0.005 + 1e-4);        // mean outdoor
                EXPECT_NEAR(c.v[8] / c.v[4], b.v[8] / b.v[4], 0.0005 + 1e-5);       // mean rate there
            }
        }
    }
}

// A plausible value outside the fixed point (an outdoor x rate covariance of 50 degC^2/h; the
// int16 of 0.001 ends at 32.767): that room is written as version 1, the lossless form.
TEST(LearnedState, ARoomOutsideTheFixedPointKeepsVersionOne) {
    std::string f{char(LearnedState::version), LearnedState::roomKind, 0, 0};
    f += char(9); f += "woonkamer"; f += char(0);
    for (const uint16_t v : {3, 2, 2, 0, 0, 0}) put(f, v);
    for (int i = 0; i < 9; ++i) put(f, 0.0);
    put(f, uint32_t(1u << 10));
    f += char(3); f += char(2); f += char(3); put(f, uint16_t(2));
    for (const float x : {1.0f, 40.0f, 0.0f, 100.0f, 1.0f, 0.0f, 100.0f, 50.0f, 0.0f}) put(f, x);
    const auto n = uint16_t(f.size() - 4); f[2] = char(n & 0xFF); f[3] = char(n >> 8);
    put(f, LearnedState::crc(f.data(), f.size()));
    FlowLearner l; l.setPlan(plan());
    uint32_t done = 0;
    ASSERT_TRUE(LearnedState::restoreRoom(f, l, done));
    EXPECT_EQ(LearnedState::roomFrame(l, 0), f);
    EXPECT_EQ(uint8_t(LearnedState::roomFrame(l, 0)[0]), LearnedState::version);
}

// Version 1 room frames (lossless, still read; written when a value does not fit version 2).
TEST(LearnedState, RoundTripGivesIdenticalLearnedValues) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    ASSERT_STREQ(a.h.learner.readiness(0), "ready");
    ASSERT_STREQ(a.h.learner.readiness(1), "ready");
    ASSERT_TRUE(a.h.learner.heatModel(0).capacityKwhPerK);
    ASSERT_GE(a.h.learner.gasIntervals(), 3);
    ASSERT_TRUE(a.policy.nights().last());
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy);
    const auto r0 = LearnedState::roomFrame(a.h.learner, 0, LearnedState::version), r1 = LearnedState::roomFrame(a.h.learner, 1, LearnedState::version);
    std::printf("[ learned ] version 1: global %zu B, floor %zu B, radiator %zu B\n", g.size(), r0.size(), r1.size());
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
    EXPECT_EQ(LearnedState::roomFrame(l, 0, LearnedState::version), r0);
    EXPECT_EQ(LearnedState::roomFrame(l, 1, LearnedState::version), r1);
    // A room that learned nothing needs no frame.
    FlowLearner empty; empty.setPlan(plan());
    EXPECT_TRUE(LearnedState::roomFrame(empty, 0).empty());
    EXPECT_TRUE(LearnedState::roomFrame(empty, 2).empty());
}

TEST(LearnedState, CorruptOldOrImplausibleFramesAreIgnoredWhole) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto g = LearnedState::globalFrame(a.h.learner, a.policy);
    for (const uint8_t v : {LearnedState::version, LearnedState::roomVersion}) {
    const auto r = LearnedState::roomFrame(a.h.learner, 0, v);
    ASSERT_EQ(uint8_t(r[0]), v);
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
    auto old = r; old[0] = char(LearnedState::roomVersion + 1);
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(old), l, done));
    old[0] = char(0);
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(old), l, done));
    // The other version's header on this payload: refused (the lengths do not match).
    old[0] = char(v == LearnedState::version ? LearnedState::roomVersion : LearnedState::version);
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(old), l, done));
    // Not finite, with a valid CRC: the first heat sum (after id, emitter and six counts).
    auto nan = r;
    if (v == LearnedState::version) { const double q = std::nan(""); std::memcpy(&nan[4 + 1 + 9 + 1 + 12], &q, sizeof q); }
    else { const float q = std::nanf(""); std::memcpy(&nan[4 + 1 + 9 + 1 + 12], &q, sizeof q); }
    EXPECT_FALSE(LearnedState::restoreRoom(resealed(nan), l, done));
    EXPECT_TRUE(LearnedState::restoreRoom(resealed(r), l, done)); // the helper itself keeps a valid frame valid
    l.setPlan(RoomPlan{}); l.setPlan(plan());                      // forget it again (removed, then a new room)
    EXPECT_EQ(done, 1u);
    EXPECT_EQ(derived(l, p), fresh);
    }
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
    expectSameLearned(derived(l, p), derived(a.h.learner, a.policy));
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

// NVS on the E32: the packed record's parts with a byte budget (the partition's free
// entries), failures on request, and the per-frame keys of earlier rc.2 builds.
struct Backend final : LearnedStore::Backend {
    std::map<size_t, std::string> slots, legacy;
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
        for (const auto& [s, v] : legacy) used += v.size();
        if (fail || used > capacity) return false;   // NVS short of room: the old value stays
        ++writes; slots[slot] = std::string(bytes); return true;
    }
    bool erase(size_t slot) override { if (fail) return false; ++erases; slots.erase(slot); return true; }
    bool readLegacy(size_t slot, std::string& out) override {
        const auto at = legacy.find(slot);
        if (at == legacy.end()) return false;
        out = at->second; return true;
    }
    bool eraseLegacy(size_t slot) override { if (fail) return false; legacy.erase(slot); return true; }
};
std::string packed(const FlowLearner& l, const FlowPolicy& p) {
    std::string out = LearnedState::globalFrame(l, p);
    for (size_t i = 0; i < l.rooms(); ++i) out += LearnedState::roomFrame(l, i);
    return out;
}

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
    EXPECT_EQ(nvs.writes, 1u);                    // 6 h: one packed part with the global frame and both rooms
    EXPECT_EQ(nvs.slots[0], packed(h.learner, p));
    EXPECT_EQ(store.rooms(), 2u);
    EXPECT_EQ(store.storedRooms(), 2u);
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
    // Before a planned restart (releaseBoilerForRestart): the changed part, whatever the clock.
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
    expectSameLearned(derived(l, q), derived(h.learner, p));
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
    nvs.slots[1] = std::string(40, '\xff');
    LearnedStore store;
    EXPECT_EQ(store.restore(nvs, h.learner, p, h.now), 0u);    // ignored, nothing half loaded
    EXPECT_STREQ(h.learner.readiness(0), "ready");             // RAM untouched
    // NVS full: false (the caller logs it), RAM keeps everything, retried at the next save.
    nvs.capacity = 100;
    EXPECT_FALSE(store.save(nvs, h.learner, p, h.now));
    EXPECT_STREQ(h.learner.readiness(0), "ready");
    EXPECT_EQ(store.storedRooms(), 0u);
    EXPECT_GT(store.pendingEntries(), 0u);
    nvs.fail = true;
    EXPECT_FALSE(store.save(nvs, h.learner, p, h.now));
    nvs.fail = false; nvs.capacity = 1 << 20;
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(store.pendingEntries(), 0u);
    EXPECT_FALSE(nvs.slots.count(1));                           // a part no longer needed is erased
    EXPECT_EQ(nvs.slots[0], packed(h.learner, p));
    ASSERT_EQ(nvs.slots.size(), 1u);
    // A room removed from the plan: its frame goes at the next save; the other keeps its model.
    RoomPlan one = plan(); one.rooms.erase(one.rooms.begin());
    h.learner.setPlan(one);
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(nvs.slots[0], LearnedState::globalFrame(h.learner, p) + LearnedState::roomFrame(h.learner, 0));
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
    EXPECT_EQ(uint8_t(LearnedState::roomFrame(Learned().h.learner, 0)[0]), LearnedState::roomVersion); // rooms: version 2 (no released firmware reads them)
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

// Version 2 frames from an edited backup or a damaged NVS part: random bytes with every
// frame's CRC made valid again (its version byte kept), so they reach the fixed-point reader.
// Nothing out of bounds (ASan/UBSan), nothing non-finite or outside the plan is loaded.
TEST(LearnedState, MutatedCompactFramesNeverLoadNonFiniteState) {
    ScopedTz tz(ScopedTz::amsterdam);
    Learned a;
    const auto bundle = LearnedState::bundle(a.h.learner, a.policy, LearnedState::backupBytes);
    ASSERT_EQ(uint8_t(bundle[LearnedState::globalFrame(a.h.learner, a.policy).size()]), LearnedState::roomVersion);
    const auto resealKept = [](std::string b) {
        for (size_t at = 0; b.size() - at >= 8;) {
            const size_t n = (uint8_t(b[at + 2]) | size_t(uint8_t(b[at + 3])) << 8) + 8;
            if (n > b.size() - at) break;
            const uint32_t c = LearnedState::crc(&b[at], n - 4);
            std::memcpy(&b[at + n - 4], &c, 4);
            at += n;
        }
        return b;
    };
    std::mt19937 rng(20261102);
    size_t accepted = 0;
    for (int k = 0; k < 1500; ++k) {
        auto b = bundle;
        for (int j = 1 + int(rng() % 4); j > 0; --j) {
            const size_t at = rng() % b.size();
            b[at] = char(rng() % 3 ? rng() : b[at] ^ (1u << (rng() % 8)));
        }
        b = resealKept(b);
        FlowLearner m; m.setPlan(plan());
        FlowPolicy q;
        const int rooms = LearnedState::restoreBundle(b, m, q);
        EXPECT_EQ(rooms >= 0, LearnedState::validBundle(b));
        accepted += rooms > 0;
        uint32_t done = 0;
        bool global = false;
        FlowLearner n; n.setPlan(plan());
        LearnedState::restoreFrames(b, n, q, done, global); // the NVS path: frame by frame
        if (k % 10 == 0) { expectFinite(m); expectFinite(n); }
    }
    std::printf("[ learned ] %zu of 1500 mutated bundles accepted (plausible), none non-finite\n", accepted);
    EXPECT_GT(accepted, 0u);
}
}

// Review of rc.2 (finding 3): a plan or Bluetooth save may erase the learned parts to make
// room (NvsOptionalRecords.h). The store then forgets what the backend holds: its next save
// writes every part again where it fits, instead of skipping the unchanged ones.
TEST(LearnedStore, AfterThePartsMadeRoomTheNextSaveWritesThemAgain) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h; h.learn();
    FlowPolicy p;
    Backend nvs;
    LearnedStore store;
    ASSERT_TRUE(store.save(nvs, h.learner, p, h.now));
    const auto stored = nvs.slots;
    ASSERT_EQ(stored.size(), 1u);
    nvs.slots.clear();                                       // erased behind the store's back
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_TRUE(nvs.slots.empty()) << "unchanged parts are skipped";
    store.forgetStored();
    const auto g = LearnedState::globalFrame(h.learner, p), r0 = LearnedState::roomFrame(h.learner, 0);
    nvs.capacity = g.size() + r0.size();                     // room for the globals and the first room
    EXPECT_FALSE(store.save(nvs, h.learner, p, h.now));      // the second room: retried at the next save
    EXPECT_EQ(nvs.slots.at(0), g + r0) << "the later rooms yield first";
    EXPECT_EQ(store.storedRooms(), 1u);
    nvs.capacity = 1 << 20;
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(nvs.slots, stored);
    const auto writes = nvs.writes;
    EXPECT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(nvs.writes, writes) << "known again: no rewrite";
}

// A part's identity must change with any frame in it: the CRC of the whole part would not
// (after a frame that ends in its own CRC the CRC register always holds the same residue).
TEST(LearnedStore, AChangeInAnEarlierFrameIsWrittenToo) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h; h.learn();
    FlowPolicy p;
    Backend nvs;
    LearnedStore store;
    ASSERT_TRUE(store.save(nvs, h.learner, p, h.now));
    const auto before = nvs.slots.at(0);
    // Only the global frame (the first) changes: one more gas interval.
    h.learner.gasMeter(1e6, h.now + hour);
    ASSERT_NE(LearnedState::globalFrame(h.learner, p), before.substr(0, LearnedState::globalFrame(h.learner, p).size()));
    ASSERT_TRUE(store.save(nvs, h.learner, p, h.now));
    EXPECT_EQ(nvs.slots.at(0), packed(h.learner, p));
}

// Earlier rc.2 builds kept one key per frame: read once, then the packed record replaces them.
TEST(LearnedStore, ThePerFrameKeysOfEarlierBuildsAreReadAndThenErased) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h; h.learn();
    FlowPolicy p;
    Backend nvs;
    nvs.legacy[0] = LearnedState::globalFrame(h.learner, p);
    nvs.legacy[1] = LearnedState::roomFrame(h.learner, 0, LearnedState::version);
    nvs.legacy[2] = LearnedState::roomFrame(h.learner, 1, LearnedState::version);
    FlowLearner l; l.setPlan(plan());
    FlowPolicy q;
    LearnedStore store;
    EXPECT_EQ(store.restore(nvs, l, q, 0), 2u);
    EXPECT_EQ(derived(l, q), derived(h.learner, p)) << "version 1 is lossless";
    // Their room is what the packed record needs: with too little for both, the old keys go first.
    nvs.capacity = packed(l, q).size() + 10;
    EXPECT_TRUE(store.save(nvs, l, q, 0));
    EXPECT_TRUE(nvs.legacy.empty());
    EXPECT_EQ(nvs.slots.at(0), packed(l, q));
    // Once a part exists, old keys are not restored (an interrupted migration): the next save erases them.
    nvs.legacy[1] = LearnedState::roomFrame(h.learner, 0, LearnedState::version);
    FlowLearner m; m.setPlan(plan());
    LearnedStore again;
    EXPECT_EQ(again.restore(nvs, m, q, 0), 2u);
    EXPECT_TRUE(again.save(nvs, m, q, 0));
    EXPECT_TRUE(nvs.legacy.empty());
}

// ---------------------------------------------------------------------------------------
// The owner's E32 (rc.2 learned-room review): all 8 rooms' learned state kept over a restart
// on a unit at the measured baseline, while a plan save, a 2 KB Bluetooth save, the handover
// confirmation, the flow record and the control record's replacement always fit. The real
// frames (LearnedStore, LearnedState), the real gate (ControlPartitionBudget) and its
// priorities (OptionalRecordPriority), NVS charged as the budget charges it (blobEntries, an
// upper bound of what NVS uses). Baselines: 198 of 630 used (beta.19 post-install capture,
// e32-beta19-20261030-postinstall-capture.json) and 178 (beta.22, /status/logs 1 Nov).
namespace {
using heating::control::ControlPartitionBudget;
using heating::control::ControlPartitionStats;
using heating::control::OptionalRecordPriority;
using heating::control::AutoTuner;
using heating::control::TakeoverReadiness;
using B = ControlPartitionBudget;

// The NVS partition as the gate sees it: a fixed baseline plus the optional records.
struct BudgetNvs final : LearnedStore::Backend {
    size_t baseline = 198, reserve = 0;
    std::map<std::string, size_t> records;      // optional key -> bytes
    std::map<size_t, std::string> parts;
    size_t used() const { size_t n = baseline; for (const auto& [k, b] : records) n += B::blobEntries(b); return n; }
    ControlPartitionStats stats() const { return {20480, 630, std::min<size_t>(used(), 630), 630 - std::min<size_t>(used(), 630), true}; }
    bool put(const std::string& key, size_t bytes, size_t priority) {
        const size_t old = records.count(key) ? records.at(key) : 0;
        if (!B::permitsOptionalWrite(stats(), bytes, old, reserve, priority)) return false;
        records[key] = bytes;
        return true;
    }
    // As LearnedNvs::write: after the knobs and the readiness counters (when not stored yet).
    bool read(size_t part, std::string& out) override {
        if (!parts.count(part)) return false;
        out = parts.at(part); return true;
    }
    bool write(size_t part, std::string_view bytes) override {
        if (!put(part ? "learned_b" : "learned_a", bytes.size(), OptionalRecordPriority::learned(records.count("autotune"), records.count("readiness")))) return false;
        parts[part] = std::string(bytes); return true;
    }
    bool erase(size_t part) override { records.erase(part ? "learned_b" : "learned_a"); parts.erase(part); return true; }
    // As AutoTunerNvs::write: the values with the full log, else the values alone.
    bool knobs(size_t learnedPending) {
        return put("autotune", AutoTuner::storedMaxBytes + 1, OptionalRecordPriority::tuningLog(learnedPending))
            || put("autotune", OptionalRecordPriority::knobsBytes, 0);
    }
    bool readiness() { return put("readiness", sizeof(TakeoverReadiness::Stored), 0); }
};

// A version 1 room frame with another id (the frame's layout: header, id length, id, the rest, CRC).
std::string renamed(const std::string& f, const std::string& id) {
    std::string out = f.substr(0, 4);
    out += char(id.size()); out += id;
    const size_t old = uint8_t(f[4]);
    out += f.substr(5 + old, f.size() - 4 - 5 - old);
    const auto n = uint16_t(out.size() - 4); out[2] = char(n & 0xFF); out[3] = char(n >> 8);
    const uint32_t c = LearnedState::crc(out.data(), out.size());
    out.append(reinterpret_cast<const char*>(&c), 4);
    return out;
}
// The worst case: a 32-character id and all 20 bins learned, each with segments without the
// outdoor (the 23-byte form), plausible values (version 1, read back through the real reader).
std::string worstRoom(const std::string& id, RoomPlan::Emitter emitter) {
    std::string f{char(LearnedState::version), LearnedState::roomKind, 0, 0};
    f += char(id.size()); f += id; f += char(emitter);
    for (const uint16_t v : {200, 50, 40, 3, 10, 10}) put(f, v);
    for (const double v : {50.0, 30.0, 9000.0, 40.0, 200.0, 3000.0, 20.0, 100.0, 8000.0}) put(f, v);
    put(f, uint32_t((1u << FlowLearner::binCount) - 1));
    for (size_t k = 0; k < FlowLearner::binCount; ++k) {
        f += char(20); f += char(8); f += char(15); put(f, uint16_t(40));
        const float w = 30 + 0.37f * k, flow = 21 + 2.0f * k, q = 0.5f + 0.03f * k, ow = 0.8f * w, o = 5 + 0.1f * k;
        for (const float x : {w, w * flow, w * q, w * (q * q + 0.04f), ow, ow * o, ow * (o * o + 9), ow * (o * (q + 0.01f) + 0.3f), ow * (q + 0.01f)})
            put(f, x);
    }
    const auto n = uint16_t(f.size() - 4); f[2] = char(n & 0xFF); f[3] = char(n >> 8);
    put(f, LearnedState::crc(f.data(), f.size()));
    return f;
}
RoomPlan eightRooms(size_t idBytes) {
    RoomPlan p; p.rooms.resize(RoomPlan::maxRooms);
    for (size_t i = 0; i < p.rooms.size(); ++i) {
        p.rooms[i].id = std::string(idBytes - 1, "abcdefgh"[i]) + char('0' + i);
        p.rooms[i].emitter = i % 2 ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor;
        p.rooms[i].state = RoomDemand::State::active; p.rooms[i].schedule = program();
    }
    return p;
}
// 8 rooms that learned what the house's floor and radiator room learned (6 bins each), or the worst case.
struct EightRooms {
    Learned source;
    FlowLearner l;
    FlowPolicy p;
    EightRooms(bool worst) {
        const auto rp = eightRooms(worst ? 32 : 10);
        l.setPlan(rp);
        EXPECT_TRUE(LearnedState::restoreGlobal(LearnedState::globalFrame(source.h.learner, source.policy), l, p));
        uint32_t done = 0;
        for (size_t i = 0; i < rp.rooms.size(); ++i) {
            const auto f = worst ? worstRoom(rp.rooms[i].id, rp.rooms[i].emitter)
                                 : renamed(LearnedState::roomFrame(source.h.learner, i % 2, LearnedState::version), rp.rooms[i].id);
            EXPECT_TRUE(LearnedState::restoreRoom(f, l, done)) << i;
        }
    }
};
struct Scenario { size_t baseline, plan, control; bool graph, worst; };
struct Outcome { size_t rooms, stored, used, parts, learnedBytes; bool log, readiness; };
// Two days of the E32's saves (readiness and knobs at the day change, then what was learned),
// then the invariant: control's writes fit without erasing anything.
Outcome run(const Scenario& s, EightRooms& house) {
    BudgetNvs nvs;
    nvs.baseline = s.baseline;
    const size_t control = B::controlReplacementEntries(s.control, s.graph);
    nvs.reserve = B::controlReserveEntries(s.plan, control);
    LearnedStore store;
    for (int day = 0; day < 2; ++day) {
        nvs.readiness();
        nvs.knobs(store.pendingEntries());
        store.save(nvs, house.l, house.p, uint64_t(day) * 24 * hour);
    }
    const auto st = nvs.stats();
    // The invariant.
    EXPECT_TRUE(B::permitsHeatingPlanWrite(st, std::min(s.plan + B::editBytes, B::configBytes), {}, control)) << "same-size plan save";
    EXPECT_TRUE(B::permitsBluetoothWrite(st, B::bluetoothBytes, {}, control)) << "a 2 KB Bluetooth save";
    EXPECT_GE(st.freeEntries, B::handoverEntries + B::blobEntries(B::flowRecordBytes) + B::entriesPerPage) << "handover and flow record";
    if (s.graph) { EXPECT_TRUE(B::permitsGraphWrite(st, B::configBytes)) << "graph profile: a full control record"; }
    else { EXPECT_GE(st.freeEntries, 2 + B::blobEntries(std::min(s.control + B::editBytes, B::configBytes)) + B::entriesPerPage) << "control replacement"; }
    EXPECT_LE(st.usedEntries, 630u - B::entriesPerPage) << "never physically full";
    size_t bytes = 0;
    for (const auto& [k, v] : nvs.parts) bytes += v.size();
    return {store.rooms(), store.storedRooms(), st.usedEntries, nvs.parts.size(), bytes,
            nvs.records.count("autotune") && nvs.records.at("autotune") > OptionalRecordPriority::knobsBytes, nvs.records.count("readiness") > 0};
}
}

TEST(LearnedNvsBudget, TheOwnersUnitKeepsEveryRoomAndControlKeepsItsRoom) {
    ScopedTz tz(ScopedTz::amsterdam);
    EightRooms typical(false), worst(true);
    // The frames are what LearnedState::compactRoomBytes says.
    EXPECT_EQ(LearnedState::roomFrame(typical.l, 0).size(), LearnedState::compactRoomBytes(10, 6));
    EXPECT_EQ(LearnedState::roomFrame(worst.l, 0).size(), LearnedState::compactRoomBytes(32, 0, 20));
    std::printf("[ nvs ] baseline  plan  control         learned       stored  parts  bytes  log  readiness  used  free\n");
    for (const size_t baseline : {size_t(198), size_t(178)})
    for (const bool w : {false, true})
    for (const auto& [plan, control, graph] : std::initializer_list<std::tuple<size_t, size_t, bool>>{
             {930, 200, false}, {930, 0, false}, {600, 200, false}, {2000, 200, false}, {930, 1200, false}, {930, 4000, false},
             {930, 1200, true}, {4096, 200, false}}) {
        auto& house = w ? worst : typical;
        const auto o = run({baseline, plan, control, graph, w}, house);
        std::printf("[ nvs ] %8zu  %4zu  %4zu B%-8s  %-12s  %2zu/%zu  %5zu  %5zu  %-3s  %-9s  %4zu  %4zu\n", baseline, plan, control,
                    graph ? " (graph)" : "", w ? "8x20 bins" : "8x6 bins", o.stored, o.rooms, o.parts, o.learnedBytes, o.log ? "yes" : "no",
                    o.readiness ? "yes" : "no", o.used, 630 - o.used);
        EXPECT_EQ(o.rooms, 8u);
        EXPECT_TRUE(o.readiness);
        // The goal on the owner's unit (plan ~0.93 KB, Home Assistant session without rooms):
        // every room, the knobs with their log and the readiness, also in the worst case
        // (there the knobs' log yields first).
        if (plan == 930 && control <= 200 && !graph) {
            EXPECT_EQ(o.stored, 8u) << baseline << (w ? " worst" : " typical");
            if (!w) { EXPECT_TRUE(o.log); }
        }
    }
}

// Before: the per-room keys, version 1 frames and a full 4 KB control replacement kept the
// owner's unit to the knobs, the readiness and at most one small room (the rc2-fw-review2 ledger).
TEST(LearnedNvsBudget, BeforeOnlyOneSmallRoomFitTheOwnersUnit) {
    const size_t before = B::handoverEntries + B::blobEntries(B::flowRecordBytes) + B::planSaveEntries(B::privateSaveBytes(930, 2048));
    const size_t free = 630 - 198;
    const size_t optional = free - before;
    const size_t knobs = 1 + B::blobEntries(AutoTuner::storedMaxBytes + 1), readiness = 1 + B::blobEntries(sizeof(TakeoverReadiness::Stored));
    std::printf("[ nvs ] before: reserve %zu of %zu free, %zu for the optional records (knobs %zu, readiness %zu)\n", before, free, optional, knobs, readiness);
    EXPECT_LT(optional, knobs + readiness + 1 + B::blobEntries(240) + 1 + B::blobEntries(353)) << "not even the globals and one room";
    const size_t after = B::controlReserveEntries(930, B::controlReplacementEntries(200, false));
    std::printf("[ nvs ] after:  reserve %zu of %zu free, %zu for the optional records\n", after, free, free - after);
    EXPECT_EQ(before - after, 136u - B::controlReplacementEntries(200, false));
}

// A requested rollback (update::requestRollback, NvsOptionalRecords.h prepareNvsForPreviousFirmware):
// the previous firmware (beta.22, rc.1) keeps a full control replacement free for its plan and
// Bluetooth saves and reads no learned or tuning record. The optional records make that room,
// the least useful first. While this boot is unconfirmed the optional records follow that ledger.
TEST(LearnedNvsBudget, ARollbackFindsThePreviousFirmwaresRoom) {
    ScopedTz tz(ScopedTz::amsterdam);
    EightRooms worst(true);
    for (const size_t baseline : {size_t(198), size_t(178)})
    for (const auto& [plan, ble] : std::initializer_list<std::pair<size_t, size_t>>{{930, 600}, {930, 2047}, {2000, 300}}) {
        BudgetNvs nvs;
        nvs.baseline = baseline;
        nvs.reserve = B::controlReserveEntries(plan, B::controlReplacementEntries(200, false));
        LearnedStore store;
        nvs.readiness(); nvs.knobs(0);
        store.save(nvs, worst.l, worst.p, 0);
        nvs.knobs(store.pendingEntries());
        const auto oldGates = [&](ControlPartitionStats s) {
            return B::permitsHeatingPlanWrite(s, std::min(plan + B::editBytes, B::configBytes))      // beta.22's own gates
                && B::permitsBluetoothWrite(s, std::min(ble + B::editBytes, B::bluetoothBytes))
                && s.freeEntries >= B::previousFirmwareReserveEntries(plan, ble);
        };
        const bool before = oldGates(nvs.stats());
        const bool hadSecondPart = nvs.records.count("learned_b") > 0;
        std::vector<std::string> erased;
        ASSERT_TRUE(B::makeRoom([&](ControlPartitionStats s) { return s.freeEntries >= B::previousFirmwareReserveEntries(plan, ble); },
                                [&] { return nvs.stats(); },
                                [&](const char* key) -> size_t { return nvs.records.count(key) ? nvs.records.at(key) : 0; },
                                [&](const char* key) { if (nvs.records.erase(key)) erased.push_back(key); }));
        EXPECT_TRUE(oldGates(nvs.stats()));
        std::string list;
        for (const auto& k : erased) list += k + " ";
        std::printf("[ nvs ] rollback, baseline %zu, plan %zu B, Bluetooth %zu B: previous firmware's room %s before; erased %s-> %zu free\n",
                    baseline, plan, ble, before ? "kept" : "short", list.c_str(), nvs.stats().freeEntries);
        if (!erased.empty()) { EXPECT_EQ(erased.front(), hadSecondPart ? "learned_b" : "learned_a") << "the later rooms first"; }
        EXPECT_FALSE(std::count(erased.begin(), erased.end(), "autotune") && nvs.records.count("readiness")) << "least useful first";
        // Unconfirmed boot: the optional records under the previous firmware's ledger keep its room too.
        BudgetNvs pending;
        pending.baseline = baseline;
        pending.reserve = B::previousFirmwareReserveEntries(plan, ble);
        LearnedStore fresh;
        pending.readiness(); pending.knobs(0);
        fresh.save(pending, worst.l, worst.p, 0);
        EXPECT_TRUE(oldGates(pending.stats())) << "a bootloader rollback finds its room";
    }
}

// rc.4 (L2): the arrival factors travel as their own frame, come back by room id, and an older
// bundle without the frame (or a damaged frame) leaves them neutral.
TEST(LearnedState, TheArrivalFactorsTravelInTheBundleAndComeBackById) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto plan2 = [](std::initializer_list<const char*> ids) {
        RoomPlan p;
        for (const char* id : ids) { RoomPlan::Room r; r.id = r.name = id; r.state = RoomDemand::State::active; r.emitter = RoomPlan::Emitter::floor; p.rooms.push_back(r); }
        return p;
    };
    FlowLearner l; l.setPlan(plan2({"woonkamer", "keuken"}));
    FlowPolicy p; p.setPlan(plan2({"woonkamer", "keuken"}));
    using heating::control::ArrivalLearner;
    const ArrivalLearner::Rise rise{1'800'000'000 + 8 * 3600, 1'800'000'000 + 6 * 3600, 2100};
    for (int64_t t = rise.startUtc - 600; t <= rise.atUtc + 1800; t += 60) {                 // keuken arrives 20 min late
        const int16_t temp = t < rise.startUtc ? 1900 : int16_t(std::min<int64_t>(2100, 1900 + 200 * (t - rise.startUtc) / (rise.atUtc + 1200 - rise.startUtc)));
        p.arrival().observe(1, t, rise, t >= rise.startUtc, temp);
    }
    ASSERT_EQ(p.arrival().events(1), 1u);
    const auto all = LearnedState::bundle(l, p, 4096);
    const auto g = LearnedState::globalFrame(l, p);
    ASSERT_GT(all.size(), g.size());
    EXPECT_EQ(all[g.size() + 1], 'A');
    EXPECT_TRUE(LearnedState::validBundle(all));
    FlowLearner m; m.setPlan(plan2({"keuken", "woonkamer"}));
    FlowPolicy q; q.setPlan(plan2({"keuken", "woonkamer"}));
    EXPECT_EQ(LearnedState::restoreBundle(all, m, q), 0) << "no room frames";
    EXPECT_NEAR(q.arrival().lead(0).factor, 1.10f, 1e-5);
    EXPECT_EQ(q.arrival().events(0), 1u);
    EXPECT_FLOAT_EQ(q.arrival().lead(1).factor, 1.0f);
    // A damaged arrival frame: the bundle is invalid; the store path skips just that frame.
    auto bad = all; bad[g.size() + 9] = char(bad[g.size() + 9] ^ 0x55);
    EXPECT_FALSE(LearnedState::validBundle(bad));
    FlowPolicy r; r.setPlan(plan2({"keuken"}));
    uint32_t done = 0; bool global = false;
    LearnedState::restoreFrames(bad, m, r, done, global);
    EXPECT_TRUE(global); EXPECT_FLOAT_EQ(r.arrival().lead(0).factor, 1.0f);
    // Without any judged morning there is no frame at all.
    FlowPolicy none; none.setPlan(plan2({"woonkamer"}));
    EXPECT_EQ(LearnedState::arrivalFrame(none), "");
    EXPECT_EQ(LearnedState::bundle(l, none, 4096), g);
}
