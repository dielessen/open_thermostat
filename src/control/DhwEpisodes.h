#pragma once
#include "EMS/ClassicBoilerMonitor.h"
#include "control/ShadowComparison.h" // localDay (device TZ)
#include <algorithm>
#include <array>
#include <cJSON.h>
#include <cstdint>
#include <optional>
#include <ostream>

namespace heating::control {
// Domestic hot water episodes from passive Classic reports (pure, boot-local,
// fixed size, observation only, never a control input). An episode is a run
// of the DHW bit of UBAMonitorFast (0x18 offset 5 bit 1); burner time is its
// flame bit (bit 3) inside the episode. Tapping or keeping warm/reheating:
//  - "flow": once the 0x34 DHW flow (offset 9) has been seen to change, flow
//    > 0 in the episode is tapping, otherwise keeping warm.
//  - "dhw_temperature_fall" until then: the EasyControl adapter reports a
//    constant 2.5 L/min and constant 0x34 bits (and 0 counters), so a fall of
//    the 0x34 DHW temperature of >= 7.5 K, from the highest value in the 2 min
//    before the episode to the lowest in it, is tapping (cold mains water in
//    the plate exchanger); a smaller fall is keeping warm. Owner logs, 27
//    episodes: taps fell 9-46 K, reheats 0-6 K.
//  - No DHW temperature either: unknown.
// An episode counts on the local day it ends. A 0x18 gap > 60 s ends it at
// the last report: no invented time. Older (reordered) reports are ignored.
class DhwEpisodes {
public:
    enum Kind : uint8_t { tapping, keepWarm, unknown, kinds };
    static constexpr uint64_t gapMs = 60000, lookbackMs = 120000;
    static constexpr int32_t tapFallCenti = 750;      // ClassicBoilerMonitor DHW temperature: hundredths degC
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
        clock(unixNow);
        const auto at = [&](F f, uint16_t type) -> std::optional<int32_t> {
            const auto& s = monitor.sample(f);
            if (s.observed && s.observedMs == now && s.sourceType == type) return s.raw;
            return {};
        };
        if (const auto t = at(F::dhwTemp, 0x34)) temperature(*t, now);
        if (const auto f = at(F::dhwFlow, 0x34)) flow(static_cast<uint8_t>(*f));
        if (const auto s = at(F::rawState, 0x18)) state(static_cast<uint8_t>(*s), now);
    }
    void state(uint8_t raw, uint64_t now) {
        if (haveState_ && now < lastStateMs_) return;
        if (open_ && now - lastStateMs_ > gapMs) close(lastStateMs_);
        if (open_ && flame_) burnerMs_ += now - lastStateMs_;
        const bool dhw = raw & 0x02;
        if (dhw && !open_) {
            open_ = true; startMs_ = now; burnerMs_ = 0; flowSeen_ = false; peak_ = 0;
            reference_ = minimum_ = std::nullopt;
            uint64_t latest = 0;                       // the fall may start before the DHW bit
            for (const auto& s : temps_) {
                if (!s.valid || s.ms > now || now - s.ms > lookbackMs) continue;
                reference_ = std::max(reference_.value_or(s.centi), s.centi);
                if (!minimum_ || s.ms >= latest) { minimum_ = s.centi; latest = s.ms; }
            }
        } else if (!dhw && open_) close(now);
        flame_ = raw & 0x08; haveState_ = true; lastStateMs_ = now;
    }
    void temperature(int32_t centi, uint64_t now) {
        temps_[next_] = {now, centi, true}; next_ = (next_ + 1) % temps_.size();
        if (!open_) return;
        if (!reference_) reference_ = centi;
        minimum_ = std::min(minimum_.value_or(centi), centi);
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

    // {"method":..,"clock_known":..,"active_s":null|s,"today":{..},"last_7_days":{..}}
    void writeJSON(std::ostream& out, uint64_t now) const {
        out << "{\"method\":\"" << (flowLive_ ? "flow" : "dhw_temperature_fall") << "\",\"clock_known\":"
            << (today_.day != unknownDay ? "true" : "false") << ",\"active_s\":";
        if (open_ && now >= startMs_) out << (now - startMs_) / 1000; else out << "null";
        out << ",\"today\":"; day(out, today_);
        out << ",\"last_7_days\":"; day(out, lastSevenDays());
        out << '}';
    }

    // /status/heating and MQTT "dhw": {"method","clock_known","today":{..},"last_7_days":{..}},
    // the closed episodes only (an open one counts once it ends). nullptr: no memory.
    cJSON* summaryJson() const {
        cJSON* root = cJSON_CreateObject();
        if (!root || !cJSON_AddStringToObject(root, "method", flowLive_ ? "flow" : "dhw_temperature_fall")
            || !cJSON_AddBoolToObject(root, "clock_known", today_.day != unknownDay)
            || !dayJson(root, "today", today_) || !dayJson(root, "last_7_days", lastSevenDays())) { cJSON_Delete(root); return nullptr; }
        return root;
    }

private:
    struct Temp { uint64_t ms = 0; int32_t centi = 0; bool valid = false; };
    void clock(std::optional<uint32_t> unixNow) {
        if (!unixNow) return;
        const int32_t d = ShadowComparison::localDay(*unixNow);
        if (today_.day == unknownDay) today_.day = d;   // boot time joins the first known day
        else if (d > today_.day) {                      // a clock step back stays today
            days_[head_] = today_; head_ = (head_ + 1) % history;
            if (count_ < history) ++count_;
            today_ = {}; today_.day = d;
        }
    }
    void close(uint64_t endMs) {
        const Kind kind = flowLive_ ? (flowSeen_ ? tapping : keepWarm)
            : reference_ && minimum_ ? (*reference_ - *minimum_ >= tapFallCenti ? tapping : keepWarm) : unknown;
        if (today_.count[kind] != UINT16_MAX) ++today_.count[kind];
        today_.seconds[kind] += static_cast<uint32_t>((endMs - startMs_) / 1000);
        today_.burnerS += static_cast<uint32_t>(burnerMs_ / 1000);
        if (flowLive_) today_.peakFlow = std::max(today_.peakFlow, peak_);
        open_ = false;
    }
    void day(std::ostream& out, const Day& d) const {
        static constexpr const char* names[kinds] = {"tapping", "keep_warm", "unknown"};
        out << '{';
        for (size_t k = 0; k < kinds; ++k)
            out << '"' << names[k] << "\":{\"count\":" << d.count[k] << ",\"s\":" << d.seconds[k] << "},";
        out << "\"burner_s\":" << d.burnerS << ",\"peak_flow_l_min\":";
        if (flowLive_ && d.peakFlow) out << d.peakFlow / 10 << '.' << d.peakFlow % 10; else out << "null";
        out << '}';
    }
    bool dayJson(cJSON* parent, const char* key, const Day& d) const {
        static constexpr const char* names[kinds] = {"tapping", "keep_warm", "unknown"};
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
    uint64_t startMs_ = 0, lastStateMs_ = 0, burnerMs_ = 0;
    std::optional<int32_t> reference_, minimum_;
    uint8_t lastFlow_ = 0, peak_ = 0;
    bool open_ = false, flame_ = false, haveState_ = false, haveFlow_ = false, flowLive_ = false, flowSeen_ = false;
};
}
