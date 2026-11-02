#pragma once
#include <algorithm>
#include <cJSON.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <optional>
#include <string>
#include <string_view>
namespace heating::control {
// The guided "Boiler test and takeover" (owner, 2 Nov 2026): a new plan starts
// active, and this test is the recommended path to the takeover instead of a
// trial run. The attended switch-over tests of docs/SWITCHOVER.md, judged by
// the E32 from boiler telemetry, one step after the other:
//   disconnect  the old thermostat is unplugged: no foreign 0x1A for 2 min
//               while boiler messages arrive (or already taken over)
//   confirm     the owner's existing takeover confirmation; passes once the
//               guard owns the boiler
//   start       target about 1 degC above the room (a temporary override with
//               an end time): burner on for heating within 10 min, flow +3 degC
//               within 15 min
//   hot_water   a hot tap for 3 min: hot water seen, heating back within 5 min
//               after it ends, no warning (skippable: no hot water from the boiler)
//   stop        target 0.5 degC below the room: once the zero was delivered the
//               burner is off within 45 s and does not restart within 5 min
// Then the override ends and the program continues. The abort rules of
// SWITCHOVER.md the E32 can see stop the test with a reason (the page then
// says "stop and give control back"): another thermostat, a hand-back,
// measurements lost, a guard warning, the flow above the ceiling while
// heating, the boiler silent for 3 minutes.
// Each step has a timeout. The result (start time, a mark per step, the end
// and its reason) is kept as one short NVS string (record()/restore()).
// Pure and single-threaded: step() every 10 s; the caller applies target().
class TakeoverTest {
public:
    enum class Step : uint8_t { disconnect, confirm, start, hotWater, stop, done };
    static constexpr size_t steps = 5; // done is not judged
    enum class Mark : char { none = 'n', pass = 'p', fail = 'f', skipped = 's', aborted = 'a' };
    // idle: never ran; stopped: an abort rule; aborted: the owner stopped it.
    enum class State : char { idle = 'i', running = 'r', passed = 'p', failed = 'f', stopped = 's', aborted = 'a' };
    struct Params {
        uint64_t quietMs = 120000, busGapMs = 30000, waitMs = 1800000;  // disconnect, confirm
        uint64_t burnerMs = 600000, riseMs = 900000;                     // start
        int16_t riseCentiC = 300;
        uint64_t tapMs = 900000, resumeMs = 300000;                      // hot water
        uint64_t zeroMs = 1800000, offMs = 45000, restartMs = 300000;    // stop
        uint64_t silentMs = 180000;                                      // abort: boiler silent
        int16_t marginCentiC = 500;                                      // abort: flow above the ceiling
        uint16_t overrideMinutes = 60;
    };
    struct Inputs {
        std::optional<uint64_t> foreignAtMs;     // the last 0x1A to the boiler from another master
        std::optional<uint64_t> boilerHeardAtMs; // the last boiler report
        bool confirmed = false, owning = false, blocked = false;
        bool released = true;                    // no positive request held: the zero was delivered
        const char* warning = nullptr;           // a guard warning that ends the test (nullptr: none)
        std::optional<bool> burnerOn, hotWater;
        std::optional<int16_t> flowCentiC, roomCentiC; // the boiler's flow; the test room's fresh reading
        uint8_t ceilingC = 80;                   // min(plan maximum, boiler limit)
        int16_t roomMinCentiC = 500, roomMaxCentiC = 2500;
    };

    TakeoverTest() = default;
    explicit TakeoverTest(Params p) : p_(p) {}

    // Starts (again) from the first step for this room; utc 0 = clock unknown.
    void start(uint64_t now, std::string room, uint32_t utc) {
        room_ = std::move(room); at_ = utc; state_ = State::running; reason_.clear();
        std::fill(marks_, marks_ + steps, Mark::none);
        enter(Step::disconnect, now);
        setTarget(std::nullopt);
    }
    // The owner stops the test: the override ends, nothing else changes.
    void abort(uint64_t now) { if (running()) finish(State::aborted, Mark::aborted, "owner", now); }
    // The caller ends it by an abort rule of its own (the plan left active mode, the override was refused).
    void interrupt(const char* why, uint64_t now) { if (running()) stop(why, now); }
    // A boiler without hot water skips that step; false in any other step.
    bool skip(uint64_t now) {
        if (!running() || step_ != Step::hotWater) return false;
        mark(Mark::skipped); next(now);
        return true;
    }

    void step(uint64_t now, const Inputs& in) {
        if (!running()) return;
        const uint64_t t = now - since_;
        const bool heating = in.burnerOn.value_or(false) && !in.hotWater.value_or(false);
        // The abort rules once the E32 owns the boiler.
        if (step_ > Step::confirm) {
            if (in.blocked) return stop("foreign_controller", now);
            if (!in.confirmed) return stop("handed_back", now);
            if (in.warning) return stop(in.warning, now);
            if (!in.boilerHeardAtMs || now - *in.boilerHeardAtMs > p_.silentMs) return stop("boiler_silent", now);
            const bool over = heating && in.flowCentiC && *in.flowCentiC > in.ceilingC * 100 + p_.marginCentiC;
            if (over && overSeen_) return stop("flow_above_limit", now);
            overSeen_ = over;
        }
        switch (step_) {
            case Step::disconnect: {
                const bool heard = in.boilerHeardAtMs && now - *in.boilerHeardAtMs <= p_.busGapMs;
                const uint64_t from = in.foreignAtMs ? std::max(since_, *in.foreignAtMs) : since_;
                quietS_ = uint32_t((now - std::min(now, from)) / 1000);
                phase_ = !heard ? "boiler_silent" : in.foreignAtMs && now - *in.foreignAtMs < p_.quietMs ? "thermostat_heard" : "listening";
                if ((in.confirmed && in.owning && !in.blocked) || (heard && now - std::min(now, from) >= p_.quietMs)) return pass(now);
                if (t >= p_.waitMs) return fail(in.foreignAtMs && now - *in.foreignAtMs < p_.quietMs ? "thermostat_heard" : "boiler_silent", now);
                return;
            }
            case Step::confirm:
                phase_ = in.confirmed ? "taking_over" : "waiting_confirmation";
                if (in.confirmed && in.owning) return pass(now);
                if (in.blocked) return fail("foreign_controller", now);
                if (t >= p_.waitMs) return fail(in.confirmed ? "no_takeover" : "not_confirmed", now);
                return;
            case Step::start:
                if (!aimed_ && !aim(in, 100, now)) return;
                if (heating && !burnerAt_) burnerAt_ = now;
                if (in.flowCentiC && !in.hotWater.value_or(false)) {
                    lowFlow_ = lowFlow_ ? std::min(*lowFlow_, *in.flowCentiC) : *in.flowCentiC;
                    riseCentiC_ = std::max<int16_t>(riseCentiC_, int16_t(*in.flowCentiC - *lowFlow_));
                }
                phase_ = !burnerAt_ ? "waiting_burner" : "waiting_flow_rise";
                if (burnerAt_ && riseCentiC_ >= p_.riseCentiC) return pass(now);
                if (!burnerAt_ && t >= p_.burnerMs) return fail("no_burner", now);
                if (t >= p_.riseMs) return fail("no_flow_rise", now);
                return;
            case Step::hotWater:
                if (!aimed_ && !aim(in, 100, now)) return;
                if (in.hotWater.value_or(false)) { tapSeen_ = true; tapEnd_.reset(); phase_ = "tap_open"; return; }
                if (!tapSeen_) {
                    phase_ = "waiting_tap";
                    if (t >= p_.tapMs) fail("no_hot_water", now);
                    return;
                }
                if (!tapEnd_) tapEnd_ = now;
                phase_ = "waiting_heating";
                if (heating) return pass(now);
                if (now - *tapEnd_ >= p_.resumeMs) fail("heating_not_resumed", now);
                return;
            case Step::stop:
                if (!aimed_ && !aim(in, -50, now)) return;
                if (!zeroAt_) {
                    phase_ = "waiting_zero";
                    if (in.released) zeroAt_ = now;
                    else { if (t >= p_.zeroMs) fail("no_stop_request", now); return; }
                }
                if (!offAt_) {
                    phase_ = "waiting_burner_off";
                    if (!heating) offAt_ = now;
                    else { if (now - *zeroAt_ > p_.offMs) fail("burner_still_on", now); return; }
                }
                phase_ = "watching_restart";
                if (heating) return fail("restarted", now);
                if (now - *offAt_ >= p_.restartMs) pass(now);
                return;
            default: return;
        }
    }

    bool running() const { return state_ == State::running; }
    State state() const { return state_; }
    Step current() const { return step_; }
    Mark mark(Step s) const { return s < Step::done ? marks_[size_t(s)] : Mark::none; }
    const std::string& room() const { return room_; }
    const std::string& reason() const { return reason_; }
    // The test room's temporary target (nullopt: none, the program applies), and whether it
    // changed since the caller last took it.
    std::optional<int16_t> target() const { return target_; }
    bool takeTargetChange() { const bool c = targetChanged_; targetChanged_ = false; return c; }
    uint16_t overrideMinutes() const { return p_.overrideMinutes; }

    // The kept result: "<utc> <marks> <state> <reason>", at most 48 characters.
    std::string record() const {
        if (state_ == State::idle || running()) return {};
        char text[64];
        std::snprintf(text, sizeof(text), "%lu %.*s %c %.24s", (unsigned long)at_, int(steps), (const char*)marks_, char(state_),
                      reason_.empty() ? "-" : reason_.c_str());
        return text;
    }
    // At boot: a record of record(); anything else leaves the test idle.
    bool restore(std::string_view text) {
        unsigned long at = 0; char marks[steps + 1] = {}, state = 0, reason[25] = {};
        const std::string copy(text.substr(0, 63));
        if (std::sscanf(copy.c_str(), "%lu %5s %c %24s", &at, marks, &state, reason) != 4 || std::strlen(marks) != steps) return false;
        for (const char m : marks) if (m && !std::strchr("npfsa", m)) return false;
        if (!std::strchr("pfsa", state)) return false;
        at_ = uint32_t(at); state_ = State(state); reason_ = std::strcmp(reason, "-") ? reason : "";
        std::copy(marks, marks + steps, (char*)marks_);
        return true;
    }

    static const char* name(Step s) {
        static constexpr const char* names[] = {"disconnect", "confirm", "start", "hot_water", "stop", "done"};
        return names[size_t(s)];
    }
    static const char* name(Mark m) {
        switch (m) {
            case Mark::pass: return "pass";
            case Mark::fail: return "fail";
            case Mark::skipped: return "skipped";
            case Mark::aborted: return "aborted";
            default: return "not_run";
        }
    }
    static const char* name(State s) {
        switch (s) {
            case State::running: return "running";
            case State::passed: return "passed";
            case State::failed: return "failed";
            case State::stopped: return "stopped";
            case State::aborted: return "aborted";
            default: return "idle";
        }
    }
    // {"state","at","steps":{name: result},"reason"[,"step","phase","step_s","room","target_c","quiet_s","rise_c"]}
    cJSON* json(uint64_t now) const {
        cJSON* root = cJSON_CreateObject();
        if (!root) return nullptr;
        bool ok = cJSON_AddStringToObject(root, "state", name(state_)) != nullptr;
        ok = ok && (at_ ? cJSON_AddNumberToObject(root, "at", at_) : cJSON_AddNullToObject(root, "at"));
        cJSON* list = ok ? cJSON_AddObjectToObject(root, "steps") : nullptr;
        for (size_t i = 0; list && i < steps; ++i)
            ok = ok && cJSON_AddStringToObject(list, name(Step(i)), running() && Step(i) == step_ ? "wait" : name(marks_[i]));
        ok = ok && list && (reason_.empty() ? cJSON_AddNullToObject(root, "reason") : cJSON_AddStringToObject(root, "reason", reason_.c_str()));
        if (ok && running()) {
            ok = cJSON_AddStringToObject(root, "step", name(step_)) && cJSON_AddStringToObject(root, "phase", phase_)
                && cJSON_AddNumberToObject(root, "step_s", double((now - std::min(now, since_)) / 1000))
                && cJSON_AddStringToObject(root, "room", room_.c_str())
                && (target_ ? cJSON_AddNumberToObject(root, "target_c", *target_ / 100.0) : cJSON_AddNullToObject(root, "target_c"));
            if (ok && step_ == Step::disconnect) ok = cJSON_AddNumberToObject(root, "quiet_s", quietS_) != nullptr;
            if (ok && step_ == Step::start) ok = cJSON_AddNumberToObject(root, "rise_c", riseCentiC_ / 100.0) != nullptr;
        }
        if (!ok) { cJSON_Delete(root); return nullptr; }
        return root;
    }

private:
    void enter(Step s, uint64_t now) {
        static constexpr const char* first[] = {"listening", "waiting_confirmation", "waiting_burner", "waiting_tap", "waiting_zero", ""};
        step_ = s; since_ = now; phase_ = first[size_t(s)]; aimed_ = tapSeen_ = overSeen_ = false;
        burnerAt_.reset(); lowFlow_.reset(); tapEnd_.reset(); zeroAt_.reset(); offAt_.reset(); riseCentiC_ = 0; quietS_ = 0;
    }
    void mark(Mark m) { marks_[size_t(step_)] = m; }
    void next(uint64_t now) {
        enter(Step(uint8_t(step_) + 1), now);
        if (step_ == Step::done) finish(State::passed, Mark::none, "", now);
    }
    void pass(uint64_t now) { mark(Mark::pass); next(now); }
    void fail(const char* why, uint64_t now) { finish(State::failed, Mark::fail, why, now); }
    void stop(const char* why, uint64_t now) { finish(State::stopped, Mark::fail, why, now); }
    void finish(State s, Mark m, const char* why, uint64_t now) {
        if (step_ < Step::done && m != Mark::none) mark(m);
        state_ = s; reason_ = why; since_ = now;
        setTarget(std::nullopt);
    }
    void setTarget(std::optional<int16_t> t) { if (t != target_) { target_ = t; targetChanged_ = true; } }
    // The temporary target `offset` from the room's reading, rounded away from it to a tenth and within the
    // room's limits (start, hot water: at least the current one). False: the test failed.
    bool aim(const Inputs& in, int16_t offset, uint64_t now) {
        if (!in.roomCentiC) { fail("no_room_reading", now); return false; }
        const int raw = *in.roomCentiC + offset;
        int t = offset > 0 ? (raw + 9) / 10 * 10 : raw / 10 * 10;
        if (offset > 0 && target_) t = std::max(t, int(*target_));
        t = std::clamp(t, int(in.roomMinCentiC), int(in.roomMaxCentiC));
        if (offset > 0 ? t <= *in.roomCentiC : t >= *in.roomCentiC) { fail("room_limit", now); return false; }
        setTarget(int16_t(t)); aimed_ = true;
        return true;
    }

    Params p_;
    State state_ = State::idle;
    Step step_ = Step::disconnect;
    Mark marks_[steps] = {Mark::none, Mark::none, Mark::none, Mark::none, Mark::none};
    std::string room_, reason_;
    const char* phase_ = "";
    uint32_t at_ = 0, quietS_ = 0;
    uint64_t since_ = 0;
    std::optional<int16_t> target_, lowFlow_;
    int16_t riseCentiC_ = 0;
    std::optional<uint64_t> burnerAt_, tapEnd_, zeroAt_, offAt_;
    bool targetChanged_ = false, aimed_ = false, tapSeen_ = false, overSeen_ = false;
};
}
