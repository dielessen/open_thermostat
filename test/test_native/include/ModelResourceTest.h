#pragma once
#include "control/ModelResourceGate.h"
#include "ControlTestHash.h"

inline heating::control::ModelResourcePlan testModelResourcePlan(uint8_t zones=1) {
    using namespace heating::control;
    ModelResourcePlan p;
    p.profile=ModelResourceProfile::bounded_memory_shadow_v1;p.schema=1;p.zones=zones;
    p.models={zones,zones,zones};p.residentBytes=131072;p.scratchBytes=16384;
    p.stackBytes=4096;p.persistentBytes=65536;
    p.checkpointSpacingMs=60000;p.checkpointsPerHour=24;p.checkpointBytesPerHour=24*554;
    return p;
}
// Actual libcrypto SHA256 behind a fixed-output callback; no mock digest.
inline bool testBoundedModelHash(std::string_view bytes,heating::control::ModelDigest& out) {
    const auto hash=controlTestHash(bytes);
    if(hash.size()!=out.size())return false;
    std::copy(hash.begin(),hash.end(),out.begin());return true;
}
