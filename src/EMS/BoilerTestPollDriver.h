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
        const auto intent = service.next(clock(), gates(), monitor);
        if (intent.command == BoilerTestSession::Command::none) return Result::waiting;
        EmsRawFrame frame;
        if (!encode || !encode(intent, frame) || !frame.length || frame.length > frame.capacity) {
            service.transportFault(clock());
            return Result::rejected;
        }
        // Encoding is not admission: time and conditions may have changed.
        if (!service.beginTransmit(intent, clock(), gates(), monitor)) return Result::rejected;
        const bool success = write(frame);
        const bool recorded = service.finishTransmit(intent, clock(), success, gates(), monitor);
        return success && recorded ? Result::sent : Result::failed;
    }
};

} // namespace heating::ems
