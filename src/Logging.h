#pragma once

#ifdef ARDUINO
#include <Arduino.h>
#endif
#include <logger/LoggerInterface.h>
#include <memory>

namespace heating {
extern std::shared_ptr<ib::logger::LoggerInterface> logger;
}

#ifdef OPENTHERMOSTAT_E32V2
namespace heating {
inline bool logMessageWanted(const ib::logger::LoggerInterface& log,
                             ib::logger::LoggerInterface::LogLevel level,
                             ib::logger::LoggerInterface::LogFeatureType feature) {
    return log.doesFeatureMeetsLevelCondition(level,feature);
}
inline bool logMessageWanted(const ib::logger::LoggerInterface& log,
                             ib::logger::LoggerInterface::LogLevel level,const char*) {
    return log.doesMeetsLevelCondition(level);
}
}
// The vendor macros call printf before filtering, evaluating every argument.
// Keep the public logger API, but skip formatting/JSON/flash work when no sink
// accepts this message. BufferedLogger includes web/syslog in its feature test.
// Evaluate the logger, level and feature/format once, including no-argument logs.
#undef DBGLOG
#define DBGLOG(log,level,first,...) \
    do { \
        const auto& otMessageLogger=(log); \
        if(otMessageLogger) { \
            const auto otMessageLevel=(level); \
            const auto otMessageFirst=(first); \
            if(heating::logMessageWanted(*otMessageLogger,otMessageLevel,otMessageFirst)) \
                otMessageLogger->printf(otMessageLevel,otMessageFirst, ##__VA_ARGS__); \
        } \
    } while(0)
#endif
