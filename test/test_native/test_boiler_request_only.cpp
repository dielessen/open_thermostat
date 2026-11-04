// rc.5 (owner, 4 Nov 2026): the EMS values the E32 only sees when someone asks for them stay shown,
// with a remark. The 23 Classic fields of 0x16 UBAParameters and 0x33 UBAParameterWW are request-only
// (requestOnlyTtlMs, 0: valid once read this boot, never expiring), and so are the entity table's
// 0xE6/0xEA settings, error records (0x10/0x11) and uptime (0x14) (requestOnlyTtl); every status or
// live value keeps its lifetime.
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/EmsEntityCatalog.h"
#include "control/BoilerStateTelemetry.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <cstdio>
#include <initializer_list>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>

namespace {
using namespace heating::ems;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

// The request-only settings by name; Home Assistant mirrors exactly these (boiler_fields.py FIELDS, REQUEST_ONLY).
const std::set<std::string> requestOnlySettings{
    "selected_dhw_temperature", "heating_enabled", "dhw_enabled", "maximum_burner_power", "pump_run_on",
    "configured_heating_temperature", "heating_hysteresis_off", "heating_hysteresis_on", "minimum_burner_period",
    "pump_modulation_maximum", "pump_modulation_minimum", "configured_pump_mode", "secondary_heating_hysteresis_off",
    "secondary_heating_hysteresis_on", "pump_start_temperature", "dhw_hysteresis_on", "dhw_charge_optimisation_enabled",
    "dhw_flow_temperature_offset", "dhw_circulation_enabled", "configured_dhw_circulation_mode",
    "dhw_disinfection_temperature", "configured_dhw_charge_type", "configured_dhw_comfort_mode"};
constexpr uint64_t hour = 3600000, day = 24 * hour;

EmsTelegram fromBoiler(uint16_t type, std::vector<uint8_t> payload, uint8_t offset = 0, uint8_t destination = 0) {
    return {destination ? EmsTelegram::WRITE : EmsTelegram::BROADCAST, 8, destination, offset, type, std::move(payload)};
}
Json parse(const std::string& text) { return Json(cJSON_Parse(text.c_str()), cJSON_Delete); }
const cJSON* fieldOf(const cJSON* doc, const char* name) {
    return cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(doc, "fields"), name);
}
const cJSON* row(const cJSON* values, size_t index) {
    for (const cJSON* r = cJSON_GetObjectItemCaseSensitive(values, "fields")->child; r; r = r->next)
        if (cJSON_GetArrayItem(r, 0)->valuedouble == index) return r;
    return nullptr;
}
// The boiler fields route index of an entity table field (catalogFieldBase + its field number).
size_t catalogIndex(std::string_view id) {
    for (size_t f = 0; f < entityFieldCount; ++f)
        if (std::string_view(entityCatalog[entityFieldRows[f]].id) == id) return heating::control::catalogFieldBase + f;
    ADD_FAILURE() << id;
    return 0;
}
// The request-only entity fields: the EMS+ twins of the Classic settings, the error records and the uptime.
const std::set<std::string> requestOnlyEntities{
    "plus_dhw_selected_temperature", "plus_heating_temperature", "plus_maximum_burner_power",
    "last_locking_error_code", "last_locking_error_number", "last_blocking_error_code", "last_blocking_error_number",
    "boiler_uptime"};
}

TEST(BoilerRequestOnly, TheCatalogMarksExactlyThe23SettingsOf0x16And0x33) {
    std::set<std::string> marked;
    for (size_t i = 0; i < boilerFieldSpecs.size(); ++i) {
        const auto& spec = boilerFieldSpecs[i];
        if (spec.requestOnly()) marked.insert(spec.name);
        // A request-only setting has no lifetime; every other field keeps one.
        EXPECT_EQ(spec.requestOnly(), spec.ttlMs == requestOnlyTtlMs) << spec.name;
        EXPECT_EQ(spec.requestOnly(), heating::control::boilerFieldSourceTypes[i] == 0x16
                  || heating::control::boilerFieldSourceTypes[i] == 0x33) << spec.name;
        if (!spec.requestOnly()) EXPECT_GE(spec.ttlMs, 30000u) << spec.name;
    }
    EXPECT_EQ(marked, requestOnlySettings);
    EXPECT_EQ(marked.size(), 23u);
}

TEST(BoilerRequestOnly, ASettingReadOnceNeverExpiresALiveReadingStillDoes) {
    ClassicBoilerMonitor m;
    // The boiler's answer to the E32's own 0x16 read at start-up (EMS/BoilerLimitRead.h): heating on, 62 degC.
    ASSERT_TRUE(m.receive(fromBoiler(0x16, {0xFF, 62}, 0, 0x0B), 60000));
    ASSERT_TRUE(m.receive(fromBoiler(0x18, {40, 0x01, 0xC8}), 60000)); // selected 40 degC, flow 45.6 degC
    EXPECT_FALSE(m.value(BoilerField::heatingLimit, 59999)) << "never before it arrived";
    EXPECT_EQ(m.value(BoilerField::flow, 60000 + 29999), 4560);
    EXPECT_FALSE(m.value(BoilerField::flow, 60000 + 30000)) << "a live reading keeps its 30 s";
    EXPECT_FALSE(m.value(BoilerField::selectedFlow, 60000 + 30000));
    for (const uint64_t later : std::initializer_list<uint64_t>{10 * 60000, day + 1, 60 * day}) {
        EXPECT_EQ(m.value(BoilerField::heatingLimit, 60000 + later), 6200) << later;
        EXPECT_EQ(m.value(BoilerField::heatingEnabled, 60000 + later), 1) << later;
    }
    // A newer read replaces it (the 6 h refresh, or someone changed the setting at the boiler).
    ASSERT_TRUE(m.receive(fromBoiler(0x16, {0xFF, 55}, 0, 0x0B), 60000 + 6 * hour));
    EXPECT_EQ(m.value(BoilerField::heatingLimit, 60000 + 7 * hour), 5500);
    EXPECT_EQ(m.sample(BoilerField::heatingLimit).observedMs, 60000 + 6 * hour);
    // The legacy projection (Home, About) keeps showing it as well.
    std::ostringstream legacy; m.writeLegacyStatus(legacy, 60000 + 3 * day);
    const auto status = parse(legacy.str());
    ASSERT_TRUE(status);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(status.get(), "heatingEnabled")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(status.get(), "currentFlowTemperature")));
    // The reception lists the setting among the valid Classic fields, the expired readings not.
    std::ostringstream reception; m.writeReceptionJSON(reception, 60000 + 3 * day);
    const auto r = parse(reception.str());
    ASSERT_TRUE(r);
    std::set<std::string> fresh;
    for (const cJSON* f = cJSON_GetObjectItemCaseSensitive(r.get(), "fresh_classic_fields")->child; f; f = f->next) fresh.insert(f->valuestring);
    EXPECT_EQ(fresh, (std::set<std::string>{"heating_enabled", "configured_heating_temperature"}));
}

TEST(BoilerRequestOnly, AnInvalidSettingStaysNoValueAndAnUnreadOneUnknown) {
    ClassicBoilerMonitor m;
    m.receive(fromBoiler(0x33, {0x7F}, 3), 1000);  // the hysteresis sentinel: invalid
    m.receive(fromBoiler(0x33, {7}, 9), 1000);     // a comfort mode outside the known codes
    EXPECT_FALSE(m.value(BoilerField::dhwHysteresisOn, 2 * day));
    EXPECT_FALSE(m.value(BoilerField::dhwComfortMode, 2 * day));
    std::ostringstream out; m.writeJSON(out, 2 * day);
    const auto doc = parse(out.str());
    ASSERT_TRUE(doc);
    for (const char* name : {"dhw_hysteresis_on", "configured_dhw_comfort_mode"}) {
        EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(fieldOf(doc.get(), name), "state")), "invalid") << name;
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(fieldOf(doc.get(), name), "value"))) << name;
    }
    // Never read this boot: unknown, without an age; the marker still says what kind of value it is.
    const auto* unread = fieldOf(doc.get(), "configured_heating_temperature");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(unread, "state")), "unknown");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(unread, "age_ms")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(unread, "request_only")));
}

TEST(BoilerRequestOnly, TheBoilerDataJsonMarksTheSettingsAndKeepsTheirReadAge) {
    ClassicBoilerMonitor m;
    // Every family once at start-up (as ClassicExpanded.All69FieldsSerialize...), then two days without a report.
    for (auto type : {0x18, 0x19, 0x16, 0x33, 0x34}) m.receive(fromBoiler(type, std::vector<uint8_t>(27, 0)), 100);
    const uint64_t now = 100 + 2 * day;
    std::ostringstream out; m.writeJSON(out, now);
    const std::string text = out.str();
    const auto doc = parse(text);
    ASSERT_TRUE(doc);
    size_t marked = 0;
    for (const cJSON* f = cJSON_GetObjectItemCaseSensitive(doc.get(), "fields")->child; f; f = f->next) {
        const cJSON* flag = cJSON_GetObjectItemCaseSensitive(f, "request_only");
        const std::string state = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(f, "state"));
        EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(f, "age_ms")), double(2 * day)) << f->string;
        EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(f, "observed_at_ms")), 100) << f->string;
        if (requestOnlySettings.count(f->string)) {
            ++marked;
            EXPECT_TRUE(cJSON_IsTrue(flag)) << f->string;
            EXPECT_EQ(state, "valid") << f->string;
            EXPECT_TRUE(cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(f, "value"))) << f->string;
        } else {
            EXPECT_EQ(flag, nullptr) << f->string << ": only a request-only field carries the marker";
            EXPECT_NE(state, "valid") << f->string;
            EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(f, "value"))) << f->string;
        }
    }
    EXPECT_EQ(marked, 23u);
    size_t markers = 0;
    for (auto at = text.find("\"request_only\":true"); at != std::string::npos; at = text.find("\"request_only\":true", at + 1)) ++markers;
    EXPECT_EQ(markers, 23u) << "one flag per setting (20 B each), no list";
    // The document keeps the budget of ClassicExpanded.All69FieldsSerialize... (/status/ems/telemetry: 64 KB).
    std::printf("[ boiler data ] 69 fields, 23 request-only markers: %zu B\n", text.size());
    EXPECT_LT(text.size(), 18000u);
}

TEST(BoilerRequestOnly, RetainedGroupsKeepASettingAndNullAnExpiredReadingWithoutANewMarker) {
    using namespace heating::control;
    ClassicBoilerMonitor m;
    ASSERT_TRUE(m.receive(fromBoiler(0x18, {40, 0x01, 0xC8}), 100));
    ASSERT_TRUE(m.receive(fromBoiler(0x16, {0xFF, 62, 85}, 0, 0x0B), 100)); // heating on, 62 degC, 85 %
    const uint64_t now = 100 + day;
    // fw/state/boiler_fields/<g>: group 0 holds the flow (index 1), group 1 heating on (16),
    // group 2 the burner power (26) and the heating temperature (28).
    std::string raw[3];
    for (size_t g = 0; g < 3; ++g) { std::ostringstream out; m.writeFieldGroup(out, now, g); raw[g] = out.str(); }
    Json live(boilerGroupValues(raw[0], 0), cJSON_Delete), on(boilerGroupValues(raw[1], 1), cJSON_Delete),
        settings(boilerGroupValues(raw[2], 2), cJSON_Delete);
    ASSERT_TRUE(live); ASSERT_TRUE(on); ASSERT_TRUE(settings);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetArrayItem(row(live.get(), 1), 1))) << "the expired flow goes out as null";
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row(live.get(), 1), 2)), 100) << "with its original observation";
    for (const auto& [values, index, value] : std::initializer_list<std::tuple<const cJSON*, size_t, double>>{
             {on.get(), 16, 1}, {settings.get(), 26, 85}, {settings.get(), 28, 6200}}) {
        const cJSON* r = row(values, index);
        ASSERT_TRUE(r) << index;
        EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(r, 1)), value) << index;
        // Home Assistant's read age: sampled_at_ms minus observed_ms.
        EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(values, "sampled_at_ms"))
                  - cJSON_GetNumberValue(cJSON_GetArrayItem(r, 2)), double(day)) << index;
    }
    // The wire keeps exactly the shape every Home Assistant release validates: four keys, five-element rows.
    for (const auto* values : {live.get(), on.get(), settings.get()}) {
        EXPECT_EQ(cJSON_GetArraySize(values), 4);
        for (const cJSON* r = cJSON_GetObjectItemCaseSensitive(values, "fields")->child; r; r = r->next) EXPECT_EQ(cJSON_GetArraySize(r), 5);
    }
    EXPECT_TRUE(validBoilerGroup(settings.get(), 2, true));
    Json envelope(boilerEnvelope(cJSON_Duplicate(settings.get(), true), 2), cJSON_Delete);
    ASSERT_TRUE(envelope);
    EXPECT_EQ(cJSON_GetArraySize(envelope.get()), 3);
    for (const auto& text : raw) EXPECT_EQ(text.find("request_only"), std::string::npos);
    // The lifetimes the retained state applies: none for a setting, the catalog's for the rest.
    EXPECT_FALSE(boilerFieldTtlMs(28).has_value());
    EXPECT_EQ(boilerFieldTtlMs(1).value_or(0), 30000u);
    EXPECT_EQ(boilerFieldTtlMs(catalogIndex("maintenance_message")).value_or(0), 600000u) << "maintenance_message stays a status value";
}

TEST(BoilerRequestOnly, TheEntityTableMarksTheAskedTelegramsAndNothingElse) {
    std::set<std::string> marked;
    for (const auto& spec : entityCatalog) {
        if (spec.requestOnly()) marked.insert(spec.id);
        EXPECT_EQ(spec.requestOnly(), spec.ttlMs == requestOnlyTtl) << spec.id;
        // The maintenance message is a status; what another controller writes (0x33 included) is live.
        if (std::string_view(spec.id) == "maintenance_message") EXPECT_EQ(spec.ttlMs, statusTtl);
        else if (spec.source == EntitySource::controller) EXPECT_EQ(spec.ttlMs, monitorTtl) << spec.id;
    }
    EXPECT_EQ(marked, requestOnlyEntities);
}

TEST(BoilerRequestOnly, EmsPlusSettingsRecordsAndUptimeStayWhileMonitorsAndStatusExpire) {
    using namespace heating::control;
    EmsEntityObserver o;
    const uint64_t at = 1000, later = at + 60 * day;
    o.observe(fromBoiler(0xE6, {0, 62, 0, 0, 85}, 0, 0x0B), at);              // heating 62 degC, burner 85 %
    o.observe(fromBoiler(0xEA, {0, 0, 0, 0, 0, 0, 55}, 0, 0x0B), at);         // hot water 55 degC
    o.observe(fromBoiler(0x10, {'E', 'A', 0x00, 0xE3}, 0, 0x0B), at);         // last locking error EA, 227
    o.observe(fromBoiler(0x14, {0x01, 0x86, 0xA0}, 0, 0x0B), at);             // uptime 100000 min
    o.observe(fromBoiler(0xE4, {0, 0, 0, 0, 0, 0, 40, 0x01, 0xC8}), at);      // flow 45.6 degC
    o.observe(fromBoiler(0x1C, {0, 0, 0, 0, 0, 3}), at);                      // maintenance message H03
    EXPECT_DOUBLE_EQ(o.value(8, "plus_flow_temperature", at + monitorTtl - 1).value_or(-1), 45.6);
    EXPECT_FALSE(o.value(8, "plus_flow_temperature", at + monitorTtl)) << "a monitor keeps its lifetime";
    EXPECT_DOUBLE_EQ(o.value(8, "maintenance_message", at + statusTtl - 1).value_or(-1), 3);
    EXPECT_FALSE(o.value(8, "maintenance_message", at + statusTtl)) << "maintenance_message stays a status value";
    EXPECT_DOUBLE_EQ(o.value(8, "plus_heating_temperature", later).value_or(-1), 62);
    EXPECT_DOUBLE_EQ(o.value(8, "plus_maximum_burner_power", later).value_or(-1), 85);
    EXPECT_DOUBLE_EQ(o.value(8, "plus_dhw_selected_temperature", later).value_or(-1), 55);
    EXPECT_DOUBLE_EQ(o.value(8, "last_locking_error_number", later).value_or(-1), 227);
    EXPECT_DOUBLE_EQ(o.value(8, "boiler_uptime", later).value_or(-1), 100000);
    EXPECT_FALSE(o.value(8, "plus_heating_temperature", at - 1)) << "never before it arrived";
    // The boiler fields route: the setting stays a field sample, the expired monitor is gone.
    const auto heating = o.field(catalogIndex("plus_heating_temperature") - catalogFieldBase, later);
    ASSERT_TRUE(heating);
    EXPECT_EQ(heating->raw, 62); EXPECT_EQ(heating->observedMs, at); EXPECT_EQ(heating->type, 0xE6);
    EXPECT_FALSE(o.field(catalogIndex("plus_flow_temperature") - catalogFieldBase, later));
    // A newer report replaces it.
    o.observe(fromBoiler(0xE6, {60}, 1, 0x0B), later);
    EXPECT_DOUBLE_EQ(o.value(8, "plus_heating_temperature", later + 1).value_or(-1), 60);
    // The page's entity JSON marks them, with when they arrived; the expired monitor and status are left out.
    std::ostringstream out; o.writeJSON(out, later + 1);
    const auto doc = parse(out.str());
    ASSERT_TRUE(doc);
    std::set<std::string> listed, flagged;
    for (const cJSON* d = cJSON_GetObjectItemCaseSensitive(doc.get(), "devices")->child; d; d = d->next)
        for (const cJSON* e = cJSON_GetObjectItemCaseSensitive(d, "entities")->child; e; e = e->next) {
            const std::string id = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(e, "id"));
            listed.insert(id);
            if (!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(e, "request_only"))) continue;
            flagged.insert(id);
            const bool replaced = id == "plus_heating_temperature";
            EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(e, "observed_at_ms")), double(replaced ? later : at)) << id;
            EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(e, "age_ms")), double(replaced ? 1 : later + 1 - at)) << id;
        }
    EXPECT_EQ(listed, flagged);
    EXPECT_EQ(listed, (std::set<std::string>{"plus_heating_temperature", "plus_maximum_burner_power", "plus_dhw_selected_temperature",
                                             "last_locking_error_code", "last_locking_error_number", "boiler_uptime"}));
    // The retained state's lifetimes: none for these, the table's for the rest.
    for (const auto& id : requestOnlyEntities) EXPECT_FALSE(boilerFieldTtlMs(catalogIndex(id)).has_value()) << id;
    EXPECT_EQ(boilerFieldTtlMs(catalogIndex("plus_flow_temperature")).value_or(0), monitorTtl);
    EXPECT_EQ(boilerFieldTtlMs(catalogIndex("maintenance_message")).value_or(0), statusTtl);
}

TEST(BoilerRequestOnly, ARetainedCatalogGroupKeepsTheSettingsAndNullsAnExpiredMonitor) {
    using namespace heating::control;
    // Group 9 (indexes 90-99): the EMS+ heating runtime (a monitor) and the three EMS+ settings.
    const size_t runtime = catalogIndex("plus_heating_runtime"), dhw = catalogIndex("plus_dhw_selected_temperature"),
                 heating = catalogIndex("plus_heating_temperature"), power = catalogIndex("plus_maximum_burner_power");
    ASSERT_EQ(runtime / boilerFieldsPerGroup, 9u);
    ASSERT_EQ(power / boilerFieldsPerGroup, 9u);
    const uint64_t at = 1000, sampled = at + day;
    std::string rows;
    for (size_t i = 90; i < 100; ++i) {
        const auto seen = [&](int raw, int type) {
            return "[" + std::to_string(i) + "," + std::to_string(raw) + "," + std::to_string(at) + ",0," + std::to_string(type) + "]";
        };
        rows += std::string(i == 90 ? "" : ",") + (i == runtime ? seen(1234, 0xE5) : i == dhw ? seen(55, 0xEA)
            : i == heating ? seen(62, 0xE6) : i == power ? seen(85, 0xE6) : "[" + std::to_string(i) + ",null,null,0,0]");
    }
    const auto raw = "{\"schema\":1,\"sampled_at_ms\":" + std::to_string(sampled) + ",\"profile\":\"plus_observed\",\"fields\":[" + rows + "]}";
    Json values(boilerGroupValues(raw, 9), cJSON_Delete);
    ASSERT_TRUE(values) << raw;
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetArrayItem(row(values.get(), runtime), 1))) << "the expired monitor goes out as null";
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row(values.get(), dhw), 1)), 55);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row(values.get(), heating), 1)), 62);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row(values.get(), power), 1)), 85);
    EXPECT_TRUE(validBoilerGroup(values.get(), 9, true));
}

TEST(BoilerRequestOnly, AFullEntityStoreLetsAnExpiredReadingGoBeforeAValueReadOnce) {
    // 48 slots: the EMS+ heating temperature read at start-up, then 47 thermostat readings.
    const auto fill = [](EmsEntityObserver& o) {
        o.observe(fromBoiler(0xE6, {0, 62}, 0, 0x0B), 1000);
        for (uint8_t address = 0x10; address < 0x10 + 23; ++address)       // setpoint and room: 46 slots
            o.observe({EmsTelegram::BROADCAST, address, 0x00, 0, 0xB1, {4, 40, 0x00, 0xC8}}, 2000);
        o.observe({EmsTelegram::WRITE, 0x27, 0x08, 0, 0x1A, {40}}, 2000);   // requested flow: the 48th
    };
    EmsEntityObserver expired;
    fill(expired);
    // A new thermostat after those readings expired takes their slots; the value read once stays.
    expired.observe({EmsTelegram::BROADCAST, 0x40, 0x00, 0, 0xB1, {4, 42, 0x00, 0xD2}}, 2000 + monitorTtl);
    EXPECT_DOUBLE_EQ(expired.value(8, "plus_heating_temperature", 2000 + monitorTtl).value_or(-1), 62);
    EXPECT_DOUBLE_EQ(expired.value(0x40, "thermostat_setpoint", 2000 + monitorTtl).value_or(-1), 21);
    // With every reading still valid the oldest report gives way, as before.
    EmsEntityObserver fresh;
    fill(fresh);
    fresh.observe({EmsTelegram::BROADCAST, 0x40, 0x00, 0, 0xB1, {4, 42, 0x00, 0xD2}}, 2001);
    EXPECT_FALSE(fresh.value(8, "plus_heating_temperature", 2001));
    EXPECT_DOUBLE_EQ(fresh.value(0x40, "thermostat_room_temperature", 2001).value_or(-1), 21);
}
