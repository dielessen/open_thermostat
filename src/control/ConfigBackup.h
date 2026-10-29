#pragma once
// Settings backup and restore (beta.19 item 23). Pure and host-testable: the
// stored documents come in as text, the candidates go out as text, and the
// device glue (ConfigBackupRoute.h) reads and writes NVS. Every section reuses
// the validator of its own settings API: RoomPlan::parse, FlowSettings::parse,
// prepareManagedBleSettings and the network rules of POST /config/device.
//
// Secrets (MQTT password, OpenWeather key, Bluetooth keys) are left out unless
// the owner chooses a passphrase; then they travel as one sealed box
// (BackupCipher.h). The Wi-Fi and web passwords are never exported: Wi-Fi is
// only saved after the setup flow proved a connection, and the web password is
// the one the owner just signed in with.
#include "BoilerDisplayModels.h"
#include "control/BleDeviceSettings.h"
#include "control/BoundedJson.h"
#include "control/FlowPolicy.h"
#include "control/ManagedDeviceSettings.h"
#include "control/NativeSourceProvisioning.h"
#include "control/RoomPlan.h"
#include "control/SessionAdmission.h"
#include <cJSON.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace heating::control::backup {

inline constexpr const char* formatName = "openthermostat-e32-backup";
inline constexpr int schemaVersion = 1;
inline constexpr std::size_t maxBytes = 24576;        // one backup file
inline constexpr std::size_t maxRequestBytes = maxBytes + 512;
inline constexpr std::size_t maxDepth = 10;           // request 1 + backup 1 + room plan 5, margin
inline constexpr std::size_t maxSecretsBytes = 1024;  // the sealed secrets document
inline constexpr std::size_t passphraseMin = 8, passphraseMax = 64;
inline constexpr uint32_t kdfIterations = 4096;       // as the web password (WebPassword.h)
inline constexpr std::size_t saltBytes = 16, nonceBytes = 13, tagBytes = 16;

// The device as it is now: the stored documents and what restore may not touch.
struct DeviceState {
    std::string network;       // ot_network/settings
    std::string bluetooth;     // ot_bluetooth/settings (with keys)
    std::string plan;          // RoomPlan API form, with its revision
    std::string flow;          // FlowSettings::json()
    std::string display;       // boiler display model id
    std::string wifiSsid;      // shown in the export only
    bool modernMode = false;   // HA-managed: legacy weather settings are read-only
    bool ethernetUp = false;   // an Ethernet link carries the network now
    bool boilerClaimed = false;// ActiveHeatGuard::claimsBoiler, a boiler test or settings write
};
struct Meta { std::string firmware, board, created, language; };
struct Secrets {
    bool present = false;
    std::string mqttPassword, weatherKey;
    std::vector<std::pair<std::string, std::string>> bleKeys; // address -> 32 hex digits
    void wipe() {
        for (auto* s : {&mqttPassword, &weatherKey}) { volatile char* p = s->data(); for (std::size_t i = 0; i < s->size(); ++i) p[i] = 0; s->clear(); }
        for (auto& k : bleKeys) { volatile char* p = k.second.data(); for (std::size_t i = 0; i < k.second.size(); ++i) p[i] = 0; }
        bleKeys.clear(); present = false;
    }
    ~Secrets() { wipe(); }
};
// Candidates; an empty one leaves its section as it is.
struct Prepared { std::string network, bluetooth, plan, flow, display, language; bool restart = false; };
// The summary the owner confirms: changes, warnings and what to re-enter.
struct Report {
    ControlJson changes{cJSON_CreateArray(), cJSON_Delete}, warnings{cJSON_CreateArray(), cJSON_Delete},
        reenter{cJSON_CreateArray(), cJSON_Delete};
    bool ok() const { return changes && warnings && reenter; }
    void add(cJSON* list, std::string_view code, std::string_view detail = {}) {
        if (!list) return;
        std::string text(code);
        if (!detail.empty()) { text += ':'; text.append(detail.data(), detail.size()); }
        for (auto item = list->child; item; item = item->next) if (cJSON_IsString(item) && text == item->valuestring) return;
        cJSON_AddItemToArray(list, cJSON_CreateString(text.c_str()));
    }
    void warn(std::string_view code, std::string_view detail = {}) { add(warnings.get(), code, detail); }
    void need(std::string_view code, std::string_view detail = {}) { add(reenter.get(), code, detail); }
    // hidden: name the change only (a secret, or room details too long to list).
    void change(const char* section, const char* field, const cJSON* from, const cJSON* to, bool hidden = false) {
        auto row = cJSON_CreateObject();
        if (!row || !cJSON_AddItemToArray(changes.get(), row)) { cJSON_Delete(row); return; }
        cJSON_AddStringToObject(row, "section", section);
        cJSON_AddStringToObject(row, "field", field);
        if (hidden) { cJSON_AddBoolToObject(row, "hidden", true); return; }
        cJSON_AddItemToObject(row, "from", from ? cJSON_Duplicate(from, true) : cJSON_CreateNull());
        cJSON_AddItemToObject(row, "to", to ? cJSON_Duplicate(to, true) : cJSON_CreateNull());
    }
};

inline std::string print(const cJSON* o) {
    std::unique_ptr<char, decltype(&cJSON_free)> s(o ? cJSON_PrintUnformatted(o) : nullptr, cJSON_free);
    return s ? s.get() : "";
}
inline const cJSON* item(const cJSON* o, const char* key) {
    return cJSON_IsObject(o) ? cJSON_GetObjectItemCaseSensitive(o, key) : nullptr;
}
// Equal values, or both absent (cJSON_Compare is false for two absent items).
inline bool same(const cJSON* a, const cJSON* b) { return (!a && !b) || cJSON_Compare(a, b, true); }
// Bindings are about 0.5 KB each: on the heap (PSRAM), not the loop stack.
inline std::unique_ptr<ManagedBleBindings> storedBindings(const cJSON* stored) {
    std::unique_ptr<ManagedBleBindings> out(new (std::nothrow) ManagedBleBindings);
    if (out && (!stored || readManagedBleBindings(stored, *out) != BleSettingsError::none)) out.reset();
    return out;
}
inline std::string_view text(const cJSON* v) {
    return cJSON_IsString(v) && v->valuestring ? std::string_view(v->valuestring) : std::string_view{};
}
// Replaces (or adds) key in object; takes ownership of value.
inline bool put(cJSON* object, const char* key, cJSON* value) {
    if (!cJSON_IsObject(object) || !value) { cJSON_Delete(value); return false; }
    if (cJSON_GetObjectItemCaseSensitive(object, key)) return cJSON_ReplaceItemInObjectCaseSensitive(object, key, value);
    if (cJSON_AddItemToObject(object, key, value)) return true;
    cJSON_Delete(value); return false;
}
inline cJSON* section(cJSON* root, const char* name) {
    if (!name) return root;
    auto s = cJSON_GetObjectItemCaseSensitive(root, name);
    if (cJSON_IsObject(s)) return s;
    return put(root, name, cJSON_CreateObject()) ? cJSON_GetObjectItemCaseSensitive(root, name) : nullptr;
}

// The network document fields a backup carries, with their types and ranges.
// Secrets (mqtt.password, openweather.appid), the device-bound native SOURCE
// profile and the Bluetooth bindings are deliberately absent.
enum class Kind : uint8_t { flag, number, text };
struct Field { const char* section; const char* name; Kind kind; int32_t low, high; };
inline constexpr Field networkFields[] = {
    {nullptr, "hostname", Kind::text, 0, 63},
    {nullptr, "interface_mode", Kind::text, 4, 8},
    {nullptr, "listenPort", Kind::number, 1, 65535},
    {nullptr, "emsEnabled", Kind::flag, 0, 1},
    {nullptr, "emsForwarderEnabled", Kind::flag, 0, 1},
    {nullptr, "rtcEnabled", Kind::flag, 0, 1},
    {nullptr, "ntpEnabled", Kind::flag, 0, 1},
    {nullptr, "ntpHost", Kind::text, 0, 253},
    {nullptr, "ntpUtcOffset", Kind::number, -86400, 86400},
    {nullptr, "ntpDaylightUtcOffset", Kind::number, -86400, 86400},
    {nullptr, "timeZone", Kind::text, 0, 96},
    {nullptr, "loggerEnabled", Kind::flag, 0, 1},
    {nullptr, "loggerHost", Kind::text, 0, 253},
    {nullptr, "loggerPort", Kind::number, 0, 65535},
    {nullptr, "loggerTimeoutMs", Kind::number, 0, 600000},
    {"mqtt", "enabled", Kind::flag, 0, 1},
    {"mqtt", "modern_shadow", Kind::flag, 0, 1},
    {"mqtt", "adapter_id", Kind::text, 0, 32},
    {"mqtt", "publishHomeAssistantDiscovery", Kind::flag, 0, 1},
    {"mqtt", "brokerAddress", Kind::text, 0, 253},
    {"mqtt", "brokerPort", Kind::number, 1, 65535},
    {"mqtt", "username", Kind::text, 0, 128},
    {"mqtt", "clientId", Kind::text, 0, 64},
    {"mqtt", "base", Kind::text, 0, 64},
    {"mqtt", "keepAlive", Kind::number, 1, 3600},
    {"mqtt", "interval", Kind::number, 1, 86400},
    {"openweather", "enabled", Kind::flag, 0, 1},
    {"openweather", "latitude", Kind::text, 0, 32},
    {"openweather", "longitude", Kind::text, 0, 32},
    {"openweather", "interval", Kind::number, 1, 86400},
    {"bt", "scanTime", Kind::number, 1, 3600},
    {"bt", "scanInterval", Kind::number, 0, 86400},
};
inline bool validField(const Field& f, const cJSON* v) {
    switch (f.kind) {
        case Kind::flag: return cJSON_IsBool(v);
        case Kind::number:
            return cJSON_IsNumber(v) && std::isfinite(v->valuedouble) && std::floor(v->valuedouble) == v->valuedouble
                && v->valuedouble >= f.low && v->valuedouble <= f.high;
        case Kind::text: {
            if (!cJSON_IsString(v) || !v->valuestring) return false;
            const std::string_view s(v->valuestring);
            if (s.size() < std::size_t(f.low) || s.size() > std::size_t(f.high)) return false;
            for (unsigned char c : s) if (c < 0x20 || c == 0x7f) return false;
            if (!std::strcmp(f.name, "interface_mode")) return s == "wifi" || s == "ethernet";
            return true;
        }
    }
    return false;
}
inline const Field* findField(const char* sectionName, const char* name) {
    for (const auto& f : networkFields)
        if (((!f.section && !sectionName) || (f.section && sectionName && !std::strcmp(f.section, sectionName)))
                && !std::strcmp(f.name, name)) return &f;
    return nullptr;
}
inline bool isNetworkSection(const char* name) {
    return !std::strcmp(name, "mqtt") || !std::strcmp(name, "openweather") || !std::strcmp(name, "bt");
}
inline std::string fieldPath(const Field& f) { return f.section ? std::string(f.section) + "." + f.name : std::string(f.name); }

inline ControlJson parseStored(const std::string& raw, std::size_t depth = legacyJsonDepth) {
    if (raw.empty()) return ControlJson(nullptr, cJSON_Delete);
    auto root = parseNestedJson(raw.c_str(), raw.size(), true, depth);
    return cJSON_IsObject(root.get()) ? std::move(root) : ControlJson(nullptr, cJSON_Delete);
}

// ---------------------------------------------------------------- export

// The secrets document sealed by BackupCipher.h; empty when there is nothing secret.
inline std::string secretsDocument(const DeviceState& s) {
    auto network = parseStored(s.network), stored = parseStored(s.bluetooth);
    ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) return {};
    bool any = false;
    const auto addText = [&](const char* sec, const char* key, const char* as) {
        const auto v = text(item(item(network.get(), sec), key));
        if (!v.empty()) any = cJSON_AddStringToObject(root.get(), as, std::string(v).c_str()) || any;
    };
    addText("mqtt", "password", "mqtt_password");
    addText("openweather", "appid", "openweather_key");
    if (auto bindings = storedBindings(stored.get())) {
        auto keys = cJSON_AddObjectToObject(root.get(), "bluetooth_keys");
        for (std::size_t i = 0; keys && i < bindings->count; ++i) {
            if (!bindings->devices[i].hasKey) continue;
            auto address = printBleHex(bindings->devices[i].address);
            auto key = printBleHex(bindings->devices[i].key);
            cJSON_AddStringToObject(keys, address.data(), key.data());
            volatile char* clear = key.data();
            for (std::size_t j = 0; j < key.size(); ++j) clear[j] = 0;
            any = true;
        }
    }
    if (!any) return {};
    auto out = print(root.get());
    // cJSON nodes are freed without wiping; the tree is PSRAM on the E32 and short lived.
    return out.size() <= maxSecretsBytes ? out : std::string();
}

// The secrets a plain backup leaves out (and a sealed one still cannot hold).
inline void notIncluded(const DeviceState& s, bool sealed, cJSON* list) {
    cJSON_AddItemToArray(list, cJSON_CreateString("wifi_password"));
    cJSON_AddItemToArray(list, cJSON_CreateString("web_password"));
    if (sealed) return;
    auto network = parseStored(s.network), stored = parseStored(s.bluetooth);
    if (!text(item(item(network.get(), "mqtt"), "password")).empty()) cJSON_AddItemToArray(list, cJSON_CreateString("mqtt_password"));
    if (!text(item(item(network.get(), "openweather"), "appid")).empty()) cJSON_AddItemToArray(list, cJSON_CreateString("openweather_key"));
    if (auto bindings = storedBindings(stored.get()))
        for (std::size_t i = 0; i < bindings->count; ++i)
            if (bindings->devices[i].hasKey) { cJSON_AddItemToArray(list, cJSON_CreateString("bluetooth_keys")); break; }
}

// The whole backup document. sealedHex: the sealed secrets box (hex), or empty.
inline ControlJson exportDocument(const DeviceState& s, const Meta& m, const std::string& sealedHex) {
    const auto fail = [] { return ControlJson(nullptr, cJSON_Delete); };
    ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) return fail();
    auto r = root.get();
    cJSON_AddStringToObject(r, "format", formatName);
    cJSON_AddNumberToObject(r, "schema", schemaVersion);
    cJSON_AddStringToObject(r, "firmware", m.firmware.c_str());
    cJSON_AddStringToObject(r, "board", m.board.c_str());
    if (m.created.empty()) cJSON_AddNullToObject(r, "created"); else cJSON_AddStringToObject(r, "created", m.created.c_str());
    if (sealedHex.empty()) cJSON_AddNullToObject(r, "secrets");
    else if (auto box = cJSON_AddObjectToObject(r, "secrets")) {
        cJSON_AddStringToObject(box, "cipher", "aes-128-ccm");
        cJSON_AddStringToObject(box, "kdf", "pbkdf2-sha256");
        cJSON_AddNumberToObject(box, "iterations", kdfIterations);
        cJSON_AddStringToObject(box, "box", sealedHex.c_str());
    }
    notIncluded(s, !sealedHex.empty(), cJSON_AddArrayToObject(r, "not_included"));

    auto network = parseStored(s.network);
    auto net = cJSON_AddObjectToObject(r, "network");
    if (!network || !net) return fail();
    for (const auto& f : networkFields) {
        const auto v = item(f.section ? item(network.get(), f.section) : network.get(), f.name);
        if (!v || !validField(f, v)) continue; // out-of-range stored values stay on the device
        auto target = section(net, f.section);
        if (!target || !put(target, f.name, cJSON_Duplicate(v, true))) return fail();
    }
    if (!s.wifiSsid.empty()) if (auto w = cJSON_AddObjectToObject(r, "wifi")) cJSON_AddStringToObject(w, "ssid", s.wifiSsid.c_str());

    auto stored = parseStored(s.bluetooth);
    if (auto bindings = storedBindings(stored.get())) {
        auto bt = cJSON_AddObjectToObject(r, "bluetooth");
        auto devices = bt ? cJSON_AddArrayToObject(bt, "devices") : nullptr;
        if (!devices) return fail();
        for (std::size_t i = 0; i < bindings->count; ++i) {
            const auto& d = bindings->devices[i];
            auto row = cJSON_CreateObject();
            if (!row || !cJSON_AddItemToArray(devices, row)) { cJSON_Delete(row); return fail(); }
            cJSON_AddStringToObject(row, "address", printBleHex(d.address).data());
            cJSON_AddStringToObject(row, "profile", managedBleProfileName(d.profile));
            cJSON_AddStringToObject(row, "encryption", managedBleEncryptionName(d.encryption));
            cJSON_AddStringToObject(row, "name", d.name.data());
        }
    }
    if (auto plan = parseStored(s.plan)) {
        cJSON_DeleteItemFromObjectCaseSensitive(plan.get(), "revision"); // device-local history
        if (!cJSON_AddItemToObject(r, "heating", plan.get())) return fail();
        plan.release();
    }
    if (auto flow = parseStored(s.flow)) { if (!cJSON_AddItemToObject(r, "flow", flow.get())) return fail(); flow.release(); }
    if (!s.display.empty()) if (auto d = cJSON_AddObjectToObject(r, "boiler_display")) cJSON_AddStringToObject(d, "model", s.display.c_str());
    if (m.language == "en" || m.language == "nl") if (auto u = cJSON_AddObjectToObject(r, "ui")) cJSON_AddStringToObject(u, "language", m.language.c_str());
    return root;
}

// ---------------------------------------------------------------- import

// POST /config/backup: {"action":"export"|"validate"|"apply", ...}.
struct Request {
    ControlJson root{nullptr, cJSON_Delete};
    std::string action, passphrase, fingerprint, language;
    const cJSON* backup = nullptr;
    ~Request() { volatile char* p = passphrase.data(); for (std::size_t i = 0; i < passphrase.size(); ++i) p[i] = 0; }
};
inline const char* readRequest(const char* body, std::size_t size, Request& out) {
    if (!body || !size || size > maxRequestBytes) return "backup_too_large";
    out.root = parseNestedJson(body, size, true, maxDepth);
    if (!cJSON_IsObject(out.root.get())) return "invalid_json";
    for (auto c = out.root->child; c; c = c->next) {
        if (!c->string) return "invalid_request";
        const std::string_view k(c->string);
        if (k == "action" || k == "passphrase" || k == "fingerprint" || k == "language") { if (!cJSON_IsString(c)) return "invalid_request"; }
        else if (k == "backup") { if (!cJSON_IsObject(c)) return "not_a_backup"; out.backup = c; }
        else return "invalid_request";
    }
    out.action = std::string(text(item(out.root.get(), "action")));
    out.passphrase = std::string(text(item(out.root.get(), "passphrase")));
    out.fingerprint = std::string(text(item(out.root.get(), "fingerprint")));
    out.language = std::string(text(item(out.root.get(), "language")));
    if (out.action != "export" && out.action != "validate" && out.action != "apply") return "invalid_request";
    if (out.action == "export" ? out.backup != nullptr : out.backup == nullptr) return "invalid_request";
    if (out.action != "apply" && !out.fingerprint.empty()) return "invalid_request";
    if (!out.passphrase.empty() && (out.passphrase.size() < passphraseMin || out.passphrase.size() > passphraseMax))
        return "invalid_passphrase";
    return nullptr;
}

inline int hexValue(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1; }
inline bool fromHex(std::string_view hex, std::string& out) {
    out.clear();
    if (hex.size() % 2) return false;
    out.reserve(hex.size() / 2);
    for (std::size_t i = 0; i < hex.size(); i += 2) {
        const int hi = hexValue(hex[i]), lo = hexValue(hex[i + 1]);
        if (hi < 0 || lo < 0) { out.clear(); return false; }
        out.push_back(static_cast<char>(hi << 4 | lo));
    }
    return true;
}
inline std::string toHex(std::string_view bytes) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out(bytes.size() * 2, '0');
    for (std::size_t i = 0; i < bytes.size(); ++i) {
        const auto b = static_cast<unsigned char>(bytes[i]);
        out[2 * i] = digits[b >> 4]; out[2 * i + 1] = digits[b & 15];
    }
    return out;
}

// The envelope: format, schema, board; sealedBox receives the raw sealed bytes.
inline const char* checkEnvelope(const cJSON* b, const Meta& device, Report& report, std::string& sealedBox) {
    sealedBox.clear();
    if (!cJSON_IsObject(b) || text(item(b, "format")) != formatName) return "not_a_backup";
    const auto schema = item(b, "schema");
    if (!cJSON_IsNumber(schema) || schema->valuedouble != std::floor(schema->valuedouble) || schema->valuedouble < 1) return "invalid_schema";
    if (schema->valuedouble > schemaVersion) return "newer_schema";
    if (!cJSON_IsString(item(b, "board")) || text(item(b, "board")) != device.board) return "other_board";
    const auto firmware = item(b, "firmware");
    if (!cJSON_IsString(firmware) || text(firmware).size() > 64) return "invalid_firmware";
    if (text(firmware) != device.firmware) report.warn("other_firmware", text(firmware));
    const auto created = item(b, "created");
    if (created && !cJSON_IsNull(created) && (!cJSON_IsString(created) || text(created).size() > 40)) return "invalid_created";
    for (auto c = b->child; c; c = c->next) {
        const std::string_view k(c->string ? c->string : "");
        if (k == "format" || k == "schema" || k == "board" || k == "firmware" || k == "created") continue;
        if (k == "not_included") { if (!cJSON_IsArray(c)) return "invalid_not_included"; continue; }
        if (k == "secrets") { if (!cJSON_IsNull(c) && !cJSON_IsObject(c)) return "invalid_secrets"; continue; }
        if (k == "network" || k == "wifi" || k == "bluetooth" || k == "heating" || k == "flow" || k == "boiler_display" || k == "ui") {
            if (!cJSON_IsObject(c)) return "invalid_section";
            continue;
        }
        report.warn("unknown_key", k);
    }
    const auto secrets = item(b, "secrets");
    if (cJSON_IsObject(secrets)) {
        const auto iterations = item(secrets, "iterations");
        const auto box = text(item(secrets, "box"));
        if (text(item(secrets, "cipher")) != "aes-128-ccm" || text(item(secrets, "kdf")) != "pbkdf2-sha256"
                || !cJSON_IsNumber(iterations) || iterations->valuedouble != kdfIterations
                || box.size() < 2 * (saltBytes + nonceBytes + tagBytes + 2)
                || box.size() > 2 * (saltBytes + nonceBytes + tagBytes + maxSecretsBytes)
                || !fromHex(box, sealedBox)) { sealedBox.clear(); return "invalid_secrets"; }
    }
    return nullptr;
}

// The opened secrets document (strict: the same shape secretsDocument() writes).
inline const char* readSecrets(const std::string& plain, Secrets& out) {
    out.wipe();
    if (plain.empty() || plain.size() > maxSecretsBytes) return "invalid_secrets";
    auto root = parseNestedJson(plain.c_str(), plain.size(), true, 3);
    if (!cJSON_IsObject(root.get())) return "invalid_secrets";
    for (auto c = root->child; c; c = c->next) {
        const std::string_view k(c->string ? c->string : "");
        if (k == "mqtt_password" && cJSON_IsString(c) && text(c).size() <= 128) out.mqttPassword = std::string(text(c));
        else if (k == "openweather_key" && cJSON_IsString(c) && text(c).size() <= 64) out.weatherKey = std::string(text(c));
        else if (k == "bluetooth_keys" && cJSON_IsObject(c)) {
            for (auto key = c->child; key; key = key->next) {
                ManagedBleAddress address{}; BleBindKey value{};
                if (!key->string || !parseManagedBleAddress(key->string, address) || !parseBleHex(text(key), value)
                        || out.bleKeys.size() >= ManagedBleBindings::capacity) { wipeBleKey(value); out.wipe(); return "invalid_secrets"; }
                wipeBleKey(value);
                out.bleKeys.emplace_back(key->string, std::string(text(key)));
            }
        } else { out.wipe(); return "invalid_secrets"; }
    }
    out.present = true;
    return nullptr;
}

// Network: the current document with the backup's known fields on top, so the
// device-bound parts (native SOURCE profile, legacy Bluetooth bindings, unknown
// fields of other firmware) stay. Rules of POST /config/device (REST.h), plus
// restore's own lock-out rules: Ethernet only while an Ethernet link is up, and
// the web port stays as it is.
inline const char* prepareNetwork(const cJSON* backup, const DeviceState& s, const Secrets& secrets,
                                  std::string& out, Report& report) {
    const auto net = item(backup, "network");
    if (!net) return nullptr;
    auto previous = parseStored(s.network);
    if (!previous) return "stored_network_invalid";
    ControlJson candidate(cJSON_Duplicate(previous.get(), true), cJSON_Delete);
    if (!candidate) return "out_of_memory";
    const auto apply = [&](const char* sec, const cJSON* object) -> const char* {
        for (auto c = object->child; c; c = c->next) {
            if (!c->string) return "invalid_network";
            if (!sec && isNetworkSection(c->string)) {
                if (!cJSON_IsObject(c)) return "invalid_network";
                continue;
            }
            const auto f = findField(sec, c->string);
            if (!f) { report.warn("unknown_key", (sec ? std::string("network.") + sec + "." : std::string("network.")) + c->string); continue; }
            if (!validField(*f, c)) { report.warn("invalid_value", "network." + fieldPath(*f)); return "invalid_network"; }
            auto target = section(candidate.get(), sec);
            if (!target || !put(target, c->string, cJSON_Duplicate(c, true))) return "out_of_memory";
        }
        return nullptr;
    };
    if (const char* e = apply(nullptr, net)) return e;
    for (const char* sec : {"mqtt", "openweather", "bt"})
        if (const auto object = item(net, sec)) if (const char* e = apply(sec, object)) return e;

    // Lock-out rules.
    const auto oldMode = text(item(previous.get(), "interface_mode"));
    const auto newMode = text(item(candidate.get(), "interface_mode"));
    if (newMode == "ethernet" && oldMode != "ethernet" && !s.ethernetUp) {
        report.warn("interface_kept");
        if (oldMode.empty()) cJSON_DeleteItemFromObjectCaseSensitive(candidate.get(), "interface_mode");
        else if (!put(candidate.get(), "interface_mode", cJSON_CreateString(std::string(oldMode).c_str()))) return "out_of_memory";
    }
    const auto oldPort = item(previous.get(), "listenPort"), newPort = item(candidate.get(), "listenPort");
    if (!same(oldPort, newPort)) {
        report.warn("listen_port_kept");
        if (!oldPort) cJSON_DeleteItemFromObjectCaseSensitive(candidate.get(), "listenPort");
        else if (!put(candidate.get(), "listenPort", cJSON_Duplicate(oldPort, true))) return "out_of_memory";
    }

    // MQTT password: restored, kept for the same broker and user, else re-entered.
    const auto oldMq = item(previous.get(), "mqtt");
    if (auto mq = cJSON_GetObjectItemCaseSensitive(candidate.get(), "mqtt"); cJSON_IsObject(mq)) {
        const bool sameBroker = oldMq && text(item(mq, "brokerAddress")) == text(item(oldMq, "brokerAddress"))
            && text(item(mq, "username")) == text(item(oldMq, "username"))
            && same(item(mq, "brokerPort"), item(oldMq, "brokerPort"));
        if (secrets.present && !secrets.mqttPassword.empty()) {
            if (!put(mq, "password", cJSON_CreateString(secrets.mqttPassword.c_str()))) return "out_of_memory";
        } else if (!sameBroker && !put(mq, "password", cJSON_CreateString(""))) return "out_of_memory";
        const bool enabled = cJSON_IsTrue(item(mq, "enabled"));
        const bool modern = cJSON_IsTrue(item(mq, "modern_shadow"));
        if (modern && !SessionAdmission::validId(std::string(text(item(mq, "adapter_id"))))) return "invalid_adapter_id";
        const bool noPassword = text(item(mq, "password")).empty();
        const auto port = item(mq, "brokerPort");
        const bool portValid = cJSON_IsNumber(port) && port->valuedouble >= 1 && port->valuedouble <= 65535;
        if (enabled && ((noPassword && !sameBroker) || (modern && (noPassword || !portValid || text(item(mq, "username")).empty())))) {
            // POST /config/device refuses a new broker or a shadow link without
            // a password; restore keeps MQTT off until it is entered.
            if (!put(mq, "enabled", cJSON_CreateFalse())) return "out_of_memory";
            report.warn("mqtt_off_until_password");
            report.need("mqtt_password");
        }
    }
    // OpenWeather key: restored, else the stored one stays (as POST /config/device).
    const auto oldWeather = item(previous.get(), "openweather");
    if (auto weather = cJSON_GetObjectItemCaseSensitive(candidate.get(), "openweather"); cJSON_IsObject(weather)) {
        if (secrets.present && !secrets.weatherKey.empty()) {
            if (!put(weather, "appid", cJSON_CreateString(secrets.weatherKey.c_str()))) return "out_of_memory";
        }
        if (!managedWeatherChangeAllowed(s.modernMode, oldWeather, weather)) {
            report.warn("weather_managed_kept");
            if (oldWeather) { if (!put(candidate.get(), "openweather", cJSON_Duplicate(oldWeather, true))) return "out_of_memory"; }
            else cJSON_DeleteItemFromObjectCaseSensitive(candidate.get(), "openweather");
        } else if (cJSON_IsTrue(item(weather, "enabled")) && text(item(weather, "appid")).empty()) report.need("openweather_key");
    }

    // The summary: every carried field that differs, secrets only named.
    for (const auto& f : networkFields) {
        const auto a = item(f.section ? item(previous.get(), f.section) : previous.get(), f.name);
        const auto b = item(f.section ? item(candidate.get(), f.section) : candidate.get(), f.name);
        if (b && !same(a, b)) report.change("network", fieldPath(f).c_str(), a, b);
    }
    for (const auto& secret : {std::make_pair("mqtt", "password"), std::make_pair("openweather", "appid")}) {
        const auto a = item(item(previous.get(), secret.first), secret.second), b = item(item(candidate.get(), secret.first), secret.second);
        if (b && !same(a, b)) report.change("network", (std::string(secret.first) + "." + secret.second).c_str(), nullptr, nullptr, true);
    }
    if (cJSON_Compare(previous.get(), candidate.get(), true)) return nullptr;
    out = print(candidate.get());
    if (!nativeNetworkSettingsBytesFit(out)) { out.clear(); return "network_too_large"; }
    return nullptr;
}

// Bluetooth sensors: the backup's list through the Bluetooth API validator. A
// key is set from the sealed secrets, else kept when this E32 already has the
// same sensor (address, profile and encryption), else re-entered.
inline const char* prepareBluetooth(const cJSON* backup, const DeviceState& s, const Secrets& secrets,
                                    std::string& out, Report& report) {
    const auto bt = item(backup, "bluetooth");
    if (!bt) return nullptr;
    for (auto c = bt->child; c; c = c->next)
        if (!c->string || std::strcmp(c->string, "devices")) report.warn("unknown_key", std::string("bluetooth.") + (c->string ? c->string : ""));
    const auto devices = item(bt, "devices");
    if (!cJSON_IsArray(devices) || cJSON_GetArraySize(devices) > int(ManagedBleBindings::capacity)) {
        report.warn("bluetooth", "invalid_device_count"); return "bluetooth_invalid";
    }
    auto previous = parseStored(s.bluetooth);
    if (!previous) return "stored_bluetooth_invalid";
    ControlJson request(cJSON_CreateObject(), cJSON_Delete);
    auto rows = request ? cJSON_AddArrayToObject(request.get(), "devices") : nullptr;
    if (!rows) return "out_of_memory";
    for (auto d = devices->child; d; d = d->next) {
        if (!cJSON_IsObject(d)) { report.warn("bluetooth", "invalid_shape"); return "bluetooth_invalid"; }
        auto row = cJSON_CreateObject();
        if (!row || !cJSON_AddItemToArray(rows, row)) { cJSON_Delete(row); return "out_of_memory"; }
        for (auto f = d->child; f; f = f->next) {
            const std::string_view k(f->string ? f->string : "");
            if (k == "address" || k == "profile" || k == "encryption" || k == "name") {
                if (!cJSON_AddItemToObject(row, f->string, cJSON_Duplicate(f, true))) return "out_of_memory";
            } else report.warn("unknown_key", "bluetooth.devices." + std::string(k));
        }
        const auto address = text(item(row, "address"));
        const std::pair<std::string, std::string>* key = nullptr;
        ManagedBleAddress a{}, b{};
        if (secrets.present && parseManagedBleAddress(address, a))
            for (const auto& k : secrets.bleKeys) if (parseManagedBleAddress(k.first, b) && a == b) key = &k;
        if (key && text(item(row, "encryption")) != "none") {
            cJSON_AddStringToObject(row, "key_action", "set");
            cJSON_AddStringToObject(row, "bindkey", key->second.c_str());
        } else cJSON_AddStringToObject(row, "key_action", "keep");
    }
    std::unique_ptr<ManagedBleBindings> next(new (std::nothrow) ManagedBleBindings), old(new (std::nothrow) ManagedBleBindings);
    if (!next || !old) return "out_of_memory";
    ControlJson candidate(nullptr, cJSON_Delete);
    bool changed = false;
    const auto error = prepareManagedBleSettings(previous.get(), request.get(), *next, candidate, changed);
    if (error != BleSettingsError::none) {
        report.warn("bluetooth", bleSettingsErrorName(error));
        return error == BleSettingsError::allocation_failed ? "out_of_memory" : "bluetooth_invalid";
    }
    for (std::size_t i = 0; i < next->count; ++i)
        if (next->devices[i].encryption != ManagedBleEncryption::plain && !next->devices[i].hasKey)
            report.need("bluetooth_key", next->devices[i].name.data());
    if (!changed) return nullptr;
    (void)readManagedBleBindings(previous.get(), *old);
    // Names in the summary; the keys never.
    const auto names = [](const ManagedBleBindings& list) {
        ControlJson out(cJSON_CreateArray(), cJSON_Delete);
        for (std::size_t i = 0; out && i < list.count; ++i) cJSON_AddItemToArray(out.get(), cJSON_CreateString(list.devices[i].name.data()));
        return out;
    };
    auto from = names(*old), to = names(*next);
    report.change("bluetooth", "devices", from.get(), to.get());
    out = print(candidate.get());
    if (out.empty() || out.size() >= ControlPartitionBudget::networkBytes) { out.clear(); return "bluetooth_too_large"; }
    return nullptr;
}

// The room plan through RoomPlan::parse; always restored in shadow mode, so a
// restore never starts active boiler control.
inline const char* preparePlan(const cJSON* backup, const DeviceState& s, std::string& out, Report& report) {
    const auto heating = item(backup, "heating");
    if (!heating) return nullptr;
    ControlJson copy(cJSON_Duplicate(heating, true), cJSON_Delete);
    if (!copy) return "out_of_memory";
    cJSON_DeleteItemFromObjectCaseSensitive(copy.get(), "revision");
    if (text(item(copy.get(), "mode")) == "active") {
        if (!put(copy.get(), "mode", cJSON_CreateString("shadow"))) return "out_of_memory";
        report.warn("plan_mode_shadow");
    }
    RoomPlan next, old;
    if (const char* e = RoomPlan::parse(copy.get(), next)) { report.warn("heating", e); return "heating_invalid"; }
    if (next.storedJson().size() + 1 > RoomPlan::storeBytes) { report.warn("heating", "plan_too_large"); return "heating_invalid"; }
    auto current = parseStored(s.plan, 10);
    const bool oldValid = current && !RoomPlan::parse(current.get(), old);
    old.revision = 0;
    const auto candidate = next.json();
    if (candidate.empty()) return "out_of_memory";
    if (oldValid && old.json() == candidate) return nullptr;
    const auto roomNames = [](const RoomPlan& p) {
        ControlJson list(cJSON_CreateArray(), cJSON_Delete);
        for (std::size_t i = 0; list && i < p.rooms.size(); ++i) cJSON_AddItemToArray(list.get(), cJSON_CreateString(p.rooms[i].name.c_str()));
        return list;
    };
    auto from = roomNames(old), to = roomNames(next);
    if (!oldValid || !cJSON_Compare(from.get(), to.get(), true)) report.change("heating", "rooms", oldValid ? from.get() : nullptr, to.get());
    else report.change("heating", "room_settings", nullptr, nullptr, true); // the same rooms, other details
    const auto number = [&](const char* field, double a, double b) {
        if (oldValid && a == b) return;
        ControlJson x(cJSON_CreateNumber(a), cJSON_Delete), y(cJSON_CreateNumber(b), cJSON_Delete);
        report.change("heating", field, oldValid ? x.get() : nullptr, y.get());
    };
    number("minimum_flow_c", old.minimumFlowC, next.minimumFlowC);
    number("maximum_flow_c", old.maximumFlowC, next.maximumFlowC);
    out = candidate;
    return nullptr;
}

// Flow options through FlowSettings::parse, one key at a time: a key this
// firmware does not know is reported and skipped, a bad value refused.
inline const char* prepareFlow(const cJSON* backup, const DeviceState& s, std::string& out, Report& report) {
    const auto flow = item(backup, "flow");
    if (!flow) return nullptr;
    FlowSettings current;
    if (auto stored = parseStored(s.flow)) (void)FlowSettings::parse(stored.get(), current);
    FlowSettings next = current;
    for (auto c = flow->child; c; c = c->next) {
        ControlJson one(cJSON_CreateObject(), cJSON_Delete);
        if (!one || !c->string || !cJSON_AddItemToObject(one.get(), c->string, cJSON_Duplicate(c, true))) return "out_of_memory";
        const char* e = FlowSettings::parse(one.get(), next);
        if (e && !std::strcmp(e, "invalid_key")) report.warn("unknown_key", std::string("flow.") + c->string);
        else if (e) { report.warn("invalid_value", std::string("flow.") + c->string); return "flow_invalid_value"; }
    }
    if (next == current) return nullptr;
    auto a = parseStored(current.json()), b = parseStored(next.json());
    for (auto c = b ? b->child : nullptr; c; c = c->next) {
        const auto was = item(a.get(), c->string);
        if (!cJSON_Compare(was, c, true)) report.change("flow", c->string, was, c);
    }
    out = next.json();
    return nullptr;
}

inline const char* prepareDisplay(const cJSON* backup, const DeviceState& s, std::string& out, Report& report) {
    const auto display = item(backup, "boiler_display");
    if (!display) return nullptr;
    for (auto c = display->child; c; c = c->next)
        if (!c->string || std::strcmp(c->string, "model")) report.warn("unknown_key", std::string("boiler_display.") + (c->string ? c->string : ""));
    const auto model = text(item(display, "model"));
    bool known = false;
    for (const auto id : boilerDisplayModelIds) known = known || model == id;
    if (!known) { report.warn("unknown_boiler_model", model.substr(0, 64)); return nullptr; }
    if (model == s.display) return nullptr;
    ControlJson a(cJSON_CreateString(s.display.c_str()), cJSON_Delete), b(cJSON_CreateString(std::string(model).c_str()), cJSON_Delete);
    report.change("boiler_display", "model", a.get(), b.get());
    out = std::string(model);
    return nullptr;
}

// Every section validated before anything is written. nullptr: out holds the
// candidates and report the summary; else the first error and nothing to apply.
inline const char* prepare(const cJSON* backup, const DeviceState& s, const Secrets& secrets, Prepared& out, Report& report) {
    out = Prepared{};
    if (!report.ok()) return "out_of_memory";
    if (s.boilerClaimed) return "boiler_owned";
    const char* e = prepareNetwork(backup, s, secrets, out.network, report);
    if (!e) e = prepareBluetooth(backup, s, secrets, out.bluetooth, report);
    if (!e) e = preparePlan(backup, s, out.plan, report);
    if (!e) e = prepareFlow(backup, s, out.flow, report);
    if (!e) e = prepareDisplay(backup, s, out.display, report);
    if (e) { out = Prepared{}; return e; }
    if (const auto wifi = item(backup, "wifi"); !text(item(wifi, "ssid")).empty()) report.warn("wifi_not_restored");
    const auto ui = item(backup, "ui");
    const auto language = text(item(ui, "language"));
    if (language == "en" || language == "nl") out.language = std::string(language);
    else if (ui) report.warn("unknown_language");
    out.restart = !out.network.empty() || !out.bluetooth.empty();
    return nullptr;
}

// What the owner confirmed: the current documents and the candidates. Apply
// recomputes it and refuses when anything changed in between.
inline std::string fingerprintInput(const DeviceState& s, const Prepared& p) {
    std::string out;
    for (const auto* part : {&s.network, &s.bluetooth, &s.plan, &s.flow, &s.display,
                             &p.network, &p.bluetooth, &p.plan, &p.flow, &p.display}) {
        out += std::to_string(part->size()); out += ':'; out += *part; out += '\n';
    }
    return out;
}

// Ordered writes with rollback: the cheapest first, the network (which needs
// the restart) last. A failure restores every section already written.
enum class Part : uint8_t { display, flow, plan, bluetooth, network };
inline const char* partName(Part p) {
    switch (p) {
        case Part::display: return "boiler_display";
        case Part::flow: return "flow";
        case Part::plan: return "heating";
        case Part::bluetooth: return "bluetooth";
        default: return "network";
    }
}
enum class Applied : uint8_t { applied, restored, partial };
// target.save(Part, text) -> bool; it must read back what it wrote.
template<class Target>
Applied apply(const DeviceState& s, const Prepared& p, Target& target, std::string& failed) {
    failed.clear();
    const std::pair<Part, std::pair<const std::string*, const std::string*>> steps[] = {
        {Part::display, {&p.display, &s.display}}, {Part::flow, {&p.flow, &s.flow}}, {Part::plan, {&p.plan, &s.plan}},
        {Part::bluetooth, {&p.bluetooth, &s.bluetooth}}, {Part::network, {&p.network, &s.network}}};
    std::size_t done = 0;
    for (; done < sizeof steps / sizeof steps[0]; ++done) {
        const auto& step = steps[done];
        if (step.second.first->empty()) continue;
        if (!target.save(step.first, *step.second.first)) break;
    }
    if (done == sizeof steps / sizeof steps[0]) return Applied::applied;
    failed = partName(steps[done].first);
    bool restored = true;
    for (std::size_t i = done + 1; i-- > 0;) {
        const auto& step = steps[i];
        // The failed write itself may have committed before its readback failed.
        if (step.second.first->empty() || step.second.second->empty()) continue;
        if (!target.save(step.first, *step.second.second)) { restored = false; failed += ','; failed += partName(step.first); }
    }
    return restored ? Applied::restored : Applied::partial;
}

inline ControlJson summaryJson(Report& report, const Prepared& p, const std::string& fingerprint, bool sealed, bool opened) {
    ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root || !report.ok()) return ControlJson(nullptr, cJSON_Delete);
    cJSON_AddBoolToObject(root.get(), "valid", true);
    cJSON_AddStringToObject(root.get(), "fingerprint", fingerprint.c_str());
    cJSON_AddBoolToObject(root.get(), "restart", p.restart);
    cJSON_AddBoolToObject(root.get(), "secrets_sealed", sealed);
    cJSON_AddBoolToObject(root.get(), "secrets_restored", opened);
    if (p.language.empty()) cJSON_AddNullToObject(root.get(), "language"); else cJSON_AddStringToObject(root.get(), "language", p.language.c_str());
    cJSON_AddItemToObject(root.get(), "changes", report.changes.release());
    cJSON_AddItemToObject(root.get(), "warnings", report.warnings.release());
    cJSON_AddItemToObject(root.get(), "reenter", report.reenter.release());
    return root;
}
}
