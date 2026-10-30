#include "EMS/BoilerProfileReport.h"
#include "EMS/EmsEntityCatalog.h"
#include "control/TelemetryPublisher.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <string>
#include <string_view>

namespace {
using namespace heating::ems;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

EmsTelegram data(uint16_t type, std::vector<uint8_t> payload, uint8_t source = 8, uint8_t destination = 0) {
    return {destination ? EmsTelegram::WRITE : EmsTelegram::BROADCAST, source, destination, 0, type, std::move(payload)};
}
// The owner's UBAMonitorFast (Bosch behind an EasyControl adapter, EMS Classic):
// 08 00 18 00 00 02 4E 00 00 00 00 00 00 80 00 80 00 02 3A 00 00 FF 30 48 00 00 FF 00 00 [crc]
// flow 59.0, no storage sensors (0x8000), return 57.0, no pressure sensor (0xFF), display "0H".
EmsTelegram ownerFast() {
    return data(0x18, {0x00, 0x02, 0x4E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x00, 0x80, 0x00, 0x02, 0x3A,
                       0x00, 0x00, 0xFF, 0x30, 0x48, 0x00, 0x00, 0xFF, 0x00, 0x00});
}
size_t slot(BoilerField f) { return static_cast<size_t>(f); }
size_t catalogSlot(std::string_view id) {
    for (size_t f = 0; f < entityFieldCount; ++f)
        if (std::string_view(entityCatalog[entityFieldRows[f]].id) == id) return BoilerProfile::catalogSlot(f);
    ADD_FAILURE() << id;
    return 0;
}
struct Rig {
    BoilerProfile profile;
    ClassicBoilerMonitor monitor;
    EmsEntityObserver entities;
    Rig() { monitor.attachProfile(&profile); entities.attachProfile(&profile); }
    void receive(const EmsTelegram& t, uint64_t now) {
        if (t.getSenderId() == 8) if (const auto v = readDeviceVersion(t)) profile.observeVersion(*v, now);
        monitor.receive(t, now);
        entities.observe(t, now);
    }
};
Json parse(const std::string& s) { return Json(cJSON_Parse(s.c_str()), cJSON_Delete); }
std::string topic(const BoilerProfile& p) { std::ostringstream out; writeBoilerProfileTopic(out, p); return out.str(); }
std::vector<int> list(const cJSON* doc, const char* key) {
    std::vector<int> out;
    const cJSON* a = cJSON_GetObjectItemCaseSensitive(doc, key);
    for (const cJSON* i = a ? a->child : nullptr; i; i = i->next) out.push_back(i->valueint);
    return out;
}
bool has(const std::vector<int>& v, size_t x) { return std::find(v.begin(), v.end(), int(x)) != v.end(); }
}

TEST(BoilerProfile, TheOwnersFrameMarksMissingSensorsNotFittedAfterTenFramesOverTenMinutes) {
    Rig r;
    for (int i = 0; i < 10; ++i) r.receive(ownerFast(), 1000 + uint64_t(i) * 60000);  // 9 min span
    EXPECT_EQ(r.profile.state(slot(BoilerField::pressure)), FieldPresence::unknown);  // too soon
    r.receive(ownerFast(), 1000 + 600000);
    EXPECT_EQ(r.profile.state(slot(BoilerField::pressure)), FieldPresence::not_fitted);
    EXPECT_EQ(r.profile.state(slot(BoilerField::storageTemp1)), FieldPresence::not_fitted);
    EXPECT_EQ(r.profile.state(slot(BoilerField::storageTemp2)), FieldPresence::not_fitted);
    EXPECT_EQ(r.profile.state(slot(BoilerField::flow)), FieldPresence::supported);
    EXPECT_EQ(r.profile.state(slot(BoilerField::returnTemp)), FieldPresence::supported);
    EXPECT_EQ(r.profile.state(slot(BoilerField::displayCode)), FieldPresence::supported);
    EXPECT_EQ(r.profile.state(slot(BoilerField::ionisationCurrent)), FieldPresence::supported);  // 0 uA is a value
    // An unreliable raw bit that only ever reads 0 proves nothing: never "not fitted".
    EXPECT_EQ(r.profile.state(slot(BoilerField::rawBurner)), FieldPresence::unknown);
    // Telegrams never seen: listed apart.
    EXPECT_EQ(r.profile.state(slot(BoilerField::outdoor)), FieldPresence::not_reported);
    EXPECT_EQ(r.profile.state(catalogSlot("plus_pressure")), FieldPresence::not_reported);
    EXPECT_EQ(r.profile.identity().families, BoilerProfile::classicFamily);
}

TEST(BoilerProfile, TenFramesInAShortBurstStayUnknown) {
    Rig r;
    for (int i = 0; i < 50; ++i) r.receive(ownerFast(), 1000 + uint64_t(i) * 1000);
    EXPECT_EQ(r.profile.state(slot(BoilerField::pressure)), FieldPresence::unknown);
    BoilerProfile p;  // and nine frames over an hour too
    for (int i = 0; i < 9; ++i) p.observe(6, FieldEvidence::absent, uint64_t(i) * 600000);
    EXPECT_EQ(p.state(6), FieldPresence::unknown);
}

TEST(BoilerProfile, OneValidValueMakesAFieldSupportedEvenAfterNotFitted) {
    BoilerProfile p;
    for (int i = 0; i <= 10; ++i) p.observe(6, FieldEvidence::absent, uint64_t(i) * 60000);
    ASSERT_EQ(p.state(6), FieldPresence::not_fitted);
    p.observe(6, FieldEvidence::value, 700000);  // a pressure sensor fitted later
    EXPECT_EQ(p.state(6), FieldPresence::supported);
    EXPECT_EQ(*p.lastValidAgeS(6, 712000), 12u);
    // Supported stays: a sensor failing later reads unavailable, not "not fitted".
    for (int i = 0; i <= 20; ++i) p.observe(6, FieldEvidence::absent, 800000 + uint64_t(i) * 60000);
    EXPECT_EQ(p.state(6), FieldPresence::supported);
    // A reordered older absent frame cannot shorten the span rule either.
    BoilerProfile q;
    for (int i = 10; i >= 0; --i) q.observe(6, FieldEvidence::absent, uint64_t(i) * 60000);
    EXPECT_EQ(q.state(6), FieldPresence::not_fitted);
}

TEST(BoilerProfile, CatalogFieldsOfEmsPlusAndThermostatsUseTheSameRules) {
    Rig r;
    // 0xE4 from the boiler: pressure byte 21 = 0 (EMS+ "no sensor"), flow 0x01F4 = 50.0.
    std::vector<uint8_t> e4(32, 0);
    e4[7] = 0x01; e4[8] = 0xF4; e4[17] = 0x80; e4[18] = 0x00;
    for (int i = 0; i <= 10; ++i) r.receive(data(0xE4, e4), uint64_t(i) * 60000);
    EXPECT_EQ(r.profile.state(catalogSlot("plus_pressure")), FieldPresence::not_fitted);
    EXPECT_EQ(r.profile.state(catalogSlot("plus_return_temperature")), FieldPresence::not_fitted);
    EXPECT_EQ(r.profile.state(catalogSlot("plus_flow_temperature")), FieldPresence::supported);
    EXPECT_EQ(r.profile.identity().families, BoilerProfile::plusFamily);
    // A room thermostat (RC10 at 0x17) is a catalog field as well.
    r.receive(data(0xB1, {0x04, 41, 0x00, 0xCD, 0, 0}, 0x17), 700000);
    EXPECT_EQ(r.profile.state(catalogSlot("thermostat_setpoint")), FieldPresence::supported);
    EXPECT_EQ(r.profile.state(catalogSlot("boiler_uptime")), FieldPresence::not_reported);
}

TEST(BoilerProfile, TheRecordRestoresStatesOverridesAndIdentity) {
    Rig r;
    r.receive(data(0x02, {0x5F, 0x02, 0x07, 0, 0, 0, 0, 0, 0, 0x01}), 100);  // product 95, version 2.7
    for (int i = 0; i <= 10; ++i) r.receive(ownerFast(), 1000 + uint64_t(i) * 60000);
    ASSERT_TRUE(r.profile.setShown(slot(BoilerField::pressure), true, 700000));
    EXPECT_FALSE(r.profile.setShown(slot(BoilerField::flow), true, 700000));  // only a not-fitted field
    const auto rec = r.profile.record();
    EXPECT_LE(rec.size(), 64u);
    BoilerProfile b;
    ASSERT_TRUE(b.restore(rec.data(), rec.size(), 0));
    EXPECT_TRUE(b.restored());
    for (size_t i = 0; i < BoilerProfile::fieldCount; ++i) {
        EXPECT_EQ(b.state(i), r.profile.state(i)) << i;
        EXPECT_EQ(b.overridden(i), r.profile.overridden(i)) << i;
    }
    EXPECT_TRUE(b.identity() == r.profile.identity());
    EXPECT_EQ(b.identity().product, 0x5F);
    EXPECT_FALSE(b.dirty());  // nothing new: no write
    EXPECT_TRUE(b.shown(slot(BoilerField::pressure)));
}

TEST(BoilerProfile, AnOlderRecordWithFewerCatalogFieldsRestoresAndInvalidOnesAreIgnored) {
    BoilerProfile a;
    a.observe(1, FieldEvidence::value, 0);
    a.observe(BoilerProfile::catalogSlot(0), FieldEvidence::value, 0);
    auto full = a.record();
    // The same record as a firmware with 30 catalog fields wrote it.
    const size_t fields = BoilerProfile::classicFields + 30;
    std::vector<uint8_t> old(BoilerProfile::headerBytes + (fields + 3) / 4 + (fields + 7) / 8, 0);
    std::copy(full.begin(), full.begin() + BoilerProfile::headerBytes + (fields + 3) / 4, old.begin());
    old[3] = 30;
    // clear state bits beyond the old field count
    BoilerProfile b;
    ASSERT_TRUE(b.restore(old.data(), old.size(), 0));
    EXPECT_EQ(b.state(1), FieldPresence::supported);
    EXPECT_EQ(b.state(BoilerProfile::catalogSlot(0)), FieldPresence::supported);
    EXPECT_TRUE(b.dirty());  // written again in the new layout
    for (auto bad : {std::vector<uint8_t>{}, std::vector<uint8_t>(full.begin(), full.end() - 1)}) {
        BoilerProfile c;
        EXPECT_FALSE(c.restore(bad.data(), bad.size(), 0));
        EXPECT_FALSE(c.restored());
    }
    auto wrong = full; wrong[0] = 0;
    BoilerProfile c;
    EXPECT_FALSE(c.restore(wrong.data(), wrong.size(), 0));
    wrong = full; wrong[3] = uint8_t(BoilerProfile::catalogFields + 1);  // a newer firmware's record
    EXPECT_FALSE(c.restore(wrong.data(), wrong.size(), 0));
}

TEST(BoilerProfile, AnotherBoilerStartsAgain) {
    Rig r;
    r.receive(data(0x02, {0x5F, 0x02, 0x07}), 0);
    for (int i = 0; i <= 10; ++i) r.receive(ownerFast(), uint64_t(i) * 60000);
    ASSERT_EQ(r.profile.state(slot(BoilerField::pressure)), FieldPresence::not_fitted);
    r.receive(data(0x02, {0x5F, 0x02, 0x07}), 700000);  // the same boiler again: nothing
    EXPECT_EQ(r.profile.resets(), 0u);
    r.receive(data(0x02, {0x40, 0x01, 0x03}), 710000);  // another product: start again
    EXPECT_EQ(r.profile.resets(), 1u);
    EXPECT_EQ(r.profile.state(slot(BoilerField::pressure)), FieldPresence::not_reported);
    EXPECT_EQ(r.profile.identity().product, 0x40);

    // Without a version report: a stored Classic boiler whose first report this boot is EMS+.
    BoilerProfile classic;
    classic.observeFamily(BoilerProtocol::classic, 0);
    classic.observe(1, FieldEvidence::value, 0);
    const auto rec = classic.record();
    Rig next;
    ASSERT_TRUE(next.profile.restore(rec.data(), rec.size(), 0));
    next.receive(data(0xE4, std::vector<uint8_t>(32, 0)), 1000);
    EXPECT_EQ(next.profile.resets(), 1u);
    EXPECT_EQ(next.profile.state(1), FieldPresence::not_reported);
    EXPECT_EQ(next.profile.identity().families, BoilerProfile::plusFamily);
    // A boiler that sends both families in one boot is not "another boiler".
    Rig mixed;
    ASSERT_TRUE(mixed.profile.restore(rec.data(), rec.size(), 0));
    mixed.receive(ownerFast(), 1000);
    mixed.receive(data(0xE4, std::vector<uint8_t>(32, 0)), 2000);
    EXPECT_EQ(mixed.profile.resets(), 0u);
    EXPECT_EQ(mixed.profile.state(1), FieldPresence::supported);
    // A record of another boiler than the one this boot already saw is dropped.
    Rig early;
    early.receive(data(0xE4, std::vector<uint8_t>(32, 0)), 10);
    EXPECT_FALSE(early.profile.restore(rec.data(), rec.size(), 20));
    EXPECT_EQ(early.profile.state(1), FieldPresence::not_reported);
}

TEST(BoilerProfile, WritesAreRareAndDebounced) {
    BoilerProfile p;
    EXPECT_FALSE(p.takeWrite(0));  // nothing changed
    p.observe(1, FieldEvidence::value, 1000);
    p.observe(2, FieldEvidence::value, 20000);
    EXPECT_FALSE(p.takeWrite(45000));             // 30 s quiet after the last change
    auto first = p.takeWrite(50000);
    ASSERT_TRUE(first);
    p.written(true);
    EXPECT_FALSE(p.takeWrite(60000));             // nothing changed since
    p.observe(1, FieldEvidence::value, 61000);    // a value of a known field is no change
    EXPECT_FALSE(p.dirty());
    p.observe(3, FieldEvidence::value, 70000);
    EXPECT_FALSE(p.takeWrite(110000));            // at most every 5 min
    ASSERT_TRUE(p.takeWrite(350000));
    p.written(false);                             // a failed write is retried
    EXPECT_TRUE(p.dirty());
    EXPECT_FALSE(p.takeWrite(400000));
    EXPECT_TRUE(p.takeWrite(650000));
    p.written(true);
    EXPECT_EQ(p.writes(), 2u);
    EXPECT_EQ(p.writeFailures(), 1u);
    // An owner override goes out at once.
    for (int i = 0; i <= 10; ++i) p.observe(6, FieldEvidence::absent, 700000 + uint64_t(i) * 60000);
    ASSERT_TRUE(p.takeWrite(1400000)); p.written(true);
    ASSERT_TRUE(p.setShown(6, true, 1401000));
    EXPECT_TRUE(p.takeWrite(1401000));
    // Bounded: a field moves not_reported -> unknown -> not_fitted -> supported at most.
    BoilerProfile q;
    size_t writes = 0;
    for (uint64_t t = 0; t < 24ull * 3600000; t += 10000) {
        for (size_t i = 0; i < BoilerProfile::fieldCount; ++i) q.observe(i, FieldEvidence::absent, t);
        if (q.takeWrite(t)) { ++writes; q.written(true); }
    }
    EXPECT_LE(writes, 3u);
}

TEST(BoilerProfile, StatusAndTopicReportIndexesNamesAndStayUnderOneKilobyte) {
    Rig r;
    for (int i = 0; i <= 10; ++i) r.receive(ownerFast(), 1000 + uint64_t(i) * 60000);
    std::ostringstream out;
    writeBoilerProfileJSON(out, r.profile, 700000);
    auto doc = parse(out.str());
    ASSERT_TRUE(doc);
    const cJSON* fields = cJSON_GetObjectItemCaseSensitive(doc.get(), "fields");
    ASSERT_EQ(cJSON_GetArraySize(fields), int(BoilerProfile::fieldCount));
    const cJSON* pressure = cJSON_GetArrayItem(fields, 6);
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(pressure, "name")->valuestring, "pressure");
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(pressure, "state")->valuestring, "not_fitted");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(pressure, "last_valid_age_s")));
    const cJSON* catalog = cJSON_GetArrayItem(fields, int(BoilerProfile::classicFields));
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(catalog, "index")->valueint, 70);
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(catalog, "name")->valuestring, entityCatalog[0].id);
    EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(doc.get(), "counts"), "not_fitted")->valueint, 3);
    EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(doc.get(), "identity"), "family")->valuestring, "classic");

    auto t = parse(topic(r.profile));
    ASSERT_TRUE(t);
    const auto supported = list(t.get(), "supported"), notFitted = list(t.get(), "not_fitted"), notReported = list(t.get(), "not_reported");
    EXPECT_TRUE(has(supported, 1));
    EXPECT_TRUE(has(notFitted, 6));
    EXPECT_TRUE(has(notReported, 3));   // outdoor: 0x19 never seen
    EXPECT_TRUE(has(notReported, 70));  // catalog fields from wire index 70
    EXPECT_FALSE(has(notReported, 69));
    // Show anyway: the field moves to "supported" for Home Assistant.
    ASSERT_TRUE(r.profile.setShown(6, true, 700000));
    t = parse(topic(r.profile));
    EXPECT_TRUE(has(list(t.get(), "supported"), 6));
    EXPECT_FALSE(has(list(t.get(), "not_fitted"), 6));
    // Worst case: every field listed.
    BoilerProfile all;
    all.observeVersion({255, 255, 255, {}}, 0);
    for (size_t i = 0; i < BoilerProfile::fieldCount; ++i) all.observe(i, FieldEvidence::value, 0);
    EXPECT_LT(topic(all).size(), 1024u);
    BoilerProfile none;
    EXPECT_LT(topic(none).size(), 1024u);
}

TEST(BoilerProfile, TheTelemetryPublisherSendsTheRetainedProfileOnChange) {
    using heating::control::TelemetryPublisher;
    BoilerProfile p;
    std::vector<std::pair<std::string, std::string>> sent;
    uint64_t now = 0;
    TelemetryPublisher publisher({{}, {}, {}, {}, [&](std::string& out, size_t group) {
            out.clear();
            if (group == heating::control::boilerProfileGroup) { std::ostringstream ss; writeBoilerProfileTopic(ss, p); out = ss.str(); }
        }, {}},
        [&](const std::string& topic, std::string_view payload, bool retained) {
            EXPECT_TRUE(retained);
            sent.push_back({topic, std::string(payload)});
            return true;
        }, [] { return true; });
    publisher.connected(0);
    const auto count = [&] { size_t n = 0; for (auto& s : sent) n += s.first == "fw/config/boiler_profile"; return n; };
    for (; now < 30000; now += 500) publisher.tick(now);
    EXPECT_EQ(count(), 1u);
    p.observe(1, FieldEvidence::value, now);
    for (; now < 60000; now += 500) publisher.tick(now);
    EXPECT_EQ(count(), 2u);
    EXPECT_NE(sent.back().second.find("\"supported\":[1]"), std::string::npos);
}

TEST(BoilerProfile, SettledAfterTheBoilerWasHeardForTheSpanAndThatIsStored) {
    Rig r;
    r.receive(ownerFast(), 1000);
    EXPECT_FALSE(r.profile.settled());
    EXPECT_NE(topic(r.profile).find("\"settled\":false"), std::string::npos);
    r.receive(ownerFast(), 601000);
    EXPECT_TRUE(r.profile.settled());
    EXPECT_NE(topic(r.profile).find("\"settled\":true"), std::string::npos);
    const auto rec = r.profile.record();
    BoilerProfile b;
    ASSERT_TRUE(b.restore(rec.data(), rec.size(), 0));
    EXPECT_TRUE(b.settled());
    b.observeVersion({0x40, 1, 1, {}}, 10);  // a first version report: adopted, no reset
    EXPECT_TRUE(b.settled());
    b.observeVersion({0x41, 1, 1, {}}, 20);  // another boiler: discovery starts again
    EXPECT_FALSE(b.settled());
}
