// Radiator valves against simulated Zigbee2MQTT TRVs (beta.24): the failure cases and a two-week soak.
// SimTrv is the device as Zigbee2MQTT shows it: it takes <base>/<name>/set, regulates its own opening
// towards its setpoint (with the external temperature where it has one), drains its battery per radio
// message and reports its state on a change and at least every 10 minutes, unless it is offline.
#include "control/TrvControl.h"
#include <cmath>
#include <gtest/gtest.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace {
using namespace heating::control;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
constexpr uint64_t second = 1000, minute = 60 * second, hour = 60 * minute, day = 24 * hour;

struct SimTrv {
    std::string name; const TrvModel* model;
    double setpoint = 21, internal = 19, external = NAN, battery = 100, position = 0;
    std::string mode = "schedule", select = "local_temperature";
    bool online = true, stuckOpen = false;
    uint64_t reportedAt = 0, externalAt = 0; int lastReported = -1;
    size_t received = 0;

    void command(const std::string& payload, uint64_t now) {
        if (!online) return;
        ++received; battery -= 0.002;  // a radio message costs a little battery
        Json j(cJSON_Parse(payload.c_str()), cJSON_Delete);
        ASSERT_TRUE(j) << payload;
        for (const cJSON* m = j->child; m; m = m->next) {
            const std::string key = m->string;
            if (key == model->setpointKey) setpoint = m->valuedouble;
            else if (model->externalKey && key == model->externalKey) { external = m->valuedouble; externalAt = now; }
            else if (model->enableKey && key == model->enableKey) mode = m->valuestring;
            else if (model->externalSelectKey && key == model->externalSelectKey) {
                // Zigbee2MQTT refuses a remote select before an external value.
                EXPECT_FALSE(std::isnan(external)) << name;
                select = m->valuestring;
            }
            else ADD_FAILURE() << name << ": unexpected key " << key;
        }
    }
    // The valve's own regulator; the Bosch falls back to its own sensor 30 min after the last external value.
    void regulate(uint64_t now, double room) {
        internal = room + 0.8;  // the valve sits by the radiator
        const double measured = !std::isnan(external) && now - externalAt < 30 * minute ? external : internal;
        position = stuckOpen ? 100 : std::clamp((setpoint - measured) * 60, 0.0, 100.0);
        battery -= 0.0000003;   // standby drain, about 2.6 %/year at 10 s steps
    }
    void report(uint64_t now, TrvControl& trv) {
        if (!online) return;
        const int pos = int(std::lround(position));
        if (reportedAt && now - reportedAt < 10 * minute && std::abs(pos - lastReported) < 5) return;
        reportedAt = now; lastReported = pos;
        std::string p = "{\"" + std::string(model->setpointKey) + "\":" + std::to_string(setpoint) + ",\"local_temperature\":" + std::to_string(internal);
        if (model->positionKey) p += ",\"" + std::string(model->positionKey) + "\":" + std::to_string(pos);
        if (model->batteryKey) p += ",\"" + std::string(model->batteryKey) + "\":" + std::to_string(int(battery));
        if (model->batteryLowKey) p += ",\"" + std::string(model->batteryLowKey) + "\":" + (battery <= 20 ? "true" : "false");
        if (model->externalSelectKey) p += ",\"" + std::string(model->externalSelectKey) + "\":\"" + select + "\"";
        EXPECT_TRUE(trv.receive("zigbee2mqtt/" + name, p + "}", now));
    }
};

struct House {
    TrvControl trv;
    std::map<std::string, SimTrv> valves;
    std::map<std::string, double> temperature;      // the room's real temperature
    std::map<std::string, bool> measured;           // its own sensor reports (false: lost, e.g. HA down)
    std::map<std::string, int16_t> target;
    std::map<std::string, size_t> sources;
    bool output = true, boilerHeat = false;
    uint64_t now = 0;
    std::map<std::string, size_t> sends, setpointSends;
    std::vector<std::string> ids;

    explicit House(TrvConfig config) {
        for (const auto& r : config.rooms) {
            ids.push_back(r.id);
            temperature[r.id] = 19; measured[r.id] = true; target[r.id] = 2100; sources[r.id] = 2;
            for (const auto& v : r.valves) valves[v.name] = SimTrv{v.name, v.model};
        }
        trv.setConfig(std::move(config));
    }
    std::vector<TrvControl::Room> rooms() const {
        std::vector<TrvControl::Room> out;
        for (const auto& id : ids) {
            TrvControl::Room r;
            r.id = id; r.active = true; r.setpoint = target.at(id); r.sources = sources.at(id);
            if (measured.at(id)) r.temperature = int16_t(std::lround(temperature.at(id) * 100));
            r.errorCentiC = r.temperature ? int16_t(*r.setpoint - *r.temperature) : 0;
            r.demanding = r.temperature && r.errorCentiC > 0;
            out.push_back(r);
        }
        return out;
    }
    FlowDemand::Request tick(FlowDemand::Request request = {true, 45, FlowDemand::Reason::heating}) {
        now += 10 * second;
        const auto views = rooms();
        const auto adjusted = trv.adjust(request, views, output, now, 30, 60);
        trv.step(now, views, output, [&](const std::string& topic, const std::string& payload) {
            const auto name = topic.substr(std::string("zigbee2mqtt/").size(), topic.size() - std::string("zigbee2mqtt/").size() - 4);
            EXPECT_EQ(topic.substr(topic.size() - 4), "/set");
            auto& v = valves.at(name);
            ++sends[name];
            if (payload.find(v.model->setpointKey) != std::string::npos) ++setpointSends[name];
            v.command(payload, now);
            return true;
        });
        // Each room warms with its valves' mean opening while the boiler fires, and cools towards 15 degC.
        boilerHeat = adjusted.heat;
        for (const auto& id : ids) {
            double open = 0; size_t n = 0;
            for (const auto& [name, v] : valves) if (trv.config().room(id) && std::any_of(trv.config().room(id)->valves.begin(),
                trv.config().room(id)->valves.end(), [&](const auto& c) { return c.name == name; })) { open += v.position; ++n; }
            auto& t = temperature[id];
            t += (boilerHeat && n ? open / n / 100 * 0.004 : 0) - (t - 15) * 0.00012;
        }
        for (auto& [name, v] : valves) {
            for (const auto& id : ids) if (const auto* r = trv.config().room(id))
                for (const auto& c : r->valves) if (c.name == name) v.regulate(now, temperature[id]);
            v.report(now, trv);
        }
        return adjusted;
    }
    void run(uint64_t span) { for (const uint64_t end = now + span; now < end;) tick(); }
};

TrvConfig config(bool control = true) {
    Json j(cJSON_Parse(control
        ? R"({"schema":1,"rooms":[{"room":"woonkamer","control":true,"valves":[{"name":"Kraan raam","model":"bosch_bth_ra"},{"name":"Kraan hoek","model":"bosch_bth_ra"}]},
             {"room":"slaapkamer","control":true,"valves":[{"name":"Kraan slaapkamer","model":"sonoff_trvzb"},{"name":"Kraan oud","model":"tuya_tv02"},{"name":"Kraan gen2","model":"sonoff_trv_zbt"}]}]})"
        : R"({"schema":1,"rooms":[{"room":"woonkamer","control":false,"valves":[{"name":"Kraan raam","model":"bosch_bth_ra"}]}]})"), cJSON_Delete);
    TrvConfig c;
    EXPECT_EQ(TrvConfig::parse(j.get(), c), nullptr);
    return c;
}
const char* health(const TrvControl& trv, const std::string& name, uint64_t now) {
    switch (trv.health(name, now)) {
    case TrvControl::Health::ok: return "ok";
    case TrvControl::Health::lowBattery: return "low_battery";
    case TrvControl::Health::offline: return "offline";
    default: return "unknown";
    }
}
bool degraded(const TrvControl& trv, const House& h, const char* room) {
    Json s(trv.statusJson(h.now, h.rooms()), cJSON_Delete);
    for (const cJSON* r = cJSON_GetObjectItem(s.get(), "rooms")->child; r; r = r->next)
        if (std::string(cJSON_GetObjectItem(r, "room")->valuestring) == room) return cJSON_IsTrue(cJSON_GetObjectItem(r, "degraded"));
    ADD_FAILURE() << room;
    return false;
}
}

TEST(TrvSimulation, TwoWeeksOfFourValvesStayWithinTheBatteryBudget) {
    House h(config());
    for (int d = 0; d < 14; ++d) {
        auto before = h.sends; auto setpointsBefore = h.setpointSends;
        for (int step = 0; step < 4; ++step) {     // four program steps a day: 21, 18, 21, 16 degC
            for (const auto& id : h.ids) h.target[id] = int16_t(step % 2 ? (step == 1 ? 1800 : 1600) : 2100);
            h.run(6 * hour);
        }
        for (const auto& [name, v] : h.valves) {
            const size_t sent = h.sends[name] - before[name], setpoints = h.setpointSends[name] - setpointsBefore[name];
            // External temperature at most every 10 min (<= 144) plus a few setpoints; a TV02 only setpoints.
            EXPECT_LE(sent, v.model->externalKey ? 160u : 12u) << name << " day " << d;
            EXPECT_LE(setpoints, 12u) << name << " day " << d;
            EXPECT_GE(setpoints, 4u) << name << " day " << d;  // every program step reaches the valve
        }
        EXPECT_LE(std::abs(h.trv.offsetC()), TrvControl::feedbackLimitC);
    }
    for (const auto& [name, v] : h.valves) {
        EXPECT_GT(v.battery, 98) << name;                // two weeks cost well under 2 % per valve
        EXPECT_NEAR(v.setpoint, 16, 0.01) << name;        // the last program step
        EXPECT_EQ(v.mode, v.model->enableValue ? v.model->enableValue : "schedule") << name;
        if (v.model->externalSelectKey) { EXPECT_EQ(v.select, v.model->externalSelectValue) << name; }
        EXPECT_STREQ(health(h.trv, name, h.now), "ok") << name;
    }
}

TEST(TrvSimulation, LowBatteryWarnsEarlyWhileTheValveKeepsBeingDriven) {
    House h(config());
    h.valves.at("Kraan raam").battery = 19.5;
    h.valves.at("Kraan oud").battery = 19.5;       // the TV02 only has a low flag
    h.run(15 * minute);
    EXPECT_STREQ(health(h.trv, "Kraan raam", h.now), "low_battery");
    EXPECT_STREQ(health(h.trv, "Kraan oud", h.now), "low_battery");
    EXPECT_STREQ(health(h.trv, "Kraan hoek", h.now), "ok");
    const auto sent = h.sends["Kraan raam"];
    h.target["woonkamer"] = 2000; h.run(5 * minute);
    EXPECT_GT(h.sends["Kraan raam"], sent);        // still driven: a warning, not a stop
    EXPECT_FALSE(degraded(h.trv, h, "woonkamer"));
}

TEST(TrvSimulation, AnOfflineValveLeavesTheRoomDegradedButHeatingAndGetsEverythingAgainWhenBack) {
    House h(config());
    h.run(30 * minute);
    auto& gone = h.valves.at("Kraan raam");
    gone.online = false;
    h.run(TrvControl::staleMs + 10 * minute);
    EXPECT_STREQ(health(h.trv, "Kraan raam", h.now), "offline");
    EXPECT_TRUE(degraded(h.trv, h, "woonkamer"));
    // Even with the other valve closed, an offline valve never counts as closed: the boiler keeps its request.
    h.valves.at("Kraan hoek").setpoint = 5; h.temperature["woonkamer"] = 19;
    for (int i = 0; i < 120; ++i) EXPECT_TRUE(h.tick().heat);
    // Back with fresh batteries and factory settings: mode, setpoint and external temperature again.
    gone = SimTrv{"Kraan raam", gone.model};
    gone.reportedAt = 0;
    gone.report(h.now, h.trv);
    const auto before = gone.received;
    h.tick();
    EXPECT_EQ(gone.mode, "manual");
    EXPECT_NEAR(gone.setpoint, 21, 0.01);
    EXPECT_FALSE(std::isnan(gone.external));
    EXPECT_EQ(gone.received - before, 3u);         // three messages, no burst
    EXPECT_FALSE(degraded(h.trv, h, "woonkamer"));
}

TEST(TrvSimulation, FailOpenWithoutOutputNothingIsSentAndTheValvesKeepTheirLastSetpoint) {
    House h(config());
    h.target["woonkamer"] = 2200; h.run(20 * minute);
    const auto sends = h.sends;
    h.output = false;                               // handed back, takeover lost, or not the boiler's controller
    for (int i = 0; i < 6 * 360; ++i) {
        const FlowDemand::Request request{true, 41, FlowDemand::Reason::heating};
        const auto out = h.tick(request);
        ASSERT_TRUE(out.heat == request.heat && out.flowC == request.flowC);
    }
    EXPECT_EQ(h.sends, sends);
    EXPECT_FALSE(h.trv.actuatorOutput());
    EXPECT_NEAR(h.valves.at("Kraan raam").setpoint, 22, 0.01);  // the valve regulates on by itself
    // Output back: the mode once more and the current target, nothing stale.
    h.output = true; h.target["woonkamer"] = 2050;
    h.tick();
    EXPECT_EQ(h.valves.at("Kraan raam").mode, "manual");
    EXPECT_NEAR(h.valves.at("Kraan raam").setpoint, 20.5, 0.01);
}

TEST(TrvSimulation, AllValvesClosedWhileRoomsAskStopsTheBoilerAfterTheHold) {
    Json j(cJSON_Parse(R"({"schema":1,"rooms":[{"room":"woonkamer","control":true,"valves":[{"name":"Kraan raam","model":"bosch_bth_ra"}]}]})"), cJSON_Delete);
    TrvConfig c; ASSERT_EQ(TrvConfig::parse(j.get(), c), nullptr);
    House h(std::move(c));
    h.target["woonkamer"] = 2150; h.temperature["woonkamer"] = 21.0;
    h.run(5 * minute);
    // The valve thinks the room is warm (a radiator cover, a sun-lit valve): it closes while the room asks.
    auto& v = h.valves.at("Kraan raam"); v.setpoint = 5;
    h.run(TrvControl::closedHoldMs - minute);
    EXPECT_TRUE(h.boilerHeat);                      // not yet: the hold rides out a short close
    h.run(3 * minute);
    EXPECT_FALSE(h.boilerHeat);
    EXPECT_STREQ(h.trv.reason(), "valves_closed");
    // A stuck-open valve (fail-open) gives the request back, after the burner's minimum off time.
    v.stuckOpen = true; h.run(FlowDemand::Params{}.minimumOffMs);
    EXPECT_TRUE(h.boilerHeat);
}

TEST(TrvSimulation, Zigbee2MqttRestartAndHomeAssistantDownCauseNoBurstAndNoBlindHeat) {
    House h(config());
    h.run(hour);
    // Zigbee2MQTT restarts: five minutes without any report, then the same state again.
    for (auto& [n, v] : h.valves) v.online = false;
    auto sends = h.sends;
    h.run(5 * minute);
    for (auto& [n, v] : h.valves) { v.online = true; v.reportedAt = 0; }
    h.run(5 * minute);
    for (const auto& [name, n] : h.sends) EXPECT_LE(n - sends[name], 2u) << name;   // only the due external values
    // Home Assistant down: the living room's own sensor is gone. No external temperature is sent then
    // (a stale one would steer the valve blind); the valve uses its own sensor after its timeout.
    h.measured["woonkamer"] = false;
    const auto externalBefore = h.valves.at("Kraan raam").externalAt;
    h.run(2 * hour);
    EXPECT_EQ(h.valves.at("Kraan raam").externalAt, externalBefore);
    EXPECT_GT(h.now - h.valves.at("Kraan raam").externalAt, 30 * minute);
    // The setpoint still follows the program; the room engine's own 30-minute rule ends its heat demand.
    h.target["woonkamer"] = 1800; h.run(2 * minute);
    EXPECT_NEAR(h.valves.at("Kraan raam").setpoint, 18, 0.01);
    h.measured["woonkamer"] = true; h.run(11 * minute);
    EXPECT_GT(h.valves.at("Kraan raam").externalAt, externalBefore);
}

TEST(TrvSimulation, AnMqttStormIsBoundedAndNeverAmplifiesWrites) {
    House quiet(config()), storm(config());
    quiet.run(hour); storm.run(hour);
    const std::string big(TrvControl::maxPayloadBytes + 1, ' ');
    for (int burst = 0; burst < 60; ++burst) {
        for (int i = 0; i < 1000; ++i) {
            ASSERT_TRUE(storm.trv.receive("zigbee2mqtt/Kraan raam", R"({"pi_heating_demand":)" + std::to_string(i % 100) + R"(,"battery":90})", storm.now));
            ASSERT_TRUE(storm.trv.receive("zigbee2mqtt/Kraan raam", big, storm.now));          // oversized: ignored
            ASSERT_TRUE(storm.trv.receive("zigbee2mqtt/Kraan raam", "{not json", storm.now));
            ASSERT_FALSE(storm.trv.receive("zigbee2mqtt/Someone else", "{}", storm.now));     // not ours
            ASSERT_FALSE(storm.trv.receive("zigbee2mqtt/Kraan raam/set", "{}", storm.now));   // our own commands
        }
        quiet.tick(); storm.tick();
    }
    for (const auto& [name, n] : quiet.sends) EXPECT_EQ(storm.sends[name], n) << name;
    EXPECT_STREQ(health(storm.trv, "Kraan raam", storm.now), "ok");
}

TEST(TrvSimulation, ControlOffLeavesEverySimulatedValveUntouchedForAWeek) {
    House h(config(false));
    h.run(7 * day);
    EXPECT_TRUE(h.sends.empty());
    EXPECT_EQ(h.valves.at("Kraan raam").received, 0u);
    EXPECT_EQ(h.valves.at("Kraan raam").mode, "schedule");
    EXPECT_FALSE(h.trv.actuatorOutput());
}
