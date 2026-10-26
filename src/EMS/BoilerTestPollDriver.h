#pragma once
#include "BoilerTestService.h"
#include "EmsFrameQueue.h"

namespace heating::ems {

// Called by the addressed-poll owner with the service/monitor serialized.
// No queue, allocation, retained intent or implicit legacy fallback. The encoder
// is an independently reviewed installation dependency, NEVER HTTP/config data.
class BoilerTestPollDriver {
public:
    using Encoder = bool (*)(const BoilerTestSession::Intent&, EmsRawFrame&);
    enum class Result { unowned, waiting, rejected, sent, failed };

    template<class Clock, class Gates, class Write>
    static Result poll(BoilerTestService& service, const ClassicBoilerMonitor& monitor,
                       Clock clock, Gates gates, Encoder encode, Write write) {
        if (!service.active()) return Result::unowned;
        uint64_t observedNow=0;
        BoilerTestSession::Intent intent{};
        bool began=false;
        const auto now=[&] { observedNow=clock();return observedNow; };
        try {
            intent = service.next(now(), gates(), monitor);
            if (intent.command == BoilerTestSession::Command::none) return Result::waiting;
            EmsRawFrame frame;
            if (!encode || !encode(intent, frame) || !frame.length || frame.length > frame.capacity) {
                service.transportFault(now());
                return Result::rejected;
            }
            // Encoding is not admission: time and conditions may have changed.
            if (!service.beginTransmit(intent, now(), gates(), monitor)) return Result::rejected;
            began=true;
            const bool success = write(frame);
            const bool recorded = service.finishTransmit(intent, now(), success, gates(), monitor);
            return success && recorded ? Result::sent : Result::failed;
        } catch (...) {
            // Never call a failing producer again while unwinding. A writer may
            // already have emitted bytes: retire its in-flight state without
            // claiming delivery, stop proof or restored positive authority.
            if (began) service.finishTransmit(intent, observedNow, false, {}, monitor);
            service.transportFault(observedNow);
            return began ? Result::failed : Result::rejected;
        }
    }
};

} // namespace heating::ems
