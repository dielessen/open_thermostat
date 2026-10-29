#include "control/DhwEpisodes.h"
#include "EMS/EmsEntityCatalog.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <fstream>
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
    DhwEpisodes e;
    const uint32_t day0 = 1792800000;                // 2026-10-24 00:00 UTC; the steps cross the CEST end
    const auto episode = [&](uint32_t unix, uint64_t ms) {
        ClassicBoilerMonitor m;
        e.observe(m, ms, unix);
        e.temperature(6000, ms); e.state(0x0A, ms + 1000); e.temperature(4000, ms + 11000); e.state(0x00, ms + 21000);
    };
    for (uint32_t i = 0; i < 9; ++i) episode(day0 + i * 86400, uint64_t(i) * 86400000);
    EXPECT_EQ(e.today().count[DhwEpisodes::tapping], 1);
    EXPECT_EQ(e.today().day, heating::control::ShadowComparison::localDay(day0 + 8 * 86400));
    EXPECT_EQ(e.lastSevenDays().count[DhwEpisodes::tapping], 7);
    EXPECT_EQ(e.lastSevenDays().seconds[DhwEpisodes::tapping], 7u * 20);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(json(e, 9ull * 86400000).get(), "clock_known")));
}
}
