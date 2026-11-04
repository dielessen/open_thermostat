#pragma once
#include "control/RoomPlan.h"
#include "control/RoomSchedule.h"
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
namespace heating::control {
// The lead factor the planner multiplies into a room's warm-up lead (WarmupPlanner::lead):
// the arrival-time feedback of rc.4 (L2). `trusted` once enough mornings were seen: an
// untrusted estimate is capped by the planner.
struct LeadFactor { float factor = 1; bool trusted = false; };

// Feedback on the arrival time (rc.4, L2; owner: "op die tijd wil ik het warm hebben"). Each
// program rise whose planned start found the room below its coming target is one event once
// the switch time has passed: the room arrived (within 0.1 degC of the target) early, on time
// or late. Late by more than 10 min: the factor grows 10 %; early by more than 15 min: it
// shrinks 8 %; within 0.5..2.0 (a default lead twice too long or too short is within 15 min
// after eight mornings). A room that never arrives within 3 h after the switch counts as
// late. Only a start the policy applied teaches (advice cannot be judged). The factor acts
// on the default lead as on the learned one, so the first mornings already converge while
// the models are still learning, and a biased model is corrected. Keyed by room id (a plan
// edit keeps it); LearnedState keeps it over restarts. Pure: observe() once a minute per room.
class ArrivalLearner {
public:
    struct Params {
        float late = 1.10f, early = 0.92f, minFactor = 0.5f, maxFactor = 2.0f;
        int32_t lateS = 600, earlyS = 900, windowS = 3 * 3600;
        int16_t marginCentiC = 10;  // arrived: within this of the target
        uint8_t trustedEvents = 3;  // from here the factor is trusted (no estimate cap)
    };
    // The rise the planner watches: its switch time, the planned start and the coming target.
    struct Rise { int64_t atUtc = 0, startUtc = 0; int16_t toCentiC = 0; };
    // A judged morning (for the scoreboard): the room, the switch time and the error in minutes.
    struct Event { uint8_t room = 0; int64_t atUtc = 0; int16_t errorMin = 0; };
    static constexpr size_t eventQueue = 8;

    ArrivalLearner() = default;
    explicit ArrivalLearner(Params p) : p_(p) {}

    // An edit keeps each room's factor by id; the rise being watched restarts.
    void setPlan(const RoomPlan& plan) {
        std::vector<Room> next(plan.rooms.size());
        for (size_t i = 0; i < plan.rooms.size(); ++i) {
            auto old = std::find_if(rooms_.begin(), rooms_.end(), [&](const Room& r) { return r.id == plan.rooms[i].id; });
            if (old != rooms_.end()) next[i] = std::move(*old);
            else next[i].id = plan.rooms[i].id;
            next[i].open = false;
        }
        rooms_ = std::move(next);
    }
    // Once a minute per room: the next rise (nullopt: none within 24 h), whether the policy
    // heats this room ahead of it right now, and the room's fresh reading (nullopt: none).
    // From the switch on the planner already reports the next rise: the watched one stays
    // until the room arrives or the window ends. Another rise (or none) before the switch
    // means the program changed: the watched rise is dropped unjudged.
    void observe(size_t room, int64_t utc, std::optional<Rise> rise, bool applied, std::optional<int16_t> temperature) {
        if (room >= rooms_.size()) return;
        auto& r = rooms_[room];
        const bool same = rise && r.open && rise->atUtc == r.rise.atUtc;
        if (r.open && !same && utc < r.rise.atUtc) r.open = false;
        if (!r.open) {
            if (!rise || utc >= rise->atUtc) return; // nothing to watch, or too late to watch this one
            r.started = r.applied = r.shortfall = r.seen = false; r.arrivedUtc = 0;
            r.open = true; r.rise = *rise;
        } else if (same) {
            r.rise = *rise; // the planned start moves while the room cools
        }
        if (applied && utc < r.rise.atUtc) r.applied = true;
        if (!r.started && utc >= r.rise.startUtc && temperature) {
            r.started = true;
            r.shortfall = *temperature < r.rise.toCentiC - p_.marginCentiC;
        }
        if (r.started && !r.arrivedUtc && temperature && *temperature >= r.rise.toCentiC - p_.marginCentiC) r.arrivedUtc = utc;
        if (utc >= r.rise.atUtc && temperature) r.seen = true;
        if (utc >= r.rise.atUtc && (r.arrivedUtc || utc >= r.rise.atUtc + p_.windowS)) resolve(r);
    }
    LeadFactor lead(size_t room) const {
        if (room >= rooms_.size()) return {};
        return {rooms_[room].factor, rooms_[room].events >= p_.trustedEvents};
    }
    size_t rooms() const { return rooms_.size(); }
    uint16_t events(size_t room) const { return room < rooms_.size() ? rooms_[room].events : 0; }
    std::optional<int16_t> lastErrorMin(size_t room) const {
        return room < rooms_.size() && rooms_[room].hasLast ? std::optional<int16_t>(rooms_[room].lastErrorMin) : std::nullopt;
    }
    const Params& params() const { return p_; }
    // The judged mornings since the last pop, oldest first (the newest are kept when the queue is full).
    bool pop(Event& out) {
        if (!eventCount_) return false;
        out = events_[0];
        for (size_t i = 1; i < eventCount_; ++i) events_[i - 1] = events_[i];
        --eventCount_;
        return true;
    }
    // {"factor":1.1,"events":3,"last_error_min":12,"last_at_utc":..} or null while no morning was judged.
    cJSON* json(size_t room) const {
        if (room >= rooms_.size() || !rooms_[room].events) return cJSON_CreateNull();
        const auto& r = rooms_[room];
        cJSON* o = cJSON_CreateObject();
        if (!o) return nullptr;
        cJSON_AddNumberToObject(o, "factor", std::floor(double(r.factor) * 100 + 0.5) / 100);
        cJSON_AddNumberToObject(o, "events", r.events);
        if (r.hasLast) { cJSON_AddNumberToObject(o, "last_error_min", r.lastErrorMin); cJSON_AddNumberToObject(o, "last_at_utc", double(r.lastAtUtc)); }
        else { cJSON_AddNullToObject(o, "last_error_min"); cJSON_AddNullToObject(o, "last_at_utc"); }
        return o;
    }

private:
    friend class LearnedState;
    struct Room {
        std::string id;
        float factor = 1;
        uint16_t events = 0;
        int16_t lastErrorMin = 0;
        bool hasLast = false;
        int64_t lastAtUtc = 0;
        // The rise being watched; seen: a reading came since its switch.
        bool open = false, started = false, applied = false, shortfall = false, seen = false;
        Rise rise;
        int64_t arrivedUtc = 0;
    };
    void resolve(Room& r) {
        r.open = false;
        if (!r.started || !r.shortfall || !r.applied) return; // nothing to warm up, or advice only: no lesson
        if (!r.arrivedUtc && !r.seen) return;                  // no reading since the switch: unknown, no lesson
        const int64_t error = (r.arrivedUtc ? r.arrivedUtc : r.rise.atUtc + p_.windowS) - r.rise.atUtc;
        if (error > p_.lateS) r.factor = std::min(p_.maxFactor, r.factor * p_.late);
        else if (error < -p_.earlyS) r.factor = std::max(p_.minFactor, r.factor * p_.early);
        if (r.events != UINT16_MAX) ++r.events;
        r.lastErrorMin = int16_t(std::clamp<int64_t>(error / 60, -32000, 32000));
        r.hasLast = true; r.lastAtUtc = r.rise.atUtc;
        if (eventCount_ == eventQueue) { for (size_t i = 1; i < eventQueue; ++i) events_[i - 1] = events_[i]; --eventCount_; }
        events_[eventCount_++] = {uint8_t(&r - rooms_.data()), r.rise.atUtc, r.lastErrorMin};
    }
    Params p_;
    std::vector<Room> rooms_;
    std::array<Event, eventQueue> events_{};
    size_t eventCount_ = 0;
};
}
