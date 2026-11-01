#include "control/TrvControl.h"
#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {
using heating::control::FlowDemand;
using heating::control::TrvConfig;
using heating::control::TrvControl;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t M = 60 * 1000ULL;

TrvConfig parse(const char* text, const char** error = nullptr) {
    Json root(cJSON_Parse(text), cJSON_Delete);
    TrvConfig c;
    const char* e = TrvConfig::parse(root.get(), c);
    if (error) *error = e;
    else EXPECT_EQ(e, nullptr) << text;
    return c;
}
const char* bedroomBosch =
    R"({"schema":1,"rooms":[{"room":"slaapkamer","control":true,"valves":[{"name":"Slaapkamer kraan","model":"bosch_bth_ra"}]},)"
    R"({"room":"woonkamer","control":false,"valves":[]}]})";
struct Sent { std::vector<std::pair<std::string, std::string>> all; };
TrvControl::Send recorder(Sent& s) { return [&s](const std::string& t, const std::string& p) { s.all.emplace_back(t, p); return true; }; }
TrvControl::Room room(const char* id, std::optional<int16_t> setpoint, std::optional<int16_t> temp, bool active = true, size_t sources = 2) {
    TrvControl::Room r; r.id = id; r.active = active; r.setpoint = setpoint; r.temperature = temp; r.sources = sources;
    if (setpoint && temp) { r.errorCentiC = int16_t(*setpoint - *temp); r.demanding = active && r.errorCentiC > 0; }
    return r;
}
FlowDemand::Request heat(uint8_t flow) { FlowDemand::Request r; r.heat = true; r.flowC = flow; return r; }

// ---- Harmless while unused --------------------------------------------------------------

TEST(TrvHarmless, NoConfigSubscribesNothingSendsNothingAndKeepsEveryRequest) {
    TrvControl trv;
    EXPECT_FALSE(trv.used());
    EXPECT_TRUE(trv.subscriptions().empty());
    Sent sent;
    const std::vector<TrvControl::Room> rooms{room("woonkamer", 2100, 1900)};
    for (bool output : {false, true})
        for (uint64_t t = 0; t < 48 * 3600 * 1000ULL; t += 10 * 1000ULL) {
            trv.step(t, rooms, output, recorder(sent));
            for (uint8_t flow : {0, 30, 45, 60}) {
                auto r = flow ? heat(flow) : FlowDemand::Request{};
                const auto out = trv.adjust(r, rooms, output, t, 30, 60);
                ASSERT_EQ(out.heat, r.heat); ASSERT_EQ(out.flowC, r.flowC);
            }
        }
    EXPECT_TRUE(sent.all.empty());
    EXPECT_EQ(trv.statusJson(1, rooms), nullptr);  // the status object is exactly as before
    EXPECT_FALSE(trv.actuatorOutput());
    EXPECT_FALSE(trv.receive("zigbee2mqtt/Some valve", R"({"position":50})", 1));  // not ours: not consumed
}

TEST(TrvHarmless, ValvesWithControlOffNeverSendOrChangeTheRequest) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"slaapkamer","control":false,"valves":[{"name":"K","model":"bosch_bth_ra"}]}]})"));
    EXPECT_EQ(trv.subscriptions(), std::vector<std::string>{"zigbee2mqtt/K"});  // listening only (status)
    Sent sent;
    const std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1700)};
    trv.receive("zigbee2mqtt/K", R"({"pi_heating_demand":0,"battery":80})", 1);
    for (uint64_t t = 1; t < 3 * 3600 * 1000ULL; t += 10 * 1000ULL) {
        trv.step(t, rooms, true, recorder(sent));
        const auto out = trv.adjust(heat(45), rooms, true, t, 30, 60);
        ASSERT_TRUE(out.heat); ASSERT_EQ(out.flowC, 45);
    }
    EXPECT_TRUE(sent.all.empty());
    EXPECT_FALSE(trv.actuatorOutput());
}

TEST(TrvHarmless, ControlOnButOutputDisabledSendsNothing) {
    // Shadow mode or no confirmed takeover: the room's control is on, still nothing goes out.
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    Sent sent;
    const std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1700)};
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":0})", 1);
    for (uint64_t t = 1; t < 2 * 3600 * 1000ULL; t += 10 * 1000ULL) {
        trv.step(t, rooms, false, recorder(sent));
        const auto out = trv.adjust(heat(45), rooms, false, t, 30, 60);
        ASSERT_EQ(out.flowC, 45); ASSERT_TRUE(out.heat);
    }
    EXPECT_TRUE(sent.all.empty());
    EXPECT_FALSE(trv.actuatorOutput());
}

// ---- Config -----------------------------------------------------------------------------

TEST(TrvConfigTest, ParsesValidatesAndRoundTrips) {
    const auto c = parse(bedroomBosch);
    EXPECT_EQ(c.baseTopic, "zigbee2mqtt");
    ASSERT_EQ(c.rooms.size(), 2u);
    EXPECT_TRUE(c.rooms[0].control);
    EXPECT_FALSE(c.rooms[1].control);
    EXPECT_EQ(parse(c.json().c_str()), c);
    const char* error = nullptr;
    for (const char* bad : {
             R"({"schema":2,"rooms":[]})",
             R"({"schema":1,"base_topic":"zig bee","rooms":[]})",
             R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":"x/#","model":"generic"}]}]})",
             R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":"x","model":"unknown"}]}]})",
             R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":"x","model":"generic"}]},{"room":"b","valves":[{"name":"x","model":"generic"}]}]})",
             R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":"bridge/state","model":"generic"}]}]})",
             R"({"schema":1,"rooms":[{"room":"a","control":"yes","valves":[]}]})"}) {
        parse(bad, &error);
        EXPECT_NE(error, nullptr) << bad;
    }
    // Control without a valve is dropped.
    const auto noValves = parse(R"({"schema":1,"rooms":[{"room":"a","control":true,"valves":[]}]})");
    EXPECT_FALSE(noValves.rooms[0].control);
    EXPECT_TRUE(noValves.empty());
    EXPECT_LT(c.json().size(), TrvConfig::maxBytes);
}

// ---- Commands and battery saving ---------------------------------------------------------

TEST(TrvCommands, SetpointExternalTemperatureAndModeOnceThenOnlyOnChange) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    Sent sent;
    std::vector<TrvControl::Room> rooms{room("slaapkamer", 2010, 1730)};
    trv.step(1000, rooms, true, recorder(sent));
    ASSERT_EQ(sent.all.size(), 3u);
    EXPECT_EQ(sent.all[0].first, "zigbee2mqtt/Slaapkamer kraan/set");
    EXPECT_EQ(sent.all[0].second, R"({"operating_mode":"manual"})");
    EXPECT_EQ(sent.all[1].second, R"({"occupied_heating_setpoint":20.0})");  // 20.10 rounds to 0.5 steps
    EXPECT_EQ(sent.all[2].second, R"({"remote_temperature":17.30})");
    sent.all.clear();
    // Small changes within 10 min: nothing.
    rooms[0].temperature = 1740; rooms[0].setpoint = 2020;
    for (uint64_t t = 1000; t < 1000 + 9 * M; t += 10000) trv.step(t, rooms, true, recorder(sent));
    EXPECT_TRUE(sent.all.empty());
    // A 0.5 degC target change goes out at once; the temperature waits for its 10 min.
    rooms[0].setpoint = 2100;
    trv.step(1000 + 9 * M + 10000, rooms, true, recorder(sent));
    ASSERT_EQ(sent.all.size(), 1u);
    EXPECT_EQ(sent.all[0].second, R"({"occupied_heating_setpoint":21.0})");
    sent.all.clear();
    // A 0.1 degC drift is sent only after 25 min (the Bosch falls back after 30 min).
    uint64_t t = 1000 + 10 * M;
    for (; t < 1000 + 24 * M; t += 10000) trv.step(t, rooms, true, recorder(sent));
    EXPECT_TRUE(sent.all.empty());
    for (; t <= 1000 + 26 * M; t += 10000) trv.step(t, rooms, true, recorder(sent));
    ASSERT_EQ(sent.all.size(), 1u);
    EXPECT_EQ(sent.all[0].second, R"({"remote_temperature":17.40})");
}

TEST(TrvCommands, InactiveRoomGetsFrostSetpointAndNoMeasurementSendsNoExternalTemperature) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"b","control":true,"valves":[{"name":"V","model":"sonoff_trvzb"}]}]})"));
    Sent sent;
    trv.step(1, {room("b", 2000, std::nullopt, false)}, true, recorder(sent));
    // No room measurement: no sensor-select to external, no external value (the valve uses its own sensor).
    ASSERT_EQ(sent.all.size(), 1u);
    EXPECT_EQ(sent.all[0].second, R"({"occupied_heating_setpoint":8.0})");
}

TEST(TrvCommands, Tv02GetsSetpointOnlyAndClampsToItsRange) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"b","control":true,"valves":[{"name":"T","model":"tuya_tv02"}]}]})"));
    Sent sent;
    trv.step(1, {room("b", 3000, 2000)}, true, recorder(sent));
    ASSERT_EQ(sent.all.size(), 2u);
    EXPECT_EQ(sent.all[0].second, R"({"preset":"manual"})");
    EXPECT_EQ(sent.all[1].second, R"({"current_heating_setpoint":29.5})");
}

// ---- Health -------------------------------------------------------------------------------

TEST(TrvHealth, BatteryLowOfflineAndDegradedStatus) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    const std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1900, true, 1)};
    EXPECT_EQ(trv.health("Slaapkamer kraan", 1), TrvControl::Health::unknown);
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":35,"battery":64,"local_temperature":19.2})", 1000);
    EXPECT_EQ(trv.health("Slaapkamer kraan", 2000), TrvControl::Health::ok);
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"battery":18})", 3000);
    EXPECT_EQ(trv.health("Slaapkamer kraan", 4000), TrvControl::Health::lowBattery);
    EXPECT_EQ(trv.health("Slaapkamer kraan", 3000 + TrvControl::staleMs), TrvControl::Health::offline);
    Json status(trv.statusJson(3000 + TrvControl::staleMs, rooms), cJSON_Delete);
    ASSERT_TRUE(status);
    const auto* r = cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(r, "degraded")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(r, "single_source")));
    const auto* v = cJSON_GetArrayItem(cJSON_GetObjectItem(r, "valves"), 0);
    EXPECT_STREQ(cJSON_GetObjectItem(v, "health")->valuestring, "offline");
    EXPECT_EQ(cJSON_GetObjectItem(v, "position_pct")->valuedouble, 35);
    // Garbage and oversized payloads are consumed and ignored.
    EXPECT_TRUE(trv.receive("zigbee2mqtt/Slaapkamer kraan", "not json", 5000));
    EXPECT_TRUE(trv.receive("zigbee2mqtt/Slaapkamer kraan", std::string(2000, ' '), 5000));
    EXPECT_FALSE(trv.receive("zigbee2mqtt/Slaapkamer kraan/set", "{}", 5000));
}

// ---- Flow feedback and the all-closed rule ------------------------------------------------

TEST(TrvFeedback, PartlyClosedLowersOpenAndColdRaisesBoundedAndRateLimited) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1950)};
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":30})", 1);
    uint64_t t = 1;
    auto out = trv.adjust(heat(45), rooms, true, t, 30, 60);
    EXPECT_EQ(out.flowC, 44);
    out = trv.adjust(heat(45), rooms, true, t + 5 * M, 30, 60);  // not yet: once per 10 min
    EXPECT_EQ(out.flowC, 44);
    for (int i = 0; i < 20; ++i) { t += 10 * M; trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":30})", t); out = trv.adjust(heat(45), rooms, true, t, 30, 60); }
    EXPECT_EQ(trv.offsetC(), -TrvControl::feedbackLimitC);
    EXPECT_EQ(out.flowC, 45 - TrvControl::feedbackLimitC);
    // Never below the plan's minimum.
    EXPECT_EQ(trv.adjust(heat(32), rooms, true, t, 30, 60).flowC, 30);
    // Fully open and still 0.5 degC cold: raises again.
    rooms[0] = room("slaapkamer", 2000, 1900);
    for (int i = 0; i < 30; ++i) { t += 10 * M; trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":100})", t); out = trv.adjust(heat(45), rooms, true, t, 30, 60); }
    EXPECT_EQ(trv.offsetC(), TrvControl::feedbackLimitC);
    EXPECT_EQ(trv.adjust(heat(58), rooms, true, t, 30, 60).flowC, 60);  // never above the plan maximum
    // It never turns heat on.
    EXPECT_FALSE(trv.adjust(FlowDemand::Request{}, rooms, true, t, 30, 60).heat);
}

TEST(TrvFeedback, AllDemandingRoomsClosedStopsTheRequestButAnUncontrolledRoomKeepsIt) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1990)};
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":0})", 1);
    EXPECT_TRUE(trv.adjust(heat(40), rooms, true, 5 * M, 30, 60).heat);  // closed for 5 min only
    const auto out = trv.adjust(heat(40), rooms, true, 11 * M, 30, 60);
    EXPECT_FALSE(out.heat);
    EXPECT_STREQ(trv.reason(), "valves_closed");
    // The living room (floor, no valve control) asks for heat too: the boiler keeps going.
    rooms.push_back(room("woonkamer", 2100, 1900));
    EXPECT_TRUE(trv.adjust(heat(40), rooms, true, 12 * M, 30, 60).heat);
    // An offline valve is no proof of a closed circuit: no stop.
    std::vector<TrvControl::Room> only{room("slaapkamer", 2000, 1990)};
    EXPECT_TRUE(trv.adjust(heat(40), only, true, 1 + TrvControl::staleMs, 30, 60).heat);
}

TEST(TrvFeedback, ValvesWithoutReadbackDriftTheOffsetBackToZero) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1950)};
    uint64_t t = 1;
    for (int i = 0; i < 4; ++i) { trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"pi_heating_demand":20})", t); trv.adjust(heat(45), rooms, true, t, 30, 60); t += 10 * M; }
    EXPECT_EQ(trv.offsetC(), -4);
    // The valve goes offline: the offset returns to the rule step by step.
    t += TrvControl::staleMs;
    for (int i = 0; i < 6; ++i) { trv.adjust(heat(45), rooms, true, t, 30, 60); t += 10 * M; }
    EXPECT_EQ(trv.offsetC(), 0);
}

TEST(TrvConfigChange, NewConfigKeepsKnownValvesAndResendsModeOnce) {
    TrvControl trv; trv.setConfig(parse(bedroomBosch));
    trv.receive("zigbee2mqtt/Slaapkamer kraan", R"({"battery":70})", 1);
    const auto g = trv.generation();
    trv.setConfig(parse(bedroomBosch));
    EXPECT_GT(trv.generation(), g);
    EXPECT_EQ(trv.health("Slaapkamer kraan", 2), TrvControl::Health::ok);
    Sent sent;
    trv.step(3, {room("slaapkamer", 2000, 1900)}, true, recorder(sent));
    ASSERT_FALSE(sent.all.empty());
    EXPECT_EQ(sent.all[0].second, R"({"operating_mode":"manual"})");
    // Removing every valve resets the feedback and the status disappears again.
    trv.setConfig(TrvConfig{});
    EXPECT_EQ(trv.statusJson(4, {}), nullptr);
    EXPECT_TRUE(trv.subscriptions().empty());
}
}  // namespace
