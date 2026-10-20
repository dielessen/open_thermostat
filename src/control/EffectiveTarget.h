#pragma once
#include "UtcSchedule.h"
#include <cstdint>
#include <optional>

namespace heating::control {
enum class ComfortMode { automatic, off, temporary, boost, away, vacation };
struct ComfortProfile {
    bool reviewed=false, windowSupported=false, presenceSupported=false;
    int16_t minimumCentiC=500,maximumCentiC=3500,awayCentiC=1700;
    uint32_t maximumTemporaryMs=0,maximumBoostMs=0,maximumPresenceAgeMs=0,maximumWindowAgeMs=0;
    bool valid() const {
        return reviewed && minimumCentiC>=500 && maximumCentiC<=3500 && minimumCentiC<=maximumCentiC
            && awayCentiC>=minimumCentiC && awayCentiC<=maximumCentiC
            && maximumTemporaryMs>=1000 && maximumTemporaryMs<=86400000
            && maximumBoostMs>=1000 && maximumBoostMs<=14400000
            && (!presenceSupported || (maximumPresenceAgeMs>=1000 && maximumPresenceAgeMs<=3600000))
            && (!windowSupported || (maximumWindowAgeMs>=1000 && maximumWindowAgeMs<=3600000));
    }
};
struct ComfortInputs {
    std::optional<int16_t> automaticCentiC;
    const char* automaticSource="base";
    bool ownerAdmitted=false,windowKnown=false,windowOpen=false,presenceKnown=false,away=false;
    uint64_t windowAt=0,presenceAt=0;
    int64_t utc=0;bool clockTrusted=false;
};
struct EffectiveTargetResult {
    std::optional<int16_t> target;
    const char* source="off";
    const char* reason="owner_unavailable";
    bool learningAllowed=false;
    // Target is not hydraulic readiness, actuator feedback or output permission.
};
class EffectiveTarget {
public:
    explicit EffectiveTarget(ComfortProfile profile={}):profile_(profile) {}
    // New comfort modes require explicit reviewed profile and negotiated owner.
    // This method does NOT establish that owner or authenticate commands.
    bool command(ComfortMode mode,std::optional<int16_t> target,uint64_t now,
                 uint32_t durationMs=0,int64_t vacationUntil=0,int64_t utc=0,bool clockTrusted=false) {
        if (seenNow_ && now<lastNow_) {latched_=true;return false;}
        if (!profile_.valid() || static_cast<unsigned>(mode)>static_cast<unsigned>(ComfortMode::vacation)) return false;
        if (mode==ComfortMode::temporary || mode==ComfortMode::boost) {
            const auto ceiling=mode==ComfortMode::boost?profile_.maximumBoostMs:profile_.maximumTemporaryMs;
            if (!inRange(target) || durationMs<1000 || durationMs>ceiling || now>UINT64_MAX-durationMs) return false;
        } else if (durationMs || target) return false;
        if (mode==ComfortMode::vacation) {
            if (!clockTrusted || utc<UtcSchedule::minimumUtcSecond || utc>=UtcSchedule::maximumUtcSecond
                || vacationUntil<=utc || vacationUntil>=UtcSchedule::maximumUtcSecond
                || vacationUntil-utc>366LL*86400) return false;
        } else if (vacationUntil) return false;
        mode_=mode;target_=target;until_=durationMs?now+durationMs:0;
        vacationUntil_=vacationUntil;vacationLastUtc_=utc;lastNow_=now;seenNow_=true;latched_=false;return true;
    }
    void invalidate() {mode_=ComfortMode::automatic;target_.reset();until_=0;vacationUntil_=0;latched_=false;}
    EffectiveTargetResult evaluate(uint64_t now,const ComfortInputs& in) {
        if (seenNow_ && now<lastNow_) {invalidate();latched_=true;}
        seenNow_=true;lastNow_=now;
        if (!profile_.valid()) return {{}, "off","profile_unqualified",false};
        if (!in.ownerAdmitted) {invalidate();return {{},"off","owner_unavailable",false};}
        if (latched_) return {{},"off","monotonic_fault",false};
        if (mode_==ComfortMode::off) return {{},"off","explicit_off",false};
        // Expire state, not just today's result: backward wall time never revives it.
        if ((mode_==ComfortMode::temporary || mode_==ComfortMode::boost) && now>=until_) {
            mode_=ComfortMode::automatic;target_.reset();until_=0;
        }
        if (mode_==ComfortMode::vacation) {
            if (!in.clockTrusted || in.utc<UtcSchedule::minimumUtcSecond || in.utc>=UtcSchedule::maximumUtcSecond)
                return {{},"vacation","vacation_time_invalid",false};
            if (in.utc<vacationLastUtc_) return {{},"vacation","vacation_time_reversed",false};
            vacationLastUtc_=in.utc;
            if (in.utc>=vacationUntil_) {mode_=ComfortMode::automatic;vacationUntil_=0;}
        }
        // Expiry is processed even while a contact blocks all normal demand.
        if (profile_.windowSupported) {
            if (!in.windowKnown || now<in.windowAt || now-in.windowAt>=profile_.maximumWindowAgeMs)
                return {{},"window","window_state_unknown",false};
            if (in.windowOpen) return {{},"window","window_open",false};
        }
        if (mode_==ComfortMode::temporary || mode_==ComfortMode::boost)
            return {target_,mode_==ComfortMode::boost?"boost":"temporary","bounded_override",false};
        if (mode_==ComfortMode::away || mode_==ComfortMode::vacation)
            return {profile_.awayCentiC,mode_==ComfortMode::away?"away":"vacation","explicit_away",false};
        if (profile_.presenceSupported) {
            if (!in.presenceKnown || now<in.presenceAt || now-in.presenceAt>=profile_.maximumPresenceAgeMs)
                return {{},"presence","presence_state_unknown",false};
            if (in.away) return {profile_.awayCentiC,"presence","presence_away",false};
        }
        if (!inRange(in.automaticCentiC)) return {{},in.automaticSource,"automatic_target_unavailable",false};
        return {in.automaticCentiC,in.automaticSource,"automatic",true};
    }
    // Existing api1 semantics only. No new wire capability is silently enabled.
    // Temporary remains monotonic, OFF wins, and invalid schedule stays unknown.
    static EffectiveTargetResult api1(std::optional<int16_t> automatic,const char* source,bool off,
                                     int16_t temporary,uint64_t until,uint64_t now) {
        if (off) return {{},"off","explicit_off",false};
        if (until>now && UtcSchedule::validTemperature(temporary))
            return {temporary,"temporary","bounded_override",false};
        return {automatic,source,automatic?"automatic":"automatic_target_unavailable",bool(automatic)};
    }
private:
    bool inRange(std::optional<int16_t> target) const {
        return target && *target>=profile_.minimumCentiC && *target<=profile_.maximumCentiC;
    }
    ComfortProfile profile_;ComfortMode mode_=ComfortMode::automatic;
    std::optional<int16_t> target_;uint64_t until_=0,lastNow_=0;
    int64_t vacationUntil_=0,vacationLastUtc_=0;bool seenNow_=false,latched_=false;
};
}
