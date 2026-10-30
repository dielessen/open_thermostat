#pragma once
#include "BoilerCapabilities.h"
#include "DeviceVersion.h"
#include "EmsEntityTable.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace heating::ems {
// The boiler capability profile (docs/modern-thermostat/BOILER-PROFILE.en.md):
// which boiler fields THIS boiler actually has, learned passively from its own
// reports. Never sends anything on the bus and never infers support from a
// model name, a brand or a setting; the decoders hand in their own verdict.
//
// Per field, one of:
//   supported     a valid value was seen (sticky: a sensor added later shows up,
//                 a sensor that fails later reads unavailable, not "not fitted")
//   not_fitted    its telegram arrived >= 10 times over >= 10 min and the field
//                 always held its "no sensor" sentinel / out-of-range value
//   not_reported  the telegram that carries it has never been seen
//   unknown       seen, but too few observations to tell
// Fields are the 69 Classic fields (wire index 0..68) and the entity catalog
// fields (wire index 70..). EMS+ (1.1) plugs in through the same catalog rows.
inline constexpr size_t classicBoilerFieldCount = 69;

// The decoder's verdict for one field in one received frame.
//   value         a valid value
//   absent        the sentinel or an out-of-range value: "no value"
//   inconclusive  a value that proves nothing either way (the 0 of an
//                 unreliable OEM counter or raw bit: adapters fill unsupported
//                 bytes with 00), so it never makes a field not_fitted
enum class FieldEvidence : uint8_t { value, absent, inconclusive };
enum class FieldPresence : uint8_t { not_reported = 0, unknown = 1, not_fitted = 2, supported = 3 };

constexpr const char* fieldPresenceName(FieldPresence p) {
    return p == FieldPresence::supported ? "supported" : p == FieldPresence::not_fitted ? "not_fitted"
        : p == FieldPresence::unknown ? "unknown" : "not_reported";
}

// Catalog row -> catalog field (rows sharing an entity id are one field).
constexpr std::array<uint8_t, entityCatalog.size()> listEntityRowFields() {
    std::array<uint8_t, entityCatalog.size()> fields{};
    for (size_t row = 0; row < entityCatalog.size(); ++row)
        for (size_t f = 0; f < entityFieldCount; ++f)
            if (sameEntity(entityFieldRows[f], row)) { fields[row] = static_cast<uint8_t>(f); break; }
    return fields;
}
inline constexpr auto entityRowFields = listEntityRowFields();

class BoilerProfile {
public:
    static constexpr size_t classicFields = classicBoilerFieldCount, catalogFields = entityFieldCount;
    static constexpr size_t fieldCount = classicFields + catalogFields, catalogWireBase = 70;
    static constexpr uint16_t notFittedFrames = 10;
    static constexpr uint32_t notFittedSpanS = 600;
    // NVS writes: only after a change, once nothing changed for 30 s, and at
    // most every 5 min (an owner override goes out on the next loop).
    static constexpr uint64_t quietMs = 30000, writeIntervalMs = 300000;
    static constexpr size_t headerBytes = 10, stateBytes = (fieldCount + 3) / 4, overrideBytes = (fieldCount + 7) / 8;
    static constexpr size_t recordBytes = headerBytes + stateBytes + overrideBytes;
    static constexpr uint8_t recordMagic = 0x42, recordSchema = 1;
    using Record = std::array<uint8_t, recordBytes>;
    static constexpr uint8_t classicFamily = 1, plusFamily = 2;
    struct Identity {
        uint8_t address = 0x08, families = 0, product = 0, major = 0, minor = 0;
        bool versioned = false;
        bool operator==(const Identity& o) const {
            return address == o.address && families == o.families && versioned == o.versioned
                && product == o.product && major == o.major && minor == o.minor;
        }
    };

    static constexpr size_t wireIndex(size_t slot) { return slot < classicFields ? slot : catalogWireBase + slot - classicFields; }
    static constexpr std::optional<size_t> slotOf(size_t wire) {
        if (wire < classicFields) return wire;
        if (wire >= catalogWireBase && wire < catalogWireBase + catalogFields) return classicFields + wire - catalogWireBase;
        return std::nullopt;
    }
    static constexpr size_t catalogSlot(size_t field) { return classicFields + field; }

    // One field in one received frame (only frames that contain it).
    void observe(size_t slot, FieldEvidence evidence, uint64_t now) {
        if (slot >= fieldCount) return;
        observed_ = true;
        auto& f = fields_[slot];
        const uint32_t s = static_cast<uint32_t>(std::min<uint64_t>(now / 1000, UINT32_MAX - 1));
        if (evidence == FieldEvidence::value) {
            f.lastValidS = std::max(f.lastValidS, s + 1);
            if (f.state != FieldPresence::supported) {
                setOverride(f, false);
                set(f, FieldPresence::supported, now);
            }
            return;
        }
        if (f.state == FieldPresence::not_reported) set(f, FieldPresence::unknown, now);
        if (evidence != FieldEvidence::absent || f.state != FieldPresence::unknown) return;
        if (!f.absentFrames || s < f.firstAbsentS) f.firstAbsentS = s;
        f.lastAbsentS = std::max(f.lastAbsentS, s);
        if (f.absentFrames < UINT16_MAX) ++f.absentFrames;
        if (f.absentFrames >= notFittedFrames && f.lastAbsentS - f.firstAbsentS >= notFittedSpanS)
            set(f, FieldPresence::not_fitted, now);
    }
    // The wire family of a decoded boiler report, before its fields. The first
    // family of a boot that the stored boiler never used: another boiler.
    void observeFamily(BoilerProtocol family, uint64_t now) {
        const uint8_t bit = family == BoilerProtocol::classic ? classicFamily : family == BoilerProtocol::plus ? plusFamily : 0;
        if (!bit) return;
        observed_ = true;
        const bool first = !bootFamilies_;
        bootFamilies_ |= bit;
        if (first) settleFromMs_ = now;
        if (!(identity_.families & bit)) {
            if (identity_.families && first) {
                Identity next;
                next.address = identity_.address; next.families = bit;
                reset(next, now);
            } else {
                identity_.families |= bit;
                changed(now);
            }
        }
        // Settled: this boiler was heard for the not-fitted span, so a field still
        // not reported is not just waiting for its first telegram.
        if (!settled_ && now >= settleFromMs_ && now - settleFromMs_ >= uint64_t(notFittedSpanS) * 1000) {
            settled_ = true;
            changed(now);
        }
    }
    // The boiler's own version report (0x02 from the boiler address), when
    // another controller asked for it: a different product/version is another boiler.
    void observeVersion(const DeviceVersion& v, uint64_t now) {
        observed_ = true;
        if (identity_.versioned && identity_.product == v.product && identity_.major == v.major && identity_.minor == v.minor) return;
        Identity next = identity_;
        next.versioned = true; next.product = v.product; next.major = v.major; next.minor = v.minor;
        if (identity_.versioned) { next.families = bootFamilies_; reset(next, now); return; }
        identity_ = next;
        changed(now);
    }

    FieldPresence state(size_t slot) const { return slot < fieldCount ? fields_[slot].state : FieldPresence::not_reported; }
    bool overridden(size_t slot) const { return slot < fieldCount && fields_[slot].shown; }
    // What Home Assistant and the dashboards should offer: supported, or an
    // owner's "show anyway" on a not_fitted field.
    bool shown(size_t slot) const {
        return state(slot) == FieldPresence::supported || (state(slot) == FieldPresence::not_fitted && overridden(slot));
    }
    std::optional<uint64_t> lastValidAgeS(size_t slot, uint64_t now) const {
        if (slot >= fieldCount || !fields_[slot].lastValidS) return std::nullopt;
        const uint64_t s = now / 1000, at = fields_[slot].lastValidS - 1;
        return s >= at ? s - at : 0;
    }
    size_t count(FieldPresence p) const {
        return static_cast<size_t>(std::count_if(fields_.begin(), fields_.end(), [p](const Field& f) { return f.state == p; }));
    }
    const Identity& identity() const { return identity_; }
    bool settled() const { return settled_; }
    uint32_t resets() const { return resets_; }
    bool restored() const { return restored_; }
    uint32_t writes() const { return writes_; }
    uint32_t writeFailures() const { return writeFailures_; }

    // Owner "show anyway" for a not_fitted field; false: no such field, or not not_fitted.
    bool setShown(size_t slot, bool show, uint64_t now) {
        if (slot >= fieldCount || (show && fields_[slot].state != FieldPresence::not_fitted)) return false;
        if (fields_[slot].shown == show) return true;
        setOverride(fields_[slot], show);
        changed(now);
        urgent_ = true;
        return true;
    }

    Record record() const {
        Record r{};
        r[0] = recordMagic; r[1] = recordSchema; r[2] = classicFields; r[3] = catalogFields;
        r[4] = identity_.address; r[5] = identity_.families; r[6] = static_cast<uint8_t>(identity_.versioned | (settled_ << 1));
        r[7] = identity_.product; r[8] = identity_.major; r[9] = identity_.minor;
        for (size_t i = 0; i < fieldCount; ++i) {
            r[headerBytes + i / 4] |= static_cast<uint8_t>(static_cast<uint8_t>(fields_[i].state) << (2 * (i % 4)));
            if (fields_[i].shown) r[headerBytes + stateBytes + i / 8] |= static_cast<uint8_t>(1u << (i % 8));
        }
        return r;
    }
    // The stored record of an earlier boot. A record of an older firmware with
    // fewer catalog fields (the catalog only grows at its end) restores those;
    // anything else invalid is ignored. Merges with what this boot saw already;
    // a record of another boiler than the one already seen is dropped.
    bool restore(const uint8_t* data, size_t size, uint64_t now) {
        if (!data || size < headerBytes || data[0] != recordMagic || data[1] != recordSchema
            || data[2] != classicFields || data[3] > catalogFields || data[6] > 3) return false;
        const size_t fields = classicFields + data[3];
        if (size != headerBytes + (fields + 3) / 4 + (fields + 7) / 8) return false;
        Identity stored;
        stored.address = data[4]; stored.families = data[5] & (classicFamily | plusFamily); stored.versioned = data[6] & 1;
        stored.product = data[7]; stored.major = data[8]; stored.minor = data[9];
        if (observed_) {
            const bool otherFamily = bootFamilies_ && stored.families && !(stored.families & bootFamilies_);
            const bool otherVersion = identity_.versioned && stored.versioned && !(identity_.product == stored.product
                && identity_.major == stored.major && identity_.minor == stored.minor);
            if (otherFamily || otherVersion) {
                if (resets_ != UINT32_MAX) ++resets_;
                changed(now);
                return false;
            }
        }
        identity_.address = stored.address;
        identity_.families |= stored.families;
        if (!identity_.versioned && stored.versioned) {
            identity_.versioned = true; identity_.product = stored.product; identity_.major = stored.major; identity_.minor = stored.minor;
        }
        for (size_t i = 0; i < fields; ++i) {
            auto& f = fields_[i];
            const auto s = static_cast<FieldPresence>((data[headerBytes + i / 4] >> (2 * (i % 4))) & 3);
            if (static_cast<uint8_t>(s) > static_cast<uint8_t>(f.state)) f.state = s;
            if (f.state == FieldPresence::not_fitted && ((data[headerBytes + (fields + 3) / 4 + i / 8] >> (i % 8)) & 1)) f.shown = true;
        }
        if (data[6] & 2) settled_ = true;
        restored_ = true;
        // Nothing new: no write. Older record or new observations: write the merge.
        const Record merged = record();
        Record stale{};
        std::copy(data, data + std::min(size, recordBytes), stale.begin());
        if (merged != stale) changed(now); else dirty_ = false;
        return true;
    }
    // Debounced persistence: the record to write now, if any.
    std::optional<Record> takeWrite(uint64_t now) {
        if (!dirty_) return std::nullopt;
        if (!urgent_) {
            if (now < lastChangeMs_ + quietMs) return std::nullopt;
            if (attempted_ && now < lastWriteMs_ + writeIntervalMs) return std::nullopt;
        }
        dirty_ = urgent_ = false; attempted_ = true; lastWriteMs_ = now;
        return record();
    }
    void written(bool ok) {
        if (ok) { if (writes_ != UINT32_MAX) ++writes_; return; }
        dirty_ = true;
        if (writeFailures_ != UINT32_MAX) ++writeFailures_;
    }
    bool dirty() const { return dirty_; }

private:
    struct Field {
        uint32_t firstAbsentS = 0, lastAbsentS = 0, lastValidS = 0; // lastValidS: boot seconds + 1, 0 = never
        uint16_t absentFrames = 0;
        FieldPresence state = FieldPresence::not_reported;
        bool shown = false;
    };
    void set(Field& f, FieldPresence state, uint64_t now) { f.state = state; changed(now); }
    static void setOverride(Field& f, bool show) { f.shown = show; }
    void changed(uint64_t now) { dirty_ = true; lastChangeMs_ = now; }
    void reset(const Identity& next, uint64_t now) {
        fields_ = {};
        identity_ = next;
        settled_ = false;
        settleFromMs_ = now;
        if (resets_ != UINT32_MAX) ++resets_;
        changed(now);
    }
    std::array<Field, fieldCount> fields_{};
    Identity identity_;
    uint64_t lastChangeMs_ = 0, lastWriteMs_ = 0, settleFromMs_ = 0;
    uint32_t resets_ = 0, writes_ = 0, writeFailures_ = 0;
    uint8_t bootFamilies_ = 0;
    bool observed_ = false, restored_ = false, settled_ = false, dirty_ = false, urgent_ = false, attempted_ = false;
};
}
