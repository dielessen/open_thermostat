#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/UBAMonitorFastPlus.h"
#include "EMS/UBAMonitorWWPlus.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <stdexcept>

namespace {
using namespace heating::ems;

// Independent bit-shift CRC, not the production lookup/encoder.
uint8_t wireCrc(const std::vector<uint8_t> &bytes) {
    uint8_t crc = 0;
    for (auto b : bytes) crc = static_cast<uint8_t>((crc << 1) ^ ((crc & 0x80) ? 0x19 : 0) ^ b);
    return crc;
}
EmsTelegram wire(std::vector<uint8_t> bytes) {
    bytes.push_back(wireCrc(bytes));
    return EmsTelegram::fromRawData(bytes.data(), bytes.size());
}
EmsTelegram data(uint16_t type, std::vector<uint8_t> payload, uint8_t offset = 0,
                 uint8_t source = 8, uint8_t destination = 0) {
    return {destination ? EmsTelegram::WRITE : EmsTelegram::BROADCAST,
            source, destination, offset, type, std::move(payload)};
}

TEST(ClassicReception, ReportsFreshnessWithoutGrantingControlOrAcceptingOtherSenders) {
    ClassicBoilerMonitor m;
    const auto snapshot = [&](uint64_t now) {
        std::ostringstream ss;
        m.writeReceptionJSON(ss, now);
        return std::unique_ptr<cJSON, decltype(&cJSON_Delete)>(cJSON_Parse(ss.str().c_str()), cJSON_Delete);
    };
    auto initial = snapshot(0);
    ASSERT_NE(initial, nullptr);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(initial.get(), "state")), "no_boiler_reports");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(initial.get(), "last_report_age_ms")));
    m.receive(data(0x18, {40}, 0, 0x19), 100);
    m.receive(data(0x77, {40}), 100);
    m.receive({EmsTelegram::READ, 8, 0x19, 0, 0x18, {1}}, 100);
    auto ignored = snapshot(100);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(ignored.get(), "report_count")), 0);
    // Zero uptime is a legitimate timestamp, including a foreign destination.
    ASSERT_TRUE(m.receive(data(0x18, {0, 1, 0x72, 80, 0, 0, 0, 0x25}, 0, 8, 0x17), 0));
    auto fresh = snapshot(29999);
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(fresh.get(), "fresh_report")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(fresh.get(), "control_approved")));
    auto fields = cJSON_GetObjectItem(fresh.get(), "fresh_classic_fields");
    EXPECT_EQ(cJSON_GetArraySize(fields), 7); // target, flow, power limit, modulation, raw state, inferred CV/DHW
    auto stale = snapshot(30000);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(stale.get(), "state")), "stale");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(stale.get(), "fresh_classic_fields")), 0);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(stale.get(), "last_report_age_ms")), 30000);
    m.receive(data(0x18, {40}), 40000);
    auto backwards = snapshot(39999);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(backwards.get(), "fresh_report")));
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(backwards.get(), "last_report_age_ms")));
    m.receive(data(0xE4, {1}), 41000);
    auto conflict = snapshot(41000);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(conflict.get(), "state")), "conflicting_families");
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(conflict.get(), "control_approved")));
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(conflict.get(), "fresh_classic_fields")), 0);
}

TEST(ClassicReception, ExtensibleTelemetryRemainsValidAndDoesNotWrapAt32Bits) {
    ClassicBoilerMonitor m;
    const uint64_t now = (uint64_t{1} << 32) + 123;
    m.receive(data(0x18, {40}), now);
    std::ostringstream ss;
    m.writeJSON(ss, now + 1, false);
    ss << ",\"transport\":{\"enabled\":true}}";
    auto json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>(cJSON_Parse(ss.str().c_str()), cJSON_Delete);
    ASSERT_NE(json, nullptr);
    auto reception = cJSON_GetObjectItem(json.get(), "reception");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(reception, "last_report_age_ms")), 1);
    EXPECT_TRUE(cJSON_IsObject(cJSON_GetObjectItem(json.get(), "fields")));
    EXPECT_TRUE(cJSON_IsTrue(cJSON_GetObjectItem(cJSON_GetObjectItem(json.get(), "transport"), "enabled")));
}

TEST(ClassicReception, DistinguishesPlusAndInvalidOrIncompleteMeasurements) {
    ClassicBoilerMonitor plus;
    plus.receive(data(0xE4, {1}), 100);
    std::ostringstream ss;
    plus.writeJSON(ss, 100);
    auto json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>(cJSON_Parse(ss.str().c_str()), cJSON_Delete);
    ASSERT_NE(json, nullptr);
    auto reception = cJSON_GetObjectItem(json.get(), "reception");
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(reception, "state")), "plus_reports_received");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(reception, "fresh_classic_fields")), 0);
    ClassicBoilerMonitor invalid;
    invalid.receive(data(0x18, {0x80, 0}, 1), 100); // invalid temperature sentinel
    invalid.receive(data(0x18, {0x01}, 1), 200); // incomplete word
    std::ostringstream fields;
    invalid.writeReceptionJSON(fields, 200);
    EXPECT_NE(fields.str().find("\"report_count\":2"), std::string::npos);
    EXPECT_NE(fields.str().find("\"fresh_classic_fields\":[]"), std::string::npos);
}

TEST(ClassicBoiler, ReplaysCaptured0PWithoutInventingFlameOrMissingPressure) {
    // Genuine CRC-valid EMS-ESP capture, 13 Oct2026 incident report. No timestamps
    // or household/device identities are needed by this fixture. Wire includes CRC03.
    const uint8_t raw[]{0x08,0x00,0x18,0x00,0x00,0x01,0x72,0x00,0x00,0x00,
        0x00,0x00,0x00,0x80,0x00,0x80,0x00,0x01,0x68,0x00,0x00,0xFF,
        0x30,0x50,0x00,0x00,0xFF,0x00,0x00,0x03};
    ClassicBoilerMonitor m;
    ASSERT_TRUE(m.receive(EmsTelegram::fromRawData(raw, sizeof(raw)), 100));
    EXPECT_EQ(m.capabilities().profile(), BoilerProtocol::classic);
    EXPECT_EQ(m.value(BoilerField::selectedFlow, 100), 0);
    EXPECT_EQ(m.value(BoilerField::flow, 100), 3700);
    EXPECT_EQ(m.value(BoilerField::returnTemp, 100), 3600);
    EXPECT_EQ(m.value(BoilerField::modulation, 100), 0);
    EXPECT_FALSE(m.value(BoilerField::pressure, 100));
    EXPECT_EQ(m.value(BoilerField::displayCode, 100), 0x3050);
    EXPECT_EQ(m.value(BoilerField::serviceNumber, 100), 0); // zero is a real code value
    EXPECT_FALSE(m.value(BoilerField::rawBurner, 100));
    EXPECT_EQ(m.sample(BoilerField::rawBurner).quality, BoilerQuality::unreliable);
    EXPECT_FALSE(m.capabilities().allowsLegacyPlusWrites());
}

TEST(ClassicBoiler, SyntheticGoldenFastStatusKeepsDemandAndModulationSeparate) {
    // Independently specified offsets: target45C, flow45.6C, powerlimit80%, actual37%.
    auto t = wire({0x08,0x00,0x18,0x00,45,0x01,0xC8,80,37,0x09,0,0x25});
    ClassicBoilerMonitor m;
    ASSERT_TRUE(m.receive(t, 123));
    EXPECT_EQ(m.value(BoilerField::selectedFlow,123),4500);
    EXPECT_EQ(m.value(BoilerField::flow,123),4560);
    EXPECT_EQ(m.value(BoilerField::requestedPowerLimit,123),80);
    EXPECT_EQ(m.value(BoilerField::modulation,123),37);
    EXPECT_EQ(m.value(BoilerField::heatingActive,123),1);
    EXPECT_EQ(m.value(BoilerField::dhwActive,123),0);
    EXPECT_EQ(m.sample(BoilerField::heatingActive).quality,BoilerQuality::inferred);
    EXPECT_FALSE(m.value(BoilerField::rawPump,123));
    EXPECT_EQ(m.value(BoilerField::rawPump,123,true),1);
}

TEST(ClassicBoiler, FragmentMustContainTheEntireFieldAndNeverRefreshesOtherFields) {
    ClassicBoilerMonitor m;
    m.receive(data(0x18,{0x01,0xC8},1),10);
    m.receive(data(0x18,{0x30,0x48},18),1000);
    EXPECT_EQ(m.value(BoilerField::displayCode,1000),0x3048);
    EXPECT_EQ(m.sample(BoilerField::flow).observedMs,10u);
    m.receive(data(0x18,{0x50},19),2000);
    EXPECT_EQ(m.value(BoilerField::displayCode,2000),0x3048); // not half-overwritten
    m.receive(data(0x18,{0x30},18),3000);
    EXPECT_EQ(m.sample(BoilerField::displayCode).observedMs,1000u);
    EXPECT_FALSE(m.value(BoilerField::flow,30010));
    EXPECT_TRUE(m.value(BoilerField::displayCode,30010));
}

TEST(ClassicBoiler, ExplicitUnavailableSampleInvalidatesPreviousTemperature) {
    ClassicBoilerMonitor m;
    m.receive(data(0x18,{0x01,0xC8},1),10);
    ASSERT_EQ(m.value(BoilerField::flow,10),4560);
    m.receive(data(0x18,{0x80,0x00},1),20);
    EXPECT_FALSE(m.value(BoilerField::flow,20));
    EXPECT_TRUE(m.sample(BoilerField::flow).observed);
    EXPECT_FALSE(m.sample(BoilerField::flow).raw);
}

TEST(ClassicBoiler, SignedOutdoorTemperatureAndThreeByteCounterAtFrameEnd) {
    ClassicBoilerMonitor m;
    m.receive(data(0x19,{0xFF,0xEA}),10); // -2.2C from documented sample
    m.receive(data(0x19,{0x01,0x02,0x03},22),11);
    EXPECT_EQ(m.value(BoilerField::outdoor,11),-220);
    EXPECT_FALSE(m.value(BoilerField::heatingStarts,11));
    EXPECT_EQ(m.value(BoilerField::heatingStarts,11,true),0x010203);
    m.receive(data(0x19,{0xFF,0xFF}),12); // -.1C is valid, NOT an unsigned sentinel
    EXPECT_EQ(m.value(BoilerField::outdoor,12),-10);
    m.receive(data(0x19,{0xFF,0xFF,0xFF},22),13);
    EXPECT_FALSE(m.value(BoilerField::heatingStarts,13));
}

TEST(ClassicBoiler, ParameterFFMeansEnabledButTemperatureFFMeansUnavailable) {
    ClassicBoilerMonitor m;
    m.receive(data(0x16,{0xFF,55,90}),10);
    m.receive(data(0x33,{8,0xFF,50}),10);
    EXPECT_EQ(m.value(BoilerField::heatingEnabled,10),1);
    EXPECT_EQ(m.value(BoilerField::heatingLimit,10),5500);
    EXPECT_EQ(m.value(BoilerField::maxBurnerPower,10),90);
    EXPECT_EQ(m.value(BoilerField::dhwEnabled,10),1);
    EXPECT_EQ(m.value(BoilerField::selectedDhw,10),5000);
    m.receive(data(0x33,{8,0,0xFF}),20);
    EXPECT_EQ(m.value(BoilerField::dhwEnabled,20),0);
    EXPECT_FALSE(m.value(BoilerField::selectedDhw,20));
}

TEST(ClassicBoiler, DhwMonitorUsesItsOwnFlowCountersAndTargetOffsets) {
    ClassicBoilerMonitor m;
    m.receive(data(0x34,{48,0x01,0xBA,0x7D,0,0x21,0,0,3,15,0,1,0x22,0,0x19,0x5B}),100);
    EXPECT_EQ(m.value(BoilerField::monitorDhwTarget,100),4800);
    EXPECT_EQ(m.value(BoilerField::dhwTemp,100),4420);
    EXPECT_FALSE(m.value(BoilerField::dhwFlow,100));
    EXPECT_EQ(m.value(BoilerField::dhwFlow,100,true),15); // raw tenths L/min, not trusted flow
    EXPECT_EQ(m.value(BoilerField::dhwMinutes,100,true),290);
    EXPECT_EQ(m.value(BoilerField::dhwStarts,100,true),6491);
    EXPECT_FALSE(m.value(BoilerField::selectedDhw,100));
    EXPECT_FALSE(m.value(BoilerField::flow,100));
}

TEST(ClassicBoiler, SourceAndOperationAdmissionAllowsPassiveOtherMasterButNotItsWrites) {
    ClassicBoilerMonitor m;
    EXPECT_FALSE(m.receive(data(0x18,{45},0,0x10),1));
    EXPECT_FALSE(m.receive(EmsTelegram(EmsTelegram::READ,8,0x99,0,0x18,{27}),1));
    EXPECT_FALSE(m.receive(data(0x18,{}),1));
    EXPECT_EQ(m.capabilities().profile(),BoilerProtocol::unknown);
    EXPECT_TRUE(m.receive(data(0x18,{45},0,8,0x0B),2));
    EXPECT_EQ(m.value(BoilerField::selectedFlow,2),4500);
}

TEST(ClassicBoiler, ReadbackDoesNotRenewFreshnessAnd32BitWrapCannotReviveOldData) {
    ClassicBoilerMonitor m;
    const uint64_t start = 0xFFFFF000ULL;
    m.receive(data(0x18,{50}),start);
    EXPECT_EQ(m.value(BoilerField::selectedFlow,start+29999u),5000);
    EXPECT_FALSE(m.value(BoilerField::selectedFlow,start+30000u));
    EXPECT_FALSE(m.value(BoilerField::selectedFlow,start+(1ULL<<32)));
    EXPECT_FALSE(m.value(BoilerField::selectedFlow,start-1));
    std::ostringstream a,b;
    m.writeJSON(a,start+10000u); m.writeJSON(b,start+20000u);
    EXPECT_EQ(m.sample(BoilerField::selectedFlow).observedMs,start);
    EXPECT_NE(a.str().find("\"age_ms\":10000"),std::string::npos);
    EXPECT_NE(b.str().find("\"age_ms\":20000"),std::string::npos);
}

TEST(ClassicBoiler, JsonIsValidAndKeepsUnknownInvalidStaleAndUnreliableDistinct) {
    ClassicBoilerMonitor m;
    m.receive(data(0x18,{0x22,0x5C},18),100); // adversarial ASCII quote/backslash
    m.receive(data(0x18,{0xFF},17),100);
    m.receive(data(0x18,{1},7),100);
    std::ostringstream s; m.writeJSON(s,101);
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> doc(cJSON_Parse(s.str().c_str()),cJSON_Delete);
    ASSERT_TRUE(doc);
    auto fields=cJSON_GetObjectItem(doc.get(),"fields");
    auto code=cJSON_GetObjectItem(fields,"display_code");
    EXPECT_STREQ(cJSON_GetObjectItem(code,"value")->valuestring,"\"\\");
    auto pressure=cJSON_GetObjectItem(fields,"pressure");
    EXPECT_STREQ(cJSON_GetObjectItem(pressure,"state")->valuestring,"invalid");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(pressure,"value")));
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(fields,"raw_burner_bit"),"quality")->valuestring,"unreliable");
    EXPECT_STREQ(cJSON_GetObjectItem(cJSON_GetObjectItem(fields,"measured_flow_temperature"),"state")->valuestring,"unknown");
    std::ostringstream expired; m.writeJSON(expired,30100);
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> old(cJSON_Parse(expired.str().c_str()),cJSON_Delete);
    ASSERT_TRUE(old);
    auto stale=cJSON_GetObjectItem(cJSON_GetObjectItem(old.get(),"fields"),"display_code");
    EXPECT_STREQ(cJSON_GetObjectItem(stale,"state")->valuestring,"stale");
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(stale,"value")));
}

TEST(ClassicBoiler, ObservedFamilyIsNotPhysicalCommissioningAndConflictClosesLegacyWrites) {
    BoilerCapabilities c;
    EXPECT_FALSE(c.allowsLegacyPlusWrites());
    c.observe(0xE4); EXPECT_TRUE(c.allowsLegacyPlusWrites());
    c.observe(0x18); EXPECT_EQ(c.profile(),BoilerProtocol::conflict);
    EXPECT_FALSE(c.allowsLegacyPlusWrites());
    EXPECT_FALSE(c.classicControlCommissioned);
    c.observe(0xE4); EXPECT_EQ(c.profile(),BoilerProtocol::conflict);
}

TEST(EmsRawParser, RejectsShortCorruptOversizedAndInvalidExtendedFrames) {
    std::array<uint8_t,33> bytes{};
    EXPECT_THROW(EmsTelegram::fromRawData(nullptr,10),std::runtime_error);
    for (size_t n=0;n<5;++n) EXPECT_THROW(EmsTelegram::fromRawData(bytes.data(),n),std::runtime_error);
    EXPECT_THROW(EmsTelegram::fromRawData(bytes.data(),33),std::runtime_error);
    std::vector<uint8_t> shortExtended{8,0,0xFF,0,1};
    shortExtended.push_back(wireCrc(shortExtended));
    EXPECT_THROW(EmsTelegram::fromRawData(shortExtended.data(),shortExtended.size()),std::runtime_error);
    const uint8_t corrupt[]{8,0,0x18,0,45,0};
    EXPECT_THROW(EmsTelegram::fromRawData(corrupt,sizeof(corrupt)),std::runtime_error);
    EXPECT_THROW(wire({8,0,0xFF,0,0xFF,0xFF,0}),std::runtime_error);
}

TEST(EmsRawParser, ClassicAndExtendedReadHeadersNeverBecomeDataUpdates) {
    auto classic=wire({0x19,0x88,0x18,0,27});
    EXPECT_EQ(classic.getOperationType(),EmsTelegram::READ);
    EXPECT_EQ(classic.getRequestedDataSize(),27);
    auto plus=wire({0x19,0x88,0xFF,0,27,0x01,0xE0});
    EXPECT_EQ(plus.getTypeId(),0x2E0);
    EXPECT_EQ(plus.getOperationType(),EmsTelegram::READ);
    EXPECT_EQ(plus.getRequestedDataSize(),27);
}

TEST(EmsRawParser, PlusGoldenOffsetsRemainUnchangedAndCannotPopulateClassicFields) {
    const std::vector<uint8_t> payload{0,'0','H',0,0,3,45,0x01,0xC8,80,37,3};
    UBAMonitorFastPlus p(EmsTelegram::BROADCAST,8,0,0,0xE4,payload);
    EXPECT_EQ(p.getCurrentFlowTemperature(),456);
    EXPECT_EQ(p.getSelectedFlowTemperature(),45);
    EXPECT_EQ(p.getCurrentBurnerPower(),37);
    EXPECT_EQ(p.getServiceCode(),3);
    ClassicBoilerMonitor m;
    EXPECT_FALSE(m.receive(p,100));
    EXPECT_EQ(m.capabilities().profile(),BoilerProtocol::plus);
    EXPECT_FALSE(m.value(BoilerField::flow,100));
    UBAMonitorWWPlus ww(EmsTelegram::BROADCAST,8,0,1,0xE9,{0x01,0xBA});
    EXPECT_EQ(ww.getCurrentTemperature(),442);
    EXPECT_FALSE(ww.getFlow());
}

TEST(ClassicBoiler, ReplaysAllFiveHistoricalMonitorParameterFamiliesAndRejectsRequestEcho) {
    // Captured source SHA256 8a45aa6f5184e60c67d1034ca02f42014c5af6eb9afcd4c4cb1a95dd81d26e64.
    // Static expected values are from independent documented offsets, not this decoder.
    const auto raw = [](const char *hex) {
        std::istringstream in(hex); std::vector<uint8_t> bytes; unsigned value;
        while (in >> std::hex >> value) bytes.push_back(static_cast<uint8_t>(value));
        return EmsTelegram::fromRawData(bytes.data(),bytes.size());
    };
    ClassicBoilerMonitor m;
    ASSERT_TRUE(m.receive(raw("08 00 18 00 00 02 E4 00 3B 0A 11 00 00 80 00 80 00 02 80 00 00 FF 3D 48 00 00 FF 00 00 56"),100));
    EXPECT_EQ(m.value(BoilerField::flow,100),7400);
    EXPECT_EQ(m.value(BoilerField::returnTemp,100),6400);
    EXPECT_EQ(m.value(BoilerField::modulation,100),59);
    EXPECT_EQ(m.value(BoilerField::displayCode,100),0x3D48); // =H / DHW, not CV evidence
    EXPECT_EQ(m.value(BoilerField::dhwActive,100),1);
    EXPECT_EQ(m.value(BoilerField::heatingActive,100),0);
    ASSERT_TRUE(m.receive(raw("08 00 19 00 80 00 80 00 80 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 C7"),110));
    EXPECT_FALSE(m.value(BoilerField::outdoor,110));
    EXPECT_EQ(m.value(BoilerField::burnerStarts,110,true),0);
    EXPECT_FALSE(m.value(BoilerField::burnerStarts,110));
    ASSERT_TRUE(m.receive(raw("08 0B 16 00 FF 37 64 00 06 FA 0A 01 03 64 64 00 D2"),120));
    EXPECT_EQ(m.value(BoilerField::heatingLimit,120),5500);
    EXPECT_EQ(m.value(BoilerField::pumpRunOn,120),3);
    ASSERT_TRUE(m.receive(raw("08 00 33 00 08 FF 37 FB FF 28 FF 02 46 00 FF E2"),130));
    EXPECT_EQ(m.value(BoilerField::selectedDhw,130),5500);
    ASSERT_TRUE(m.receive(raw("08 00 34 00 3C 00 D2 80 00 20 00 00 01 19 00 00 00 00 00 00 00 6C"),140));
    EXPECT_EQ(m.value(BoilerField::dhwTemp,140),2100);
    EXPECT_EQ(m.value(BoilerField::monitorDhwTarget,140),6000);
    EXPECT_EQ(m.value(BoilerField::selectedDhw,140),5500); // different source semantics
    EXPECT_EQ(m.value(BoilerField::dhwFlow,140,true),25);
    EXPECT_FALSE(m.receive(raw("0B 88 16 00 1B D7"),150));
    EXPECT_FALSE(m.receive(raw("17 08 1A 00 24 64 64 00 42"),160));
    EXPECT_EQ(m.value(BoilerField::selectedFlow,160),0); // request36C is NOT reported target0C
    EXPECT_EQ(m.value(BoilerField::heatingLimit,160),5500);
}

TEST(ClassicExpanded, FastStorageCurrentAndRawFlagsPreserveFragmentsAndQuality) {
    ClassicBoilerMonitor m;
    m.receive(data(0x18,{0xFF},7),100);
    m.receive(data(0x18,{0x01,0xF4,0x02,0x58,0x01,0x90,0x00,0x1B},9),110);
    EXPECT_EQ(m.value(BoilerField::storageTemp1,110),5000);
    EXPECT_EQ(m.value(BoilerField::storageTemp2,110),6000);
    EXPECT_EQ(m.value(BoilerField::ionisationCurrent,110),27); // published 2.7 uA
    for(auto f:{BoilerField::rawSecondBurner,BoilerField::rawIgnition,BoilerField::rawOilPreheat,
                BoilerField::rawDhwValve,BoilerField::rawDhwCirculation}) {
        EXPECT_FALSE(m.value(f,110)); EXPECT_EQ(m.value(f,110,true),1);
    }
    m.receive(data(0x18,{0x01},15),120); // no refresh from incomplete word
    EXPECT_EQ(m.sample(BoilerField::ionisationCurrent).observedMs,110);
    for(auto word:{0x7D00,0x7FFF,0x8000,0x8300,0xFFFF}) {
        m.receive(data(0x18,{uint8_t(word>>8),uint8_t(word)},15),130);
        EXPECT_FALSE(m.value(BoilerField::ionisationCurrent,130));
    }
    EXPECT_FALSE(m.value(BoilerField::storageTemp1,30110));
}
TEST(ClassicExpanded, SlowTemperaturesPumpAndCountersRemainDistinct) {
    ClassicBoilerMonitor m;
    m.receive(data(0x19,{0x02,0x58,0x07,0xA0},2),10);
    m.receive(data(0x19,{100},9),10);
    m.receive(data(0x19,{0,1,2},16),10);
    m.receive(data(0x19,{0x01,0x90},25),10);
    EXPECT_EQ(m.value(BoilerField::boilerTemp,10),6000);
    EXPECT_EQ(m.value(BoilerField::exhaustTemp,10),19520);
    EXPECT_EQ(m.value(BoilerField::switchTemp,10),4000);
    EXPECT_EQ(m.value(BoilerField::pumpModulation,10),100);
    EXPECT_FALSE(m.value(BoilerField::secondBurnerMinutes,10));
    EXPECT_EQ(m.value(BoilerField::secondBurnerMinutes,10,true),258);
    m.receive(data(0x19,{101},9),20);
    EXPECT_FALSE(m.value(BoilerField::pumpModulation,20));
}
TEST(ClassicExpanded, SignedParametersAndDhwComfortAreWireValues) {
    ClassicBoilerMonitor m;
    m.receive(data(0x16,{0xFF,0xFA,15,0,3,100,20,2,8,0xF8},4),10);
    m.receive(data(0x16,{40},23),10);
    EXPECT_EQ(m.value(BoilerField::hysteresisOff,10),-1);
    EXPECT_EQ(m.value(BoilerField::hysteresisOn,10),-6);
    EXPECT_EQ(m.value(BoilerField::minimumBurnerPeriod,10),15);
    EXPECT_EQ(m.value(BoilerField::secondaryHysteresisOn,10),-8);
    EXPECT_EQ(m.value(BoilerField::pumpStartTemp,10),4000);
    m.receive(data(0x16,{0x7F},4),20);
    EXPECT_FALSE(m.value(BoilerField::hysteresisOff,20));
    m.receive(data(0x33,{0xFB,0xFF,40,0xFF,2,70,0xD8,0xFF},3),30);
    EXPECT_EQ(m.value(BoilerField::dhwHysteresisOn,30),-5);
    EXPECT_EQ(m.value(BoilerField::dhwChargeOptimisation,30),1);
    EXPECT_EQ(m.value(BoilerField::dhwCirculationEnabled,30),1);
    EXPECT_EQ(m.value(BoilerField::dhwComfortMode,30),0xD8);
    EXPECT_EQ(m.value(BoilerField::dhwChargeType,30),1); // FF is valid bit, not missing
    m.receive(data(0x33,{0xEC},9),40);
    EXPECT_EQ(m.value(BoilerField::dhwComfortMode,40),0xEC);
    m.receive(data(0x33,{7},9),50);
    EXPECT_FALSE(m.value(BoilerField::dhwComfortMode,50));
}
TEST(ClassicExpanded, DhwExtraSensorsAndRawStatusNeverBecomeControlEvidence) {
    ClassicBoilerMonitor m;
    m.receive(data(0x34,{0x01,0xF4,0x7E},3),10);
    m.receive(data(0x34,{3},8),10);
    m.receive(data(0x34,{0x02,0x58},17),10);
    EXPECT_EQ(m.value(BoilerField::dhwTemp2,10),5000);
    EXPECT_EQ(m.value(BoilerField::dhwSolarTemp,10),6000);
    EXPECT_EQ(m.value(BoilerField::dhwType,10),3);
    for(auto f:{BoilerField::rawDhwOneTime,BoilerField::rawDhwDisinfection,BoilerField::rawDhwCharging,
                BoilerField::rawDhwRecharging,BoilerField::rawDhwTempOk,BoilerField::rawDhwActive}) {
        EXPECT_FALSE(m.value(f,10)); EXPECT_EQ(m.value(f,10,true),1);
    }
}
TEST(ClassicExpanded, All69FieldsSerializeAndCatalogDoesNotRefreshMeasurements) {
    ClassicBoilerMonitor m;
    for(auto type:{0x18,0x19,0x16,0x33,0x34}) m.receive(data(type,std::vector<uint8_t>(27,0)),100);
    for(size_t i=0;i<boilerFieldSpecs.size();++i) EXPECT_TRUE(m.sample(static_cast<BoilerField>(i)).observed)<<i;
    m.receive(data(0x777,{1,2},3),30100); // catalog only; old report remains stale
    std::ostringstream ss; m.writeJSON(ss,30101);
    auto j=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(ss.str().c_str()),cJSON_Delete);
    ASSERT_TRUE(j); auto fields=cJSON_GetObjectItem(j.get(),"fields");
    EXPECT_EQ(cJSON_GetArraySize(fields),69);
    auto inventory=cJSON_GetObjectItem(j.get(),"telegram_inventory");
    EXPECT_EQ(cJSON_GetArraySize(cJSON_GetObjectItem(inventory,"types")),6);
    auto reception=cJSON_GetObjectItem(j.get(),"reception");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(reception,"report_count")),5);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(reception,"fresh_report")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(reception,"control_approved")));
    EXPECT_LT(ss.str().size(),18000u);
}
TEST(ClassicExpanded, CatalogIsBoundedAndFiltersForeignAndReadTraffic) {
    ClassicBoilerMonitor m;
    for(uint16_t i=0;i<26;++i) m.receive(data(0x500+i,{1}),100);
    m.receive(data(0x500,{1,2},4),200); // existing slot still updates after overflow
    m.receive(data(0x500,{1},0,0x19),300);
    m.receive(data(0x500,{}),300);
    m.receive(EmsTelegram(EmsTelegram::READ,8,0x0B,0,0x500,{1}),300);
    m.receive(EmsTelegram(EmsTelegram::READ_WITH_DATA,8,0x0B,0,0x500,{1}),300);
    std::ostringstream ss; m.writeJSON(ss,201);
    auto j=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>(cJSON_Parse(ss.str().c_str()),cJSON_Delete);
    ASSERT_TRUE(j);auto inv=cJSON_GetObjectItem(j.get(),"telegram_inventory");
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(inv,"untracked_frames")),2);
    auto types=cJSON_GetObjectItem(inv,"types"); EXPECT_EQ(cJSON_GetArraySize(types),24);
    auto first=cJSON_GetArrayItem(types,0);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(first,"frames")),2);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(first,"last_offset")),4);
    EXPECT_STREQ(cJSON_GetStringValue(cJSON_GetObjectItem(first,"decoder")),"unmapped");
    EXPECT_STREQ(m.capabilities().name(),"unknown");
}

}

TEST(EmsEncoding, VectorPayloadLengthNeverWrapsAtOneByteBoundary) {
    EmsTelegram telegram(EmsTelegram::WRITE, 0x0B, 8, 0, 0x1A, std::vector<uint8_t>(256, 42));
    EXPECT_EQ(telegram.dataSize(), 256u);
    EXPECT_TRUE(telegram.encodeToRawDataWithCRC().empty());
}
TEST(EmsEncoding, RejectsFramesLargerThanTheReceiveProtocolLimit) {
    for (const auto type : {0x1A, 0x2E0}) {
        const size_t maximum = type == 0x1A ? 27 : 25;
        EmsTelegram valid(EmsTelegram::WRITE, 0x0B, 8, 0, type, std::vector<uint8_t>(maximum, 42));
        const auto bytes = valid.encodeToRawDataWithCRC();
        ASSERT_EQ(bytes.size(), 32u);
        EXPECT_NO_THROW(EmsTelegram::fromRawData(bytes.data(), bytes.size()));
        EmsTelegram oversized(EmsTelegram::WRITE, 0x0B, 8, 0, type, std::vector<uint8_t>(maximum + 1, 42));
        EXPECT_TRUE(oversized.encodeToRawDataWithCRC().empty());
    }
}
TEST(EmsEncoding, ReadRequestCannotSilentlyDiscardAdditionalPayload) {
    EmsTelegram telegram(EmsTelegram::READ, 0x0B, 8, 0, 0x18, {27, 42});
    EXPECT_TRUE(telegram.encodeToRawDataWithCRC().empty());
}
