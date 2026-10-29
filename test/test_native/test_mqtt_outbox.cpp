#include "control/MqttOutbox.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <deque>
#include <string>
#include <vector>
using heating::control::MqttOutbox;
using heating::control::mqttTopicClass;
namespace {
// PUBLISH (QoS 0) exactly as PubSubClient frames it.
std::vector<uint8_t> publish(const std::string& topic, const std::string& payload, bool retained = false) {
    std::vector<uint8_t> f{uint8_t(0x30 | (retained ? 1 : 0))};
    size_t length = 2 + topic.size() + payload.size();
    do { uint8_t d = length & 127; length >>= 7; if (length) d |= 128; f.push_back(d); } while (length);
    f.push_back(uint8_t(topic.size() >> 8)); f.push_back(uint8_t(topic.size()));
    f.insert(f.end(), topic.begin(), topic.end()); f.insert(f.end(), payload.begin(), payload.end());
    return f;
}
const std::vector<uint8_t> pingreq{0xC0, 0x00};

// The broker side of the socket: takes at most `perCall` bytes per send, 0
// (EAGAIN) while `blockedUntil` lies ahead, an error when `broken`.
struct FakeSocket {
    uint64_t now = 0;
    size_t perCall = 1 << 20;
    uint64_t blockedUntil = 0;
    uint64_t ackDelay = 0;                               // the send buffer is full until the ACK
    bool broken = false;
    std::vector<uint8_t> wire;
    std::ptrdiff_t send(const uint8_t* p, size_t n) {
        if (broken) return -1;
        if (now < blockedUntil) return 0;
        const size_t k = std::min(n, perCall);
        wire.insert(wire.end(), p, p + k);
        if (ackDelay) blockedUntil = now + ackDelay;
        return std::ptrdiff_t(k);
    }
    // The packets on the wire, split by their own length fields.
    std::vector<std::vector<uint8_t>> packets() const {
        std::vector<std::vector<uint8_t>> out;
        for (size_t i = 0; i < wire.size();) {
            size_t length = 0, j = i + 1;
            for (unsigned shift = 0;; shift += 7) { const uint8_t d = wire.at(j++); length |= size_t(d & 127) << shift; if (!(d & 128)) break; }
            out.emplace_back(wire.begin() + i, wire.begin() + j + length);
            i = j + length;
        }
        return out;
    }
};
struct Bench {
    std::vector<uint8_t> arena;
    MqttOutbox box;
    FakeSocket socket;
    std::vector<uint64_t> latencies;
    explicit Bench(size_t capacity = 24576, size_t reserve = 9216, size_t highWater = 8192) : arena(capacity) {
        box.attach(arena.data(), capacity, reserve, highWater);
    }
    MqttOutbox::Push push(const std::vector<uint8_t>& f, MqttOutbox::Class c = MqttOutbox::state, bool coalesce = true) {
        return box.push(f.data(), f.size(), c, coalesce, socket.now);
    }
    MqttOutbox::Pump pump() {
        return box.pump([&](const uint8_t* p, size_t n) { return socket.send(p, n); }, [&] { return socket.now; },
                        [&](size_t, uint64_t latency, bool) { latencies.push_back(latency); });
    }
    // One MQTT loop iteration every `step` ms; disconnect check as DeadlineWiFiClient::poll.
    bool run(uint64_t ms, uint64_t step = 5) {
        for (uint64_t t = 0; t < ms; t += step) {
            if (pump() == MqttOutbox::Pump::error) return false;
            if (box.stalled(socket.now)) return false;
            socket.now += step;
        }
        return true;
    }
};
}

TEST(MqttOutbox, OneAndTwoSecondAckLatencyNeverDisconnects) {
    for (const uint64_t latency : {1000u, 2000u}) {
        Bench b;
        // A slow link: one 1000 B segment per send, then nothing until its ACK returns.
        b.socket.perCall = 1000; b.socket.ackDelay = latency;
        std::string big(1400, 'x');
        for (int cycle = 0; cycle < 20; ++cycle) {
            for (int room = 0; room < 3; ++room) ASSERT_NE(b.push(publish("p/v1/fw/state/room/r" + std::to_string(room), big)), MqttOutbox::Push::rejected);
            ASSERT_NE(b.push(pingreq), MqttOutbox::Push::rejected);
            for (uint64_t t = 0; t < 15000; t += 5) {
                ASSERT_NE(b.pump(), MqttOutbox::Pump::error);
                ASSERT_FALSE(b.box.stalled(b.socket.now)) << latency << " ms at cycle " << cycle;
                b.socket.now += 5;
            }
        }
        EXPECT_TRUE(b.box.empty());
        const auto packets = b.socket.packets();
        EXPECT_EQ(packets.size(), 20u * 4u);
        EXPECT_GT(*std::max_element(b.latencies.begin(), b.latencies.end()), latency);  // queued, not dropped
    }
}

TEST(MqttOutbox, OnlyARealStallDisconnects) {
    Bench b;
    ASSERT_EQ(b.push(publish("p/v1/fw/state/heating", std::string(900, 'h'))), MqttOutbox::Push::queued);
    b.socket.blockedUntil = 14000;                         // 14 s without an ACK: still alive
    EXPECT_TRUE(b.run(14500));
    EXPECT_TRUE(b.box.empty());
    ASSERT_EQ(b.push(publish("p/v1/fw/state/heating", std::string(900, 'h'))), MqttOutbox::Push::queued);
    b.socket.blockedUntil = b.socket.now + 60000;          // the link is gone
    const uint64_t start = b.socket.now;
    EXPECT_FALSE(b.run(60000));
    EXPECT_GE(b.socket.now - start, MqttOutbox::stallMs);
    EXPECT_LT(b.socket.now - start, MqttOutbox::stallMs + 50);
    // Partial progress is progress: a trickle never counts as a stall.
    Bench t;
    ASSERT_EQ(t.push(publish("p/v1/fw/state/heating", std::string(1400, 'h'))), MqttOutbox::Push::queued);
    t.socket.perCall = 1; t.socket.ackDelay = 10000;       // one byte per 10 s
    for (int i = 0; i < 2000 && !t.box.empty(); ++i) {
        ASSERT_NE(t.pump(), MqttOutbox::Pump::error);
        t.socket.now += 10000;
        ASSERT_FALSE(t.box.stalled(t.socket.now));
    }
    EXPECT_TRUE(t.box.empty());
}

TEST(MqttOutbox, SocketErrorIsReported) {
    Bench b;
    ASSERT_EQ(b.push(pingreq), MqttOutbox::Push::queued);
    b.socket.broken = true;
    EXPECT_EQ(b.pump(), MqttOutbox::Pump::error);
}

TEST(MqttOutbox, FramesStayWholeAndInOrderAcrossPartialSends) {
    Bench b;
    b.socket.perCall = 7;                                  // every frame needs many sends
    std::vector<std::vector<uint8_t>> sent;
    for (int i = 0; i < 12; ++i) {
        sent.push_back(publish("p/v1/fw/session", "{\"n\":" + std::to_string(i) + std::string(i * 37, ' ') + "}"));
        ASSERT_EQ(b.push(sent.back(), MqttOutbox::control, false), MqttOutbox::Push::queued);
        if (i % 3 == 0) b.pump();
    }
    while (!b.box.empty()) { b.socket.now += 1; ASSERT_NE(b.pump(), MqttOutbox::Pump::error); }
    EXPECT_EQ(b.socket.packets(), sent);                   // byte-identical, in order
}

TEST(MqttOutbox, ControlGoesFirstAndTelemetryLeavesOneFramePerPumpWithARest) {
    Bench b;
    b.socket.blockedUntil = 1;
    b.push(publish("p/v1/fw/telemetry/summary", "s"), MqttOutbox::slow);
    b.push(publish("p/v1/fw/state/room/a", "a"), MqttOutbox::state);
    b.push(publish("p/v1/fw/state/boiler_fields/0", "g"), MqttOutbox::config);
    b.push(publish("p/v1/fw/state/room/b", "b"), MqttOutbox::state);
    b.push(pingreq);
    b.push(publish("p/v1/fw/hello", "h"), MqttOutbox::control);
    b.socket.now = 1;
    b.pump();
    auto packets = b.socket.packets();
    ASSERT_EQ(packets.size(), 3u);                         // both control frames, then one telemetry frame
    EXPECT_EQ(packets[0], pingreq);
    EXPECT_EQ(packets[1], publish("p/v1/fw/hello", "h"));
    EXPECT_EQ(packets[2], publish("p/v1/fw/state/room/a", "a"));
    b.pump();
    EXPECT_EQ(b.socket.packets().size(), 3u);              // resting
    b.socket.now += MqttOutbox::telemetryGapMs;
    b.pump();
    b.socket.now += MqttOutbox::telemetryGapMs;
    b.pump();
    b.socket.now += MqttOutbox::telemetryGapMs;
    b.pump();
    packets = b.socket.packets();
    ASSERT_EQ(packets.size(), 6u);
    EXPECT_EQ(packets[3], publish("p/v1/fw/state/room/b", "b"));
    EXPECT_EQ(packets[4], publish("p/v1/fw/state/boiler_fields/0", "g"));
    EXPECT_EQ(packets[5], publish("p/v1/fw/telemetry/summary", "s"));
}

TEST(MqttOutbox, ANewerFrameForTheSameTopicReplacesTheWaitingOne) {
    Bench b;
    b.socket.blockedUntil = 1000;
    EXPECT_EQ(b.push(publish("p/v1/fw/state/room/a", "21.0")), MqttOutbox::Push::queued);
    EXPECT_EQ(b.push(publish("p/v1/fw/state/room/b", "19.0")), MqttOutbox::Push::queued);
    EXPECT_EQ(b.push(publish("p/v1/fw/state/room/a", "21.1")), MqttOutbox::Push::replaced);
    EXPECT_EQ(b.push(publish("p/v1/fw/state/room/a", "21.2")), MqttOutbox::Push::replaced);
    const size_t bytes = b.box.bytes();
    for (int i = 0; i < 100; ++i) b.push(publish("p/v1/fw/state/room/a", "21.3"));
    EXPECT_EQ(b.box.bytes(), bytes);                       // bounded: one frame per topic
    b.socket.now = 1000;
    b.run(1000);
    const auto packets = b.socket.packets();
    ASSERT_EQ(packets.size(), 2u);
    EXPECT_EQ(packets[0], publish("p/v1/fw/state/room/b", "19.0"));
    EXPECT_EQ(packets[1], publish("p/v1/fw/state/room/a", "21.3"));
    // The frame on the wire is never replaced: the newer one follows it whole.
    Bench f;
    f.socket.perCall = 3;
    f.push(publish("p/v1/fw/state/room/a", "first-value"));
    f.pump();
    EXPECT_EQ(f.push(publish("p/v1/fw/state/room/a", "second")), MqttOutbox::Push::queued);
    while (!f.box.empty()) { f.socket.now += 50; f.pump(); }
    const auto two = f.socket.packets();
    ASSERT_EQ(two.size(), 2u);
    EXPECT_EQ(two[0], publish("p/v1/fw/state/room/a", "first-value"));
    EXPECT_EQ(two[1], publish("p/v1/fw/state/room/a", "second"));
    // Control frames are never merged.
    Bench c;
    c.socket.blockedUntil = 10;
    c.push(publish("p/v1/fw/config_result", "1"), MqttOutbox::control, false);
    EXPECT_EQ(c.push(publish("p/v1/fw/config_result", "2"), MqttOutbox::control, false), MqttOutbox::Push::queued);
}

TEST(MqttOutbox, AFullQueueRejectsWholeFramesWithoutCorruptingTheStream) {
    Bench b(4096, 1024, 2048);
    b.socket.blockedUntil = 100;
    std::vector<std::vector<uint8_t>> accepted;
    size_t rejected = 0;
    for (int i = 0; i < 10; ++i) {
        const auto f = publish("p/v1/fw/state/room/r" + std::to_string(i), std::string(700, char('a' + i)));
        if (b.push(f) == MqttOutbox::Push::rejected) ++rejected; else accepted.push_back(f);
    }
    EXPECT_EQ(accepted.size(), 4u);                        // telemetry: 4096 - 1024 reserved
    EXPECT_EQ(rejected, 6u);
    EXPECT_FALSE(b.box.acceptsTelemetry());                // above the high-water mark
    EXPECT_EQ(b.push(pingreq), MqttOutbox::Push::queued);  // the reserve keeps the keepalive
    EXPECT_EQ(b.push(publish("p/v1/fw/session", std::string(1500, 's')), MqttOutbox::control, false), MqttOutbox::Push::rejected);
    // Malformed or partial packets are refused, never sent half.
    const auto whole = publish("p/v1/fw/state/heating", "x");
    EXPECT_EQ(b.box.push(whole.data(), whole.size() - 1, MqttOutbox::state, true, 0), MqttOutbox::Push::rejected);
    const uint8_t one = 0x30;
    EXPECT_EQ(b.box.push(&one, 1, MqttOutbox::control, false, 0), MqttOutbox::Push::rejected);
    b.socket.now = 100;
    b.run(2000);
    auto expected = std::vector<std::vector<uint8_t>>{pingreq};
    expected.insert(expected.end(), accepted.begin(), accepted.end());
    EXPECT_EQ(b.socket.packets(), expected);
    EXPECT_TRUE(b.box.acceptsTelemetry());
    EXPECT_GE(b.box.peak(), 4 * accepted[0].size());
}

TEST(MqttOutbox, ADirectDeadlineWriteWaitsForAHalfSentFrameAndQueuedControl) {
    Bench b;
    EXPECT_TRUE(b.box.idleForDeadline());
    b.socket.perCall = 5; b.socket.ackDelay = 100;
    b.push(publish("p/v1/fw/state/heating", std::string(100, 'h')));
    b.pump();
    EXPECT_FALSE(b.box.idleForDeadline());                 // half on the wire
    b.socket.perCall = 1 << 20; b.socket.ackDelay = 0; b.socket.now = 100;
    b.pump();
    EXPECT_TRUE(b.box.empty());
    b.socket.blockedUntil = 10;
    b.push(publish("p/v1/fw/state/room/a", "a"));
    EXPECT_TRUE(b.box.idleForDeadline());                  // waiting telemetry may follow the actuator frame
    b.push(pingreq);
    EXPECT_FALSE(b.box.idleForDeadline());                 // session frames keep their order
}

TEST(MqttOutbox, ClearDropsEverythingForANewSession) {
    Bench b;
    b.socket.blockedUntil = 10;
    b.push(publish("p/v1/fw/state/room/a", "a"));
    b.push(pingreq);
    b.box.clear();
    EXPECT_TRUE(b.box.empty());
    EXPECT_EQ(b.box.bytes(), 0u);
    EXPECT_EQ(b.box.telemetryBytes(), 0u);
    EXPECT_FALSE(b.box.stalled(1000000));
}

TEST(MqttOutbox, TopicClasses) {
    bool coalesce = false;
    EXPECT_EQ(mqttTopicClass("fw/state/room/woonkamer", coalesce), MqttOutbox::state); EXPECT_TRUE(coalesce);
    EXPECT_EQ(mqttTopicClass("fw/state/heating", coalesce), MqttOutbox::state);
    EXPECT_EQ(mqttTopicClass("fw/state/boiler", coalesce), MqttOutbox::state);
    EXPECT_EQ(mqttTopicClass("fw/state/boiler_fields/3", coalesce), MqttOutbox::config);
    EXPECT_EQ(mqttTopicClass("fw/config/entities", coalesce), MqttOutbox::config);
    EXPECT_EQ(mqttTopicClass("fw/telemetry/learned/woonkamer", coalesce), MqttOutbox::slow);
    EXPECT_EQ(mqttTopicClass("fw/heartbeat", coalesce), MqttOutbox::slow); EXPECT_TRUE(coalesce);
    EXPECT_EQ(mqttTopicClass("fw/state/zones", coalesce), MqttOutbox::control); EXPECT_TRUE(coalesce);
    EXPECT_EQ(mqttTopicClass("fw/hello", coalesce), MqttOutbox::control); EXPECT_TRUE(coalesce);
    for (const char* control : {"fw/heartbeat_result", "fw/session", "fw/config_result", "fw/availability", "fw/actuator_command/x"}) {
        EXPECT_EQ(mqttTopicClass(control, coalesce), MqttOutbox::control) << control;
        EXPECT_FALSE(coalesce) << control;
    }
}
