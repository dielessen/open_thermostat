#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <ostream>

namespace heating::control {

// 24 hours of charts without Home Assistant (beta.19 item 20): one 5-minute
// average per series in a fixed ring, allocated once in PSRAM at boot. RAM
// only (no flash wear): the history starts again after every restart.
//
// Storage is int16 fixed point: temperatures in 0.1 degC, the burner as the
// percentage of samples with the burner on. INT16_MIN marks "no value". Room
// columns follow the room id, so renaming, adding or reordering rooms keeps
// the history of the rooms that stay and clears only a column that changes
// hands. Owned by the loop task, like the HTTP server that reads it.
class HeatingHistory {
public:
    static constexpr size_t slots = 288;                // 24 h
    static constexpr uint32_t periodMs = 300000;        // 5 min
    static constexpr size_t rooms = 8;                  // RoomPlan::maxRooms
    static constexpr size_t idBytes = 33;               // room ids are at most 32 characters
    static constexpr int16_t none = INT16_MIN;
    enum Column : uint8_t { flow, returnTemp, burner, request, thermostat, roomBase };
    static constexpr size_t columns = roomBase + 2 * rooms; // per room: temperature, target
    using Allocate = void* (*)(size_t);
    using Release = void (*)(void*);

    struct Sample {
        std::array<std::optional<int16_t>, rooms> temperatureCentiC{}, targetCentiC{};
        std::optional<int16_t> flowCentiC, returnCentiC;
        std::optional<bool> burnerOn;
        std::optional<uint8_t> requestFlowC;     // the E32's request; 0 = no heat
        std::optional<uint8_t> thermostatFlowC;  // the existing thermostat's request; 0 = no heat
    };

    HeatingHistory() = default;
    HeatingHistory(const HeatingHistory&) = delete;
    HeatingHistory& operator=(const HeatingHistory&) = delete;
    ~HeatingHistory() { if (store_ && release_) release_(store_); }

    // Once at boot. false: no memory, the charts are unavailable (never retried).
    bool begin(Allocate allocate, Release release) {
        if (store_ || attempted_) return store_ != nullptr;
        attempted_ = true;
        if (!allocate || !release) return false;
        store_ = static_cast<Store*>(allocate(sizeof(Store)));
        if (!store_) return false;
        release_ = release;
        std::fill(&store_->ring[0][0], &store_->ring[0][0] + slots * columns, none);
        std::memset(store_->ids, 0, sizeof(store_->ids));
        clearAccumulators();
        return true;
    }
    bool available() const { return store_ != nullptr; }
    static constexpr size_t bytes() { return sizeof(Store); }

    // The current room ids, in plan order; called before every sample (cheap
    // when nothing changed). A new id takes a free column, cleared first.
    template <class IdAt> void syncRooms(size_t count, IdAt idAt) {
        if (!store_) return;
        count = std::min(count, rooms);
        bool same = count == roomCount_;
        for (size_t i = 0; same && i < count; ++i) same = std::strcmp(store_->ids[order_[i]], idAt(i)) == 0;
        if (same) return;
        std::array<bool, rooms> kept{};
        std::array<uint8_t, rooms> next{};
        std::array<bool, rooms> placed{};
        for (size_t i = 0; i < count; ++i)
            for (uint8_t c = 0; c < rooms; ++c)
                if (!kept[c] && store_->ids[c][0] && std::strcmp(store_->ids[c], idAt(i)) == 0) { kept[c] = true; next[i] = c; placed[i] = true; break; }
        for (size_t i = 0; i < count; ++i) {
            if (placed[i]) continue;
            uint8_t c = 0;
            while (kept[c]) ++c; // count <= rooms: a column is free
            kept[c] = true; next[i] = c;
            clearRoom(c);
            std::strncpy(store_->ids[c], idAt(i), idBytes - 1);
            store_->ids[c][idBytes - 1] = 0;
        }
        for (uint8_t c = 0; c < rooms; ++c) if (!kept[c] && store_->ids[c][0]) { clearRoom(c); store_->ids[c][0] = 0; }
        order_ = next; roomCount_ = static_cast<uint8_t>(count);
    }

    // Every control step (10 s). Room i is plan room i (see syncRooms).
    void sample(uint64_t nowMs, const Sample& s) {
        if (!store_) return;
        advance(nowMs / periodMs);
        auto& a = store_->acc;
        const auto temperature = [&](size_t c, const std::optional<int16_t>& v) { if (v) { a[c].sum += *v; ++a[c].n; } };
        const auto requested = [&](size_t c, const std::optional<uint8_t>& v) {
            if (!v) return;
            if (*v) { a[c].sum += int32_t(*v) * 100; ++a[c].n; } else ++a[c].zeros;
        };
        temperature(flow, s.flowCentiC);
        temperature(returnTemp, s.returnCentiC);
        if (s.burnerOn) { a[burner].sum += *s.burnerOn ? 1 : 0; ++a[burner].n; }
        requested(request, s.requestFlowC);
        requested(thermostat, s.thermostatFlowC);
        for (size_t i = 0; i < roomCount_; ++i) {
            temperature(roomBase + 2 * order_[i], s.temperatureCentiC[i]);
            temperature(roomBase + 2 * order_[i] + 1, s.targetCentiC[i]);
        }
        sampled_ = true;
    }

    // Committed 5-minute points plus the running one, oldest first.
    size_t points() const {
        return store_ ? count_ + (sampled_ ? 1 : 0) : 0;
    }
    // Value of point p (0 = oldest) in column c; none when unknown.
    int16_t value(size_t p, size_t c) const {
        if (!store_ || c >= columns || p >= points()) return none;
        if (p == count_) return encode(c, store_->acc[c]);
        return store_->ring[(head_ + slots - count_ + p) % slots][c];
    }
    size_t roomCount() const { return roomCount_; }
    const char* roomId(size_t i) const { return store_ && i < roomCount_ ? store_->ids[order_[i]] : ""; }
    static constexpr size_t temperatureColumn(uint8_t column) { return roomBase + 2 * column; }

    // GET /status/history: compact JSON, temperatures in 0.1 degC. The
    // browser places point p at oldest_start_ago_s - p * period_s seconds ago
    // (the slot start); a series without any value is null.
    void json(std::ostream& out, uint64_t nowMs) const {
        out << "{\"schema\":1,\"available\":" << (store_ ? "true" : "false") << ",\"period_s\":" << periodMs / 1000
            << ",\"capacity\":" << slots << ",\"bytes\":" << bytes() << ",\"uptime_s\":" << nowMs / 1000;
        if (!store_) { out << ",\"reason\":\"memory_unavailable\",\"points\":0}"; return; }
        const size_t n = points();
        out << ",\"points\":" << n << ",\"partial\":" << (partial(nowMs) ? "true" : "false");
        if (n) out << ",\"oldest_start_ago_s\":" << (nowMs - (currentSlot_ - count_) * uint64_t(periodMs)) / 1000;
        out << ",\"rooms\":[";
        for (size_t i = 0; i < roomCount_; ++i) {
            if (i) out << ',';
            out << "{\"id\":\""; writeId(out, store_->ids[order_[i]]);
            out << "\",\"temperature\":"; series(out, roomBase + 2 * order_[i], n);
            out << ",\"target\":"; series(out, roomBase + 2 * order_[i] + 1, n);
            out << '}';
        }
        out << "],\"flow\":"; series(out, flow, n);
        out << ",\"return\":"; series(out, returnTemp, n);
        out << ",\"burner_pct\":"; series(out, burner, n);
        out << ",\"request\":"; series(out, request, n);
        out << ",\"thermostat_request\":"; series(out, thermostat, n);
        out << '}';
    }

private:
    struct Accumulator { int32_t sum = 0; uint16_t n = 0, zeros = 0; };
    struct Store {
        int16_t ring[slots][columns];
        Accumulator acc[columns];
        char ids[rooms][idBytes];
    };
    Store* store_ = nullptr;
    Release release_ = nullptr;
    bool attempted_ = false, started_ = false, sampled_ = false; // sampled_: the running slot has a sample
    uint64_t currentSlot_ = 0;   // 5-minute slot number since boot of the running average
    size_t head_ = 0, count_ = 0; // next ring row, committed rows
    std::array<uint8_t, rooms> order_{};
    uint8_t roomCount_ = 0;

    // The running slot (always the newest point once sampled) is still filling.
    bool partial(uint64_t nowMs) const { return sampled_ && nowMs / periodMs == currentSlot_; }

    static int16_t roundDiv(int32_t a, int32_t b) {
        const int32_t q = a >= 0 ? (a + b / 2) / b : -((-a + b / 2) / b);
        return static_cast<int16_t>(std::clamp<int32_t>(q, -32767, 32767));
    }
    static int16_t encode(size_t c, const Accumulator& a) {
        if (c == burner) return a.n ? roundDiv(a.sum * 100, a.n) : none;
        if (c == request || c == thermostat) return a.n ? roundDiv(a.sum, int32_t(a.n) * 10) : a.zeros ? 0 : none;
        return a.n ? roundDiv(a.sum, int32_t(a.n) * 10) : none;
    }
    void clearAccumulators() { for (auto& a : store_->acc) a = Accumulator{}; sampled_ = false; }
    void push(bool fromAccumulator) {
        for (size_t c = 0; c < columns; ++c) store_->ring[head_][c] = fromAccumulator ? encode(c, store_->acc[c]) : none;
        head_ = (head_ + 1) % slots;
        count_ = std::min(count_ + 1, slots);
    }
    // Commit the running slot when time moved on; missed slots become gaps.
    void advance(uint64_t slot) {
        if (!started_) { started_ = true; currentSlot_ = slot; return; }
        if (slot <= currentSlot_) return;
        push(true);
        const uint64_t gaps = std::min<uint64_t>(slot - currentSlot_ - 1, slots);
        for (uint64_t i = 0; i < gaps; ++i) push(false);
        currentSlot_ = slot;
        clearAccumulators();
    }
    void clearRoom(uint8_t column) {
        for (size_t r = 0; r < slots; ++r) store_->ring[r][temperatureColumn(column)] = store_->ring[r][temperatureColumn(column) + 1] = none;
        store_->acc[temperatureColumn(column)] = store_->acc[temperatureColumn(column) + 1] = Accumulator{};
    }
    static void writeId(std::ostream& out, const char* id) {
        for (; *id; ++id) if (*id != '"' && *id != '\\' && static_cast<unsigned char>(*id) >= 0x20) out << *id; // ids are identifiers
    }
    void series(std::ostream& out, size_t c, size_t n) const {
        bool any = false;
        for (size_t p = 0; p < n && !any; ++p) any = value(p, c) != none;
        if (!any) { out << "null"; return; }
        out << '[';
        for (size_t p = 0; p < n; ++p) {
            if (p) out << ',';
            const int16_t v = value(p, c);
            if (v == none) out << "null"; else out << v;
        }
        out << ']';
    }
};

} // namespace heating::control
