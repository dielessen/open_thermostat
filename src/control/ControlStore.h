#pragma once
#include "ControlPartitionBudget.h"
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
    // true only when the last save() returned false BEFORE touching durable
    // storage (refused: size or partition budget). Then nothing is ambiguous.
    virtual bool lastSaveRefused() const {return false;}
    // Model-only opt-in boundary: backend checks length BEFORE allocating/copying.
    // Fail closed by default: config/NVS "config" stores are NOT model keys.
    virtual bool loadBounded(std::string&,size_t) {return false;}
    virtual bool saveBounded(std::string_view,size_t) {return false;}
    virtual ControlPartitionStats modelPartitionStats() const {return {};}
};

}
