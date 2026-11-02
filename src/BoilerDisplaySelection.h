#pragma once
#include "BoilerDisplayModels.h"
#include <atomic>
#include <iterator>
#include <string_view>

namespace heating {
// The boiler-model selection (presentation only, BoilerDisplay.h) as it goes out in the
// retained fw/config/boiler_profile ("display_model"): Home Assistant picks the display-code
// table of that model. An index into boilerDisplayModelIds, so no string is shared between
// the web task and the telemetry task; -1 while not read yet.
inline std::atomic<int>& boilerDisplayModelIndex() { static std::atomic<int> index{-1}; return index; }
inline void rememberBoilerDisplayModel(std::string_view model) {
    int found = -1, i = 0;
    for (const auto id : boilerDisplayModelIds) { if (id == model) found = i; ++i; }
    boilerDisplayModelIndex().store(found);
}
// "" while unknown or when no boiler is chosen ("none").
inline std::string_view rememberedBoilerDisplayModel() {
    const int i = boilerDisplayModelIndex().load();
    if (i < 0 || size_t(i) >= std::size(boilerDisplayModelIds)) return {};
    return boilerDisplayModelIds[i] == "none" ? std::string_view() : boilerDisplayModelIds[i];
}
}
