#pragma once

#include "BoilerCapabilities.h"
#include "BoilerProfile.h"
#include "BoilerTelegramInventory.h"
#include "EmsTelegram.h"
#include <array>
#include <algorithm>
#include <cstdint>
#include <optional>
#include <ostream>

namespace heating::ems {

enum class BoilerField : size_t {
    selectedFlow, flow, returnTemp, outdoor, modulation, requestedPowerLimit,
    pressure, rawBurner, rawPump, rawFan, rawState, heatingActive, dhwActive,
    selectedDhw, dhwTemp, dhwFlow, heatingEnabled, dhwEnabled,
    burnerStarts, burnerMinutes, heatingMinutes, heatingStarts, dhwMinutes, dhwStarts,
    displayCode, serviceNumber, maxBurnerPower, pumpRunOn, heatingLimit, monitorDhwTarget,
    storageTemp1, storageTemp2, ionisationCurrent, rawSecondBurner, rawIgnition,
    rawOilPreheat, rawDhwValve, rawDhwCirculation,
    boilerTemp, exhaustTemp, switchTemp, pumpModulation, secondBurnerMinutes,
    hysteresisOff, hysteresisOn, minimumBurnerPeriod, pumpMaximum, pumpMinimum,
    pumpMode, secondaryHysteresisOff, secondaryHysteresisOn, pumpStartTemp,
    dhwHysteresisOn, dhwChargeOptimisation, dhwFlowOffset, dhwCirculationEnabled,
    dhwCirculationMode, dhwDisinfectionTemp, dhwChargeType, dhwComfortMode,
    dhwTemp2, dhwSolarTemp, dhwType, rawDhwOneTime, rawDhwDisinfection,
    rawDhwCharging, rawDhwRecharging, rawDhwTempOk, rawDhwActive, count
};
enum class BoilerQuality { reported, unreliable, inferred };

// One boiler field: name, unit, raw divisor and lifetime. ttlMs: how long a value the boiler sends on its
// own (status, measurements, counters) stays valid after it arrived. requestOnlyTtlMs (ttlMs 0) marks a
// request-only setting: the boiler sends 0x16 UBAParameters and 0x33 UBAParameterWW only when a
// controller asks for them (the E32 reads 0x16 at boot and every 6 h, EMS/BoilerLimitRead.h), so the last
// value read this boot stays valid until a newer report replaces it; it never expires (rc.5, owner: show
// such values, with a remark); so do their EMS+ twins (EmsEntityTable.h requestOnlyTtl). The E32 pages'
// JSON marks it "request_only":true (writeJSON); the MQTT rows are unchanged. Home Assistant mirrors the
// catalog (boiler_fields.py FIELDS: TTL REQUEST_ONLY; its test reads these rows, the marker must name "request").
inline constexpr uint32_t requestOnlyTtlMs = 0;
struct BoilerFieldSpec {
    const char *name; const char *unit; int divisor; uint32_t ttlMs;
    constexpr bool requestOnly() const { return ttlMs == requestOnlyTtlMs; }
    // Whether a value that arrived at observedMs is still valid at now (never before it arrived).
    constexpr bool fresh(uint64_t observedMs, uint64_t now) const {
        return now >= observedMs && (requestOnly() || now - observedMs < ttlMs);
    }
};
inline constexpr std::array<BoilerFieldSpec, static_cast<size_t>(BoilerField::count)> boilerFieldSpecs{{
    {"reported_selected_flow_temperature", "degC", 100, 30000},
    {"measured_flow_temperature", "degC", 100, 30000},
    {"measured_return_temperature", "degC", 100, 30000},
    {"outdoor_temperature", "degC", 100, 180000},
    {"reported_burner_modulation", "%", 1, 30000},
    {"reported_requested_power_limit", "%", 1, 30000},
    {"pressure", "bar", 10, 30000},
    {"raw_burner_bit", "bool", 1, 30000},
    {"raw_pump_bit", "bool", 1, 30000},
    {"raw_fan_bit", "bool", 1, 30000},
    {"raw_boiler_state", "bits", 1, 30000},
    {"heating_active", "bool", 1, 30000},
    {"dhw_active", "bool", 1, 30000},
    {"selected_dhw_temperature", "degC", 100, requestOnlyTtlMs},
    {"measured_dhw_temperature", "degC", 100, 30000},
    {"dhw_flow", "L/min", 10, 30000},
    {"heating_enabled", "bool", 1, requestOnlyTtlMs},
    {"dhw_enabled", "bool", 1, requestOnlyTtlMs},
    {"reported_burner_starts", "starts", 1, 180000},
    {"reported_burner_runtime", "min", 1, 180000},
    {"reported_heating_runtime", "min", 1, 180000},
    {"reported_heating_starts", "starts", 1, 180000},
    {"reported_dhw_runtime", "min", 1, 30000},
    {"reported_dhw_starts", "starts", 1, 30000},
    {"display_code", "text", 1, 30000},
    {"service_number", "code", 1, 30000},
    {"maximum_burner_power", "%", 1, requestOnlyTtlMs},
    {"pump_run_on", "min", 1, requestOnlyTtlMs},
    {"configured_heating_temperature", "degC", 100, requestOnlyTtlMs},
    {"reported_dhw_target", "degC", 100, 30000},
    {"storage_temperature_1", "degC", 100, 30000},
    {"storage_temperature_2", "degC", 100, 30000},
    {"ionisation_current", "uA", 10, 30000},
    {"raw_second_burner_bit", "bool", 1, 30000},
    {"raw_ignition_bit", "bool", 1, 30000},
    {"raw_oil_preheat_bit", "bool", 1, 30000},
    {"raw_dhw_valve_bit", "bool", 1, 30000},
    {"raw_dhw_circulation_bit", "bool", 1, 30000},
    {"boiler_temperature", "degC", 100, 180000},
    {"exhaust_temperature", "degC", 100, 180000},
    {"hydraulic_switch_temperature", "degC", 100, 180000},
    {"reported_heating_pump_modulation", "%", 1, 180000},
    {"reported_second_burner_runtime", "min", 1, 180000},
    {"heating_hysteresis_off", "K", 1, requestOnlyTtlMs},
    {"heating_hysteresis_on", "K", 1, requestOnlyTtlMs},
    {"minimum_burner_period", "min", 1, requestOnlyTtlMs},
    {"pump_modulation_maximum", "%", 1, requestOnlyTtlMs},
    {"pump_modulation_minimum", "%", 1, requestOnlyTtlMs},
    {"configured_pump_mode", "code", 1, requestOnlyTtlMs},
    {"secondary_heating_hysteresis_off", "K", 1, requestOnlyTtlMs},
    {"secondary_heating_hysteresis_on", "K", 1, requestOnlyTtlMs},
    {"pump_start_temperature", "degC", 100, requestOnlyTtlMs},
    {"dhw_hysteresis_on", "K", 1, requestOnlyTtlMs},
    {"dhw_charge_optimisation_enabled", "bool", 1, requestOnlyTtlMs},
    {"dhw_flow_temperature_offset", "K", 1, requestOnlyTtlMs},
    {"dhw_circulation_enabled", "bool", 1, requestOnlyTtlMs},
    {"configured_dhw_circulation_mode", "code", 1, requestOnlyTtlMs},
    {"dhw_disinfection_temperature", "degC", 100, requestOnlyTtlMs},
    {"configured_dhw_charge_type", "code", 1, requestOnlyTtlMs},
    {"configured_dhw_comfort_mode", "code", 1, requestOnlyTtlMs},
    {"secondary_dhw_temperature", "degC", 100, 30000},
    {"solar_dhw_temperature", "degC", 100, 30000},
    {"reported_dhw_type", "code", 1, 30000},
    {"raw_dhw_one_time_bit", "bool", 1, 30000},
    {"raw_dhw_disinfection_bit", "bool", 1, 30000},
    {"raw_dhw_charging_bit", "bool", 1, 30000},
    {"raw_dhw_recharging_bit", "bool", 1, 30000},
    {"raw_dhw_temperature_ok_bit", "bool", 1, 30000},
    {"raw_dhw_active_bit", "bool", 1, 30000}
}};

struct BoilerSample {
    std::optional<int32_t> raw;
    uint64_t observedMs = 0;
    uint16_t sourceType = 0;
    BoilerQuality quality = BoilerQuality::reported;
    bool observed = false;
    // Against a lifetime of the caller's own (a trial's settings window, a live check).
    bool fresh(uint64_t now, uint32_t ttl) const {
        return observed && now >= observedMs && now - observedMs < ttl;
    }
    // Against the field's catalog lifetime: a request-only setting stays valid once it arrived.
    bool fresh(uint64_t now, const BoilerFieldSpec &spec) const { return observed && spec.fresh(observedMs, now); }
};

// Independent implementation from documented wire offsets. No copied EMS-ESP code.
// Stored numeric temperatures are hundredths Celsius; publication applies specs.
class ClassicBoilerMonitor {
public:
    const BoilerCapabilities &capabilities() const { return capabilities_; }
    // The boiler profile this monitor reports its field verdicts to (same owner and lock).
    void attachProfile(BoilerProfile* profile) { profile_ = profile; }
    const BoilerSample &sample(BoilerField f) const { return samples_[index(f)]; }
    // A field the boiler profile calls left empty (BoilerProfile::leftEmpty): its
    // 0 is no value. sample() keeps the raw bytes for the attended test.
    bool notReported(size_t field) const { return profile_ && profile_->leftEmpty(field); }
    std::optional<int32_t> value(BoilerField f, uint64_t now, bool allowUnreliable = false) const {
        const auto &s = sample(f);
        if (!s.fresh(now, boilerFieldSpecs[index(f)]) || notReported(index(f)) ||
            (!allowUnreliable && s.quality == BoilerQuality::unreliable)) return {};
        return s.raw;
    }

    bool receive(const EmsTelegram &t, uint64_t now) {
        if (t.getSenderId() != 0x08 || t.dataSize() == 0 ||
            t.getOperationType() == EmsTelegram::READ ||
            t.getOperationType() == EmsTelegram::READ_WITH_DATA) return false;
        telegrams_.observe(t.getTypeId(), t.getOffset(), t.dataSize(), now);
        const auto family = BoilerCapabilities::family(t.getTypeId());
        if (family == BoilerProtocol::unknown) return false;
        // Counts decoded boiler reports, never polls, CRC failures or our own
        // requests. A frame need not contain a complete usable measurement.
        if (reportCount_ != UINT64_MAX) ++reportCount_;
        lastReportMs_ = std::max(lastReportMs_, now);
        capabilities_.observe(t.getTypeId());
        if (profile_) profile_->observeFamily(family, now);
        if (family != BoilerProtocol::classic) return false; // Plus processors remain intact.
        // What a 0 of a field tells the boiler profile: a value; nothing (an
        // unreliable field, or a default an idle boiler reports as well); or that
        // the byte is left empty, because this same frame shows the activity the
        // field reports (Zero::unfilled, chosen per frame by activity() below).
        enum class Zero : uint8_t { value, nothing, unfilled };
        const auto put = [&](BoilerField field, std::optional<int32_t> v,
                             BoilerQuality quality = BoilerQuality::reported, Zero zero = Zero::value) {
            // Boiler profile: the decoder's own verdict, every frame.
            if (quality == BoilerQuality::unreliable && zero == Zero::value) zero = Zero::nothing;
            if (profile_) profile_->observe(index(field), !v ? FieldEvidence::absent
                : *v != 0 || zero == Zero::value ? FieldEvidence::value
                : zero == Zero::nothing ? FieldEvidence::inconclusive : FieldEvidence::unfilled, now);
            auto& current=samples_[index(field)];
            if(current.observed&&now<=current.observedMs) {
                // Packet order is not acquisition order. Keep the newest fact
                // per FIELD, so an older partial can still fill missing fields.
                // Same-time contradictions retire this field until a strictly
                // newer report; replaying either cached value cannot repair it.
                if(now==current.observedMs&&(current.raw!=v||current.quality!=quality
                    ||current.sourceType!=t.getTypeId()))current.raw.reset();
                return;
            }
            current = {v, now, t.getTypeId(), quality, true};
        };
        const auto byte = [&](BoilerField f, uint8_t offset, int scale = 1, int maximum = 254, Zero zero = Zero::value) {
            if (auto b = t.byteAt(offset)) put(f, *b <= maximum ? std::optional<int32_t>(*b * scale) : std::nullopt,
                BoilerQuality::reported, zero);
        };
        const auto temp = [&](BoilerField f, uint8_t offset, bool signedValue = false, int maximum = 1300) {
            if (auto w = t.wordAt(offset)) {
                const int32_t v = signedValue ? static_cast<int16_t>(*w) : *w;
                put(f, *w != 0x8000 && *w != 0x7FFF && v >= -600 && v <= maximum
                    ? std::optional<int32_t>(v * 10) : std::nullopt);
            }
        };
        const auto counter = [&](BoilerField f, uint8_t offset) {
            // Present on the wire, but historically stationary on this Classic chain.
            if (auto c = t.counterAt(offset)) put(f, *c != 0xFFFFFF ? std::optional<int32_t>(*c) : std::nullopt,
                BoilerQuality::unreliable);
        };
        const auto enabled = [&](BoilerField f, uint8_t offset) {
            if (auto b = t.byteAt(offset)) put(f, (*b == 0 || *b == 0xFF)
                ? std::optional<int32_t>(*b == 0xFF) : std::nullopt);
        };
        const auto signedByte = [&](BoilerField f, uint8_t offset) {
            if (auto b = t.byteAt(offset)) put(f, *b == 0x7F ? std::nullopt
                : std::optional<int32_t>(*b < 128 ? int(*b) : int(*b) - 256));
        };
        const auto rawBit = [&](BoilerField f, uint8_t offset, uint8_t mask, Zero zero = Zero::nothing) {
            if (auto b = t.byteAt(offset)) put(f, (*b & mask) != 0, BoilerQuality::unreliable, zero);
        };
        const auto activity = [](bool active) { return active ? Zero::unfilled : Zero::nothing; };
        switch (t.getTypeId()) {
            case 0x18: {
                // The activity this frame itself reports (modulation byte 4, state
                // byte 5): a field that reports the same activity cannot read 0
                // then. A partial frame without those bytes shows no activity.
                const auto power = t.byteAt(4), stateByte = t.byteAt(5);
                const bool firing = power && *power >= 1 && *power <= 100;
                const bool heating = stateByte && (*stateByte & 0x09) == 0x09;
                const bool hotWater = stateByte && (*stateByte & 0x0A) == 0x0A;
                // Selected flow 0 proves nothing while idle, but not while heating.
                byte(BoilerField::selectedFlow, 0, 100, 100, activity(heating));
                temp(BoilerField::flow, 1);
                byte(BoilerField::requestedPowerLimit, 3, 1, 100);
                byte(BoilerField::modulation, 4, 1, 100);
                if (auto state = t.byteAt(5)) {
                    // EMS adapter-reported state, not an independent flame sensor.
                    put(BoilerField::rawState, *state);
                    put(BoilerField::heatingActive, (*state & 0x09) == 0x09, BoilerQuality::inferred);
                    put(BoilerField::dhwActive, (*state & 0x0A) == 0x0A, BoilerQuality::inferred);
                }
                // Byte 7 flags. Conservative Classic profile: historically unreliable
                // on Mark's adapter (the EasyControl sends 00 while the burner fires).
                rawBit(BoilerField::rawBurner, 7, 0x01, activity(firing));
                rawBit(BoilerField::rawPump, 7, 0x20, activity(heating));
                rawBit(BoilerField::rawFan, 7, 0x04, activity(firing));
                rawBit(BoilerField::rawSecondBurner, 7, 0x02);
                rawBit(BoilerField::rawIgnition, 7, 0x08);
                rawBit(BoilerField::rawOilPreheat, 7, 0x10);
                rawBit(BoilerField::rawDhwValve, 7, 0x40, activity(hotWater));
                rawBit(BoilerField::rawDhwCirculation, 7, 0x80);
                temp(BoilerField::storageTemp1, 9);
                temp(BoilerField::storageTemp2, 11);
                temp(BoilerField::returnTemp, 13);
                if (auto current = t.wordAt(15)) put(BoilerField::ionisationCurrent,
                    *current != 0x7D00 && *current != 0x7FFF && *current != 0x8000
                    && *current != 0x8300 && *current != 0xFFFF
                        ? std::optional<int32_t>(*current) : std::nullopt);
                byte(BoilerField::pressure, 17);
                if (auto code = t.wordAt(18)) {
                    const auto a = *code >> 8, b = *code & 255;
                    put(BoilerField::displayCode, a >= 32 && a <= 126 && b >= 32 && b <= 126
                        ? std::optional<int32_t>(*code) : std::nullopt);
                }
                if (auto code = t.wordAt(20)) put(BoilerField::serviceNumber, *code != 0xFFFF
                    ? std::optional<int32_t>(*code) : std::nullopt);
                break;
            }
            case 0x19:
                temp(BoilerField::outdoor, 0, true);
                temp(BoilerField::boilerTemp, 2);
                temp(BoilerField::exhaustTemp, 4, false, 5000);
                temp(BoilerField::switchTemp, 25);
                byte(BoilerField::pumpModulation, 9, 1, 100);
                counter(BoilerField::burnerStarts, 10);
                counter(BoilerField::burnerMinutes, 13);
                counter(BoilerField::secondBurnerMinutes, 16);
                counter(BoilerField::heatingMinutes, 19);
                counter(BoilerField::heatingStarts, 22);
                break;
            case 0x16:
                enabled(BoilerField::heatingEnabled, 0);
                byte(BoilerField::heatingLimit, 1, 100, 130);
                byte(BoilerField::maxBurnerPower, 2, 1, 100);
                byte(BoilerField::pumpRunOn, 8);
                signedByte(BoilerField::hysteresisOff, 4);
                signedByte(BoilerField::hysteresisOn, 5);
                byte(BoilerField::minimumBurnerPeriod, 6);
                byte(BoilerField::pumpMaximum, 9, 1, 100);
                byte(BoilerField::pumpMinimum, 10, 1, 100);
                byte(BoilerField::pumpMode, 11);
                signedByte(BoilerField::secondaryHysteresisOff, 12);
                signedByte(BoilerField::secondaryHysteresisOn, 13);
                byte(BoilerField::pumpStartTemp, 23, 100, 130);
                break;
            case 0x33:
                enabled(BoilerField::dhwEnabled, 1);
                byte(BoilerField::selectedDhw, 2, 100, 100);
                signedByte(BoilerField::dhwHysteresisOn, 3);
                enabled(BoilerField::dhwChargeOptimisation, 4);
                byte(BoilerField::dhwFlowOffset, 5, 1, 100);
                enabled(BoilerField::dhwCirculationEnabled, 6);
                byte(BoilerField::dhwCirculationMode, 7);
                byte(BoilerField::dhwDisinfectionTemp, 8, 100, 100);
                if (auto mode = t.byteAt(9)) put(BoilerField::dhwComfortMode,
                    *mode == 0 || *mode == 0xD8 || *mode == 0xEC ? std::optional<int32_t>(*mode) : std::nullopt);
                if (auto charge = t.byteAt(10)) put(BoilerField::dhwChargeType, *charge & 1);
                break;
            case 0x34:
                byte(BoilerField::monitorDhwTarget, 0, 100, 100);
                temp(BoilerField::dhwTemp, 1);
                temp(BoilerField::dhwTemp2, 3);
                temp(BoilerField::dhwSolarTemp, 17);
                byte(BoilerField::dhwType, 8);
                rawBit(BoilerField::rawDhwOneTime, 5, 0x02);
                rawBit(BoilerField::rawDhwDisinfection, 5, 0x04);
                rawBit(BoilerField::rawDhwCharging, 5, 0x08);
                rawBit(BoilerField::rawDhwRecharging, 5, 0x10);
                rawBit(BoilerField::rawDhwTempOk, 5, 0x20);
                rawBit(BoilerField::rawDhwActive, 5, 0x40);
                if (auto flow = t.byteAt(9)) put(BoilerField::dhwFlow,
                    *flow != 0xFF ? std::optional<int32_t>(*flow) : std::nullopt, BoilerQuality::unreliable);
                counter(BoilerField::dhwMinutes, 10);
                counter(BoilerField::dhwStarts, 13);
                break;
        }
        return true;
    }

    // Compatibility projection for Home/About/legacy JSON consumers. Values
    // come from this same aged monitor, never a second Classic decoder/cache.
    void writeLegacyStatus(std::ostream& out,uint64_t now,bool closeObject=true) const {
        out<<"{\"protocolProfile\":\""<<capabilities_.name()<<"\",\"physicalValidation\":false";
        if(capabilities_.profile()==BoilerProtocol::classic) {
            const auto emit=[&](const char *name,BoilerField field,int divisor=1,bool boolean=false) {
                const auto sample=value(field,now);
                out<<",\""<<name<<"\":";
                if(!sample)out<<"null";
                else if(boolean)out<<(*sample?"true":"false");
                else out<<static_cast<double>(*sample)/divisor;
            };
            emit("currentFlowTemperature",BoilerField::flow,10);
            emit("currentReturnTemperature",BoilerField::returnTemp,10);
            emit("selectedFlowTemperature",BoilerField::selectedFlow,100);
            emit("currentWarmWaterTemperature",BoilerField::dhwTemp,10);
            emit("selectedWarmWaterTemperature",BoilerField::selectedDhw,100);
            emit("currentBurnerPower",BoilerField::modulation);
            emit("pressure",BoilerField::pressure);
            emit("outdoorTemperature",BoilerField::outdoor);
            emit("warmWaterFlow",BoilerField::dhwFlow);
            emit("heatingActive",BoilerField::heatingActive,1,true);
            emit("warmWaterActive",BoilerField::dhwActive,1,true);
            emit("heatingEnabled",BoilerField::heatingEnabled,1,true);
            emit("warmWaterEnabled",BoilerField::dhwEnabled,1,true);
            emit("burningGas",BoilerField::rawBurner,1,true);
            emit("pumpEnabled",BoilerField::rawPump,1,true);
            emit("fanEnabled",BoilerField::rawFan,1,true);
            emit("serviceCode",BoilerField::serviceNumber);
            const auto& display=sample(BoilerField::displayCode);
            if(value(BoilerField::displayCode,now)&&display.raw) {
                // The decoder validates both ASCII code characters.
                out<<",\"displayCode\":\"";
                for(char c:{char((*display.raw>>8)&255),char(*display.raw&255)}) {
                    if(c=='"'||c=='\\')out<<'\\';
                    out<<c;
                }
                out<<'"';
            }
        }
        if(closeObject)out<<'}';
    }
    void writeFieldGroup(std::ostream& ss,uint64_t now,size_t group) const {
        constexpr size_t perGroup=10;
        if(group>=7)return;
        ss << "{\"schema\":1,\"sampled_at_ms\":" << now
           << ",\"profile\":\"" << capabilities_.name() << "\",\"fields\":[";
        const size_t begin=group*perGroup,end=std::min(begin+perGroup,samples_.size());
        for(size_t i=begin;i<end;++i) {
            if(i!=begin)ss<<',';
            const auto& s=samples_[i];ss<<'['<<i<<',';
            if(s.observed&&s.raw&&!notReported(i))ss<<*s.raw;else ss<<"null";
            ss<<',';if(s.observed)ss<<s.observedMs;else ss<<"null";
            ss<<','<<(s.quality==BoilerQuality::reported?0:s.quality==BoilerQuality::unreliable?1:2)
              <<','<<s.sourceType<<']';
        }
        ss<<"]}";
    }

    void writeJSON(std::ostream &ss, uint64_t now, bool closeObject = true) const {
        ss << "{\"protocol_profile\":\"" << capabilities_.name()
           << "\",\"classic_control_commissioned\":false,\"physical_validation\":false,\"reception\":";
        writeReceptionJSON(ss, now);
        ss << ",\"fields\":{";
        for (size_t i = 0; i < samples_.size(); ++i) {
            if (i) ss << ',';
            const auto &s = samples_[i]; const auto &spec = boilerFieldSpecs[i];
            const bool fresh = s.fresh(now, spec), empty = notReported(i);
            // not_reported: the boiler leaves this field empty (BoilerProfile::leftEmpty), its 0 is no value.
            const char *state = !s.observed ? "unknown" : empty ? "not_reported" : !s.raw ? "invalid" : !fresh ? "stale" : "valid";
            ss << '"' << spec.name << "\":{\"value\":";
            // Unreliable bits remain inspectable, but are never trustworthy measurements.
            if (fresh && s.raw && !empty) {
                if (i == index(BoilerField::displayCode)) {
                    ss << '"';
                    for (char c : {static_cast<char>(*s.raw >> 8), static_cast<char>(*s.raw & 255)}) {
                        if (c == '"' || c == '\\') ss << '\\';
                        ss << c;
                    }
                    ss << '"';
                } else ss << static_cast<double>(*s.raw) / spec.divisor;
            } else ss << "null";
            ss << ",\"unit\":\"" << spec.unit << "\",\"state\":\"" << state << "\",\"quality\":\""
               << (s.quality == BoilerQuality::reported ? "reported" : s.quality == BoilerQuality::inferred ? "inferred" : "unreliable")
               << "\",\"source_type\":" << s.sourceType << ",\"source_address\":8,\"age_ms\":";
            if (s.observed && now >= s.observedMs) ss << now - s.observedMs; else ss << "null";
            ss << ",\"observed_at_ms\":";
            if (s.observed) ss << s.observedMs; else ss << "null";
            // A setting the boiler sends only when asked: valid until replaced; the page says when it was read.
            if (spec.requestOnly()) ss << ",\"request_only\":true";
            ss << '}';
        }
        ss << "},\"telegram_inventory\":";
        telegrams_.writeJSON(ss, now);
        if (closeObject) ss << '}';
    }

    // The latest decoded boiler (0x08) report of any family; nullopt: none yet.
    std::optional<uint64_t> lastReportMs() const { return reportCount_ ? std::optional<uint64_t>(lastReportMs_) : std::nullopt; }

    void writeReceptionJSON(std::ostream &ss, uint64_t now) const {
        const bool fresh = reportCount_ && now >= lastReportMs_ && now - lastReportMs_ < 30000;
        const auto profile = capabilities_.profile();
        const char *state = !reportCount_ ? "no_boiler_reports" : !fresh ? "stale"
            : profile == BoilerProtocol::conflict ? "conflicting_families"
            : profile == BoilerProtocol::classic ? "classic_reports_received" : "plus_reports_received";
        ss << "{\"state\":\"" << state << "\",\"report_count\":" << reportCount_
           << ",\"last_report_age_ms\":";
        if (reportCount_ && now >= lastReportMs_) ss << now - lastReportMs_; else ss << "null";
        ss << ",\"fresh_report\":" << (fresh ? "true" : "false")
           << ",\"control_approved\":false,\"fresh_classic_fields\":[";
        bool first = true;
        for (size_t i = 0; i < samples_.size(); ++i) {
            const auto &sample = samples_[i];
            if (profile != BoilerProtocol::classic || !sample.raw || !sample.fresh(now, boilerFieldSpecs[i])
                || sample.quality == BoilerQuality::unreliable || notReported(i)) continue;
            if (!first) ss << ',';
            first = false;
            ss << '"' << boilerFieldSpecs[i].name << '"';
        }
        ss << "]}";
    }

private:
    static_assert(static_cast<size_t>(BoilerField::count) == classicBoilerFieldCount, "boiler profile covers every Classic field");
    static_assert(BoilerProfile::schema1ZeroValueSlots[0] == static_cast<size_t>(BoilerField::selectedFlow),
                  "the profile restores a schema-1 selected flow as unknown");
    BoilerProfile* profile_ = nullptr;
    uint64_t reportCount_ = 0;
    uint64_t lastReportMs_ = 0;
    static constexpr size_t index(BoilerField f) { return static_cast<size_t>(f); }
    BoilerCapabilities capabilities_;
    BoilerTelegramInventory telegrams_;
    std::array<BoilerSample, static_cast<size_t>(BoilerField::count)> samples_{};
};
}
