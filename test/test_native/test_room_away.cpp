// Away temperature per room ("plan.room_away.v1", after 1.0.0-rc.2): the owner's rules of 3 Nov 2026.
//  1. everyone away, house mode away or holiday: every room the house away temperature;
//  2. a room whose own persons are all away while others are home: the room's own away temperature;
//  3. a room without persons of its own follows the house;
//  4. a room with persons but without its own value: the house value;
//  5. away is a ceiling (a cooler program stays cooler), the warm-up before a holiday's end and the
//     window pause keep working;
//  6. house mode home ignores presence.
// Also the plan field itself: the API and packed stored forms, the store and request bounds, a rollback
// to rc.2 and beta.21 (frozen parsers) and the settings backup.
#include "control/ConfigBackup.h"
#include "control/RoomOverrides.h"
#include "RoomPlanBeta21.h"
#include "RoomPlanRc2.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>

namespace {
using heating::control::ControlPartitionBudget;
using heating::control::RoomDemand;
using heating::control::RoomEngine;
using heating::control::RoomOverrides;
using heating::control::RoomPlan;
using heating::control::RoomPlanBeta21;
using heating::control::RoomPlanRc2;
using heating::control::RoomSchedule;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
namespace b = heating::control::backup;
constexpr uint64_t minute = 60000;
constexpr uint32_t monNoon = 1793617200;   // Mon 2 Nov 2026 12:00 Amsterdam (CET)

// The owner's example house: a living room without persons of its own (its own value is never used,
// rule 3), Jolien's study with its own 16 degC, a bedroom for two without its own value, and a guest
// room whose fixed target (15 degC) is already below its own away value (18 degC).
const std::string houseText = R"({"schema":1,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[
 {"id":"living","name":"Living room","state":"active","inactive_until":0,"emitter":"floor",
  "sources":[{"type":"ble","id":"a4c138000001"}],"setpoint_entity":"","fallback_centi_c":2100,
  "minimum_centi_c":500,"maximum_centi_c":2500,"away_centi_c":1900},
 {"id":"study","name":"Study","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000002"}],"setpoint_entity":"","fallback_centi_c":2000,
  "minimum_centi_c":500,"maximum_centi_c":2500,"away_centi_c":1600},
 {"id":"bedroom","name":"Bedroom","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000003"}],"setpoint_entity":"","fallback_centi_c":1900,
  "minimum_centi_c":500,"maximum_centi_c":2500},
 {"id":"guest","name":"Guest room","state":"active","inactive_until":0,"emitter":"radiator",
  "sources":[{"type":"ble","id":"a4c138000004"}],"setpoint_entity":"","fallback_centi_c":1500,
  "minimum_centi_c":500,"maximum_centi_c":2500,"away_centi_c":1800}]})";
enum : size_t { living, study, bedroom, guest };

RoomPlan parsed(const std::string& text) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    RoomPlan plan;
    EXPECT_EQ(RoomPlan::parse(root.get(), plan), nullptr) << text;
    return plan;
}
const char* parseError(const std::string& text) {
    Json root(cJSON_Parse(text.c_str()), cJSON_Delete);
    RoomPlan plan;
    return RoomPlan::parse(root.get(), plan);
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const auto at = text.find(from);
    EXPECT_NE(at, std::string::npos) << from;
    return at == std::string::npos ? text : text.replace(at, from.size(), to);
}
const char* command(RoomOverrides& o, const RoomPlan& p, const std::string& body, std::optional<uint32_t> utc = monNoon) {
    Json root(cJSON_Parse(body.c_str()), cJSON_Delete);
    bool persist = false;
    return o.command(root.get(), p, 0, utc, persist);
}
void house(RoomOverrides& o, const RoomPlan& p, bool home, uint64_t now = 0) {
    EXPECT_TRUE(o.input(std::string(R"({"kind":"presence","home":)") + (home ? "true" : "false") + "}", p, now));
}
void persons(RoomOverrides& o, const RoomPlan& p, const char* room, bool home, uint64_t now = 0) {
    EXPECT_TRUE(o.input(std::string(R"({"kind":"room_presence","room":")") + room + R"(","home":)" + (home ? "true" : "false") + "}", p, now));
}
const auto noLead = [](size_t, uint32_t, int16_t, int16_t) { return uint32_t(0); };
// The setpoint RoomEngine reports for each room after one step with the adjustments (every room at 19 degC).
std::optional<int16_t> setpoint(const RoomPlan& p, const RoomOverrides& o, size_t room, uint64_t now = 0, std::optional<uint32_t> utc = monNoon) {
    RoomEngine e; e.setPlan(p);
    for (const char* id : {"a4c138000001", "a4c138000002", "a4c138000003", "a4c138000004"}) e.bleReading(id, 1900, now);
    e.step(now, utc, o.adjust());
    return e.result(room).setpoint;
}
std::string comfortJson(const RoomOverrides& o, const RoomPlan& p, const char* id) {
    Json status(cJSON_CreateObject(), cJSON_Delete);
    cJSON* rooms = cJSON_AddArrayToObject(status.get(), "rooms");
    cJSON* r = cJSON_CreateObject(); cJSON_AddStringToObject(r, "id", id); cJSON_AddItemToArray(rooms, r);
    EXPECT_TRUE(o.addStatus(status.get(), p, 0));
    const cJSON* c = cJSON_GetObjectItem(r, "comfort");
    if (!c) return "";
    char* text = cJSON_PrintUnformatted(c);
    std::string out = text;
    cJSON_free(text);
    return out;
}
}

// Rule 2: "Jolien's study: Jolien is out, Mark is home -> study 16 degC, living room stays 21 degC".
TEST(RoomAway, TheRoomsOwnPersonsAwayUseItsOwnValueWhileOthersAreHome) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    ASSERT_EQ(p.rooms[study].awayCentiC, 1600);
    RoomOverrides o;
    house(o, p, true);
    persons(o, p, "study", false);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(study).mode, "presence_away");
    EXPECT_STREQ(o.view(study).awayBy, "room");
    EXPECT_EQ(o.view(study).targetCentiC, 1600);
    EXPECT_EQ(o.adjust()[study].ceiling, 1600);
    EXPECT_EQ(setpoint(p, o, study), 1600);
    EXPECT_TRUE(o.holdsProgram(study));
    // The living room (no persons of its own) and the others stay warm.
    for (size_t room : {size_t(living), size_t(bedroom), size_t(guest)}) {
        EXPECT_EQ(o.view(room).mode, nullptr) << room;
        EXPECT_FALSE(o.adjust()[room].ceiling) << room;
    }
    EXPECT_EQ(setpoint(p, o, living), 2100);
    EXPECT_EQ(comfortJson(o, p, "study"), R"({"mode":"presence_away","persons":"away","away_by":"room","target_c":16})");
    // Jolien is back: the study follows its program again at once (presence has no known end, so no lead).
    persons(o, p, "study", true, minute);
    o.step(p, minute, monNoon + 60, noLead);
    EXPECT_EQ(o.view(study).mode, nullptr);
    EXPECT_EQ(o.view(study).awayBy, nullptr);
    EXPECT_EQ(setpoint(p, o, study, minute), 2000);
}

// Rule 2 with two persons: HA reports the room home while one of them is home (test_room_away.py
// checks that aggregation); the E32 keeps such a room warm and lowers it only on "away".
TEST(RoomAway, ARoomForTwoGoesAwayOnlyWhenBothAreOut) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    house(o, p, true);
    persons(o, p, "bedroom", true);    // one of the two is still home
    o.step(p, 0, monNoon, noLead);
    EXPECT_EQ(o.view(bedroom).mode, nullptr);
    EXPECT_STREQ(o.view(bedroom).persons, "home");
    persons(o, p, "bedroom", false, minute);   // both out
    o.step(p, minute, monNoon + 60, noLead);
    EXPECT_STREQ(o.view(bedroom).mode, "presence_away");
    // Rule 4: no own value, so the house away temperature (15 degC by default).
    EXPECT_EQ(o.view(bedroom).targetCentiC, RoomOverrides::defaultAwayCentiC);
    EXPECT_STREQ(o.view(bedroom).awayBy, "room");
    EXPECT_EQ(setpoint(p, o, bedroom, minute), 1500);
}

// Rule 1: "both out -> every room the house value 17 degC", also the rooms with their own value.
TEST(RoomAway, EveryoneAwayUsesTheHouseValueForEveryRoom) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"house_mode":"auto","temperature":17})"), nullptr);
    persons(o, p, "study", false);
    persons(o, p, "bedroom", false);
    house(o, p, false);
    o.step(p, 0, monNoon, noLead);
    for (size_t room : {size_t(living), size_t(study), size_t(bedroom)}) {
        EXPECT_STREQ(o.view(room).mode, "presence_away") << room;
        EXPECT_STREQ(o.view(room).awayBy, "house") << room;
        EXPECT_EQ(o.view(room).targetCentiC, 1700) << room;
        EXPECT_EQ(setpoint(p, o, room), 1700) << room;
    }
    EXPECT_EQ(comfortJson(o, p, "study"), R"({"mode":"presence_away","persons":"away","away_by":"house","target_c":17})");
    EXPECT_EQ(comfortJson(o, p, "living"), R"({"mode":"presence_away","away_by":"house","target_c":17})");
    // Mark comes home: the house is no longer away, Jolien's study goes back to its own 16 degC.
    house(o, p, true, minute);
    o.step(p, minute, monNoon + 60, noLead);
    EXPECT_EQ(o.view(living).mode, nullptr);
    EXPECT_EQ(o.view(study).targetCentiC, 1600);
    EXPECT_STREQ(o.view(study).awayBy, "room");
}

// Rule 3: a room without persons of its own follows the house; its own value is never used.
TEST(RoomAway, ARoomWithoutPersonsFollowsTheHouse) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    house(o, p, true);
    o.step(p, 0, monNoon, noLead);
    EXPECT_EQ(o.view(living).mode, nullptr);
    house(o, p, false);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(living).mode, "presence_away");
    EXPECT_EQ(o.view(living).targetCentiC, 1500);   // the house value, not its own 19 degC
    EXPECT_STREQ(o.view(living).awayBy, "house");
    // Without any report (HA offline) presence is "home": nothing is lowered.
    RoomOverrides fresh;
    fresh.step(p, 0, monNoon, noLead);
    for (size_t room = 0; room < p.rooms.size(); ++room) EXPECT_EQ(fresh.view(room).mode, nullptr) << room;
}

// Rule 5: a ceiling. The guest room's fixed 15 degC stays 15 with its own away value of 18 degC.
TEST(RoomAway, ACoolerProgramStaysCooler) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    house(o, p, true);
    persons(o, p, "guest", false);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(guest).mode, "presence_away");
    EXPECT_EQ(o.adjust()[guest].ceiling, 1800);
    EXPECT_FALSE(o.adjust()[guest].setpoint);       // never raises the target
    EXPECT_EQ(setpoint(p, o, guest), 1500);
}

// Rule 6: "At home" ignores presence, also a room's own persons and its own value.
TEST(RoomAway, AtHomeIgnoresPresence) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    ASSERT_EQ(command(o, p, R"({"house_mode":"home"})"), nullptr);
    persons(o, p, "study", false);
    house(o, p, false);
    o.step(p, 0, monNoon, noLead);
    for (size_t room = 0; room < p.rooms.size(); ++room) {
        EXPECT_EQ(o.view(room).mode, nullptr) << room;
        EXPECT_FALSE(o.adjust()[room].ceiling) << room;
    }
    EXPECT_EQ(setpoint(p, o, study), 2000);
}

// Rule 1 for the house modes: Away and Holiday use the house value, also in a room with its own value;
// the warm-up before the holiday's end starts from that value and brings the room back in time.
TEST(RoomAway, AwayAndHolidayUseTheHouseValueAndWarmUpInTime) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    house(o, p, true);
    persons(o, p, "study", false);
    ASSERT_EQ(command(o, p, R"({"house_mode":"away","temperature":14})"), nullptr);
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(study).mode, "away");
    EXPECT_EQ(o.view(study).targetCentiC, 1400);
    EXPECT_EQ(o.view(study).awayBy, nullptr);
    EXPECT_EQ(setpoint(p, o, study), 1400);
    const uint32_t back = monNoon + 86400;
    ASSERT_EQ(command(o, p, R"({"house_mode":"holiday","until":)" + std::to_string(back) + "}"), nullptr);
    size_t asked = 0;
    const auto lead = [&](size_t room, uint32_t until, int16_t away, int16_t target) {
        ++asked;
        EXPECT_EQ(until, back);
        EXPECT_EQ(away, 1400);   // the house value, also for the study with its own 16 degC
        EXPECT_EQ(target, p.rooms[room].fallbackCentiC);
        return uint32_t(room == study ? 7200 : 0);
    };
    o.step(p, minute, back - 3600, lead);
    EXPECT_GT(asked, 0u);
    EXPECT_STREQ(o.view(study).mode, "away_return");   // warm again in time
    EXPECT_EQ(setpoint(p, o, study, minute, back - 3600), 2000);
    EXPECT_STREQ(o.view(bedroom).mode, "away");
    // The holiday ends; the study's persons are still out (and the house home): its own value again.
    persons(o, p, "study", false, 2 * minute);
    o.step(p, 2 * minute, back, noLead);
    EXPECT_STREQ(o.houseMode(), "auto");
    EXPECT_STREQ(o.view(study).mode, "presence_away");
    EXPECT_EQ(o.view(study).targetCentiC, 1600);
}

// Rule 5: an open window keeps priority over the room's own away; frost protection is its floor.
TEST(RoomAway, AnOpenWindowStillPausesTheRoom) {
    ScopedTz tz(ScopedTz::amsterdam);
    const auto p = parsed(houseText);
    RoomOverrides o;
    house(o, p, true);
    persons(o, p, "study", false);
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"study","open":true,"delay_s":0})", p, 0));
    o.step(p, 0, monNoon, noLead);
    EXPECT_STREQ(o.view(study).mode, "window_open");
    EXPECT_TRUE(o.adjust()[study].pause);
    EXPECT_EQ(o.adjust()[study].setpoint, RoomOverrides::frostCentiC);
    // Closed again: its own away value.
    EXPECT_TRUE(o.input(R"({"kind":"contact","room":"study","open":false})", p, minute));
    o.step(p, minute, monNoon + 60, noLead);
    EXPECT_STREQ(o.view(study).mode, "presence_away");
    EXPECT_EQ(o.adjust()[study].ceiling, 1600);
    // An override wins too (it is the owner's own choice for the room).
    ASSERT_EQ(command(o, p, R"({"room":"study","override":"timed","temperature":21,"minutes":60})"), nullptr);
    EXPECT_STREQ(o.view(study).mode, "timed");
}

// The plan field: API form, packed stored form, documents, bounds and the checks.
TEST(RoomAway, ThePlanFieldInEveryForm) {
    const auto p = parsed(houseText);
    EXPECT_FALSE(p.rooms[bedroom].awayCentiC);
    const auto api = p.json();
    EXPECT_NE(api.find(R"("features":["plan.levels.v1","plan.room_away.v1"])"), std::string::npos);
    EXPECT_NE(api.find(R"("maximum_centi_c":2500,"away_centi_c":1600)"), std::string::npos);
    EXPECT_EQ(api.find("away_centi_c", api.find(R"("id":"bedroom")")), api.find("away_centi_c", api.find(R"("id":"guest")")));
    EXPECT_EQ(parsed(api).json(), api);
    // A backup document carries the value, never what the firmware can.
    const auto doc = p.documentJson();
    EXPECT_EQ(doc.find("features"), std::string::npos);
    EXPECT_NE(doc.find(R"("away_centi_c":1600)"), std::string::npos);
    EXPECT_EQ(parsed(doc).json(), api);
    // A small plan is stored in the API form; a large one packs it as "aw".
    EXPECT_EQ(p.storedJson(), doc);
    // Range 5..25 degC, whole centi degC, a number; never both forms at once.
    const std::string own = R"("away_centi_c":1600)";
    EXPECT_EQ(parseError(replaced(houseText, own, R"("away_centi_c":500)")), nullptr);
    EXPECT_EQ(parseError(replaced(houseText, own, R"("away_centi_c":2500)")), nullptr);
    EXPECT_EQ(parseError(replaced(houseText, own, R"("aw":1600)")), nullptr);
    for (const char* bad : {R"("away_centi_c":499)", R"("away_centi_c":2501)", R"("away_centi_c":1600.5)", R"("away_centi_c":"1600")",
                            R"("away_centi_c":null)", R"("away_centi_c":1600,"aw":1600)", R"("aw":true)"})
        EXPECT_STREQ(parseError(replaced(houseText, own, bad)), "invalid_room_away") << bad;
    // The comfort record (NVS "comfort") does not change: the value lives in the plan only.
    RoomOverrides o;
    EXPECT_EQ(o.stored(), RoomOverrides{}.stored());
}

// 8 rooms of 4 switch points a day with levels AND their own away value: the packed stored form still
// fits the store (with room for an edit), the API form fits the request bound, and rc.2 and beta.21
// read both forms after a rollback with the same rooms and programs (the value is simply absent there).
TEST(RoomAway, EightRoomsWithOwnValuesFitAndRollBackToRc2AndBeta21) {
    const char* ids[] = {"woonkamer", "keuken", "badkamer", "slaapkamer", "kinderkamer", "logeerkamer", "werkkamer", "zolder"};
    RoomPlan plan;
    plan.revision = 12;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = ids[i]; r.name = ids[i];
        r.state = RoomDemand::State::active;
        r.sources = {{RoomPlan::SourceType::ha, std::string("sensor.") + ids[i] + "_temperature"},
                     {RoomPlan::SourceType::ble, "a4c13800000" + std::to_string(i)}};
        r.setpointEntity = std::string("climate.") + ids[i];
        const RoomSchedule::Point weekday[] = {{390, 2050}, {480, 1800}, {1020, 2100}, {1350, 1700}};
        for (int d = 0; d < 7; ++d) {
            auto& day = r.schedule.days[d];
            for (const auto& pt : weekday) day.points[day.count++] = pt;
            r.pointLevels[d] = 0 | 2 << 2 | 1 << 4 | 3 << 6;
        }
        r.hasLevels = true; r.levels = {2100, 1800, 1700};
        r.awayCentiC = int16_t(1550 + 50 * i);
        plan.rooms.push_back(r);
    }
    auto without = plan;
    for (auto& r : without.rooms) r.awayCentiC.reset();
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room away ] 8 rooms x 4 points, levels and own away: API form %zu B (+%zu), stored form %zu B (+%zu), store %zu B\n",
                api.size(), api.size() - without.json().size(), stored.size(), stored.size() - without.storedJson().size(), RoomPlan::storeBytes);
    EXPECT_NE(stored.find(R"("aw":1550)"), std::string::npos);
    EXPECT_EQ(stored.find("away_centi_c"), std::string::npos);
    EXPECT_EQ(stored.size() - without.storedJson().size(), 8 * std::strlen(R"(,"aw":1550)"));
    EXPECT_LE(stored.size() + 1 + ControlPartitionBudget::editBytes, RoomPlan::storeBytes);
    EXPECT_LE(api.size() + 8 * 80, RoomPlan::requestBytes);
    // NVS: the plan's blob grows by at most 3 entries; the ledger reserves a full 4 KB plan save anyway.
    EXPECT_LE(ControlPartitionBudget::blobEntries(stored.size() + 1) - ControlPartitionBudget::blobEntries(without.storedJson().size() + 1), 3u);
    const auto back = parsed(stored);
    EXPECT_EQ(back.json(), api);
    EXPECT_EQ(back.rooms[7].awayCentiC, 1900);
    for (const std::string& form : {stored, plan.documentJson()}) {
        Json root(cJSON_Parse(form.c_str()), cJSON_Delete);
        RoomPlanRc2 rc2;
        ASSERT_EQ(RoomPlanRc2::parse(root.get(), rc2), nullptr) << form.substr(0, 120);
        RoomPlanBeta21 beta21;
        ASSERT_EQ(RoomPlanBeta21::parse(root.get(), beta21), nullptr);
        ASSERT_EQ(rc2.rooms.size(), 8u);
        ASSERT_EQ(beta21.rooms.size(), 8u);
        for (size_t i = 0; i < 8; ++i)
            for (uint8_t d = 0; d < 7; ++d)
                for (uint16_t m = 0; m < 1440; m += 30) {
                    EXPECT_EQ(rc2.rooms[i].schedule.at(d, m), plan.rooms[i].schedule.at(d, m));
                    EXPECT_EQ(beta21.rooms[i].schedule.at(d, m), plan.rooms[i].schedule.at(d, m));
                }
        // rc.2 keeps its own fields (levels) and drops only the away value; its plan is today's without it.
        EXPECT_EQ(rc2.json().find("away"), std::string::npos);
        EXPECT_EQ(parsed(rc2.json()).json(), without.json());
    }
}

// The largest storable plan with an own away value in every room still has an API form within the
// request bound (as Home Assistant prints it, with escaped names).
TEST(RoomAway, TheApiFormOfTheLargestStorablePlanFitsTheRequestBound) {
    RoomPlan plan;
    plan.revision = 4294967295u; plan.minimumFlowC = 20; plan.maximumFlowC = 80;
    for (int i = 0; i < 8; ++i) {
        RoomPlan::Room r;
        r.id = std::string(32, char('a' + i));
        r.name = std::string(40, '\x01');
        r.inactiveUntil = 4102444800u;
        r.sources.push_back({RoomPlan::SourceType::ha, "sensor." + std::string(72, char('a' + i))});
        r.setpointEntity = "climate." + std::string(72, char('a' + i));
        r.fallbackCentiC = 2999; r.minimumCentiC = 1000; r.maximumCentiC = 3000;
        for (auto& day : r.schedule.days)
            for (uint16_t m = 1434; day.count < RoomSchedule::maxPoints; ++m)
                day.points[day.count++] = {m, int16_t(2990 + day.count)};
        r.hasLevels = true;
        r.levels = {r.schedule.days[0].points[1].centiC, r.schedule.days[0].points[2].centiC, r.schedule.days[0].points[3].centiC};
        for (auto& marks : r.pointLevels) marks = 1 << 2 | 2 << 4 | 3 << 6;
        r.awayCentiC = 2499;
        plan.rooms.push_back(r);
    }
    for (size_t turn = 0; plan.storedJson().size() + 1 > RoomPlan::storeBytes; ++turn) {
        ASSERT_LT(turn, 20000u) << plan.storedJson().size();
        auto& r = plan.rooms[turn % 8];
        if (r.name.size() > 1) { r.name.pop_back(); continue; }
        for (auto& s : r.sources) if (s.id.size() > 9) s.id.erase(7, 1);
        if (r.setpointEntity.size() > 9) r.setpointEntity.erase(8, 1);
    }
    const auto api = plan.json(), stored = plan.storedJson();
    std::printf("[ room away ] largest storable plan with own away values: stored %zu B, API form %zu B (request bound %zu B)\n",
                stored.size(), api.size(), RoomPlan::requestBytes);
    EXPECT_EQ(parsed(stored).json(), api);
    EXPECT_LE(api.size() + 8 * 80, RoomPlan::requestBytes);
}

// The settings backup carries the value (it is part of the plan): a restore onto a factory-reset E32
// brings it back, a restore onto the same E32 changes nothing, and one without it is a room change.
TEST(RoomAway, TheValueTravelsWithTheSettingsBackup) {
    b::DeviceState source;
    source.network = R"({"hostname":"heating-home","mqtt":{"enabled":false}})";
    source.bluetooth = R"({"bt":{}})";
    source.plan = parsed(houseText).json();
    source.flow = heating::control::FlowSettings{}.json(); source.display = "none";
    b::Meta meta; meta.firmware = "1.0.0-e32v2-rc.3"; meta.board = "e32v2"; meta.created = "2026-11-03T20:00:00Z"; meta.language = "en";
    auto doc = b::exportDocument(source, meta, "");
    ASSERT_TRUE(doc);
    const auto heating = b::print(b::item(doc.get(), "heating"));
    EXPECT_NE(heating.find(R"("away_centi_c":1600)"), std::string::npos);
    EXPECT_EQ(heating.find("features"), std::string::npos);
    const auto prepare = [&](const b::DeviceState& onto, b::Prepared& out, b::Report& report) {
        return b::preparePlan(doc.get(), onto, out.plan, report);
    };
    // Onto a factory-reset E32: the plan candidate holds the value.
    b::DeviceState factory = source;
    factory.plan = R"({"schema":1,"revision":0,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[]})";
    b::Prepared out; b::Report report;
    ASSERT_EQ(prepare(factory, out, report), nullptr);
    ASSERT_FALSE(out.plan.empty());
    const auto restored = parsed(out.plan);
    EXPECT_EQ(restored.rooms[study].awayCentiC, 1600);
    EXPECT_EQ(restored.rooms[guest].awayCentiC, 1800);
    EXPECT_FALSE(restored.rooms[bedroom].awayCentiC);
    // Onto the same E32: nothing to do.
    b::Prepared same; b::Report sameReport;
    ASSERT_EQ(prepare(source, same, sameReport), nullptr);
    EXPECT_TRUE(same.plan.empty());
    // Onto an E32 whose study lost its value: the same rooms, other details.
    b::DeviceState other = source;
    other.plan = parsed(replaced(houseText, R"(,"away_centi_c":1600)", "")).json();
    b::Prepared changed; b::Report changedReport;
    ASSERT_EQ(prepare(other, changed, changedReport), nullptr);
    EXPECT_EQ(parsed(changed.plan).rooms[study].awayCentiC, 1600);
    EXPECT_NE(b::print(changedReport.changes.get()).find("room_settings"), std::string::npos);
}
