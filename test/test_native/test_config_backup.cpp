// Settings backup and restore (control/ConfigBackup.h): export, strict import
// validation, the staged summary, ordered apply with rollback and a round trip
// onto a factory-reset E32. Host only; every value below is a test fixture.
#include "control/ConfigBackup.h"
#include <gtest/gtest.h>
#include <map>
#include <random>
#include <stdexcept>
#include <string>

namespace {
using namespace heating::control;
namespace b = heating::control::backup;
constexpr auto fixtureKey = "231d39c1d7cc1ab1aee224cd096db932"; // public BTHome vector, not a device secret
const std::string fakeBox(2 * (16 + 13 + 16 + 40), 'a'); // the envelope only checks the sealed box shape

std::string print(const cJSON* j) { return b::print(j); }
ControlJson parse(const std::string& s) {
    auto j = parseNestedJson(s.c_str(), s.size(), true, 12);
    if (!j) throw std::runtime_error("invalid fixture JSON: " + s.substr(0, 80));
    return j;
}
std::string bluetoothDoc(bool withKey) {
    auto previous = parse(R"({"bt":{}})");
    auto request = parse(std::string(R"({"devices":[{"address":"54:48:E6:8F:80:A5","profile":"shelly_ht_display","encryption":"bthome_v2","name":"Living","key_action":")")
        + (withKey ? std::string("set\",\"bindkey\":\"") + fixtureKey + "\"" : std::string("keep\""))
        + R"(},{"address":"a4:c1:38:00:00:01","profile":"pvvx_thermometer","encryption":"none","name":"Bath","key_action":"keep"}]})");
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed = false;
    if (prepareManagedBleSettings(previous.get(), request.get(), next, candidate, changed) != BleSettingsError::none) throw std::runtime_error("ble fixture");
    return print(candidate.get());
}
const std::string configuredNetwork = R"({"hostname":"heating-home","interface_mode":"wifi","listenPort":80,"emsEnabled":true,"emsForwarderEnabled":false,)"
    R"("rtcEnabled":true,"ntpEnabled":true,"ntpHost":"pool.ntp.org","ntpUtcOffset":0,"ntpDaylightUtcOffset":3600,"timeZone":"CET-1CEST,M3.5.0,M10.5.0/3",)"
    R"("loggerHost":"","loggerEnabled":false,"loggerPort":8701,"loggerTimeoutMs":10000,)"
    R"("mqtt":{"enabled":true,"modern_shadow":true,"adapter_id":"ha_adapter_1","publishHomeAssistantDiscovery":false,"brokerAddress":"192.0.2.10",)"
    R"("brokerPort":1883,"username":"e32","password":"broker-fixture","clientId":"e32","base":"ib-therm","keepAlive":60,"interval":30,"native_shadow_source":{"device":"bound"}},)"
    R"("openweather":{"enabled":false,"appid":"weather-fixture","latitude":"52.1","longitude":"5.1","interval":120},)"
    R"("bt":{"scanTime":60,"scanInterval":60},"vendor_extra":{"keep":1}})";
// The packaged default (data/cfg/cfgnetwork.json) of a factory-reset E32.
const std::string factoryNetwork = R"({"hostname":"","listenPort":80,"emsEnabled":true,"emsForwarderEnabled":false,"rtcEnabled":true,"ntpEnabled":true,)"
    R"("ntpHost":"pool.ntp.org","ntpUtcOffset":0,"ntpDaylightUtcOffset":3600,"timeZone":"CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00",)"
    R"("loggerHost":"","loggerEnabled":false,"loggerPort":8701,"loggerTimeoutMs":10000,)"
    R"("mqtt":{"enabled":true,"publishHomeAssistantDiscovery":false,"brokerAddress":"","brokerPort":1883,"username":"","password":"","clientId":"","base":"ib-therm","keepAlive":60,"interval":30},)"
    R"("openweather":{"enabled":false,"appid":"","latitude":"","longitude":"","interval":120},"bt":{"scanTime":60,"scanInterval":60}})";
const std::string configuredPlan = R"({"schema":1,"revision":7,"mode":"shadow","minimum_flow_c":28,"maximum_flow_c":55,"rooms":[)"
    R"({"id":"living","name":"Living room","state":"active","inactive_until":0,"emitter":"floor","sources":[{"type":"ble","id":"5448e68f80a5"},{"type":"ha","id":"sensor.living"}],)"
    R"("setpoint_entity":"climate.living","fallback_centi_c":2000,"minimum_centi_c":500,"maximum_centi_c":2500},)"
    R"({"id":"bath","name":"Bathroom","state":"inactive","inactive_until":0,"emitter":"radiator","sources":[{"type":"ble","id":"a4c138000001"}],)"
    R"("setpoint_entity":"","fallback_centi_c":2100,"minimum_centi_c":1500,"maximum_centi_c":2400}]})";

b::DeviceState configured(bool withKey = true) {
    b::DeviceState s;
    s.network = configuredNetwork; s.bluetooth = bluetoothDoc(withKey); s.plan = configuredPlan;
    s.flow = R"({"weather_curve":true,"apply_learned":false,"curve_design_flow_c":45})";
    s.display = "nefit-ecomline-classic"; s.wifiSsid = "home-fixture"; s.modernMode = true;
    return s;
}
b::DeviceState factory() {
    b::DeviceState s;
    s.network = factoryNetwork; s.bluetooth = R"({"bt":{}})";
    s.plan = R"({"schema":1,"revision":0,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[]})";
    s.flow = FlowSettings{}.json(); s.display = "none";
    return s;
}
b::Meta meta() { b::Meta m; m.firmware = "0.1.0-e32v2-beta.19"; m.board = "e32v2"; m.created = "2026-10-29T20:00:00Z"; m.language = "nl"; return m; }

// Applies like the device: each save stored, failures on request.
struct FakeTarget {
    explicit FakeTarget(b::DeviceState& state) : s(state) {}
    b::DeviceState& s;
    std::map<b::Part, int> failAt; // part -> fail the n-th save of it (1 = first)
    std::map<b::Part, int> saves;
    std::vector<std::pair<b::Part, std::string>> log;
    bool save(b::Part part, const std::string& text) {
        log.emplace_back(part, text);
        if (++saves[part] == failAt[part]) return false;
        switch (part) {
            case b::Part::display: s.display = text; break;
            case b::Part::flow: s.flow = text; break;
            case b::Part::plan: { // as setHeatingPlan: a new revision on top of the current one
                auto root = parse(text); RoomPlan current, next;
                if (RoomPlan::parse(parse(s.plan).get(), current) || RoomPlan::parse(root.get(), next)) return false;
                next.revision = current.revision + 1; s.plan = next.json(); break;
            }
            case b::Part::bluetooth: s.bluetooth = text; break;
            case b::Part::network: s.network = text; break;
        }
        return true;
    }
};
std::string request(const std::string& action, const cJSON* backup, const std::string& extra = "") {
    return "{\"action\":\"" + action + "\",\"backup\":" + print(backup) + extra + "}";
}
struct Validated {
    const char* error = nullptr;
    b::Prepared prepared;
    b::Report report;
    std::string sealed;
};
Validated validate(const std::string& body, const b::DeviceState& onto, const b::Secrets* secrets = nullptr) {
    Validated v;
    b::Request r;
    if ((v.error = b::readRequest(body.c_str(), body.size(), r))) return v;
    if ((v.error = b::checkEnvelope(r.backup, meta(), v.report, v.sealed))) return v;
    b::Secrets none;
    v.error = b::prepare(r.backup, onto, secrets ? *secrets : none, v.prepared, v.report);
    return v;
}
bool has(const cJSON* list, const std::string& value) {
    for (auto i = list ? list->child : nullptr; i; i = i->next) if (cJSON_IsString(i) && value == i->valuestring) return true;
    return false;
}
std::string field(const std::string& doc, const char* section, const char* key) {
    auto j = parse(doc); auto o = section ? b::item(j.get(), section) : j.get();
    auto v = b::item(o, key);
    return v ? print(v) : "<absent>";
}
}

TEST(ConfigBackup, ExportCarriesSettingsButNoSecret) {
    const auto s = configured();
    auto doc = b::exportDocument(s, meta(), "");
    ASSERT_TRUE(doc);
    const auto text = print(doc.get());
    EXPECT_EQ(b::text(b::item(doc.get(), "format")), "openthermostat-e32-backup");
    EXPECT_EQ(b::item(doc.get(), "schema")->valueint, 1);
    EXPECT_EQ(b::text(b::item(doc.get(), "board")), "e32v2");
    EXPECT_EQ(b::text(b::item(doc.get(), "created")), "2026-10-29T20:00:00Z");
    EXPECT_TRUE(cJSON_IsNull(b::item(doc.get(), "secrets")));
    for (const char* secret : {"broker-fixture", "weather-fixture", fixtureKey, "\"password\"", "appid", "bindkey", "native_shadow_source", "vendor_extra", "revision"})
        EXPECT_EQ(text.find(secret), std::string::npos) << secret;
    const auto missing = b::item(doc.get(), "not_included");
    for (const char* name : {"wifi_password", "web_password", "mqtt_password", "openweather_key", "bluetooth_keys"}) EXPECT_TRUE(has(missing, name)) << name;
    EXPECT_EQ(b::text(b::item(b::item(b::item(doc.get(), "network"), "mqtt"), "brokerAddress")), "192.0.2.10");
    EXPECT_EQ(cJSON_GetArraySize(b::item(b::item(doc.get(), "bluetooth"), "devices")), 2);
    EXPECT_EQ(b::text(b::item(b::item(doc.get(), "wifi"), "ssid")), "home-fixture");
    EXPECT_EQ(b::text(b::item(b::item(doc.get(), "ui"), "language")), "nl");
    EXPECT_EQ(b::text(b::item(b::item(doc.get(), "boiler_display"), "model")), "nefit-ecomline-classic");
    EXPECT_LT(text.size(), b::maxBytes);
}

TEST(ConfigBackup, SecretsDocumentHoldsOnlyTheSecrets) {
    const auto plain = b::secretsDocument(configured());
    auto j = parse(plain);
    EXPECT_EQ(b::text(b::item(j.get(), "mqtt_password")), "broker-fixture");
    EXPECT_EQ(b::text(b::item(j.get(), "openweather_key")), "weather-fixture");
    EXPECT_EQ(b::text(b::item(b::item(j.get(), "bluetooth_keys"), "5448e68f80a5")), fixtureKey);
    EXPECT_EQ(b::secretsDocument(factory()), "");
    b::Secrets read;
    ASSERT_EQ(b::readSecrets(plain, read), nullptr);
    EXPECT_TRUE(read.present);
    EXPECT_EQ(read.mqttPassword, "broker-fixture");
    ASSERT_EQ(read.bleKeys.size(), 1u);
    for (const char* bad : {"", "[]", R"({"other":1})", R"({"mqtt_password":1})", R"({"bluetooth_keys":{"zz":"00"}})",
                            R"({"bluetooth_keys":{"5448e68f80a5":"abc"}})"}) {
        b::Secrets s; EXPECT_NE(b::readSecrets(bad, s), nullptr) << bad; EXPECT_FALSE(s.present);
    }
}

// Done when: restoring onto a new or factory-reset E32 works.
TEST(ConfigBackup, RoundTripOntoFactoryResetDevice) {
    const auto source = configured();
    auto doc = b::exportDocument(source, meta(), "");
    auto target = factory();
    target.ethernetUp = false;
    const auto v = validate(request("validate", doc.get()), target);
    ASSERT_EQ(v.error, nullptr) << print(v.report.warnings.get());
    EXPECT_TRUE(v.prepared.restart);
    EXPECT_EQ(v.prepared.language, "nl");
    EXPECT_TRUE(has(v.report.warnings.get(), "wifi_not_restored"));
    // A new broker without its password: MQTT stays off until it is entered.
    EXPECT_TRUE(has(v.report.reenter.get(), "mqtt_password"));
    EXPECT_TRUE(has(v.report.reenter.get(), "bluetooth_key:Living"));
    FakeTarget fake{target};
    std::string failed;
    ASSERT_EQ(b::apply(target, v.prepared, fake, failed), b::Applied::applied) << failed;
    // Every section equals the source again, apart from the secrets and the
    // device-bound SOURCE profile.
    auto again = b::exportDocument(target, meta(), "");
    for (const char* sec : {"bluetooth", "heating", "flow", "boiler_display"})
        EXPECT_EQ(print(b::item(again.get(), sec)), print(b::item(doc.get(), sec))) << sec;
    auto a = parse(print(b::item(doc.get(), "network"))), c = parse(print(b::item(again.get(), "network")));
    cJSON_ReplaceItemInObjectCaseSensitive(cJSON_GetObjectItemCaseSensitive(a.get(), "mqtt"), "enabled", cJSON_CreateFalse());
    EXPECT_EQ(print(c.get()), print(a.get()));
    EXPECT_EQ(field(target.network, "mqtt", "password"), "\"\"");
    EXPECT_EQ(field(target.network, "mqtt", "native_shadow_source"), "<absent>");
    // The restored plan is a new revision on this device.
    EXPECT_EQ(field(target.plan, nullptr, "revision"), "1");
}

TEST(ConfigBackup, RoundTripWithSealedSecretsRestoresKeysAndPasswords) {
    const auto source = configured();
    auto doc = b::exportDocument(source, meta(), fakeBox);
    b::Secrets secrets;
    ASSERT_EQ(b::readSecrets(b::secretsDocument(source), secrets), nullptr);
    auto target = factory();
    const auto v = validate(request("validate", doc.get()), target, &secrets);
    ASSERT_EQ(v.error, nullptr) << print(v.report.warnings.get());
    EXPECT_FALSE(has(v.report.reenter.get(), "mqtt_password"));
    EXPECT_FALSE(has(v.report.reenter.get(), "bluetooth_key:Living"));
    FakeTarget fake{target};
    std::string failed;
    ASSERT_EQ(b::apply(target, v.prepared, fake, failed), b::Applied::applied);
    EXPECT_EQ(b::secretsDocument(target), b::secretsDocument(source));
    EXPECT_EQ(field(target.network, "mqtt", "enabled"), "true");
}

TEST(ConfigBackup, RestoreOntoTheSameDeviceChangesNothing) {
    const auto s = configured();
    auto doc = b::exportDocument(s, meta(), "");
    const auto v = validate(request("validate", doc.get()), s);
    ASSERT_EQ(v.error, nullptr) << print(v.report.warnings.get());
    EXPECT_TRUE(v.prepared.network.empty()); EXPECT_TRUE(v.prepared.bluetooth.empty());
    EXPECT_TRUE(v.prepared.plan.empty()); EXPECT_TRUE(v.prepared.flow.empty()); EXPECT_TRUE(v.prepared.display.empty());
    EXPECT_FALSE(v.prepared.restart);
    EXPECT_EQ(cJSON_GetArraySize(v.report.changes.get()), 0);
    // The stored password and key stay for the same broker and the same sensor.
    EXPECT_EQ(cJSON_GetArraySize(v.report.reenter.get()), 0);
}

TEST(ConfigBackup, SummaryListsChangesWithoutSecretValues) {
    auto s = configured(), onto = factory();
    b::Secrets secrets; ASSERT_EQ(b::readSecrets(b::secretsDocument(s), secrets), nullptr);
    auto doc = b::exportDocument(s, meta(), fakeBox);
    auto v = validate(request("validate", doc.get()), onto, &secrets);
    ASSERT_EQ(v.error, nullptr);
    const auto changes = print(v.report.changes.get());
    EXPECT_NE(changes.find("\"field\":\"hostname\""), std::string::npos);
    EXPECT_NE(changes.find("\"field\":\"mqtt.password\",\"hidden\":true"), std::string::npos);
    EXPECT_NE(changes.find("Living room"), std::string::npos);
    EXPECT_EQ(changes.find("broker-fixture"), std::string::npos);
    EXPECT_EQ(changes.find(fixtureKey), std::string::npos);
    const auto summary = b::summaryJson(v.report, v.prepared, "f", true, true);
    ASSERT_TRUE(summary);
    EXPECT_TRUE(cJSON_IsTrue(b::item(summary.get(), "restart")));
    EXPECT_EQ(print(summary.get()).find("broker-fixture"), std::string::npos);
}

TEST(ConfigBackup, EnvelopeIsStrict) {
    auto doc = b::exportDocument(configured(), meta(), "");
    const auto with = [&](const char* key, cJSON* value) {
        auto copy = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
        if (value) b::put(copy.get(), key, value); else cJSON_DeleteItemFromObjectCaseSensitive(copy.get(), key);
        return validate(request("validate", copy.get()), factory()).error;
    };
    EXPECT_STREQ(with("format", cJSON_CreateString("other")), "not_a_backup");
    EXPECT_STREQ(with("format", nullptr), "not_a_backup");
    EXPECT_STREQ(with("schema", cJSON_CreateNumber(2)), "newer_schema");
    EXPECT_STREQ(with("schema", cJSON_CreateNumber(1.5)), "invalid_schema");
    EXPECT_STREQ(with("schema", cJSON_CreateString("1")), "invalid_schema");
    EXPECT_STREQ(with("board", cJSON_CreateString("esp32dev")), "other_board");
    EXPECT_STREQ(with("network", cJSON_CreateArray()), "invalid_section");
    EXPECT_STREQ(with("secrets", cJSON_CreateString("x")), "invalid_secrets");
    EXPECT_STREQ(with("created", cJSON_CreateNumber(1)), "invalid_created");
    EXPECT_EQ(with("future_section", cJSON_CreateObject()), nullptr); // a warning, not an error
    auto copy = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
    b::put(copy.get(), "future_section", cJSON_CreateObject());
    const auto v = validate(request("validate", copy.get()), factory());
    EXPECT_TRUE(has(v.report.warnings.get(), "unknown_key:future_section"));
    // A sealed box must be well formed hex of a plausible size.
    auto box = cJSON_CreateObject();
    cJSON_AddStringToObject(box, "cipher", "aes-128-ccm"); cJSON_AddStringToObject(box, "kdf", "pbkdf2-sha256");
    cJSON_AddNumberToObject(box, "iterations", b::kdfIterations); cJSON_AddStringToObject(box, "box", "zz");
    EXPECT_STREQ(with("secrets", box), "invalid_secrets");
}

TEST(ConfigBackup, RequestIsBounded) {
    b::Request r;
    EXPECT_STREQ(b::readRequest("", 0, r), "backup_too_large");
    const std::string huge(b::maxRequestBytes + 1, ' ');
    EXPECT_STREQ(b::readRequest(huge.c_str(), huge.size(), r), "backup_too_large");
    for (const char* bad : {"[]", "{\"action\":\"delete\"}", "{\"action\":\"export\",\"backup\":{}}", "{\"action\":\"validate\"}",
                            "{\"action\":\"validate\",\"backup\":[]}", "{\"action\":\"export\",\"extra\":1}",
                            "{\"action\":\"validate\",\"backup\":{},\"fingerprint\":\"x\"}", "{\"action\":\"export\",\"passphrase\":\"short\"}",
                            "{\"action\":\"export\"} trailing"}) {
        b::Request q; EXPECT_NE(b::readRequest(bad, std::strlen(bad), q), nullptr) << bad;
    }
    const std::string deep = "{\"action\":\"validate\",\"backup\":" + std::string(40, '[') + std::string(40, ']') + "}";
    b::Request q; EXPECT_NE(b::readRequest(deep.c_str(), deep.size(), q), nullptr);
    const char* ok = "{\"action\":\"export\",\"passphrase\":\"long enough\",\"language\":\"nl\"}";
    b::Request e; ASSERT_EQ(b::readRequest(ok, std::strlen(ok), e), nullptr);
    EXPECT_EQ(e.passphrase, "long enough"); EXPECT_EQ(e.language, "nl");
}

TEST(ConfigBackup, NetworkFieldsAreTypeAndRangeChecked) {
    auto doc = b::exportDocument(configured(), meta(), "");
    const auto network = [&](const char* sec, const char* key, cJSON* value) {
        auto copy = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
        auto net = cJSON_GetObjectItemCaseSensitive(copy.get(), "network");
        b::put(sec ? cJSON_GetObjectItemCaseSensitive(net, sec) : net, key, value);
        return validate(request("validate", copy.get()), factory());
    };
    EXPECT_STREQ(network(nullptr, "listenPort", cJSON_CreateNumber(70000)).error, "invalid_network");
    EXPECT_STREQ(network(nullptr, "hostname", cJSON_CreateString(std::string(64, 'a').c_str())).error, "invalid_network");
    EXPECT_STREQ(network(nullptr, "hostname", cJSON_CreateString("a\nb")).error, "invalid_network");
    EXPECT_STREQ(network(nullptr, "interface_mode", cJSON_CreateString("cellular")).error, "invalid_network");
    EXPECT_STREQ(network("mqtt", "brokerPort", cJSON_CreateString("1883")).error, "invalid_network");
    EXPECT_STREQ(network("mqtt", "enabled", cJSON_CreateNumber(1)).error, "invalid_network");
    EXPECT_STREQ(network("mqtt", "adapter_id", cJSON_CreateString("bad id")).error, "invalid_adapter_id");
    EXPECT_STREQ(network(nullptr, "mqtt", cJSON_CreateString("x")).error, "invalid_network");
    const auto unknown = network("mqtt", "password", cJSON_CreateString("smuggled"));
    ASSERT_EQ(unknown.error, nullptr);
    EXPECT_TRUE(has(unknown.report.warnings.get(), "unknown_key:network.mqtt.password"));
    EXPECT_EQ(unknown.prepared.network.find("smuggled"), std::string::npos);
    const auto devices = network("bt", "devices", parse(R"({"schema":1,"items":[]})").release());
    ASSERT_EQ(devices.error, nullptr);
    EXPECT_TRUE(has(devices.report.warnings.get(), "unknown_key:network.bt.devices"));
}

TEST(ConfigBackup, NetworkRestoreCannotLockTheOwnerOut) {
    auto source = configured();
    auto net = parse(source.network);
    b::put(net.get(), "interface_mode", cJSON_CreateString("ethernet"));
    b::put(net.get(), "listenPort", cJSON_CreateNumber(8080));
    source.network = print(net.get());
    auto doc = b::exportDocument(source, meta(), "");
    auto onto = factory();
    auto v = validate(request("validate", doc.get()), onto);
    ASSERT_EQ(v.error, nullptr);
    EXPECT_TRUE(has(v.report.warnings.get(), "interface_kept"));
    EXPECT_TRUE(has(v.report.warnings.get(), "listen_port_kept"));
    EXPECT_EQ(field(v.prepared.network, nullptr, "interface_mode"), "<absent>");
    EXPECT_EQ(field(v.prepared.network, nullptr, "listenPort"), "80");
    // Ethernet is accepted while an Ethernet link carries the network.
    onto.ethernetUp = true;
    v = validate(request("validate", doc.get()), onto);
    ASSERT_EQ(v.error, nullptr);
    EXPECT_EQ(field(v.prepared.network, nullptr, "interface_mode"), "\"ethernet\"");
}

TEST(ConfigBackup, RestoreIsRefusedWhileTheE32OwnsTheBoiler) {
    auto doc = b::exportDocument(configured(), meta(), "");
    auto onto = factory(); onto.boilerClaimed = true;
    EXPECT_STREQ(validate(request("validate", doc.get()), onto).error, "boiler_owned");
}

TEST(ConfigBackup, PlanIsAlwaysRestoredInShadowMode) {
    auto source = configured();
    auto plan = parse(source.plan); b::put(plan.get(), "mode", cJSON_CreateString("active"));
    source.plan = print(plan.get());
    auto doc = b::exportDocument(source, meta(), "");
    const auto v = validate(request("validate", doc.get()), factory());
    ASSERT_EQ(v.error, nullptr);
    EXPECT_TRUE(has(v.report.warnings.get(), "plan_mode_shadow"));
    EXPECT_EQ(field(v.prepared.plan, nullptr, "mode"), "\"shadow\"");
    // Invalid rooms are refused with the RoomPlan error as the reason.
    auto bad = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
    auto rooms = cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(bad.get(), "heating"), "rooms");
    b::put(cJSON_GetArrayItem(rooms, 0), "minimum_centi_c", cJSON_CreateNumber(100));
    const auto r = validate(request("validate", bad.get()), factory());
    EXPECT_STREQ(r.error, "heating_invalid");
    EXPECT_TRUE(has(r.report.warnings.get(), "heating:invalid_room_limits"));
}

TEST(ConfigBackup, BluetoothRowsUseTheBluetoothValidator) {
    auto doc = b::exportDocument(configured(), meta(), "");
    auto bad = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
    auto devices = cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(bad.get(), "bluetooth"), "devices");
    b::put(cJSON_GetArrayItem(devices, 0), "address", cJSON_CreateString("ff:ff:ff:ff:ff:ff"));
    const auto v = validate(request("validate", bad.get()), factory());
    EXPECT_STREQ(v.error, "bluetooth_invalid");
    EXPECT_TRUE(has(v.report.warnings.get(), "bluetooth:invalid_device_address"));
    b::put(cJSON_GetArrayItem(devices, 0), "address", cJSON_CreateString("54:48:E6:8F:80:A5"));
    b::put(cJSON_GetArrayItem(devices, 0), "key_action", cJSON_CreateString("set")); // not a backup field
    const auto w = validate(request("validate", bad.get()), factory());
    ASSERT_EQ(w.error, nullptr);
    EXPECT_TRUE(has(w.report.warnings.get(), "unknown_key:bluetooth.devices.key_action"));
}

TEST(ConfigBackup, FlowAndDisplayIgnoreUnknownButRefuseInvalidValues) {
    auto doc = b::exportDocument(configured(), meta(), "");
    auto copy = ControlJson(cJSON_Duplicate(doc.get(), true), cJSON_Delete);
    auto flow = cJSON_GetObjectItemCaseSensitive(copy.get(), "flow");
    b::put(flow, "future_option", cJSON_CreateTrue());
    b::put(cJSON_GetObjectItemCaseSensitive(copy.get(), "boiler_display"), "model", cJSON_CreateString("future-boiler"));
    auto v = validate(request("validate", copy.get()), factory());
    ASSERT_EQ(v.error, nullptr);
    EXPECT_TRUE(has(v.report.warnings.get(), "unknown_key:flow.future_option"));
    EXPECT_TRUE(has(v.report.warnings.get(), "unknown_boiler_model:future-boiler"));
    EXPECT_TRUE(v.prepared.display.empty());
    EXPECT_EQ(field(v.prepared.flow, nullptr, "curve_design_flow_c"), "45");
    b::put(flow, "curve_design_flow_c", cJSON_CreateNumber(99));
    EXPECT_STREQ(validate(request("validate", copy.get()), factory()).error, "flow_invalid_value");
}

TEST(ConfigBackup, FailedApplyRestoresTheOldSettings) {
    const auto source = configured();
    auto doc = b::exportDocument(source, meta(), "");
    const auto before = factory();
    auto target = before;
    const auto v = validate(request("validate", doc.get()), target);
    ASSERT_EQ(v.error, nullptr);
    for (auto part : {b::Part::display, b::Part::flow, b::Part::plan, b::Part::bluetooth, b::Part::network}) {
        target = before;
        FakeTarget fake{target};
        fake.failAt[part] = 1;
        std::string failed;
        EXPECT_EQ(b::apply(before, v.prepared, fake, failed), b::Applied::restored) << b::partName(part);
        EXPECT_EQ(failed, b::partName(part));
        EXPECT_EQ(target.network, before.network); EXPECT_EQ(target.bluetooth, before.bluetooth);
        EXPECT_EQ(target.flow, before.flow); EXPECT_EQ(target.display, before.display);
        RoomPlan was, now;
        ASSERT_EQ(RoomPlan::parse(parse(before.plan).get(), was), nullptr);
        ASSERT_EQ(RoomPlan::parse(parse(target.plan).get(), now), nullptr);
        was.revision = now.revision = 0;
        EXPECT_EQ(now.json(), was.json()) << b::partName(part);
    }
    // A rollback that fails too is reported, never hidden.
    target = before;
    FakeTarget fake{target};
    fake.failAt[b::Part::network] = 1; fake.failAt[b::Part::plan] = 2;
    std::string failed;
    EXPECT_EQ(b::apply(before, v.prepared, fake, failed), b::Applied::partial);
    EXPECT_EQ(failed, "network,heating");
}

TEST(ConfigBackup, FingerprintCoversDeviceAndCandidates) {
    auto doc = b::exportDocument(configured(), meta(), "");
    auto onto = factory();
    const auto v = validate(request("validate", doc.get()), onto);
    ASSERT_EQ(v.error, nullptr);
    const auto a = b::fingerprintInput(onto, v.prepared);
    auto changed = onto; changed.display = "emsesp-product-8";
    EXPECT_NE(b::fingerprintInput(changed, v.prepared), a);
    auto other = v.prepared; other.flow.clear();
    EXPECT_NE(b::fingerprintInput(onto, other), a);
}

// Fuzz-style: byte flips, truncations and splices of a valid request never
// crash, and whatever is accepted is valid for the real readers.
TEST(ConfigBackup, MalformedBackupsNeverYieldInvalidCandidates) {
    auto doc = b::exportDocument(configured(), meta(), "");
    const auto valid = request("validate", doc.get());
    std::mt19937 random(23);
    const std::string alphabet = "{}[]\",:0123456789-.eEtruefalsn \\u";
    int accepted = 0;
    for (int i = 0; i < 4000; ++i) {
        std::string body = valid;
        const int edits = 1 + int(random() % 4);
        for (int e = 0; e < edits && !body.empty(); ++e) {
            const auto at = random() % body.size();
            switch (random() % 4) {
                case 0: body[at] = alphabet[random() % alphabet.size()]; break;
                case 1: body.erase(at, 1 + random() % 8); break;
                case 2: body.insert(at, 1, alphabet[random() % alphabet.size()]); break;
                default: body.resize(at); break;
            }
        }
        const auto v = validate(body, factory());
        if (v.error) continue;
        ++accepted;
        if (!v.prepared.network.empty()) {
            auto n = parse(v.prepared.network);
            EXPECT_TRUE(nativeNetworkSettingsBytesFit(v.prepared.network));
            EXPECT_FALSE(networkSettingsContainManagedBleBindings(n.get()));
        }
        if (!v.prepared.bluetooth.empty()) {
            ManagedBleBindings bindings;
            EXPECT_EQ(readManagedBleBindings(parse(v.prepared.bluetooth).get(), bindings), BleSettingsError::none);
        }
        if (!v.prepared.plan.empty()) {
            RoomPlan plan;
            EXPECT_EQ(RoomPlan::parse(parse(v.prepared.plan).get(), plan), nullptr);
            EXPECT_EQ(plan.mode, RoomPlan::Mode::shadow);
        }
        if (!v.prepared.flow.empty()) { FlowSettings f; EXPECT_EQ(FlowSettings::parse(parse(v.prepared.flow).get(), f), nullptr); }
    }
    EXPECT_GT(accepted, 0);
}

TEST(ConfigBackup, CreatedTimeIsUtcText) {
    EXPECT_EQ(b::utcText(1704067200), "2024-01-01T00:00:00Z");
    EXPECT_EQ(b::utcText(1761768000), "2025-10-29T20:00:00Z");
    EXPECT_EQ(b::utcText(1709251199), "2024-02-29T23:59:59Z"); // leap day
    EXPECT_EQ(b::utcText(0), "");          // no NTP yet
    EXPECT_EQ(b::utcText(1704067199), "");
}
