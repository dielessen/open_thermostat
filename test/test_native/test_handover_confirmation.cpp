#include "control/ActiveHeatGuard.h"
#include "control/HandoverConfirmation.h"
#include <gtest/gtest.h>
#include <string>
#include <vector>

namespace {
using heating::control::ActiveHeatGuard;
using heating::control::FlowDemand;
using heating::control::HandoverConfirmation;
using heating::control::RoomPlan;
using State = ActiveHeatGuard::State;
constexpr uint64_t second = 1000, minute = 60000;

// NVS stand-in: counts writes, can fail.
struct FakeStore {
    std::string record;
    bool fails = false;
    int writes = 0, erases = 0;
    std::string read() const { return record; }
    bool write(std::string_view r) { ++writes; if (fails) return false; record = std::string(r); return true; }
    bool erase() { ++erases; if (fails) return false; record.clear(); return true; }
};

// One boot of the E32: guard + persistence, stepped like HeatingController.
struct Boot {
    FakeStore& store;
    HandoverConfirmation<FakeStore> handover;
    ActiveHeatGuard guard;
    ActiveHeatGuard::Inputs in;
    uint64_t now = 0;
    std::vector<uint8_t> sent;
    std::vector<uint64_t> sentAt;
    bool busHeard = true; // the boiler's reports arrive (0x18 every 10 s)
    Boot(FakeStore& s, const char* firmware) : store(s), handover(s, firmware) {
        in.mode = RoomPlan::Mode::active; in.routeReady = true; in.boilerLimitC = 60;
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 1900;
        in.request = {true, 40, FlowDemand::Reason::heating};
        if (handover.restore()) guard.restore(now);
    }
    void confirm(bool on) { guard.confirm(now, on); handover.sync(guard.confirmed()); }
    void runFor(uint64_t duration) {
        for (const uint64_t end = now + duration; now < end;) {
            now += 10 * second; in.uptimeMs = now;
            if (busHeard) in.boilerHeardAtMs = now - second;
            const auto c = guard.step(now, in);
            handover.sync(guard.confirmed());
            if (c.send) { sent.push_back(c.flowC); sentAt.push_back(now); guard.transmitted(now, true); }
        }
    }
};

TEST(HandoverConfirmation, StoredOnlyOnChangeAndRestoredForTheSameFirmware) {
    FakeStore store;
    {
        Boot b(store, "v0.1.0-e32v2-beta.19/0011223344556677");
        EXPECT_EQ(b.guard.state(), State::shadow);
        b.confirm(true);
        EXPECT_EQ(store.record, "v0.1.0-e32v2-beta.19/0011223344556677");
        b.runFor(10 * minute);
        EXPECT_EQ(store.writes, 1); // no flash write per step
        EXPECT_EQ(b.guard.state(), State::active);
    }
    // Restart while active: heat again without a new confirmation, after 2 min
    // of bus reception without a foreign 0x1A (review A6; the tado sends every ~40 s).
    Boot again(store, "v0.1.0-e32v2-beta.19/0011223344556677");
    EXPECT_TRUE(again.guard.confirmed());
    EXPECT_TRUE(again.guard.restored());
    EXPECT_TRUE(again.handover.stored());
    again.runFor(2 * minute);
    EXPECT_TRUE(again.sent.empty()); // first report at 9 s: 111 s heard
    EXPECT_EQ(again.guard.state(), State::arming);
    again.runFor(10 * second);
    ASSERT_EQ(again.sent.size(), 1u);
    EXPECT_EQ(again.sent[0], 40);
    EXPECT_EQ(again.sentAt[0], 130 * second);
    EXPECT_FALSE(again.guard.restored());
    EXPECT_EQ(store.writes, 1);
    // Frost protection follows the same rule.
    Boot frost(store, "v0.1.0-e32v2-beta.19/0011223344556677");
    frost.in.request = {false, 0, FlowDemand::Reason::idle}; frost.in.rooms.coldestCentiC = 600;
    frost.runFor(2 * minute);
    EXPECT_TRUE(frost.sent.empty());
    frost.runFor(10 * second);
    ASSERT_FALSE(frost.sent.empty());
    EXPECT_EQ(frost.sent.back(), 30);
    EXPECT_STREQ(frost.guard.command().why, "frost_minimum");
}

// Review A6: the tado was plugged in again while the E32 was off (an
// emergency hand-back by power), then the E32 restarts with the stored confirmation.
TEST(HandoverConfirmation, ThermostatBackBeforeTheRestartIsCaughtBeforeAnyRequest) {
    for (const uint64_t first : {5 * second, 60 * second, 115 * second}) { // the tado's next 0x1A after boot
        FakeStore store; store.record = "fw/1";
        Boot b(store, "fw/1");
        b.in.rooms.coldestCentiC = 600; // frost too: that is the tado's job now
        b.runFor(first - first % (10 * second));
        b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 1};
        b.runFor(10 * minute);
        EXPECT_TRUE(b.sent.empty()) << first;
        EXPECT_EQ(b.guard.state(), State::blockedForeignController);
        EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
        EXPECT_TRUE(store.record.empty());
    }
}

// The 2 minutes count only while the boiler is heard: a silent bus proves nothing.
TEST(HandoverConfirmation, ListeningNeedsContinuousBoilerReception) {
    FakeStore store; store.record = "fw/1";
    Boot b(store, "fw/1");
    b.busHeard = false;
    b.runFor(30 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.listenedMs(b.now), 0u);
    b.busHeard = true; b.runFor(90 * second);
    EXPECT_TRUE(b.sent.empty());
    b.busHeard = false; b.runFor(40 * second); // a gap of more than 30 s starts the count again
    EXPECT_EQ(b.guard.listenedMs(b.now), 0u); // nothing heard right now: no listening at all
    b.busHeard = true; b.runFor(110 * second);
    EXPECT_TRUE(b.sent.empty());
    b.runFor(20 * second);
    ASSERT_EQ(b.sent.size(), 1u);
    // A confirmation given on the page this boot needs no listening window.
    FakeStore fresh;
    Boot page(fresh, "fw/1");
    page.busHeard = false;
    page.confirm(true);
    page.runFor(minute);
    EXPECT_EQ(page.sent.size(), 1u);
    EXPECT_FALSE(page.guard.restored());
}

TEST(HandoverConfirmation, NewFirmwareAsksAgain) {
    FakeStore store; store.record = "v0.1.0-e32v2-beta.18/aaaaaaaaaaaaaaaa";
    Boot b(store, "v0.1.0-e32v2-beta.19/0011223344556677");
    EXPECT_FALSE(b.guard.confirmed());
    EXPECT_TRUE(store.record.empty());
    b.runFor(5 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
    // No firmware identity: never stored, never restored.
    FakeStore unknown; unknown.record = "x";
    Boot anonymous(unknown, "");
    EXPECT_FALSE(anonymous.guard.confirmed());
    anonymous.confirm(true);
    EXPECT_TRUE(anonymous.guard.confirmed());
    EXPECT_TRUE(unknown.record.empty());
}

TEST(HandoverConfirmation, ForeignRequestHandBackAndShadowEraseIt) {
    const char* fw = "fw/1";
    FakeStore store;
    {
        Boot b(store, fw); b.confirm(true); b.runFor(2 * minute);
        b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 1}; // the tado again
        b.runFor(10 * second);
        EXPECT_FALSE(b.guard.confirmed());
        EXPECT_TRUE(store.record.empty());
        EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::foreignController));
    }
    {
        Boot b(store, fw); b.confirm(true); b.runFor(2 * minute);
        b.confirm(false); // "back to the thermostat"
        EXPECT_TRUE(store.record.empty());
    }
    {
        Boot b(store, fw); b.confirm(true);
        b.in.mode = RoomPlan::Mode::shadow; b.runFor(10 * second);
        EXPECT_TRUE(store.record.empty());
    }
    // A foreign 0x1A within the boot holdoff after a restore: no heat at all.
    store.record = fw;
    Boot b(store, fw);
    b.runFor(30 * second);
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 5 * second};
    b.runFor(5 * minute);
    EXPECT_TRUE(b.sent.empty());
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_TRUE(store.record.empty());
}

TEST(HandoverConfirmation, FailedWriteRetriesNextStep) {
    FakeStore store; store.fails = true;
    Boot b(store, "fw/1"); b.confirm(true);
    EXPECT_FALSE(b.handover.stored());
    b.runFor(20 * second);
    EXPECT_EQ(store.writes, 3);
    store.fails = false; b.runFor(10 * second);
    EXPECT_TRUE(b.handover.stored());
    b.runFor(minute);
    EXPECT_EQ(store.writes, 4);
}
}
