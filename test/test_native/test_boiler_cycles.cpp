#include "EMS/EmsEntityCatalog.h"
#include "control/BoilerFieldTelemetry.h"
#include "control/BurnerCycleMonitor.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <memory>
#include <sstream>
#include <string>

namespace {
using namespace heating::ems;
using heating::control::BurnerCycleMonitor;
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
// A frame as the E32 logs it ("frame=..."): header, data, CRC, break byte.
EmsTelegram logged(const std::string& hex) {
    std::vector<uint8_t> bytes;std::istringstream in(hex);std::string b;
    while(in>>b)bytes.push_back(static_cast<uint8_t>(std::stoul(b,nullptr,16)));
    bytes.pop_back(); // break
    return EmsTelegram::fromRawData(bytes.data(),bytes.size());
}
// Live EcomLine HRC 22H behind the EasyControl adapter (out/e32-hang-monitor).
const char* fastIdle="08 00 18 00 00 02 6C 00 00 00 00 00 00 80 00 80 00 02 6C 00 00 FF 30 48 00 00 FF 00 00 0B 00";
const char* fastDhwBurn="08 00 18 00 00 02 E4 00 25 0A 10 00 00 80 00 80 00 02 B2 00 00 FF 3D 48 00 00 FF 00 00 11 00";
const char* slow="08 00 19 00 80 00 80 00 80 00 00 00 04 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 3A 00";
const char* ww="08 00 34 00 3C 02 B2 80 00 20 00 00 01 19 00 00 00 00 00 00 00 3B 00";
constexpr uint64_t minute=60000;

TEST(BoilerCounters, LiveClassicFramesCarryCountersAndCodesButTheyReadZero){
    ClassicBoilerMonitor m;EmsEntityObserver o;
    for(auto frame:{fastIdle,slow,ww}){const auto t=logged(frame);m.receive(t,100);o.observe(t,100);}
    EXPECT_EQ(*m.value(BoilerField::flow,100),6200);
    EXPECT_EQ(*m.value(BoilerField::displayCode,100),('0'<<8)|'H');
    EXPECT_EQ(*m.value(BoilerField::serviceNumber,100),0);
    EXPECT_EQ(*m.value(BoilerField::dhwTemp,100),6900);
    // Starts and runtimes are on the wire (0x19 offsets 10-24, 0x34 offsets 10-15),
    // stationary at 0 on this chain, so they stay unreliable Classic fields.
    for(auto f:{BoilerField::burnerStarts,BoilerField::burnerMinutes,BoilerField::heatingMinutes,
                BoilerField::heatingStarts,BoilerField::dhwMinutes,BoilerField::dhwStarts}) {
        EXPECT_FALSE(m.value(f,100).has_value());EXPECT_EQ(*m.value(f,100,true),0);
    }
    for(size_t f=0;f<entityFieldCount;++f)EXPECT_FALSE(o.field(f,100).has_value()); // no duplicate in the table
}
TEST(BoilerCounters, ErrorRecordsAndUptimeDecodeFromTheTable){
    EmsEntityObserver o;
    // 0x10 newest record: "EA", error 227, 2026-10-28 14:05, 3 min, source 0x08.
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x10,{'E','A',0x00,0xE3,0x9A,10,14,28,5,0x00,0x03,0x08}},100);
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x14,{0x01,0x86,0xA0}},100);
    EXPECT_DOUBLE_EQ(*o.value(8,"last_locking_error_code",100),('E'<<8)|'A');
    EXPECT_DOUBLE_EQ(*o.value(8,"last_locking_error_number",100),227);
    EXPECT_DOUBLE_EQ(*o.value(8,"boiler_uptime",100),100000);
    std::ostringstream out;o.writeJSON(out,100);
    EXPECT_NE(out.str().find("{\"id\":\"last_locking_error_code\",\"value\":\"EA\""),std::string::npos) << out.str();
    Json j(cJSON_Parse(out.str().c_str()),cJSON_Delete);EXPECT_TRUE(j);
    // An empty blocking record is no code; a thermostat never reports the boiler's errors.
    o.observe({EmsTelegram::WRITE,0x08,0x0b,0,0x11,{0,0,0,0}},200);
    o.observe({EmsTelegram::BROADCAST,0x17,0x00,0,0x10,{'X','X',0,1}},200);
    EXPECT_FALSE(o.value(8,"last_blocking_error_code",200).has_value());
    EXPECT_DOUBLE_EQ(*o.value(8,"last_blocking_error_number",200),0);
    EXPECT_DOUBLE_EQ(*o.value(8,"last_locking_error_code",200),('E'<<8)|'A');
    EXPECT_FALSE(o.value(0x17,"last_locking_error_code",200).has_value());
    EXPECT_TRUE(o.value(8,"boiler_uptime",100+settingTtl-1));EXPECT_FALSE(o.value(8,"boiler_uptime",100+settingTtl));
}
// Firmware and HA share the generated table: 36 catalog fields in 4 groups.
TEST(BoilerCounters, CatalogGroupsStayValidAndBoundedAtTheirLargest){
    using namespace heating::control;
    EXPECT_EQ(entityFieldCount,36u);EXPECT_EQ(boilerFieldGroupCountV2,11u);
    size_t largest=0;
    for(size_t group=boilerFieldGroupCount;group<boilerFieldGroupCountV2;++group) {
        // EmsController::getBoilerFieldGroup's shape at the largest values.
        std::ostringstream out;const uint64_t now=maximumBoilerTimestamp;
        out<<"{\"schema\":1,\"sampled_at_ms\":"<<now<<",\"profile\":\"conflicting_families\",\"fields\":[";
        const size_t begin=group*boilerFieldsPerGroup,end=std::min(begin+boilerFieldsPerGroup,catalogFieldBase+entityFieldCount);
        for(size_t i=begin;i<end;++i) {
            const auto row=entityFieldRows[i-catalogFieldBase];uint16_t type=0;
            for(const auto& spec:entityCatalog)if(std::string_view(spec.id)==entityCatalog[row].id)type=std::max(type,spec.type);
            out<<(i==begin?"":",")<<'['<<i<<','<<entityCatalog[row].maximum<<','<<now<<",0,"<<type<<']';
        }
        out<<"]}";
        Json j(cJSON_Parse(out.str().c_str()),cJSON_Delete);
        EXPECT_TRUE(validBoilerGroup(j.get(),group,true)) << group;
        largest=std::max(largest,out.str().size());
    }
    EXPECT_LE(largest,maximumBoilerGroupBytes);
}

TEST(BurnerCycles, SixHeatingStartsAnHourIsShortCycling){
    BurnerCycleMonitor c;uint64_t t=0;
    c.observe(false,false,t);
    for(int i=0;i<6;++i) {
        for(int s=0;s<4;++s)c.observe(false,false,t+=minute);   // 4 min off, a report each minute
        for(int s=0;s<6;++s)c.observe(true,false,t+=minute);    // first on report is the start
        EXPECT_EQ(c.summary(t).shortCycling,i>=5) << i;         // 6 min runs: only the count flags
    }
    const auto s=c.summary(t);
    EXPECT_EQ(s.heatingStarts,6u);EXPECT_EQ(*s.medianHeatingRunMs,6*minute);EXPECT_TRUE(s.known);
    // An hour later the window holds none of them.
    for(int i=0;i<60;++i)c.observe(false,false,t+=minute);
    EXPECT_FALSE(c.summary(t).shortCycling);EXPECT_EQ(c.summary(t).starts,0u);EXPECT_EQ(c.observedStarts(),6u);
}
TEST(BurnerCycles, ShortMedianRunFlagsButLongRunsAndDhwDrawsDoNot){
    const auto hour=[](uint64_t onMinutes,bool dhw){
        BurnerCycleMonitor c;uint64_t t=0;c.observe(false,false,t);
        for(int i=0;i<3;++i){
            for(int s=0;s<10;++s)c.observe(false,false,t+=minute);
            for(uint64_t s=0;s<onMinutes;++s)c.observe(true,dhw,t+=minute);
        }
        c.observe(false,false,t+=minute);
        return c.summary(t);
    };
    EXPECT_TRUE(hour(4,false).shortCycling);       // three runs, median 4 min < 5 min
    EXPECT_FALSE(hour(12,false).shortCycling);
    const auto dhw=hour(1,true);                   // the live pattern: ~1 min DHW burns
    EXPECT_FALSE(dhw.shortCycling);EXPECT_EQ(dhw.starts,3u);EXPECT_EQ(dhw.heatingStarts,0u);
}
TEST(BurnerCycles, GapsReorderedReportsAndARunningStartAreNeverGuessed){
    BurnerCycleMonitor c;
    c.observe(true,false,0);                       // already burning: no start
    c.observe(false,false,minute);
    EXPECT_EQ(c.summary(minute).starts,0u);
    c.observe(true,false,2*minute);
    c.observe(false,false,2*minute+10000);
    c.observe(true,false,2*minute+5000);           // older than the newest report
    c.observe(true,false,3*minute);c.observe(true,false,6*minute);   // 3 min report gap mid-run
    c.observe(false,false,6*minute+10000);
    c.observe(true,false,7*minute);c.observe(false,false,7*minute+10000);
    c.observe(true,false,8*minute);c.observe(false,false,8*minute+10000);
    const auto s=c.summary(8*minute+10000);
    EXPECT_EQ(s.heatingStarts,4u);EXPECT_EQ(*s.medianHeatingRunMs,10000u); // the gapped run is not measured
    EXPECT_EQ(s.observedMs,2*minute+10000);        // covered since the gap
    EXPECT_FALSE(c.summary(8*minute+10000+BurnerCycleMonitor::gapMs+1).known);  // no reports: unknown
    EXPECT_FALSE(c.summary(8*minute+10000+BurnerCycleMonitor::gapMs+1).shortCycling);
}
TEST(BurnerCycles, ClassicMonitorFeedUsesOnlyTheCurrentFastReport){
    ClassicBoilerMonitor m;BurnerCycleMonitor c;
    const auto feed=[&](const char* frame,uint64_t now){m.receive(logged(frame),now);c.observe(m,now);};
    feed(fastIdle,0);feed(fastDhwBurn,10000);
    m.receive(logged(slow),15000);c.observe(m,15000);   // another telegram: the 0x18 state is not re-observed
    feed(fastDhwBurn,70000);feed(fastIdle,80000);
    const auto s=c.summary(80000);
    EXPECT_EQ(s.starts,1u);EXPECT_EQ(s.heatingStarts,0u);EXPECT_FALSE(s.shortCycling);
    std::ostringstream out;c.writeJSON(out,80000);
    Json j(cJSON_Parse(out.str().c_str()),cJSON_Delete);ASSERT_TRUE(j);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetObjectItem(j.get(),"starts_last_hour")),1);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItem(j.get(),"median_heating_run_s")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItem(j.get(),"short_cycling")));
}
}
