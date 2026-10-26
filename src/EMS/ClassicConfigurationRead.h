#pragma once
#include "ClassicBoilerTestEncoder.h"
#include "control/BoundedJson.h"
#include "control/WebAuthSession.h"
#include <algorithm>
#include <array>
#include <ostream>

namespace heating::ems {
// Explicit boot-local one-shot acquisition, NOT a generic EMS request queue.
// Wire reference: https://emsesp.org/EMS-bus (EMS1 read destination MSB).
// Only the addressed UART poll owner calls poll(), under the telemetry lock.
class ClassicConfigurationRead {
public:
    enum class Phase { idle, queued, waiting, completed, failed };
    struct Result { int http; const char* error; bool duplicate=false; };
    static constexpr uint32_t pollTimeoutMs=5000, responseTimeoutMs=15000, cooldownMs=30000;
    static constexpr uint32_t maximumRevision=2147483647;
    ClassicConfigurationRead(uint64_t boot,bool compiled):boot_(boot),compiled_(compiled) {}
    bool active()const{return phase_==Phase::queued||phase_==Phase::waiting;}
    uint32_t revision()const{return revision_;}
    Phase phase()const{return phase_;}
    const char* reason()const{return reason_;}
    bool available(uint64_t now,bool permitted,bool otherActive)const{
        return compiled_&&boot_&&permitted&&!otherActive&&!active()&&revision_<maximumRevision
            &&(!revision_||(now>=armedAt_&&now-armedAt_>=cooldownMs));
    }
    Result request(std::string_view body,std::string_view owner,uint64_t now,bool permitted,bool otherActive){
        if(!control::WebAuthSession::hexToken(owner))return {401,"authentication_required"};
        if(body.size()>256)return {400,"invalid_request"};
        const auto doc=control::parseControlJson(body);const auto* j=doc.get();
        if(!exactFields(j,{"schema","boot_id","revision","exclusive_owner_confirmed","independent_stop_confirmed"})
            ||!integerField(j,"schema",1,1)||!integerField(j,"revision",1,maximumRevision))return {400,"invalid_request"};
        if(!cJSON_IsTrue(field(j,"exclusive_owner_confirmed"))
            ||!cJSON_IsTrue(field(j,"independent_stop_confirmed")))return {400,"site_confirmation_required"};
        if(stringField(j,"boot_id")!=bootText())return {409,"boot_changed"};
        const auto requested=static_cast<uint32_t>(field(j,"revision")->valuedouble);
        if(requested==revision_&&revision_){
            if(std::string_view(owner_.data())!=owner)return {403,"different_operator"};
            return {200,"",true}; // No lease, deadline or read is renewed.
        }
        if(revision_==maximumRevision||requested!=revision_+1)return {409,"revision_changed"};
        if(!available(now,permitted,otherActive))return {409,"configuration_read_unavailable"};
        revision_=requested;armedAt_=lastNow_=now;emittedAt_=responseAt_=0;emitted_=false;
        std::copy(owner.begin(),owner.end(),owner_.begin());owner_[64]=0;
        phase_=Phase::queued;reason_="awaiting_poll";return {202,""};
    }
    void fail(const char* reason){if(active()){phase_=Phase::failed;reason_=reason;}}
    void tick(uint64_t now,bool permitted){
        if(!active())return;
        if(now<lastNow_){fail("clock_changed");return;}lastNow_=now;
        if(!permitted){fail("transport_unavailable");return;}
        if(phase_==Phase::queued&&now-armedAt_>=pollTimeoutMs)fail("poll_timeout");
        if(phase_==Phase::waiting&&now-emittedAt_>=responseTimeoutMs)fail("response_timeout");
    }
    template<class Clock,class Gate,class Write>
    bool poll(Clock clock,Gate gate,Write write){
        if(!active())return false;
        try{
            auto now=clock();tick(now,gate());
            if(phase_!=Phase::queued)return true;
            EmsRawFrame frame{};encode(frame);
            now=clock();tick(now,gate()); // Final admission AFTER encoding.
            if(phase_!=Phase::queued)return true;
            if(!write(frame)){fail("transmit_failed");return true;}
            // A successful echo proves emission only. Replies must be acquired
            // strictly after completed emission, never while queued or echoed.
            const auto finished=clock();
            if(finished<now){fail("clock_changed");return true;}
            emittedAt_=lastNow_=finished;emitted_=true;phase_=Phase::waiting;reason_="awaiting_response";
            tick(finished,gate());
        }catch(...){fail("transport_exception");}
        return true;
    }
    void observe(const EmsTelegram& telegram,uint64_t acquiredAt,uint64_t now,
                 bool permitted,const ClassicBoilerMonitor& monitor){
        tick(now,permitted);
        if(phase_!=Phase::waiting||acquiredAt<=emittedAt_||acquiredAt>now
            ||telegram.getOperationType()!=EmsTelegram::WRITE||telegram.getSenderId()!=8
            ||telegram.getDestinationId()!=0x0b||telegram.getTypeId()!=0x16
            ||telegram.getOffset()!=0||telegram.dataSize()!=2)return;
        const auto& enabled=monitor.sample(BoilerField::heatingEnabled);
        const auto& limit=monitor.sample(BoilerField::heatingLimit);
        if(!enabled.raw||!limit.raw||enabled.observedMs!=acquiredAt||limit.observedMs!=acquiredAt
            ||enabled.sourceType!=0x16||limit.sourceType!=0x16){fail("invalid_configuration_response");return;}
        responseAt_=acquiredAt;phase_=Phase::completed;reason_="configuration_received";
    }
    void writeJSON(std::ostream& out,uint64_t now,bool permitted,bool otherActive)const{
        out<<"{\"schema\":1,\"boot_id\":\""<<bootText()<<"\",\"revision\":"<<revision_
            <<",\"available\":"<<(available(now,permitted,otherActive)?"true":"false")
            <<",\"active\":"<<(active()?"true":"false")<<",\"phase\":\""<<phaseName()
            <<"\",\"reason\":\""<<reason_<<"\",\"clock\":\"boot_monotonic_ms\",\"observed_at_ms\":"<<now
            <<",\"emitted_at_ms\":";
        if(emitted_)out<<emittedAt_;else out<<"null";
        out<<",\"response_at_ms\":";if(phase_==Phase::completed)out<<responseAt_;else out<<"null";
        out<<",\"physical_validation\":false}";
    }
    static void encode(EmsRawFrame& frame){
        frame={};frame.length=6;frame.data[0]=0x0b;frame.data[1]=0x88;
        frame.data[2]=0x16;frame.data[3]=0;frame.data[4]=2;
        frame.data[5]=EmsTelegram::calculateCRC(frame.data.data(),5);
    }
private:
    static const cJSON* field(const cJSON* j,const char* key){return cJSON_GetObjectItemCaseSensitive(j,key);}
    static std::string_view stringField(const cJSON* j,const char* key){
        const auto* v=field(j,key);return cJSON_IsString(v)?std::string_view(v->valuestring):std::string_view{};
    }
    static bool integerField(const cJSON* j,const char* key,uint32_t lo,uint32_t hi){
        const auto* v=field(j,key);return cJSON_IsNumber(v)&&v->valuedouble>=lo&&v->valuedouble<=hi&&std::floor(v->valuedouble)==v->valuedouble;
    }
    static bool exactFields(const cJSON* j,std::initializer_list<const char*> keys){
        if(!cJSON_IsObject(j)||cJSON_GetArraySize(j)!=static_cast<int>(keys.size()))return false;
        for(auto key:keys)if(!field(j,key))return false;
        return true;
    }
    const char* phaseName()const{
        switch(phase_){case Phase::idle:return "idle";case Phase::queued:return "queued";
            case Phase::waiting:return "waiting";case Phase::completed:return "completed";case Phase::failed:return "failed";}
        return "failed";
    }
    std::string bootText()const{
        std::string text(16,'0');auto value=boot_;
        for(int i=15;i>=0;--i){text[i]="0123456789abcdef"[value&15];value>>=4;}return text;
    }
    uint64_t boot_,armedAt_=0,lastNow_=0,emittedAt_=0,responseAt_=0;
    bool compiled_,emitted_=false;uint32_t revision_=0;Phase phase_=Phase::idle;const char* reason_="not_requested";
    std::array<char,65> owner_{};
};
}
