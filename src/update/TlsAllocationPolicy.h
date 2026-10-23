#pragma once
#include <cstddef>
#include <limits>

namespace heating::update {
// Only the updater task opts into the SDK-supported external TLS heap. Other
// tasks retain the pinned SDK allocator, and external failure never falls back.
template<class Internal,class External>
void *allocateTlsMemory(size_t count,size_t size,bool updater,Internal internal,External external) {
    if(count&&size>std::numeric_limits<size_t>::max()/count)return nullptr;
    return updater?external(count,size):internal(count,size);
}
}
