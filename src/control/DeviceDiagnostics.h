#pragma once
#include <cmath>
#include <cstdint>
#include <sstream>
#include <string>
namespace heating::control {
// E32 has no enabled RTC temperature sensor. Do not turn its disabled zero into
// a temperature reading. CPU die temperature is separate from room temperature.
inline std::string deviceDiagnosticsJson(uint32_t free, uint32_t minimum,
        uint32_t largest, float cpu, uint64_t uptimeSeconds) {
    std::ostringstream out;
    out << "{\"mem_free\":" << free << ",\"mem_min_free\":" << minimum
        << ",\"mem_max_alloc\":" << largest << ",\"temperature\":null,\"cpu_temperature\":";
    if(std::isfinite(cpu) && cpu>=-40 && cpu<=150) out << cpu;
    else out << "null";
    out << ",\"uptime\":" << uptimeSeconds << '}';
    return out.str();
}
// fw/heartbeat's "cpu_deci_c" (beta.21): the CPU die temperature in tenths of a degree,
// rounded without libm; noCpuDeciC when it is not a plausible reading (-40..150 C).
inline constexpr int noCpuDeciC=-32768;
inline int deviceCpuDeciC(float cpu) {
    if(!std::isfinite(cpu) || cpu<-40 || cpu>150) return noCpuDeciC;
    const float scaled=cpu*10.0f;
    return static_cast<int>(scaled<0?scaled-0.5f:scaled+0.5f);
}
}
