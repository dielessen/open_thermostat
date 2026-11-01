#include "control/RoomOverrides.h"
#include "RoomOverridesBeta21.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstring>
#include <memory>
#include <string>

namespace {
using heating::control::FlowLearner;
using heating::control::RoomEngine;
using heating::control::RoomOverrides;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t minute = 60000;
constexpr uint32_t monNoon = 1793617200;   // Mon 2 Nov 2026 12:00 Amsterdam (CET)
constexpr uint32_t mon2230 = 1793655000;   // Mon 2 Nov 2026 22:30
constexpr uint32_t satNoonDst = 1792836000; // Sat 24 Oct 2026 12:00 CEST, DST ends Sunday 03:00
constexpr uint32_t mon0630Cet = 1792992600; // Mon 26 Oct 2026 06:30 CET

// A radiator room with a week program (Mon 06:30 20.5, 22:30 18.0) and a Bluetooth
// sensor, a floor room without a program (fallback 20.0) and an inactive bathroom.
std::string planText(const char* livingMinimum = "500") {
    return std::string(R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[
 {"id":"living","name":"Living","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000001"}],"setpoint_entity":"","fallback_centi_c":2000,
  "minimum_centi_c":)") + livingMinimum + R"(,"maximum_centi_c":2400,"schedule":[[[390,2050],[1350,1800]],[],[],[],[],[],[]]},
 {"id":"study","name":"Study","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ble","id":"a4c138000002"}],"setpoint_entity":"","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500},
 {"id":"bath","name":"Bath","state":"inactive","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000003"}],"setpoint_entity":"","fallback_centi_c":2200,"minimum_centi_c":500,"maximum_centi_c":2500}]})";
}
RoomPlan plan(const char* livingMinimum = "500") {
    Json root(cJSON_Parse(planText(livingMinimum).c_str()), cJSON_Delete);
    RoomPlan p;
    EXPECT_EQ(RoomPlan::parse(root.get(), p), nullptr);
    return p;
}
const char* command(RoomOverrides& o, const RoomPlan& p, const char* body, uint64_t now, std::optional<uint32_t> utc,
                    bool* persisted = nullptr) {
    Json root(cJSON_Parse(body), cJSON_Delete);
    bool persist = false;
    const char* error = o.command(root.get(), p, now, utc, persist);
    if (persisted) *persisted = persist;
    return error;
}
const auto noLead = [](size_t, uint32_t, int16_t, int16_t) { return uint32_t(0); };
// The setpoint RoomEngine reports for a room after one step with the adjustments.
std::optional<int16_t> engineSetpoint(RoomEngine& e, const RoomOverrides& o, size_t room, uint64_t now, std::optional<uint32_t> utc,
                                      int16_t temperature = 1900) {
    for (const char* id : {"a4c138000001", "a4c138000002", "a4c138000003"}) e.bleReading(id, temperature, now);
    e.step(now, utc, o.adjust());
    return e.result(room).setpoint;
}
}

TEST(RoomOverrides, BoostRunsAnHourAtTheRoomMaximumThenTheWeekProgramReturns) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomEngine e; e.setPlan(p);
    RoomOverrides o;
    bool persisted = false;
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"boost"})", 0, monNoon, &persisted), nullptr);
    EXPECT_TRUE(persisted);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(0).mode, "boost");
    EXPECT_EQ(o.view(0).until, monNoon + 3600);
    EXPECT_EQ(engineSetpoint(e, o, 0, 0, monNoon), 2400);
    o.step(p, 59 * minute, monNoon + 59 * 60, noLead);
    EXPECT_EQ(engineSetpoint(e, o, 0, 59 * minute, monNoon + 59 * 60), 2400);
    o.step(p, 60 * minute, monNoon + 3600, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_EQ(o.view(0).kind, RoomOverrides::Kind::none);
    EXPECT_EQ(engineSetpoint(e, o, 0, 60 * minute, monNoon + 3600), 2050); // Monday's 06:30 point
    // Only the room's target changed: the flow limits are the plan's.
    EXPECT_LE(e.step(61 * minute, monNoon + 3660, o.adjust()).flowC, p.maximumFlowC);
}

TEST(RoomOverrides, TwoHoursAtTwentyOneAndUntilTheNextSwitchPoint) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"timed","temperature":21,"minutes":120})", 0, monNoon), nullptr);
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"next","temperature":19.5})", 0, monNoon), nullptr);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(1).mode, "timed");
    EXPECT_EQ(o.view(1).targetCentiC, 2100);
    EXPECT_EQ(o.view(1).until, monNoon + 7200);
    EXPECT_STREQ(o.view(0).mode, "next");
    EXPECT_EQ(o.view(0).until, mon2230);   // the program's next point, 22:30 local
    EXPECT_EQ(o.adjust()[0].setpoint, 1950);
    o.step(p, 120 * minute, monNoon + 7200, noLead);
    EXPECT_EQ(o.view(1).mode, nullptr);
    EXPECT_STREQ(o.view(0).mode, "next");
    o.step(p, 630 * minute, mon2230, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_FALSE(o.adjust()[0].setpoint);
    // Clearing an override returns at once.
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"timed","temperature":21,"minutes":30})", 0, monNoon), nullptr);
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"none"})", 1000, monNoon + 1), nullptr);
    EXPECT_EQ(o.view(1).mode, nullptr);
}

TEST(RoomOverrides, NextSwitchPointFollowsTheLocalClockAcrossDst) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    // Saturday noon (CEST) to Monday 06:30 (CET): 42.5 h of wall time, 43.5 h real.
    EXPECT_EQ(RoomOverrides::nextSwitchUtc(p.rooms[0].schedule, satNoonDst), mon0630Cet);
    EXPECT_EQ(RoomOverrides::nextSwitchUtc(p.rooms[1].schedule, satNoonDst), 0u); // no program
    // An override never lasts longer than a day, also "until the next switch point".
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"next","temperature":21})", 0, satNoonDst), nullptr);
    EXPECT_EQ(o.view(0).until, satNoonDst + 86400);
}

TEST(RoomOverrides, CommandsAreCheckedAgainstThePlan) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    EXPECT_STREQ(command(o, p, R"({"room":"attic","override":"boost"})", 0, monNoon), "unknown_room");
    EXPECT_STREQ(command(o, p, R"({"room":"bath","override":"boost"})", 0, monNoon), "room_inactive");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"timed","temperature":24.5,"minutes":60})", 0, monNoon), "invalid_temperature");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"timed","temperature":21})", 0, monNoon), "invalid_minutes");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"timed","temperature":21,"minutes":1441})", 0, monNoon), "invalid_minutes");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"timed","temperature":21,"minutes":1.5})", 0, monNoon), "invalid_minutes");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"hold","temperature":21})", 0, monNoon), "invalid_override");
    EXPECT_STREQ(command(o, p, R"({"room":"study","override":"next","temperature":21})", 0, monNoon), "no_schedule");
    EXPECT_STREQ(command(o, p, R"({"room":"living","override":"next","temperature":21})", 0, std::nullopt), "no_clock");
    EXPECT_STREQ(command(o, p, R"({"away":true,"until":1})", 0, monNoon), "invalid_until");
    EXPECT_STREQ(command(o, p, R"({"away":true,"until":1893456000})", 0, monNoon), "invalid_until"); // > 366 days
    EXPECT_STREQ(command(o, p, R"({"away":true,"until":1793700000})", 0, std::nullopt), "no_clock");
    EXPECT_STREQ(command(o, p, R"({"away":true,"temperature":30})", 0, monNoon), "invalid_temperature");
    EXPECT_STREQ(command(o, p, R"({"away":"yes"})", 0, monNoon), "invalid_request");
    EXPECT_STREQ(command(o, p, R"([1])", 0, monNoon), "invalid_request");
    o.step(p, 0, monNoon, noLead);
    for (size_t i = 0; i < 3; ++i) EXPECT_EQ(o.view(i).mode, nullptr);
    EXPECT_EQ(o.stored(), R"({"v":1,"away_c":1500,"o":[]})");
}

TEST(RoomOverrides, KeptAcrossARestartOnlyWithATrustedClock) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides before;
    ASSERT_EQ(command(before, p, R"({"room":"study","override":"timed","temperature":21,"minutes":120})", 5 * minute, monNoon), nullptr);
    const auto record = before.stored();
    EXPECT_NE(record.find(R"("id":"study","k":"timed","c":2100,"u":1793624400)"), std::string::npos);

    // After the restart: no clock yet, so the room follows its plan and the override waits.
    RoomOverrides after;
    ASSERT_TRUE(after.restore(record));
    RoomEngine e; e.setPlan(p);
    after.step(p, 0, std::nullopt, noLead);
    EXPECT_EQ(after.view(1).mode, nullptr);
    EXPECT_TRUE(after.view(1).waiting);
    EXPECT_EQ(engineSetpoint(e, after, 1, 0, std::nullopt), 2000);
    // The clock arrives 30 min after the override began: the remaining 90 min apply.
    after.step(p, minute, monNoon + 1800, noLead);
    EXPECT_STREQ(after.view(1).mode, "timed");
    EXPECT_EQ(engineSetpoint(e, after, 1, minute, monNoon + 1800), 2100);
    after.step(p, 91 * minute, monNoon + 7200, noLead);
    EXPECT_EQ(after.view(1).mode, nullptr);

    // A restart after its end drops it as soon as the clock is known.
    RoomOverrides late;
    ASSERT_TRUE(late.restore(record));
    late.step(p, 0, monNoon + 7200, noLead);
    EXPECT_EQ(late.view(1).kind, RoomOverrides::Kind::none);
    EXPECT_EQ(late.stored(), R"({"v":1,"away_c":1500,"o":[]})");

    // A room that left the plan loses its override.
    RoomOverrides moved;
    ASSERT_TRUE(moved.restore(R"({"v":1,"away_c":1500,"o":[{"id":"attic","k":"boost","c":2400,"u":1793621000}]})"));
    moved.step(p, 0, monNoon, noLead);
    EXPECT_EQ(moved.stored(), R"({"v":1,"away_c":1500,"o":[]})");
}

TEST(RoomOverrides, WithoutAClockAnOverrideLastsItsUptimeAndIsNotKept) {
    const auto p = plan();
    RoomOverrides o;
    bool persisted = true;
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"timed","temperature":22,"minutes":10})", 0, std::nullopt, &persisted), nullptr);
    EXPECT_FALSE(persisted);
    o.step(p, minute, std::nullopt, noLead);
    EXPECT_STREQ(o.view(1).mode, "timed");
    EXPECT_EQ(o.view(1).remainingS, 540u);
    EXPECT_EQ(o.view(1).until, 0u);
    EXPECT_EQ(o.stored(), R"({"v":1,"away_c":1500,"o":[]})");
    // A clock that arrives later (or jumps) never extends it.
    o.step(p, 9 * minute, monNoon, noLead);
    EXPECT_STREQ(o.view(1).mode, "timed");
    o.step(p, 10 * minute, monNoon + 60, noLead);
    EXPECT_EQ(o.view(1).mode, nullptr);
    // A clocked override also ends at its uptime when the wall clock goes back.
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"timed","temperature":22,"minutes":10})", 20 * minute, monNoon), nullptr);
    o.step(p, 30 * minute, monNoon - 3600, noLead);
    EXPECT_EQ(o.view(1).mode, nullptr);
}

TEST(RoomOverrides, StoredRecordsThisFirmwareCannotReadAreIgnored) {
    RoomOverrides o;
    for (const char* bad : {"", "{", R"({"v":2,"o":[]})", R"({"v":1})", R"({"v":1,"away_c":9000,"o":[]})",
                            R"({"v":1,"o":[{"id":"x","k":"hold","c":2000,"u":5}]})",
                            R"({"v":1,"o":[{"id":"x","k":"boost","c":2000,"u":0}]})",
                            R"({"v":1,"o":[{"id":"x","k":"boost","c":2000.5,"u":5}]})",
                            R"({"v":1,"o":[[[[[1]]]]]})"}) {
        EXPECT_FALSE(o.restore(bad)) << bad;
        EXPECT_EQ(o.stored(), R"({"v":1,"away_c":1500,"o":[]})") << bad;
    }
    EXPECT_FALSE(o.restore(std::string(RoomOverrides::storeBytes + 1, ' ')));
}

TEST(RoomOverrides, AnOpenWindowPausesAfterItsDelayAtTheFrostFloor) {
    const auto p = plan("1000"); // the living room's own minimum is 10 degC
    RoomEngine e; e.setPlan(p);
    RoomOverrides o;
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":true,"delay_s":60})", p, 0));
    o.step(p, 0, std::nullopt, noLead);
    EXPECT_STREQ(o.view(0).window, "pending");
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_EQ(engineSetpoint(e, o, 0, 0, std::nullopt), 2000);
    // A repeated open report does not restart the delay.
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":true,"delay_s":60})", p, 30000));
    o.step(p, 60000, std::nullopt, noLead);
    EXPECT_STREQ(o.view(0).mode, "window_open");
    EXPECT_STREQ(o.view(0).window, "open");
    // Paused: the frost floor applies, also below the room minimum.
    EXPECT_EQ(engineSetpoint(e, o, 0, 60000, std::nullopt, 1200), 800);
    EXPECT_FALSE(e.result(0).errorCentiC > 0);
    EXPECT_EQ(engineSetpoint(e, o, 0, 70000, std::nullopt, 600), 800);
    EXPECT_GT(e.result(0).errorCentiC, 0); // a cold room still asks for heat
    // Closed: the room resumes at once.
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":false,"delay_s":60})", p, 80000));
    o.step(p, 80000, std::nullopt, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_EQ(engineSetpoint(e, o, 0, 80000, std::nullopt), 2000);
}

TEST(RoomOverrides, AWindowHoldsAnOverrideAndUnknownContactsNeverPause) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"boost"})", 0, monNoon), nullptr);
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"study","open":true,"delay_s":0})", p, 0));
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(1).mode, "window_open");
    EXPECT_EQ(o.view(1).kind, RoomOverrides::Kind::boost); // still visible, its time runs on
    // No refresh for 15 min: the contact is unknown and the boost applies again.
    o.step(p, 15 * minute, monNoon + 900, noLead);
    EXPECT_STREQ(o.view(1).mode, "boost");
    EXPECT_EQ(o.view(1).window, nullptr);
    // Reports for unknown rooms or with bad values are consumed and ignored.
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"attic","open":true})", p, 0));
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":1})", p, 0));
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":true,"delay_s":1801})", p, 0));
    o.step(p, 15 * minute, monNoon + 900, noLead);
    EXPECT_EQ(o.view(0).window, nullptr);
    // Other heating inputs are left to HeatingInput.
    EXPECT_FALSE(o.input(R"({"entity":"climate.living","temperature":20.5})", p, 0));
    EXPECT_FALSE(o.input(R"({"kind":"gas_m3","entity":"sensor.gas","value":1})", p, 0));
}

TEST(RoomOverrides, AwayLowersUntilItsDateAndWarmsUpInTimeForTheReturn) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomEngine e; e.setPlan(p);
    RoomOverrides o;
    const uint32_t back = monNoon + 86400; // Tuesday noon
    ASSERT_EQ(command(o, p, (R"({"away":true,"temperature":15,"until":)" + std::to_string(back) + "}").c_str(), 0, monNoon), nullptr);
    size_t asked = 0;
    const auto lead = [&](size_t room, uint32_t until, int16_t away, int16_t target) {
        ++asked;
        EXPECT_EQ(until, back); EXPECT_EQ(away, 1500);
        EXPECT_EQ(target, room == 0 ? 1800 : 2000); // living: Monday 22:30 holds on Tuesday; study: fallback
        return uint32_t(room == 0 ? 3600 : 10800);
    };
    o.step(p, 0, monNoon, lead);
    EXPECT_EQ(asked, 0u); // more than 8 h ahead: no warm-up yet
    EXPECT_STREQ(o.view(0).mode, "away");
    EXPECT_EQ(o.view(0).until, back);
    EXPECT_EQ(engineSetpoint(e, o, 0, 0, monNoon), 1500);
    EXPECT_STREQ(o.view(2).mode, "away"); // the inactive bath is reported too, but RoomEngine leaves it off
    // Three hours before: the floor room warms up, the radiator room not yet.
    o.step(p, minute, back - 10800, lead);
    EXPECT_GT(asked, 0u);
    EXPECT_STREQ(o.view(1).mode, "away_return");
    EXPECT_EQ(o.adjust()[1].setpoint, 2000);
    EXPECT_STREQ(o.view(0).mode, "away");
    o.step(p, 2 * minute, back - 3600, lead);
    EXPECT_STREQ(o.view(0).mode, "away_return");
    EXPECT_EQ(engineSetpoint(e, o, 0, 2 * minute, back - 3600), 1800);
    o.step(p, 3 * minute, back, lead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_FALSE(o.awayOn());
    // An override wins over away.
    ASSERT_EQ(command(o, p, R"({"away":true})", 0, back), nullptr);
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"timed","temperature":21,"minutes":60})", 0, back), nullptr);
    EXPECT_STREQ(o.view(0).mode, "timed");
    EXPECT_STREQ(o.view(1).mode, "away");
    EXPECT_EQ(o.view(1).until, 0u); // no end date
}

TEST(RoomOverrides, AwayIsKeptAcrossARestartAndADatedOneWaitsForTheClock) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"away":true,"temperature":16,"until":1793700000})", 0, monNoon), nullptr);
    const auto record = o.stored();
    EXPECT_EQ(record, R"({"v":1,"away_c":1600,"o":[],"away_until":1793700000})");
    RoomOverrides after;
    ASSERT_TRUE(after.restore(record));
    after.step(p, 0, std::nullopt, noLead);
    EXPECT_EQ(after.view(0).mode, nullptr); // without a clock: comfort, never a cold return
    EXPECT_TRUE(after.view(0).waiting);
    after.step(p, minute, monNoon, noLead);
    EXPECT_STREQ(after.view(0).mode, "away");
    EXPECT_EQ(after.adjust()[0].ceiling, 1600);
    // An open-ended away applies without a clock.
    ASSERT_EQ(command(after, p, R"({"away":true})", minute, monNoon), nullptr);
    RoomOverrides open;
    ASSERT_TRUE(open.restore(after.stored()));
    open.step(p, 0, std::nullopt, noLead);
    EXPECT_STREQ(open.view(1).mode, "away");
    bool persisted = false;
    ASSERT_EQ(command(open, p, R"({"away":false})", 0, std::nullopt, &persisted), nullptr);
    EXPECT_TRUE(persisted);
    EXPECT_EQ(open.view(1).mode, nullptr);
}

TEST(RoomOverrides, EveryoneAwayFromHomeAssistantPresence) {
    const auto p = plan();
    RoomOverrides o;
    EXPECT_TRUE(o.input(R"({"kind":"presence","home":false})", p, 0));
    o.step(p, 0, std::nullopt, noLead);
    EXPECT_STREQ(o.view(0).mode, "presence_away");
    EXPECT_EQ(o.adjust()[0].ceiling, 1500);
    // The plan's own lower target stays (away only ever lowers).
    RoomEngine e; e.setPlan(p);
    EXPECT_EQ(engineSetpoint(e, o, 1, 0, std::nullopt), 1500);
    EXPECT_TRUE(o.input(R"({"kind":"presence","home":true})", p, minute));
    o.step(p, minute, std::nullopt, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    // Unknown presence (no report for 15 min) is "home".
    EXPECT_TRUE(o.input(R"({"kind":"presence","home":false})", p, 2 * minute));
    o.step(p, 17 * minute, std::nullopt, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
}

TEST(RoomOverrides, StatusShowsTheReasonPerRoomAndTheHouseAway) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomEngine e; e.setPlan(p);
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"timed","temperature":21,"minutes":60})", 0, monNoon), nullptr);
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"study","open":true,"delay_s":0})", p, 0));
    o.step(p, 0, monNoon, noLead);
    e.step(0, monNoon, o.adjust());
    Json status(e.json(), cJSON_Delete);
    ASSERT_TRUE(o.addStatus(status.get(), p, 0));
    const cJSON* rooms = cJSON_GetObjectItem(status.get(), "rooms");
    const auto comfort = [&](int i) { return cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, i), "comfort"); };
    char* living = cJSON_PrintUnformatted(comfort(0));
    EXPECT_STREQ(living, R"({"mode":"timed","target_c":21,"until":1793620800,"override":"timed"})");
    cJSON_free(living);
    char* study = cJSON_PrintUnformatted(comfort(1));
    EXPECT_STREQ(study, R"({"mode":"window_open","window":"open","target_c":8})");
    cJSON_free(study);
    EXPECT_FALSE(comfort(2)); // following its plan: nothing added
    char* away = cJSON_PrintUnformatted(cJSON_GetObjectItem(status.get(), "away"));
    EXPECT_STREQ(away, R"({"on":false,"source":"none","target_c":15,"until":null,"presence":"unknown","mode":"auto"})");
    cJSON_free(away);
    Json api(o.json(p, 0), cJSON_Delete);
    ASSERT_TRUE(api);
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(api.get(), "rooms")), 3);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(api.get(), "rooms"), 2), "mode")), "program");
}

TEST(RoomOverrides, ReturnLeadUsesTheWarmupPlannersDefaultWhileNotLearned) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    FlowLearner l; l.setPlan(p);
    // 5 degC to gain: radiator 45 min per degC, at most 3 h; floor 2 h per degC, at most 6 h.
    EXPECT_EQ(RoomOverrides::returnLeadS(l, 0, monNoon + 86400, 1500, 2000, 1500, monNoon, std::nullopt), 10800u);
    EXPECT_EQ(RoomOverrides::returnLeadS(l, 1, monNoon + 86400, 1500, 2000, 1500, monNoon, std::nullopt), 21600u);
    EXPECT_EQ(RoomOverrides::returnLeadS(l, 1, monNoon + 86400, 1500, 1600, 1500, monNoon, std::nullopt), 7200u);
    EXPECT_EQ(RoomOverrides::returnLeadS(l, 1, monNoon + 86400, 1500, 1500, 1500, monNoon, std::nullopt), 0u);
    EXPECT_EQ(RoomOverrides::returnLeadS(l, 7, monNoon + 86400, 1500, 2000, 1500, monNoon, std::nullopt), 0u);
}

// The telemetry budget (TELEMETRIEBUDGET.nl.md): fw/state/room/<id> is at most 319 B for a
// worst-case plan and fw/state/heating 754 B; comfort adds at most 160 B and away 100 B.
TEST(RoomOverrides, StatusAdditionsStayWithinTheTelemetryBudget) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomEngine e; e.setPlan(p);
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"room":"living","override":"timed","temperature":21.25,"minutes":1440})", 0, monNoon), nullptr);
    ASSERT_EQ(command(o, p, R"({"away":true,"temperature":15.5,"until":1817000000})", 0, monNoon), nullptr);
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"living","open":true,"delay_s":0})", p, 0));
    EXPECT_TRUE(o.input(R"({"kind":"presence","home":false})", p, 0));
    o.step(p, 0, monNoon, noLead);
    Json status(e.json(), cJSON_Delete);
    ASSERT_TRUE(o.addStatus(status.get(), p, 0));
    const auto size = [](const cJSON* item) {
        char* text = cJSON_PrintUnformatted(item);
        const size_t n = std::strlen(text);
        cJSON_free(text);
        return n;
    };
    const cJSON* living = cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0), "comfort");
    ASSERT_TRUE(living);
    EXPECT_LE(size(living) + std::strlen(R"(,"comfort":)"), 160u);
    // 100 B until beta.21; beta.23 adds "mode" (at most ,"mode":"holiday", 17 B). fw/state/heating stays well below 1 KB.
    EXPECT_LE(size(cJSON_GetObjectItem(status.get(), "away")) + std::strlen(R"(,"away":)"), 117u);
    EXPECT_LE(o.stored().size(), RoomOverrides::storeBytes);
}

// Eight rooms, each with a stored override: the NVS record stays within its bound.
TEST(RoomOverrides, EightStoredOverridesFitTheRecord) {
    std::string text = R"({"v":1,"away_c":1500,"away_until":4102444000,"o":[)";
    for (int i = 0; i < 8; ++i)
        text += std::string(i ? "," : "") + R"({"id":")" + std::string(31, 'a') + char('0' + i) + R"(","k":"timed","c":2500,"u":4102444000})";
    text += "]}";
    RoomOverrides o;
    ASSERT_LE(text.size(), RoomOverrides::storeBytes);
    ASSERT_TRUE(o.restore(text));
    EXPECT_EQ(o.stored().size(), text.size());
}

TEST(RoomOverrides, HouseModeAutoHomeAwayAndHoliday) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    EXPECT_STREQ(o.houseMode(), "auto");
    // Home: "everyone away" from Home Assistant no longer lowers any room.
    bool persisted = false;
    ASSERT_EQ(command(o, p, R"({"house_mode":"home"})", 0, monNoon, &persisted), nullptr);
    EXPECT_TRUE(persisted);
    EXPECT_STREQ(o.houseMode(), "home");
    EXPECT_TRUE(o.input(R"({"kind":"presence","home":false})", p, 0));
    o.step(p, 0, monNoon, noLead);
    EXPECT_EQ(o.view(0).mode, nullptr);
    EXPECT_FALSE(o.adjust()[0].ceiling);
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON_AddArrayToObject(status.get(), "rooms");
    ASSERT_TRUE(o.addStatus(status.get(), p, 0));
    char* home = cJSON_PrintUnformatted(cJSON_GetObjectItem(status.get(), "away"));
    EXPECT_STREQ(home, R"({"on":false,"source":"none","target_c":15,"until":null,"presence":"away","mode":"home"})");
    cJSON_free(home);
    // Auto: presence decides again.
    ASSERT_EQ(command(o, p, R"({"house_mode":"auto","temperature":16})", 0, monNoon, &persisted), nullptr);
    EXPECT_TRUE(persisted);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(0).mode, "presence_away");
    EXPECT_EQ(o.adjust()[0].ceiling, 1600);
    // Away until switched back, then holiday with a date and a warm return.
    ASSERT_EQ(command(o, p, R"({"house_mode":"away"})", 0, monNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "away");
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(1).mode, "away");
    EXPECT_EQ(o.view(1).until, 0u);
    const uint32_t back = monNoon + 86400;
    ASSERT_EQ(command(o, p, (R"({"house_mode":"holiday","until":)" + std::to_string(back) + "}").c_str(), 0, monNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "holiday");
    o.step(p, minute, back - 3600, [](size_t, uint32_t, int16_t, int16_t) { return uint32_t(7200); });
    EXPECT_STREQ(o.view(1).mode, "away_return");  // warm again in time
    o.step(p, 2 * minute, back, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");           // the holiday ended by itself
    // Checked like the other commands.
    EXPECT_STREQ(command(o, p, R"({"house_mode":"party"})", 0, monNoon), "invalid_house_mode");
    EXPECT_STREQ(command(o, p, R"({"house_mode":"holiday"})", 0, monNoon), "invalid_until");
    EXPECT_STREQ(command(o, p, R"({"house_mode":"away","until":1793700000})", 0, monNoon), "invalid_until");
    EXPECT_STREQ(command(o, p, (R"({"house_mode":"holiday","until":)" + std::to_string(back) + "}").c_str(), 0, std::nullopt), "no_clock");
    EXPECT_STREQ(command(o, p, R"({"house_mode":"away","temperature":3})", 0, monNoon), "invalid_temperature");
    EXPECT_STREQ(command(o, p, R"({"house_mode":"auto","away":true})", 0, monNoon), "invalid_request");
    EXPECT_STREQ(command(o, p, R"({"house_mode":"auto","room":"living"})", 0, monNoon), "invalid_request");
    // The older away command still works and leaves home mode.
    ASSERT_EQ(command(o, p, R"({"house_mode":"home"})", 0, monNoon), nullptr);
    ASSERT_EQ(command(o, p, R"({"away":true})", 0, monNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "away");
    ASSERT_EQ(command(o, p, R"({"away":false})", 0, monNoon), nullptr);
    EXPECT_STREQ(o.houseMode(), "auto");
    // An unchanged mode writes nothing.
    ASSERT_EQ(command(o, p, R"({"house_mode":"auto"})", 0, monNoon, &persisted), nullptr);
    EXPECT_FALSE(persisted);
}

TEST(RoomOverrides, HouseModeSurvivesARestart) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan();
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"house_mode":"home","temperature":16.5})", 0, monNoon), nullptr);
    const auto record = o.stored();
    EXPECT_EQ(record, R"({"v":1,"away_c":1650,"o":[],"home":true})");
    RoomOverrides after;
    ASSERT_TRUE(after.restore(record));
    EXPECT_STREQ(after.houseMode(), "home");
    EXPECT_EQ(after.awayCentiC(), 1650);
    // A record claiming both home and away is not one this firmware wrote.
    EXPECT_FALSE(after.restore(R"({"v":1,"away_c":1500,"o":[],"away_until":0,"home":true})"));
    EXPECT_FALSE(after.restore(R"({"v":1,"away_c":1500,"o":[],"home":"yes"})"));
    EXPECT_TRUE(after.restore(R"({"v":1,"away_c":1500,"o":[],"home":false})"));
    EXPECT_STREQ(after.houseMode(), "auto");
}

// A rollback to E32 beta.21 must keep working with the record beta.23 wrote:
// beta.21 reads it (ignoring "home", so it runs auto), keeps away and holiday,
// and the room overrides; and beta.23 reads what beta.21 wrote.
TEST(RoomOverrides, Beta21ReadsTheHouseModeRecordAfterARollback) {
    ScopedTz tz(ScopedTz::amsterdam);
    using heating::control::RoomOverridesBeta21;
    const auto p = plan();
    const uint32_t back = monNoon + 86400;
    for (const std::string& body : {std::string(R"({"house_mode":"home","temperature":16})"), std::string(R"({"house_mode":"away"})"),
                                   R"({"house_mode":"holiday","until":)" + std::to_string(back) + "}",
                                   std::string(R"({"house_mode":"auto","temperature":17})")}) {
        RoomOverrides o;
        ASSERT_EQ(command(o, p, R"({"room":"living","override":"timed","temperature":21,"minutes":60})", 0, monNoon), nullptr);
        ASSERT_EQ(command(o, p, body.c_str(), 0, monNoon), nullptr) << body;
        const auto record = o.stored();
        RoomOverridesBeta21 old;
        ASSERT_TRUE(old.restore(record)) << record;
        EXPECT_EQ(old.awayCentiC(), o.awayCentiC()) << record;
        EXPECT_EQ(old.awayOn(), o.awayOn()) << record;      // home and auto: not away
        EXPECT_EQ(old.awayUntil(), o.awayUntil()) << record;
        old.step(p, 0, monNoon, noLead);
        EXPECT_STREQ(old.view(0).mode, "timed") << record;  // the override survives too
        // Back again: the newer firmware reads beta.21's own record.
        RoomOverrides again;
        ASSERT_TRUE(again.restore(old.stored())) << old.stored();
        EXPECT_STREQ(again.houseMode(), o.homeMode() ? "auto" : o.houseMode()) << record;
    }
}
