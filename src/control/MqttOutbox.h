#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace heating::control {
// Outgoing MQTT frames of the one broker connection, between PubSubClient and
// the nonblocking socket. PubSubClient writes every packet in ONE write()
// (CONNECT, SUBSCRIBE, PUBLISH, PINGREQ, DISCONNECT); the outbox keeps each
// whole and in order within its class, so a slow ACK never splits a frame and
// never closes the session. Anything else (a partial packet) is rejected.
//
// Classes: control (session protocol, keepalive, CONNECT; FIFO) goes first,
// then state, config, slow telemetry. A newer frame for the same topic of a
// coalescing class replaces the queued one (not the one being sent): at most
// one frame per topic waits. Telemetry leaves at most one frame per pump and
// then rests telemetryGapMs; it may use the arena up to capacity - reserve and
// is refused above highWater (the publisher drops that cycle).
// Disconnect only after stallMs without one byte of progress or a socket error.
// Single task (the MQTT loop), no allocation: the arena comes from attach().
struct MqttOutbox {
    enum Class : uint8_t { control = 0, state = 1, config = 2, slow = 3 };
    enum class Push : uint8_t { queued, replaced, rejected };
    enum class Pump : uint8_t { idle, progress, blocked, error };
    static constexpr size_t maxFrames = 48;
    static constexpr uint64_t stallMs = 15000, sliceMs = 3, telemetryGapMs = 50;

    // capacity: arena bytes; reserve: bytes only control frames may use;
    // highWater: queued telemetry bytes above which acceptsTelemetry() is false.
    void attach(uint8_t* arena, size_t capacity, size_t reserve, size_t highWater) {
        arena_ = arena; capacity_ = arena ? capacity : 0; reserve_ = reserve; highWater_ = highWater; clear();
    }
    void clear() { count_ = 0; used_ = 0; telemetryBytes_ = 0; nextTelemetry_ = 0; }
    bool empty() const { return count_ == 0; }
    size_t bytes() const { return used_; }
    size_t capacity() const { return capacity_; }
    size_t telemetryBytes() const { return telemetryBytes_; }
    bool acceptsTelemetry() const { return capacity_ && telemetryBytes_ < highWater_; }
    // No partly sent frame and no control frame waits: a direct (deadline)
    // write cannot interleave with queued bytes or overtake session frames.
    bool idleForDeadline() const {
        for (size_t i = 0; i < count_; ++i) if (entries_[i].sent || entries_[i].cls == control) return false;
        return true;
    }
    bool stalled(uint64_t now) const { return count_ && now >= lastProgress_ && now - lastProgress_ >= stallMs; }

    // A whole MQTT packet: fixed header, remaining length, then for PUBLISH the
    // topic. Returns the PUBLISH topic (empty for other packets) or false.
    static bool parse(const uint8_t* p, size_t size, std::string_view& topic) {
        topic = {};
        if (!p || size < 2) return false;
        size_t length = 0, i = 1;
        for (unsigned shift = 0;; shift += 7) {
            if (i >= size || shift > 21) return false;
            const uint8_t digit = p[i++];
            length |= size_t(digit & 127) << shift;
            if (!(digit & 128)) break;
        }
        if (i + length != size) return false;
        if ((p[0] & 0xF0) != 0x30) return true;
        if (length < 2) return false;
        const size_t topicSize = size_t(p[i]) << 8 | p[i + 1];
        if (i + 2 + topicSize > size) return false;
        topic = std::string_view(reinterpret_cast<const char*>(p + i + 2), topicSize);
        return true;
    }

    // cls/coalesce for a PUBLISH come from the caller's topic rule; other packets
    // are always control. now: monotonic ms.
    Push push(const uint8_t* frame, size_t size, Class cls, bool coalesce, uint64_t now) {
        std::string_view topic;
        if (!arena_ || !parse(frame, size, topic) || size > 0xFFFF) return Push::rejected;
        if (topic.empty()) { cls = control; coalesce = false; }
        bool replaced = false;
        if (coalesce)
            for (size_t i = 0; i < count_; ++i)
                if (!entries_[i].sent && entries_[i].cls == cls && topicOf(i) == topic) { remove(i); replaced = true; break; }
        const size_t limit = cls == control ? capacity_ : (capacity_ > reserve_ ? capacity_ - reserve_ : 0);
        if (count_ >= maxFrames || used_ + size > limit) return Push::rejected;
        if (!count_) lastProgress_ = now;
        Entry& e = entries_[count_++];
        e = Entry{uint32_t(used_), uint16_t(size), 0, uint16_t(topic.empty() ? 0 : reinterpret_cast<const uint8_t*>(topic.data()) - frame),
                  uint16_t(topic.size()), cls, now};
        std::memcpy(arena_ + used_, frame, size);
        used_ += size;
        if (cls != control) telemetryBytes_ += size;
        if (used_ > peak_) peak_ = used_;
        return replaced ? Push::replaced : Push::queued;
    }

    // Sends what the socket takes now: the frame in flight first, then control
    // frames, then at most one telemetry frame (after the rest gap). send(p, n)
    // returns bytes taken (0: would block) or < 0 on a socket error; clock()
    // bounds the slice. Completed frames report their queue latency.
    template <class Send, class Clock, class Done>
    Pump pump(Send&& send, Clock&& clock, Done&& done) {
        const uint64_t start = clock();
        Pump result = count_ ? Pump::blocked : Pump::idle;
        bool telemetrySent = false;
        while (count_) {
            const uint64_t now = clock();
            const size_t i = next(now, telemetrySent);
            if (i >= count_) break;
            Entry& e = entries_[i];
            const auto n = send(arena_ + e.offset + e.sent, size_t(e.size - e.sent));
            if (n < 0 || size_t(n) > size_t(e.size - e.sent)) return Pump::error;
            if (n == 0) break;
            e.sent = uint16_t(e.sent + size_t(n));
            lastProgress_ = clock();
            result = Pump::progress;
            if (e.sent == e.size) {
                const bool telemetry = e.cls != control;
                done(e.size, lastProgress_ >= e.queuedAt ? lastProgress_ - e.queuedAt : 0, telemetry);
                if (telemetry) { telemetrySent = true; nextTelemetry_ = lastProgress_ + telemetryGapMs; }
                remove(i);
            }
            const uint64_t after = clock();
            if (after < start || after - start >= sliceMs) break;
        }
        return result;
    }
    size_t peak() const { return peak_; }
    void resetPeak() { peak_ = used_; }

private:
    struct Entry {
        uint32_t offset; uint16_t size, sent, topicOffset, topicSize; Class cls; uint64_t queuedAt;
    };
    std::string_view topicOf(size_t i) const {
        const Entry& e = entries_[i];
        return std::string_view(reinterpret_cast<const char*>(arena_ + e.offset + e.topicOffset), e.topicSize);
    }
    size_t next(uint64_t now, bool telemetrySent) const {
        size_t best = count_;
        for (size_t i = 0; i < count_; ++i) {
            const Entry& e = entries_[i];
            if (e.sent) return i;
            if (e.cls != control && (telemetrySent || now < nextTelemetry_)) continue;
            if (best == count_ || e.cls < entries_[best].cls) best = i;
        }
        return best;
    }
    void remove(size_t i) {
        const Entry e = entries_[i];
        const size_t end = e.offset + e.size;
        std::memmove(arena_ + e.offset, arena_ + end, used_ - end);
        used_ -= e.size;
        if (e.cls != control) telemetryBytes_ -= e.size;
        for (size_t k = i + 1; k < count_; ++k) { entries_[k - 1] = entries_[k]; entries_[k - 1].offset -= e.size; }
        --count_;
    }
    uint8_t* arena_ = nullptr;
    size_t capacity_ = 0, reserve_ = 0, highWater_ = 0, used_ = 0, telemetryBytes_ = 0, peak_ = 0, count_ = 0;
    uint64_t lastProgress_ = 0, nextTelemetry_ = 0;
    Entry entries_[maxFrames]{};
};

// Topic rule of the product transport (suffix after the base, e.g. "v1/").
// Session protocol and results stay control/FIFO; hello and the zone state
// are snapshots (a newer one replaces a waiting one).
inline MqttOutbox::Class mqttTopicClass(std::string_view suffix, bool& coalesce) {
    const auto starts = [&](std::string_view p) { return suffix.substr(0, p.size()) == p; };
    coalesce = true;
    if (suffix == "fw/hello" || suffix == "fw/state/zones") return MqttOutbox::control;
    if (starts("fw/state/boiler_fields/") || starts("fw/config/")) return MqttOutbox::config;
    if (starts("fw/state/")) return MqttOutbox::state;
    if (starts("fw/telemetry/") || suffix == "fw/heartbeat") return MqttOutbox::slow;
    coalesce = false;
    return MqttOutbox::control;
}

// /status/logs and fw/heartbeat. Static (internal RAM): read-modify-write
// atomics must not live in the PSRAM-resident transport.
struct MqttCounters {
    static inline std::atomic<uint32_t> stalledDisconnects{0}, socketErrorDisconnects{0}, rejected{0},
        frames{0}, bytes{0}, latencySumMs{0}, latencyMaxMs{0}, peakBytes{0};
};
}
