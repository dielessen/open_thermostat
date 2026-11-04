// P22 (4 Nov 2026): Home Assistant stopped feeding the E32, and the E32 page could only say "Home Assistant is
// gone". The E32 now says why it refused the last ha/heating_input message (ha.last_rejected) and, after 15
// silent minutes on a live broker session, subscribes the topic again (ha.resubscribed_s). Acceptance itself
// and the rooms' 15-minute fallback are unchanged.
#include "control/HaInputSilence.h"
#include "control/HeatingInput.h"
#include "control/HeatingTelemetry.h"
#include "control/RoomOverrides.h"
#include "control/TelemetryPolicy.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60 * second;

std::string print(const cJSON* o) {
    char* text = cJSON_PrintUnformatted(o);
    std::string s = text ? text : "";
    cJSON_free(text);
    return s;
}

const char* why(const std::string& payload) {
    const char* reason = nullptr;
    EXPECT_FALSE(HeatingInput::parse(payload, &reason)) << payload;
    return reason;
}

RoomPlan livingPlan() {
    RoomPlan plan;
    RoomPlan::Room room; room.id = "woonkamer"; room.name = "Woonkamer";
    room.sources = {{RoomPlan::SourceType::ha, "climate.woonkamer"}}; room.setpointEntity = "climate.woonkamer";
    plan.rooms = {room};
    return plan;
}

TEST(HeatingInputLink, EveryRefusalHasAReason) {
    EXPECT_STREQ(why(std::string(R"({"kind":"gas_price","value":1.3,"pad":")") + std::string(240, 'x') + "\"}"), "too_large");
    EXPECT_STREQ(why("not json"), "invalid_json");
    EXPECT_STREQ(why(R"(["climate.woonkamer"])"), "invalid_json");
    EXPECT_STREQ(why(R"({"kind":"gas_price","value":1.3,"x":[[[[1]]]]})"), "invalid_json");
    EXPECT_STREQ(why(R"({"temperature":20})"), "no_entity");
    EXPECT_STREQ(why(R"({"entity":""})"), "no_entity");
    EXPECT_STREQ(why(R"({"entity":")" + std::string(81, 'a') + R"("})"), "no_entity");
    EXPECT_STREQ(why(R"({"kind":"gas_m3","value":1234.5})"), "no_entity");
    EXPECT_STREQ(why(R"({"kind":"outdoor_c","value":7})"), "no_entity");
    EXPECT_STREQ(why(R"({"kind":"electricity_kwh","entity":"sensor.p1","value":3})"), "unknown_kind");
    EXPECT_STREQ(why(R"({"kind":1,"entity":"climate.woonkamer","temperature":20})"), "unknown_kind");
    EXPECT_STREQ(why(R"({"kind":null,"entity":"climate.woonkamer","temperature":20})"), "unknown_kind");
    EXPECT_STREQ(why(R"({"kind":"gas_m3","entity":"sensor.gas","value":-1})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"gas_m3","entity":"sensor.gas","value":"12"})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"gas_price","value":0})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"gas_price","value":1000.01})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"outdoor_c","entity":"sensor.buiten","value":61})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"boiler_kw","value":2.9})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"gas_kwh_per_m3","value":15.1})"), "invalid_value");
    EXPECT_STREQ(why(R"({"kind":"gas_kwh_per_m3"})"), "invalid_value");
    // What was accepted before still is, and leaves the reason untouched.
    for (const char* ok : {R"({"entity":"climate.woonkamer","temperature":20.44,"target":21.0})",
                           R"({"entity":"sensor.x","temperature":120,"target":3})", R"({"kind":"gas_price","value":1000})",
                           R"({"kind":"gas_m3","entity":"sensor.gas","value":0})", R"({"kind":"outdoor_c","entity":"s.b","value":-50})",
                           R"({"kind":"boiler_kw","value":60})", R"({"kind":"gas_kwh_per_m3","value":5})"}) {
        const char* reason = nullptr;
        EXPECT_TRUE(HeatingInput::parse(ok, &reason)) << ok;
        EXPECT_EQ(reason, nullptr) << ok;
    }
}

TEST(HeatingInputLink, TheRouteKeepsTheLastRefusalApartFromTheLastAcceptance) {
    const auto plan = livingPlan();
    RoomEngine rooms; rooms.setPlan(plan);
    FlowLearner learner; learner.setPlan(plan);
    HeatingInputRoute route;
    EXPECT_EQ(route.lastRejected().reason, nullptr);
    ASSERT_TRUE(route.accept(R"({"entity":"climate.woonkamer","temperature":20.4,"target":21})", 2000, rooms, learner));
    EXPECT_FALSE(route.accept(R"({"kind":"gas_price","value":0})", 3000, rooms, learner));
    EXPECT_STREQ(route.lastRejected().reason, "invalid_value");
    EXPECT_EQ(route.lastRejected().atMs, 3000u);
    EXPECT_EQ(route.lastAcceptedMs(), 2000u);  // a refusal never counts as Home Assistant alive
    ASSERT_TRUE(route.accept(R"({"kind":"gas_price","value":1.2})", 4000, rooms, learner));
    EXPECT_STREQ(route.lastRejected().reason, "invalid_value");  // kept: the last refusal, with its own age
    route.reject("unknown_room", 5000);
    EXPECT_STREQ(route.lastRejected().reason, "unknown_room");
    EXPECT_EQ(route.lastAcceptedMs(), 4000u);
}

TEST(HeatingInputLink, ContactsAndPresenceSayWhyTheyWereRefused) {
    const auto plan = livingPlan();
    RoomOverrides overrides;
    const auto refused = [&](const std::string& payload) {
        const char* reason = nullptr;
        EXPECT_TRUE(overrides.input(payload, plan, 1000, &reason)) << payload;  // consumed, as before
        return reason;
    };
    EXPECT_STREQ(refused(R"({"kind":"contact","room":"zolder","open":true})"), "unknown_room");
    EXPECT_STREQ(refused(R"({"kind":"room_presence","room":"zolder","home":true})"), "unknown_room");
    EXPECT_STREQ(refused(R"({"kind":"contact","room":"woonkamer","open":"yes"})"), "invalid_value");
    EXPECT_STREQ(refused(R"({"kind":"contact","room":"woonkamer","open":true,"delay_s":1801})"), "invalid_value");
    EXPECT_STREQ(refused(R"({"kind":"presence","home":"maybe"})"), "invalid_value");
    EXPECT_STREQ(refused(R"({"kind":"room_presence","room":7,"home":true})"), "invalid_value");
    EXPECT_EQ(refused(R"({"kind":"contact","room":"woonkamer","open":true,"delay_s":120})"), nullptr);
    EXPECT_EQ(refused(R"({"kind":"presence","home":false})"), nullptr);
    EXPECT_EQ(refused(R"({"kind":"room_presence","room":"woonkamer","home":true})"), nullptr);
    const char* untouched = nullptr;
    EXPECT_FALSE(overrides.input(R"({"entity":"climate.woonkamer","temperature":20})", plan, 1000, &untouched));
    EXPECT_EQ(untouched, nullptr);  // not a comfort message: HeatingInputRoute decides
}

TEST(HeatingInputLink, TheHaBlockNamesTheRefusalAndTheResubscription) {
    Json plain(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addHaLink(plain.get(), 1000, 43999, true));
    EXPECT_EQ(print(cJSON_GetObjectItem(plain.get(), "ha")), R"({"input_age_s":42,"broker_connected":true})");
    Json full(cJSON_CreateObject(), cJSON_Delete);
    ASSERT_TRUE(addHaLink(full.get(), 1000, 43999, true, "unknown_room", 33999, uint64_t(13999)));
    EXPECT_EQ(print(cJSON_GetObjectItem(full.get(), "ha")),
              R"({"input_age_s":42,"broker_connected":true,"last_rejected":{"reason":"unknown_room","age_s":10},"resubscribed_s":30})");
    Json future(cJSON_CreateObject(), cJSON_Delete);  // never a negative age: left out
    ASSERT_TRUE(addHaLink(future.get(), std::nullopt, 5000, true, "too_large", 9000, uint64_t(9000)));
    EXPECT_EQ(print(cJSON_GetObjectItem(future.get(), "ha")), R"({"input_age_s":null,"broker_connected":true})");
}

TEST(HeatingInputLink, GrowingAgesNeverResendTheHeatingStatusButANewReasonDoes) {
    const auto doc = [](const char* reason, double age, double resubscribed) {
        Json root(cJSON_Parse(R"({"schema":1,"request":{"heat":true,"flow_c":44,"reason":"heating"}})"), cJSON_Delete);
        addHaLink(root.get(), 1000, 1000 + 600 * second, true, reason, uint64_t(1000 + 600 * second - age * second),
                  uint64_t(1000 + 600 * second - resubscribed * second));
        return root;
    };
    const auto before = print(doc("invalid_value", 3, 30).get());
    EXPECT_FALSE(changedBeyond(before, doc("invalid_value", 250, 290).get(), heatingBands));
    EXPECT_TRUE(changedBeyond(before, doc("unknown_room", 3, 30).get(), heatingBands));
    Json none(cJSON_Parse(R"({"schema":1,"request":{"heat":true,"flow_c":44,"reason":"heating"}})"), cJSON_Delete);
    addHaLink(none.get(), 1000, 1000 + 600 * second, true);
    EXPECT_TRUE(changedBeyond(print(none.get()), doc("invalid_value", 3, 30).get(), heatingBands));  // the first refusal
}

TEST(HeatingInputLink, FifteenSilentMinutesOnALiveSessionSubscribeAgain) {
    HaInputSilence silence;
    int asked = 0;
    const auto expected = [&](bool value) { return [&asked, value] { ++asked; return value; }; };
    silence.connected(10 * second);
    EXPECT_FALSE(silence.due(10 * second + 14 * minute, expected(true)));
    EXPECT_EQ(asked, 0);  // the plan is only asked once the silence is long enough
    silence.received(10 * second + 14 * minute);  // a message arrived: the subscription works
    EXPECT_FALSE(silence.due(10 * second + 20 * minute, expected(true)));
    ASSERT_TRUE(silence.due(10 * second + 29 * minute, expected(true)));
    silence.resubscribed(10 * second + 29 * minute);
    EXPECT_EQ(silence.count(), 1u);
    EXPECT_EQ(silence.lastResubscribeMs(), 10 * second + 29 * minute);
    EXPECT_FALSE(silence.due(10 * second + 43 * minute, expected(true)));  // again only after another quarter
    EXPECT_TRUE(silence.due(10 * second + 44 * minute, expected(true)));
    // A plan without Home Assistant entities expects nothing: no resubscription, and the plan is asked again
    // only after another quarter of an hour.
    HaInputSilence quiet;
    quiet.connected(0);
    asked = 0;
    EXPECT_FALSE(quiet.due(15 * minute, expected(false)));
    EXPECT_FALSE(quiet.due(20 * minute, expected(false)));
    EXPECT_EQ(asked, 1);
    EXPECT_FALSE(quiet.due(30 * minute, expected(false)));
    EXPECT_EQ(asked, 2);
    EXPECT_FALSE(quiet.lastResubscribeMs());
    // A new broker session starts the count afresh (its subscriptions are new).
    silence.connected(50 * minute);
    EXPECT_FALSE(silence.due(64 * minute, expected(true)));
    EXPECT_TRUE(silence.due(65 * minute, expected(true)));
    EXPECT_EQ(silence.count(), 1u);  // counted on resubscribed() only
}
}
