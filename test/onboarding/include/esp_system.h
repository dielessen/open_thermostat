#pragma once
#include <cstddef>
#include <cassert>
#include "bootloader_random.h"
// Deterministic test bytes. This does NOT validate entropy or cryptographic quality.
inline void esp_fill_random(void *out,std::size_t size){
    assert(testCrypto::entropyEnabled);++testCrypto::entropyCalls;
    auto bytes=static_cast<unsigned char*>(out);
    for(std::size_t i=0;i<size;++i)bytes[i]=static_cast<unsigned char>(i+testCrypto::entropyCalls);
}
