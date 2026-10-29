#pragma once
#include "control/FlowLearner.h"
#include "control/RoomSchedule.h"
#include <cstdio>
namespace heating::control {
// Optimum start and night-setback economics from FlowLearner's per-room models
// (owner, 29 Oct: start on time for the week program; "het kan goedkoper zijn om
// hem modulerend 's nachts op 19 graden te laten"). Beta.18: report only. The
// active mode can later raise the effective setpoint to Start::targetCentiC
// while Start::startNow holds. Pure: no IO or clock.
struct WarmupPlanner {
    static constexpr uint32_t maxLeadS = 8 * 3600, compareS = 6 * 3600;
    // While not learned: floor 2 h per degC (max 6 h), radiator 45 min (max 3 h).
    static uint32_t defaultLeadS(RoomPlan::Emitter e, int16_t shortfallCentiC) {
        const bool floor = e == RoomPlan::Emitter::floor;
        const uint32_t s = static_cast<uint32_t>(std::max<int16_t>(shortfallCentiC, 0));
        return std::min<uint32_t>(s * (floor ? 7200 : 2700) / 100, floor ? 21600 : 10800);
    }
    // The next rise of the program within 24 h, and the night before it.
    struct Rise {
        int64_t atUtc = 0, nightUtc = 0;   // nightUtc: the last drop before the rise (or now)
        int16_t fromCentiC = 0, toCentiC = 0;
        std::optional<int16_t> eveningCentiC; // before that drop, when it lies ahead
    };
    // Minute steps in local time from now (a DST change within 24 h shifts the result by 1 h).
    static std::optional<Rise> nextRise(const RoomSchedule& s, int64_t utc) {
        auto t = RoomSchedule::amsterdam(utc);
        auto previous = s.at(t);
        if (!previous) return std::nullopt;
        Rise r; r.nightUtc = utc;
        const int64_t minuteUtc = utc - utc % 60;
        for (int m = 1; m <= 1440; ++m) {
            if (++t.minute == 1440) { t.minute = 0; t.weekday = uint8_t((t.weekday + 1) % 7); }
            const auto now = s.at(t);
            if (*now < *previous) { r.nightUtc = minuteUtc + m * 60; r.eveningCentiC = previous; }
            if (*now > *previous) { r.atUtc = minuteUtc + m * 60; r.fromCentiC = *previous; r.toCentiC = *now; return r; }
            previous = now;
        }
        return std::nullopt;
    }

    struct Start {
        const char* reason = "no_schedule"; // planned / no_rise_within_24h / no_schedule
        Rise rise;
        int64_t startUtc = 0;
        uint32_t leadS = 0;
        int16_t startTemperatureCentiC = 0;
        uint8_t flowC = 0;
        const char* confidence = "default";  // learned / default
        bool reachable = true, startNow = false;
    };
    // When heating must start, at the lowest acceptable flow, to reach the next
    // higher setpoint AT its switch time. Cooling until then follows the learned
    // loss rate (with outdoor), else the room is assumed at the night setpoint.
    static Start optimumStart(const FlowLearner& l, size_t room, const RoomSchedule& s, int64_t utc,
                              std::optional<int16_t> temperature, std::optional<int16_t> outdoor) {
        Start out;
        if (room >= l.rooms() || s.empty()) return out;
        const auto rise = nextRise(s, utc);
        if (!rise) { out.reason = "no_rise_within_24h"; return out; }
        out.rise = *rise; out.reason = "planned";
        lead(l, room, *rise, rise->fromCentiC, temperature, utc, outdoor, l.heatModel(room).lossPerHour, out);
        out.startUtc = rise->atUtc - out.leadS;
        out.startNow = utc >= out.startUtc && utc < rise->atUtc;
        return out;
    }
    // The shortest lead (5 min steps) that covers the warm-up from the room
    // temperature at that start: an earlier start is warmer, so the need falls
    // while the lead grows. Learned lowest acceptable flow, else the default lead.
    static void lead(const FlowLearner& l, size_t room, const Rise& rise, int16_t nightCentiC, std::optional<int16_t> temperature,
                     int64_t utc, std::optional<int16_t> outdoor, std::optional<float> loss, Start& out) {
        for (uint32_t lead = 0;; lead += 300) {
            const int64_t start = std::max(utc, rise.atUtc - int64_t(lead));
            out.startTemperatureCentiC = cooled(nightCentiC, temperature, rise.eveningCentiC, rise.nightUtc, utc, start, loss, outdoor);
            const int16_t shortfall = static_cast<int16_t>(rise.toCentiC - out.startTemperatureCentiC);
            const auto a = l.advise(room, shortfall, outdoor);
            uint32_t need;
            if (a.flowC) {
                out.confidence = "learned"; out.flowC = *a.flowC;
                out.reachable = a.reason[0] == 'l'; // learned / lowest_learned
                need = std::min(a.warmupS.value_or(maxLeadS), maxLeadS);
            } else {
                out.confidence = "default"; out.flowC = l.ruleFlow(shortfall);
                need = defaultLeadS(l.emitter(room), shortfall);
            }
            if (need <= lead || lead >= maxLeadS) { out.leadS = lead; return; }
            if (start == utc) { out.leadS = need; out.reachable = false; return; } // too late already
        }
    }

    struct Strategy {
        const char* name = "";
        int16_t nightCentiC = 0;
        float kwh = 0, m3 = 0;          // gas
        std::optional<float> eur;
        int16_t endCentiC = 0;          // at the switch time
        bool onTime = false;
    };
    struct Night {
        const char* reason = "no_schedule"; // estimated / not_learned / outdoor_unknown / ...
        Rise rise;
        std::array<Strategy, 4> strategies{};
        uint8_t count = 0, best = 0;
        float savingM3 = 0;             // best against the program's own setback
        std::optional<float> savingEur;
        const char* confidence = "low"; // low: nominal boiler power; calibrated: gas meter
    };
    // Tonight: the program's setback with optimum start, holding 0.5 / 1 degC
    // higher, and the tado-like start at the switch time with the rule flow,
    // each from the night start (or now) to 6 h after the switch. Energy: free
    // cooling costs nothing; holding costs UA (T - Tout); warming costs
    // C dT + UA (T - Tout); gas = heat / efficiency(flow - return drop).
    // Lumped single-room model of the house; constant outdoor; no comfort cost.
    static Night night(const FlowLearner& l, size_t room, const RoomSchedule& s, int64_t utc,
                       std::optional<int16_t> temperature, std::optional<int16_t> outdoor) {
        Night out;
        if (room >= l.rooms() || s.empty()) return out;
        const auto rise = nextRise(s, utc);
        if (!rise) { out.reason = "no_rise_within_24h"; return out; }
        out.rise = *rise;
        const auto m = l.heatModel(room);
        if (!outdoor) { out.reason = "outdoor_unknown"; return out; }
        if (std::string(l.readiness(room)) != "ready" || !m.capacityKwhPerK) { out.reason = "not_learned"; return out; }
        out.reason = "estimated";
        out.confidence = l.gasIntervals() >= 3 ? "calibrated" : "low";
        const auto add = [&](const char* name, int16_t night, bool atSwitch) {
            if (night >= rise->toCentiC) return;
            auto& st = out.strategies[out.count++];
            st.name = name; st.nightCentiC = night;
            simulate(l, room, *rise, utc, temperature, *outdoor, *m.lossPerHour, *m.capacityKwhPerK, atSwitch, st);
            if (l.price()) st.eur = st.m3 * *l.price();
        };
        add("program", rise->fromCentiC, false);
        add("hold_0_5", static_cast<int16_t>(rise->fromCentiC + 50), false);
        add("hold_1_0", static_cast<int16_t>(rise->fromCentiC + 100), false);
        add("tado_like", rise->fromCentiC, true);
        bool found = false;
        for (uint8_t i = 0; i < out.count; ++i) {
            const auto& st = out.strategies[i];
            if (st.onTime && (!found || st.m3 < out.strategies[out.best].m3)) { out.best = i; found = true; }
        }
        if (!found) { out.reason = "none_on_time"; return out; }
        out.savingM3 = out.strategies[0].m3 - out.strategies[out.best].m3;
        // Within the model's noise the program stays: at least 0.05 m3 and 2 %.
        if (out.strategies[0].onTime && out.savingM3 < std::max(0.05f, 0.02f * out.strategies[0].m3)) { out.best = 0; out.savingM3 = 0; }
        if (l.price()) out.savingEur = out.savingM3 * *l.price();
        return out;
    }

    // {"rooms":[{"id":..,"optimum_start":{..},"night":{..}}]}; temperatures per plan room.
    static cJSON* json(const FlowLearner& l, const RoomPlan& plan, int64_t utc,
                       const std::optional<int16_t>* temperatures, std::optional<int16_t> outdoor) {
        cJSON* root = cJSON_CreateObject();
        cJSON* rooms = root ? cJSON_AddArrayToObject(root, "rooms") : nullptr;
        if (!rooms) { cJSON_Delete(root); return nullptr; }
        for (size_t i = 0; i < plan.rooms.size() && i < l.rooms(); ++i) {
            cJSON* o = roomJson(l, plan, i, utc, temperatures[i], outdoor);
            if (!o || !cJSON_AddItemToArray(rooms, o)) { cJSON_Delete(o); cJSON_Delete(root); return nullptr; }
        }
        return root;
    }

    // One plan room of json(): {"id":..,"optimum_start":{..},"night":{..}}; nullptr: no memory.
    static cJSON* roomJson(const FlowLearner& l, const RoomPlan& plan, size_t i, int64_t utc,
                           std::optional<int16_t> temperature, std::optional<int16_t> outdoor) {
        if (i >= plan.rooms.size() || i >= l.rooms()) return nullptr;
        cJSON* o = cJSON_CreateObject();
        cJSON* st = o ? cJSON_AddObjectToObject(o, "optimum_start") : nullptr;
        cJSON* ni = st ? cJSON_AddObjectToObject(o, "night") : nullptr;
        if (!ni) { cJSON_Delete(o); return nullptr; }
        cJSON_AddStringToObject(o, "id", plan.rooms[i].id.c_str());
        const auto& schedule = plan.rooms[i].schedule;
        const auto start = optimumStart(l, i, schedule, utc, temperature, outdoor);
        cJSON_AddStringToObject(st, "reason", start.reason);
        if (start.reason[0] == 'p') {
            riseJson(st, start.rise);
            local(st, "predicted_start", start.startUtc);
            cJSON_AddNumberToObject(st, "predicted_start_utc", double(start.startUtc));
            cJSON_AddNumberToObject(st, "lead_minutes", (start.leadS + 30) / 60);
            FlowLearner::number(st, "start_temperature_c", start.startTemperatureCentiC / 100.0f, 100);
            cJSON_AddNumberToObject(st, "flow_c", start.flowC);
            cJSON_AddStringToObject(st, "confidence", start.confidence);
            cJSON_AddBoolToObject(st, "reachable", start.reachable);
            cJSON_AddBoolToObject(st, "start_now", start.startNow);
        }
        const auto n = night(l, i, schedule, utc, temperature, outdoor);
        cJSON_AddStringToObject(ni, "reason", n.reason);
        if (!n.count) return o;
        cJSON_AddStringToObject(ni, "confidence", n.confidence);
        cJSON* list = cJSON_AddArrayToObject(ni, "strategies");
        for (uint8_t k = 0; list && k < n.count; ++k) {
            const auto& s = n.strategies[k];
            cJSON* so = cJSON_CreateObject();
            if (!so || !cJSON_AddItemToArray(list, so)) { cJSON_Delete(so); break; }
            cJSON_AddStringToObject(so, "name", s.name);
            FlowLearner::number(so, "night_c", s.nightCentiC / 100.0f, 100);
            FlowLearner::number(so, "kwh", s.kwh, 100);
            FlowLearner::number(so, "m3", s.m3, 1000);
            FlowLearner::number(so, "eur", s.eur, 100);
            FlowLearner::number(so, "end_c", s.endCentiC / 100.0f, 100);
            cJSON_AddBoolToObject(so, "on_time", s.onTime);
        }
        if (n.reason[0] == 'e') {
            cJSON_AddStringToObject(ni, "recommended", n.strategies[n.best].name);
            FlowLearner::number(ni, "recommended_night_c", n.strategies[n.best].nightCentiC / 100.0f, 100);
            FlowLearner::number(ni, "saving_m3", n.savingM3, 1000);
            FlowLearner::number(ni, "saving_eur", n.savingEur, 100);
        }
        return o;
    }

private:
    // Room temperature at `at`: free cooling from the evening/now value with the
    // learned loss rate, floored at the night setpoint; without a loss model the
    // conservative night setpoint (or a colder current reading).
    static int16_t cooled(int16_t night, std::optional<int16_t> now, std::optional<int16_t> evening, int64_t nightUtc,
                          int64_t utc, int64_t at, std::optional<float> loss, std::optional<int16_t> outdoor) {
        const bool ahead = nightUtc > utc && evening;
        const int16_t from = ahead ? *evening : now.value_or(night);
        if (from <= night) return from;
        if (!loss || !outdoor) return night;
        const double h = std::max<int64_t>(0, at - (ahead ? nightUtc : utc)) / 3600.0;
        const double t = *outdoor + (from - *outdoor) * std::exp(-*loss * h);
        return static_cast<int16_t>(std::max<double>(night, std::lround(t)));
    }
    // 5-minute steps from the night start (or now) to the switch time.
    static void simulate(const FlowLearner& l, size_t room, const Rise& rise, int64_t utc, std::optional<int16_t> now,
                         int16_t outdoorCentiC, float b, float capacity, bool atSwitch, Strategy& st) {
        const auto& p = l.params();
        const bool ahead = rise.nightUtc > utc && rise.eveningCentiC;
        const int64_t from = ahead ? rise.nightUtc : utc;
        double T = (ahead ? *rise.eveningCentiC : now.value_or(rise.fromCentiC)) / 100.0;
        const double To = outdoorCentiC / 100.0, ua = b * capacity, dt = 300 / 3600.0;
        // Recovery start: the optimum start towards this night setpoint, or the switch time.
        int64_t recovery = rise.atUtc;
        uint8_t recoveryFlow = l.ruleFlow(static_cast<int16_t>(rise.toCentiC - st.nightCentiC));
        if (!atSwitch) {
            Start s;
            lead(l, room, rise, st.nightCentiC, now, utc, outdoorCentiC, b, s);
            recovery = rise.atUtc - s.leadS; recoveryFlow = s.flowC;
        }
        const auto holdFlow = l.advise(room, 0, outdoorCentiC).flowC.value_or(l.ruleFlow(0));
        double gas = 0; // kWh
        st.endCentiC = INT16_MIN;
        // Until compareS after the switch, so a late (tado-like) recovery is counted too.
        for (int64_t t = from; t < rise.atUtc + compareS; t += 300) {
            if (t >= rise.atUtc && st.endCentiC == INT16_MIN) st.endCentiC = static_cast<int16_t>(std::lround(T * 100));
            const bool recovering = t >= recovery;
            const double target = (recovering ? rise.toCentiC : st.nightCentiC) / 100.0;
            if (T < target - 0.02) {
                const uint8_t flow = recovering ? recoveryFlow
                    : l.advise(room, static_cast<int16_t>(std::lround((target - T) * 100)), outdoorCentiC).flowC.value_or(recoveryFlow);
                const double rate = std::max(0.0f, l.rate(room, flow, outdoorCentiC).value_or(0.0f));
                const double rise1 = std::min(rate * dt, target - T);
                const double q = capacity * rise1 + ua * (T - To) * dt;
                gas += q / FlowLearner::efficiency(flow - p.returnDropK);
                T += rise1;
            } else if (T > target + 0.02) {
                T = std::max(target, To + (T - To) * std::exp(-b * dt));
            } else {
                const double q = ua * (target - To) * dt;
                gas += q / FlowLearner::efficiency(holdFlow - p.returnDropK);
                T = target;
            }
        }
        st.kwh = static_cast<float>(gas); st.m3 = static_cast<float>(gas / p.kwhPerM3);
        st.onTime = st.endCentiC >= rise.toCentiC - 20;
    }
    static void riseJson(cJSON* o, const Rise& r) {
        cJSON* n = cJSON_AddObjectToObject(o, "next_switch");
        if (!n) return;
        local(n, "time", r.atUtc);
        cJSON_AddNumberToObject(n, "utc", double(r.atUtc));
        FlowLearner::number(n, "from_c", r.fromCentiC / 100.0f, 100);
        FlowLearner::number(n, "target_c", r.toCentiC / 100.0f, 100);
    }
    static void local(cJSON* o, const char* key, int64_t utc) {
        static constexpr const char* days[7] = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"};
        const auto t = RoomSchedule::amsterdam(utc);
        char text[12];
        std::snprintf(text, sizeof text, "%s %02u:%02u", days[t.weekday % 7], unsigned(t.minute / 60), unsigned(t.minute % 60));
        cJSON_AddStringToObject(o, key, text);
    }
};
}
