#pragma once
#include <string>
#include <string_view>

namespace heating::control {
// Single-key atomic durable store. Native fault-injection stores exercise this
// interface; ESP implementation uses NVS set_blob/commit, not SPIFFS overwrite.
class ControlStore {
public:
    virtual ~ControlStore()=default;
    virtual bool load(std::string &bytes)=0; // empty success = never configured
    virtual bool save(std::string_view bytes)=0; // false => durability ambiguous
};

}
