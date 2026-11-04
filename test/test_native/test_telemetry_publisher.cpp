#include "control/TelemetryPublisher.h"
#include "control/TrvControl.h"
#include <gtest/gtest.h>
#include <map>
#include <string>
#include <vector>

// TelemetryPublisher: cadences, deadbands, spreading, backpressure and the
// clearing of topics that left the plan, against fake sources.
namespace {
using namespace heating::control;
struct Sent { std::string topic, payload; bool retained; uint64_t at; };
struct Bench {
    uint64_t now = 1000;
    std::vector<Sent> sent;
    bool ready = true, accept = true;
    std::vector<std::string> rooms{"woonkamer", "keuken", "badkamer"};
    std::map<std::string, double> temperature{{"woonkamer", 20.5}, {"keuken", 19.0}, {"badkamer", 21.0}};
    int flow = 40;
    int boilerFlow = 4500;
    std::string learnedResult = "learning";
    std::string scoreboard;    // rc.4: the summary source's "scoreboard" object, when set (HeatingController's Scoreboard::addJson)
    std::string insight;       // rc.5: the summary source's "insight" object, when set (HeatingController's addInsightJson)
    TrvControl* trv = nullptr; // radiator valves, added to the status as HeatingController does
    TelemetryPublisher publisher{
        TelemetryPublisher::Sources{
            [this] {
                std::string rows, entities;
                for (const auto& id : rooms) {
                    char t[16]; std::snprintf(t, sizeof t, "%.2f", temperature[id]);
                    rows += std::string(rows.empty() ? "" : ",") + R"({"id":")" + id + R"(","name":"R","state":"active","status":"ok","temperature":)" + t + R"(,"setpoint":21,"demand":true})";
                    entities += std::string(entities.empty() ? "" : ",") + "\"climate." + id + "\"";
                }
                const std::string s = R"({"schema":1,"revision":3,"mode":"shadow","request":{"heat":true,"flow_c":)" + std::to_string(flow)
                    + R"(,"reason":"heating"},"ha_entities":[)" + entities + R"(],"rooms":[)" + rows
                    + R"(],"ble_sensors":[{"id":"a4c138a3e8db","temperature":19.5,"humidity":50,"battery":90,"age_s":)" + std::to_string(now / 1000)
                    + R"(}],"shadow":{"today":{"s":)" + std::to_string(now / 1000) + R"(}},"ha":{"input_age_s":)" + std::to_string(now / 1000 % 300) + R"(,"broker_connected":true}})";
                cJSON* status = cJSON_Parse(s.c_str());
                if (cJSON* valves = trv && status ? trv->statusJson(now, {}) : nullptr) cJSON_AddItemToObject(status, "trv", valves);
                return status;
            },
            [this] { return rooms.size(); },
            [this](size_t i, std::string& id) {
                id = rooms.at(i);
                return R"({"schema":1,"id":")" + id + R"(","learned":{"readiness":")" + learnedResult + R"(","now":{"flow_c":)" + std::to_string(now / 1000 % 50) + "}},\"plan\":null}";
            },
            [this] {
                return std::string(R"({"schema":1,"learned":{"schema":1},"flow":{"source":"rule"},"night_gas":{"m3":0.1})")
                    + (scoreboard.empty() ? std::string() : ",\"scoreboard\":" + scoreboard)
                    + (insight.empty() ? std::string() : ",\"insight\":" + insight) + "}";
            },
            [this](std::string& out, size_t group) {
                if (group != 0) { out.clear(); return; }
                std::string rows;
                for (size_t i = 0; i < 10; ++i) {
                    const auto& spec = heating::ems::boilerFieldSpecs[i];
                    (void)spec;
                    const int raw = i == 1 ? boilerFlow : i == 2 ? 4000 : i == 4 ? 30 : i == 6 ? 15 : i == 3 ? 500 : i == 5 ? 100 : 0;
                    const int quality = boilerFieldQualities[i];
                    rows += std::string(i ? "," : "") + "[" + std::to_string(i) + "," + std::to_string(raw) + "," + std::to_string(now - 500) + ","
                        + std::to_string(quality) + "," + std::to_string(boilerFieldSourceTypes[i]) + "]";
                }
                out = R"({"schema":1,"sampled_at_ms":)" + std::to_string(now) + R"(,"profile":"classic_observed","fields":[)" + rows + "]}";
            },
            [this] { return std::string(R"({"schema":1,"uptime_s":)") + std::to_string(now / 1000) + "}"; }},
        [this](const std::string& topic, std::string_view payload, bool retained) {
            if (!accept) return false;
            sent.push_back({topic, std::string(payload), retained, now});
            return true;
        },
        [this] { return ready; }};
    void run(uint64_t ms) { for (uint64_t end = now + ms; now < end; now += 100) publisher.tick(now); }
    size_t count(const std::string& topic, uint64_t since = 0) const {
        size_t n = 0;
        for (const auto& s : sent) n += s.topic == topic && s.at >= since;
        return n;
    }
    std::map<uint64_t, size_t> perSecond() const {
        std::map<uint64_t, size_t> m;
        for (const auto& s : sent) if (s.topic != "fw/heartbeat") ++m[s.at / 1000];
        return m;
    }
    // The last payload of a topic sent at or after `since` (empty: none).
    std::string last(const std::string& topic, uint64_t since = 0) const {
        std::string payload;
        for (const auto& s : sent) if (s.topic == topic && s.at >= since) payload = s.payload;
        return payload;
    }
};
}

// rc.4 (B1): HeatingController's summary now carries the daily scoreboard (two days, a rooms
// array per day). Left inside fw/telemetry/summary, six to eight rooms pushed that topic over
// the 1.5 KB hard limit, where send() drops it silently every 5 minutes (Home Assistant then
// lost the learned header and today's hot water too). It goes out on its own topic, like
// "flow" and "tuning"; a source without the key sends nothing there.
TEST(TelemetryPublisher, TheScoreboardGoesOutOnItsOwnTopicAndLeavesTheSummary) {
    Bench b;
    b.publisher.connected(b.now);
    b.run(30000);
    ASSERT_GE(b.count("fw/telemetry/summary"), 1u);
    EXPECT_EQ(b.count("fw/telemetry/scoreboard"), 0u) << "no scoreboard in the source: nothing sent";
    EXPECT_EQ(b.last("fw/telemetry/summary").find("scoreboard"), std::string::npos);
    b.scoreboard = R"({"yesterday":{"day":"2026-11-03","heating_h":9,"rooms":[{"id":"woonkamer","on_time_min":-5,"overshoot_c":0.3}]},)"
                   R"("today":{"day":"2026-11-04","heating_h":3}})";
    const uint64_t at = b.now;
    b.run(310000);                                          // the next 5-minute summary
    ASSERT_EQ(b.count("fw/telemetry/summary", at), 1u);
    ASSERT_EQ(b.count("fw/telemetry/scoreboard", at), 1u);
    EXPECT_EQ(b.last("fw/telemetry/scoreboard", at), R"({"schema":1,"scoreboard":)" + b.scoreboard + "}");
    const auto summary = b.last("fw/telemetry/summary", at);
    EXPECT_EQ(summary.find("scoreboard"), std::string::npos) << summary;
    EXPECT_NE(summary.find(R"("learned":{"schema":1})"), std::string::npos) << summary;
    EXPECT_EQ(summary.find("\"flow\""), std::string::npos) << "flow still goes apart";
    EXPECT_EQ(b.count("fw/telemetry/flow", at), 1u);
    for (const auto& s : b.sent) { if (s.topic == "fw/telemetry/scoreboard") EXPECT_TRUE(s.retained); }
    // The source dropped the key again (no memory for the board): the topic falls silent.
    b.scoreboard.clear();
    const uint64_t again = b.now;
    b.run(310000);
    EXPECT_EQ(b.count("fw/telemetry/summary", again), 1u);
    EXPECT_EQ(b.count("fw/telemetry/scoreboard", again), 0u);
}

// rc.5 (P2): what the E32 knows about the house, its boiler and yesterday goes out on its own topic,
// fw/telemetry/insight, retained, with the summary every 5 minutes: the source's "insight" object's
// members after a schema, {"schema":1,"knowledge":..,"house":..,"boiler":..,"insights":[..]}. The
// summary keeps nothing of it; a source without it sends nothing there.
TEST(TelemetryPublisher, TheInsightGoesOutOnItsOwnTopicAndLeavesTheSummary) {
    Bench b;
    b.publisher.connected(b.now);
    b.run(30000);
    ASSERT_GE(b.count("fw/telemetry/summary"), 1u);
    EXPECT_EQ(b.count("fw/telemetry/insight"), 0u) << "no insight in the source: nothing sent";
    b.scoreboard = R"({"yesterday":null,"today":{"day":"2026-11-04","heating_h":3}})";
    b.insight = R"({"knowledge":{"pct":70,"missing":["curve","boiler_response"],"more":0},)"
                R"("house":{"ua_kw_per_k":0.2,"kw_per_flow_k":0.5,"slope":0.4,"state":"learned"},)"
                R"("boiler":{"held":0,"rest_s":null,"ceiling_c":null,"absorbed_kw":null,"kw_per_k":null,"state":"not_driving"},)"
                R"("insights":[{"kind":"gas_per_dd_up","pct":35}]})";
    const uint64_t at = b.now;
    b.run(310000);                                          // the next 5-minute summary
    ASSERT_EQ(b.count("fw/telemetry/summary", at), 1u);
    ASSERT_EQ(b.count("fw/telemetry/insight", at), 1u);
    EXPECT_EQ(b.count("fw/telemetry/scoreboard", at), 1u) << "all five parts in the same round";
    EXPECT_EQ(b.last("fw/telemetry/insight", at), R"({"schema":1,)" + b.insight.substr(1));
    const auto summary = b.last("fw/telemetry/summary", at);
    for (const char* key : {"insight", "knowledge", "house", "boiler", "insights"})
        EXPECT_EQ(summary.find(std::string("\"") + key + "\""), std::string::npos) << key << ": " << summary;
    for (const auto& s : b.sent) { if (s.topic == "fw/telemetry/insight") EXPECT_TRUE(s.retained); }
    // A reconnect sends it once more; a source that drops it again sends nothing there.
    uint64_t again = b.now;
    b.publisher.connected(b.now);
    b.run(30000);
    EXPECT_EQ(b.count("fw/telemetry/insight", again), 1u);
    b.insight.clear();
    again = b.now;
    b.run(310000);
    EXPECT_EQ(b.count("fw/telemetry/summary", again), 1u);
    EXPECT_EQ(b.count("fw/telemetry/insight", again), 0u);
}

TEST(TelemetryPublisher, AConnectSendsEverythingOnceSpreadOverSeconds) {
    Bench b;
    b.publisher.connected(b.now);
    b.run(30000);
    for (const char* topic : {"fw/state/heating", "fw/state/room/woonkamer", "fw/state/room/keuken", "fw/state/room/badkamer",
                              "fw/state/ble/a4c138a3e8db", "fw/config/plan", "fw/config/entities", "fw/telemetry/shadow",
                              "fw/telemetry/summary", "fw/telemetry/flow", "fw/state/boiler", "fw/state/boiler_fields/0", "fw/telemetry/learned/woonkamer",
                              "fw/telemetry/learned/keuken", "fw/telemetry/learned/badkamer"})
        EXPECT_GE(b.count(topic), 1u) << topic;
    EXPECT_EQ(b.count("fw/heartbeat"), 1u);
    for (const auto& s : b.sent) EXPECT_EQ(s.retained, s.topic != "fw/heartbeat") << s.topic;
    for (const auto& [second, n] : b.perSecond()) EXPECT_LE(n, TelemetryPublisher::burst) << second;
    EXPECT_EQ(b.count("fw/state/boiler_fields/1"), 0u);   // no data for that group: nothing sent
    // Nothing changed beyond its deadband: nothing more for minutes, but the heartbeat.
    const uint64_t quiet = b.now;
    b.run(240000);
    EXPECT_EQ(b.sent.size() - b.count("fw/heartbeat"), [&] { size_t n = 0; for (const auto& s : b.sent) n += s.at < quiet && s.topic != "fw/heartbeat"; return n; }());
    EXPECT_EQ(b.count("fw/heartbeat", quiet), 4u);
    // Every 5 minutes the state comes again anyway.
    b.run(70000);
    EXPECT_EQ(b.count("fw/state/room/keuken", quiet), 1u);
    EXPECT_EQ(b.count("fw/telemetry/summary", quiet), 1u);
    // A reconnect sends everything once more.
    const uint64_t again = b.now;
    b.publisher.connected(b.now);
    b.run(20000);
    EXPECT_EQ(b.count("fw/state/room/woonkamer", again), 1u);
    EXPECT_EQ(b.count("fw/config/plan", again), 1u);
    EXPECT_EQ(b.count("fw/heartbeat", again), 1u);
}

TEST(TelemetryPublisher, ARealChangeGoesOutWithinTenSecondsNoiseNever) {
    Bench b;
    b.publisher.connected(b.now);
    b.run(30000);
    uint64_t at = b.now;
    b.temperature["keuken"] = 19.05;                       // below the 0.1 degC deadband
    b.boilerFlow = 4540;                                   // below 0.5 degC
    b.run(60000);
    EXPECT_EQ(b.count("fw/state/room/keuken", at), 0u);
    EXPECT_EQ(b.count("fw/state/boiler", at), 0u);
    at = b.now;
    b.temperature["keuken"] = 19.2;
    b.flow = 45;
    b.boilerFlow = 4600;
    b.run(12000);
    EXPECT_EQ(b.count("fw/state/room/keuken", at), 1u);
    EXPECT_EQ(b.count("fw/state/heating", at), 1u);
    EXPECT_EQ(b.count("fw/state/boiler", at), 1u);
    EXPECT_EQ(b.count("fw/state/room/woonkamer", at), 0u);
    for (const auto& s : b.sent) { if (s.at >= at && s.topic == "fw/state/room/keuken") EXPECT_LE(s.at - at, 3000u); }
    // A room that keeps changing: at most every 10 s.
    at = b.now;
    for (int i = 0; i < 60; ++i) { b.temperature["keuken"] += 0.5; b.run(1000); }
    EXPECT_LE(b.count("fw/state/room/keuken", at), 7u);
    EXPECT_GE(b.count("fw/state/room/keuken", at), 5u);
    // The boiler group: at most once per 60 s.
    at = b.now;
    for (int i = 0; i < 120; ++i) { b.boilerFlow += 100; b.run(1000); }
    EXPECT_LE(b.count("fw/state/boiler_fields/0", at), 3u);
    EXPECT_GE(b.count("fw/state/boiler_fields/0", at), 1u);
    // The learned room: a new result, not its minute-by-minute advice.
    at = b.now;
    b.run(120000);
    EXPECT_EQ(b.count("fw/telemetry/learned/keuken", at), 0u);
    b.learnedResult = "ready";
    b.run(70000);
    EXPECT_EQ(b.count("fw/telemetry/learned/keuken", at), 1u);
}

TEST(TelemetryPublisher, ARoomThatLeftThePlanHasItsRetainedTopicsCleared) {
    Bench b;
    b.publisher.connected(b.now);
    b.run(30000);
    const uint64_t at = b.now;
    b.rooms = {"woonkamer", "keuken"};
    b.run(5000);
    bool clearedRoom = false, clearedLearned = false;
    for (const auto& s : b.sent) {
        if (s.at < at) continue;
        clearedRoom = clearedRoom || (s.topic == "fw/state/room/badkamer" && s.payload.empty() && s.retained);
        clearedLearned = clearedLearned || (s.topic == "fw/telemetry/learned/badkamer" && s.payload.empty() && s.retained);
    }
    EXPECT_TRUE(clearedRoom);
    EXPECT_TRUE(clearedLearned);
    EXPECT_GE(b.count("fw/config/plan", at), 1u);         // the plan changed: at once
    EXPECT_GE(b.count("fw/config/entities", at), 1u);
}

// Review 1.0: a plan save drops a deleted room's valves (TrvConfig::dropRooms); its retained
// fw/state/trv/<room> is then cleared like the room's own topics.
TEST(TelemetryPublisher, ADroppedValveRoomHasItsRetainedTopicCleared) {
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> record(cJSON_Parse(R"({"schema":1,"rooms":[)"
        R"({"room":"woonkamer","control":true,"valves":[{"name":"K1","model":"bosch_bth_ra"}]},)"
        R"({"room":"zolder","control":true,"valves":[{"name":"K2","model":"bosch_bth_ra"}]}]})"), cJSON_Delete);
    TrvConfig config;
    ASSERT_EQ(TrvConfig::parse(record.get(), config), nullptr);
    TrvControl trv; trv.setConfig(config);
    Bench b; b.trv = &trv;
    b.publisher.connected(b.now);
    b.run(30000);
    ASSERT_GE(b.count("fw/state/trv/zolder"), 1u);
    const uint64_t at = b.now;
    ASSERT_TRUE(config.dropRooms([](const std::string& id) { return id != "zolder"; }));
    trv.setConfig(config);
    b.run(5000);
    bool cleared = false, kept = false;
    for (const auto& s : b.sent) {
        if (s.at < at) continue;
        cleared = cleared || (s.topic == "fw/state/trv/zolder" && s.payload.empty() && s.retained);
        kept = kept || (s.topic == "fw/state/trv/woonkamer" && s.payload.empty());
    }
    EXPECT_TRUE(cleared);
    EXPECT_FALSE(kept);
}

TEST(TelemetryPublisher, BackpressureDropsACycleAndRetriesLater) {
    Bench b;
    b.publisher.connected(b.now);
    b.ready = false;
    const auto dropped = TelemetryCounters::dropped.load();
    b.run(10000);
    EXPECT_EQ(b.sent.size(), 1u);                          // only the heartbeat
    EXPECT_EQ(b.sent[0].topic, "fw/heartbeat");
    EXPECT_GE(TelemetryCounters::dropped.load(), dropped + 9);
    b.ready = true;
    b.accept = false;                                      // the outbox refuses: counted, retried
    const auto failed = TelemetryCounters::failed.load();
    b.run(3000);
    EXPECT_GT(TelemetryCounters::failed.load(), failed);
    b.accept = true;
    b.run(30000);
    EXPECT_GE(b.count("fw/state/room/badkamer"), 1u);
    EXPECT_GE(b.count("fw/config/plan"), 1u);
}

// fw/config/ems_devices (beta.23): the identities on the bus for Home Assistant's
// devices; retained, sent once and again only when an identity changes.
TEST(TelemetryPublisher, TheBusIdentitiesGoOutRetainedAndOnlyAgainOnAChange) {
    std::string identities = R"({"schema":1,"devices":[{"address":8,"product_id":null,"version":null,"brand_id":null}]})";
    std::vector<Sent> sent;
    uint64_t now = 1000;
    TelemetryPublisher publisher{
        TelemetryPublisher::Sources{[] { return static_cast<cJSON*>(nullptr); }, {}, {}, {},
            [&](std::string& out, size_t group) { if (group == emsDevicesGroup) out = identities; else out.clear(); },
            {}},
        [&](const std::string& topic, std::string_view payload, bool retained) {
            sent.push_back({topic, std::string(payload), retained, now}); return true; },
        [] { return true; }};
    auto devices = [&] {
        std::vector<Sent> out;
        for (const auto& s : sent) if (s.topic == "fw/config/ems_devices") out.push_back(s);
        return out;
    };
    for (uint64_t end = now + 60000; now < end; now += 100) publisher.tick(now);
    ASSERT_EQ(devices().size(), 1u);
    EXPECT_TRUE(devices()[0].retained);
    EXPECT_EQ(devices()[0].payload, identities);
    identities = R"({"schema":1,"devices":[{"address":8,"product_id":211,"version":"1.3","brand_id":1}]})";
    for (uint64_t end = now + 30000; now < end; now += 100) publisher.tick(now);
    ASSERT_EQ(devices().size(), 2u);
    EXPECT_EQ(devices()[1].payload, identities);
}
