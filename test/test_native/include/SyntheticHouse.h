#pragma once
#include "control/FlowLearner.h"
#include "control/RoomPlan.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

// rc.5 (P2): a synthetic house whose answers are known, for HouseModel and Knowledge. Each room warms
// at a (flow - room) - b (room - outdoor) degC/h and takes C a (flow - room) kW, so the boiler gives
// k = sum C a kW per K of flow above the rooms, room i sees the house's heat loss as b_i k / a_i and
// its weather curve slope is b_i / a_i. Even rooms are floors (a 0.035, b 0.02, C 5, coasting 1.5 h),
// odd rooms radiators (0.1, 0.05, 1.5, 0.2 h). learn() gives every room ready flow bins (36, 44 and
// 52 degC, from just below 20 degC: the room the house model assumes), cooling and power segments.
struct SyntheticHouse {
    struct Room { double a, b, c, coastHours; double t = 20, coast = 0; heating::control::RoomPlan::Emitter emitter; };
    static constexpr uint64_t second = 1000, minute = 60000, hour = 3600000;
    std::vector<Room> rooms;
    heating::control::RoomPlan plan;
    heating::control::FlowLearner learner;
    uint64_t now = 0;
    double outdoor = 5;
    bool modulation = true, outdoorKnown = true;
    explicit SyntheticHouse(size_t count, size_t idBytes = 0) {
        using heating::control::RoomPlan;
        for (size_t i = 0; i < count; ++i) {
            rooms.push_back(i % 2 ? Room{0.1, 0.05, 1.5, 0.2, 20, 0, RoomPlan::Emitter::radiator} : Room{0.035, 0.02, 5, 1.5, 20, 0, RoomPlan::Emitter::floor});
            RoomPlan::Room r;
            r.id = r.name = "room" + std::to_string(i);
            if (r.id.size() < idBytes) r.id.resize(idBytes, 'x');
            r.state = heating::control::RoomDemand::State::active; r.emitter = rooms.back().emitter;
            plan.rooms.push_back(r);
        }
        learner.setPlan(plan);
    }
    double k() const { double s = 0; for (const auto& r : rooms) s += r.c * r.a; return s; }
    void run(uint64_t ms, std::optional<double> flowC) {
        using heating::control::FlowLearner;
        for (uint64_t t = 0; t < ms; t += 10 * second) {
            now += 10 * second;
            const double dt = 10.0 / 3600;
            double heatKw = 0;
            for (auto& r : rooms) {
                const double emit = flowC ? r.a * (*flowC - r.t) : 0;
                if (flowC) r.coast = emit; else r.coast *= std::exp(-dt / r.coastHours);
                r.t += (flowC ? emit : r.coast) * dt - r.b * (r.t - outdoor) * dt;
                heatKw += r.c * emit;
            }
            FlowLearner::Boiler b;
            const double flow = flowC ? *flowC + ((now / (5 * minute)) % 2 ? 0.5 : -0.5) : rooms[0].t + 3;
            b.flowCentiC = int16_t(std::lround(flow * 100)); b.returnCentiC = int16_t(std::lround((flow - 5) * 100));
            b.burnerOn = flowC.has_value(); b.hotWater = false;
            b.requestedFlowC = flowC ? uint8_t(*flowC) : uint8_t(0);
            if (outdoorKnown) b.outdoorCentiC = int16_t(std::lround(outdoor * 100));
            if (modulation) b.modulationPct = uint8_t(std::clamp(std::lround(heatKw / FlowLearner::efficiency(flow - 5) / 22 * 100), 0L, 100L));
            std::vector<FlowLearner::RoomInput> in(rooms.size());
            for (size_t i = 0; i < rooms.size(); ++i) {
                in[i].temperatureCentiC = int16_t(std::lround(rooms[i].t * 100));
                in[i].setpointCentiC = 2100; in[i].source = 0;
            }
            learner.sample(now, b, in.data(), in.size());
        }
    }
    // Hour-long heating runs from just below 20 degC, each followed by 8 h off.
    void learn() {
        for (int c = 0; c < 3; ++c)
            for (const double o : {0.0, 10.0})
                for (const double f : {36.0, 44.0, 52.0}) {
                    outdoor = o;
                    for (auto& r : rooms) r.t = 19.6;
                    run(60 * minute, f); run(8 * hour, std::nullopt);
                }
        outdoor = 5;
    }
};
