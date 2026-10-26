#pragma once
#include <cstdarg>
#include <logger/Logger.h>
#include "SystemLog.h"

namespace heating::diagnostics {
class BufferedLogger final : public ib::logger::Logger {
public:
    BufferedLogger(std::vector<std::shared_ptr<ib::logger::LoggerSinkInterface>> sinks,SystemLog& log,uint64_t(*clock)())
        : ib::logger::Logger(std::move(sinks)), log_(log),clock_(clock) {}
    void printf(LogLevel level,const char* format,...) const override {
        va_list args;va_start(args,format);write(level,0,format,args,false);va_end(args);
    }
    void printf(LogLevel level,LogFeatureType feature,const char* format,...) const override {
        if(!isFeatureEnabled(feature))return;
        va_list args;va_start(args,format);write(level,feature,format,args);va_end(args);
    }
private:
    void write(LogLevel level,LogFeatureType feature,const char* format,va_list args,bool featured=true) const {
        if(!featured&&!doesMeetsLevelCondition(level))return;
        char text[256]{};va_list copy;va_copy(copy,args);
        const int size=std::vsnprintf(text,sizeof(text),format,copy);va_end(copy);
        if(size<0)return;
        // Delegate the untouched original arguments to the pinned public va_list
        // overload. Only the diagnostic copy is bounded; serial/TCP is unchanged.
        ib::logger::Logger::printf(level,feature,format,args);
        log_.append(static_cast<uint8_t>(level),getFeatureName(feature),text,clock_(),size>=int(sizeof(text)));
    }
    SystemLog& log_;
    uint64_t(*clock_)();
};
} // namespace heating::diagnostics
