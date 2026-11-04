#pragma once
#include <cstdint>
#include <optional>

namespace heating::control {
// ha/heating_input on a live broker session (P22). Home Assistant sends each value on every change and
// every five minutes, so a quarter of an hour without any message while the plan reads Home Assistant
// entities means nothing arrives. The E32 then subscribes to the topic again (a broker that lost the
// subscription gets it back; one that has it replaces it, MQTT 3.1.1 3.8.4), and again every silenceMs
// while the silence lasts. The status reports when it last did (ha.resubscribed_s), so Home Assistant
// and the E32 page can tell "nothing arrives" (and the E32 already tried) from "arrives but refused"
// (ha.last_rejected). The 15-minute fallback of the rooms is unchanged. Pure; ModernTransport owns one
// per broker session and decides only when to call the predicate (once per silenceMs at most).
class HaInputSilence {
public:
    static constexpr uint64_t silenceMs = 900000;
    // A new broker session (its subscriptions are fresh): the silence counts from now.
    void connected(uint64_t now) { since_ = now; }
    // Any ha/heating_input message, accepted or not: the subscription works.
    void received(uint64_t now) { if (now > since_) since_ = now; }
    // True when silenceMs passed since the session started, the last message or the last resubscription,
    // and expected() (the plan reads Home Assistant entities); without that it looks again after silenceMs.
    template <class Expected>
    bool due(uint64_t now, Expected&& expected) {
        if (now < since_ || now - since_ < silenceMs) return false;
        if (!expected()) { since_ = now; return false; }
        return true;
    }
    void resubscribed(uint64_t now) { since_ = now; last_ = now; ++count_; }
    // Uptime ms of the last resubscription; nullopt: none this boot.
    std::optional<uint64_t> lastResubscribeMs() const { return last_; }
    uint32_t count() const { return count_; }

private:
    uint64_t since_ = 0;
    std::optional<uint64_t> last_;
    uint32_t count_ = 0;
};
}
