#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <chrono>
#include <thread>
#define ESP32 1
using boolean=bool;
using byte=uint8_t;
inline unsigned long millis(){return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
inline void yield(){std::this_thread::yield();}
inline uint8_t pgm_read_byte_near(const void* address){return *static_cast<const uint8_t*>(address);}
