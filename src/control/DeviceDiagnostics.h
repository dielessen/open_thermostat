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
}
