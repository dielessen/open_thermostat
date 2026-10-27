#pragma once
#include <cstdint>
inline uint64_t fake_microseconds=0;
inline uint64_t clock_reads=0;
inline int64_t esp_timer_get_time(){++clock_reads;return fake_microseconds;}
