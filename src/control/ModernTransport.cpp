#ifdef OPENTHERMOSTAT_E32V2
#include "ModernTransport.h"
#include "update/GitHubUpdate.h"
#include "diagnostics/SupervisorPolicy.h"
namespace heating { extern bool networkTimeTrusted; }
bool heating::control::ModernTransport::clockValid() { return heating::networkTimeTrusted; }
void heating::control::ModernTransport::scheduleFaultRestart(uint32_t delayMs) {
    heating::update::scheduleControlledRestart(delayMs,
        static_cast<uint8_t>(heating::diagnostics::SupervisorPolicy::Reason::controlFault));
}
#endif
