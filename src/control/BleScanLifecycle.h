#pragma once
#include <algorithm>
#include <atomic>
#include <cstdint>

namespace heating::control {
// One existing scanner, with callback-to-loop publication. No task or retry loop.
class BleScanLifecycle {
public:
    bool begin(uint32_t now, uint32_t intervalMs) {
        if (state_.load(std::memory_order_acquire) != State::idle) return false;
        // uint32 elapsed supports millis wrap; configured intervals fit below 2^31.
        if (finished_ && uint32_t(now - finishedAt_) < cooldownMs_) return false;
        // Single loop caller prepares metadata before publishing pending to
        // the asynchronous SDK callback.
        intervalMs_ = intervalMs;
        State expected = State::idle;
        if (!state_.compare_exchange_strong(expected, State::pending,
                std::memory_order_acq_rel)) return false;
        return true;
    }
    template<class Cleanup>
    bool complete(uint32_t now, Cleanup cleanup, bool startFailed = false) {
        State expected = State::pending;
        if (!state_.compare_exchange_strong(expected, State::cleaning,
                std::memory_order_acq_rel)) return false;
        // Results must be released BEFORE the main loop may start a new scan.
        // A stop/reentrant callback during cleanup must never reopen the scanner.
        try { cleanup(); }
        catch (...) { close(); return false; }
        finishedAt_ = now;
        cooldownMs_ = startFailed ? std::max<uint32_t>(1000, intervalMs_) : intervalMs_;
        finished_ = true;
        expected = State::cleaning;
        return state_.compare_exchange_strong(expected, State::idle,
            std::memory_order_release, std::memory_order_relaxed);
    }
    bool acceptsReports() const {
        return state_.load(std::memory_order_acquire) == State::pending;
    }
    bool pending() const {
        const auto state = state_.load(std::memory_order_acquire);
        return state == State::pending || state == State::cleaning;
    }
    void close() { state_.store(State::closed, std::memory_order_release); }
private:
    enum class State : uint8_t { idle, pending, cleaning, closed };
    std::atomic<State> state_{State::idle};
    // Only loop writes interval; only one admitted completion writes the rest.
    // Idle release/acquire publishes the completion to the next loop invocation.
    uint32_t intervalMs_ = 0, finishedAt_ = 0, cooldownMs_ = 0;
    bool finished_ = false;
};
}
