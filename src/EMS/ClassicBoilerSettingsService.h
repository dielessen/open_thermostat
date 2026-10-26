#pragma once
#include "ClassicBoilerSettingTransaction.h"
#include "ClassicSettingBusExchange.h"
#include "ManualClassicUartWrite.h"
#include "control/BoundedJson.h"
#include "control/WebAuthSession.h"
#include <array>
#include <algorithm>
#include <ostream>

namespace heating::ems {
// HTTP-independent bounded request/status contract. Transport qualification is
// a source-owned decision, never an HTTP field, selected photo or runtime flag.
class ClassicBoilerSettingsService {
public:
    struct Result { int http; const char* error; bool duplicate=false; };
    explicit ClassicBoilerSettingsService(uint64_t boot,bool transportQualified=false)
        : boot_(boot),qualified_(transportQualified),transaction_(boot,transportQualified) {}
    Result request(std::string_view body,std::string_view owner,uint64_t now,bool permitted) {
        if(!control::WebAuthSession::hexToken(owner))return {401,"authentication_required"};
        if(body.size()>384)return {400,"invalid_request"};
        const auto document=control::parseControlJson(body);const auto* json=document.get();
        constexpr const char* keys[]={"schema","boot_id","revision","entity","value",
            "exclusive_owner_confirmed","independent_stop_confirmed"};
        if(!cJSON_IsObject(json)||cJSON_GetArraySize(json)!=7)return {400,"invalid_request"};
        for(auto key:keys)if(!field(json,key))return {400,"invalid_request"};
        if(!integer(field(json,"schema"),1,1)||!integer(field(json,"revision"),1,2147483647)
            ||!integer(field(json,"value"),-1000,1000))return {400,"invalid_request"};
        if(string(field(json,"boot_id"))!=bootText())return {409,"boot_changed"};
        if(!cJSON_IsTrue(field(json,"exclusive_owner_confirmed"))
            ||!cJSON_IsTrue(field(json,"independent_stop_confirmed")))return {400,"site_confirmation_required"};
        ClassicBoilerSettingsEncoder::Setting setting{};bool found=false;
        for(const auto candidate:settings()){
            ClassicBoilerSettingsEncoder::Definition definition;
            ClassicBoilerSettingsEncoder::definition(candidate,definition);
            if(string(field(json,"entity"))==definition.entity){setting=candidate;found=true;break;}
        }
        if(!found)return {400,"unknown_setting"};
        const auto revision=static_cast<uint32_t>(field(json,"revision")->valuedouble);
        const auto value=static_cast<int>(field(json,"value")->valuedouble);
        ClassicBoilerSettingsEncoder::Definition definition;
        ClassicBoilerSettingsEncoder::definition(setting,definition);
        if(value<definition.minimum||value>definition.maximum)return {400,"value_out_of_range"};
        if(revision==transaction_.revision() && std::string_view(owner_.data())!=owner)
            return {403,"different_operator"};
        if(inIo_||(exchange_.active()&&revision!=transaction_.revision()))return {409,"settings_request_unavailable"};
        if(transportFault_)return {409,"settings_transport_fault"};
        if(!qualified_)return {409,"settings_transport_unqualified"};
        const auto result=transaction_.request({boot_,revision,revision,setting,value,true,true},now,permitted);
        if(result==ClassicBoilerSettingTransaction::Admission::rejected)return {409,"settings_request_unavailable"};
        if(result==ClassicBoilerSettingTransaction::Admission::duplicate)return {200,"",true};
        std::copy(owner.begin(),owner.end(),owner_.begin());owner_[64]=0;
        setting_=setting;value_=value;revoked_=false;sessionUntilMs_=sessionObservedMs_=0;
        return {202,""};
    }
    // Called only on the HTTP/session owner thread, under the controller lock.
    // Projects the existing session deadline; does not touch/renew the session.
    void synchronizeSessions(const control::WebAuthSession& sessions,uint64_t now){
        const auto owner=std::string_view(owner_.data());
        if(owner.empty()||revoked_)return;
        const auto remaining=sessions.remainingMs(owner,now);
        if(!remaining||now<sessionObservedMs_||remaining>UINT64_MAX-now){revokeOwner(owner);return;}
        sessionObservedMs_=now;sessionUntilMs_=now+remaining;
    }
    // Serialized by the controller owner. Gate receives the original internal
    // session token and must check current session/installation/transport rights.
    // Clock is boot-relative MICROSECONDS, including original UART acquisition.
    template<class Clock,class Gate>
    void tick(Clock clock,Gate gate){
        if(inIo_||!active())return;
        try{
            const bool permit=permission(gate,clock);const auto now=clock();
            transaction_.tick(now/1000,permit&&sessionValid(now/1000));
            const auto event=exchange_.tick(now,permit&&transaction_.active());
            if(event.result==ClassicSettingBusExchange::Result::failed)transaction_.fail("settings_exchange_failed");
        }catch(...){transportFault_=true;transaction_.fail("transport_exception");exchange_.cancel();}
    }
    template<class Clock,class Gate,class Send>
    bool poll(Clock clock,Gate gate,Send send){
        if(inIo_)return active();
        tick(clock,gate);
        if(!transaction_.active())return false;
        inIo_=true;struct Release{bool& flag;~Release(){flag=false;}}release{inIo_};
        const bool owned=transaction_.poll([&]{return clock()/1000;},[&]{return permission(gate,clock);},
            [&](const EmsRawFrame& frame){
                if(!sessionValid(clock()/1000))return false;
                if(!exchange_.begin(frame,setting_,value_,transaction_.revision(),frame.data[1]==0x88,clock()))return false;
                ManualClassicUartWrite::Result result;
                try{result=send(frame,setting_,value_,frame.data[1]==0x88);}catch(...){
                    transportFault_=true;exchange_.cancel();throw;
                }
                if(!result.detached)transportFault_=true;
                exchange_.finish(result.succeeded(),clock());
                return result.succeeded();
            });
        if(!transaction_.active())exchange_.cancel();
        return owned;
    }
    template<class Clock,class Gate,class Close>
    void receive(const uint8_t* bytes,size_t length,uint64_t acquiredAt,Clock clock,Gate gate,Close close){
        if(inIo_)return;
        // Completion-byte IO must not change the bytes used as readback proof.
        std::array<uint8_t,6> captured{};
        if(!bytes||length>captured.size()){tick(clock,gate);return;}
        std::copy_n(bytes,length,captured.begin());bytes=captured.data();
        tick(clock,gate);
        if(!transaction_.active())return;
        inIo_=true;struct Release{bool& flag;~Release(){flag=false;}}release{inIo_};
        try{
            const auto event=exchange_.receive(bytes,length,acquiredAt,clock,[&]{return permission(gate,clock);},[&]{
                ManualClassicUartWrite::Result result;
                if(!sessionValid(clock()/1000))return false;
                try{result=close();}catch(...){transportFault_=true;throw;}
                if(!result.detached)transportFault_=true;
                return result.succeeded();
            });
            const bool permit=permission(gate,clock);const auto now=clock();
            using Result=ClassicSettingBusExchange::Result;
            if(event.result==Result::failed){transaction_.fail("settings_exchange_failed");return;}
            if(event.result==Result::writeClosed||event.result==Result::rejected)
                transaction_.writeClosed(event.revision,now/1000,event.result==Result::writeClosed,permit);
            if(event.result==Result::readClosed){
                transaction_.receive(EmsTelegram::fromRawData(bytes,length),acquiredAt/1000,now/1000,permit);
                if(transaction_.active())transaction_.fail("setting_readback_unconfirmed");
            }
        }catch(...){transportFault_=true;transaction_.fail("transport_exception");}
    }
    void revokeOwner(std::string_view owner){
        if(std::string_view(owner_.data())==owner){revoked_=true;transaction_.fail("operator_revoked");if(!inIo_)exchange_.cancel();}
    }
    void failTransport(){if(!active())return;transportFault_=true;transaction_.fail("settings_transport_fault");exchange_.cancel();}
    bool transportFault()const{return transportFault_;}
    void writeJSON(std::ostream& out,uint64_t now,bool permitted,std::string_view requester={})const {
        out<<"{\"schema\":1,\"boot_id\":\""<<bootText()<<"\",\"revision\":"<<transaction_.revision()
           <<",\"available\":"<<(transaction_.available(now,permitted&&!transportFault_&&!inIo_&&!exchange_.active())?"true":"false")
           <<",\"active\":"<<(active()?"true":"false")
           <<",\"reason\":\""<<(qualified_?transaction_.reason():"settings_transport_unqualified")
           <<"\",\"write_attempted\":"<<(transaction_.writeAttempted()?"true":"false")
           <<",\"transport_fault\":"<<(transportFault_?"true":"false")
           <<",\"phase\":\""<<phaseName()<<"\",\"owned_by_requester\":"
           <<(transaction_.revision()&&control::WebAuthSession::hexToken(requester)&&requester==std::string_view(owner_.data())?"true":"false")
           <<",\"request\":";
        if(transaction_.revision()){
            ClassicBoilerSettingsEncoder::Definition d;ClassicBoilerSettingsEncoder::definition(setting_,d);
            out<<"{\"entity\":\""<<d.entity<<"\",\"value\":"<<value_<<'}';
        }else out<<"null";
        out<<",\"response_at_ms\":";
        if(transaction_.phase()==ClassicBoilerSettingTransaction::Phase::completed)out<<transaction_.responseAt();else out<<"null";
        out<<",\"physical_validation\":false,\"settings\":[";
        bool first=true;
        for(const auto setting:settings()){
            ClassicBoilerSettingsEncoder::Definition d;ClassicBoilerSettingsEncoder::definition(setting,d);
            if(!first)out<<',';
            first=false;
            out<<"{\"entity\":\""<<d.entity<<"\",\"minimum\":"<<d.minimum<<",\"maximum\":"<<d.maximum
               <<",\"telegram_type\":22,\"offset\":"<<static_cast<unsigned>(d.offset)
               <<",\"unit\":\""<<(setting==ClassicBoilerSettingsEncoder::Setting::heatingActivated?"bool":
                   setting==ClassicBoilerSettingsEncoder::Setting::heatingTemperature?"degC":"min")<<"\"}";
        }
        out<<"]}";
    }
    bool active()const{return transaction_.active()||exchange_.active()||inIo_;}
private:
    const char* phaseName()const{
        using Phase=ClassicBoilerSettingTransaction::Phase;
        switch(transaction_.phase()){
            case Phase::idle:return "idle";case Phase::queuedWrite:return "queued_write";
            case Phase::waitingWriteStatus:return "waiting_write_status";case Phase::queuedRead:return "queued_read";
            case Phase::waitingResponse:return "waiting_response";case Phase::completed:return "completed";
            case Phase::failed:return "failed";
        }
        return "failed";
    }
    bool sessionValid(uint64_t now)const{return sessionUntilMs_&&now>=sessionObservedMs_&&now<sessionUntilMs_;}
    template<class Gate,class Clock>bool permission(Gate& gate,Clock& clock)const{
        if(!qualified_||transportFault_||revoked_)return false;
        const bool allowed=gate(std::string_view(owner_.data()));
        return allowed&&sessionValid(clock()/1000);
    }
    static constexpr std::array<ClassicBoilerSettingsEncoder::Setting,4> settings(){return std::array<ClassicBoilerSettingsEncoder::Setting,4>{
        ClassicBoilerSettingsEncoder::Setting::heatingActivated,ClassicBoilerSettingsEncoder::Setting::heatingTemperature,
        ClassicBoilerSettingsEncoder::Setting::burnerMinimumPeriod,ClassicBoilerSettingsEncoder::Setting::pumpDelay};}
    static const cJSON* field(const cJSON* json,const char* key){return cJSON_GetObjectItemCaseSensitive(json,key);}
    static std::string_view string(const cJSON* value){return cJSON_IsString(value)?std::string_view(value->valuestring):std::string_view{};}
    static bool integer(const cJSON* value,int64_t minimum,int64_t maximum){return cJSON_IsNumber(value)
        &&value->valuedouble>=minimum&&value->valuedouble<=maximum&&std::floor(value->valuedouble)==value->valuedouble;}
    std::string bootText()const{
        std::string result(16,'0');auto value=boot_;
        for(int index=15;index>=0;--index){result[index]="0123456789abcdef"[value&15];value>>=4;}
        return result;
    }
    uint64_t boot_,sessionUntilMs_=0,sessionObservedMs_=0;bool qualified_;
    ClassicBoilerSettingTransaction transaction_;
    ClassicSettingBusExchange exchange_;
    ClassicBoilerSettingsEncoder::Setting setting_{};int value_=0;
    bool transportFault_=false,revoked_=false,inIo_=false;
    std::array<char,65> owner_{};
};
} // namespace heating::ems
