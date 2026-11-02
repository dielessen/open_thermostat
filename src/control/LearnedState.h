#pragma once
#include "control/FlowPolicy.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <string_view>
#include <type_traits>
namespace heating::control {
// What the thermostat learned, kept over restarts, power cuts and updates
// (rc.2; owner: "een echt zelflerende thermostaat"). Compact binary frames:
// one global (heating periods, gas calibration, the curve slope's sums, the
// option comparison of today and yesterday, the night ledger, ~0.25 KB) and
// one per plan room that learned something (counts, the heat-loss and
// capacity sums and the used flow bins: 0.1 KB + 41 B per bin, at most 0.95
// KB). A frame: version, kind, payload length (u16 LE), payload, CRC-32 of
// all before it; numbers in the E32's (little-endian) byte order. Not kept:
// open segments, windows and nights (uptime clocks) and what HA sends again
// (boiler power, calorific value, price). Another version, a bad CRC or a
// value that is not finite: the frame is ignored as a whole, never half
// loaded. A room comes back only into a plan room with its id and emitter.
// rc.2: the global frame is version 2, with the boiler's learned minimum flow
// (BoilerMinimumFlow, 8 B) at its end; a version 1 global frame is still read
// (the minimum then starts unlearned). Room frames stay version 1, so older
// firmware after a rollback keeps every room and only drops the global frame.
// Pure; LearnedStore below decides when the frames are written.
class LearnedState {
public:
    static constexpr uint8_t version = 1, globalVersion = 2; // room frames; the global frame (also reads 1)
    static constexpr char globalKind = 'G', roomKind = 'R';
    static constexpr size_t maxFrame = 1024;
    static constexpr size_t backupBytes = 4096; // in the settings backup: 8 KB of hex at most
    static uint32_t crc(const char* p, size_t n) {
        uint32_t c = ~0u;
        while (n--) { c ^= uint8_t(*p++); for (int k = 0; k < 8; ++k) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1))); }
        return ~c;
    }
    static std::string globalFrame(const FlowLearner& l, const FlowPolicy& p) {
        auto& m = const_cast<FlowLearner&>(l);   // Out only reads
        auto& q = const_cast<FlowPolicy&>(p);
        return frame(globalKind, globalVersion, [&](Out& o) { globals(o, m.period_, m.gas_, q.curveLearner_, q.compare_, q.nights_, m.minimum_); });
    }
    // Empty for a room that learned nothing yet (no NVS entry needed).
    static std::string roomFrame(const FlowLearner& l, size_t i) {
        if (i >= l.rooms_.size()) return {};
        auto& r = const_cast<FlowLearner::Room&>(l.rooms_[i]);
        if (!r.segments && !r.heat.coolSegments && !r.heat.powerSegments) return {};
        return frame(roomKind, version, [&](Out& o) { room(o, r); });
    }
    static bool restoreGlobal(std::string_view f, FlowLearner& l, FlowPolicy& p) {
        std::unique_ptr<Globals> g(new (std::nothrow) Globals{l.period_, l.gas_, p.curveLearner_, p.compare_, p.nights_, l.minimum_});
        if (!g) return false;
        g->minimum.forget(); // a version 1 frame has none
        if (!readGlobal(f, *g)) return false;
        l.period_ = g->period; l.gas_ = g->gas; p.curveLearner_ = g->curve; p.compare_ = g->compare; p.nights_ = g->nights;
        l.minimum_ = g->minimum;
        return true;
    }
    // Into the plan room with the same id and emitter (removed or changed: false);
    // `done` marks restored rooms, so an older duplicate of a room does not win.
    static bool restoreRoom(std::string_view f, FlowLearner& l, uint32_t& done) {
        std::unique_ptr<FlowLearner::Room> r(new (std::nothrow) FlowLearner::Room);
        if (!r || !readRoom(f, *r)) return false;
        for (size_t i = 0; i < l.rooms_.size(); ++i) {
            auto& t = l.rooms_[i];
            if (t.id != r->id || (done >> i & 1)) continue;
            if (t.emitter != r->emitter) return false;
            t.bins = r->bins; t.heat = r->heat;
            t.segments = r->segments; t.periods = r->periods; t.lastPeriod = r->lastPeriod; t.rejected = r->rejected;
            done |= 1u << i;
            return true;
        }
        return false;
    }
    // The settings backup: the global frame and as many room frames as fit in maxBytes.
    static std::string bundle(const FlowLearner& l, const FlowPolicy& p, size_t maxBytes) {
        std::string out = globalFrame(l, p);
        for (size_t i = 0; i < l.rooms_.size(); ++i) {
            const auto f = roomFrame(l, i);
            if (out.size() + f.size() <= maxBytes) out += f;
        }
        return out;
    }
    // Every frame valid (the backup check); nothing is applied. Heap, not the loop stack.
    static bool validBundle(std::string_view b) {
        std::unique_ptr<Globals> g(new (std::nothrow) Globals{});
        std::unique_ptr<FlowLearner::Room> r(new (std::nothrow) FlowLearner::Room);
        std::string_view f;
        size_t frames = 0;
        for (; g && r && next(b, f); ++frames)
            if (!(f[1] == globalKind ? readGlobal(f, *g) : readRoom(f, *r))) return false;
        return frames && b.empty();
    }
    // The rooms restored from a valid bundle; -1: invalid, nothing applied.
    static int restoreBundle(std::string_view b, FlowLearner& l, FlowPolicy& p) {
        if (!validBundle(b)) return -1;
        std::string_view f;
        uint32_t done = 0;
        int rooms = 0;
        while (next(b, f)) {
            if (f[1] == globalKind) restoreGlobal(f, l, p);
            else rooms += restoreRoom(f, l, done);
        }
        return rooms;
    }

private:
    struct Out {
        static constexpr bool reading = false;
        uint8_t version = 0; // of the frame being written
        std::string s;
        bool ok = true;
        template <class... T> void operator()(T&... v) { (s.append(reinterpret_cast<const char*>(&v), sizeof v), ...); }
    };
    struct In {
        static constexpr bool reading = true;
        const char* p = nullptr;
        size_t n = 0;
        uint8_t version = 0; // of the frame being read
        bool ok = true;
        template <class... T> void operator()(T&... v) { (take(v), ...); }
        template <class T> void take(T& v) {
            static_assert(std::is_trivially_copyable_v<T>);
            if (!ok || n < sizeof v) { ok = false; return; }
            std::memcpy(&v, p, sizeof v); p += sizeof v; n -= sizeof v;
            if constexpr (std::is_floating_point_v<T>) ok = std::isfinite(v);
        }
        bool done() const { return ok && !n; }
    };
    template <class F> static std::string frame(char kind, uint8_t v, F&& body) {
        Out o;
        o.version = v;
        o.s.assign(4, '\0'); o.s[0] = char(v); o.s[1] = kind;
        body(o);
        const size_t n = o.s.size() - 4;
        if (n + 8 > maxFrame) return {};
        o.s[2] = char(n & 0xFF); o.s[3] = char(n >> 8);
        const uint32_t c = crc(o.s.data(), o.s.size());
        o.s.append(reinterpret_cast<const char*>(&c), sizeof c);
        return o.s;
    }
    static bool open(std::string_view f, char kind, In& in) {
        if (f.size() < 8 || f[1] != kind) return false;
        const uint8_t v = uint8_t(f[0]);
        if (!(kind == globalKind ? v == 1 || v == globalVersion : v == version)) return false;
        const size_t n = uint8_t(f[2]) | size_t(uint8_t(f[3])) << 8;
        uint32_t c;
        if (f.size() != n + 8) return false;
        std::memcpy(&c, f.data() + 4 + n, sizeof c);
        if (c != crc(f.data(), n + 4)) return false;
        in.p = f.data() + 4; in.n = n; in.version = v;
        return true;
    }
    // The next frame of a bundle (by its length; the CRC is checked by open()).
    static bool next(std::string_view& b, std::string_view& f) {
        if (b.size() < 8) return false;
        const size_t n = (uint8_t(b[2]) | size_t(uint8_t(b[3])) << 8) + 8;
        if (n > b.size()) return false;
        f = b.substr(0, n); b.remove_prefix(n);
        return true;
    }
    struct Globals { uint16_t period = 0; GasCalibration gas; CurveLearner curve; FlowCompare compare; NightLedger nights; BoilerMinimumFlow minimum; };
    static bool readGlobal(std::string_view f, Globals& g) {
        In in;
        return open(f, globalKind, in) && (globals(in, g.period, g.gas, g.curve, g.compare, g.nights, g.minimum), in.done());
    }
    static bool readRoom(std::string_view f, FlowLearner::Room& r) {
        In in;
        return open(f, roomKind, in) && (room(in, r), in.done());
    }
    template <class IO, class T> static void optional(IO& io, std::optional<T>& v) {
        uint8_t has = v.has_value();
        io(has);
        if (!has) { v.reset(); return; }
        if (!v) v.emplace();
        io(*v);
    }
    // A fixed name (nullptr: none) as its index in `names`.
    template <class IO, size_t N> static void name(IO& io, const char*& s, const std::array<const char*, N>& names) {
        uint8_t i = 0xFF;
        for (uint8_t k = 0; k < N; ++k) if (s && !std::strcmp(s, names[k])) i = k;
        io(i);
        if constexpr (IO::reading) s = i < N ? names[i] : nullptr;
    }
    template <class IO> static void globals(IO& io, uint16_t& period, GasCalibration& g, CurveLearner& c, FlowCompare& f, NightLedger& n,
                                            BoilerMinimumFlow& m) {
        io(period, g.intervals_, g.rejected_, g.measuredSum_, g.predicted_, g.n_, g.r_, g.rr_);
        io(c.windows_, c.rejected_, c.sxy_, c.sxx_, c.n_);
        io(f.today_);
        optional(io, f.yesterday_);
        io(n.nights_, n.ratioN_, n.ratioSum_);
        uint8_t has = n.last_.has_value();
        io(has);
        if (!has) n.last_.reset();
        else {
            if (!n.last_) n.last_.emplace();
            night(io, *n.last_);
        }
        if (io.version < 2) return;
        // Version 2: the boiler's minimum flow; never above what BoilerMinimumFlow can learn.
        io(m.learnedC_, m.productId_, m.raises_, m.burnS_);
        if constexpr (IO::reading) if (m.learnedC_ > m.params().maxC) io.ok = false;
    }
    template <class IO> static void night(IO& io, NightLedger::Record& r) {
        io(r.startUtc, r.switchUtc);
        for (auto* v : {&r.measuredM3, &r.hotWaterM3, &r.heatingM3, &r.programM3, &r.thermostatM3, &r.recommendedM3}) optional(io, *v);
        name(io, r.status, std::array<const char*, 3>{"open", "measured", "no_meter"});
        name(io, r.recommended, std::array<const char*, 4>{"program", "hold_0_5", "hold_1_0", "thermostat_like"});
        if constexpr (IO::reading) if (!r.status) io.ok = false;
    }
    // A bin as FlowLearner::finish() builds it: 30 min (floor)..3 h segments up to binMemoryHours of
    // weight, a mean flow of 0..100 degC and a rate within maxRateCentiCPerHour (3 degC/h).
    static bool plausible(const FlowLearner::Bin& b) {
        if (!(b.w >= 0.1f && b.w <= 2 * FlowLearner::Params{}.binMemoryHours)) return false;
        const float f = b.wf / b.w, q = b.wr / b.w, qq = b.wrr / b.w;
        if (!(f >= 0 && f <= 100 && std::fabs(q) <= 10 && qq >= 0 && qq <= 100)) return false;
        if (!b.outdoorSegments) return true;
        if (!(b.ow > 0 && b.ow <= b.w * 1.001f)) return false;
        const float o = b.wo / b.ow;
        return std::fabs(o) <= 80 && b.woo >= 0 && b.woo / b.ow <= 6400 && std::fabs(b.wor / b.ow) <= 800 && std::fabs(b.wro / b.ow) <= 10;
    }
    template <class IO> static void room(IO& io, FlowLearner::Room& r) {
        uint8_t size = uint8_t(std::min<size_t>(r.id.size(), 32)), emitter = uint8_t(r.emitter);
        io(size);
        if constexpr (IO::reading) {
            if (!size || size > 32 || io.n < size) { io.ok = false; return; }
            r.id.assign(io.p, size); io.p += size; io.n -= size;
        } else io.s.append(r.id, 0, size);
        io(emitter);
        if constexpr (IO::reading) r.emitter = RoomPlan::Emitter(emitter);
        if (emitter > uint8_t(RoomPlan::Emitter::radiator)) io.ok = false;
        auto& h = r.heat;
        io(r.segments, r.periods, r.lastPeriod, r.rejected, h.coolSegments, h.powerSegments);
        io(h.cw, h.crd, h.cdd, h.pw, h.spr, h.spd, h.srr, h.srd, h.sdd);
        if constexpr (IO::reading) // weights and sums of squares are never negative
            if (!(h.cw >= 0 && h.cdd >= 0 && h.pw >= 0 && h.srr >= 0 && h.sdd >= 0)) io.ok = false;
        uint32_t used = 0;
        for (size_t i = 0; i < FlowLearner::binCount; ++i) if (r.bins[i].segments) used |= 1u << i;
        io(used);
        if (used >> FlowLearner::binCount) io.ok = false;
        for (size_t i = 0; i < FlowLearner::binCount && io.ok; ++i) {
            if (!(used >> i & 1)) continue;
            auto& b = r.bins[i];
            io(b.segments, b.periods, b.outdoorSegments, b.lastPeriod, b.w, b.wf, b.wr, b.wrr);
            if (b.outdoorSegments) io(b.ow, b.wo, b.woo, b.wor, b.wro); // without, they are all 0
            if (!b.segments || !plausible(b)) io.ok = false;             // a used bin has weight, and what finish() can produce
        }
    }
};

// The largest room frame: a 32-character id and all 20 bins with the outdoor known.
static_assert(4 + 1 + 32 + 1 + 6 * 2 + 9 * 8 + 4 + FlowLearner::binCount * (3 + 2 + 9 * 4) + 4 <= LearnedState::maxFrame);

// Keeps the frames in a backend, one entry per slot: 0 global, 1 + i the plan
// room i (NVS "ot_heating"/"learned", "learned0".."learned7" on the E32).
// Written at most every 6 h, at a day change and before a planned restart,
// and then only the slots whose bytes changed; a slot whose room left the plan
// or learned nothing is erased. A failed write keeps RAM as it is and is
// retried at the next save (NVS full: logged by the caller, never fatal).
class LearnedStore {
public:
    struct Backend {
        virtual bool read(size_t slot, std::string& out) = 0;      // false: absent
        virtual bool write(size_t slot, std::string_view bytes) = 0; // true: committed and read back
        virtual bool erase(size_t slot) = 0;
    protected:
        ~Backend() = default;
    };
    static constexpr uint64_t saveEveryMs = 6 * 3600000ull;
    static constexpr size_t slots = 1 + RoomPlan::maxRooms;
    static constexpr int32_t unknownDay = INT32_MIN;
    // At boot, after the plan and the tuning, before the first step: the rooms restored.
    size_t restore(Backend& b, FlowLearner& l, FlowPolicy& p, uint64_t now) {
        savedAt_ = now;
        size_t rooms = 0;
        uint32_t done = 0;
        for (size_t s = 0; s < slots; ++s) {
            std::string f;
            if (!b.read(s, f)) continue;
            present_ |= 1u << s; crc_[s] = content(f);
            if (s) rooms += LearnedState::restoreRoom(f, l, done);
            else LearnedState::restoreGlobal(f, l, p);
        }
        return rooms;
    }
    // Every step: true every 6 h and at a local day change (the first known day only starts it).
    bool due(uint64_t now, std::optional<uint32_t> unixNow) {
        if (unixNow) {
            const int32_t day = RoomSchedule::localDay(*unixNow);
            if (day_ == unknownDay) day_ = day;
            else if (day > day_) { day_ = day; return true; }
        }
        return now - savedAt_ >= saveEveryMs;
    }
    // The changed slots; false when a write or erase failed.
    bool save(Backend& b, const FlowLearner& l, const FlowPolicy& p, uint64_t now) {
        savedAt_ = now;
        bool ok = true;
        for (size_t s = 0; s < slots; ++s) {
            const auto f = s ? LearnedState::roomFrame(l, s - 1) : LearnedState::globalFrame(l, p);
            const bool had = present_ >> s & 1;
            if (f.empty()) {
                if (had && b.erase(s)) present_ &= ~(1u << s);
                else if (had) ok = false;
                continue;
            }
            const uint32_t c = content(f);
            if (had && crc_[s] == c) continue;
            if (b.write(s, f)) { present_ |= 1u << s; crc_[s] = c; }
            else ok = false;
        }
        return ok;
    }
private:
    // A frame's identity: the CRC of all but its own CRC (with it, every valid frame has the same residue).
    static uint32_t content(std::string_view f) { return LearnedState::crc(f.data(), f.size() - std::min<size_t>(f.size(), 4)); }
    std::array<uint32_t, slots> crc_{};
    uint32_t present_ = 0;   // slots the backend holds
    uint64_t savedAt_ = 0;
    int32_t day_ = unknownDay;
};
}
