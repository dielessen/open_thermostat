#include "control/DhwEpisodes.h"
#include "EMS/EmsEntityCatalog.h"
#include "ScopedTz.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <algorithm>
#include <fstream>
#include <cstdio>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {
using namespace heating::ems;
using heating::control::DhwEpisodes;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

// A logged frame "08 00 18 00 .. CRC" (without the BREAK); fromRawData checks the CRC.
EmsTelegram frame(const std::string& hex) {
    std::istringstream in(hex); std::vector<uint8_t> bytes; unsigned b;
    while (in >> std::hex >> b) bytes.push_back(static_cast<uint8_t>(b));
    return EmsTelegram::fromRawData(bytes.data(), bytes.size());
}
Json json(const DhwEpisodes& e, uint64_t now) {
    std::ostringstream out; e.writeJSON(out, now);
    return Json(cJSON_Parse(out.str().c_str()), cJSON_Delete);
}
double at(const cJSON* o, const char* a, const char* b = nullptr) {
    const cJSON* v = cJSON_GetObjectItem(o, a);
    return cJSON_GetNumberValue(b ? cJSON_GetObjectItem(v, b) : v);
}

// The owner's tado (RC10-type, 0x17) frames from the device log of 27-28 Oct 2026.
TEST(TadoFrames, RealRc10MonitorSetPointsAndDhwRequestDecodeToPlausibleVerifiedValues) {
    EmsEntityObserver o;
    o.observe(frame("17 00 B1 00 04 2A 00 D5 00 00 00 00 BC"), 100);  // setpoint 21.0, room 21.3
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_setpoint", 100), 21.0);
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_room_temperature", 100), 21.3);
    o.observe(frame("17 00 B1 00 04 26 00 D4 00 00 00 00 87"), 200);  // night setpoint 19.0, room 21.2
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_setpoint", 200), 19.0);
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_room_temperature", 200), 21.2);
    o.observe(frame("17 08 1A 00 20 64 64 00 62"), 300);              // heat: flow 32, power and pump 100 %
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_requested_flow_temperature", 300), 32);
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_requested_burner_power", 300), 100);
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_requested_pump_modulation", 300), 100);
    o.observe(frame("17 08 1A 00 00 00 00 00 3A"), 400);              // idle request
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_requested_flow_temperature", 400), 0);
    o.observe(frame("17 08 33 02 37 D6"), 500);                       // tado writes DHW 55 degC
    EXPECT_DOUBLE_EQ(*o.value(0x17, "thermostat_requested_dhw_temperature", 500), 55);
    // Not table rows: UBAFlags (constant 11 11) and the tado's read of 0x16.
    o.observe(frame("17 08 35 00 11 11 D0"), 600);
    o.observe(frame("17 88 16 01 01 16"), 600);
    // Each entity of the tado says it is verified; the table-wide flag stays false.
    std::ostringstream out; o.writeJSON(out, 600);
    Json j(cJSON_Parse(out.str().c_str()), cJSON_Delete);
    ASSERT_TRUE(j);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(j.get(), "verified_on_hardware")));
    const cJSON* devices = cJSON_GetObjectItem(j.get(), "devices");
    ASSERT_EQ(cJSON_GetArraySize(devices), 1);
    const cJSON* entities = cJSON_GetObjectItem(cJSON_GetArrayItem(devices, 0), "entities");
    EXPECT_EQ(cJSON_GetArraySize(entities), 6);
    for (int i = 0; i < cJSON_GetArraySize(entities); ++i)
        EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(cJSON_GetArrayItem(entities, i), "verified")));
}
TEST(TadoFrames, BoilerParameterWwBroadcastFillsTheClassicFieldsNotTheThermostatRequest) {
    EmsEntityObserver o; ClassicBoilerMonitor m;
    const auto t = frame("08 00 33 00 08 FF 37 FB FF 28 FF 02 46 00 FF E2");
    o.observe(t, 100); m.receive(t, 100);
    EXPECT_FALSE(o.value(0x08, "thermostat_requested_dhw_temperature", 100));
    EXPECT_EQ(*m.value(BoilerField::selectedDhw, 100), 5500);
    EXPECT_EQ(*m.value(BoilerField::dhwEnabled, 100), 1);
    EXPECT_EQ(*m.value(BoilerField::dhwCirculationEnabled, 100), 1);
    EXPECT_EQ(*m.value(BoilerField::dhwCirculationMode, 100), 2);
    EXPECT_EQ(*m.value(BoilerField::dhwComfortMode, 100), 0);           // 0 = hot (comfort)
    EXPECT_EQ(*m.value(BoilerField::dhwDisinfectionTemp, 100), 7000);
}
TEST(TadoFrames, VerifiedRowsAreOnlyThermostatRowsSeenFromTheTado) {
    size_t n = 0;
    for (const auto& spec : entityCatalog) {
        if (!spec.verified) continue;
        ++n;
        EXPECT_EQ(spec.source, EntitySource::controller) << spec.id;
        EXPECT_TRUE(spec.type == 0x1A || spec.type == 0xB1 || spec.type == 0x33) << spec.id;
    }
    EXPECT_EQ(n, 6u);
    EXPECT_STREQ(entityCatalog.back().id, "thermostat_requested_dhw_temperature"); // appended: indexes stay
}

// Real 0x18/0x34 broadcasts: one tap and one keep-warm episode.
TEST(DhwEpisodes, RealHrc22FramesGiveOneTapAndOneKeepWarmEpisode) {
    std::ifstream file("test/fixtures/dhw-episodes-hrc22.txt");
    ASSERT_TRUE(file.good());
    ClassicBoilerMonitor m; DhwEpisodes e; std::string line; size_t frames = 0; uint64_t last = 0;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream in(line); uint64_t ms; in >> ms;
        std::string hex; std::getline(in, hex);
        ASSERT_TRUE(m.receive(frame(hex), ms)) << line;
        e.observe(m, ms, std::nullopt);
        ++frames; last = ms;
    }
    EXPECT_GT(frames, 100u);
    EXPECT_FALSE(e.flowLive()); // the adapter's 0x34 flow is a constant 2.5 L/min
    const auto& d = e.today();
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 1); EXPECT_EQ(d.seconds[DhwEpisodes::tapping], 69u);       // 68 -> 33 degC
    EXPECT_EQ(d.count[DhwEpisodes::keepWarm], 1); EXPECT_EQ(d.seconds[DhwEpisodes::keepWarm], 211u);   // 57 -> 54 -> 61
    EXPECT_EQ(d.count[DhwEpisodes::unknown], 0);
    EXPECT_EQ(d.burnerS, 280u);
    const auto j = json(e, last);
    ASSERT_TRUE(j);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(j.get(), "method")), "dhw_temperature_fall");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(j.get(), "clock_known")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(), "active_s")));
    const cJSON* week = cJSON_GetObjectItem(j.get(), "last_7_days");
    EXPECT_EQ(at(week, "tapping", "count"), 1); EXPECT_EQ(at(week, "keep_warm", "s"), 211);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(week, "peak_flow_l_min")));
}

// Synthetic: 0x18 offset 5 bit 1 = DHW, bit 3 = flame; DHW temperature in hundredths.
TEST(DhwEpisodes, LiveFlowDecidesTappingAndGivesThePeak) {
    DhwEpisodes e;
    e.flow(0); e.flow(0);
    EXPECT_FALSE(e.flowLive());
    e.state(0x00, 0); e.state(0x0A, 10000);
    e.flow(62); e.flow(85); e.state(0x0A, 20000);
    EXPECT_TRUE(e.flowLive());
    e.state(0x00, 40000);                             // tap: 30 s, all with the flame
    e.state(0x0A, 50000); e.flow(0); e.state(0x02, 60000); e.state(0x00, 70000); // no flow: keep warm
    const auto& d = e.today();
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 1); EXPECT_EQ(d.seconds[DhwEpisodes::tapping], 30u);
    EXPECT_EQ(d.count[DhwEpisodes::keepWarm], 1); EXPECT_EQ(d.seconds[DhwEpisodes::keepWarm], 20u);
    EXPECT_EQ(d.burnerS, 40u); EXPECT_EQ(d.peakFlow, 85);
    const auto j = json(e, 70000);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(j.get(), "method")), "flow");
    EXPECT_DOUBLE_EQ(at(cJSON_GetObjectItem(j.get(), "today"), "peak_flow_l_min"), 8.5);
}
TEST(DhwEpisodes, ReheatRightAfterATapIsKeepWarmNotASecondTap) {
    DhwEpisodes e;
    uint64_t t = 0;
    const auto report = [&](uint8_t state, int32_t centi) { t += 10000; e.temperature(centi, t - 5000); e.state(state, t); };
    for (int i = 0; i < 30; ++i) report(0x00, 5000);                 // idle, exchanger at 50 degC
    for (int c : {3500, 2200, 2000, 2000, 2000, 2000}) report(0x0A, c); // a 1-minute tap
    report(0x00, 2000);
    for (int c : {2000, 2600, 3300, 4000, 4600, 5000, 5200}) report(0x0A, c); // reheat 10 s later
    report(0x00, 5200);
    const auto& d = e.today();
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 1);
    EXPECT_EQ(d.count[DhwEpisodes::keepWarm], 1);
}
TEST(DhwEpisodes, WithoutTemperatureOrFlowAnEpisodeIsUnknownAndAGapEndsIt) {
    DhwEpisodes e;
    e.state(0x0A, 0); e.state(0x0A, 10000);
    EXPECT_DOUBLE_EQ(at(json(e, 15000).get(), "active_s"), 15);
    e.state(0x0A, 100000);                           // 90 s gap: ends at 10 s, a new episode opens
    e.state(0x00, 110000);
    e.state(0x0A, 50000);                            // older, reordered report: ignored
    const auto& d = e.today();
    EXPECT_EQ(d.count[DhwEpisodes::unknown], 2); EXPECT_EQ(d.seconds[DhwEpisodes::unknown], 20u);
    EXPECT_EQ(d.burnerS, 20u);
}
TEST(DhwEpisodes, DaysRollAtLocalMidnightAndTheWeekKeepsSevenDays) {
    ScopedTz tz(ScopedTz::amsterdam);
    DhwEpisodes e;
    const uint32_t day0 = 1792800000;                // 2026-10-24 00:00 UTC; the steps cross the CEST end
    const auto episode = [&](uint32_t utc, uint64_t ms) {
        ClassicBoilerMonitor m;
        e.observe(m, ms, utc);
        e.temperature(6000, ms); e.state(0x0A, ms + 1000); e.temperature(4000, ms + 11000); e.state(0x00, ms + 21000);
    };
    for (uint32_t i = 0; i < 9; ++i) episode(day0 + i * 86400, uint64_t(i) * 86400000);
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 1);
    EXPECT_EQ(e.today().day, heating::control::ShadowComparison::localDay(day0 + 8 * 86400));
    EXPECT_EQ(e.lastSevenDays().count[DhwEpisodes::tapping], 7);
    EXPECT_EQ(e.lastSevenDays().seconds[DhwEpisodes::tapping], 7u * 20);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json(e, 9ull * 86400000).get(), "clock_known")));
}
// rc.4 (F2): today and the last 7 days survive a restart. The record is stored at a new day and
// hourly when something changed; at boot it joins this boot's counts once the clock gives the day.
// Without it, today's totals start at the restart and since_restart_utc says when.
TEST(DhwEpisodes, TodayAndTheWeekSurviveARestart) {
    ScopedTz tz(ScopedTz::amsterdam);
    const uint32_t day0 = 1792800000;                // 2026-10-24 00:00 UTC
    const auto tap = [](DhwEpisodes& e, uint32_t utc, uint64_t ms) {
        ClassicBoilerMonitor m;
        e.observe(m, ms, utc);
        e.temperature(6000, ms); e.state(0x0A, ms + 1000); e.temperature(4000, ms + 11000); e.state(0x00, ms + 21000);
    };
    DhwEpisodes before;
    for (uint32_t i = 0; i < 9; ++i) tap(before, day0 + i * 86400 + 36000, uint64_t(i) * 86400000);
    tap(before, day0 + 8 * 86400 + 39600, 8ull * 86400000 + 3600000); // a second tap on the last day
    ASSERT_EQ(before.today().count[DhwEpisodes::tapping], 2);
    ASSERT_EQ(before.lastSevenDays().count[DhwEpisodes::tapping], 8);
    const std::string record = before.record();
    EXPECT_EQ(record.rfind("1;", 0), 0u);
    EXPECT_LE(record.size(), 260u) << record; // today and 6 days
    // A restart the same day: a tap before the clock is known, then the clock; the stored day joins.
    DhwEpisodes after;
    ASSERT_TRUE(after.restore(record));
    EXPECT_FALSE(after.saveDue(1000)); // never before the clock and the join
    EXPECT_TRUE(after.record().empty());
    after.temperature(6000, 1000); after.state(0x0A, 2000); after.temperature(4000, 12000); after.state(0x00, 22000);
    ClassicBoilerMonitor m;
    after.observe(m, 30000, day0 + 8 * 86400 + 43200);
    EXPECT_EQ(after.today().count[DhwEpisodes::tapping], 3);
    EXPECT_EQ(after.lastSevenDays().count[DhwEpisodes::tapping], 9);
    EXPECT_EQ(after.lastSevenDays().seconds[DhwEpisodes::tapping], 9u * 20);
    EXPECT_FALSE(after.sinceRestartUtc()); // today's totals are whole
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(json(after, 30000).get(), "since_restart_utc")));
    EXPECT_TRUE(after.saveDue(30000)); // the joined record is stored at once
    after.saved(30000);
    EXPECT_FALSE(after.saveDue(30000 + 3600000)); // nothing new: no write
    tap(after, day0 + 8 * 86400 + 45000, 60000);
    EXPECT_FALSE(after.saveDue(82000));          // new, but within the hour
    EXPECT_TRUE(after.saveDue(30000 + 3600000)); // hourly
    // A restart on a later day: the stored day goes into the history, the oldest drops out.
    DhwEpisodes nextDay;
    ASSERT_TRUE(nextDay.restore(after.record()));
    nextDay.observe(m, 5000, day0 + 9 * 86400 + 36000);
    EXPECT_EQ(nextDay.today().count[DhwEpisodes::tapping], 0);
    EXPECT_EQ(nextDay.lastSevenDays().count[DhwEpisodes::tapping], 9); // days 3..7 and day 8's four
    ASSERT_TRUE(nextDay.sinceRestartUtc());
    EXPECT_EQ(*nextDay.sinceRestartUtc(), day0 + 9 * 86400 + 36000 - 5);
    EXPECT_TRUE(nextDay.saveDue(5000));
    // No record at all: the totals start at this boot, until the boot's day has passed.
    DhwEpisodes fresh;
    fresh.observe(m, 2000, day0 + 36000);
    EXPECT_DOUBLE_EQ(at(json(fresh, 3000).get(), "since_restart_utc"), day0 + 36000 - 2);
    Json summary(fresh.summaryJson(), cJSON_Delete); // the MQTT summary keeps its size: the page's field only
    EXPECT_FALSE(cJSON_GetObjectItem(summary.get(), "since_restart_utc"));
    fresh.observe(m, 86400000, day0 + 86400 + 36000);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(json(fresh, 86400000).get(), "since_restart_utc")));
    // Malformed, foreign or out-of-order records are ignored.
    for (const char* bad : {"", "1;", "2;20390,0,0,0,0,0,0,0,0,0,0", "1;20390,0,0,0,0,0,0,0,0,0", "1;20390,0,0,0,0,0,0,0,0,0,256",
                            "1;20390,0,0,0,0,0,0,0,0,0,0;20391,0,0,0,0,0,0,0,0,0,0", "1;0,0,0,0,0,0,0,0,0,0,0",
                            "1;20390,x,0,0,0,0,0,0,0,0,0", "1;20390,70000,0,0,0,0,0,0,0,0,0", "1;20390,0,0,0,0,0,0,0,0,0,0,"}) {
        DhwEpisodes e;
        EXPECT_FALSE(e.restore(bad)) << bad;
    }
}
// The day boundary is the device's local midnight: 04:00 UTC in New York (EDT).
TEST(DhwEpisodes, DaysRollAtTheDeviceTimeZonesMidnight) {
    const uint32_t day0 = 1792800000;                // 2026-10-24 00:00 UTC
    const auto todayTaps = [day0](const char* zone) {
        ScopedTz tz(zone);
        DhwEpisodes e;
        const auto episode = [&](uint32_t utc, uint64_t ms) {
            ClassicBoilerMonitor m;
            e.observe(m, ms, utc);
            e.temperature(6000, ms); e.state(0x0A, ms + 1000); e.temperature(4000, ms + 11000); e.state(0x00, ms + 21000);
        };
        episode(day0 + 3 * 3600, 0);                 // 23:00 EDT Friday / 05:00 CEST Saturday
        episode(day0 + 5 * 3600, 2 * 3600000);       // 01:00 EDT Saturday / 07:00 CEST Saturday
        return e.today().count[DhwEpisodes::tapping];
    };
    EXPECT_EQ(todayTaps(ScopedTz::newYork), 1);
    EXPECT_EQ(todayTaps(ScopedTz::amsterdam), 2);
}

// The owner's boiler, a whole day (31 Oct 2026) and a morning (1 Nov) from the Home Assistant history:
// the comfort mode reheats the plate exchanger about every 11 minutes. Expected counts come from an
// independent reference of the rule (the fixture generator); before 1 Nov many of these rounds were taps.
DhwEpisodes::Day ownerDay(const char* path) {
    std::ifstream file(path);
    EXPECT_TRUE(file.good()) << path;
    DhwEpisodes e; std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream in(line); uint64_t ms; char kind; int value;
        in >> ms >> kind >> value;
        if (kind == 'T') e.temperature(value, ms); else e.state(static_cast<uint8_t>(value), ms);
    }
    return e.today();
}
TEST(DhwEpisodes, OwnersDayCountsTheKeepWarmRoundsAsKeepingWarm) {
    const auto d = ownerDay("test/fixtures/dhw-owner-20261031.txt");
    EXPECT_EQ(d.count[DhwEpisodes::keepWarm], 40);
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 17);   // 13:00: 9 K in 1.5 min before a shallow round (no night learned: the 2 K/min default)
    EXPECT_EQ(d.count[DhwEpisodes::unknown], 0);
    EXPECT_EQ(d.count[DhwEpisodes::charging], 0);
    const auto m = ownerDay("test/fixtures/dhw-owner-20261101.txt");
    EXPECT_EQ(m.count[DhwEpisodes::keepWarm], 5);   // incl. two rounds at night (02:54, 04:29) that dip 9-11 K
    EXPECT_EQ(m.count[DhwEpisodes::tapping], 1);    // 00:38: 64 -> 18 degC
}
// The live activity on the owner's day (Home Assistant's timeline): each episode ends showing what it is
// counted as, and a tap shows as keeping warm only until its fall is clear.
TEST(DhwEpisodes, OwnersDayActivityEndsEachEpisodeAsItIsCounted) {
    std::ifstream file("test/fixtures/dhw-owner-20261031.txt");
    ASSERT_TRUE(file.good());
    DhwEpisodes e; std::string line, last;
    std::map<std::string, int> ended, seen;
    uint64_t openedMs = 0;
    std::vector<uint64_t> tapShownAfterMs;
    bool open = false, tapShown = false;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream in(line); uint64_t ms; char kind; int value;
        in >> ms >> kind >> value;
        if (kind == 'T') e.temperature(value, ms); else e.state(static_cast<uint8_t>(value), ms);
        const std::string now = e.activity() ? e.activity() : "";
        if (now != last) ++seen[now];
        const bool opened = e.openKind().has_value();
        if (opened && !open) { openedMs = ms; tapShown = false; }
        if (opened && now == "tapping" && !tapShown) { tapShown = true; tapShownAfterMs.push_back(ms - openedMs); }
        if (!opened && open) ++ended[last];
        open = opened; last = now;
    }
    EXPECT_EQ(ended["tapping"], 17);
    EXPECT_EQ(ended["keep_warm"], 40);
    EXPECT_EQ(ended.size(), 2u);
    EXPECT_GT(seen["heating"], 0);
    EXPECT_GT(seen["idle"], 0);
    // Most taps fall fast; a slow one shows once it has been 7.5 K under for 90 s.
    ASSERT_EQ(tapShownAfterMs.size(), 17u);
    std::sort(tapShownAfterMs.begin(), tapShownAfterMs.end());
    EXPECT_LE(tapShownAfterMs[8], 60000u);
    EXPECT_LE(tapShownAfterMs.back(), 180000u);
    std::printf("owner 31 Oct: a tap shows after %llu s (median), %llu s (slowest)\n",
                static_cast<unsigned long long>(tapShownAfterMs[8] / 1000),
                static_cast<unsigned long long>(tapShownAfterMs.back() / 1000));
}
// The owner's week (25 Oct - 1 Nov 2026) with the clock: the nights teach how fast the sensor falls
// before a round nobody tapped for (also while the store mixes after a short reheat), and a round after
// a faster fall is usage. Printed per day for the report.
TEST(DhwEpisodes, OwnersWeekLearnsTheNightRoundsAndCountsFasterFallsAsUsage) {
    ScopedTz tz(ScopedTz::amsterdam);
    std::ifstream file("test/fixtures/dhw-owner-week-20261025.txt");
    ASSERT_TRUE(file.good());
    constexpr uint32_t origin = 1792879200;            // 25 Oct 2026 00:00 CEST
    DhwEpisodes e; std::string line;
    EXPECT_STREQ(e.method(), "dhw_temperature_fall");
    EXPECT_FALSE(e.nightLearned());
    EXPECT_EQ(e.usageRate(), DhwEpisodes::defaultUsageRate);
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream in(line); uint64_t ms; char kind; int value;
        in >> ms >> kind >> value;
        const DhwEpisodes::Day before = e.today();
        e.clock(origin + static_cast<uint32_t>(ms / 1000), ms);
        if (before.day != DhwEpisodes::unknownDay && e.today().day != before.day)
            std::printf("owner day %d: %u keep-warm, %u taps (limit %d)\n", before.day, before.count[DhwEpisodes::keepWarm],
                        before.count[DhwEpisodes::tapping], e.usageRate());
        if (kind == 'T') e.temperature(value, ms); else e.state(static_cast<uint8_t>(value), ms);
    }
    EXPECT_TRUE(e.nightLearned());
    EXPECT_EQ(e.usageRate(), 137);                     // night rounds while the store mixes: up to 1.1 K/min
    const auto week = e.lastSevenDays();
    std::printf("owner week: usage above %d hundredths K/min; last 7 days %u keep-warm, %u taps; today %u keep-warm, %u taps\n",
                e.usageRate(), week.count[DhwEpisodes::keepWarm], week.count[DhwEpisodes::tapping],
                e.today().count[DhwEpisodes::keepWarm], e.today().count[DhwEpisodes::tapping]);
    // With the episode's own fall only, the reference counts 1-5 more keep-warm rounds a day.
    EXPECT_EQ(week.count[DhwEpisodes::keepWarm], 142);
    EXPECT_EQ(week.count[DhwEpisodes::tapping], 72);
    EXPECT_EQ(e.today().count[DhwEpisodes::keepWarm], 14);
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 2);
    EXPECT_EQ(week.count[DhwEpisodes::unknown], 0);
    EXPECT_EQ(week.count[DhwEpisodes::charging], 0);
    cJSON* json = e.summaryJson();
    ASSERT_NE(json, nullptr);
    EXPECT_STREQ(cJSON_GetObjectItem(json, "baseline")->valuestring, "night");
    cJSON_Delete(json);
}
// A small tap (washing hands) only cools the sensor before the round; standing loss and mixing are slower.
TEST(DhwEpisodes, AFastFallBeforeAShallowRoundIsUsageASlowOneKeepingWarm) {
    const auto run = [](int32_t fallCenti, uint64_t overMs) {
        DhwEpisodes e; uint64_t t = 0;
        e.state(0x00, t);
        e.temperature(6500, t + 1000);                 // the peak after the previous round
        for (uint64_t at = 10000; at <= overMs; at += 10000) {
            e.temperature(6500 - static_cast<int32_t>(fallCenti * at / overMs), t + at); e.state(0x00, t + at);
        }
        t = overMs + 10000;
        e.state(0x0A, t); e.temperature(5900, t + 5000); e.state(0x0A, t + 10000); e.temperature(6400, t + 15000);
        e.state(0x00, t + 20000);
        return e.today();
    };
    EXPECT_EQ(run(700, 600000).count[DhwEpisodes::keepWarm], 1);     // 7 K in 10 min: 0.7 K/min
    EXPECT_EQ(run(700, 120000).count[DhwEpisodes::tapping], 1);      // 7 K in 2 min: 3.5 K/min
    EXPECT_EQ(run(700, 7200000).count[DhwEpisodes::keepWarm], 1);    // 7 K in 2 h
}
// The night teaches the limit: a round faster than this installation's night rounds is usage.
TEST(DhwEpisodes, NightRoundsSetTheLimitAndTheBaselineSaysSo) {
    ScopedTz tz(ScopedTz::amsterdam);
    constexpr uint32_t night = 1793232000;              // 1 Nov 2026 00:00 UTC = 01:00 CET
    DhwEpisodes e; uint64_t t = 0;
    const auto round = [&](int32_t fallCenti, uint64_t overMs) {
        e.clock(night + static_cast<uint32_t>(t / 1000), t);
        e.state(0x00, t); e.temperature(6500, t + 1000);
        for (uint64_t at = 10000; at <= overMs; at += 10000) { e.temperature(6500 - static_cast<int32_t>(fallCenti * at / overMs), t + at); e.state(0x00, t + at); }
        t += overMs + 10000;
        e.state(0x0A, t); e.temperature(5900, t + 5000); e.state(0x0A, t + 10000); e.state(0x00, t + 20000);
        t += 20000;
    };
    cJSON* json = e.summaryJson();
    EXPECT_STREQ(cJSON_GetObjectItem(json, "baseline")->valuestring, "default");
    cJSON_Delete(json);
    for (int i = 0; i < 4; ++i) round(600, 1200000);   // 6 K in 20 min at night: 0.3 K/min
    EXPECT_TRUE(e.nightLearned());
    EXPECT_EQ(e.usageRate(), 36);                      // 29 (6 K over 20 min 9 s) + a quarter
    EXPECT_EQ(e.today().count[DhwEpisodes::keepWarm], 4);
    t += 6 * 3600000;                                  // the morning
    round(600, 600000);                                // 0.6 K/min: faster than any night round
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 1);
    json = e.summaryJson();
    EXPECT_STREQ(cJSON_GetObjectItem(json, "baseline")->valuestring, "night");
    cJSON_Delete(json);
    DhwEpisodes flow; flow.flow(0); flow.flow(12);     // a flow meter decides: no baseline
    json = flow.summaryJson();
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(json, "baseline")));
    cJSON_Delete(json);
}
// A dip that recovers is keeping warm; a smaller fall that lasts is a tap; a deep fall is a tap.
TEST(DhwEpisodes, ABriefDipIsKeepWarmALastingOrDeepFallIsATap) {
    const auto run = [](std::vector<int32_t> inside) {
        DhwEpisodes e; uint64_t t = 0;
        for (int i = 0; i < 12; ++i) { t += 10000; e.temperature(5900, t - 5000); e.state(0x00, t); }
        for (int32_t c : inside) { t += 10000; e.temperature(c, t - 5000); e.state(0x0A, t); }
        t += 10000; e.state(0x00, t);
        return e.today();
    };
    auto d = run({5800, 5200, 4900, 5100, 5500, 5800, 6000});        // 10 K for ~30 s, then reheated
    EXPECT_EQ(d.count[DhwEpisodes::keepWarm], 1);
    d = run({5600, 5000, 5000, 5000, 5000, 5000, 5000, 5000, 5000, 5000, 5000, 5100, 5200}); // 9 K for 100 s
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 1);
    d = run({5000, 4300, 4500, 5600});                                // 16 K deep, brief
    EXPECT_EQ(d.count[DhwEpisodes::tapping], 1);
}
// Universal: a boiler with a cylinder charges it; a combi with a live flow uses the flow.
TEST(DhwEpisodes, ACylinderBoilerChargesInsteadOfTappingOrKeepingWarm) {
    DhwEpisodes e;
    e.dhwType(3);                                                     // buffer (cylinder)
    e.temperature(6000, 0); e.state(0x0A, 1000); e.temperature(3000, 11000); e.state(0x00, 600000);
    EXPECT_EQ(e.today().count[DhwEpisodes::charging], 1);
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 0);
    EXPECT_TRUE(e.storage());
    EXPECT_STREQ(e.method(), "storage");
    const auto j = json(e, 600000);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(j.get(), "method")), "storage");
    EXPECT_EQ(at(cJSON_GetObjectItem(j.get(), "today"), "charging", "count"), 1);
}
TEST(DhwEpisodes, AChargingBitThatChangesMarksTheCylinderUnlessTheTypeIsACombi) {
    DhwEpisodes e;
    e.chargingBit(false); e.state(0x00, 0);
    e.chargingBit(true); e.state(0x0A, 10000); e.state(0x00, 20000);     // the bit changed: live, set in the episode
    e.chargingBit(false); e.state(0x0A, 30000); e.state(0x00, 40000);    // not set: no temperature, unknown
    EXPECT_EQ(e.today().count[DhwEpisodes::charging], 1);
    EXPECT_EQ(e.today().count[DhwEpisodes::unknown], 1);
    DhwEpisodes combi;
    combi.dhwType(1);
    combi.chargingBit(false); combi.chargingBit(true);
    combi.temperature(6000, 0); combi.state(0x0A, 1000); combi.temperature(5800, 11000); combi.state(0x00, 21000);
    EXPECT_FALSE(combi.storage());
    EXPECT_EQ(combi.today().count[DhwEpisodes::keepWarm], 1);
    EXPECT_STREQ(combi.method(), "dhw_temperature_fall");
}
// What the boiler does now, for the Home Assistant timeline and the E32 chart.
TEST(DhwEpisodes, ActivityFollowsTheOpenEpisodeAndTheFlame) {
    DhwEpisodes e;
    EXPECT_EQ(e.activity(), nullptr);                                  // nothing heard yet
    e.state(0x00, 0); EXPECT_STREQ(e.activity(), "idle");
    e.state(0x08, 10000); EXPECT_STREQ(e.activity(), "heating");        // flame without hot water
    e.temperature(5800, 15000);
    e.state(0x0A, 20000); EXPECT_STREQ(e.activity(), "keep_warm");     // hot water, no fall yet
    e.temperature(5600, 25000); EXPECT_STREQ(e.activity(), "keep_warm");
    e.temperature(3500, 30000); EXPECT_STREQ(e.activity(), "tapping");  // a deep fall: a tap after all
    ASSERT_TRUE(e.openKind()); EXPECT_EQ(*e.openKind(), DhwEpisodes::tapping);
    e.state(0x00, 60000); EXPECT_STREQ(e.activity(), "idle");
    EXPECT_FALSE(e.openKind());
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 1);
    DhwEpisodes cylinder; cylinder.dhwType(4);
    cylinder.state(0x0A, 0); EXPECT_STREQ(cylinder.activity(), "charging");
    DhwEpisodes blind;
    blind.state(0x0A, 0); EXPECT_STREQ(blind.activity(), "hot_water");  // no source to sort it
}
}
