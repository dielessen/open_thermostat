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
    // No room measurement: no external value and no sensor select (the valve keeps its own sensor).
    ASSERT_EQ(sent.all.size(), 2u);
    EXPECT_EQ(sent.all[0].second, R"({"system_mode":"heat"})");
    EXPECT_EQ(sent.all[1].second, R"({"occupied_heating_setpoint":8.0})");
}

// Zigbee2MQTT refuses a remote sensor select before an external value, so the select comes last.
TEST(TrvCommands, SonoffGen2GetsHeatModeSetpointExternalValueThenTheSensorSelect) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"b","control":true,"valves":[{"name":"G2","model":"sonoff_trv_zbt"}]}]})"));
    Sent sent;
    trv.step(1, {room("b", 3400, 1950)}, true, recorder(sent));
    ASSERT_EQ(sent.all.size(), 4u);
    EXPECT_EQ(sent.all[0], std::make_pair(std::string("zigbee2mqtt/G2/set"), std::string(R"({"system_mode":"heat"})")));
    EXPECT_EQ(sent.all[1].second, R"({"occupied_heating_setpoint":30.0})");  // clamped to the TRV-ZBT's 30 degC
    EXPECT_EQ(sent.all[2].second, R"({"external_temperature_input":19.50})");
    EXPECT_EQ(sent.all[3].second, R"({"temperature_sensor_select":"remote_temperature"})");
}

TEST(TrvCommands, SonoffSelectFollowsTheReportedValuesAndIsAskedAgainWhileTheValveKeepsItsOwnSensor) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"b","control":true,"valves":[{"name":"V","model":"sonoff_trvzb"}]}]})"));
    const std::vector<TrvControl::Room> rooms{room("b", 2100, 1900)};
    const auto selects = [](const Sent& s) {
        std::vector<std::string> out;
        for (const auto& [t, p] : s.all) if (p.find("temperature_sensor_select") != std::string::npos) out.push_back(p);
        return out;
    };
    // Older Zigbee2MQTT reports internal/external: the select uses "external".
    trv.receive("zigbee2mqtt/V", R"({"temperature_sensor_select":"internal","battery":90})", 500);
    Sent sent;
    trv.step(1000, rooms, true, recorder(sent));
    ASSERT_EQ(selects(sent), std::vector<std::string>{R"({"temperature_sensor_select":"external"})"});
    // Still its own sensor 10 min later (the write got lost): asked once more, not every step.
    trv.receive("zigbee2mqtt/V", R"({"temperature_sensor_select":"internal"})", 1000 + M);
    sent.all.clear();
    for (uint64_t t = 1000 + M; t < 1000 + 10 * M; t += 10000) trv.step(t, rooms, true, recorder(sent));
    EXPECT_TRUE(selects(sent).empty());
    trv.step(1000 + 10 * M, rooms, true, recorder(sent));
    EXPECT_EQ(selects(sent).size(), 1u);
    // Selected now: nothing more.
    trv.receive("zigbee2mqtt/V", R"({"temperature_sensor_select":"external"})", 1000 + 11 * M);
    sent.all.clear();
    for (uint64_t t = 1000 + 11 * M; t < 1000 + 120 * M; t += 10000) trv.step(t, rooms, true, recorder(sent));
    EXPECT_TRUE(selects(sent).empty());

    // Current Zigbee2MQTT: remote_temperature, and remote_source_offline counts as selected.
    TrvControl now;
    now.setConfig(parse(R"({"schema":1,"rooms":[{"room":"b","control":true,"valves":[{"name":"V","model":"sonoff_trvzb"}]}]})"));
    now.receive("zigbee2mqtt/V", R"({"temperature_sensor_select":"local_temperature"})", 500);
    sent.all.clear();
    now.step(1000, rooms, true, recorder(sent));
    ASSERT_EQ(selects(sent), std::vector<std::string>{R"({"temperature_sensor_select":"remote_temperature"})"});
    now.receive("zigbee2mqtt/V", R"({"temperature_sensor_select":"remote_source_offline"})", 1000 + M);
    sent.all.clear();
    for (uint64_t t = 1000 + M; t < 1000 + 60 * M; t += 10000) now.step(t, rooms, true, recorder(sent));
    EXPECT_TRUE(selects(sent).empty());
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

// ---- Home Assistant valves (ha_climate) ----------------------------------------------------

TEST(TrvHaClimate, TheNameIsAClimateEntityId) {
    const auto c = parse(R"({"schema":1,"rooms":[{"room":"a","control":true,"valves":[{"name":"climate.bedroom_trv_2","model":"ha_climate"},)"
                         R"({"name":"climate.zigbee_name","model":"generic"}]}]})");
    ASSERT_EQ(c.rooms[0].valves.size(), 2u);
    EXPECT_STREQ(c.rooms[0].valves[0].model->label, "Home Assistant climate entity");
    EXPECT_EQ(parse(c.json().c_str()), c);
    const char* error = nullptr;
    for (const char* name : {"Bedroom valve", "climate.", "climate.Bedroom", "climate.a-b", "climate.a.b", "sensor.bedroom",
                             " climate.a", "climate.a b"}) {
        const std::string text = std::string(R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":")") + name + R"(","model":"ha_climate"}]}]})";
        parse(text.c_str(), &error);
        EXPECT_STREQ(error, "invalid_valve_name") << name;
    }
    const std::string tooLong = R"({"schema":1,"rooms":[{"room":"a","valves":[{"name":"climate.)" + std::string(57, 'x')
                                + R"(","model":"ha_climate"}]}]})";
    parse(tooLong.c_str(), &error);
    EXPECT_STREQ(error, "invalid_valve_name");
}

// One run over 6 h: reports, a target change, a room going inactive, output on after 30 min.
struct Run { Sent sent; std::vector<std::pair<bool, uint8_t>> requests; std::vector<std::string> reasons; std::string status; };
Run scenario(const char* config) {
    TrvControl trv; trv.setConfig(parse(config));
    Run run;
    std::vector<TrvControl::Room> rooms{room("slaapkamer", 2000, 1950), room("keuken", 2100, 1800), room("zolder", 2000, 1800)};
    uint64_t t = 1;
    for (int i = 0; i < 6 * 60; ++i, t += M) {
        if (i % 10 == 0) {
            EXPECT_TRUE(trv.receive("zigbee2mqtt/Slaapkamer kraan", i < 120 ? R"({"pi_heating_demand":30,"battery":70})" : R"({"pi_heating_demand":100})", t));
            EXPECT_TRUE(trv.receive("zigbee2mqtt/Keuken", R"({"battery":60,"temperature_sensor_select":"local_temperature"})", t));
            // A Home Assistant valve's name on the Zigbee2MQTT base is never ours.
            EXPECT_FALSE(trv.receive("zigbee2mqtt/climate.slaapkamer_trv", R"({"pi_heating_demand":0,"battery":5})", t));
        }
        if (i == 90) rooms[0].setpoint = 2150;
        if (i == 200) rooms[1].active = false;
        if (i == 240) rooms[0].temperature = 1900;
        trv.step(t, rooms, i >= 30, recorder(run.sent));
        const auto out = trv.adjust(heat(45), rooms, i >= 30, t, 30, 60);
        run.requests.emplace_back(out.heat, out.flowC);
        run.reasons.emplace_back(trv.reason() ? trv.reason() : "-");
    }
    // The status of the rooms with Zigbee2MQTT valves, those valves only.
    Json status(trv.statusJson(t, rooms), cJSON_Delete);
    for (cJSON* r = cJSON_GetObjectItem(status.get(), "rooms")->child; r; r = r->next) {
        cJSON* valves = cJSON_GetObjectItem(r, "valves");
        for (int k = cJSON_GetArraySize(valves) - 1; k >= 0; --k)
            if (std::string(cJSON_GetObjectItem(cJSON_GetArrayItem(valves, k), "model")->valuestring) == "ha_climate") cJSON_DeleteItemFromArray(valves, k);
        if (!cJSON_GetArraySize(valves)) continue;
        char* text = cJSON_PrintUnformatted(r);
        run.status += text;
        cJSON_free(text);
    }
    return run;
}

// The same Zigbee2MQTT valves with and without Home Assistant valves beside them: the same
// subscriptions, commands, boiler feedback and status per Zigbee2MQTT valve; nothing for HA's.
TEST(TrvHaClimate, NothingIsSubscribedOrSentAndZigbeeValvesBehaveExactlyAsBefore) {
    const char* zigbee =
        R"({"schema":1,"rooms":[{"room":"slaapkamer","control":true,"valves":[{"name":"Slaapkamer kraan","model":"bosch_bth_ra"}]},)"
        R"({"room":"keuken","control":true,"valves":[{"name":"Keuken","model":"sonoff_trvzb"}]}]})";
    const char* mixed =
        R"({"schema":1,"rooms":[{"room":"slaapkamer","control":true,"valves":[{"name":"Slaapkamer kraan","model":"bosch_bth_ra"},)"
        R"({"name":"climate.slaapkamer_trv","model":"ha_climate"}]},)"
        R"({"room":"keuken","control":true,"valves":[{"name":"climate.keuken_trv","model":"ha_climate"},{"name":"Keuken","model":"sonoff_trvzb"}]},)"
        R"({"room":"zolder","control":true,"valves":[{"name":"climate.zolder","model":"ha_climate"}]}]})";
    TrvControl a, b; a.setConfig(parse(zigbee)); b.setConfig(parse(mixed));
    EXPECT_EQ(a.subscriptions(), b.subscriptions());
    EXPECT_EQ(b.subscriptions(), (std::vector<std::string>{"zigbee2mqtt/Slaapkamer kraan", "zigbee2mqtt/Keuken"}));
    const auto before = scenario(zigbee), after = scenario(mixed);
    ASSERT_GT(before.sent.all.size(), 5u);
    EXPECT_EQ(before.sent.all, after.sent.all);
    for (const auto& sent : after.sent.all) EXPECT_EQ(sent.first.find("climate."), std::string::npos) << sent.first;
    EXPECT_EQ(before.requests, after.requests);
    EXPECT_EQ(before.reasons, after.reasons);
    EXPECT_FALSE(before.status.empty());
    EXPECT_EQ(before.status, after.status);
}

TEST(TrvHaClimate, OnlyHaValvesSendNothingButAreListedWithUnknownHealthAndSetTheOutputFlag) {
    TrvControl trv;
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"zolder","control":true,"valves":[{"name":"climate.zolder","model":"ha_climate"}]}]})"));
    EXPECT_TRUE(trv.used());
    EXPECT_TRUE(trv.subscriptions().empty());
    const std::vector<TrvControl::Room> rooms{room("zolder", 2000, 1800, true, 1)};
    Sent sent;
    for (uint64_t t = 1; t < 8 * 3600 * 1000ULL; t += 10 * 1000ULL) {
        trv.step(t, rooms, true, recorder(sent));
        const auto out = trv.adjust(heat(45), rooms, true, t, 30, 60);
        ASSERT_TRUE(out.heat); ASSERT_EQ(out.flowC, 45);    // no readback: no feedback
    }
    EXPECT_TRUE(sent.all.empty());
    EXPECT_EQ(trv.offsetC(), 0);
    EXPECT_EQ(trv.reason(), nullptr);
    // "output": the valve route is live, so Home Assistant drives the room's valves now.
    EXPECT_TRUE(trv.actuatorOutput());
    trv.step(1, rooms, false, recorder(sent));
    EXPECT_FALSE(trv.actuatorOutput());
    Json status(trv.statusJson(1, rooms), cJSON_Delete);
    ASSERT_TRUE(status);
    const auto* r = cJSON_GetArrayItem(cJSON_GetObjectItem(status.get(), "rooms"), 0);
    EXPECT_FALSE(cJSON_IsTrue(cJSON_GetObjectItem(r, "degraded")));      // HA judges these valves
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(r, "single_source")));
    const auto* v = cJSON_GetArrayItem(cJSON_GetObjectItem(r, "valves"), 0);
    EXPECT_STREQ(cJSON_GetObjectItem(v, "name")->valuestring, "climate.zolder");
    EXPECT_STREQ(cJSON_GetObjectItem(v, "model")->valuestring, "ha_climate");
    EXPECT_STREQ(cJSON_GetObjectItem(v, "health")->valuestring, "unknown");
    EXPECT_EQ(cJSON_GetObjectItem(v, "battery_pct"), nullptr);
    // A Zigbee2MQTT valve of that name re-added as a Home Assistant one keeps nothing of its reports.
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"zolder","control":true,"valves":[{"name":"climate.zolder","model":"generic"}]}]})"));
    trv.receive("zigbee2mqtt/climate.zolder", R"({"battery":10})", 2);
    EXPECT_EQ(trv.health("climate.zolder", 3), TrvControl::Health::lowBattery);
    trv.setConfig(parse(R"({"schema":1,"rooms":[{"room":"zolder","control":true,"valves":[{"name":"climate.zolder","model":"ha_climate"}]}]})"));
    EXPECT_EQ(trv.health("climate.zolder", 3), TrvControl::Health::unknown);
    EXPECT_FALSE(trv.receive("zigbee2mqtt/climate.zolder", R"({"battery":10})", 4));
}
}  // namespace
