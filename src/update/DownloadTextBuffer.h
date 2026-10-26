#pragma once
#include <cstring>
#include <memory>
#include <string>

namespace heating::update {
// The caller chooses the memory region. Never silently fall back to internal
// heap: TLS needs that heap while the response is being received.
class DownloadTextBuffer {
    std::unique_ptr<char,void(*)(void*)> bytes_;
    size_t limit_,size_=0;
public:
    DownloadTextBuffer(size_t limit,void *(*allocate)(size_t),void (*release)(void*)):
        bytes_(static_cast<char*>(allocate(limit)),release),limit_(limit) {}
    bool ready() const {return bytes_!=nullptr;}
    size_t append(const void *data,size_t size) {
        if(!ready()||size>limit_-size_)return 0;
        if(size)std::memcpy(bytes_.get()+size_,data,size);
        size_+=size;return size;
    }
    std::string text() const {return ready()?std::string(bytes_.get(),size_):std::string();}
};
}
