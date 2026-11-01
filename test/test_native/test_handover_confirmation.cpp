#include "control/ActiveHeatGuard.h"
#include "control/HandoverConfirmation.h"
#include <gtest/gtest.h>
#include <memory>
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
    std::vector<uint8_t> sent; // delivered commands
    std::vector<uint64_t> sentAt;
    std::vector<std::string> why;
    int attempts = 0;
    bool busHeard = true; // the boiler's reports arrive (0x18 every 10 s)
    bool delivers = true; // the reviewed route completes the write
    Boot(FakeStore& s, const char* firmware) : store(s), handover(s, firmware) {
        in.mode = RoomPlan::Mode::active; in.routeReady = true; in.boilerLimitC = 60;
        in.rooms.active = in.rooms.fresh = 1; in.rooms.coldestCentiC = 1900;
        in.request = {true, 40, FlowDemand::Reason::heating};
        switch (handover.restoreState()) { // as HeatingController's constructor
            case HandoverConfirmation<FakeStore>::Restored::confirmed: guard.restore(now); break;
            case HandoverConfirmation<FakeStore>::Restored::reconfirm: guard.restoreReconfirm(); break;
            default: break;
        }
    }
    void sync() { handover.sync(guard.confirmed(), guard.reconfirmPending()); }
    void confirm(bool on) { guard.confirm(now, on); sync(); }
    void runFor(uint64_t duration) {
        for (const uint64_t end = now + duration; now < end;) {
            now += 10 * second; in.uptimeMs = now;
            if (busHeard) in.boilerHeardAtMs = now - second;
            const auto c = guard.step(now, in);
            sync();
            if (!c.send) continue;
            ++attempts;
            if (delivers) { sent.push_back(c.flowC); sentAt.push_back(now); why.emplace_back(c.why); }
            guard.transmitted(now, delivers);
        }
    }
    bool anyPositive() const { for (const auto f : sent) if (f) return true; return false; }
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
    // Only the boot zero (review S2): the boiler may still hold the request of the last boot.
    ASSERT_EQ(again.sent.size(), 1u); // first report at 9 s: 111 s heard
    EXPECT_EQ(again.sent[0], 0);
    EXPECT_EQ(again.sentAt[0], 10 * second);
    EXPECT_EQ(again.why[0], "boot_zero");
    EXPECT_EQ(again.guard.state(), State::arming);
    again.runFor(10 * second);
    ASSERT_EQ(again.sent.size(), 2u);
    EXPECT_EQ(again.sent[1], 40);
    EXPECT_EQ(again.sentAt[1], 130 * second);
    EXPECT_FALSE(again.guard.restored());
    EXPECT_EQ(store.writes, 1);
    // Frost protection follows the same rule.
    Boot frost(store, "v0.1.0-e32v2-beta.19/0011223344556677");
    frost.in.request = {false, 0, FlowDemand::Reason::idle}; frost.in.rooms.coldestCentiC = 600;
    frost.runFor(2 * minute);
    ASSERT_EQ(frost.sent.size(), 1u);
    EXPECT_EQ(frost.sent[0], 0);
    frost.runFor(10 * second);
    ASSERT_EQ(frost.sent.size(), 2u);
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
        // Never a positive request. Before the tado's 0x1A: at most the one boot zero
        // (10 s after boot; the tado repeats its request within ~40 s).
        EXPECT_FALSE(b.anyPositive()) << first;
        EXPECT_EQ(b.sent.size(), first < 10 * second ? 0u : 1u) << first;
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
    ASSERT_EQ(b.sent.size(), 1u); // the boot zero only: it needs a ready route, not listening
    EXPECT_EQ(b.sent[0], 0);
    EXPECT_EQ(b.guard.listenedMs(b.now), 0u);
    b.busHeard = true; b.runFor(90 * second);
    EXPECT_EQ(b.sent.size(), 1u);
    b.busHeard = false; b.runFor(40 * second); // a gap of more than 30 s starts the count again
    EXPECT_EQ(b.guard.listenedMs(b.now), 0u); // nothing heard right now: no listening at all
    b.busHeard = true; b.runFor(110 * second);
    EXPECT_EQ(b.sent.size(), 1u);
    b.runFor(20 * second);
    ASSERT_EQ(b.sent.size(), 2u);
    EXPECT_EQ(b.sent[1], 40);
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
    // The E32 owned the boiler before the update: it waits for a new confirmation (review S3).
    EXPECT_EQ(store.record, "reconfirm");
    EXPECT_TRUE(b.guard.reconfirmPending());
    EXPECT_TRUE(b.handover.pending());
    b.runFor(5 * minute);
    EXPECT_FALSE(b.anyPositive()); // 19 degC: no frost
    ASSERT_EQ(b.sent.size(), 1u); // the boot zero
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
    b.confirm(true);
    EXPECT_EQ(store.record, "v0.1.0-e32v2-beta.19/0011223344556677");
    EXPECT_FALSE(b.guard.reconfirmPending());
    b.runFor(10 * second);
    EXPECT_EQ(b.sent.back(), 40); // a confirmation on the page needs no listening window
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
    ASSERT_EQ(b.sent.size(), 1u); // the boot zero at 10 s, before the tado was heard
    EXPECT_EQ(b.sent[0], 0);
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

// Review P1 (S2): an unexpected restart while the boiler held 40 degC, before the
// room readings are fresh again. Before beta.23 the first command came after
// 30 min (lostAfterMs): the boiler kept the old request all that time.
TEST(HandoverConfirmation, RestartWithdrawsAStaleRequestBeforeListening) {
    FakeStore store; store.record = "fw/1";
    Boot b(store, "fw/1");
    b.in.rooms.fresh = 0; // not fresh yet after the restart
    EXPECT_TRUE(b.guard.bootZeroDue());
    EXPECT_TRUE(b.guard.claimsBoiler()); // the boiler trial waits for it
    EXPECT_FALSE(b.guard.released());
    b.runFor(10 * second);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0], 0);
    EXPECT_EQ(b.sentAt[0], 10 * second); // the first step over a ready route
    EXPECT_EQ(b.why[0], "boot_zero");
    EXPECT_FALSE(b.guard.bootZeroDue());
    EXPECT_TRUE(b.guard.released());
    EXPECT_FALSE(b.guard.claimsBoiler());
    b.runFor(29 * minute);
    EXPECT_EQ(b.sent.size(), 1u); // once: no zero train while it listens and waits
    EXPECT_EQ(b.guard.state(), State::arming);
}

// The boot zero waits for a ready route and repeats every 10 s until delivered.
TEST(HandoverConfirmation, BootZeroRepeatsUntilDelivered) {
    FakeStore store; store.record = "fw/1";
    Boot b(store, "fw/1");
    b.in.routeReady = false; b.runFor(30 * second);
    EXPECT_EQ(b.attempts, 0);
    EXPECT_STREQ(b.guard.command().why, "route_not_ready");
    b.in.routeReady = true; b.delivers = false; b.runFor(50 * second);
    EXPECT_EQ(b.attempts, 5);
    EXPECT_TRUE(b.guard.bootZeroDue());
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    b.runFor(20 * second); // one minute without a delivered zero
    EXPECT_TRUE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    EXPECT_FALSE(b.guard.released());
    b.delivers = true; b.runFor(10 * second);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.sent[0], 0);
    EXPECT_FALSE(b.guard.bootZeroDue());
    b.runFor(10 * second);
    EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
    EXPECT_EQ(b.attempts, 8);
}

// Review 1.0 (S2 gap): after new firmware a boot zero still owed when frost protection
// may run (2 min of listening) is not dropped in a warm house: it keeps repeating
// every 10 s until delivered, and then the boiler trial is free again.
TEST(HandoverConfirmation, BootZeroOwedPastTheListeningWindowIsStillSent) {
    for (const bool routeLate : {true, false}) {
        FakeStore store; store.record = "fw/1";
        Boot b(store, "fw/2"); // rooms at 19 degC: frost asks nothing
        b.in.routeReady = !routeLate; b.delivers = false; // the first 3 min deliver nothing
        b.runFor(3 * minute);
        EXPECT_EQ(b.attempts, routeLate ? 0 : 18) << routeLate; // also past 130 s
        EXPECT_TRUE(b.guard.bootZeroDue());
        EXPECT_EQ(b.guard.warning(ActiveHeatGuard::transmitFailed), !routeLate);
        b.in.routeReady = true; b.delivers = true;
        b.runFor(10 * second);
        ASSERT_EQ(b.sent.size(), 1u) << routeLate;
        EXPECT_EQ(b.sent[0], 0);
        EXPECT_EQ(b.why[0], "boot_zero");
        EXPECT_FALSE(b.guard.bootZeroDue());
        EXPECT_TRUE(b.guard.released());
        EXPECT_FALSE(b.guard.claimsBoiler());
        b.runFor(30 * minute);
        EXPECT_EQ(b.sent.size(), 1u) << routeLate; // once, then quiet
        EXPECT_FALSE(b.guard.warning(ActiveHeatGuard::transmitFailed));
        EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
    }
}

// Shadow mode stays silent whatever the store holds: command for command and
// status for status the same as a boot without any record. A boot without a
// record in active mode sends no boot zero either.
TEST(HandoverConfirmation, ShadowIsUnchangedByAnyStoredRecord) {
    using Json = std::unique_ptr<char, void (*)(void*)>;
    const auto status = [](const ActiveHeatGuard& g, uint64_t now) {
        cJSON* j = g.json(now);
        Json text(cJSON_PrintUnformatted(j), cJSON_free);
        cJSON_Delete(j);
        return std::string(text.get());
    };
    for (const char* record : {"fw/1", "reconfirm", "fw/0"}) {
        FakeStore none, store; store.record = record;
        Boot plain(none, "fw/1"), left(store, "fw/1");
        for (Boot* b : {&plain, &left}) b->in.mode = RoomPlan::Mode::shadow;
        for (int i = 0; i < 400; ++i) {
            for (Boot* b : {&plain, &left}) { // every input a shadow boot can see
                b->in.rooms.coldestCentiC = i % 7 < 3 ? 600 : 2100;
                b->in.rooms.fresh = i % 11 ? 1 : 0;
                b->in.routeReady = i % 13 != 0;
                b->busHeard = i % 17 != 0;
                if (i == 200) b->in.foreign = ActiveHeatGuard::Foreign{0x17, b->now + 1};
                if (i == 300) b->guard.withdraw(b->now);
                b->runFor(10 * second);
            }
            ASSERT_EQ(left.guard.command().send, plain.guard.command().send) << record << " " << i;
            ASSERT_EQ(left.guard.command().flowC, plain.guard.command().flowC) << record << " " << i;
            ASSERT_STREQ(left.guard.command().why, plain.guard.command().why) << record << " " << i;
            ASSERT_EQ(status(left.guard, left.now), status(plain.guard, plain.now)) << record << " " << i;
            ASSERT_EQ(left.guard.claimsBoiler(), plain.guard.claimsBoiler()) << record << " " << i;
            ASSERT_EQ(left.guard.released(), plain.guard.released()) << record << " " << i;
            ASSERT_EQ(left.guard.outputActive(), plain.guard.outputActive()) << record << " " << i;
        }
        EXPECT_EQ(left.attempts, 0) << record;
        EXPECT_EQ(plain.attempts, 0);
        EXPECT_TRUE(store.record.empty()) << record; // the shadow plan erases it
    }
    FakeStore none;
    Boot fresh(none, "fw/1"); // active, never confirmed on this E32
    fresh.in.rooms.coldestCentiC = 600;
    EXPECT_FALSE(fresh.guard.bootZeroDue());
    EXPECT_FALSE(fresh.guard.claimsBoiler());
    fresh.runFor(30 * minute);
    EXPECT_EQ(fresh.attempts, 0);
    EXPECT_EQ(fresh.guard.state(), State::awaitingConfirmation);
}

// Review P3 (S3a): after a firmware update the E32 owned the boiler but waits for
// the owner to confirm again. Before beta.23 nobody kept frost protection then.
TEST(HandoverConfirmation, FrostProtectionWhileWaitingForANewConfirmation) {
    FakeStore store; store.record = "fw/1";
    Boot b(store, "fw/2");
    b.in.rooms.coldestCentiC = 600; // the rooms still ask 40 degC: never followed unconfirmed
    b.runFor(2 * minute);
    ASSERT_EQ(b.sent.size(), 1u);
    EXPECT_EQ(b.why[0], "boot_zero");
    b.runFor(10 * second); // past the boot holdoff and 2 min of listening without a foreign 0x1A
    ASSERT_EQ(b.sent.size(), 2u);
    EXPECT_EQ(b.sent[1], 30);
    EXPECT_EQ(b.sentAt[1], 130 * second);
    EXPECT_EQ(b.why[1], "frost_unconfirmed");
    EXPECT_EQ(b.guard.state(), State::awaitingConfirmation);
    EXPECT_FALSE(b.guard.confirmed());
    EXPECT_TRUE(b.guard.outputActive());
    EXPECT_TRUE(b.guard.claimsBoiler());
    b.runFor(10 * minute);
    for (size_t i = 1; i < b.sent.size(); ++i) EXPECT_EQ(b.sent[i], 30) << i;
    EXPECT_GE(b.sent.size(), 11u); // repeated every minute
    // Warm again: the zero window, then quiet.
    b.in.rooms.coldestCentiC = 950;
    const size_t warm = b.sent.size();
    b.runFor(2 * minute);
    ASSERT_GT(b.sent.size(), warm);
    EXPECT_EQ(b.why[warm], "stop_zero");
    for (size_t i = warm; i < b.sent.size(); ++i) EXPECT_EQ(b.sent[i], 0) << i;
    EXPECT_TRUE(b.guard.released());
    EXPECT_FALSE(b.guard.claimsBoiler());
    EXPECT_FALSE(b.guard.outputActive());
    const size_t quiet = b.sent.size();
    b.runFor(10 * minute);
    EXPECT_EQ(b.sent.size(), quiet);
    EXPECT_EQ(store.record, "reconfirm"); // still waiting for the owner
    // Review P4: the boiler's limit unknown, no frost request.
    FakeStore unknown; unknown.record = "fw/1";
    Boot u(unknown, "fw/2");
    u.in.boilerLimitC.reset(); u.in.rooms.coldestCentiC = 600;
    u.runFor(10 * minute);
    EXPECT_FALSE(u.anyPositive());
}

// S3a: only without a foreign master this boot.
TEST(HandoverConfirmation, ForeignControllerEndsTheWaitAndItsFrost) {
    {
        FakeStore store; store.record = "fw/1";
        Boot b(store, "fw/2"); b.in.rooms.coldestCentiC = 600;
        b.runFor(minute);
        b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 1}; // within the listening window
        b.runFor(10 * minute);
        EXPECT_FALSE(b.anyPositive());
        EXPECT_EQ(b.guard.state(), State::blockedForeignController);
        EXPECT_FALSE(b.guard.reconfirmPending());
        EXPECT_TRUE(store.record.empty());
    }
    FakeStore store; store.record = "fw/1";
    Boot b(store, "fw/2"); b.in.rooms.coldestCentiC = 600;
    b.runFor(3 * minute);
    ASSERT_TRUE(b.anyPositive());
    b.in.foreign = ActiveHeatGuard::Foreign{0x17, b.now + 1}; // the tado reconnected while frost runs
    const size_t at = b.sent.size();
    b.runFor(2 * minute);
    ASSERT_GT(b.sent.size(), at);
    for (size_t i = at; i < b.sent.size(); ++i) EXPECT_EQ(b.sent[i], 0) << i;
    EXPECT_EQ(b.guard.state(), State::blockedForeignController);
    EXPECT_TRUE(b.guard.released());
    EXPECT_TRUE(store.record.empty());
}

TEST(HandoverConfirmation, HandBackOrShadowEndsTheWait) {
    for (const bool shadow : {false, true}) {
        FakeStore store; store.record = "fw/1";
        Boot b(store, "fw/2"); b.in.rooms.coldestCentiC = 600;
        b.runFor(3 * minute);
        ASSERT_TRUE(b.anyPositive());
        const size_t at = b.sent.size();
        if (shadow) b.in.mode = RoomPlan::Mode::shadow;
        else b.confirm(false); // "back to the thermostat": handover false first
        b.runFor(30 * minute);
        ASSERT_GT(b.sent.size(), at) << shadow;
        for (size_t i = at; i < b.sent.size(); ++i) EXPECT_EQ(b.sent[i], 0) << shadow;
        EXPECT_FALSE(b.guard.reconfirmPending());
        EXPECT_TRUE(b.guard.released());
        EXPECT_FALSE(b.guard.claimsBoiler());
        EXPECT_TRUE(store.record.empty()) << shadow;
    }
}

// The wait survives a restart under the same firmware until the owner answers;
// confirming binds the new firmware again.
TEST(HandoverConfirmation, ReconfirmRecordSurvivesARestartUntilAnswered) {
    FakeStore store; store.record = "fw/1";
    { Boot b(store, "fw/2"); EXPECT_EQ(store.writes, 1); b.runFor(minute); }
    EXPECT_EQ(store.record, "reconfirm");
    {
        Boot b(store, "fw/2");
        EXPECT_TRUE(b.guard.reconfirmPending());
        EXPECT_TRUE(b.guard.bootZeroDue());
        b.runFor(minute);
        EXPECT_EQ(store.writes, 1); // no flash write per step or boot
        b.confirm(true);
    }
    EXPECT_EQ(store.record, "fw/2");
    {
        Boot b(store, "fw/2");
        EXPECT_TRUE(b.guard.confirmed());
        EXPECT_FALSE(b.guard.reconfirmPending());
    }
    // A failed write at boot still waits this boot and writes it again.
    FakeStore failing; failing.record = "fw/1"; failing.fails = true;
    Boot f(failing, "fw/2");
    EXPECT_TRUE(f.guard.reconfirmPending());
    EXPECT_FALSE(f.handover.pending());
    failing.fails = false; f.runFor(10 * second);
    EXPECT_EQ(failing.record, "reconfirm");
    EXPECT_TRUE(f.handover.pending());
}
}
