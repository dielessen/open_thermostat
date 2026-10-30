// Actual firmware storage/logger/transport, with NVS failures and clock injected.
// Transport shims call real POSIX nonblocking UDP on loopback only.
#include "diagnostics/LogRuntime.h"
#include "diagnostics/BufferedLogger.h"
#include "diagnostics/NativeLogCapture.h"
#include "Logging.h"
#include "EMS/EmsTelegram.h"
#include <esp_log.h>
#include <cassert>
#include <optional>
#include <iostream>
using namespace heating::diagnostics;
std::optional<std::string> committed,pending;
bool read_error=false,write_error=false,commit_error=false,open_error=false;
unsigned opens=0,closes=0;
int nvs_open(const char* name,int mode,nvs_handle_t* h){assert(std::string(name)=="ot_logging");if(open_error)return 2;if(mode==NVS_READONLY&&!committed)return ESP_ERR_NVS_NOT_FOUND;++opens;*h=1;return ESP_OK;}
int nvs_get_str(nvs_handle_t,const char* key,char* buffer,size_t* length){assert(std::string(key)=="settings");if(read_error)return 2;if(!committed)return ESP_ERR_NVS_NOT_FOUND;if(*length<committed->size()+1)return 2;*length=committed->size()+1;std::memcpy(buffer,committed->c_str(),*length);return ESP_OK;}
int nvs_set_str(nvs_handle_t,const char* key,const char* value){assert(std::string(key)=="settings");if(write_error)return 2;pending=value;return ESP_OK;}
int nvs_commit(nvs_handle_t){if(commit_error)return 2;committed=pending;return ESP_OK;}
void nvs_close(nvs_handle_t){++closes;}
struct MemorySink:ib::logger::LoggerSinkInterface{
    using Level=ib::logger::LoggerInterface::LogLevel;
    std::string output;Level level=Level::TRACE;
    Level getLevel()const override{return level;}
    void setLevel(Level value)override{level=value;}
    void writeLog(const char* bytes,size_t count)override{output.append(bytes,count);}
};
std::string nativeOutput;
int idfSetters=0;
int rawConsole(const char* format,va_list args){va_list copy;va_copy(copy,args);int size=std::vsnprintf(nullptr,0,format,copy);va_end(copy);std::string text(size+1,'\0');std::vsnprintf(text.data(),text.size(),format,args);nativeOutput.assign(text.data(),size);return size;}
extern "C" int __real_log_printfv(const char* format,va_list args){return rawConsole(format,args);}
vprintf_like_t sdkOutput=rawConsole;
vprintf_like_t esp_log_set_vprintf(vprintf_like_t callback){++idfSetters;auto old=sdkOutput;sdkOutput=callback;return old;}
void sdkMessage(const char* format,...){va_list args;va_start(args,format);sdkOutput(format,args);va_end(args);}
extern "C" int __wrap_log_printfv(const char*,va_list);
void arduinoMessage(const char* format,...){va_list args;va_start(args,format);__wrap_log_printfv(format,args);va_end(args);}
int main(){
    const int receiver=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);assert(receiver>=0);
    sockaddr_in local{};local.sin_family=AF_INET;local.sin_addr.s_addr=inet_addr("127.0.0.1");
    assert(bind(receiver,reinterpret_cast<sockaddr*>(&local),sizeof(local))==0);
    socklen_t size=sizeof(local);assert(getsockname(receiver,reinterpret_cast<sockaddr*>(&local),&size)==0);
    timeval timeout{0,200000};assert(setsockopt(receiver,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))==0);
    LogRuntime runtime;runtime.begin();assert(runtime.storageReady&&!runtime.log.settings().enabled);
    const auto idleClocks=clock_reads;const auto idleSends=send_calls;
    for(unsigned i=0;i<100000;++i)runtime.poll(i%2,"heatingtest");
    assert(clock_reads==idleClocks&&"Disabled syslog must not query the clock on each main-loop pass");
    assert(send_calls==idleSends);
    // This transport scenario exercises EMS explicitly; the product default is ESP-only.
    Settings s;s.enabled=true;s.syslogEms=true;s.port=ntohs(local.sin_port);std::strcpy(s.server.data(),"127.0.0.1");
    assert(runtime.save(s));assert(loadSettings()&&settingsJson(*loadSettings())==settingsJson(s));
    runtime.poll(true,"heatingtest"); // Explicit current network availability, no packet yet.
    auto sink=std::make_shared<MemorySink>();BufferedLogger logger({sink},runtime.log,uptimeMs);
    const auto feature=logger.addFeature("EMS");
    logger.printf(ib::logger::LoggerInterface::LogLevel::WARN,feature,"Temperature %d C",42);
    assert(send_calls==0); // Capture never performs network IO.
    fake_microseconds=100000;runtime.poll(true,"heatingtest");
    char bytes[1024]{};const auto length=recv(receiver,bytes,sizeof(bytes),0);assert(length>0);
    const std::string frame(bytes,length);
    assert(frame=="<132>1 - heatingtest openthermostat - - - uptime_ms=0 seq=1 source=ems [EMS] Temperature 42 C");
    assert(runtime.log.stats().sent==1&&runtime.log.stats().pending==0);
    assert(sink->output.find("Temperature 42 C")!=std::string::npos);
    logger.printf(ib::logger::LoggerInterface::LogLevel::ERROR,feature,"Password: fake-test-secret");
    Record record;assert(runtime.log.next(1,record));assert(std::string(record.text.data()).find("fake-test-secret")==std::string::npos);
    fake_microseconds+=100000;runtime.poll(true,"heatingtest");assert(recv(receiver,bytes,sizeof(bytes),0)>0);
    runtime.log.append(3,"App","offline",uptimeMs());runtime.poll(false,"heatingtest");
    assert(runtime.log.stats().pending==0);const auto sent=send_calls;
    const auto offlineClocks=clock_reads,offlineDrops=runtime.log.stats().syslogDropped;
    for(unsigned i=0;i<100000;++i)runtime.poll(false,"heatingtest");
    assert(clock_reads==offlineClocks&&runtime.log.stats().syslogDropped==offlineDrops);
    fake_microseconds+=100000;runtime.poll(true,"heatingtest");assert(send_calls==sent);
    runtime.log.append(3,"App","once",uptimeMs());fail_send=true;fake_microseconds+=100000;runtime.poll(true,"heatingtest");
    assert(runtime.log.stats().syslogDropped==2);fail_send=false;fake_microseconds+=100000;runtime.poll(true,"heatingtest");assert(send_calls==sent+1);
    // Pacing: at most one datagram per 100 ms however often the main loop polls; never a burst.
    {
        const auto paced=send_calls;
        for(int i=0;i<3;++i){runtime.log.append(3,"App","paced",uptimeMs());}
        for(unsigned i=0;i<1000;++i){runtime.poll(true,"heatingtest");}
        assert(send_calls==paced);
        fake_microseconds+=99000;runtime.poll(true,"heatingtest");assert(send_calls==paced);
        for(unsigned n=1;n<=3;++n){
            fake_microseconds+=100000;
            for(unsigned i=0;i<100;++i){runtime.poll(true,"heatingtest");}
            assert(send_calls==paced+n);assert(recv(receiver,bytes,sizeof(bytes),0)>0);
        }
        assert(runtime.log.stats().pending==0);
    }
    auto changed=s;changed.webLevel=5;
    write_error=true;assert(!runtime.save(changed));write_error=false;assert(runtime.log.settings().webLevel==3);
    commit_error=true;assert(!runtime.save(changed));commit_error=false;assert(runtime.log.settings().webLevel==3);
    read_error=true;assert(!runtime.save(changed));read_error=false;assert(runtime.log.settings().webLevel==3);
    assert(runtime.save(s));open_error=true;assert(!runtime.save(changed));open_error=false;
    assert(opens==closes);
    committed="invalid";LogRuntime invalid;invalid.begin();assert(!invalid.storageReady&&!invalid.log.settings().enabled);
    committed=settingsJson(s);assert(runtime.save(s));s.markSeconds=1;assert(runtime.save(s));
    fake_microseconds+=1000000;runtime.poll(true,"heatingtest");const auto mark_length=recv(receiver,bytes,sizeof(bytes),0);assert(mark_length>0);
    assert(std::string(bytes,mark_length).find("[Syslog] MARK")!=std::string::npos);
    const auto beforeLong=runtime.log.stats().latest;
    const auto longApp=std::string(700,'q');
    logger.printf(ib::logger::LoggerInterface::LogLevel::INFO,feature,"%s",longApp.c_str());
    assert(sink->output.find(longApp)!=std::string::npos);
    assert(runtime.log.next(beforeLong,record)&&std::string(record.text.data())=="[sensitive log content omitted]");
    runtime.poll(false,"heatingtest");
    auto& nativeLog=heating::diagnostics::runtime.log;nativeLog.configure(Settings{});
    installNativeLogCapture();installNativeLogCapture();assert(idfSetters==1);
    arduinoMessage("[ 10][E][ssl_client.cpp] TLS failed: %d",-12288);
    assert(nativeOutput=="[ 10][E][ssl_client.cpp] TLS failed: -12288");
    assert(nativeLog.next(0,record)&&record.level==1&&std::string(record.feature.data())=="Arduino");
    sdkMessage("W (10) network: %s","link unavailable");
    assert(nativeOutput=="W (10) network: link unavailable");
    assert(nativeLog.next(record.sequence,record)&&record.level==2&&std::string(record.feature.data())=="ESP-IDF");
    arduinoMessage("[E] Password: %s","test-secret");
    assert(nativeOutput.find("test-secret")!=std::string::npos);
    assert(nativeLog.next(record.sequence,record)&&std::string(record.text.data())=="[sensitive log content omitted]");
    arduinoMessage("[E] %s",std::string(700,'x').c_str());
    assert(nativeOutput.size()==704); // Original UART path is not truncated by capture.
    assert(nativeLog.next(record.sequence,record)&&std::string(record.text.data())=="[sensitive log content omitted]");
    // Persist source choices, then exercise actual nonblocking UDP on loopback.
    s.markSeconds=0;s.syslogEsp=false;s.syslogEms=true;assert(runtime.save(s));
    LogRuntime restored;restored.begin();assert(!restored.log.settings().syslogEsp&&restored.log.settings().syslogEms);
    runtime.poll(true,"heatingtest");
    runtime.log.append(3,"App","must stay local",uptimeMs());
    runtime.log.append(3,"EMS","source-only EMS",uptimeMs());
    assert(runtime.log.stats().pending==1);
    fake_microseconds+=100000;runtime.poll(true,"heatingtest");
    auto sourceLength=recv(receiver,bytes,sizeof(bytes),0);assert(sourceLength>0);
    assert(std::string(bytes,sourceLength).find("source=ems [EMS] source-only EMS")!=std::string::npos);
    // An old open six-field page may update levels/address, but must not reset source choices.
    const auto legacy=R"({"syslog_enabled":true,"server":"127.0.0.1","port":514,"syslog_level":3,"web_level":3,"mark_interval_s":0})";
    auto migrated=parseSettings(legacy,runtime.log.settings());assert(migrated&&!migrated->syslogEsp&&migrated->syslogEms);
    migrated->port=s.port;assert(runtime.save(*migrated));
    assert(!loadSettings()->syslogEsp&&loadSettings()->syslogEms);
    s.syslogEsp=true;assert(runtime.save(s));runtime.poll(true,"heatingtest");
    runtime.log.append(3,"App","ESP together",uptimeMs());runtime.log.append(3,"EMS","EMS together",uptimeMs());
    for(const auto source:{"source=esp","source=ems"}){
        fake_microseconds+=100000;runtime.poll(true,"heatingtest");sourceLength=recv(receiver,bytes,sizeof(bytes),0);assert(sourceLength>0);
        assert(std::string(bytes,sourceLength).find(source)!=std::string::npos);
    }
    // Disabling an online destination drops its pending queue once. Idle polls
    // do no clock/transport work; local web records still work independently.
    runtime.log.append(3,"EMS","queued before disable",uptimeMs());
    const auto beforeDisable=runtime.log.stats();assert(beforeDisable.pending==1);
    auto disabled=s;disabled.enabled=false;assert(runtime.save(disabled));
    assert(!runtime.log.syslogEnabled()&&runtime.log.stats().pending==0);
    assert(runtime.log.stats().syslogDropped==beforeDisable.syslogDropped+1);
    const auto disabledClocks=clock_reads;const auto disabledSends=send_calls;
    for(unsigned i=0;i<100000;++i)runtime.poll(true,"heatingtest");
    assert(clock_reads==disabledClocks&&send_calls==disabledSends);
    const auto localSequence=runtime.log.stats().latest;runtime.log.append(3,"EMS","web only",0);
    assert(runtime.log.next(localSequence,record)&&std::string(record.text.data())=="web only"&&runtime.log.stats().pending==0);
    assert(runtime.save(s));assert(runtime.log.syslogEnabled());runtime.poll(true,"heatingtest");
    runtime.log.append(3,"EMS","after reenable",uptimeMs());fake_microseconds+=100000;runtime.poll(true,"heatingtest");
    const auto reenabledLength=recv(receiver,bytes,sizeof(bytes),0);assert(reenabledLength>0);
    assert(std::string(bytes,reenabledLength).find("[EMS] after reenable")!=std::string::npos);
    runtime.poll(false,"heatingtest");
    // Project macros skip expensive arguments only when no destination wants
    // the record. Web/syslog are independent of the serial sink's level.
    using Level=ib::logger::LoggerInterface::LogLevel;
    SystemLog filtered;auto silent=std::make_shared<MemorySink>();silent->level=Level::OFF;
    auto lazy=std::make_shared<BufferedLogger>(std::vector<std::shared_ptr<ib::logger::LoggerSinkInterface>>{silent},filtered,uptimeMs);
    auto app=lazy->addFeature("App"),ems=lazy->addFeature("EMS");
    Settings filters;filters.webLevel=0;filtered.configure(filters);
    unsigned expensive=0,loggerCalls=0,featureCalls=0;
    auto chooseLogger=[&]{++loggerCalls;return lazy;};auto chooseFeature=[&]{++featureCalls;return app;};
    DBGLOGFD(chooseLogger(),chooseFeature(),"cost %u",++expensive);
    assert(loggerCalls==1&&featureCalls==1&&expensive==0&&filtered.stats().latest==0);
    filters.webLevel=4;filtered.configure(filters);
    DBGLOGFD(chooseLogger(),chooseFeature(),"cost %u",++expensive);
    assert(loggerCalls==2&&featureCalls==2&&expensive==1&&silent->output.empty());
    assert(filtered.next(0,record)&&record.level==4&&std::string(record.text.data())=="cost 1");
    lazy->enableFeature(app,false);DBGLOGFD(lazy,app,"disabled %u",++expensive);assert(expensive==1);
    lazy->enableFeature(app,true);filters.webLevel=0;filters.enabled=true;
    filters.syslogLevel=4;filters.syslogEsp=false;filters.syslogEms=true;filtered.configure(filters);
    DBGLOGFD(lazy,app,"ESP ignored %u",++expensive);assert(expensive==1);
    DBGLOGFD(lazy,ems,"EMS requested %u",++expensive);assert(expensive==2&&filtered.stats().pending==1);
    filters.enabled=false;filtered.configure(filters);silent->level=Level::DEBUG;
    DBGLOGFD(lazy,app,"serial %u",++expensive);assert(expensive==3);
    assert(silent->output.find("serial 3")!=std::string::npos);
    DBGLOGFI(lazy,app,"message only");DBGLOGI(lazy,"unfeatured message only");
    assert(silent->output.find("message only")!=std::string::npos);
    std::shared_ptr<ib::logger::LoggerInterface> missing;
    DBGLOGFD(missing,chooseFeature(),"never %u",++expensive);assert(expensive==3&&featureCalls==2);
    // The real telegram debug path honors BufferedLogger's combined acceptance.
    uint8_t raw[]={8,0,0x18,0,1,0};raw[5]=heating::ems::EmsTelegram::calculateCRC(raw,5);auto telegram=heating::ems::EmsTelegram::fromRawData(raw,sizeof(raw));
    silent->output.clear();silent->level=Level::OFF;telegram.logDebug(*lazy,ems);assert(silent->output.empty());
    filters.webLevel=4;filtered.configure(filters);const auto cursor=filtered.stats().latest;
    telegram.logDebug(*lazy,ems);assert(filtered.next(cursor,record)&&record.level==4);
    assert(std::string(record.text.data()).find("data: 01")!=std::string::npos);
    close(receiver);std::cout<<"PASS actual logger, NVS failure/readback, native SDK hooks, real RFC5424 UDP, lazy arguments and independent log destinations\n";
}
