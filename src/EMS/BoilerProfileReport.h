#pragma once
#include "BoilerProfile.h"
#include "ClassicBoilerMonitor.h"
#include <ostream>

namespace heating::ems {
// The field id of a profile slot: the boiler-fields name (Home Assistant, E32 page).
inline const char* boilerProfileFieldName(size_t slot) {
    if (slot < BoilerProfile::classicFields) return boilerFieldSpecs[slot].name;
    if (slot < BoilerProfile::fieldCount) return entityCatalog[entityFieldRows[slot - BoilerProfile::classicFields]].id;
    return "";
}

inline void writeBoilerProfileIdentity(std::ostream& out, const BoilerProfile& p) {
    const auto& id = p.identity();
    const auto both = BoilerProfile::classicFamily | BoilerProfile::plusFamily;
    out << "{\"address\":" << unsigned(id.address) << ",\"family\":\""
        << (id.families == both ? "mixed" : id.families == BoilerProfile::classicFamily ? "classic"
            : id.families == BoilerProfile::plusFamily ? "plus" : "unknown") << "\",\"product_id\":";
    if (id.versioned) out << unsigned(id.product) << ",\"version\":\"" << unsigned(id.major) << '.' << unsigned(id.minor) << '"';
    else out << "null,\"version\":null";
    out << '}';
}

// GET /status/boiler/profile: every field with its state, for the E32 page.
inline void writeBoilerProfileJSON(std::ostream& out, const BoilerProfile& p, uint64_t now) {
    out << "{\"schema\":1,\"identity\":";
    writeBoilerProfileIdentity(out, p);
    out << ",\"rules\":{\"not_fitted_frames\":" << BoilerProfile::notFittedFrames
        << ",\"not_fitted_span_s\":" << BoilerProfile::notFittedSpanS << "},\"counts\":{";
    bool first = true;
    for (auto s : {FieldPresence::supported, FieldPresence::not_fitted, FieldPresence::not_reported, FieldPresence::unknown}) {
        out << (first ? "" : ",") << '"' << fieldPresenceName(s) << "\":" << p.count(s);
        first = false;
    }
    out << "},\"settled\":" << (p.settled() ? "true" : "false") << ",\"resets\":" << p.resets() << ",\"restored\":" << (p.restored() ? "true" : "false")
        << ",\"writes\":" << p.writes() << ",\"write_failures\":" << p.writeFailures() << ",\"fields\":[";
    for (size_t i = 0; i < BoilerProfile::fieldCount; ++i) {
        out << (i ? "," : "") << "{\"index\":" << BoilerProfile::wireIndex(i) << ",\"name\":\"" << boilerProfileFieldName(i)
            << "\",\"state\":\"" << fieldPresenceName(p.state(i)) << "\",\"last_valid_age_s\":";
        if (const auto age = p.lastValidAgeS(i, now)) out << *age; else out << "null";
        if (p.overridden(i)) out << ",\"shown_anyway\":true";
        out << '}';
    }
    out << "]}";
}

// Retained fw/config/boiler_profile (< 1 KB): wire indexes only. "supported"
// includes a not_fitted field the owner chose to show anyway; a field in no
// list is still unknown.
inline void writeBoilerProfileTopic(std::ostream& out, const BoilerProfile& p) {
    out << "{\"schema\":1,\"boiler\":";
    writeBoilerProfileIdentity(out, p);
    const auto list = [&](const char* key, auto&& match) {
        out << ",\"" << key << "\":[";
        bool first = true;
        for (size_t i = 0; i < BoilerProfile::fieldCount; ++i)
            if (match(i)) { out << (first ? "" : ",") << BoilerProfile::wireIndex(i); first = false; }
        out << ']';
    };
    list("supported", [&](size_t i) { return p.shown(i); });
    list("not_fitted", [&](size_t i) { return p.state(i) == FieldPresence::not_fitted && !p.shown(i); });
    list("not_reported", [&](size_t i) { return p.state(i) == FieldPresence::not_reported; });
    out << ",\"settled\":" << (p.settled() ? "true" : "false") << '}';
}
}
