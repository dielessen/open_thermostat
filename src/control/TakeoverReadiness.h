#pragma once
#include "control/FlowDemand.h"
#include "control/RoomDemand.h"
#include "control/RoomSchedule.h"
#include "diagnostics/SupervisorPolicy.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <optional>
namespace heating::control {
// "Ready to take over?" (owner, 1 Nov 2026): the shadow exit criteria of
// tools/switchover/shadow_exit.py and docs/SWITCHOVER.md judged on the E32
// itself, so the Rooms page needs no Home Assistant token or script:
//   stable   72 h without an unexpected restart; planned ones (an update, a
//            restart from the pages, a settings restore) do not reset it
//   periods  10 thermostat heating periods, with a night setback, a morning
//            warm-up and a period of an hour without demand
//   timing   20 thermostat starts and stops; 80 % with an E32 one within
//            30 min, half of those within 5 min and 90 % within 15 min
//   flow     the E32 request never above min(plan maximum, boiler limit,
//            80 degC); judged after an hour of requests
//   cycling  not more E32 heating periods than the thermostat's (after 10)
//   sources  every active room measured; a fallback source took over once
// Without a thermostat on the bus (no 0x1A seen in the window) nothing can be
// compared: stable, sources, boiler (heard) and boiler_limit (0x16 read).
// Counters per local day over the last 7 days (today and 6 before); the
// caller stores them (stored()/restore()) so a restart keeps them. The
// thermostat side is its 0x1A flow >= ShadowComparison::tadoHeatFromC; a stop
// counts once it stayed off 2 min (shorter gaps merge, as in the script).
// Pure and single-threaded: sample() every 10 s; fixed size, no heap.
class TakeoverReadiness {
public:
    enum class Result : uint8_t { pass, wait, fail };
    enum class Restart : uint8_t { first, planned, unexpected, power }; // the one before this boot
    static constexpr uint32_t stableNeededS = 72 * 3600;
    static constexpr uint16_t periodsNeeded = 10, eventsNeeded = 2 * periodsNeeded;
    static constexpr uint64_t mergeGapMs = 120000;
    static constexpr uint32_t matchS = 1800, closeS = 300, nearS = 900;
    static constexpr int16_t setbackCentiC = 50;
    static constexpr uint32_t quietS = 3600, warmupS = 3600, requestNeededS = 3600;
    static constexpr uint8_t ceilingC = 80, thermostatHeatFromC = 20; // ShadowComparison::tadoHeatFromC
    static constexpr uint32_t maxCreditMs = 30000;
    static constexpr uint64_t boilerFreshMs = 300000, limitGraceMs = 900000;
    static constexpr uint64_t saveEveryMs = 6 * 3600000ull; // and at a day change and before a planned restart
    static constexpr size_t windowDays = 7, maxRooms = 8;   // RoomPlan::maxRooms
    static constexpr int32_t unknownDay = -1;
    static constexpr uint8_t thermostatSeen = 1, fallbackSeen = 2;

    struct Day {
        int32_t day = unknownDay; // local days since 1970-01-01; unknownDay until the clock is known
        uint32_t requestS = 0;    // E32 heat requested
        uint16_t thermostatPeriods = 0, e32Periods = 0, events = 0, matched = 0, close = 0, near = 0, over = 0;
        uint8_t setbacks = 0, warmups = 0, quiet = 0, flowMaxC = 0, flags = 0;
    };
    // The NVS record: a different version or size is not read.
    struct Stored {
        static constexpr uint16_t currentVersion = 1;
        uint16_t version = currentVersion, size = sizeof(Stored);
        uint32_t stableS = 0;
        std::array<Day, windowDays> days{}; // [0] today
    };
    struct Room { RoomDemand::Status status = RoomDemand::Status::inactive; std::optional<int16_t> setpoint; uint8_t sources = 0; };
    struct Inputs {
        std::optional<uint32_t> utc;        // nullopt while the clock is unknown
        FlowDemand::Request e32;
        std::optional<uint8_t> thermostatFlowC; // 0x1A, nullopt while unknown or stale
        uint8_t planMaximumC = ceilingC;
        std::optional<uint8_t> boilerLimitC;
        std::array<Room, maxRooms> rooms{};
        size_t roomCount = 0;
        bool active = false;                // the E32 controls the boiler: nothing to judge
        std::optional<uint64_t> boilerHeardAtMs;
        bool limitRead = false;             // the boiler limit known from the E32's own 0x16 read
    };

    // The restart before this boot: esp_reset_reason() and the reason the
    // previous boot recorded (BlackBox). Only a software restart without a
    // fault reason is planned (update, restart button, settings); a power cut
    // or brownout is power; a panic, watchdog or supervisor restart unexpected.
    static constexpr int resetPowerOn = 1, resetExternal = 2, resetSoftware = 3, resetBrownout = 9; // esp_reset_reason_t
    static Restart classify(int resetReason, diagnostics::SupervisorPolicy::Reason previous) {
        using R = diagnostics::SupervisorPolicy::Reason;
        if (resetReason == resetSoftware)
            return previous == R::none || previous == R::bluetoothApply || previous == R::settingsRestore || previous == R::setupReenter
                ? Restart::planned : Restart::unexpected;
        return resetReason == resetPowerOn || resetReason == resetExternal || resetReason == resetBrownout ? Restart::power : Restart::unexpected;
    }

    // At boot: the stored counters (nullptr: none), kept after any restart;
    // the stable time only after a planned one.
    void restore(const Stored* stored, Restart restart) {
        const bool valid = stored && stored->version == Stored::currentVersion && stored->size == sizeof(Stored);
        restart_ = valid ? restart : Restart::first;
        if (valid) days_ = stored->days;
        carriedS_ = valid && restart == Restart::planned ? stored->stableS : 0;
        saveNow_ = valid && restart != Restart::planned; // the stored stable time no longer holds
    }
    Stored stored() const { Stored s; s.stableS = stableS(); s.days = days_; return s; }
    // A stored record with a thermostat period in its window: the E32 heard another controller ask
    // the boiler for heat before (rc.3: the boiler test's record keeps that fact from then on).
    static bool thermostatSeenIn(const Stored& s) {
        if (s.version != Stored::currentVersion || s.size != sizeof(Stored)) return false;
        for (const auto& d : s.days) if (d.flags & thermostatSeen) return true;
        return false;
    }
    bool saveDue(uint64_t nowMs) const { return saveNow_ || nowMs - savedAtMs_ >= saveEveryMs; }
    void saved(uint64_t nowMs) { saveNow_ = false; savedAtMs_ = nowMs; }
    // rc.4 (R1-04): a plan edit moves the rooms' last known targets with them (new index -> old
    // index, -1: a new room), so a reorder is no setback or rise of its own.
    void remap(const std::array<int8_t, maxRooms>& from) {
        std::array<std::optional<int16_t>, maxRooms> moved{};
        for (size_t i = 0; i < maxRooms; ++i) if (from[i] >= 0 && size_t(from[i]) < maxRooms) moved[i] = setpoints_[from[i]];
        setpoints_ = moved;
    }

    void sample(uint64_t nowMs, const Inputs& in) {
        carryMs_ += static_cast<uint32_t>(haveLast_ && nowMs > lastMs_ ? std::min<uint64_t>(nowMs - lastMs_, maxCreditMs) : 0);
        const uint32_t dt = carryMs_ / 1000;
        carryMs_ %= 1000; lastMs_ = nowMs; haveLast_ = true;
        view_ = in; // the live part of the verdict: rooms, boiler, mode
        if (in.active) return; // frozen while the E32 controls the boiler
        if (in.utc) {
            const int32_t day = RoomSchedule::localDay(*in.utc);
            if (days_[0].day == unknownDay) days_[0].day = day; // boot time joins the first known day
            else if (day > days_[0].day) roll(day);             // an earlier day (clock step back) stays today
        }
        Day& d = days_[0];
        // Interval before this sample, by the previous states: E32 heat while the thermostat rests.
        if (thermostat_.known && !thermostat_.on && e32_.on) quietE32S_ += dt;
        if (in.e32.heat) {
            d.requestS += dt;
            d.flowMaxC = std::max(d.flowMaxC, in.e32.flowC);
            if (in.e32.flowC > limitC(in)) { if (!over_) inc(d.over); over_ = true; } else over_ = false;
        } else over_ = false;
        rooms(nowMs, in);
        edges(e32_, in.e32.heat, nowMs, [&](bool start, uint64_t t) {
            if (start) inc(d.e32Periods);
            e32Event(start ? 0 : 1, t);
        });
        if (in.thermostatFlowC) {
            d.flags |= thermostatSeen;
            const bool heat = *in.thermostatFlowC >= thermostatHeatFromC;
            edges(thermostat_, heat, nowMs, [&](bool start, uint64_t t) { start ? thermostatStart(t) : thermostatStop(t); });
            if (thermostat_.on) quietE32S_ = 0;
        }
        expire(nowMs);
    }

    // Seconds without an unexpected restart: before this boot (planned restarts) and since.
    uint32_t stableS() const { return carriedS_ + static_cast<uint32_t>(lastMs_ / 1000); }
    Restart restart() const { return restart_; }
    const Day& day(size_t i) const { return days_[i]; } // 0: today

    struct Totals {
        uint32_t requestS = 0;
        uint16_t thermostatPeriods = 0, e32Periods = 0, events = 0, matched = 0, close = 0, near = 0, over = 0;
        uint16_t setbacks = 0, warmups = 0, quiet = 0;
        uint8_t flowMaxC = 0, flags = 0;
    };
    Totals totals() const {
        Totals t;
        const auto add = [](uint16_t& sum, uint16_t v) { sum = uint16_t(std::min<uint32_t>(0xFFFF, uint32_t(sum) + v)); };
        for (const auto& d : days_) {
            t.requestS += d.requestS;
            add(t.thermostatPeriods, d.thermostatPeriods); add(t.e32Periods, d.e32Periods); add(t.events, d.events);
            add(t.matched, d.matched); add(t.close, d.close); add(t.near, d.near); add(t.over, d.over);
            add(t.setbacks, d.setbacks); add(t.warmups, d.warmups); add(t.quiet, d.quiet);
            t.flowMaxC = std::max(t.flowMaxC, d.flowMaxC); t.flags |= d.flags;
        }
        return t;
    }

    Result stable() const { return stableS() >= stableNeededS ? Result::pass : Result::wait; }
    Result periods(const Totals& t) const {
        return t.thermostatPeriods >= periodsNeeded && t.setbacks && t.warmups && t.quiet ? Result::pass : Result::wait;
    }
    // shadow_exit.py: matched >= 80 %, median <= 5 min, 90th percentile <= 15 min, as counts.
    Result timing(const Totals& t) const {
        if (t.events < eventsNeeded) return Result::wait;
        const bool ok = t.matched && uint32_t(t.matched) * 10 >= uint32_t(t.events) * 8
            && uint32_t(t.close) * 2 >= t.matched && uint32_t(t.near) * 10 >= uint32_t(t.matched) * 9;
        return ok ? Result::pass : Result::fail;
    }
    Result flow(const Totals& t) const { return t.over ? Result::fail : t.requestS < requestNeededS ? Result::wait : Result::pass; }
    Result cycling(const Totals& t) const {
        if (t.thermostatPeriods < periodsNeeded) return Result::wait;
        return t.e32Periods <= t.thermostatPeriods ? Result::pass : Result::fail;
    }
    struct Sources { uint8_t rooms = 0, working = 0, backup = 0; };
    Sources sources() const {
        Sources s;
        for (size_t i = 0; i < view_.roomCount && i < maxRooms; ++i) {
            const auto& r = view_.rooms[i];
            if (r.status == RoomDemand::Status::inactive) continue;
            ++s.rooms;
            if (r.status == RoomDemand::Status::ok || r.status == RoomDemand::Status::fallback) ++s.working;
            if (r.sources >= 2) ++s.backup;
        }
        return s;
    }
    // No room, or one without a fresh reading: fail. A fallback that never can
    // take over (no room with a second source) fails too; otherwise wait for it.
    Result sources(const Totals& t) const {
        const auto s = sources();
        if (!s.rooms || s.working < s.rooms) return Result::fail;
        if (t.flags & fallbackSeen) return Result::pass;
        return s.backup ? Result::wait : Result::fail;
    }
    Result boiler() const {
        if (view_.boilerHeardAtMs && *view_.boilerHeardAtMs <= lastMs_ && lastMs_ - *view_.boilerHeardAtMs <= boilerFreshMs) return Result::pass;
        return lastMs_ < boilerFreshMs ? Result::wait : Result::fail;
    }
    Result boilerLimit() const { return view_.limitRead ? Result::pass : lastMs_ < limitGraceMs ? Result::wait : Result::fail; }

    // ready only when every criterion of the list passes; not_ready with any
    // failure; not_applicable once the E32 controls the boiler.
    const char* state() const {
        if (view_.active) return "not_applicable";
        const auto t = totals();
        bool wait = false, fail = false;
        const auto judge = [&](Result r) { wait |= r == Result::wait; fail |= r == Result::fail; };
        judge(stable()); judge(sources(t));
        if (t.flags & thermostatSeen) { judge(periods(t)); judge(timing(t)); judge(flow(t)); judge(cycling(t)); }
        else { judge(boiler()); judge(boilerLimit()); }
        return fail ? "not_ready" : wait ? "waiting" : "ready";
    }

    // {"state","comparison", then per criterion {"result", its figures}}; only
    // {"state":"not_applicable"} in active mode. At most ~560 bytes.
    cJSON* json() const {
        cJSON* root = cJSON_CreateObject();
        if (!root || !cJSON_AddStringToObject(root, "state", state())) { cJSON_Delete(root); return nullptr; }
        if (view_.active) return root;
        const auto t = totals();
        const bool compare = t.flags & thermostatSeen;
        bool ok = cJSON_AddBoolToObject(root, "comparison", compare) != nullptr;
        const auto item = [&](const char* key, Result r) {
            cJSON* o = ok ? cJSON_AddObjectToObject(root, key) : nullptr;
            ok = o && cJSON_AddStringToObject(o, "result", name(r));
            return ok ? o : nullptr;
        };
        const auto num = [&](cJSON* o, const char* key, double v) { ok = ok && o && cJSON_AddNumberToObject(o, key, v); };
        if (cJSON* o = item("stable", stable())) {
            num(o, "s", stableS());
            ok = ok && cJSON_AddStringToObject(o, "restart", restartName(restart_));
        }
        if (compare) {
            if (cJSON* o = item("periods", periods(t))) {
                num(o, "thermostat", t.thermostatPeriods); num(o, "night_setbacks", t.setbacks);
                num(o, "morning_warmups", t.warmups); num(o, "no_demand", t.quiet);
            }
            if (cJSON* o = item("timing", timing(t))) {
                num(o, "events", t.events); num(o, "matched", t.matched); num(o, "within_5min", t.close); num(o, "within_15min", t.near);
            }
            if (cJSON* o = item("flow", flow(t))) {
                if (t.requestS) num(o, "max_c", t.flowMaxC); else ok = ok && cJSON_AddNullToObject(o, "max_c");
                num(o, "limit_c", limitC(view_)); num(o, "over", t.over); num(o, "request_s", t.requestS);
            }
            if (cJSON* o = item("cycling", cycling(t))) { num(o, "e32", t.e32Periods); num(o, "thermostat", t.thermostatPeriods); }
        }
        const auto s = sources();
        if (cJSON* o = item("sources", sources(t))) {
            num(o, "rooms", s.rooms); num(o, "working", s.working); num(o, "backup", s.backup);
            ok = ok && cJSON_AddBoolToObject(o, "fallback_seen", (t.flags & fallbackSeen) != 0);
        }
        if (!compare) {
            if (cJSON* o = item("boiler", boiler())) {
                if (view_.boilerHeardAtMs && *view_.boilerHeardAtMs <= lastMs_) num(o, "age_s", double((lastMs_ - *view_.boilerHeardAtMs) / 1000));
                else ok = ok && cJSON_AddNullToObject(o, "age_s");
            }
            if (cJSON* o = item("boiler_limit", boilerLimit())) {
                if (view_.limitRead && view_.boilerLimitC) num(o, "limit_c", *view_.boilerLimitC); else ok = ok && cJSON_AddNullToObject(o, "limit_c");
            }
        }
        if (!ok) { cJSON_Delete(root); return nullptr; }
        return root;
    }
    static const char* name(Result r) { return r == Result::pass ? "pass" : r == Result::fail ? "fail" : "wait"; }
    static const char* restartName(Restart r) {
        switch (r) {
            case Restart::planned: return "planned";
            case Restart::unexpected: return "unexpected";
            case Restart::power: return "power";
            default: return "first";
        }
    }

private:
    struct Side { bool known = false, on = false, stopping = false; uint64_t offAtMs = 0; };
    struct Pending { uint64_t atMs = 0; uint32_t beforeS = UINT32_MAX; }; // beforeS: since the E32's latest such event
    static constexpr size_t pendingMax = 4;

    static void inc(uint16_t& v) { if (v < 0xFFFF) ++v; }
    static void inc(uint8_t& v) { if (v < 0xFF) ++v; }
    static uint8_t limitC(const Inputs& in) {
        uint8_t limit = std::min(ceilingC, in.planMaximumC);
        if (in.boilerLimitC && *in.boilerLimitC > 0) limit = std::min(limit, *in.boilerLimitC);
        return limit;
    }
    // One side's heat at nowMs as merged periods: event(true, t) at a start,
    // event(false, t) at the stop once it stayed off mergeGapMs.
    template <class Event>
    static void edges(Side& s, bool heat, uint64_t nowMs, Event&& event) {
        if (!s.known) { s.known = true; s.on = heat; return; } // the first sample sets the state, no event
        if (s.stopping && nowMs - s.offAtMs >= mergeGapMs) { s.stopping = false; event(false, s.offAtMs); }
        if (heat && !s.on) { s.on = true; if (s.stopping) s.stopping = false; else event(true, nowMs); }
        else if (!heat && s.on) { s.on = false; s.stopping = true; s.offAtMs = nowMs; }
    }
    // A room's target falling 0.5 degC from 18:00 to 03:00 is a night setback;
    // rising from 04:00 to 10:00 a morning rise, a warm-up once the thermostat
    // starts within the hour. A room on a fallback source shows it works.
    void rooms(uint64_t nowMs, const Inputs& in) {
        Day& d = days_[0];
        const int hour = in.utc ? RoomSchedule::localAt(*in.utc).minute / 60 : -1;
        for (size_t i = 0; i < maxRooms; ++i) {
            const Room* r = i < in.roomCount ? &in.rooms[i] : nullptr;
            const bool active = r && r->status != RoomDemand::Status::inactive;
            if (active && r->status == RoomDemand::Status::fallback) d.flags |= fallbackSeen;
            const auto next = active ? r->setpoint : std::nullopt;
            if (next && setpoints_[i] && hour >= 0) {
                const int change = int(*next) - int(*setpoints_[i]);
                if (change <= -setbackCentiC && (hour >= 18 || hour < 3)) inc(d.setbacks);
                else if (change >= setbackCentiC && hour >= 4 && hour < 10) morningRiseMs_ = nowMs;
            }
            setpoints_[i] = next;
        }
    }
    void thermostatStart(uint64_t t) {
        Day& d = days_[0];
        inc(d.thermostatPeriods);
        if (lastStopMs_ && t - *lastStopMs_ >= uint64_t(quietS) * 1000 && uint64_t(quietE32S_) * 10000 <= t - *lastStopMs_) inc(d.quiet);
        if (morningRiseMs_ && t >= *morningRiseMs_ && t - *morningRiseMs_ <= uint64_t(warmupS) * 1000) { inc(d.warmups); morningRiseMs_.reset(); }
        thermostatEvent(0, t);
    }
    void thermostatStop(uint64_t t) { lastStopMs_ = t; thermostatEvent(1, t); }
    // Each thermostat start (kind 0) or stop (1) against the E32's nearest of
    // the same kind, before or after it, within matchS.
    void thermostatEvent(int kind, uint64_t t) {
        const uint32_t before = lastE32_[kind] && *lastE32_[kind] <= t ? uint32_t((t - *lastE32_[kind]) / 1000) : UINT32_MAX;
        if (before == 0) { resolve(0); return; } // nothing comes closer
        auto& list = pending_[kind];
        auto& n = pendingCount_[kind];
        if (n == pendingMax) { resolve(list[0].beforeS); std::copy(list.begin() + 1, list.end(), list.begin()); --n; }
        list[n++] = {t, before};
    }
    void e32Event(int kind, uint64_t t) {
        for (size_t i = 0; i < pendingCount_[kind]; ++i) {
            const auto& p = pending_[kind][i];
            const uint32_t after = uint32_t((t >= p.atMs ? t - p.atMs : p.atMs - t) / 1000);
            resolve(std::min(p.beforeS, after));
        }
        pendingCount_[kind] = 0;
        lastE32_[kind] = t;
    }
    void expire(uint64_t nowMs) {
        for (int kind = 0; kind < 2; ++kind) {
            auto& list = pending_[kind];
            auto& n = pendingCount_[kind];
            while (n && nowMs - list[0].atMs > uint64_t(matchS) * 1000) {
                resolve(list[0].beforeS);
                std::copy(list.begin() + 1, list.end(), list.begin()); --n;
            }
        }
    }
    void resolve(uint32_t s) {
        Day& d = days_[0];
        inc(d.events);
        if (s > matchS) return;
        inc(d.matched);
        if (s <= nearS) inc(d.near);
        if (s <= closeS) inc(d.close);
    }
    // A new local day; days the E32 was off stay empty, older ones leave the window.
    void roll(int32_t day) {
        const size_t shift = size_t(std::min<int64_t>(int64_t(day) - days_[0].day, int64_t(windowDays)));
        std::copy_backward(days_.begin(), days_.end() - shift, days_.end());
        std::fill(days_.begin(), days_.begin() + shift, Day{});
        days_[0].day = day;
        saveNow_ = true;
    }

    std::array<Day, windowDays> days_{};
    Inputs view_{};
    Restart restart_ = Restart::first;
    uint32_t carriedS_ = 0, carryMs_ = 0, quietE32S_ = 0;
    uint64_t lastMs_ = 0, savedAtMs_ = 0;
    bool haveLast_ = false, over_ = false, saveNow_ = false;
    Side e32_, thermostat_;
    std::array<std::optional<int16_t>, maxRooms> setpoints_{};
    std::optional<uint64_t> morningRiseMs_, lastStopMs_;
    std::array<std::optional<uint64_t>, 2> lastE32_{};
    std::array<std::array<Pending, pendingMax>, 2> pending_{};
    std::array<uint8_t, 2> pendingCount_{};
};
}
