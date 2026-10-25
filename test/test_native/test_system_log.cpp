#include "diagnostics/SystemLog.h"
#include "diagnostics/LogSettings.h"
#include "diagnostics/NativeLogCapture.h"
#include "diagnostics/EmsLogCapture.h"
#include "control/HttpAccessPolicy.h"
#include <gtest/gtest.h>
#include <thread>
using namespace heating::diagnostics;
namespace {
Settings remote(){Settings s;s.enabled=true;std::strcpy(s.server.data(),"127.0.0.1");return s;}
TEST(SystemLog, DefaultsAreLocalInfoAndNoExternalDestination){SystemLog log;auto s=log.settings();EXPECT_FALSE(s.enabled);EXPECT_EQ(s.webLevel,3);EXPECT_EQ(s.port,514);EXPECT_EQ(s.server[0],0);EXPECT_LT(sizeof(log),11000u);}
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
    EXPECT_NE(std::string(record.text.data()).find("RX src=08 dst=10 type=0018 offset=0 len=33 frame=00 01"),std::string::npos);
    EXPECT_NE(std::string(record.text.data()).find("1F 20"),std::string::npos);
    EXPECT_EQ(log.stats().truncated,0u);EXPECT_EQ(log.stats().redacted,0u);
    captureEmsRx(log,nullptr,7,0,0,0,0,0);captureEmsRx(log,frame,34,0,0,0,0,0);captureEmsRx(log,frame,6,0,0,0,0,0);
    EXPECT_EQ(log.stats().latest,1u);
}
TEST(LogSettings, LegacySixFieldSettingsLoadWithoutEnablingSyslogAndNewSourcesRoundtrip) {
    const auto legacy=R"({"syslog_enabled":false,"server":"","port":514,"syslog_level":3,"web_level":3,"mark_interval_s":0})";
    auto old=parseSettings(legacy);ASSERT_TRUE(old);EXPECT_FALSE(old->enabled);EXPECT_TRUE(old->syslogEsp);EXPECT_TRUE(old->syslogEms);
    old->syslogEsp=false;auto parsed=parseSettings(settingsJson(*old));ASSERT_TRUE(parsed);EXPECT_FALSE(parsed->syslogEsp);EXPECT_TRUE(parsed->syslogEms);
    std::string partial=legacy;partial.insert(1,"\"syslog_esp\":true,");EXPECT_FALSE(parseSettings(partial));
    auto invalid=settingsJson(*old);invalid.replace(invalid.find("\"syslog_ems\":true"),17,"\"syslog_ems\":1");EXPECT_FALSE(parseSettings(invalid));
}
