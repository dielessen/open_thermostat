#ifdef OPENTHERMOSTAT_E32V2
#include "ModernTransport.h"
#include "update/GitHubUpdate.h"
#include "diagnostics/SupervisorPolicy.h"
#include "diagnostics/BlackBox.h"
namespace heating { extern bool networkTimeTrusted; }
bool heating::control::ModernTransport::clockValid() { return heating::networkTimeTrusted; }
bool heating::control::ModernTransport::decideFaultRestart(uint64_t now,uint64_t faultAt) {
    using heating::diagnostics::SupervisorPolicy;
    switch(SupervisorPolicy::controlFault(now,faultAt,heating::diagnostics::blackBox.previousRestart())) {
        case SupervisorPolicy::ControlFaultAction::wait: return false;
        case SupervisorPolicy::ControlFaultAction::hold: heating::diagnostics::blackBox.controlFaultHeld(); return true;
        case SupervisorPolicy::ControlFaultAction::restart: break;
    }
    heating::update::scheduleControlledRestart(10000,static_cast<uint8_t>(SupervisorPolicy::Reason::controlFault));
    return true;
}
#endif
