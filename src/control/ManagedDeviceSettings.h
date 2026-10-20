#pragma once
#include <cJSON.h>

namespace heating::control {
// Called only AFTER secret-preserving merge, inside existing session/CSRF/update
// guards. General network recovery stays writable; hidden legacy weather does not.
inline bool managedWeatherChangeAllowed(bool managed,const cJSON* previous,const cJSON* candidate) {
    if (!managed) return true;
    if (!previous || !candidate) return previous == candidate;
    if (!cJSON_IsObject(previous) || !cJSON_IsObject(candidate)) return false;
    return cJSON_Compare(previous,candidate,true);
}
}
