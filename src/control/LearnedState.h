#pragma once
#include "control/ControlPartitionBudget.h"
#include "control/FlowPolicy.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>
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
// (the minimum then starts unlearned). Room frames are version 2: the heat sums
// as float and each used bin as means and spreads in fixed point (19 B a bin
// with the outdoor known for all its segments, else 23 or 13 B; version 1: 41
// B), ~0.06 KB + 19 B a bin. A room with a value outside the fixed-point ranges
// keeps version 1 (lossless), which is still read. No released firmware reads
// room frames (rc.2 is the first that learns over restarts).
// Pure; LearnedStore below decides when the frames are written.
class LearnedState {
public:
    static constexpr uint8_t version = 1, roomVersion = 2, globalVersion = 2; // room frames v1 (lossless) and v2; the global frame (also reads 1)
    static constexpr char globalKind = 'G', roomKind = 'R';
    static constexpr size_t maxFrame = 1024;
    // A version 2 room frame's size: an id of `idBytes`, bins whose segments all had the
    // outdoor (19 B), bins where some had (23 B) and bins without it (13 B).
    static constexpr size_t compactRoomBytes(size_t idBytes, size_t outdoorBins, size_t partialBins = 0, size_t indoorBins = 0) {
        return 4 + 1 + idBytes + 1 + 6 * 2 + 9 * 4 + 2 * 4 + outdoorBins * 19 + partialBins * 23 + indoorBins * 13 + 4;
    }
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
    // Empty for a room that learned nothing yet (no NVS entry needed). Version 2
    // when every value fits its fixed point and the frame reads back plausible,
    // else version 1 (`v` = version: always version 1, the lossless form).
    static std::string roomFrame(const FlowLearner& l, size_t i, uint8_t v = roomVersion) {
        if (i >= l.rooms_.size()) return {};
        auto& r = const_cast<FlowLearner::Room&>(l.rooms_[i]);
        if (!r.segments && !r.heat.coolSegments && !r.heat.powerSegments) return {};
        if (v == roomVersion) {
            auto f = frame(roomKind, roomVersion, [&](Out& o) { compactRoom(o, r); });
            std::unique_ptr<FlowLearner::Room> back(new (std::nothrow) FlowLearner::Room);
            if (!f.empty() && back && readRoom(f, *back)) return f;
        }
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
    // A packed record part (LearnedStore): each valid frame applied (the global
    // frame only while `global` is false), a damaged frame skipped, a bad length
    // ends the walk. The rooms restored.
    static size_t restoreFrames(std::string_view b, FlowLearner& l, FlowPolicy& p, uint32_t& done, bool& global) {
        std::string_view f;
        size_t rooms = 0;
        while (next(b, f)) {
            if (f[1] == globalKind) { if (!global && restoreGlobal(f, l, p)) global = true; }
            else rooms += restoreRoom(f, l, done);
        }
        return rooms;
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
        if (!o.ok || n + 8 > maxFrame) return {};
        o.s[2] = char(n & 0xFF); o.s[3] = char(n >> 8);
        const uint32_t c = crc(o.s.data(), o.s.size());
        o.s.append(reinterpret_cast<const char*>(&c), sizeof c);
        return o.s;
    }
    static bool open(std::string_view f, char kind, In& in) {
        if (f.size() < 8 || f[1] != kind) return false;
        const uint8_t v = uint8_t(f[0]);
        if (!(kind == globalKind ? v == 1 || v == globalVersion : v == version || v == roomVersion)) return false;
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
        return open(f, roomKind, in) && (in.version == roomVersion ? compactRoom(in, r) : room(in, r), in.done());
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
    // Both versions: the id, the emitter and the room's counts.
    template <class IO> static void roomHead(IO& io, FlowLearner::Room& r) {
        uint8_t size = uint8_t(std::min<size_t>(r.id.size(), 32)), emitter = uint8_t(r.emitter);
        io(size);
        if constexpr (IO::reading) {
            if (!size || size > 32 || io.n < size) { io.ok = false; return; }
            r.id.assign(io.p, size); io.p += size; io.n -= size;
        } else io.s.append(r.id, 0, size);
        io(emitter);
        if constexpr (IO::reading) r.emitter = RoomPlan::Emitter(emitter);
        if (emitter > uint8_t(RoomPlan::Emitter::radiator)) io.ok = false;
        io(r.segments, r.periods, r.lastPeriod, r.rejected, r.heat.coolSegments, r.heat.powerSegments);
    }
    static bool heatPlausible(const FlowLearner::Heat& h) { // weights and sums of squares are never negative
        return h.cw >= 0 && h.cdd >= 0 && h.pw >= 0 && h.srr >= 0 && h.sdd >= 0;
    }
    // Version 1: every sum as it is in RAM (lossless).
    template <class IO> static void room(IO& io, FlowLearner::Room& r) {
        roomHead(io, r);
        auto& h = r.heat;
        io(h.cw, h.crd, h.cdd, h.pw, h.spr, h.spd, h.srr, h.srd, h.sdd);
        if constexpr (IO::reading) if (!heatPlausible(h)) io.ok = false;
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
    // Version 2: the heat sums as float (relative 6e-8), then two masks: the used bins and,
    // among those with outdoor segments, the ones whose outdoor weight is not their own
    // (an outdoor reading was missing in some segment). A bin: its counts (5 B), then its
    // weight (u16, 1/600 h), mean flow (i16, 0.01 degC), mean rate and the rate's spread
    // (i16 and u16, 0.001 degC/h); with outdoor segments the mean outdoor (i16, 0.01 degC),
    // its spread (u16, 0.01 K) and the outdoor x rate covariance (i16, 0.001 degC^2/h), and
    // for a partial bin first its outdoor weight and mean rate. The sums come back as
    // weight x mean (+ spread^2): the flow 0.005 degC, the rates 0.0005 degC/h from RAM.
    static constexpr double hourScale = 600, centiScale = 100, milliScale = 1000;
    template <class T> static bool fixed(double v, double scale, T& out) {
        const double r = learnmath::round(v * scale); // not std::round: no libm member (FlowLearner.h)
        if (!(r >= double(std::numeric_limits<T>::min()) && r <= double(std::numeric_limits<T>::max()))) return false; // NaN too
        out = T(r);
        return true;
    }
    static double spread(double meanSquare, double mean) { return learnmath::sqrt(std::max(0.0, meanSquare - mean * mean)); }
    static void compactRoom(Out& o, FlowLearner::Room& r) {
        roomHead(o, r);
        auto& h = r.heat;
        for (const double d : {h.cw, h.crd, h.cdd, h.pw, h.spr, h.spd, h.srr, h.srd, h.sdd}) {
            const float v = float(d);
            if (!std::isfinite(v)) { o.ok = false; return; }
            o(v);
        }
        uint32_t used = 0, partial = 0;
        for (size_t i = 0; i < FlowLearner::binCount; ++i) {
            const auto& b = r.bins[i];
            if (!b.segments) continue;
            used |= 1u << i;
            if (b.outdoorSegments && !(b.ow == b.w && b.wro == b.wr)) partial |= 1u << i;
        }
        o(used, partial);
        for (size_t i = 0; i < FlowLearner::binCount && o.ok; ++i) {
            if (!(used >> i & 1)) continue;
            auto& b = r.bins[i];
            o(b.segments, b.periods, b.outdoorSegments, b.lastPeriod);
            const double w = b.w, q = b.wr / w;
            uint16_t qw = 0, qs = 0; int16_t qf = 0, qq = 0;
            o.ok = w > 0 && fixed(w, hourScale, qw) && fixed(b.wf / w, centiScale, qf) && fixed(q, milliScale, qq)
                && fixed(spread(b.wrr / w, q), milliScale, qs);
            o(qw, qf, qq, qs);
            if (!b.outdoorSegments || !o.ok) continue;
            const double ow = b.ow, qo = b.wro / ow, t = b.wo / ow;
            if (partial >> i & 1) {
                uint16_t qow = 0; int16_t qqo = 0;
                o.ok = ow > 0 && fixed(ow, hourScale, qow) && fixed(qo, milliScale, qqo);
                qow = std::min(qow, qw); // a part of the weight, also after rounding
                o(qow, qqo);
            }
            uint16_t qso = 0; int16_t qt = 0, qc = 0;
            o.ok = o.ok && ow > 0 && fixed(t, centiScale, qt) && fixed(spread(b.woo / ow, t), centiScale, qso)
                && fixed(b.wor / ow - t * qo, milliScale, qc);
            o(qt, qso, qc);
        }
    }
    static void compactRoom(In& in, FlowLearner::Room& r) {
        roomHead(in, r);
        auto& h = r.heat;
        for (double* d : {&h.cw, &h.crd, &h.cdd, &h.pw, &h.spr, &h.spd, &h.srr, &h.srd, &h.sdd}) {
            float v = 0;
            in(v);           // not finite: refused by In::take
            *d = v;
        }
        if (!heatPlausible(h)) in.ok = false;
        uint32_t used = 0, partial = 0;
        in(used, partial);
        if (used >> FlowLearner::binCount || partial & ~used) in.ok = false;
        for (size_t i = 0; i < FlowLearner::binCount && in.ok; ++i) {
            if (!(used >> i & 1)) continue;
            auto& b = r.bins[i];
            uint16_t qw = 0, qs = 0; int16_t qf = 0, qq = 0;
            in(b.segments, b.periods, b.outdoorSegments, b.lastPeriod, qw, qf, qq, qs);
            const double w = qw / hourScale, q = qq / milliScale, sd = qs / milliScale;
            b.w = float(w); b.wf = float(w * (qf / centiScale)); b.wr = float(w * q); b.wrr = float(w * (sd * sd + q * q));
            if (partial >> i & 1 && !b.outdoorSegments) in.ok = false;
            if (b.outdoorSegments) {
                double ow = w, qo = q;
                if (partial >> i & 1) {
                    uint16_t qow = 0; int16_t qqo = 0;
                    in(qow, qqo);
                    ow = qow / hourScale; qo = qqo / milliScale;
                    b.ow = float(ow); b.wro = float(ow * qo);
                } else { b.ow = b.w; b.wro = b.wr; } // exactly as finish() sums them
                uint16_t qso = 0; int16_t qt = 0, qc = 0;
                in(qt, qso, qc);
                const double t = qt / centiScale, so = qso / centiScale, c = qc / milliScale;
                b.wo = float(ow * t); b.woo = float(ow * (so * so + t * t)); b.wor = float(ow * (c + t * qo));
            }
            if (!b.segments || !plausible(b)) in.ok = false;
        }
    }
};

// The largest room frame: a 32-character id and all 20 bins with the outdoor known
// (version 1; version 2 is smaller: 4 + 33 + 1 + 12 + 36 + 8 + 20 x 23 + 4 = 558 B).
static_assert(4 + 1 + 32 + 1 + 6 * 2 + 9 * 8 + 4 + FlowLearner::binCount * (3 + 2 + 9 * 4) + 4 <= LearnedState::maxFrame);
static_assert(LearnedState::compactRoomBytes(32, 0, FlowLearner::binCount) == 558);

// Keeps the frames in a backend as one packed record of at most two parts
// (NVS "ot_heating"/"learned_a", "learned_b" on the E32): the global frame,
// then each plan room that learned something, in plan order, a part holding
// whole frames up to partBytes. One record instead of a key per room: NVS
// charges every blob its index, a chunk header and the rounding of its last
// 32-byte entry (control/ControlPartitionBudget.h blobEntries: 6 entries a
// blob), and the frames are version 2 (LearnedState above).
// Written at most every 6 h, at a day change and before a planned restart,
// and then only the parts whose frames changed. A write the backend refuses
// (NVS short of room: control first) is retried without its last frames, so
// the globals and the first rooms are kept; what does not fit stays in RAM
// (pendingEntries) and is tried again at the next save. A part no longer
// needed is erased once everything before it was written.
// rc.2 builds before the packed record kept a key per frame ("learned",
// "learned0".."learned7"): read when no part exists, erased once the packed
// record holds everything (or when it needs their room).
class LearnedStore {
public:
    struct Backend {
        virtual bool read(size_t part, std::string& out) = 0;      // false: absent
        virtual bool write(size_t part, std::string_view bytes) = 0; // true: committed and read back
        virtual bool erase(size_t part) = 0;
        // The per-frame keys of earlier rc.2 builds: 0 global, 1 + i room i.
        virtual bool readLegacy(size_t slot, std::string& out) { (void)slot; (void)out; return false; }
        virtual bool eraseLegacy(size_t slot) { (void)slot; return true; }
    protected:
        ~Backend() = default;
    };
    static constexpr uint64_t saveEveryMs = 6 * 3600000ull;
    static constexpr size_t parts = 2, partBytes = 4000, legacySlots = 1 + RoomPlan::maxRooms;
    static constexpr int32_t unknownDay = INT32_MIN;
    // At boot, after the plan and the tuning, before the first step: the rooms restored.
    size_t restore(Backend& b, FlowLearner& l, FlowPolicy& p, uint64_t now) {
        savedAt_ = now;
        size_t rooms = 0;
        uint32_t done = 0;
        bool global = false;
        for (size_t i = 0; i < parts; ++i) {
            std::string f;
            if (!b.read(i, f)) continue;
            present_ |= 1u << i; id_[i] = identity(f);
            rooms += LearnedState::restoreFrames(f, l, p, done, global);
        }
        // The per-frame keys: restored only without a part (an interrupted migration
        // leaves both); erased by the next save that stores everything.
        const bool packed = present_ != 0;
        for (size_t s = 0; s < legacySlots; ++s) {
            std::string f;
            if (!b.readLegacy(s, f)) continue;
            legacy_ |= 1u << s;
            if (packed) continue;
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
    // The changed parts; true when every frame is stored.
    bool save(Backend& b, const FlowLearner& l, const FlowPolicy& p, uint64_t now) {
        savedAt_ = now;
        std::vector<std::string> frames;
        if (auto g = LearnedState::globalFrame(l, p); !g.empty()) frames.push_back(std::move(g));
        for (size_t i = 0; i < l.rooms(); ++i)
            if (auto f = LearnedState::roomFrame(l, i); !f.empty()) frames.push_back(std::move(f));
        bool complete = savePacked(b, frames);
        if (legacy_ && !complete) {
            // The old per-frame keys hold room the packed record needs: theirs is in RAM (restored).
            eraseLegacy(b);
            complete = savePacked(b, frames);
        }
        if (legacy_ && complete) eraseLegacy(b);
        rooms_ = frames.empty() ? 0 : frames.size() - (frames[0][1] == LearnedState::globalKind);
        return complete;
    }
    // Parts erased behind the store's back (a plan save made room): the next save writes
    // every part again where it fits, and erases what is no longer needed.
    void forgetStored() { present_ = (1u << parts) - 1; unsure_ = present_; }
    // After a save: the rooms that learned something and how many of them are stored.
    size_t rooms() const { return rooms_; }
    size_t storedRooms() const { return storedRooms_; }
    // The NVS entries the frames left in RAM at the last save would need (each part
    // charged whole, ControlPartitionBudget::blobEntries): the knobs' log leaves them room.
    size_t pendingEntries() const { return pendingEntries_; }
private:
    // A part's identity: the CRC over its frames' CRCs (the CRC of a whole part would not
    // do: after a frame that ends in its own CRC the register always holds the same residue).
    static uint32_t identity(std::string_view part) {
        std::string crcs;
        for (std::string_view f; part.size() >= 8;) {
            const size_t n = (uint8_t(part[2]) | size_t(uint8_t(part[3])) << 8) + 8;
            if (n > part.size()) break;
            f = part.substr(0, n); part.remove_prefix(n);
            crcs.append(f.data() + n - 4, 4);
        }
        crcs.append(part.data(), part.size()); // a damaged tail still counts
        return LearnedState::crc(crcs.data(), crcs.size());
    }
    bool savePacked(Backend& b, const std::vector<std::string>& frames) {
        size_t next = 0, stored = 0, pending = 0;
        bool complete = true;
        for (size_t i = 0; i < parts; ++i) {
            const uint32_t bit = 1u << i;
            size_t planned = next, plannedBytes = 0;
            while (planned < frames.size() && plannedBytes + frames[planned].size() <= partBytes) plannedBytes += frames[planned++].size();
            if (planned == next) {
                // Nothing for this part: erased once everything before it was written.
                if ((present_ & bit) && complete) {
                    if (b.erase(i)) { present_ &= ~bit; unsure_ &= ~bit; }
                    else complete = false;
                }
                continue;
            }
            size_t end = planned, bytes = plannedBytes;
            bool written = false;
            for (; end > next; bytes -= frames[--end].size()) { // refused: again without the last frame
                std::string part;
                part.reserve(bytes);
                for (size_t k = next; k < end; ++k) part += frames[k];
                const uint32_t id = identity(part);
                if ((present_ & bit) && id_[i] == id && !(unsure_ & bit)) { written = true; break; }
                if (b.write(i, part)) { present_ |= bit; unsure_ &= ~bit; id_[i] = id; written = true; break; }
            }
            if (written) stored += end - next;
            if (end < planned) {
                // Refused (at least its last frames): an older part stays as it was.
                complete = false;
                pending += 1 + ControlPartitionBudget::blobEntries(plannedBytes) - (written ? 1 + ControlPartitionBudget::blobEntries(bytes) : 0);
            }
            next = planned;
        }
        if (next < frames.size()) complete = false; // beyond the last part: RAM only (not with 8 rooms of version 2)
        storedRooms_ = stored - (stored && frames[0][1] == LearnedState::globalKind);
        pendingEntries_ = pending;
        return complete;
    }
    void eraseLegacy(Backend& b) {
        for (size_t s = 0; s < legacySlots; ++s)
            if ((legacy_ >> s & 1) && b.eraseLegacy(s)) legacy_ &= ~(1u << s);
    }
    std::array<uint32_t, parts> id_{};
    uint32_t present_ = 0;   // parts the backend holds
    uint32_t unsure_ = 0;    // parts it may have lost (forgetStored)
    uint32_t legacy_ = 0;    // per-frame keys of earlier rc.2 builds still stored
    size_t rooms_ = 0, storedRooms_ = 0, pendingEntries_ = 0;
    uint64_t savedAt_ = 0;
    int32_t day_ = unknownDay;
};
}
