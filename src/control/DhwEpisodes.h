#pragma once
#include "EMS/ClassicBoilerMonitor.h"
#include "control/ShadowComparison.h" // localDay (device TZ)
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <optional>
#include <ostream>
#include <string>
#include <string_view>

namespace heating::control {
// Domestic hot water episodes from passive Classic reports (pure, boot-local,
// fixed size, observation only, never a control input). An episode is a run
// of the DHW bit of UBAMonitorFast (0x18 offset 5 bit 1); burner time is its
// flame bit (bit 3) inside the episode. The most direct source the boiler
// reports decides what the episode was (universal, every boiler type):
//  - "storage": a boiler with a cylinder (0x34 offset 8 DHW type 3 = buffer,
//    4 = layered buffer), or a charging bit (0x34 offset 5, 0x08) seen to
//    change and set in the episode (DHW type unknown): it charged the cylinder.
//  - "flow": a combi whose 0x34 DHW flow (offset 9) has been seen to change:
//    flow > 0 in the episode is tapping, otherwise keeping warm.
//  - "dhw_temperature_fall" for boilers without either (the EasyControl
//    adapter reports a constant 2.5 L/min and constant 0x34 bits): a tap is
//    cold mains water in the plate exchanger, so the 0x34 DHW temperature
//    falls deep or stays down: >= 15 K from the highest value in the 2 min
//    before the episode to the lowest in it, or >= 90 s at 7.5 K or more below
//    that value. The look-back starts no earlier than the end of the previous
//    episode (a reheat right after a tap is no second tap). A small tap
//    (washing hands) may only cool the sensor before the round: so a round is
//    keeping warm only when the sensor fell before it no faster than it does
//    in this installation's own rounds at night (01:00-05:00 local, nobody
//    taps): from the highest value since the previous episode to the start.
//    The sensor sits where heat enters the store: after a reheat it overshoots
//    and falls fast while the heat mixes through, so the fall is compared
//    with the night rounds, never read as a heat loss. Usage: faster than the
//    second-fastest of the last 16 night rounds by a quarter (at least
//    0.3 K/min); until 4 night rounds are seen, faster than 2 K/min (no
//    tap-free round on the owner's boiler fell faster than 1.5 K/min). Owner
//    data 26 Oct-1 Nov 2026: taps fall 14-46 K and stay down for minutes;
//    keep-warm rounds dip 2-11 K and recover within about a minute; at night
//    a short reheat is often followed by more rounds 8-14 min apart while the
//    store mixes (0.6-1.5 K/min before them), as fast as most daytime rounds.
//  - No DHW temperature either: unknown.
// An episode counts on the local day it ends. A 0x18 gap > 60 s ends it at
// the last report: no invented time. Older (reordered) reports are ignored.
// rc.4 (F2): today and the last 6 days survive a restart through record() and
// restore() (HeatingController keeps them in NVS); the rest stays boot-local.
class DhwEpisodes {
public:
    enum Kind : uint8_t { tapping, keepWarm, unknown, charging, kinds };
    static constexpr uint64_t gapMs = 60000, lookbackMs = 120000, tapBelowMs = 90000;
    static constexpr int32_t tapFallCenti = 1500;     // ClassicBoilerMonitor DHW temperature: hundredths degC
    static constexpr int32_t tapBelowCenti = 750;     // this far below the reference for tapBelowMs: a tap too
    // The fall before a round, in hundredths degC per minute: usage above this until the nights are learned,
    // and never a learned limit below the floor.
    static constexpr int32_t defaultUsageRate = 200, usageRateFloor = 30;
    static constexpr size_t nightRounds = 16, nightRoundsNeeded = 4;
    static constexpr size_t history = 6;               // completed days: today + 6 = last 7 days
    static constexpr int32_t unknownDay = ShadowComparison::unknownDay;
    struct Day {
        int32_t day = unknownDay;                      // local days since 1970-01-01
        std::array<uint16_t, kinds> count{};
        std::array<uint32_t, kinds> seconds{};
        uint32_t burnerS = 0;
        uint8_t peakFlow = 0;                          // tenths L/min, only while the flow is live
    };

    // Call after ClassicBoilerMonitor::receive() for every telegram; reacts
    // only to the 0x18/0x34 report that arrived at `now`.
    void observe(const ems::ClassicBoilerMonitor& monitor, uint64_t now, std::optional<uint32_t> unixNow) {
        using F = ems::BoilerField;
        clock(unixNow, now);
        const auto at = [&](F f, uint16_t type) -> std::optional<int32_t> {
            const auto& s = monitor.sample(f);
            if (s.observed && s.observedMs == now && s.sourceType == type) return s.raw;
            return {};
        };
        if (const auto t = at(F::dhwTemp, 0x34)) temperature(*t, now);
        if (const auto f = at(F::dhwFlow, 0x34)) flow(static_cast<uint8_t>(*f));
        if (const auto t = at(F::dhwType, 0x34)) dhwType(static_cast<uint8_t>(*t));
        if (const auto c = at(F::rawDhwCharging, 0x34)) chargingBit(*c != 0);
        if (const auto s = at(F::rawState, 0x18)) state(static_cast<uint8_t>(*s), now);
    }
    void state(uint8_t raw, uint64_t now) {
        if (haveState_ && now < lastStateMs_) return;
        if (open_ && now - lastStateMs_ > gapMs) close(lastStateMs_);
        if (open_ && flame_) burnerMs_ += now - lastStateMs_;
        const bool dhw = raw & 0x02;
        if (dhw && !open_) {
            open_ = true; startMs_ = now; burnerMs_ = 0; flowSeen_ = false; peak_ = 0;
            chargingSeen_ = chargingBit_; belowMs_ = 0; lastTempMs_ = 0; lastTempBelow_ = false;
            reference_ = minimum_ = preRate_ = std::nullopt;
            uint64_t latest = 0;                       // the fall may start before the DHW bit
            for (const auto& s : temps_) {
                if (!s.valid || s.ms > now || now - s.ms > lookbackMs || s.ms < endMs_) continue;
                reference_ = std::max(reference_.value_or(s.centi), s.centi);
                if (!minimum_ || s.ms >= latest) { minimum_ = s.centi; latest = s.ms; }
            }
            // How fast the sensor fell before this round: from the highest value since the previous episode.
            if (idlePeak_ && lastTemp_ && now >= idlePeakMs_ + 60000)
                preRate_ = static_cast<int32_t>(std::max<int64_t>(0, *idlePeak_ - *lastTemp_) * 60000 / int64_t(now - idlePeakMs_));
            const auto hour = localHour(now);
            night_ = hour && *hour >= 1 && *hour < 5;
        } else if (!dhw && open_) close(now);
        flame_ = raw & 0x08; haveState_ = true; lastStateMs_ = now;
    }
    void temperature(int32_t centi, uint64_t now) {
        temps_[next_] = {now, centi, true}; next_ = (next_ + 1) % temps_.size();
        lastTemp_ = centi;
        if (!open_) {
            if (!idlePeak_ || centi > *idlePeak_) { idlePeak_ = centi; idlePeakMs_ = now; }
            return;
        }
        if (!reference_) reference_ = centi;
        minimum_ = std::min(minimum_.value_or(centi), centi);
        // Time well below the reference: a tap keeps the exchanger cold, a keep-warm dip recovers.
        if (lastTempBelow_ && now >= lastTempMs_) belowMs_ += now - lastTempMs_;
        lastTempBelow_ = centi <= *reference_ - tapBelowCenti; lastTempMs_ = now;
    }
    // 0x34 offset 8: 1 = flow (combi), 2 = buffered flow, 3 = buffer, 4 = layered buffer (cylinder).
    void dhwType(uint8_t type) { dhwType_ = type; }
    void chargingBit(bool on) {
        if (haveCharging_ && on != chargingBit_) chargingLive_ = true; // boot-local, sticky
        haveCharging_ = true; chargingBit_ = on;
        if (open_ && on) chargingSeen_ = true;
    }
    void flow(uint8_t tenths) {
        if (haveFlow_ && tenths != lastFlow_) flowLive_ = true; // boot-local, sticky
        haveFlow_ = true; lastFlow_ = tenths;
        if (open_ && tenths) { flowSeen_ = true; peak_ = std::max(peak_, tenths); }
    }

    const Day& today() const { return today_; }
    Day lastSevenDays() const {
        Day sum = today_;
        for (size_t i = 0; i < count_; ++i) {
            const Day& d = days_[(head_ + history - 1 - i) % history];
            if (today_.day != unknownDay && d.day != unknownDay && d.day < today_.day - 6) continue;
            for (size_t k = 0; k < kinds; ++k) { sum.count[k] = static_cast<uint16_t>(std::min<uint32_t>(65535, sum.count[k] + d.count[k])); sum.seconds[k] += d.seconds[k]; }
            sum.burnerS += d.burnerS; sum.peakFlow = std::max(sum.peakFlow, d.peakFlow);
        }
        return sum;
    }
    bool flowLive() const { return flowLive_; }
    // The open episode so far, by the rule close() uses (a tap shows once its fall is clear,
    // usually within half a minute); nullopt without an open episode.
    std::optional<Kind> openKind() const { return open_ ? std::optional<Kind>(classify()) : std::nullopt; }
    // What the boiler does now: "tapping", "keep_warm", "charging", "hot_water" (no source to
    // sort it), "heating" (flame without hot water), "idle"; nullptr before the first 0x18.
    const char* activity() const {
        static constexpr const char* names[kinds] = {"tapping", "keep_warm", "hot_water", "charging"};
        if (const auto kind = openKind()) return names[*kind];
        if (!haveState_) return nullptr;
        return flame_ ? "heating" : "idle";
    }
    // A cylinder: by its DHW type, or (type unknown) by a charging bit that changes.
    bool storage() const { return cylinder() || (chargingLive_ && !combi()); }
    const char* method() const { return storage() ? "storage" : flowLive_ ? "flow" : "dhw_temperature_fall"; }
    // The DHW temperature rule's limit for the fall before a round: learned from the nights, or the default.
    bool nightLearned() const { return nightCount_ >= nightRoundsNeeded; }
    int32_t usageRate() const {
        if (!nightLearned()) return defaultUsageRate;
        int32_t first = 0, second = 0;                 // the second-fastest: one night tap does not set the limit
        for (size_t i = 0; i < nightCount_; ++i) {
            const int32_t r = nightRates_[i];
            if (r > first) { second = first; first = r; } else if (r > second) second = r;
        }
        return std::max(usageRateFloor, second + second / 4);
    }
    // Wall clock (unix seconds) at the monotonic `now`: for the day of an episode and the night hours.
    void clock(std::optional<uint32_t> unixNow, uint64_t now) {
        if (!unixNow) return;
        unixNow_ = *unixNow; unixAtMs_ = now;
        const int32_t d = ShadowComparison::localDay(*unixNow);
        if (today_.day == unknownDay) {                 // boot time joins the first known day
            today_.day = firstDay_ = d;
            bootUtc_ = *unixNow - uint32_t(std::min<uint64_t>(now / 1000, *unixNow));
            if (pending_) applyPending();
        } else if (d > today_.day) {                    // a clock step back stays today
            days_[head_] = today_; head_ = (head_ + 1) % history;
            if (count_ < history) ++count_;
            today_ = {}; today_.day = d; ++version_;
        }
    }

    // rc.4 (F2): the days over a restart. record(): "1" then today and each history day of the
    // last 7 days, newest first, as ";day,count x4,seconds x4,burner_s,peak_flow" (at most
    // recordBytes); empty until the day is known and a stored record was joined. restore(): that
    // text at boot; it joins this boot's counts once the clock gives the day (today's are added,
    // earlier days go back into the history). False: not a record (ignored).
    static constexpr size_t recordBytes = 512;
    std::string record() const {
        if (today_.day == unknownDay || pending_) return {};
        std::string out = "1";
        const auto number = [&](uint32_t v) {
            char digits[10]; size_t n = 0;
            do { digits[n++] = char('0' + v % 10); v /= 10; } while (v);
            while (n) out += digits[--n];
        };
        const auto add = [&](const Day& d) {
            out += ';'; number(uint32_t(d.day));
            for (size_t k = 0; k < kinds; ++k) { out += ','; number(d.count[k]); }
            for (size_t k = 0; k < kinds; ++k) { out += ','; number(d.seconds[k]); }
            out += ','; number(d.burnerS); out += ','; number(d.peakFlow);
        };
        add(today_);
        for (size_t i = 0; i < count_; ++i) {
            const Day& d = days_[(head_ + history - 1 - i) % history];
            if (d.day != unknownDay && d.day < today_.day && d.day >= today_.day - int32_t(history)) add(d);
        }
        return out.size() <= recordBytes ? out : std::string();
    }
    bool restore(std::string_view text) {
        pending_ = false; pendingCount_ = 0;
        if (text.size() < 3 || text.size() > recordBytes || text.substr(0, 2) != "1;") return false;
        text.remove_prefix(2);
        std::array<Day, history + 1> days{};
        size_t n = 0;
        for (;;) {
            const auto end = text.find(';');
            if (n == days.size() || !parseDay(text.substr(0, end), days[n]) || (n && days[n].day >= days[n - 1].day)) return false;
            ++n;
            if (end == std::string_view::npos) break;
            text.remove_prefix(end + 1);
        }
        pendingDays_ = days; pendingCount_ = n; pending_ = true;
        if (today_.day != unknownDay) applyPending();
        return true;
    }
    // Store now: a new day, or an hour after the last store with something new; never before
    // the clock is known and a stored record joined. saved(): after each attempt (a refused write
    // tries again in an hour).
    bool saveDue(uint64_t now) const {
        return unsaved() && (savedDay_ != today_.day || !savedAtMs_ || now - savedAtMs_ >= 3600000);
    }
    // Something new since the last store (a planned restart stores it at once).
    bool unsaved() const { return today_.day != unknownDay && !pending_ && (savedDay_ != today_.day || version_ != savedVersion_); }
    void saved(uint64_t now) { savedDay_ = today_.day; savedVersion_ = version_; savedAtMs_ = now ? now : 1; }
    // Today's totals start at this boot (no stored record of today joined, the boot was today):
    // the unix time of the boot, else nullopt (also while the clock is unknown).
    std::optional<uint32_t> sinceRestartUtc() const {
        if (today_.day == unknownDay || today_.day > firstDay_ || todayRestored_) return std::nullopt;
        return bootUtc_;
    }

    // {"method":..,"baseline":..,"clock_known":..,"since_restart_utc":null|s,"active_s":null|s,"today":{..},"last_7_days":{..}}
    // baseline: what the DHW temperature rule compares the fall before a round with ("night": this
    // installation's night rounds, "default"); null for the other methods. since_restart_utc (rc.4):
    // today's totals start at this boot (sinceRestartUtc): the Boiler page says "since the restart at
    // hh:mm" (only here, not in the MQTT summary below).
    void writeJSON(std::ostream& out, uint64_t now) const {
        out << "{\"method\":\"" << method() << "\",\"baseline\":";
        if (const char* b = baseline()) out << '"' << b << '"'; else out << "null";
        out << ",\"clock_known\":"
            << (today_.day != unknownDay ? "true" : "false") << ",\"since_restart_utc\":";
        if (const auto since = sinceRestartUtc()) out << *since; else out << "null";
        out << ",\"active_s\":";
        if (open_ && now >= startMs_) out << (now - startMs_) / 1000; else out << "null";
        out << ",\"today\":"; day(out, today_);
        out << ",\"last_7_days\":"; day(out, lastSevenDays());
        out << '}';
    }

    // /status/heating and MQTT "dhw": {"method","baseline","clock_known","today":{..},"last_7_days":{..}},
    // the closed episodes only (an open one counts once it ends). nullptr: no memory.
    cJSON* summaryJson() const {
        cJSON* root = cJSON_CreateObject();
        const char* b = baseline();
        if (!root || !cJSON_AddStringToObject(root, "method", method())
            || !(b ? cJSON_AddStringToObject(root, "baseline", b) : cJSON_AddNullToObject(root, "baseline"))
            || !cJSON_AddBoolToObject(root, "clock_known", today_.day != unknownDay)
            || !dayJson(root, "today", today_) || !dayJson(root, "last_7_days", lastSevenDays())) { cJSON_Delete(root); return nullptr; }
        return root;
    }

private:
    struct Temp { uint64_t ms = 0; int32_t centi = 0; bool valid = false; };
    const char* baseline() const {
        return storage() || flowLive_ ? nullptr : nightLearned() ? "night" : "default";
    }
    std::optional<int> localHour(uint64_t now) const {
        if (!unixNow_ || now < unixAtMs_) return std::nullopt;
        const int64_t local = RoomSchedule::localSeconds(int64_t(*unixNow_) + int64_t((now - unixAtMs_) / 1000));
        return int(((local % 86400) + 86400) % 86400 / 3600);
    }
    // A tap by the episode's own fall: deep, or lasting.
    bool fellLikeATap() const { return *reference_ - *minimum_ >= tapFallCenti || belowMs_ >= tapBelowMs; }
    void close(uint64_t endMs) {
        if (lastTempBelow_ && endMs >= lastTempMs_) belowMs_ += endMs - lastTempMs_;
        const Kind kind = classify();
        // A night round without a tap's own fall: how fast this installation's sensor falls when nobody taps.
        if (night_ && preRate_ && !storage() && !flowLive_ && reference_ && minimum_ && !fellLikeATap()) {
            nightRates_[nightNext_] = static_cast<int16_t>(std::min<int32_t>(*preRate_, INT16_MAX));
            nightNext_ = (nightNext_ + 1) % nightRounds;
            if (nightCount_ < nightRounds) ++nightCount_;
        }
        if (today_.count[kind] != UINT16_MAX) ++today_.count[kind];
        today_.seconds[kind] += static_cast<uint32_t>((endMs - startMs_) / 1000);
        today_.burnerS += static_cast<uint32_t>(burnerMs_ / 1000);
        if (flowLive_) today_.peakFlow = std::max(today_.peakFlow, peak_);
        open_ = false; endMs_ = endMs; idlePeak_ = std::nullopt; ++version_;
    }
    // One stored day: "day,count x4,seconds x4,burner_s,peak_flow", unsigned decimals within bounds.
    static bool parseDay(std::string_view s, Day& d) {
        constexpr size_t fields = 3 + 2 * kinds;
        uint32_t v[fields] = {};
        for (size_t f = 0; f < fields; ++f) {
            size_t len = 0;
            uint64_t value = 0;
            while (len < s.size() && len < 10 && s[len] >= '0' && s[len] <= '9') value = value * 10 + uint64_t(s[len++] - '0');
            if (!len || value > UINT32_MAX) return false;
            v[f] = uint32_t(value);
            s.remove_prefix(len);
            if (f + 1 == fields) break;
            if (s.empty() || s.front() != ',') return false;
            s.remove_prefix(1);
        }
        constexpr uint32_t dayLimit = 2 * 86400; // an episode across midnight counts on the day it ends
        if (!s.empty() || !v[0] || v[0] > 1000000 || v[fields - 2] > dayLimit || v[fields - 1] > 255) return false;
        d = {};
        d.day = int32_t(v[0]);
        for (size_t k = 0; k < kinds; ++k) {
            if (v[1 + k] > UINT16_MAX || v[1 + kinds + k] > dayLimit) return false;
            d.count[k] = uint16_t(v[1 + k]); d.seconds[k] = v[1 + kinds + k];
        }
        d.burnerS = v[fields - 2]; d.peakFlow = uint8_t(v[fields - 1]);
        return true;
    }
    // A stored record joins this boot once the day is known: today's totals are added, earlier
    // days of the last 7 go back into the (empty at boot) history; others are dropped.
    void applyPending() {
        pending_ = false;
        const auto inHistory = [&](int32_t day) {
            for (size_t i = 0; i < count_; ++i) if (days_[(head_ + history - 1 - i) % history].day == day) return true;
            return false;
        };
        for (size_t i = pendingCount_; i-- > 0;) { // oldest first, as the day change fills the history
            const Day& d = pendingDays_[i];
            if (d.day == today_.day) {
                for (size_t k = 0; k < kinds; ++k) {
                    today_.count[k] = uint16_t(std::min<uint32_t>(UINT16_MAX, uint32_t(today_.count[k]) + d.count[k]));
                    today_.seconds[k] += d.seconds[k];
                }
                today_.burnerS += d.burnerS; today_.peakFlow = std::max(today_.peakFlow, d.peakFlow);
                todayRestored_ = true;
            } else if (d.day < today_.day && d.day >= today_.day - int32_t(history) && count_ < history && !inHistory(d.day)) {
                days_[head_] = d; head_ = (head_ + 1) % history; ++count_;
            }
        }
        pendingCount_ = 0; ++version_;
    }
    void day(std::ostream& out, const Day& d) const {
        static constexpr const char* names[kinds] = {"tapping", "keep_warm", "unknown", "charging"};
        out << '{';
        for (size_t k = 0; k < kinds; ++k)
            out << '"' << names[k] << "\":{\"count\":" << d.count[k] << ",\"s\":" << d.seconds[k] << "},";
        out << "\"burner_s\":" << d.burnerS << ",\"peak_flow_l_min\":";
        if (flowLive_ && d.peakFlow) out << d.peakFlow / 10 << '.' << d.peakFlow % 10; else out << "null";
        out << '}';
    }
    bool dayJson(cJSON* parent, const char* key, const Day& d) const {
        static constexpr const char* names[kinds] = {"tapping", "keep_warm", "unknown", "charging"};
        cJSON* o = cJSON_AddObjectToObject(parent, key);
        if (!o) return false;
        for (size_t k = 0; k < kinds; ++k) {
            cJSON* kind = cJSON_AddObjectToObject(o, names[k]);
            if (!kind || !cJSON_AddNumberToObject(kind, "count", d.count[k]) || !cJSON_AddNumberToObject(kind, "s", d.seconds[k])) return false;
        }
        if (!cJSON_AddNumberToObject(o, "burner_s", d.burnerS)) return false;
        return flowLive_ && d.peakFlow ? cJSON_AddNumberToObject(o, "peak_flow_l_min", d.peakFlow / 10.0) != nullptr
                                       : cJSON_AddNullToObject(o, "peak_flow_l_min") != nullptr;
    }
    std::array<Temp, 16> temps_{};                     // ~2.5 min of 0x34 at its ~10 s cadence
    size_t next_ = 0;
    Day today_;
    std::array<Day, history> days_{};
    size_t head_ = 0, count_ = 0;
    Kind classify() const {
        if (cylinder() || (chargingLive_ && chargingSeen_ && !combi())) return charging;
        if (flowLive_) return flowSeen_ ? tapping : keepWarm;
        // Deep or lasting in the episode, or a faster fall before it than this installation's night rounds.
        if (reference_ && minimum_) return fellLikeATap() || (preRate_ && *preRate_ > usageRate()) ? tapping : keepWarm;
        return unknown;
    }
    bool cylinder() const { return dhwType_ == 3 || dhwType_ == 4; }
    bool combi() const { return dhwType_ == 1 || dhwType_ == 2; }
    uint64_t startMs_ = 0, lastStateMs_ = 0, burnerMs_ = 0, endMs_ = 0, belowMs_ = 0, lastTempMs_ = 0;
    std::optional<uint8_t> dhwType_;
    std::optional<int32_t> reference_, minimum_, preRate_, idlePeak_, lastTemp_;
    std::optional<uint32_t> unixNow_;
    uint64_t unixAtMs_ = 0, idlePeakMs_ = 0;
    std::array<int16_t, nightRounds> nightRates_{};    // the fall before night rounds, hundredths degC per minute
    size_t nightCount_ = 0, nightNext_ = 0;
    bool night_ = false;
    uint8_t lastFlow_ = 0, peak_ = 0;
    bool open_ = false, flame_ = false, haveState_ = false, haveFlow_ = false, flowLive_ = false, flowSeen_ = false;
    bool haveCharging_ = false, chargingBit_ = false, chargingLive_ = false, chargingSeen_ = false, lastTempBelow_ = false;
    // rc.4 (F2): the stored days over a restart.
    std::array<Day, history + 1> pendingDays_{};       // a restored record until the day is known
    size_t pendingCount_ = 0;
    bool pending_ = false, todayRestored_ = false;
    int32_t firstDay_ = unknownDay, savedDay_ = unknownDay; // the boot's first known day; the day last stored
    uint32_t bootUtc_ = 0, version_ = 0, savedVersion_ = 0;  // version_: a counted episode or a new day
    uint64_t savedAtMs_ = 0;
};
}
