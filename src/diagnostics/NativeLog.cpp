#ifdef OPENTHERMOSTAT_E32V2
#include "LogRuntime.h"
#include "NativeLogCapture.h"
#include <esp_log.h>
#include <atomic>
#include <cstdio>

extern "C" int __real_log_printfv(const char*,va_list);
namespace heating::diagnostics {
namespace {
std::atomic<bool> captureEnabled{false};
std::atomic_flag capturing=ATOMIC_FLAG_INIT;
std::atomic<vprintf_like_t> previousIdf{nullptr};
std::atomic<bool> installed{false};
void capture(const char* feature,const char* format,va_list args) {
    if(!captureEnabled.load(std::memory_order_relaxed))return;
    if(capturing.test_and_set(std::memory_order_acquire)){runtime.log.noteContention();return;}
    captureNative(runtime.log,feature,uptimeMs(),format,args);
    capturing.clear(std::memory_order_release);
}
int idfOutput(const char* format,va_list args) {
    va_list copy;va_copy(copy,args);capture("ESP-IDF",format,copy);va_end(copy);
    const auto previous=previousIdf.load(std::memory_order_acquire);
    return previous?previous(format,args):std::vprintf(format,args);
}
}
void installNativeLogCapture() {
    if(installed.exchange(true))return;
    previousIdf.store(esp_log_set_vprintf(idfOutput),std::memory_order_release);
    captureEnabled.store(true,std::memory_order_relaxed);
}
}
extern "C" int __wrap_log_printfv(const char* format,va_list args) {
    va_list copy;va_copy(copy,args);
    heating::diagnostics::capture("Arduino",format,copy);va_end(copy);
    // The pinned SDK already owns __wrap_log_printf. Its unresolved call to
    // log_printfv passes here; keep that SDK wrapper and the full UART output.
    return __real_log_printfv(format,args);
}
#endif
