#pragma once
#include "EMS/UBAMonitorFastPlus.h"
#include "EMS/UBAMonitorWWPlus.h"
#include "EMS/UBAOutdoorTemp.h"
#include "EMS/UBAFactory.h"
#include "EMS/EmsMetricTotals.h"
#include <TimeHelpers.h>

#include <functional>
#include <mutex>
#include <ostream>
#include <tuple>

namespace heating::ems {

class EmsMetrics {
public:
    using registerProcessorFunc_t = std::function<void(uint16_t, std::function<void(EmsTelegram const&)>)>;
    using clock_t = std::function<uint64_t()>;

    explicit EmsMetrics(registerProcessorFunc_t registerProcessor,
                        clock_t clock = [] { return ib::getTimeMillis(); }) : clock_(std::move(clock)) {
        registerProcessor(UBAMonitorFastPlus::predefinedTypeId, [this](EmsTelegram const& t) {
            if (!admitted(t)) return;
            const auto now = clock_();
            std::lock_guard<std::mutex> lock(mutex_);
            // Interpret the real telegram bytes, without downcasting a base object.
            if (auto b = t.byteAt(10)) totals_.power(now, *b);
            if (auto b = t.byteAt(11)) {
                totals_.modes(now, (*b & 4) == 0 && (*b & 2) != 0,
                              (*b & 1) != 0 && (*b & 4) != 0, (*b & 1) != 0);
            }
        });
        registerProcessor(UBAMonitorWWPlus::predefinedTypeId, [this](EmsTelegram const& t) {
            if (!admitted(t)) return;
            if (auto b = t.byteAt(11)) {
                std::lock_guard<std::mutex> lock(mutex_);
                totals_.flow(clock_(), *b);
            }
        });
        registerProcessor(UBAOutdoorTemp::predefinedTypeId, [this](EmsTelegram const& t) {
            if (!admitted(t)) return;
            if (auto value = t.wordAt(0)) {
                std::lock_guard<std::mutex> lock(mutex_);
                auto signedValue = static_cast<int16_t>(*value);
                outdoorTemperature_ = *value != 0x8000 && *value != 0x7FFF
                    && signedValue >= -600 && signedValue <= 600
                    ? std::optional<double>(signedValue / 10.0) : std::nullopt;
                outdoorObserved_ = clock_();
            }
        });
        registerProcessor(UBAFactory::predefinedTypeId, [this](EmsTelegram const& t) {
            if (!admitted(t)) return;
            if (auto b = t.byteAt(4)) {
                std::lock_guard<std::mutex> lock(mutex_);
                totals_.nominal(clock_(), *b);
            }
        });
    }

    std::tuple<double, double, double> getGasBurnedKwh() {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto s = totals_.snapshot(clock_());
        return {s.energyKwh, s.heatingKwh, s.dhwKwh};
    }
    std::tuple<double, double> getWarmWaterUsage() {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto s = totals_.snapshot(clock_());
        return {s.waterLitres, s.averageFlow.value_or(0)};
    }
    std::optional<double> getOutdoorTemperature() {
        std::lock_guard<std::mutex> lock(mutex_);
        return outdoor(clock_());
    }

    void getMetrics(std::ostream& ss) {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto now = clock_();
        const auto s = totals_.snapshot(now);
        ss << "{\"metricsSchema\":2,\"counterScope\":\"boot\","
              "\"energyQuality\":\"estimated_nominal_modulation\","
              "\"protocolScope\":\"plus\",\"flowQuality\":\"reported_integrated\","
              "\"totalEnergyUsedKwh\":";
        number(ss, s.energyObserved ? std::optional<double>(s.energyKwh) : std::nullopt);
        ss << ",\"heatingEnergyUsedKwh\":";
        number(ss, s.energyObserved ? std::optional<double>(s.heatingKwh) : std::nullopt);
        ss << ",\"warmWaterEnergyUsedKwh\":";
        number(ss, s.energyObserved ? std::optional<double>(s.dhwKwh) : std::nullopt);
        ss << ",\"unattributedEnergyUsedKwh\":";
        number(ss, s.energyObserved ? std::optional<double>(s.unattributedKwh) : std::nullopt);
        ss << ",\"warmWaterUsage\":";
        number(ss, s.flowObserved ? std::optional<double>(s.waterLitres) : std::nullopt);
        ss << ",\"warmWaterAvgFlow\":"; number(ss, s.averageFlow);
        ss << ",\"warmWaterFlow\":"; number(ss, s.currentFlow);
        ss << ",\"observedBurnerSeconds\":";
        number(ss, s.burnerObserved ? std::optional<double>(s.burnerSeconds) : std::nullopt);
        ss << ",\"powerFresh\":" << (s.powerFresh ? "true" : "false");
        ss << ",\"outdoorTemperature\":"; number(ss, outdoor(now));
        ss << "}";
    }

private:
    static bool admitted(const EmsTelegram& t) {
        return t.getSenderId() == 8 && t.dataSize()
            && t.getOperationType() != EmsTelegram::READ
            && t.getOperationType() != EmsTelegram::READ_WITH_DATA;
    }
    static void number(std::ostream& ss, std::optional<double> value) {
        if (value) ss << *value; else ss << "null";
    }
    std::optional<double> outdoor(uint64_t now) const {
        return now >= outdoorObserved_ && now - outdoorObserved_ < 180000
            ? outdoorTemperature_ : std::nullopt;
    }
    std::mutex mutex_;
    clock_t clock_;
    EmsMetricTotals totals_;
    std::optional<double> outdoorTemperature_;
    uint64_t outdoorObserved_ = 0;
};
}
