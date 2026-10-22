#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace heating::control {

struct ScheduleTransition { int64_t atUtc; int16_t temperatureCentiC; };
enum class ScheduleState { not_configured, time_not_valid, not_started, active, expired };
struct ScheduleTarget {
    ScheduleState state;
    std::optional<int16_t> temperatureCentiC;
    std::optional<ScheduleTransition> next;
};

// The adapter materializes native HA's complete week + timezone into UTC. This
// class is the firmware's ONLY schedule evaluator, with no HA timer deciding heat.
class UtcSchedule {
public:
    static constexpr std::size_t maximumTransitions = 128;
    static constexpr int64_t maximumHorizonSeconds = 16 * 86400;
    static constexpr int64_t minimumUtcSecond = 946684800; // 2000-01-01
    static constexpr int64_t maximumUtcSecond = 4102444800; // exclusive 2100-01-01
    bool configure(int64_t from, int64_t until, int16_t baseCentiC,
                   const ScheduleTransition *transitions, std::size_t count) {
        if (!transitions || count == 0 || count > maximumTransitions ||
            from < minimumUtcSecond || until > maximumUtcSecond || until <= from || until - from > maximumHorizonSeconds ||
            !validTemperature(baseCentiC) || transitions[0].atUtc != from) return false;
        for (std::size_t i = 0; i < count; ++i) {
            if (!validTemperature(transitions[i].temperatureCentiC) || transitions[i].atUtc < from ||
                transitions[i].atUtc >= until || (i && transitions[i].atUtc <= transitions[i-1].atUtc)) return false;
        }
        // Only after the entire candidate is valid; invalid input leaves old config intact.
        for (std::size_t i = 0; i < count; ++i) transitions_[i] = transitions[i];
        count_ = count; from_ = from; until_ = until; baseCentiC_ = baseCentiC;
        return true;
    }
    ScheduleTarget target(int64_t utcNow, bool clockValidated) const {
        if (!count_) return {ScheduleState::not_configured, {}, {}};
        if (!clockValidated) return {ScheduleState::time_not_valid, {}, {}};
        if (utcNow < from_) return {ScheduleState::not_started, {}, transitions_[0]};
        if (utcNow >= until_) return {ScheduleState::expired, {}, {}};
        std::size_t i = 1;
        while (i < count_ && transitions_[i].atUtc <= utcNow) ++i;
        return {ScheduleState::active, transitions_[i-1].temperatureCentiC,
                i < count_ ? std::optional<ScheduleTransition>(transitions_[i]) : std::nullopt};
    }
    int16_t baseCentiC() const { return baseCentiC_; }
    static constexpr bool validTemperature(int value) { return value >= 500 && value <= 3500; }
private:
    std::array<ScheduleTransition, maximumTransitions> transitions_{};
    std::size_t count_ = 0;
    int64_t from_ = 0, until_ = 0;
    int16_t baseCentiC_ = 0;
};
}
