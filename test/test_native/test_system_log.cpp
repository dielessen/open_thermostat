#include "diagnostics/SystemLog.h"
#include "diagnostics/LogSettings.h"
#include "diagnostics/NativeLogCapture.h"
#include "diagnostics/EmsLogCapture.h"
#include "control/HttpAccessPolicy.h"
#include <gtest/gtest.h>
#include <thread>
using namespace heating::diagnostics;
namespace {
Settings remote(){Settings s;s.enabled=true;s.syslogEms=true;std::strcpy(s.server.data(),"127.0.0.1");return s;}
TEST(SystemLog, DefaultsAreLocalInfoAndNoExternalDestination){SystemLog log;auto s=log.settings();EXPECT_FALSE(s.enabled);EXPECT_TRUE(s.syslogEsp);EXPECT_FALSE(s.syslogEms);EXPECT_EQ(s.webLevel,3);EXPECT_EQ(s.port,514);EXPECT_EQ(s.server[0],0);EXPECT_LT(sizeof(log),11000u);}
TEST(SystemLog, LazyAcceptanceMatchesActualAppendAcrossIndependentDestinations) {
    for(uint8_t web=0;web<=5;++web)for(uint8_t remoteLevel=0;remoteLevel<=5;++remoteLevel)
    for(bool enabled:{false,true})for(bool esp:{false,true})for(bool ems:{false,true}) {
        SystemLog log;auto settings=remote();settings.webLevel=web;settings.syslogLevel=remoteLevel;
        settings.enabled=enabled;settings.syslogEsp=esp;settings.syslogEms=ems;log.configure(settings);
        EXPECT_EQ(log.syslogEnabled(),enabled);
        for(uint8_t level=0;level<=6;++level) {
            bool any=false;
            for(const char* feature:{"App","EMS","EmsVerbose"}) {
                const auto before=log.stats().latest;
                const bool wanted=log.wants(level,feature);any=any||wanted;
                log.append(level,feature,"ready",1);
                EXPECT_EQ(wanted,log.stats().latest!=before);
            }
            EXPECT_EQ(log.wantsLevel(level),any);
        }
    }
}
TEST(SystemLog, LazyAcceptanceTracksSettingsChangesWithoutMutatingHistory) {
    SystemLog log;EXPECT_TRUE(log.wants(3,"App"));EXPECT_FALSE(log.wants(4,"EMS"));
    auto settings=remote();settings.webLevel=0;settings.syslogEsp=false;settings.syslogLevel=5;
    log.configure(settings);EXPECT_FALSE(log.wants(3,"App"));EXPECT_TRUE(log.wants(5,"EMS"));
    EXPECT_EQ(log.stats().latest,0u);settings.enabled=false;log.configure(settings);
    EXPECT_FALSE(log.wantsLevel(1));EXPECT_EQ(log.stats().latest,0u);
}
TEST(SystemLog, FixedRingRetainsNewestAndCountsOverwrites){SystemLog log;for(int i=0;i<100;++i)log.append(3,"App","ready",i);auto s=log.stats();EXPECT_EQ(s.retained,32u);EXPECT_EQ(s.overwritten,68u);Record r;ASSERT_TRUE(log.next(0,r));EXPECT_EQ(r.sequence,69u);ASSERT_TRUE(log.next(99,r));EXPECT_EQ(r.sequence,100u);EXPECT_FALSE(log.next(100,r));}
TEST(SystemLog, LevelsAreIndependentAndOffNeverProducesAnEvent){SystemLog log;auto s=remote();s.webLevel=1;s.syslogLevel=4;log.configure(s);log.append(0,"App","off",0);log.append(4,"App","debug",1);EXPECT_EQ(log.stats().retained,0u);Record r;Settings target;ASSERT_TRUE(log.pop(r,target));EXPECT_EQ(r.level,4);log.append(1,"App","error",2);EXPECT_EQ(log.stats().retained,1u);log.append(5,"App","trace",3);EXPECT_EQ(log.stats().latest,2u);}
TEST(SystemLog, BacklogIsBoundedAndOfflineDoesNotReplay){SystemLog log;log.configure(remote());for(int i=0;i<50;++i)log.append(3,"App","message",i);EXPECT_EQ(log.stats().pending,8u);EXPECT_EQ(log.stats().syslogDropped,42u);log.offline();EXPECT_EQ(log.stats().pending,0u);EXPECT_EQ(log.stats().syslogDropped,50u);log.append(3,"App","still offline",0);EXPECT_EQ(log.stats().syslogDropped,51u);Record r;Settings s;EXPECT_FALSE(log.pop(r,s));}
TEST(SystemLog, ChangingDestinationDropsOldPendingPackets){SystemLog log;auto s=remote();log.configure(s);log.append(1,"App","old",0);s.server[8]='2';log.configure(s);EXPECT_EQ(log.stats().syslogDropped,1u);EXPECT_EQ(log.stats().pending,0u);}
TEST(SystemLog, ClearingLocalLogDoesNotEraseRemoteOrReuseCursor){SystemLog log;log.configure(remote());log.append(3,"App","first",0);log.clear();EXPECT_EQ(log.stats().retained,0u);EXPECT_EQ(log.stats().pending,1u);log.append(3,"App","second",1);Record r;ASSERT_TRUE(log.next(1,r));EXPECT_EQ(r.sequence,2u);}
TEST(SystemLog, CredentialAndPayloadMessagesAreSuppressedForBothSinks){for(const auto* secret:{"Password: hunter2","AUTHORIZATION Bearer hidden","Cookie: hidden","csrf=hidden","myToken hidden","SECRET hidden","SSID private","userName admin","payload hidden","{\"pass\":\"hidden\"}","https://u:p@host"}){SystemLog log;log.configure(remote());log.append(1,"App",secret,0);Record local,remoteRecord;Settings target;ASSERT_TRUE(log.next(0,local));ASSERT_TRUE(log.pop(remoteRecord,target));EXPECT_STREQ(local.text.data(),"[sensitive log content omitted]");EXPECT_STREQ(local.text.data(),remoteRecord.text.data());EXPECT_EQ(log.stats().redacted,1u);}}
TEST(SystemLog, TruncatedPrintfInputIsSuppressedAndControlCharactersAreSingleLine){SystemLog log;log.append(3,"App","partial",0,true);Record r;ASSERT_TRUE(log.next(0,r));EXPECT_STREQ(r.text.data(),"[sensitive log content omitted]");EXPECT_EQ(log.stats().truncated,1u);log.append(3,"App\nspoof","hello\r\nworld",1);ASSERT_TRUE(log.next(1,r));EXPECT_STREQ(r.text.data(),"hello  world");EXPECT_STREQ(r.feature.data(),"App spoof");}
TEST(SystemLog, FieldSizesAndSendFailureCountersAreBounded){SystemLog log;log.append(3,std::string(80,'f'),std::string(1000,'x'),0);Record r;ASSERT_TRUE(log.next(0,r));EXPECT_EQ(std::strlen(r.feature.data()),16u);EXPECT_EQ(std::strlen(r.text.data()),192u);EXPECT_EQ(log.stats().truncated,1u);log.sent(true);log.sent(false);EXPECT_EQ(log.stats().sent,1u);EXPECT_EQ(log.stats().syslogDropped,1u);}
TEST(SystemLog, SyslogHasActualRfc5424HeaderSeverityAndSingleMessage){Record r;r.sequence=7;r.uptimeMs=12000;std::strcpy(r.feature.data(),"EMS");std::strcpy(r.text.data(),"ready");for(const auto& item:std::array<std::pair<int,int>,5>{{{1,131},{2,132},{3,134},{4,135},{5,135}}}){r.level=item.first;const auto frame=rfc5424(r,"heatingtest");EXPECT_EQ(frame,"<"+std::to_string(item.second)+">1 - heatingtest openthermostat - - - uptime_ms=12000 seq=7 source=esp [EMS] ready");EXPECT_LT(frame.size(),512u);}}
TEST(SystemLog, SyslogHostnameCannotInjectHeaders){Record r;r.level=3;auto frame=rfc5424(r,"host\r\n spoof");EXPECT_EQ(frame.find('\r'),std::string::npos);EXPECT_EQ(frame.find('\n'),std::string::npos);EXPECT_NE(frame.find("host___spoof"),std::string::npos);}
TEST(SystemLog, ConcurrentReceptionHasUniqueMonotonicRetainedEvents){SystemLog log;std::thread a([&]{for(int i=0;i<10000;++i)log.append(3,"A","message",i);});std::thread b([&]{for(int i=0;i<10000;++i)log.append(3,"B","message",i);});a.join();b.join();Record r;uint64_t cursor=0;size_t count=0;while(log.next(cursor,r)){EXPECT_GT(r.sequence,cursor);cursor=r.sequence;++count;}EXPECT_LE(count,32u);EXPECT_EQ(log.stats().latest+log.stats().contention,20000u);}
TEST(LogSettings, CanonicalRoundtripIncludesIndependentLevelsAndOptionalMark){auto s=remote();s.webLevel=5;s.syslogLevel=2;s.port=5514;s.markSeconds=600;const auto parsed=parseSettings(settingsJson(s));ASSERT_TRUE(parsed);EXPECT_EQ(settingsJson(*parsed),settingsJson(s));}
TEST(LogSettings, InvalidAddressLevelsPortAndMarksAreRejected){for(const char* address:{"host.local","0.0.0.0","224.0.0.1","255.255.255.255","1.2.3","1.2.3.256","1.2.3.4\n","1.2.3.04x","010.0.0.1"}){auto s=remote();std::strncpy(s.server.data(),address,15);EXPECT_FALSE(valid(s));}auto s=remote();s.port=0;EXPECT_FALSE(valid(s));s=remote();s.webLevel=6;EXPECT_FALSE(valid(s));s=remote();s.markSeconds=86401;EXPECT_FALSE(valid(s));}
TEST(LogSettings, StrictSchemaCannotEnableByTruthyDuplicateExtraOrPartialInput){auto s=remote();const auto json=settingsJson(s);for(const auto& bad:{"{}", "null","[]","{\"syslog_enabled\":true}","{\"syslog_enabled\":true,\"syslog_enabled\":false}"})EXPECT_FALSE(parseSettings(bad));auto bad=json;bad.replace(bad.find("true"),4,"1");EXPECT_FALSE(parseSettings(bad));bad=json;bad.insert(1,"\"other\":0,");EXPECT_FALSE(parseSettings(bad));bad=json;bad.replace(bad.find("514"),3,"514.5");EXPECT_FALSE(parseSettings(bad));EXPECT_FALSE(parseSettings(json+" trailing"));}
TEST(LogSettings, ProtectedRoutesPreserveExistingMethodAndControlWriterBoundaries){using namespace heating::control;EXPECT_FALSE(allowedHttpMethod("/logs/clear","GET"));EXPECT_TRUE(allowedHttpMethod("/logs/clear","POST"));EXPECT_FALSE(allowedHttpMethod("/status/logs","POST"));EXPECT_TRUE(allowedHttpMethod("/config/logging","POST"));EXPECT_FALSE(legacyControlWrite("/config/logging","POST"));EXPECT_TRUE(boilerTestMutationBlocked("/logs/clear",true));EXPECT_TRUE(boilerTestMutationBlocked("/config/logging",true));}
void nativeMessage(SystemLog& log,const char* format,...){va_list args;va_start(args,format);captureNative(log,"Arduino",7,format,args);va_end(args);}
TEST(SystemLog, NativeArduinoAndIdfSeverityAndFormattingAreCaptured){
    SystemLog log;nativeMessage(log,"[ 10][E][ssl_client.cpp:273] TLS failed: %d",-12288);
    Record r;ASSERT_TRUE(log.next(0,r));EXPECT_EQ(r.level,1);EXPECT_NE(std::string(r.text.data()).find("-12288"),std::string::npos);
    EXPECT_EQ(nativeLevel("E (123) wifi: error"),1);EXPECT_EQ(nativeLevel("W (123) wifi: warning"),2);
    EXPECT_EQ(nativeLevel("[ 10][D][file.cpp] debug [E] within text"),4);EXPECT_EQ(nativeLevel("[ 10][V][file.cpp] trace"),5);
}
TEST(SystemLog, NativeCredentialOrLongPayloadNeverEntersVisibleRing){
    SystemLog log;nativeMessage(log,"[E] Cookie: %s","test-secret");Record r;
    ASSERT_TRUE(log.next(0,r));EXPECT_STREQ(r.text.data(),"[sensitive log content omitted]");
    nativeMessage(log,"%s",std::string(500,'x').c_str());ASSERT_TRUE(log.next(1,r));
    EXPECT_STREQ(r.text.data(),"[sensitive log content omitted]");EXPECT_EQ(log.stats().truncated,1u);
}

TEST(SystemLog, TerminalFormattingCannotHideSensitiveLabelsFromEitherSink) {
    for (const auto* text : {"pass\x1b[31mword=private-value", "To\x1b[0mken private-value", "https:\x1b[0m//user:private-value@host"}) {
        SystemLog log; log.configure(remote()); log.append(3, "App", text, 1);
        Record local, packet; Settings destination;
        ASSERT_TRUE(log.next(0, local)); ASSERT_TRUE(log.pop(packet, destination));
        EXPECT_STREQ(local.text.data(), "[sensitive log content omitted]");
        EXPECT_STREQ(packet.text.data(), local.text.data());
        EXPECT_EQ(log.stats().redacted, 1u);
    }
    SystemLog log; log.append(3, "pass\x1b[0mword", "private-value", 1);
    Record local; ASSERT_TRUE(log.next(0, local));
    EXPECT_STREQ(local.feature.data(), "Log");
    EXPECT_STREQ(local.text.data(), "[sensitive log content omitted]");
}
TEST(SystemLog, RedactionScansNormalizedLabelBeyondVisibleRecordBoundary) {
    SystemLog log;
    log.append(3, "App", "private-value" + std::string(220, 'x') + "pass\x1b[0mword", 1);
    Record local; ASSERT_TRUE(log.next(0, local));
    EXPECT_STREQ(local.text.data(), "[sensitive log content omitted]");
}
TEST(SystemLog, HarmlessTerminalFormattingRemainsReadableWithoutRedaction) {
    SystemLog log; log.append(3, "\x1b[32mApp\x1b[0m", "\x1b[32mready\x1b[0m", 1);
    Record local; ASSERT_TRUE(log.next(0, local));
    EXPECT_STREQ(local.feature.data(), "App"); EXPECT_STREQ(local.text.data(), "ready");
    EXPECT_EQ(log.stats().redacted, 0u);
}

}

TEST(SystemLog, RemoteSourceChoicesAreIndependentOfWebHistory) {
    for(const bool esp : {false,true})for(const bool ems : {false,true}) {
        SystemLog log;auto settings=remote();settings.syslogEsp=esp;settings.syslogEms=ems;
        log.configure(settings);log.append(3,"App","ready",1);log.append(3,"EmsControl","received",2);
        EXPECT_EQ(log.stats().retained,2u);EXPECT_EQ(log.stats().pending,size_t(esp)+size_t(ems));
        Record record;Settings destination;
        if(esp){ASSERT_TRUE(log.pop(record,destination));EXPECT_EQ(record.source,Source::esp);}
        if(ems){ASSERT_TRUE(log.pop(record,destination));EXPECT_EQ(record.source,Source::ems);}
        EXPECT_FALSE(log.pop(record,destination));
    }
}
TEST(SystemLog, EmsSourceIsPreservedThroughRedactionAndSyslogHeader) {
    SystemLog log;log.configure(remote());log.append(2,"EmsVerbose","secret hidden",5);
    Record record;ASSERT_TRUE(log.next(0,record));EXPECT_EQ(record.source,Source::ems);
    EXPECT_STREQ(record.feature.data(),"Log");EXPECT_NE(rfc5424(record,"test").find("source=ems"),std::string::npos);
    EXPECT_EQ(sourceForFeature("Arduino"),Source::esp);EXPECT_EQ(sourceForFeature("EMS"),Source::ems);
}
TEST(SystemLog, DeferredRxRecordsBoundedOriginalFrameAndReceptionTime) {
    SystemLog log;uint8_t frame[33]{};for(unsigned i=0;i<33;++i)frame[i]=uint8_t(i);
    captureEmsRx(log,frame,33,8,16,0x18,0,1234);
    Record record;ASSERT_TRUE(log.next(0,record));EXPECT_EQ(record.source,Source::ems);EXPECT_EQ(record.uptimeMs,1234u);
    EXPECT_NE(std::string(record.text.data()).find("RX Boiler(08) W Thermostat(10) UBAMonitorFast(0018) off=0 len=33 frame=00 01"),std::string::npos);
    EXPECT_NE(std::string(record.text.data()).find("1F 20"),std::string::npos);
    EXPECT_EQ(log.stats().truncated,0u);EXPECT_EQ(log.stats().redacted,0u);
    captureEmsRx(log,nullptr,7,0,0,0,0,0);captureEmsRx(log,frame,34,0,0,0,0,0);captureEmsRx(log,frame,4,0,0,0,0,0);
    EXPECT_EQ(log.stats().latest,1u);
}
TEST(SystemLog, EmsAddressRolesCoverTheUsualBusRanges) {
    using heating::ems::addressRole;
    EXPECT_STREQ(addressRole(0x00), "All"); EXPECT_STREQ(addressRole(0x08), "Boiler"); EXPECT_STREQ(addressRole(0x88), "Boiler");
    EXPECT_STREQ(addressRole(0x0B), "Service");
    for (uint8_t a : {0x10, 0x15, 0x17, 0x18, 0x1F}) EXPECT_STREQ(addressRole(a), "Thermostat") << int(a);
    for (uint8_t a : {0x20, 0x21, 0x28, 0x2F}) EXPECT_STREQ(addressRole(a), "Mixer") << int(a);
    EXPECT_STREQ(addressRole(0x48), "Gateway"); EXPECT_STREQ(addressRole(0xC8), "Gateway");
    for (uint8_t a : {0x09, 0x0F, 0x30, 0x47, 0x49}) EXPECT_STREQ(addressRole(a), "Device") << int(a);
}
TEST(LogSettings, LegacySixFieldSettingsLoadWithoutEnablingSyslogAndNewSourcesRoundtrip) {
    const auto legacy=R"({"syslog_enabled":false,"server":"","port":514,"syslog_level":3,"web_level":3,"mark_interval_s":0})";
    auto old=parseSettings(legacy);ASSERT_TRUE(old);EXPECT_FALSE(old->enabled);EXPECT_TRUE(old->syslogEsp);EXPECT_FALSE(old->syslogEms);
    old->syslogEsp=false;auto parsed=parseSettings(settingsJson(*old));ASSERT_TRUE(parsed);EXPECT_FALSE(parsed->syslogEsp);EXPECT_FALSE(parsed->syslogEms);
    std::string partial=legacy;partial.insert(1,"\"syslog_esp\":true,");EXPECT_FALSE(parseSettings(partial));
    auto invalid=settingsJson(*old);invalid.replace(invalid.find("\"syslog_ems\":false"),18,"\"syslog_ems\":1");EXPECT_FALSE(parseSettings(invalid));
}

TEST(LogSettings, LegacyClientSavePreservesExplicitSourceSelection) {
    const auto legacy=R"({"syslog_enabled":true,"server":"127.0.0.1","port":5514,"syslog_level":4,"web_level":2,"mark_interval_s":0})";
    for(bool esp:{false,true})for(bool ems:{false,true}) {
        Settings current;current.syslogEsp=esp;current.syslogEms=ems;
        const auto changed=parseSettings(legacy,current);ASSERT_TRUE(changed);
        EXPECT_EQ(changed->syslogEsp,esp);EXPECT_EQ(changed->syslogEms,ems);
        EXPECT_TRUE(changed->enabled);EXPECT_EQ(changed->port,5514);EXPECT_EQ(changed->webLevel,2);
        auto explicitSettings=*changed;explicitSettings.syslogEsp=!esp;explicitSettings.syslogEms=!ems;
        const auto explicitSave=parseSettings(settingsJson(explicitSettings),current);ASSERT_TRUE(explicitSave);
        EXPECT_EQ(explicitSave->syslogEsp,!esp);EXPECT_EQ(explicitSave->syslogEms,!ems);
    }
}

TEST(SystemLog, ReadRequestKeepsRawDestinationReadBitAndKnownNames) {
    SystemLog log;uint8_t frame[6]={0x0B,0x97,0x06,0,1,0};
    captureEmsRx(log,frame,6,0x0B,0x97,0x06,0,123);
    Record record;ASSERT_TRUE(log.next(0,record));
    EXPECT_NE(std::string(record.text.data()).find("Service(0B) R Thermostat(17) RCTime(0006)"),std::string::npos);
    EXPECT_EQ(log.stats().truncated,0u);
}
TEST(SystemLog, AllNamedTelegramLogsKeepTheEntireMaximumLengthFrame) {
    uint8_t frame[33]{};frame[32]=0xAB;
    for(unsigned type=0;type<=65535;++type) {
        if(std::strcmp(heating::ems::telegramName(uint16_t(type)),"Unknown")==0)continue;
        SystemLog log;captureEmsRx(log,frame,33,0x17,0x10,uint16_t(type),255,123);
        Record record;ASSERT_TRUE(log.next(0,record));
        const std::string message=record.text.data();
        EXPECT_EQ(message.substr(message.size()-2),"AB");
        EXPECT_EQ(log.stats().truncated,0u);
    }
}
