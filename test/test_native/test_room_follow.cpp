// Rooms that follow their own thermostat or radiator valve in Home Assistant (owner, 30 Oct 2026):
// the target only from that device; without HA the learned program, the last target or day/night.
#include "control/RoomOverrides.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>

namespace {
using heating::control::LearnedProgram;
using heating::control::RoomEngine;
using heating::control::RoomOverrides;
using heating::control::RoomPlan;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t minute = 60000, hour = 60 * minute;
constexpr uint32_t monNoon = 1793617200;    // Mon 2 Nov 2026 12:00 Amsterdam
constexpr uint32_t mon2230 = 1793655000;
constexpr uint32_t oct12 = 1791756000;      // Mon 12 Oct 2026 00:00 CEST; DST ends Sun 25 Oct
constexpr const char* tado = "climate.tado_woonkamer";
constexpr const char* tv02 = "climate.thermostaat_badkamer";

// The owner's house: Woonkamer follows the tado (setpoint entity, with a Bluetooth fallback sensor and
// an old week program), Badkamer only has the TV02 valve as its source, Slaapkamer only a sensor.
std::string planText(const std::string& extra = "") {
    return std::string(R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[
 {"id":"woonkamer","name":"Woonkamer","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ha","id":"climate.tado_woonkamer"},{"type":"ble","id":"a4c138a3e8db"}],
  "setpoint_entity":"climate.tado_woonkamer","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500,
  "schedule":[[[390,2200]],[],[],[],[],[],[]]},
 {"id":"badkamer","name":"Badkamer","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ha","id":"climate.thermostaat_badkamer"}],"setpoint_entity":"","fallback_centi_c":2000,
  "minimum_centi_c":500,"maximum_centi_c":2500)") + extra + R"(},
 {"id":"slaapkamer","name":"Slaapkamer","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000002"}],"setpoint_entity":"","fallback_centi_c":2000,
  "minimum_centi_c":500,"maximum_centi_c":2500}]})";
}
RoomPlan plan(const std::string& extra = "") {
    Json root(cJSON_Parse(planText(extra).c_str()), cJSON_Delete);
    RoomPlan p;
    EXPECT_EQ(RoomPlan::parse(root.get(), p), nullptr);
    return p;
}
const char* command(RoomOverrides& o, const RoomPlan& p, const char* body, uint64_t now, std::optional<uint32_t> utc) {
    Json root(cJSON_Parse(body), cJSON_Delete);
    bool persist = false;
    return o.command(root.get(), p, now, utc, persist);
}
const auto noLead = [](size_t, uint32_t, int16_t, int16_t) { return uint32_t(0); };

// One house step: HA reports (when given), then what the E32 does every 10 s.
struct House {
    RoomPlan plan;
    RoomEngine engine;
    RoomOverrides overrides;
    explicit House(RoomPlan p) : plan(std::move(p)) { engine.setPlan(plan); }
    void step(uint64_t now, std::optional<uint32_t> utc, std::optional<int16_t> tadoTarget = std::nullopt,
              std::optional<int16_t> tv02Target = std::nullopt) {
        if (tadoTarget) engine.haState(tado, 2000, tadoTarget, now);
        if (tv02Target) engine.haState(tv02, 1950, tv02Target, now);
        engine.bleReading("a4c138a3e8db", 2000, now);
        engine.bleReading("a4c138000002", 1900, now);
        overrides.noteTargets(plan, engine, now, utc);
        overrides.step(plan, now, utc, noLead);
        engine.step(now, utc, overrides.adjust());
    }
    std::optional<int16_t> setpoint(size_t room) const { return engine.result(room).setpoint; }
    const char* mode(size_t room) const { return overrides.view(room).mode; }
};
std::string str(const char* s) { return s ? s : "(none)"; }
}

TEST(RoomFollow, TheThermostatRoomsAreRecognisedFromThePlanAlone) {
    const auto p = plan();
    EXPECT_EQ(p.rooms[0].followedThermostat(), tado);   // its setpoint entity is a climate
    EXPECT_EQ(p.rooms[1].followedThermostat(), tv02);   // a climate source, no setpoint entity
    EXPECT_TRUE(p.rooms[2].followedThermostat().empty()); // sensors only: the E32's own program
    // The plan is stored unchanged: nothing about following is written.
    EXPECT_EQ(p.json().find("follow"), std::string::npos);
}

TEST(RoomFollow, WoonkamerAndBadkamerTakeTheirDevicesTargetAndNeverTheProgram) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan());
    h.step(0, monNoon, 1950, 2150);
    EXPECT_EQ(h.setpoint(0), 1950);  // the tado's, not the stored 22 degC program
    EXPECT_EQ(h.setpoint(1), 2150);  // the TV02's own target
    EXPECT_EQ(h.setpoint(2), 2000);  // the sensor-only room: its own target (day value)
    Json status(h.engine.json(), cJSON_Delete);
    const cJSON* rooms = cJSON_GetObjectItem(status.get(), "rooms");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, 0), "follows")), tado);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, 1), "follows")), tv02);
    EXPECT_FALSE(cJSON_GetObjectItem(cJSON_GetArrayItem(rooms, 2), "follows"));
    // Overrides are not offered for them; the sensor-only room still has them.
    EXPECT_STREQ(command(h.overrides, h.plan, R"({"room":"woonkamer","override":"boost"})", 0, monNoon), "room_follows_thermostat");
    EXPECT_STREQ(command(h.overrides, h.plan, R"({"room":"badkamer","override":"timed","temperature":21,"minutes":60})", 0, monNoon),
                 "room_follows_thermostat");
    EXPECT_EQ(command(h.overrides, h.plan, R"({"room":"slaapkamer","override":"boost"})", 0, monNoon), nullptr);
    // Away lowers the sensor-only room only; the devices keep their own targets.
    EXPECT_EQ(command(h.overrides, h.plan, R"({"away":true,"temperature":15})", 0, monNoon), nullptr);
    h.step(minute, monNoon + 60, 1950, 2150);
    EXPECT_EQ(h.setpoint(0), 1950);
    EXPECT_EQ(h.setpoint(1), 2150);
    EXPECT_TRUE(h.overrides.view(0).ignored);
    EXPECT_TRUE(h.overrides.holdsProgram(0)); // no optimum start towards the ignored program
}

TEST(RoomFollow, KeptDataIsIgnoredButNotDeletedAndTheWindowPauseStillWorks) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan());
    // An override from before the upgrade (stored when the room did not follow yet).
    ASSERT_TRUE(h.overrides.restore(R"({"v":1,"away_c":1500,"o":[{"id":"woonkamer","k":"timed","c":2400,"u":1793624400}]})"));
    h.step(0, monNoon, 1950);
    EXPECT_EQ(h.setpoint(0), 1950);
    EXPECT_TRUE(h.overrides.view(0).ignored);
    EXPECT_NE(h.overrides.stored().find(R"("id":"woonkamer","k":"timed")"), std::string::npos); // kept
    Json status(h.engine.json(), cJSON_Delete);
    ASSERT_TRUE(h.overrides.addStatus(status.get(), h.plan, 0));
    char* comfort = cJSON_PrintUnformatted(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0), "comfort"));
    EXPECT_STREQ(comfort, R"({"mode":"follows","until":1793624400,"override":"timed","ignored":true})");
    cJSON_free(comfort);
    EXPECT_TRUE(h.overrides.input(R"({"kind":"contact","room":"woonkamer","open":true,"delay_s":0})", h.plan, minute));
    h.step(minute, monNoon + 60, 1950);
    EXPECT_STREQ(h.mode(0), "window_open");
    EXPECT_EQ(h.setpoint(0), 800); // the frost floor
}

TEST(RoomFollow, WithoutHomeAssistantTheLastTargetHoldsSixHoursAlsoAcrossARestartThenDayNight) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan());
    for (uint64_t m = 0; m <= 60; m += 5) h.step(m * minute, monNoon + uint32_t(m * 60), 2100);
    EXPECT_EQ(h.setpoint(0), 2100);
    EXPECT_EQ(h.mode(0), nullptr);
    EXPECT_TRUE(h.overrides.takeDirty()); // the held target is kept in NVS ...
    EXPECT_FALSE(h.overrides.takeDirty()); // ... once, not every report
    // HA goes away at 13:00: 15 min later the target is stale and is held.
    h.step(76 * minute, monNoon + 76 * 60);
    EXPECT_STREQ(h.mode(0), "holding");
    EXPECT_EQ(h.setpoint(0), 2100);
    EXPECT_EQ(h.overrides.view(0).until, monNoon + 3600 + RoomOverrides::holdS);
    // The E32 restarts at 15:00 (HA still away): without a clock first the day value, then the hold.
    const auto record = h.overrides.stored();
    House after(plan());
    ASSERT_TRUE(after.overrides.restore(record));
    after.step(0, std::nullopt);
    EXPECT_EQ(after.setpoint(0), 2000); // conservative: the day/night value without a clock (here: day value)
    after.step(minute, monNoon + 3 * 3600);
    EXPECT_STREQ(after.mode(0), "holding");
    EXPECT_EQ(after.setpoint(0), 2100);
    // Six hours after the last report (19:00): "temperature without Home Assistant", by day then by night.
    after.step(4 * hour + minute, monNoon + 7 * 3600 + 60);
    EXPECT_STREQ(after.mode(0), "without_ha");
    EXPECT_EQ(after.setpoint(0), 2000);
    after.step(11 * hour, mon2230 + 60);
    EXPECT_EQ(after.setpoint(0), 1700);
    // Home Assistant is back: the tado leads at once.
    after.step(11 * hour + minute, mon2230 + 120, 1800);
    EXPECT_EQ(after.mode(0), nullptr);
    EXPECT_EQ(after.setpoint(0), 1800);
}

TEST(RoomFollow, AManualTargetOnlyWhileHomeAssistantIsAwayAndOnlyUntilItIsBack) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan());
    h.step(0, monNoon, 2100, 2150);
    EXPECT_STREQ(command(h.overrides, h.plan, R"({"room":"woonkamer","override":"offline","temperature":22})", 0, monNoon),
                 "room_follows_thermostat"); // HA is there: change it on the thermostat
    EXPECT_STREQ(command(h.overrides, h.plan, R"({"room":"slaapkamer","override":"offline","temperature":22})", 0, monNoon),
                 "invalid_override");
    h.step(20 * minute, monNoon + 1200);
    EXPECT_EQ(command(h.overrides, h.plan, R"({"room":"woonkamer","override":"offline","temperature":22})", 20 * minute, monNoon + 1200), nullptr);
    h.step(21 * minute, monNoon + 1260);
    EXPECT_STREQ(h.mode(0), "offline");
    EXPECT_EQ(h.setpoint(0), 2200);
    EXPECT_EQ(h.overrides.view(0).until, mon2230); // at most until the next day/night switch
    h.step(30 * minute, monNoon + 1800, 2100);     // the tado is back
    EXPECT_EQ(h.mode(0), nullptr);
    EXPECT_EQ(h.setpoint(0), 2100);
    EXPECT_EQ(h.overrides.view(0).kind, RoomOverrides::Kind::none); // ended, not just hidden
    // Not back: it ends at the day/night switch.
    h.step(50 * minute, monNoon + 3000);
    ASSERT_EQ(command(h.overrides, h.plan, R"({"room":"badkamer","override":"offline","temperature":19})", 50 * minute, monNoon + 3000), nullptr);
    h.step(51 * minute, monNoon + 3060);
    EXPECT_EQ(h.setpoint(1), 1900);
    h.step(10 * hour + 31 * minute, mon2230);
    EXPECT_NE(str(h.mode(1)), "offline");
}

TEST(RoomFollow, TemperatureWithoutHomeAssistantIsDayAndNightAndRoundTrips) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = plan(R"(,"fallback_night":[420,1320,1600])");
    EXPECT_EQ(p.rooms[1].fallbackAt(419), 1600);
    EXPECT_EQ(p.rooms[1].fallbackAt(420), 2000);
    EXPECT_EQ(p.rooms[1].fallbackAt(1320), 1600);
    EXPECT_NE(p.json().find(R"("fallback_night":[420,1320,1600])"), std::string::npos);
    EXPECT_EQ(plan().json().find("fallback_night"), std::string::npos); // the default is not written
    // A night that wraps (day from 22:00 to 06:00, e.g. a night worker).
    const auto w = plan(R"(,"fallback_night":[1320,360,1700])");
    EXPECT_EQ(w.rooms[1].fallbackAt(1400), 2000);
    EXPECT_EQ(w.rooms[1].fallbackAt(600), 1700);
    for (const char* bad : {R"(,"fallback_night":[420,420,1600])", R"(,"fallback_night":[420,1320,3000])",
                            R"(,"fallback_night":[1440,1320,1600])", R"(,"fallback_night":[420,1320])"}) {
        Json root(cJSON_Parse(planText(bad).c_str()), cJSON_Delete);
        RoomPlan out;
        EXPECT_STREQ(RoomPlan::parse(root.get(), out), "invalid_fallback_night") << bad;
    }
    // A sensor-only room without a program uses it too (it replaces the single fixed value).
    House h(plan());
    h.step(0, mon2230 + 60);
    EXPECT_EQ(h.setpoint(2), 1700);
    h.step(minute, std::nullopt);
    EXPECT_EQ(h.setpoint(2), 2000); // no clock: the day value, as before
}

// The realistic 8-room home of the compact-plan test (each room: HA thermometer, Bluetooth sensor,
// climate target, 4 switch points a day), now every room with its own day/night values too.
TEST(RoomFollow, EightFullRoomsWithDayNightStillFitTheStore) {
    using heating::control::RoomDemand;
    using heating::control::RoomSchedule;
    const char* ids[] = {"woonkamer", "keuken", "badkamer", "slaapkamer", "kinderkamer", "logeerkamer", "werkkamer", "zolder"};
    RoomPlan p;
    p.revision = 12;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = ids[i]; r.name = std::string(ids[i]).substr(0, 1) == "w" ? "Woonkamer" : ids[i];
        r.state = RoomDemand::State::active;
        r.sources = {{RoomPlan::SourceType::ha, std::string("sensor.") + ids[i] + "_temperature"},
                     {RoomPlan::SourceType::ble, "a4c13800000" + std::to_string(i)}};
        r.setpointEntity = std::string("climate.") + ids[i];
        r.dayFromMinute = 1435; r.nightFromMinute = 1439; r.nightCentiC = 2500; // the longest form
        const RoomSchedule::Point weekday[] = {{390, 2050}, {480, 1800}, {1020, 2100}, {1350, 1700}};
        for (int d = 0; d < 7; ++d) for (const auto& point : weekday) r.schedule.days[d].points[r.schedule.days[d].count++] = point;
        p.rooms.push_back(r);
    }
    const auto stored = p.storedJson();
    printf("[ room plan ] 8 rooms x 4 points with day/night: stored form %zu B (store %zu B incl. NUL)
", stored.size(), RoomPlan::storeBytes);
    EXPECT_LT(stored.size() + 1, RoomPlan::storeBytes);
    Json back(cJSON_Parse(stored.c_str()), cJSON_Delete);
    RoomPlan reread;
    ASSERT_EQ(RoomPlan::parse(back.get(), reread), nullptr);
    EXPECT_EQ(reread.rooms[7].nightCentiC, 2500);
    EXPECT_EQ(reread.rooms[7].schedule.days[6].count, 4);
}

// --- the learned week program ------------------------------------------------------------------

namespace {
// The tado's own program over two weeks from Mon 12 Oct: workdays 06:30 21, 08:30 18, 17:00 21,
// 22:30 17; weekend 08:00 21, 23:00 17. From Wednesday of week 2 workdays start at 07:00.
// A 5-minute blip (somebody touched it) on Tuesday of week 2 is not part of it.
int16_t tadoProgram(uint32_t utc) {
    const auto t = heating::control::RoomSchedule::localAt(utc);
    const bool week2 = utc >= oct12 + 7 * 86400;
    const bool changed = week2 && utc >= oct12 + 9 * 86400; // Wed 21 Oct 00:00 (CEST: no DST in between)
    if (week2 && t.weekday == 1 && t.minute >= 600 && t.minute < 605) return 2350;
    if (t.weekday >= 5) return t.minute >= 480 && t.minute < 1380 ? 2100 : 1700;
    const uint16_t morning = changed ? 420 : 390;
    if (t.minute >= morning && t.minute < 510) return 2100;
    if (t.minute >= 1020 && t.minute < 1350) return 2100;
    return t.minute >= 510 && t.minute < 1020 ? 1800 : 1700;
}
}

TEST(RoomFollow, TheThermostatsProgramIsLearnedFromTwoWeeksIncludingDstAndAChange) {
    ScopedTz tz(ScopedTz::amsterdam);
    LearnedProgram l;
    int writes = 0, lastWriteDay = -1;
    uint64_t now = 0;
    for (uint32_t utc = oct12; utc <= oct12 + 14 * 86400 + 3600 + 60; utc += 60, now += minute) {
        l.observe("woonkamer", tadoProgram(utc), now, utc);
        if (l.takeDirty()) {
            ++writes;
            const int day = heating::control::RoomSchedule::localDay(utc);
            EXPECT_NE(day, lastWriteDay) << "at most one write a day";
            lastWriteDay = day;
        }
    }
    EXPECT_EQ(writes, 14);
    const auto at = [&](uint32_t utc) { return l.at("woonkamer", utc).value_or(-1); };
    // Monday (learned 19 Oct, before the change): 06:30.
    EXPECT_EQ(at(1792991700), 1700); // Mon 26 Oct 06:15 (CET, after the DST change)
    EXPECT_EQ(at(1792994400), 2100); // Mon 07:00
    // Wednesday (learned 21 Oct, after the change): 07:00, not 06:30.
    EXPECT_EQ(at(1793166300), 1700); // Wed 28 Oct 06:45
    EXPECT_EQ(at(1793167200), 2100); // Wed 07:00
    // Tuesday's 5-minute blip is not part of it; its points are the program's.
    const auto* days = l.days("woonkamer");
    ASSERT_TRUE(days);
    const auto& tue = days[1];
    ASSERT_EQ(tue.count, 5);
    EXPECT_EQ(tue.points[1].minute, 390); EXPECT_EQ(tue.points[1].centiC, 2100);
    EXPECT_EQ(tue.points[4].minute, 1350); EXPECT_EQ(tue.points[4].centiC, 1700);
    // Sunday 25 Oct had 25 hours (DST ended): learned at local time all the same.
    const auto& sun = days[6];
    ASSERT_EQ(sun.count, 3);
    EXPECT_EQ(sun.points[1].minute, 480); EXPECT_EQ(sun.points[2].minute, 1380);
    // Stored compactly and read back the same.
    const auto record = l.stored();
    printf("[ learned ] one room, 7 days: %zu B\n", record.size());
    LearnedProgram back;
    ASSERT_TRUE(back.restore(record));
    EXPECT_EQ(back.stored(), record);
    EXPECT_EQ(back.at("woonkamer", 1793167200), 2100);
}

TEST(RoomFollow, AnIncompleteDayOrADayWithTooManyChangesIsNotLearned) {
    ScopedTz tz(ScopedTz::amsterdam);
    LearnedProgram l;
    uint64_t now = 0;
    // Monday: HA away for an hour at noon. Tuesday: 10 changes. Wednesday: whole and normal.
    for (uint32_t utc = oct12; utc < oct12 + 3 * 86400 + 60; utc += 60, now += minute) {
        const auto t = heating::control::RoomSchedule::localAt(utc);
        std::optional<int16_t> target = tadoProgram(utc);
        if (t.weekday == 0 && t.minute >= 720 && t.minute < 780) target.reset();
        if (t.weekday == 1) target = int16_t(1700 + 100 * ((t.minute / 120) % 2));
        l.observe("woonkamer", target, now, utc);
    }
    EXPECT_FALSE(l.at("woonkamer", oct12 + 7 * 86400 + 43200)); // Monday
    EXPECT_FALSE(l.at("woonkamer", oct12 + 8 * 86400 + 43200)); // Tuesday
    EXPECT_TRUE(l.at("woonkamer", oct12 + 9 * 86400 + 43200));  // Wednesday
}

TEST(RoomFollow, EightRoomsOfLearnedProgramsStayWithinTheirRecord) {
    std::string w;
    for (int d = 0; d < 7; ++d) { if (d) w += '.'; w += "BBB"; for (int i = 0; i < 8; ++i) w += std::string("A") + char('A' + i * 3) + char('k' + i); }
    std::string text = R"({"v":1,"r":[)";
    for (int r = 0; r < 8; ++r) text += std::string(r ? "," : "") + R"({"id":")" + std::string(31, 'a') + char('0' + r) + R"(","w":")" + w + R"("})";
    text += "]}";
    printf("[ learned ] 8 rooms x 7 days x 8 points: %zu B (bound %zu B)\n", text.size(), LearnedProgram::storeBytes);
    ASSERT_LE(text.size(), LearnedProgram::storeBytes);
    LearnedProgram l;
    ASSERT_TRUE(l.restore(text));
    EXPECT_EQ(l.stored(), text);
    for (const char* bad : {R"({"v":1,"r":[{"id":"x","w":"BBBAAk"}]})", R"({"v":2,"r":[]})", R"({"v":1,"r":[{"id":"x","w":"*"}]})"})
        EXPECT_FALSE(l.restore(bad)) << bad;
}

TEST(RoomFollow, DuringAnOutageTheLearnedProgramIsReplayedAlsoAfterARestartElseDayNight) {
    ScopedTz tz(ScopedTz::amsterdam);
    House h(plan());
    uint64_t now = 0;
    uint32_t utc = oct12;
    // Eight days of the tado's program with HA there: Monday..Monday learned (Tuesday 13 Oct too).
    for (; utc < oct12 + 8 * 86400 + 60; utc += 60, now += minute) h.step(now, utc, tadoProgram(utc));
    EXPECT_EQ(h.setpoint(0), 1700);
    // HA goes away on Tuesday 20 Oct at 06:00: from 06:15 the learned Tuesday (06:30 21 degC) runs.
    const uint32_t outage = oct12 + 8 * 86400 + 6 * 3600;
    for (; utc <= outage; utc += 60, now += minute) h.step(now, utc, tadoProgram(utc));
    for (; utc < outage + 45 * 60; utc += 60, now += minute) h.step(now, utc);
    EXPECT_STREQ(h.mode(0), "learned");
    EXPECT_EQ(h.setpoint(0), 2100);
    // The E32 restarts at 07:00: the learned program is read back from its own record.
    House after(plan());
    ASSERT_TRUE(after.overrides.restore(h.overrides.stored()));
    ASSERT_TRUE(after.overrides.learned().restore(h.overrides.learned().stored()));
    after.step(0, outage + 3 * 3600); // 09:00 Tuesday
    EXPECT_STREQ(after.mode(0), "learned");
    EXPECT_EQ(after.setpoint(0), 1800);
    // A weekday that was never learned (Badkamer's TV02 never reported): day/night.
    EXPECT_STREQ(after.mode(1), "without_ha");
    EXPECT_EQ(after.setpoint(1), 2000);
    // HA back: the tado leads again.
    after.step(minute, outage + 3 * 3600 + 60, 1900);
    EXPECT_EQ(after.mode(0), nullptr);
    EXPECT_EQ(after.setpoint(0), 1900);
}
