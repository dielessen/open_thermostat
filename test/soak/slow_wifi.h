// Soak scenario "slowwifi" (included by soak.cpp; telemetry budget, TELEMETRIEBUDGET.nl.md
// section 8): the real MqttOutbox and TelemetryPublisher on a simulated Wi-Fi link
// with a 5744-byte TCP send buffer, 1460-byte segments and 300-2000 ms per ACK,
// short outages (5-12 s without any ACK) and broker restarts (socket error).
// Invariants: no disconnect from slowness, the queue stays within its bounds,
// every frame arrives whole and in order, a room's real change reaches the
// broker in time, the traffic stays within the budget, and a reconnect sends
// every retained topic again.
// soak.cpp includes control/MqttOutbox.h and control/TelemetryPublisher.h at its top.

struct SlowLink {
    static constexpr size_t sendBuffer = 5744, segment = 1460;
    uint64_t now = 0;
    size_t inflight = 0;
    std::deque<std::pair<uint64_t, size_t>> acks;
    uint64_t downUntil = 0;
    bool broken = false;
    std::vector<uint8_t> wire;  // bytes not yet parsed by the broker
    std::ptrdiff_t send(const uint8_t* p, size_t n) {
        if (broken) return -1;
        if (now >= downUntil)
            while (!acks.empty() && acks.front().first <= now) { inflight -= acks.front().second; acks.pop_front(); }
        const size_t k = std::min({n, sendBuffer - inflight, segment});
        if (!k) return 0;
        inflight += k;
        const uint64_t latency = 300 + rng() % 1701;  // 300..2000 ms
        acks.emplace_back(std::max(now, downUntil) + latency, k);
        wire.insert(wire.end(), p, p + k);
        return std::ptrdiff_t(k);
    }
};

void slowWifiScenario() {
    const size_t roomCount = opt.days > 1 ? 8 : 3;
    std::vector<std::string> rooms;
    for (size_t i = 0; i < roomCount; ++i) rooms.push_back("room_" + std::to_string(i));
    std::vector<double> temperature(roomCount, 20.0), delivered(roomCount, -100.0);
    std::vector<uint64_t> changedAt(roomCount, 0);
    int flow = 40;
    SlowLink link;
    std::vector<uint8_t> arena(24576);
    heating::control::MqttOutbox box;
    box.attach(arena.data(), arena.size(), 9216, 8192);
    std::map<std::string, size_t> topicBytes;
    std::set<std::string> retainedSeen;
    uint64_t wireBytes = 0, frames = 0, stalls = 0, errors = 0, restarts = 0, rejected = 0;
    bool connected = true;
    const std::string prefix = "p/v1/";
    const auto publishFrame = [&](const std::string& topic, std::string_view payload, bool retained) {
        std::vector<uint8_t> f{uint8_t(0x30 | (retained ? 1 : 0))};
        size_t length = 2 + topic.size() + payload.size();
        do { uint8_t d = length & 127; length >>= 7; if (length) d |= 128; f.push_back(d); } while (length);
        f.push_back(uint8_t(topic.size() >> 8)); f.push_back(uint8_t(topic.size()));
        f.insert(f.end(), topic.begin(), topic.end()); f.insert(f.end(), payload.begin(), payload.end());
        bool coalesce = false;
        const auto cls = heating::control::mqttTopicClass(std::string_view(topic).substr(prefix.size()), coalesce);
        const bool ok = connected && box.push(f.data(), f.size(), cls, coalesce, link.now) != heating::control::MqttOutbox::Push::rejected;
        if (connected && !ok) ++rejected;
        return ok;
    };
    heating::control::TelemetryPublisher publisher{
        heating::control::TelemetryPublisher::Sources{
            [&] {
                std::string rows, entities;
                for (size_t i = 0; i < roomCount; ++i) {
                    char t[16]; std::snprintf(t, sizeof t, "%.2f", temperature[i]);
                    rows += std::string(i ? "," : "") + R"({"id":")" + rooms[i] + R"(","name":"Room","state":"active","status":"ok","source":"climate.)" + rooms[i]
                        + R"(","temperature":)" + t + R"(,"setpoint":21,"setpoint_source":"ha","demand":true})";
                    entities += std::string(i ? "," : "") + "\"climate." + rooms[i] + "\"";
                }
                const std::string s = R"({"schema":1,"revision":3,"mode":"shadow","request":{"heat":true,"flow_c":)" + std::to_string(flow)
                    + R"(,"reason":"heating"},"ha_entities":[)" + entities + R"(],"rooms":[)" + rows
                    + R"(],"ble_sensors":[],"burner":{"starts_last_hour":2,"heating_starts_last_hour":2,"short_cycling":false},"shadow":{"today":{"s":)"
                    + std::to_string(link.now / 1000) + R"(}},"ha":{"input_age_s":)" + std::to_string(link.now / 1000 % 300) + R"(,"broker_connected":true}})";
                return cJSON_Parse(s.c_str());
            },
            [&] { return roomCount; },
            [&](size_t i, std::string& id) {
                id = rooms[i];
                return R"({"schema":1,"id":")" + id + R"(","learned":{"readiness":"learning","now":{"flow_c":)" + std::to_string(link.now / 60000 % 50) + "}},\"plan\":null}";
            },
            [] { return std::string(R"({"schema":1,"learned":{"schema":1,"applied":false}})"); },
            [&](std::string& out, size_t group) {
                out.clear();
                if (group != 0) return;
                std::string rows;
                for (size_t i = 0; i < 10; ++i) {
                    const int raw = i == 1 ? 4000 + int(link.now / 7000 % 900) : i == 2 ? 3500 : i == 4 ? 30 : i == 6 ? 15 : i == 3 ? 500 : i == 5 ? 100 : 0;
                    rows += std::string(i ? "," : "") + "[" + std::to_string(i) + "," + std::to_string(raw) + "," + std::to_string(link.now - 500) + ","
                        + std::to_string(heating::control::boilerFieldQualities[i]) + "," + std::to_string(heating::control::boilerFieldSourceTypes[i]) + "]";
                }
                out = R"({"schema":1,"sampled_at_ms":)" + std::to_string(link.now) + R"(,"profile":"classic_observed","fields":[)" + rows + "]}";
            },
            [&] { return std::string(R"({"schema":1,"uptime_s":)") + std::to_string(link.now / 1000) + "}"; }},
        [&](const std::string& suffix, std::string_view payload, bool retained) { return publishFrame(prefix + suffix, payload, retained); },
        [&] { return box.acceptsTelemetry(); }};
    // The broker: parses the stream; every frame must be a whole PUBLISH or PINGREQ.
    size_t parsed = 0;
    const auto broker = [&] {
        while (link.wire.size() - parsed >= 2) {
            size_t length = 0, j = parsed + 1;
            bool complete = true;
            for (unsigned shift = 0;; shift += 7) {
                if (j >= link.wire.size()) { complete = false; break; }
                const uint8_t d = link.wire[j++];
                length |= size_t(d & 127) << shift;
                if (!(d & 128)) break;
                EXPECT(shift < 21, "slowwifi_frame_length", "a remaining length longer than 4 bytes");
            }
            if (!complete || link.wire.size() - j < length) break;
            const uint8_t type = link.wire[parsed] & 0xF0;
            EXPECT(type == 0x30 || type == 0xC0, "slowwifi_frame_type", "an unexpected packet 0x%02x: a frame was split or interleaved", type);
            if (type == 0x30) {
                const size_t topicSize = size_t(link.wire[j]) << 8 | link.wire[j + 1];
                const std::string topic(link.wire.begin() + std::ptrdiff_t(j + 2), link.wire.begin() + std::ptrdiff_t(j + 2 + topicSize));
                const std::string payload(link.wire.begin() + std::ptrdiff_t(j + 2 + topicSize), link.wire.begin() + std::ptrdiff_t(j + length));
                EXPECT(topic.rfind(prefix + "fw/", 0) == 0, "slowwifi_topic", "a frame with topic %s: the stream is corrupt", topic.c_str());
                EXPECT(payload.size() <= heating::control::telemetryHardBytes, "slowwifi_message_size", "%s carries %zu B", topic.c_str(), payload.size());
                topicBytes[topic] += j + length - parsed;
                if (link.wire[parsed] & 1) retainedSeen.insert(topic);
                for (size_t i = 0; i < roomCount; ++i)
                    if (topic == prefix + "fw/state/room/" + rooms[i]) {
                        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> doc(cJSON_Parse(payload.c_str()), cJSON_Delete);
                        const cJSON* t = doc ? cJSON_GetObjectItem(doc.get(), "temperature") : nullptr;
                        if (cJSON_IsNumber(t)) {
                            if (changedAt[i] && std::fabs(t->valuedouble - temperature[i]) < 0.1) {
                                const uint64_t delay = link.now - changedAt[i];
                                if (delay > 30000) fail("slowwifi_room_latency", "room %zu reached the broker %" PRIu64 " ms after its change", i, delay);
                                count("slowwifi_room_changes_delivered");
                                changedAt[i] = 0;
                            }
                            delivered[i] = t->valuedouble;
                        }
                    }
            }
            ++frames;
            wireBytes += j + length - parsed;
            parsed = j + length;
        }
        if (parsed > (1 << 20)) { link.wire.erase(link.wire.begin(), link.wire.begin() + std::ptrdiff_t(parsed)); parsed = 0; }
    };
    const auto reconnect = [&] {
        box.clear();
        link.broken = false; link.inflight = 0; link.acks.clear(); link.wire.clear(); parsed = 0;
        retainedSeen.clear();
        connected = true;
        publisher.connected(link.now);
    };
    const uint64_t end = uint64_t(std::max(0.25, opt.days) * 86400000.0);
    publisher.connected(0);
    uint64_t nextPing = 15000, nextOutage = 3600000 + rng() % 3600000, nextRestart = 6 * 3600000ull, restartedAt = 0;
    uint64_t lastStatsAt = 0, lastStatsBytes = 0, peak = 0;
    double worstRate = 0;
    for (; link.now < end; link.now += 20) {
        ctx.uptime = link.now; ctx.utc = ctx.startUtc + int64_t(link.now / 1000);
        // The house: noise below the deadband every 30 s, a real change now and then.
        if (link.now % 30000 == 0)
            for (size_t i = 0; i < roomCount; ++i) {
                temperature[i] += (rng() % 2 ? 0.02 : -0.02);
                if (rng() % 20 == 0) temperature[i] += (rng() % 2 ? 0.3 : -0.3);
                if (std::fabs(temperature[i] - delivered[i]) >= 0.1 && !changedAt[i]) changedAt[i] = link.now;
                if (std::fabs(temperature[i] - delivered[i]) < 0.1) changedAt[i] = 0;
            }
        if (link.now % 600000 == 0) flow = 35 + int(rng() % 15);
        if (link.now >= nextOutage) {               // a short outage: no ACK for 5-12 s
            link.downUntil = link.now + 5000 + rng() % 7001;
            nextOutage = link.now + 1800000 + rng() % 5400000;
            count("slowwifi_outages");
        }
        if (link.now >= nextRestart) {              // the broker restarts: the socket fails
            link.broken = true;
            nextRestart = link.now + 6 * 3600000ull;
        }
        if (connected) {
            if (link.now >= nextPing) { static const uint8_t ping[]{0xC0, 0}; box.push(ping, 2, heating::control::MqttOutbox::control, false, link.now); nextPing = link.now + 15000; }
            publisher.tick(link.now);
            const auto r = box.pump([&](const uint8_t* p, size_t n) { return link.send(p, n); }, [&] { return link.now; }, [](size_t, uint64_t, bool) {});
            if (r == heating::control::MqttOutbox::Pump::error) { ++errors; connected = false; restartedAt = link.now; }
            else if (box.stalled(link.now)) {
                ++stalls;
                fail("slowwifi_stall_disconnect", "the outbox made no progress for 15 s on a slow but working link (outage until %" PRIu64 ")", link.downUntil);
                connected = false; restartedAt = link.now;
            }
            EXPECT(box.bytes() <= arena.size(), "slowwifi_queue_bound", "%zu B queued", box.bytes());
            EXPECT(box.telemetryBytes() <= arena.size() - 9216, "slowwifi_queue_bound", "%zu B of telemetry queued", box.telemetryBytes());
            peak = std::max<uint64_t>(peak, box.bytes());
        } else if (link.now - restartedAt >= 5000) {  // reconnect after the existing 5 s backoff
            ++restarts;
            reconnect();
        }
        broker();
        if (restarts && link.now - restartedAt == 40000) {
            // Every retained topic once more within 30 s of the reconnect.
            for (const char* t : {"fw/state/heating", "fw/config/plan", "fw/config/entities", "fw/state/boiler", "fw/telemetry/summary"})
                EXPECT(retainedSeen.count(prefix + t), "slowwifi_reconnect_complete", "%s not sent again after a reconnect", t);
            for (const auto& room : rooms)
                EXPECT(retainedSeen.count(prefix + "fw/state/room/" + room), "slowwifi_reconnect_complete", "room %s not sent again", room.c_str());
        }
        if (link.now - lastStatsAt >= 3600000) {
            const double rate = double(wireBytes - lastStatsBytes) * 1000.0 / double(link.now - lastStatsAt);
            worstRate = std::max(worstRate, rate);
            lastStatsAt = link.now; lastStatsBytes = wireBytes;
        }
    }
    const double average = double(wireBytes) * 1000.0 / double(link.now);
    EXPECT(average <= 250.0, "slowwifi_traffic_budget", "%.0f B/s on average with %zu rooms (budget 250 B/s)", average, roomCount);
    EXPECT(errors == restarts || errors == restarts + 1, "slowwifi_restart_reasons", "%" PRIu64 " socket errors for %" PRIu64 " reconnects", errors, restarts);
    EXPECT(rejected == 0, "slowwifi_rejected", "%" PRIu64 " frames refused by a full outbox", rejected);
    count("slowwifi_frames", frames);
    count("slowwifi_bytes", wireBytes);
    count("slowwifi_reconnects_after_broker_restart", restarts);
    count("slowwifi_stall_disconnects", stalls);
    char text[160];
    std::snprintf(text, sizeof text, "%zu rooms: %.0f B/s average, worst hour %.0f B/s, queue peak %" PRIu64 " B", roomCount, average, worstRate, peak);
    observe("slowwifi_traffic", text);
    for (const auto& [topic, bytes] : topicBytes) {
        std::snprintf(text, sizeof text, "%.1f B/s", double(bytes) * 1000.0 / double(link.now));
        observe("slowwifi_bytes " + topic.substr(prefix.size()), text);
    }
}
