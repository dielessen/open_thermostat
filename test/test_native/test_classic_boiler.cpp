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
}
