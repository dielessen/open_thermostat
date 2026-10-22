#ifdef OPENTHERMOSTAT_E32V2
#include "ModernTransport.h"
namespace heating { extern bool networkTimeTrusted; }
bool heating::control::ModernTransport::clockValid() { return heating::networkTimeTrusted; }
#endif
