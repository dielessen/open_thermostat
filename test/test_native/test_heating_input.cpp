#include "control/HeatingInput.h"
#include "control/HeatingTelemetry.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>

namespace {
using heating::control::FlowLearner;
using heating::control::HeatingInput;
using heating::control::HeatingInputRoute;
using heating::control::RoomEngine;
using heating::control::RoomPlan;
using Kind = HeatingInput::Kind;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t minute = 60000;

TEST(HeatingInput, RoomPayloadsKeepTheirFormat) {
    const auto in = HeatingInput::parse(R"({"entity":"climate.woonkamer","temperature":20.44,"target":21.0})");
    ASSERT_TRUE(in);
    EXPECT_EQ(in->kind, Kind::room);
    EXPECT_EQ(in->entity, "climate.woonkamer");
    EXPECT_EQ(in->temperatureCentiC, 2044); EXPECT_EQ(in->targetCentiC, 2100);
    const auto partial = HeatingInput::parse(R"({"entity":"input_number.badkamer","temperature":null,"target":19.5})");
    ASSERT_TRUE(partial);
    EXPECT_FALSE(partial->temperatureCentiC); EXPECT_EQ(partial->targetCentiC, 1950);
    // Out of range values are dropped, the message still counts.
    const auto wild = HeatingInput::parse(R"({"entity":"sensor.x","temperature":120,"target":3})");
    ASSERT_TRUE(wild);
    EXPECT_FALSE(wild->temperatureCentiC); EXPECT_FALSE(wild->targetCentiC);
    EXPECT_FALSE(HeatingInput::parse(R"({"temperature":20})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"entity":""})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"entity":")" + std::string(81, 'a') + R"("})"));
    EXPECT_FALSE(HeatingInput::parse(R"(["climate.woonkamer"])"));
    EXPECT_FALSE(HeatingInput::parse("not json"));
}

TEST(HeatingInput, TypedKindsAreValidatedStrictly) {
    const auto gas = HeatingInput::parse(R"({"kind":"gas_m3","entity":"sensor.gas_consumed","value":1234.567})");
    ASSERT_TRUE(gas); EXPECT_EQ(gas->kind, Kind::gasM3); EXPECT_DOUBLE_EQ(gas->value, 1234.567);
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_m3","value":1234.5})"));                  // entity required
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_m3","entity":"sensor.gas","value":-1})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_m3","entity":"sensor.gas","value":"12"})"));
    const auto price = HeatingInput::parse(R"({"kind":"gas_price","value":1.32})");
    ASSERT_TRUE(price); EXPECT_EQ(price->kind, Kind::gasPrice);
    EXPECT_TRUE(HeatingInput::parse(R"({"kind":"gas_price","value":20})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_price","value":0})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_price","value":20.01})"));
    const auto outdoor = HeatingInput::parse(R"({"kind":"outdoor_c","entity":"sensor.buiten","value":-7.4})");
    ASSERT_TRUE(outdoor); EXPECT_EQ(outdoor->kind, Kind::outdoorC); EXPECT_DOUBLE_EQ(outdoor->value, -7.4);
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"outdoor_c","entity":"sensor.buiten","value":61})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"outdoor_c","value":7})"));
    const auto kw = HeatingInput::parse(R"({"kind":"boiler_kw","value":24})");
    ASSERT_TRUE(kw); EXPECT_EQ(kw->kind, Kind::boilerKw);
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"boiler_kw","value":2.9})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"boiler_kw","value":61})"));
    const auto kwh = HeatingInput::parse(R"({"kind":"gas_kwh_per_m3","value":9.77})");
    ASSERT_TRUE(kwh); EXPECT_EQ(kwh->kind, Kind::gasKwhPerM3);
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_kwh_per_m3","value":4.9})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_kwh_per_m3","value":15.1})"));
    // Unknown or malformed kinds are ignored, also with a room-like body.
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"electricity_kwh","entity":"sensor.p1","value":3})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":1,"entity":"climate.woonkamer","temperature":20})"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":null,"entity":"climate.woonkamer","temperature":20})"));
    // Size and depth limits as before.
    EXPECT_FALSE(HeatingInput::parse(std::string(R"({"kind":"gas_price","value":1.3,"pad":")") + std::string(240, 'x') + "\"}"));
    EXPECT_FALSE(HeatingInput::parse(R"({"kind":"gas_price","value":1.3,"x":[[[[1]]]]})"));
}

TEST(HeatingInput, RouteFeedsRoomsAndLearnerAndTracksFreshness) {
    RoomPlan plan;
    RoomPlan::Room room; room.id = "woonkamer"; room.name = "Woonkamer";
    room.sources = {{RoomPlan::SourceType::ha, "climate.woonkamer"}}; room.setpointEntity = "climate.woonkamer";
    plan.rooms = {room};
    RoomEngine rooms; rooms.setPlan(plan);
    FlowLearner learner; learner.setPlan(plan);
    HeatingInputRoute route;
    EXPECT_FALSE(route.lastAcceptedMs());
    EXPECT_FALSE(route.accept(R"({"kind":"electricity_kwh","value":3})", 1000, rooms, learner));
    EXPECT_FALSE(route.lastAcceptedMs());                 // ignored messages do not count as HA alive
    ASSERT_TRUE(route.accept(R"({"entity":"climate.woonkamer","temperature":20.4,"target":21})", 2000, rooms, learner));
    EXPECT_EQ(rooms.freshTemperature(0, 2000), 2040);
    EXPECT_EQ(route.lastAcceptedMs(), 2000u);
    ASSERT_TRUE(route.accept(R"({"kind":"gas_m3","entity":"sensor.gas","value":100.5})", 3000, rooms, learner));
    EXPECT_EQ(learner.gasMeterAt(), 3000u);
    ASSERT_TRUE(route.accept(R"({"kind":"gas_price","value":1.32})", 4000, rooms, learner));
    EXPECT_FLOAT_EQ(*learner.price(), 1.32f);
    EXPECT_FALSE(learner.nominalFromHa());
    ASSERT_TRUE(route.accept(R"({"kind":"boiler_kw","value":24})", 5000, rooms, learner));
    EXPECT_FLOAT_EQ(learner.nominalKw(), 24); EXPECT_TRUE(learner.nominalFromHa());
    EXPECT_FALSE(learner.kwhPerM3FromHa());
    ASSERT_TRUE(route.accept(R"({"kind":"gas_kwh_per_m3","value":11.5})", 5500, rooms, learner));
    EXPECT_FLOAT_EQ(learner.params().kwhPerM3, 11.5f); EXPECT_TRUE(learner.kwhPerM3FromHa());
    // Outdoor: the boiler's wins; HA's is used while at most 15 min old.
    EXPECT_FALSE(route.outdoor(std::nullopt, 5000).source);
    ASSERT_TRUE(route.accept(R"({"kind":"outdoor_c","entity":"sensor.buiten","value":7.45})", 6000, rooms, learner));
    const auto ha = route.outdoor(std::nullopt, 6000 + 15 * minute);
    EXPECT_STREQ(ha.source, "ha"); EXPECT_EQ(ha.centiC, 745);
    const auto boiler = route.outdoor(int16_t(-120), 7000);
    EXPECT_STREQ(boiler.source, "boiler"); EXPECT_EQ(boiler.centiC, -120);
    EXPECT_FALSE(route.outdoor(std::nullopt, 6001 + 15 * minute).centiC);
    EXPECT_EQ(route.lastAcceptedMs(), 6000u);
    // learned.inputs shows what HA delivered.
    heating::control::LearnedContext context;
    context.now = 3000 + heating::control::gasMeterFreshMs; context.outdoorSource = "ha";
    Json learned(heating::control::learnedJson(learner, plan, context), cJSON_Delete);
    const cJSON* inputs = cJSON_GetObjectItem(learned.get(), "inputs");
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(inputs, "gas_meter")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(inputs, "gas_price")));
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "outdoor")->valuestring, "ha");
    EXPECT_EQ(cJSON_GetObjectItem(inputs, "boiler_kw")->valuedouble, 24);
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "boiler_kw_source")->valuestring, "ha");
    EXPECT_EQ(cJSON_GetObjectItem(inputs, "gas_kwh_per_m3")->valuedouble, 11.5);
    EXPECT_STREQ(cJSON_GetObjectItem(inputs, "gas_kwh_per_m3_source")->valuestring, "ha");
    EXPECT_FALSE(cJSON_GetObjectItem(learned.get(), "plans"));  // no trusted clock
    context.now += 1; context.outdoorSource = nullptr;
    Json later(heating::control::learnedJson(learner, plan, context), cJSON_Delete);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(cJSON_GetObjectItem(later.get(), "inputs"), "gas_meter")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(cJSON_GetObjectItem(later.get(), "inputs"), "outdoor")));
}
}
