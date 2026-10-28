#pragma once
#include "BleDeviceConfig.h"
#include "BoundedJson.h"
#include <cstring>
#include <initializer_list>
#include <new>

namespace heating::control {
enum class BleSettingsError { none, invalid_shape, invalid_count, invalid_address, duplicate_address,
    unsupported_profile, invalid_encryption, invalid_key, invalid_name, invalid_key_action,
    previous_config_invalid, settings_too_large, allocation_failed };
inline const char* bleSettingsErrorName(BleSettingsError error) noexcept {
    switch (error) {
        case BleSettingsError::none: return "none";
        case BleSettingsError::invalid_count: return "invalid_device_count";
        case BleSettingsError::invalid_address: return "invalid_device_address";
        case BleSettingsError::duplicate_address: return "duplicate_device_address";
        case BleSettingsError::unsupported_profile: return "unsupported_device_profile";
        case BleSettingsError::invalid_encryption: return "invalid_device_encryption";
        case BleSettingsError::invalid_key: return "invalid_device_key";
        case BleSettingsError::invalid_name: return "invalid_device_name";
        case BleSettingsError::invalid_key_action: return "invalid_device_key_action";
        case BleSettingsError::previous_config_invalid: return "stored_bluetooth_config_invalid";
        case BleSettingsError::settings_too_large: return "device_settings_too_large";
        case BleSettingsError::allocation_failed: return "bluetooth_resources_unavailable";
        default: return "invalid_bluetooth_settings";
    }
}
inline const cJSON* bleSetting(const cJSON* root, const char* name) noexcept {
    return cJSON_IsObject(root) ? cJSON_GetObjectItemCaseSensitive(root, name) : nullptr;
}
inline std::string_view bleSettingText(const cJSON* value) noexcept {
    return cJSON_IsString(value) && value->valuestring ? std::string_view(value->valuestring) : std::string_view{};
}
inline bool bleSettingsFields(const cJSON* value, std::initializer_list<const char*> required,
        std::initializer_list<const char*> optional = {}) noexcept {
    if (!cJSON_IsObject(value)) return false;
    for (auto field : required) if (!bleSetting(value, field)) return false;
    for (auto child = value->child; child; child = child->next) {
        if (!child->string) return false;
        const std::string_view name(child->string);
        bool allowed = false;
        for (auto field : required) allowed = allowed || name == field;
        for (auto field : optional) allowed = allowed || name == field;
        if (!allowed) return false;
        for (auto prior = value->child; prior != child; prior = prior->next)
            if (!std::strcmp(prior->string, child->string)) return false;
    }
    return true;
}
inline bool bleSettingInteger(const cJSON* value, int low, int high) noexcept {
    return cJSON_IsNumber(value) && value->valuedouble == value->valueint
        && value->valueint >= low && value->valueint <= high;
}
inline bool appendBleJson(cJSON* array, cJSON* item) noexcept {
    if (!item) return false;
    if (cJSON_AddItemToArray(array, item)) return true;
    cJSON_Delete(item); return false;
}

inline BleSettingsError readManagedBleBindings(const cJSON* settings, ManagedBleBindings& out) noexcept {
    out.clear();
    const auto fail = [&](BleSettingsError error) { out.clear(); return error; };
    if (!cJSON_IsObject(settings)) return fail(BleSettingsError::invalid_shape);
    const auto bt = bleSetting(settings, "bt");
    if (!bt) return BleSettingsError::none;
    if (!cJSON_IsObject(bt)) return fail(BleSettingsError::invalid_shape);
    const auto stored = bleSetting(bt, "devices");
    if (!stored) return BleSettingsError::none; // Read never creates a default or namespace.
    if (!bleSettingsFields(stored, {"schema", "items"})
            || !bleSettingInteger(bleSetting(stored, "schema"), 1, 1)) return fail(BleSettingsError::invalid_shape);
    const auto items = bleSetting(stored, "items");
    if (!cJSON_IsArray(items) || cJSON_GetArraySize(items) > int(ManagedBleBindings::capacity))
        return fail(BleSettingsError::invalid_count);
    for (auto row = items->child; row; row = row->next) {
        if (!cJSON_IsArray(row) || cJSON_GetArraySize(row) != 5) return fail(BleSettingsError::invalid_shape);
        ManagedBleBinding value;
        const auto at = [&](int index) { return cJSON_GetArrayItem(row, index); };
        if (!parseManagedBleAddress(bleSettingText(at(0)), value.address)) return fail(BleSettingsError::invalid_address);
        if (out.find(value.address)) return fail(BleSettingsError::duplicate_address);
        if (!bleSettingInteger(at(1), 1, 3)) return fail(BleSettingsError::unsupported_profile);
        value.profile = static_cast<ManagedBleProfile>(at(1)->valueint);
        if (!bleSettingInteger(at(2), 0, 2)) return fail(BleSettingsError::invalid_encryption);
        value.encryption = static_cast<ManagedBleEncryption>(at(2)->valueint);
        if (!cJSON_IsNull(at(3))) {
            if (value.encryption == ManagedBleEncryption::plain
                    || !parseBleHex(bleSettingText(at(3)), value.key)) return fail(BleSettingsError::invalid_key);
            value.hasKey = true;
        }
        if (!cJSON_IsString(at(4)) || !validManagedBleName(bleSettingText(at(4)))) return fail(BleSettingsError::invalid_name);
        const auto name = bleSettingText(at(4));
        std::copy(name.begin(), name.end(), value.name.begin());
        if(!validManagedBleProfileEncryption(value.profile,value.encryption)) return fail(BleSettingsError::invalid_encryption);
        out.devices[out.count++] = value;
    }
    out.sort();
    return BleSettingsError::none;
}

// Public projection is constructed separately: a bindkey is never temporarily
// serialized into a response and then hidden by the browser.
inline ControlJson publicManagedBleBindings(const ManagedBleBindings& bindings) {
    ControlJson out(cJSON_CreateArray(), cJSON_Delete);
    if (!out || bindings.count > bindings.capacity) return {nullptr, cJSON_Delete};
    for (std::size_t i = 0; i < bindings.count; ++i) {
        const auto& device = bindings.devices[i];
        if (!validManagedBleBinding(device)) return {nullptr, cJSON_Delete};
        auto row = cJSON_CreateObject();
        if (!appendBleJson(out.get(), row)) return {nullptr, cJSON_Delete};
        const auto address = printBleHex(device.address);
        if (!cJSON_AddStringToObject(row, "address", address.data())
                || !cJSON_AddStringToObject(row, "profile", managedBleProfileName(device.profile))
                || !cJSON_AddStringToObject(row, "encryption", managedBleEncryptionName(device.encryption))
                || !cJSON_AddStringToObject(row, "name", device.name.data())
                || !cJSON_AddBoolToObject(row, "key_stored", device.hasKey)
                || !cJSON_AddBoolToObject(row, "control_qualified", false)) return {nullptr, cJSON_Delete};
    }
    return out;
}
inline ControlJson committedManagedBleBindings(const ManagedBleBindings& bindings) {
    ControlJson out(cJSON_CreateObject(), cJSON_Delete);
    if (!out || bindings.count > bindings.capacity || !cJSON_AddNumberToObject(out.get(), "schema", 1))
        return {nullptr, cJSON_Delete};
    const auto items = cJSON_AddArrayToObject(out.get(), "items");
    if (!items) return {nullptr, cJSON_Delete};
    for (std::size_t i = 0; i < bindings.count; ++i) {
        const auto& value = bindings.devices[i];
        if (!validManagedBleBinding(value)) return {nullptr, cJSON_Delete};
        auto row = cJSON_CreateArray();
        if (!appendBleJson(items, row)) return {nullptr, cJSON_Delete};
        const auto address = printBleHex(value.address);
        if (!appendBleJson(row, cJSON_CreateString(address.data()))
                || !appendBleJson(row, cJSON_CreateNumber(static_cast<uint8_t>(value.profile)))
                || !appendBleJson(row, cJSON_CreateNumber(static_cast<uint8_t>(value.encryption)))) return {nullptr, cJSON_Delete};
        cJSON* key = nullptr;
        if (value.hasKey) {
            auto encoded = printBleHex(value.key);
            key = cJSON_CreateString(encoded.data());
            volatile char* clear = encoded.data();
            for (std::size_t j = 0; j < encoded.size(); ++j) clear[j] = 0;
        } else key = cJSON_CreateNull();
        if (!appendBleJson(row, key) || !appendBleJson(row, cJSON_CreateString(value.name.data()))) return {nullptr, cJSON_Delete};
    }
    return out;
}

inline BleSettingsError prepareManagedBleSettings(const cJSON* previous, const cJSON* request,
        ManagedBleBindings& next, ControlJson& candidate, bool& changed) {
    next.clear(); candidate.reset(); changed = false;
    const auto fail = [&](BleSettingsError error) { next.clear(); candidate.reset(); return error; };
    if (!cJSON_IsObject(previous) || !bleSettingsFields(request, {"devices"}, {"reset_invalid"}))
        return fail(BleSettingsError::invalid_shape);
    const auto reset = bleSetting(request, "reset_invalid");
    if (reset && !cJSON_IsBool(reset)) return fail(BleSettingsError::invalid_shape);
    const auto items = bleSetting(request, "devices");
    if (!cJSON_IsArray(items) || cJSON_GetArraySize(items) > int(ManagedBleBindings::capacity))
        return fail(BleSettingsError::invalid_count);
    std::unique_ptr<ManagedBleBindings> old(new(std::nothrow) ManagedBleBindings);
    if (!old) return fail(BleSettingsError::allocation_failed);
    const auto oldError = readManagedBleBindings(previous, *old);
    if (oldError != BleSettingsError::none && (!cJSON_IsTrue(reset) || cJSON_GetArraySize(items)))
        return fail(BleSettingsError::previous_config_invalid);
    for (auto row = items->child; row; row = row->next) {
        if (!bleSettingsFields(row, {"address", "profile", "encryption", "name", "key_action"}, {"bindkey"}))
            return fail(BleSettingsError::invalid_shape);
        ManagedBleBinding value;
        if (!parseManagedBleAddress(bleSettingText(bleSetting(row, "address")), value.address))
            return fail(BleSettingsError::invalid_address);
        if (next.find(value.address)) return fail(BleSettingsError::duplicate_address);
        const auto profile = bleSettingText(bleSetting(row,"profile"));
        if(profile=="shelly_ht_display")value.profile=ManagedBleProfile::shellyHtDisplay;
        else if(profile=="xiaomi_monitor_3")value.profile=ManagedBleProfile::xiaomiMonitor3;
        else if(profile=="shelly_blu_trv")value.profile=ManagedBleProfile::shellyTrv;
        else if(profile=="pvvx_thermometer")value.profile=ManagedBleProfile::pvvxThermometer;
        else return fail(BleSettingsError::unsupported_profile);
        const auto encryption = bleSettingText(bleSetting(row,"encryption"));
        if(encryption=="bthome_v2")value.encryption=ManagedBleEncryption::bthomeV2;
        else if(encryption=="mibeacon_v4_v5")value.encryption=ManagedBleEncryption::miBeaconV4V5;
        else if(encryption!="none")return fail(BleSettingsError::invalid_encryption);
        if(!validManagedBleProfileEncryption(value.profile,value.encryption))return fail(BleSettingsError::invalid_encryption);
        const auto name = bleSettingText(bleSetting(row, "name"));
        if (!cJSON_IsString(bleSetting(row, "name")) || !validManagedBleName(name)) return fail(BleSettingsError::invalid_name);
        std::copy(name.begin(), name.end(), value.name.begin());
        const auto action = bleSettingText(bleSetting(row, "key_action"));
        const auto supplied = bleSetting(row, "bindkey");
        if (action == "set") {
            if (value.encryption == ManagedBleEncryption::plain || !parseBleHex(bleSettingText(supplied), value.key))
                return fail(BleSettingsError::invalid_key);
            value.hasKey = true;
        } else if (action == "keep" || action == "clear") {
            if (supplied) return fail(BleSettingsError::invalid_key_action);
            const auto prior = old->find(value.address);
            if (action == "keep" && prior && prior->profile == value.profile && prior->encryption == value.encryption) {
                value.key = prior->key; value.hasKey = prior->hasKey;
            }
        } else return fail(BleSettingsError::invalid_key_action);
        next.devices[next.count++] = value;
    }
    next.sort();
    if (oldError == BleSettingsError::none && next.same(*old)) return BleSettingsError::none;
    candidate.reset(cJSON_Duplicate(previous, true));
    if (!candidate) return fail(BleSettingsError::allocation_failed);
    auto bt = cJSON_GetObjectItemCaseSensitive(candidate.get(), "bt");
    if (!bt) bt = cJSON_AddObjectToObject(candidate.get(), "bt");
    if (!cJSON_IsObject(bt)) return fail(BleSettingsError::previous_config_invalid);
    auto devices = committedManagedBleBindings(next);
    if (!devices) return fail(BleSettingsError::allocation_failed);
    cJSON_DeleteItemFromObjectCaseSensitive(bt, "devices");
    if (!cJSON_AddItemToObject(bt, "devices", devices.get())) return fail(BleSettingsError::allocation_failed);
    devices.release();
    std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(candidate.get()), cJSON_free);
    if (!text) return fail(BleSettingsError::allocation_failed);
    if (std::strlen(text.get()) >= 2048) return fail(BleSettingsError::settings_too_large);
    changed = true;
    return BleSettingsError::none;
}

// New bindings/keys belong only to the private store. In particular a full
// network restore must not put them in the older firmware's echoed document.
inline bool networkSettingsContainManagedBleBindings(const cJSON* settings) noexcept {
    return bleSetting(bleSetting(settings,"bt"),"devices") != nullptr;
}
// An older network form must neither receive bindkeys nor erase bindings it
// does not understand. Explicit device edits use the Bluetooth form/API.
inline void redactManagedBleSettings(cJSON* settings) noexcept {
    auto bt = cJSON_GetObjectItemCaseSensitive(settings, "bt");
    if (cJSON_IsObject(bt)) cJSON_DeleteItemFromObjectCaseSensitive(bt, "devices");
}
inline bool retainManagedBleSettings(const cJSON* previous, cJSON* candidate) {
    const auto old = bleSetting(bleSetting(previous, "bt"), "devices");
    if (!old) return true;
    auto bt = cJSON_GetObjectItemCaseSensitive(candidate, "bt");
    if (!bt) {
        auto copied = cJSON_Duplicate(bleSetting(previous, "bt"), true);
        if (!copied) return false;
        if (cJSON_AddItemToObject(candidate, "bt", copied)) return true;
        cJSON_Delete(copied); return false;
    }
    if (!cJSON_IsObject(bt)) return false;
    if (bleSetting(bt, "devices")) return true; // Explicit full-settings restore is validated separately.
    auto copied = cJSON_Duplicate(old, true);
    if (!copied) return false;
    if (cJSON_AddItemToObject(bt, "devices", copied)) return true;
    cJSON_Delete(copied); return false;
}
}
