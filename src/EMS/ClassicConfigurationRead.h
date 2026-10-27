#pragma once
#include "ClassicBoilerTestEncoder.h"
#include "DeviceVersion.h"
#include "control/BoundedJson.h"
#include "control/WebAuthSession.h"
#include <algorithm>
#include <array>
#include <functional>
#include <ostream>

namespace heating::ems {
// Explicit boot-local one-shot acquisition, NOT a generic EMS request queue.
// Wire reference: https://emsesp.org/EMS-bus (EMS1 read destination MSB).
// Only the addressed UART poll owner calls poll(), under the telemetry lock.
class ClassicConfigurationRead {
public:
    enum class Phase { idle, queued, waiting, completed, failed };
    enum class Kind { configuration, identity };
    struct Result { int http; const char* error; bool duplicate=false; };
    static constexpr uint32_t pollTimeoutMs=5000, responseTimeoutMs=15000, cooldownMs=30000;
    static constexpr uint32_t maximumRevision=2147483647;
    ClassicConfigurationRead(uint64_t boot,bool compiled):boot_(boot),compiled_(compiled) {}
    bool active()const{return phase_==Phase::queued||phase_==Phase::waiting;}
    uint32_t revision()const{return revision_;}
    Phase phase()const{return phase_;}
    const char* reason()const{return reason_;}
    Kind kind()const{return kind_;}
    bool available(uint64_t now,bool permitted,bool otherActive,Kind kind=Kind::configuration)const{
        if(kind!=Kind::configuration&&kind!=Kind::identity)return false;
        const auto index=kind==Kind::identity?1u:0u;
        return compiled_&&boot_&&permitted&&!otherActive&&!active()&&!inIo_&&revision_<maximumRevision
            &&(!revision_||now>=lastNow_)
            &&(!started_[index]||(now>=startedAt_[index]&&now-startedAt_[index]>=cooldownMs));
    }
    // An identity read targets the boiler unless the body names another device
    // that already sent a report this boot. Never our own or an unseen address.
    using ObservedDevice=std::function<bool(uint8_t)>;
    Result request(std::string_view body,std::string_view owner,uint64_t now,bool permitted,bool otherActive,
                   const control::WebAuthSession& sessions,Kind kind=Kind::configuration,
                   const ObservedDevice& observed={}){
        if(kind!=Kind::configuration&&kind!=Kind::identity)return {400,"invalid_read_kind"};
        if(!control::WebAuthSession::hexToken(owner))return {401,"authentication_required"};
        const auto remaining=sessions.remainingMs(owner,now);
        if(!remaining||remaining>UINT64_MAX-now)return {401,"authentication_required"};
        if(inIo_)return {409,"configuration_read_busy"};
        if(body.size()>256)return {400,"invalid_request"};
        const auto doc=control::parseControlJson(body);const auto* j=doc.get();
        const bool targeted=kind==Kind::identity&&cJSON_IsObject(j)&&field(j,"target_address");
        if(!(targeted?exactFields(j,{"schema","boot_id","revision","exclusive_owner_confirmed","independent_stop_confirmed","target_address"})
                     :exactFields(j,{"schema","boot_id","revision","exclusive_owner_confirmed","independent_stop_confirmed"}))
            ||!integerField(j,"schema",1,1)||!integerField(j,"revision",1,maximumRevision))return {400,"invalid_request"};
        uint8_t target=boilerAddress;
        if(targeted){
            if(!integerField(j,"target_address",1,0x7F))return {400,"invalid_target_address"};
            target=static_cast<uint8_t>(field(j,"target_address")->valuedouble);
            if(target==serviceAddress||(target!=boilerAddress&&!(observed&&observed(target))))return {409,"target_not_observed"};
        }
        if(!cJSON_IsTrue(field(j,"exclusive_owner_confirmed"))
            ||!cJSON_IsTrue(field(j,"independent_stop_confirmed")))return {400,"site_confirmation_required"};
        if(stringField(j,"boot_id")!=bootText())return {409,"boot_changed"};
        const auto requested=static_cast<uint32_t>(field(j,"revision")->valuedouble);
        if(requested==revision_&&revision_){
            if(std::string_view(owner_.data())!=owner)return {403,"different_operator"};
            if(kind!=kind_||(kind==Kind::identity&&target!=target_))return {409,"read_kind_changed"};
            return {200,"",true}; // No lease, deadline or read is renewed.
        }
        if(revision_==maximumRevision||requested!=revision_+1)return {409,"revision_changed"};
        if(!available(now,permitted,otherActive,kind))return {409,"configuration_read_unavailable"};
        revision_=requested;armedAt_=lastNow_=now;emittedAt_=responseAt_=0;emitted_=false;
        kind_=kind;target_=kind==Kind::identity?target:boilerAddress;const auto index=kind==Kind::identity?1u:0u;
        started_[index]=true;startedAt_[index]=now;
        std::copy(owner.begin(),owner.end(),owner_.begin());owner_[64]=0;
        sessionObservedAt_=now;sessionUntil_=now+remaining;operatorWithdrawn_=false;
        phase_=Phase::queued;reason_="awaiting_poll";return {202,""};
    }
    // Only the HTTP/session owner may read the real session table. UART and
    // telemetry paths use this cached deadline under their existing owner lock.
    // This projection never touches or renews the authentication session.
    void synchronizeSessions(const control::WebAuthSession& sessions,uint64_t now){
        if(!active()||operatorWithdrawn_)return;
        const auto remaining=sessions.remainingMs(std::string_view(owner_.data()),now);
        if(now<sessionObservedAt_){fail("clock_changed");return;}
        if(!remaining||remaining>UINT64_MAX-now){withdrawOperator();return;}
        sessionObservedAt_=now;sessionUntil_=now+remaining;
    }
    void fail(const char* reason){if(active()){phase_=Phase::failed;reason_=reason;}}
    void tick(uint64_t now,bool permitted){
        if(!active())return;
        if(now<lastNow_){fail("clock_changed");return;}lastNow_=now;
        if(now<sessionObservedAt_){fail("clock_changed");return;}
        if(!sessionUntil_||now>=sessionUntil_)withdrawOperator();
        if(!active())return;
        if(!permitted){fail("transport_unavailable");return;}
        if(phase_==Phase::queued&&now-armedAt_>=pollTimeoutMs)fail("poll_timeout");
        if(phase_==Phase::waiting&&now-emittedAt_>=responseTimeoutMs)
            fail(operatorWithdrawn_?"operator_session_expired":"response_timeout");
    }
    template<class Clock,class Gate,class Write>
    bool poll(Clock clock,Gate gate,Write write){
        if(inIo_)return true;
        if(!active())return false;
        inIo_=true;struct Release{bool& value;~Release(){value=false;}}release{inIo_};
        try{
            const bool permitted=gate();auto now=clock();tick(now,permitted);
            if(phase_!=Phase::queued)return true;
            EmsRawFrame frame{};
            if(kind_==Kind::identity)encodeIdentity(frame,target_);else encode(frame);
            const bool finalPermission=gate();now=clock();tick(now,finalPermission); // Fresh time AFTER the final gate.
            if(phase_!=Phase::queued)return true;
            if(!write(frame)){fail("transmit_failed");return true;}
            // A successful echo proves emission only. Replies must be acquired
            // strictly after completed emission, never while queued or echoed.
            const auto finished=clock();
            if(finished<now){fail("clock_changed");return true;}
            emittedAt_=lastNow_=finished;emitted_=true;
            if(phase_!=Phase::queued&&!operatorWithdrawn_)return true;
            // A sent frame cannot be undone. Retain exclusive ownership until
            // its response/deadline, without reviving the cancelled acquisition.
            phase_=Phase::waiting;reason_=operatorWithdrawn_?"operator_session_expired":"awaiting_response";
            const bool afterPermission=gate();tick(clock(),afterPermission);
        }catch(...){fail("transport_exception");}
        return true;
    }
    void observe(const EmsTelegram& telegram,uint64_t acquiredAt,uint64_t now,
                 bool permitted,const ClassicBoilerMonitor& monitor){
        tick(now,permitted);
        if(phase_!=Phase::waiting||acquiredAt<=emittedAt_||acquiredAt>now
            ||telegram.getOperationType()!=EmsTelegram::WRITE||telegram.getSenderId()!=target_
            ||telegram.getDestinationId()!=serviceAddress||telegram.getOffset()!=0)return;
        if(kind_==Kind::identity){
            if(telegram.getTypeId()!=0x02||telegram.dataSize()<3||telegram.dataSize()>10)return;
            if(operatorWithdrawn_){fail("operator_session_expired");return;}
            if(!readDeviceVersion(telegram)){fail("invalid_identity_response");return;}
            responseAt_=acquiredAt;phase_=Phase::completed;reason_="identity_received";return;
        }
        if(telegram.getTypeId()!=0x16||telegram.dataSize()!=2)return;
        if(operatorWithdrawn_){fail("operator_session_expired");return;}
        const auto& enabled=monitor.sample(BoilerField::heatingEnabled);
        const auto& limit=monitor.sample(BoilerField::heatingLimit);
        if(!enabled.raw||!limit.raw||enabled.observedMs!=acquiredAt||limit.observedMs!=acquiredAt
            ||enabled.sourceType!=0x16||limit.sourceType!=0x16){fail("invalid_configuration_response");return;}
        responseAt_=acquiredAt;phase_=Phase::completed;reason_="configuration_received";
    }
    void writeJSON(std::ostream& out,uint64_t now,bool permitted,bool otherActive)const{
        out<<"{\"schema\":1,\"boot_id\":\""<<bootText()<<"\",\"revision\":"<<revision_
            <<",\"available\":"<<(available(now,permitted,otherActive)?"true":"false")
            <<",\"identity_supported\":"<<(compiled_?"true":"false")
            <<",\"identity_available\":"<<(available(now,permitted,otherActive,Kind::identity)?"true":"false")
            <<",\"kind\":\""<<(kind_==Kind::identity?"identity":"configuration")<<'"'
            <<",\"target_address\":"<<unsigned(target_)
            <<",\"active\":"<<(active()?"true":"false")<<",\"phase\":\""<<phaseName()
            <<"\",\"withdrawn\":"<<(operatorWithdrawn_?"true":"false")
            <<",\"reason\":\""<<reason_<<"\",\"clock\":\"boot_monotonic_ms\",\"observed_at_ms\":"<<now
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
    static void encodeIdentity(EmsRawFrame& frame,uint8_t target=boilerAddress){
        frame={};frame.length=6;frame.data[0]=serviceAddress;frame.data[1]=0x80|target;
        frame.data[2]=0x02;frame.data[3]=0;frame.data[4]=10;
        frame.data[5]=EmsTelegram::calculateCRC(frame.data.data(),5);
    }
private:
    static constexpr uint8_t boilerAddress=0x08,serviceAddress=0x0b;
    void withdrawOperator(){
        operatorWithdrawn_=true;sessionUntil_=0;
        if(phase_==Phase::queued)fail("operator_session_expired");
        else if(phase_==Phase::waiting)reason_="operator_session_expired";
    }
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
    uint64_t sessionObservedAt_=0,sessionUntil_=0;
    bool compiled_,emitted_=false,inIo_=false,operatorWithdrawn_=false;uint32_t revision_=0;Phase phase_=Phase::idle;const char* reason_="not_requested";
    std::array<char,65> owner_{};
    Kind kind_=Kind::configuration;
    uint8_t target_=boilerAddress;
    std::array<uint64_t,2> startedAt_{};
    std::array<bool,2> started_{};
};
}
