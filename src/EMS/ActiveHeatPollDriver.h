#pragma once
#include "BoilerTestSession.h"
#include "EmsFrameQueue.h"
#include <algorithm>
#include <cstdint>
#include <optional>

namespace heating::ems {
// Active heating's own envelope (owner, 28 Oct): at most 60 degC and never
// above the heating limit the boiler itself reported (Classic 0x16, the
// latest this boot: the setting only changes at the boiler).
struct ActiveHeatEnvelope {
    static constexpr uint8_t maximumFlowC = 60;
    static std::optional<uint8_t> limitC(const ClassicBoilerMonitor& monitor) {
        const auto& limit = monitor.sample(BoilerField::heatingLimit);
        if (monitor.capabilities().profile() != BoilerProtocol::classic || !limit.observed || !limit.raw
            || limit.quality != BoilerQuality::reported || limit.sourceType != 0x16) return std::nullopt;
        return static_cast<uint8_t>(std::clamp<int32_t>(*limit.raw / 100, 0, maximumFlowC));
    }
    static bool admits(const ClassicBoilerMonitor& monitor, uint8_t flowC) {
        const auto limit = limitC(monitor);
        return !flowC || (limit && flowC <= *limit);
    }
};

// Sends the active guard's 0x1A command (control/ActiveHeatGuard) through the
// attended trial's reviewed route: the same Classic encoder and manual-frame
// write, only when the boiler polls 0x0B. The loop posts one command per 10 s
// step; the poll owner sends it at most once and records {seq, ok}. Callers
// serialize all calls (telemetry mutex). No queue, retry or legacy fallback.
class ActiveHeatPollDriver {
public:
    static constexpr uint32_t commandTtlMs = 10000; // a command never outlives its step
    static constexpr uint64_t session = 0xAC71;     // this route's fixed id in the encoder intent
    using Encoder = bool (*)(const BoilerTestSession::Intent&, EmsRawFrame&);
    struct Result { uint32_t seq = 0; bool ok = false; };

    // compiled: board::emsActiveHeatAllowed, injected for host tests.
    ActiveHeatPollDriver(uint64_t boot, bool compiled) : boot_(boot), compiled_(compiled) {}
    // flowC: the command to send (0 = zero request), nullopt = none this step.
    // heatAllowed: plan active and the owner's confirmation present (needed
    // for a positive request). claim: the guard owns the boiler or withdraws.
    uint32_t post(uint64_t now, std::optional<uint8_t> flowC, bool heatAllowed, bool claim) {
        claim_ = compiled_ && claim;
        command_.reset();
        if (compiled_ && flowC) command_ = Pending{++seq_, *flowC, now, heatAllowed};
        return command_ ? command_->seq : 0;
    }
    bool claimed() const { return claim_; }
    const std::optional<Result>& last() const { return last_; }

    // At a poll of 0x0B. ready: the reviewed route's gates (transport healthy,
    // no trial, configuration read or settings write). True: a frame was written.
    template<class Ready, class Write>
    bool poll(uint64_t now, const ClassicBoilerMonitor& monitor, Ready ready, Encoder encode, Write write) {
        if (!command_) return false;
        const Pending c = *command_;
        command_.reset(); // one attempt per post
        last_ = Result{c.seq, false};
        if (!compiled_ || now < c.postedMs || now - c.postedMs >= commandTtlMs || (c.flowC && !c.heatAllowed)
            || !ActiveHeatEnvelope::admits(monitor, c.flowC) || !ready()) return false;
        using Command = BoilerTestSession::Command;
        const BoilerTestSession::Intent intent{c.flowC ? Command::positive : Command::zero, c.flowC, boot_, session, c.seq,
                                               c.flowC ? c.postedMs + commandTtlMs : 0};
        EmsRawFrame frame;
        if (!encode || !encode(intent, frame) || !frame.length || frame.length > frame.capacity) return false;
        bool ok = false;
        try { ok = write(frame); } catch (...) {}
        last_ = Result{c.seq, ok};
        return true;
    }

private:
    struct Pending { uint32_t seq; uint8_t flowC; uint64_t postedMs; bool heatAllowed; };
    uint64_t boot_;
    bool compiled_, claim_ = false;
    uint32_t seq_ = 0;
    std::optional<Pending> command_;
    std::optional<Result> last_;
};
}
