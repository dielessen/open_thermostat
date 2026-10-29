#pragma once
#include "BoilerStateTelemetry.h"
#include "HeatingStateTopics.h"
#include "TelemetryPolicy.h"
#include <atomic>
#include <cstdlib>
#include <functional>
#include <string>
#include <vector>
#if __has_include(<esp_heap_caps.h>)
#include <esp_heap_caps.h>
#endif

namespace heating::control {
// Heating telemetry: counted in /status/logs (heating_telemetry_*). Static:
// read-modify-write atomics stay out of the PSRAM-resident transport.
struct TelemetryCounters {
    // dropped: over the hard limit, or a cycle skipped while the outbox was
    // above its high-water mark; failed: the outbox refused it; large: > 1 KB.
    static inline std::atomic<uint32_t> dropped{0}, failed{0}, large{0};
};

// Which topic goes out when (TELEMETRIEBUDGET.nl.md sections 4 and 5), one
// tick per second from the MQTT loop: the heating documents every other
// second, the boiler state in between, one boiler field group and one learned
// room per tick, the summary and shadow every 5 minutes, the heartbeat every
// 60 s. At most `burst` messages per tick, so a (re)connect sends everything
// once, spread over some seconds. Retained except the heartbeat. A room, sensor
// or entity part that left the plan gets its retained topic cleared.
class TelemetryPublisher {
public:
    struct Sources {
        std::function<cJSON*()> status;                          // compact status, ours to delete
        std::function<size_t()> roomCount;
        std::function<std::string(size_t, std::string&)> learned; // payload, room id
        std::function<std::string()> summary;
        std::function<void(std::string&, size_t)> boilerGroup;    // EmsController::getBoilerFieldGroup
        std::function<std::string()> heartbeat;
    };
    using Publish = std::function<bool(const std::string& suffix, std::string_view payload, bool retained)>;
    using Ready = std::function<bool()>;
    static constexpr size_t maxSlots = 64, lastPayloads = 40, burst = 6;
    static constexpr uint64_t tickMs = 1000, heartbeatMs = 60000;

    TelemetryPublisher(Sources sources, Publish publish, Ready ready)
        : sources_(std::move(sources)), publish_(std::move(publish)), ready_(std::move(ready)) {
        // Once: the last sent payload of every deadband topic (PSRAM on the E32).
#if __has_include(<esp_heap_caps.h>)
        store_ = static_cast<char*>(heap_caps_malloc(lastPayloads * telemetryHardBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
#else
        store_ = static_cast<char*>(std::malloc(lastPayloads * telemetryHardBytes));
#endif
        slots_.reserve(maxSlots);
    }
    ~TelemetryPublisher() {
#if __has_include(<esp_heap_caps.h>)
        heap_caps_free(store_);
#else
        std::free(store_);
#endif
    }
    TelemetryPublisher(const TelemetryPublisher&) = delete;
    TelemetryPublisher& operator=(const TelemetryPublisher&) = delete;

    // A new broker session: everything goes out once more, the heartbeat first.
    void connected(uint64_t now) {
        for (auto& s : slots_) s.state.reset();
        nextTick_ = now; nextHeartbeat_ = now; phase_ = 0;
    }
    void tick(uint64_t now) {
        if (now < nextTick_ && nextTick_ - now <= tickMs) return;
        nextTick_ = now + tickMs;
        if (sources_.heartbeat && now >= nextHeartbeat_) {
            const auto beat = sources_.heartbeat();
            if (!beat.empty() && publish_("fw/heartbeat", beat, false)) nextHeartbeat_ = now + heartbeatMs;
        }
        if (ready_ && !ready_()) { TelemetryCounters::dropped.fetch_add(1, std::memory_order_relaxed); return; }
        budget_ = burst;
        if (phase_++ % 2 == 0) heating(now); else boilerState(now);
        boilerGroup(now);
        learned(now);
        if (sources_.summary) summary(now);
    }

private:
    enum class Kind : uint8_t { heating, room, ble, plan, entities, shadow, learned, summary, boiler, group };
    struct Slot {
        std::string topic;
        Kind kind;
        TelemetrySlot state;
        int store = -1;      // index of its last payload, deadband topics only
        uint16_t size = 0;
        bool seen = false;
    };
    static bool hasBands(Kind k) {
        return k == Kind::heating || k == Kind::room || k == Kind::ble || k == Kind::learned || k == Kind::boiler || k == Kind::group;
    }
    static const TelemetryCadence& cadence(Kind k) {
        switch (k) {
        case Kind::plan: case Kind::entities: return configCadence;
        case Kind::shadow: case Kind::summary: return summaryCadence;
        case Kind::learned: return learnedCadence;
        case Kind::group: return fieldsCadence;
        default: return stateCadence;
        }
    }
    Slot* slot(const std::string& topic, Kind kind) {
        for (auto& s : slots_) if (s.topic == topic) return &s;
        if (slots_.size() >= maxSlots) return nullptr;
        Slot s{topic, kind, {}, -1, 0, false};
        if (hasBands(kind) && store_) {
            std::vector<bool> used(lastPayloads);
            for (const auto& o : slots_) if (o.store >= 0) used[size_t(o.store)] = true;
            for (size_t i = 0; i < lastPayloads; ++i) if (!used[i]) { s.store = int(i); break; }
        }
        slots_.push_back(std::move(s));
        return &slots_.back();
    }
    std::string_view last(const Slot& s) const { return s.store >= 0 ? std::string_view(store_ + size_t(s.store) * telemetryHardBytes, s.size) : std::string_view(); }
    bool changed(const Slot& s, const std::string& payload, const cJSON* doc) const {
        if (s.state.sent && telemetryHash(payload) == s.state.hash) return false;
        if (!doc) return true;
        switch (s.kind) {
        case Kind::heating: return changedBeyond(last(s), doc, heatingBands);
        case Kind::room: return changedBeyond(last(s), doc, roomBands);
        case Kind::ble: return changedBeyond(last(s), doc, bleBands);
        case Kind::learned: return changedBeyond(last(s), doc, learnedBands);
        case Kind::boiler: return boilerFieldsChanged(last(s), doc, boilerStateBand);
        case Kind::group: return boilerFieldsChanged(last(s), doc, boilerFieldBand);
        default: return true;
        }
    }
    // Decides and sends one document of its slot.
    void consider(Slot& s, const std::string& payload, const cJSON* doc, uint64_t now) {
        s.seen = true;
        if (!budget_ || payload.empty() || !s.state.due(now, cadence(s.kind), changed(s, payload, doc))) return;
        send(s, payload, now);
    }
    void send(Slot& s, const std::string& payload, uint64_t now) {
        if (payload.empty()) return;
        if (payload.size() > telemetryHardBytes) {  // never: the size tests bound every topic
            TelemetryCounters::dropped.fetch_add(1, std::memory_order_relaxed);
            s.state.mark(now, telemetryHash(payload));
            return;
        }
        if (payload.size() > telemetrySoftBytes) TelemetryCounters::large.fetch_add(1, std::memory_order_relaxed);
        --budget_;
        if (!publish_(s.topic, payload, true)) { TelemetryCounters::failed.fetch_add(1, std::memory_order_relaxed); return; }
        s.state.mark(now, telemetryHash(payload));
        if (s.store >= 0) { std::memcpy(store_ + size_t(s.store) * telemetryHardBytes, payload.data(), payload.size()); s.size = uint16_t(payload.size()); }
    }
    // Topics of `kinds` not seen in this round left the plan: clear them.
    template <class Match>
    void sweep(Match&& match) {
        for (size_t i = 0; i < slots_.size();) {
            Slot& s = slots_[i];
            if (match(s.kind) && !s.seen) {
                if (s.state.sent && !publish_(s.topic, std::string_view(), true)) { ++i; continue; }
                slots_.erase(slots_.begin() + std::ptrdiff_t(i));
                continue;
            }
            ++i;
        }
    }
    static std::string print(const cJSON* doc) {
        char* text = doc ? cJSON_PrintUnformatted(doc) : nullptr;
        std::string out = text ? text : "";
        cJSON_free(text);
        return out;
    }
    void heating(uint64_t now) {
        if (!sources_.status) return;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> status(sources_.status(), cJSON_Delete);
        if (!status) return;
        for (auto& s : slots_) if (s.kind <= Kind::shadow) s.seen = false;
        bool split = splitHeatingStatus(status.get(), [&](HeatingTopic topic, const std::string& suffix, const cJSON* doc) {
            const Kind kind = Kind(uint8_t(topic));
            if (kind == Kind::plan) {  // the plan's rooms keep their learned topics
                for (auto& s : slots_) if (s.kind == Kind::learned) s.seen = false;
                for (const cJSON* id = cJSON_GetObjectItemCaseSensitive(doc, "rooms")->child; id; id = id->next)
                    for (auto& s : slots_) if (s.kind == Kind::learned && s.topic == std::string("fw/telemetry/learned/") + id->valuestring) s.seen = true;
                planKnown_ = true;
            }
            if (Slot* s = slot(suffix, kind)) consider(*s, print(doc), doc, now);
        });
        if (!split) return;
        sweep([](Kind k) { return k == Kind::room || k == Kind::ble || k == Kind::entities; });
        sweep([](Kind k) { return k == Kind::learned; });
    }
    void boilerState(uint64_t now) {
        if (!sources_.boilerGroup || !budget_) return;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> doc(boilerStateDocument(sources_.boilerGroup), cJSON_Delete);
        if (Slot* s = doc ? slot("fw/state/boiler", Kind::boiler) : nullptr) consider(*s, print(doc.get()), doc.get(), now);
    }
    void boilerGroup(uint64_t now) {
        if (!sources_.boilerGroup || !budget_) return;
        const size_t g = group_++ % boilerFieldGroupCountV2;
        std::string raw;
        sources_.boilerGroup(raw, g);
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> doc(boilerEnvelope(boilerGroupValues(raw, g), int(g)), cJSON_Delete);
        if (Slot* s = doc ? slot("fw/state/boiler_fields/" + std::to_string(g), Kind::group) : nullptr) consider(*s, print(doc.get()), doc.get(), now);
    }
    // fw/telemetry/summary (learned header, hot water) and fw/telemetry/flow (the
    // flow policy's "flow" and "night_gas"): split so each stays within 1 KB.
    void summary(uint64_t now) {
        Slot* s = slot("fw/telemetry/summary", Kind::summary);
        Slot* f = slot("fw/telemetry/flow", Kind::summary);
        if (!s || !f || budget_ < 2 || !s->state.due(now, summaryCadence, false)) return;
        const auto raw = sources_.summary();
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> doc(cJSON_ParseWithLength(raw.data(), raw.size()), cJSON_Delete);
        if (!doc) return;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> flow(cJSON_CreateObject(), cJSON_Delete);
        if (!flow || !cJSON_AddNumberToObject(flow.get(), "schema", 1)) return;
        for (const char* key : {"flow", "night_gas"})
            if (cJSON* part = cJSON_DetachItemFromObjectCaseSensitive(doc.get(), key)) cJSON_AddItemToObject(flow.get(), key, part);
        send(*s, print(doc.get()), now);
        if (cJSON_GetArraySize(flow.get()) > 1) send(*f, print(flow.get()), now);
    }
    void learned(uint64_t now) {
        if (!sources_.roomCount || !sources_.learned || !budget_ || !planKnown_) return;
        const size_t rooms = sources_.roomCount();
        if (!rooms) return;
        const size_t room = room_++ % rooms;
        std::string id;
        const auto payload = sources_.learned(room, id);
        if (payload.empty() || !topicSafeRoomId(id)) return;
        Slot* s = slot("fw/telemetry/learned/" + id, Kind::learned);
        if (!s) return;
        std::unique_ptr<cJSON, decltype(&cJSON_Delete)> doc(cJSON_ParseWithLength(payload.data(), payload.size()), cJSON_Delete);
        consider(*s, payload, doc.get(), now);
    }
    Sources sources_;
    Publish publish_;
    Ready ready_;
    std::vector<Slot> slots_;
    char* store_ = nullptr;
    uint64_t nextTick_ = 0, nextHeartbeat_ = 0;
    size_t budget_ = 0, group_ = 0, room_ = 0;
    uint32_t phase_ = 0;
    bool planKnown_ = false;
};
}
