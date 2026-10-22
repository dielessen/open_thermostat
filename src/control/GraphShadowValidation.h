#pragma once
// Shared graph-shadow validator, including the source-stage configuration core.
// NOT selected by active api1/ModernTransport. Validation itself has no device
// callbacks, persistence or capability advertisement.
#include <cJSON.h>
#include <array>
#include <algorithm>
#include <cstdint>
#include <utility>
#include <cmath>
#include <cstring>
#include <functional>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>

namespace heating::graph_test {
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
using Hash=std::function<std::string(std::string_view)>;
struct Context {
    std::string controllerId,bootId,adapterId,sessionId,grantId;
    uint32_t epoch,grantSequence,currentRevision,mappingRevision;
    std::string mappingDigest,qualificationDigest;
};
struct TestLayout {
    static constexpr size_t rooms=1,groups=1,actuators=1,transitions=8,totalTransitions=8,streams=7;
};
struct Transition { int64_t utc=0; int16_t target=0; };
// Fixed-layout accounting object only. No actuator execution/state machine.
struct GraphShadowCandidate {
    uint32_t revision=0,mappingRevision=0;
    std::array<char,9> room{};
    std::array<char,33> group{},actuator{},sensor{},output{},feedback{};
    std::array<int16_t,9> curve{};
    std::array<Transition,TestLayout::transitions> transitions{};
    uint8_t transitionCount=0,streamCount=0;
    int16_t base=0,minimum=0,maximum=0;
    bool boilerOutputEnabled=false,actuatorOutputEnabled=false;
};
struct Result { std::string code; GraphShadowCandidate candidate{}; };
struct Failure { const char *code; };
inline void need(bool value,const char *code) { if(!value) throw Failure{code}; }
inline const cJSON *get(const cJSON *o,const char *k) { return cJSON_GetObjectItemCaseSensitive(o,k); }
inline std::string str(const cJSON *o) { return cJSON_IsString(o)&&o->valuestring?o->valuestring:""; }
inline std::string print(const cJSON *o) {
    std::unique_ptr<char,decltype(&cJSON_free)> p(cJSON_PrintUnformatted(o),cJSON_free);
    need(bool(p),"allocation");return p.get();
}
inline bool id(std::string_view s) {
    if(s.empty()||s.size()>32)return false;
    for(unsigned char c:s)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||
        (c>='0'&&c<='9')||c=='_'||c=='-'))return false;
    return true;
}
inline bool hex(std::string_view s,size_t length=64) {
    if(s.size()!=length)return false;
    for(char c:s)if(!((c>='a'&&c<='f')||(c>='0'&&c<='9')))return false;
    return true;
}
inline void object(const cJSON *o,std::initializer_list<const char*> keys) {
    need(cJSON_IsObject(o)&&cJSON_GetArraySize(o)==static_cast<int>(keys.size()),"schema");
    for(auto k:keys)need(get(o,k),"schema");
}
inline int64_t integer(const cJSON *v,int64_t low,int64_t high) {
    need(cJSON_IsNumber(v)&&std::isfinite(v->valuedouble)&&v->valuedouble>=low&&
        v->valuedouble<=high&&std::floor(v->valuedouble)==v->valuedouble,"bounds");
    return static_cast<int64_t>(v->valuedouble);
}
inline void literal(const cJSON *v,const char *expected,const char *code="schema") {
    need(cJSON_IsString(v)&&str(v)==expected,code);
}
inline void nullValue(const cJSON *v,const char *code="schema") { need(cJSON_IsNull(v),code); }
inline void zero(const cJSON *v,const char *code="schema") {need(cJSON_IsNumber(v)&&v->valuedouble==0,code);}
inline void falseValue(const cJSON *v,const char *code="schema") {need(cJSON_IsFalse(v),code);}
inline void equal(const cJSON *a,const cJSON *b,const char *code="schema") {need(a&&b&&print(a)==print(b),code);}
inline void identifier(const cJSON *v) {need(cJSON_IsString(v)&&id(str(v)),"reference");}
inline std::pair<int64_t,int64_t> limits(const cJSON *o) {
    object(o,{"minimum_centi_c","maximum_centi_c"});
    auto low=integer(get(o,"minimum_centi_c"),500,9000);
    return {low,integer(get(o,"maximum_centi_c"),low+1,9000)};
}
inline Json parse(std::string_view raw) {
    need(!raw.empty(),"json_format");need(raw.size()<=8192,"budget_exceeded");
    for(unsigned char c:raw)need(c<128&&c!='\\'&&(c>=32||c=='\t'||c=='\r'||c=='\n'),"json_format");
    size_t depth=0,nodes=0,length=0;bool quoted=false;
    for(size_t i=0;i<raw.size();++i) {
        char c=raw[i];
        if(quoted) {
            if(c=='"'){quoted=false;++nodes;}
            else {need(static_cast<unsigned char>(c)>=32,"json_format");need(++length<=64,"budget_exceeded");}
        } else if(c=='"'){quoted=true;length=0;}
        else if(c=='{'||c=='['){need(++depth<=8,"budget_exceeded");++nodes;}
        else if(c=='}'||c==']'){if(depth)--depth;}
        else if(c=='-'||(c>='0'&&c<='9')) {
            size_t end=i+1;
            while(end<raw.size()&&std::string_view(",]} \t\r\n").find(raw[end])==std::string_view::npos)++end;
            for(size_t j=i;j<end;++j)need(raw[j]=='-'||(raw[j]>='0'&&raw[j]<='9'),"json_integer");
            size_t begin=i+(raw[i]=='-'?1:0);
            need(begin<end&&!(raw[begin]=='0'&&end-begin>1),"json_format");
            uint64_t number=0;
            for(size_t j=begin;j<end;++j) {
                need(raw[j]>='0'&&raw[j]<='9',"json_format");
                number=number*10+static_cast<unsigned>(raw[j]-'0');
                need(number<=UINT32_MAX,"json_integer");
            }
            ++nodes;i=end-1;
        } else if(c=='N'||c=='I') {
            need(raw.substr(i,3)!="NaN"&&raw.substr(i,8)!="Infinity","json_integer");
        } else if(c=='t'||c=='f'||c=='n') {
            size_t end=i;
            while(end<raw.size()&&std::string_view(",]} \t\r\n").find(raw[end])==std::string_view::npos)++end;
            ++nodes;i=end-1;
        }
        need(nodes<=512,"budget_exceeded");
    }
    std::string owned(raw);
    Json root(cJSON_ParseWithLengthOpts(owned.c_str(),owned.size()+1,nullptr,true),cJSON_Delete);
    need(bool(root)&&cJSON_IsObject(root.get()),"json_format");
    const auto unique=[](auto&& self,const cJSON *o)->void {
        for(auto p=o->child;p;p=p->next) {
            if(cJSON_IsObject(o))
                for(auto earlier=o->child;earlier!=p;earlier=earlier->next)
                    need(std::strcmp(earlier->string,p->string)!=0,"json_duplicate");
            self(self,p);
        }
    };
    unique(unique,root.get());
    const auto check=[](auto&& self,const cJSON *o)->void {
        if(cJSON_IsNumber(o))need(std::isfinite(o->valuedouble)&&std::floor(o->valuedouble)==o->valuedouble&&
            std::abs(o->valuedouble)<=4294967295.0,"json_integer");
        const char *previous=nullptr;
        for(auto p=o->child;p;p=p->next) {
            if(cJSON_IsObject(o)) {
                need(!previous||std::strcmp(previous,p->string)<0,"json_canonical");
                previous=p->string;
            }
            self(self,p);
        }
    };
    check(check,root.get());need(print(root.get())==raw,"json_canonical");
    return root;
}
inline Result validate(std::string_view raw,std::string_view mappingRaw,const Context &ctx,const Hash &hash) {
    try {
        need(ctx.mappingRevision?hex(ctx.mappingDigest):ctx.mappingDigest.empty(),"mapping_conflict");
        auto message=parse(raw);auto mapping=parse(mappingRaw);
        const auto e=message.get();const auto m=mapping.get();
        object(e,{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id",
            "grant_sequence","config_revision","binding_id","sequence","expected_revision","config_digest","config"});
        need(cJSON_IsNumber(get(e,"api"))&&get(e,"api")->valuedouble==2,"unsupported_schema");
        for(auto pair:{std::pair{"controller_id",&ctx.controllerId},{"boot_id",&ctx.bootId},
            {"adapter_id",&ctx.adapterId},{"adapter_session_id",&ctx.sessionId},{"grant_id",&ctx.grantId}}) {
            literal(get(e,pair.first),pair.second->c_str(),"identity");identifier(get(e,pair.first));
        }
        need(cJSON_IsNumber(get(e,"epoch"))&&get(e,"epoch")->valuedouble==ctx.epoch&&
            cJSON_IsNumber(get(e,"grant_sequence"))&&get(e,"grant_sequence")->valuedouble==ctx.grantSequence,"identity");
        integer(get(e,"epoch"),1,UINT32_MAX);integer(get(e,"grant_sequence"),1,UINT32_MAX);
        integer(get(e,"sequence"),1,UINT32_MAX);literal(get(e,"binding_id"),"config","identity");
        auto c=get(e,"config");
        object(c,{"schema","mode","revision","mapping_revision","mapping_digest","required_capabilities",
            "central","groups","actuators","rooms","qualification"});
        need(cJSON_IsNumber(get(c,"schema"))&&get(c,"schema")->valuedouble==2,"unsupported_schema");
        literal(get(c,"mode"),"shadow_graph","unsupported_schema");
        need(ctx.currentRevision<UINT32_MAX,"revision_exhausted");
        for(auto k:{"expected_revision","config_revision"})
            need(cJSON_IsNumber(get(e,k))&&get(e,k)->valuedouble==ctx.currentRevision,"revision_conflict");
        need(cJSON_IsNumber(get(c,"revision"))&&get(c,"revision")->valuedouble==ctx.currentRevision+1,"revision_conflict");
        const auto bytes=print(c);need(bytes.size()<=4096,"budget_exceeded");
        literal(get(e,"config_digest"),hash(bytes).c_str(),"config_digest");
        const std::array<const char*,6> caps{"heating.actuator.binary_valve.v1","heating.central_weather.v1",
            "heating.emitter.floor.v1","heating.emitter_groups.v1","heating.graph_shadow.v1","schedule.utc.v1"};
        auto required=get(c,"required_capabilities");
        need(cJSON_IsArray(required)&&cJSON_GetArraySize(required)==6,"unsupported_capability");
        for(int i=0;i<6;++i)literal(cJSON_GetArrayItem(required,i),caps[i],"unsupported_capability");
        object(m,{"mapping_schema","mapping_revision","channels"});
        need(cJSON_IsNumber(get(m,"mapping_schema"))&&get(m,"mapping_schema")->valuedouble==2,"mapping_conflict");
        auto revision=integer(get(m,"mapping_revision"),1,UINT32_MAX);
        need(cJSON_IsNumber(get(c,"mapping_revision"))&&get(c,"mapping_revision")->valuedouble==revision,"mapping_conflict");
        const auto md=hash(mappingRaw);literal(get(c,"mapping_digest"),md.c_str(),"mapping_conflict");
        if(md==ctx.mappingDigest)need(revision==ctx.mappingRevision,"mapping_conflict");
        else need(ctx.mappingRevision<UINT32_MAX&&revision==ctx.mappingRevision+1,"mapping_conflict");
        auto channels=get(m,"channels");
        need(cJSON_IsArray(channels)&&cJSON_GetArraySize(channels)==3,"reference");
        std::set<std::string> resources,ids{"adapter","config","snapshot"};
        for(auto p=channels->child;p;p=p->next) {
            object(p,{"channel_id","direction","owner_id","resource_id"});
            identifier(get(p,"channel_id"));identifier(get(p,"owner_id"));
            need(ids.insert(str(get(p,"channel_id"))).second&&hex(str(get(p,"resource_id"))),"reference");
            need(resources.insert(str(get(p,"resource_id"))).second,"output_owner_conflict");
            auto dir=str(get(p,"direction"));need(dir=="input"||dir=="output","reference");
        }
        const auto role=[channels](const cJSON *channel,const char *direction,const std::string &owner) {
            for(auto p=channels->child;p;p=p->next)
                if(str(get(p,"channel_id"))==str(channel)) {
                    need(str(get(p,"direction"))==direction&&str(get(p,"owner_id"))==owner,"reference");return;
                }
            throw Failure{"reference"};
        };
        for(auto k:{"rooms","groups","actuators"})
            need(cJSON_IsArray(get(c,k))&&cJSON_GetArraySize(get(c,k))==1,"test_layout_limit");
        auto r=get(c,"rooms")->child;auto g=get(c,"groups")->child;auto a=get(c,"actuators")->child;
        object(r,{"zone_id","sensor_id","base_centi_c","minimum_target_centi_c","maximum_target_centi_c",
            "max_age_ms","report_profile_id","report_evidence","schedule"});
        const auto rid=str(get(r,"zone_id"));need(hex(rid,8),"reference");
        role(get(r,"sensor_id"),"input",rid);
        auto minimum=integer(get(r,"minimum_target_centi_c"),500,3499);
        auto maximum=integer(get(r,"maximum_target_centi_c"),minimum+1,3500);
        auto base=integer(get(r,"base_centi_c"),minimum,maximum);auto age=integer(get(r,"max_age_ms"),1000,86400000);
        object(g,{"group_id","emitter","supply_limits","pump_channel","pump_start_delay_s","postrun_s","mixing"});
        identifier(get(g,"group_id"));auto gid=str(get(g,"group_id"));literal(get(g,"emitter"),"floor","unsupported_capability");
        auto [gl,gh]=limits(get(g,"supply_limits"));
        nullValue(get(g,"mixing"),"unsupported_capability");nullValue(get(g,"pump_channel"),"unsupported_capability");
        zero(get(g,"pump_start_delay_s"),"unsupported_capability");zero(get(g,"postrun_s"),"unsupported_capability");
        auto central=get(c,"central");
        object(central,{"weather_enabled","outdoor_channel","outdoor_kind","outdoor_maximum_age_ms",
            "stale_policy","fixed_fallback_centi_c","supply_limits","outdoor_axis_centi_c","curve_centi_c"});
        falseValue(get(central,"weather_enabled"),"unsupported_capability");
        nullValue(get(central,"outdoor_channel"),"unsupported_capability");nullValue(get(central,"outdoor_kind"),"unsupported_capability");
        integer(get(central,"outdoor_maximum_age_ms"),1000,86400000);
        literal(get(central,"stale_policy"),"block_normal_demand","unsupported_capability");
        nullValue(get(central,"fixed_fallback_centi_c"),"unsupported_capability");
        auto [cl,ch]=limits(get(central,"supply_limits"));need(gh==ch&&gl>=cl,"bounds");
        need(print(get(central,"outdoor_axis_centi_c"))=="[2000,1500,1000,500,0,-500,-1000,-1500,-2000]","schema");
        auto curve=get(central,"curve_centi_c");need(cJSON_IsArray(curve)&&cJSON_GetArraySize(curve)==9,"schema");
        int64_t lastCurve=cl;
        for(auto p=curve->child;p;p=p->next){auto v=integer(p,cl,ch);need(v>=lastCurve,"bounds");lastCurve=v;}
        object(a,{"actuator_id","room_id","group_id","profile","output_channel","settings"});
        identifier(get(a,"actuator_id"));auto aid=str(get(a,"actuator_id"));
        need(ids.insert(rid).second&&ids.insert(gid).second&&ids.insert(aid).second,"reference");
        literal(get(a,"room_id"),rid.c_str(),"reference");literal(get(a,"group_id"),gid.c_str(),"reference");
        literal(get(a,"profile"),"binary_valve","unsupported_capability");role(get(a,"output_channel"),"output",aid);
        auto settings=get(a,"settings");
        object(settings,{"deenergized_position","control","travel_time_s","minimum_on_s","minimum_off_s","cycle_s"});
        auto deenergized=str(get(settings,"deenergized_position"));
        need(deenergized=="normally_closed"||deenergized=="normally_open","qualification");
        literal(get(settings,"control"),"tpi","unsupported_capability");
        auto travel=integer(get(settings,"travel_time_s"),1,3600);
        auto on=integer(get(settings,"minimum_on_s"),travel,7200);auto off=integer(get(settings,"minimum_off_s"),1,7200);
        integer(get(settings,"cycle_s"),std::max(int64_t(60),on+off),86400);
        auto q=get(c,"qualification");
        object(q,{"record_digest","outputs_ready","boiler_ready","sources","devices","installation"});
        falseValue(get(q,"outputs_ready"),"qualification");falseValue(get(q,"boiler_ready"),"qualification");
        Json manifest(cJSON_CreateObject(),cJSON_Delete);
        need(bool(manifest),"allocation");
        // Retain each duplicate until the public cJSON API confirms transfer.
        // Failed key allocation does NOT transfer ownership to the object.
        for(auto k:{"devices","installation","sources"}) {
            Json copy(cJSON_Duplicate(get(q,k),true),cJSON_Delete);
            need(bool(copy),"allocation");
            need(cJSON_AddItemToObject(manifest.get(),k,copy.get()),"allocation");
            copy.release();
        }
        const auto qd=hash(print(manifest.get()));
        need(hex(ctx.qualificationDigest)&&str(get(q,"record_digest"))==qd&&qd==ctx.qualificationDigest,"qualification");
        auto sources=get(q,"sources");need(cJSON_IsArray(sources)&&cJSON_GetArraySize(sources)==1,"qualification");
        auto source=sources->child;
        object(source,{"channel_id","profile_id","evidence","maximum_report_interval_ms",
            "maximum_transport_delay_ms","restore_policy","evidence_record_id","producer_path_record_id"});
        equal(get(source,"channel_id"),get(r,"sensor_id"),"qualification");
        identifier(get(source,"profile_id"));identifier(get(source,"evidence_record_id"));identifier(get(source,"producer_path_record_id"));
        equal(get(r,"report_profile_id"),get(source,"profile_id"),"qualification");
        auto evidence=str(get(source,"evidence"));need(evidence=="physical_report"||evidence=="validated_integration_report","qualification");
        equal(get(r,"report_evidence"),get(source,"evidence"),"qualification");
        auto cadence=integer(get(source,"maximum_report_interval_ms"),1,86400000);
        auto delay=integer(get(source,"maximum_transport_delay_ms"),1,15000);
        need(cadence+delay<age,"qualification");literal(get(source,"restore_policy"),"reject","qualification");
        auto devices=get(q,"devices");need(cJSON_IsArray(devices)&&cJSON_GetArraySize(devices)==1,"qualification");
        auto device=devices->child;
        object(device,{"output_channel","profile_id","deenergized_position","energized_position","command_polarity",
            "feedback_channel","feedback_profile_id","feedback_maximum_age_ms","readiness","opening_deadline_ms",
            "failure_policy_id","reference_policy","evidence_record_id","power_loss_position","safe_position","failure_action","stale_feedback_policy","safe_position_record_id"});
        equal(get(device,"output_channel"),get(a,"output_channel"),"qualification");
        for(auto k:{"profile_id","feedback_profile_id","failure_policy_id","evidence_record_id","safe_position_record_id"})identifier(get(device,k));
        equal(get(device,"deenergized_position"),get(settings,"deenergized_position"),"qualification");
        literal(get(device,"energized_position"),deenergized=="normally_closed"?"open":"closed","qualification");
        const char *powerLoss=deenergized=="normally_closed"?"closed":"open";
        literal(get(device,"power_loss_position"),powerLoss,"qualification");
        literal(get(device,"safe_position"),powerLoss,"qualification");
        literal(get(device,"failure_action"),"withdraw_heat_deenergize","qualification");
        literal(get(device,"stale_feedback_policy"),"withdraw_heat","qualification");
        literal(get(device,"command_polarity"),"on_energizes","qualification");
        role(get(device,"feedback_channel"),"input",aid);
        integer(get(device,"feedback_maximum_age_ms"),1,15000);
        literal(get(device,"readiness"),"end_switch_open","qualification");
        integer(get(device,"opening_deadline_ms"),travel*1000,3600000);
        literal(get(device,"reference_policy"),"binary_endstops","qualification");
        auto inst=get(q,"installation");
        object(inst,{"group_id","minimum_flow_record_id","postrun_record_id","high_limit_record_id","maximum_supply_centi_c","high_limit_kind","floor_limit_kind","maximum_floor_centi_c","floor_limit_record_id"});
        literal(get(inst,"group_id"),gid.c_str(),"qualification");
        for(auto k:{"minimum_flow_record_id","postrun_record_id","high_limit_record_id","floor_limit_record_id"})identifier(get(inst,k));
        equal(get(inst,"maximum_supply_centi_c"),get(get(g,"supply_limits"),"maximum_centi_c"),"qualification");
        literal(get(inst,"high_limit_kind"),"independent_water_cutout","qualification");
        literal(get(inst,"floor_limit_kind"),"independent_floor_cutout","qualification");
        integer(get(inst,"maximum_floor_centi_c"),500,3500);
        GraphShadowCandidate out;
        out.revision=ctx.currentRevision+1;out.mappingRevision=revision;out.base=base;out.minimum=minimum;out.maximum=maximum;
        auto schedule=get(r,"schedule");
        if(!cJSON_IsNull(schedule)) {
            object(schedule,{"timezone","policy","valid_from_utc","valid_until_utc","base_centi_c","transitions"});
            auto tz=str(get(schedule,"timezone"));need(tz=="UTC"||tz=="Europe/Amsterdam","schedule");
            literal(get(schedule,"policy"),"wall-clock-membership/v1","schedule");
            auto start=integer(get(schedule,"valid_from_utc"),946684800,4102444799LL);
            auto end=integer(get(schedule,"valid_until_utc"),start+1,std::min<int64_t>(start+16*86400,4102444800LL));
            equal(get(schedule,"base_centi_c"),get(r,"base_centi_c"),"schedule");
            auto transitions=get(schedule,"transitions");
            need(cJSON_IsArray(transitions)&&cJSON_GetArraySize(transitions)>=1&&cJSON_GetArraySize(transitions)<=int(TestLayout::transitions),"schedule_budget");
            int64_t last=start-1;
            for(auto p=transitions->child;p;p=p->next) {
                need(cJSON_IsArray(p)&&cJSON_GetArraySize(p)==2,"schedule");
                auto at=integer(p->child,start,end-1);auto target=integer(p->child->next,minimum,maximum);
                need(at>last&&(out.transitionCount||at==start),"schedule");last=at;
                out.transitions[out.transitionCount++]={at,static_cast<int16_t>(target)};
            }
        }
        need(out.transitionCount<=TestLayout::totalTransitions,"schedule_budget");
        out.streamCount=3+2+2;need(out.streamCount<=TestLayout::streams,"stream_budget");
        const auto copy=[](auto &dest,const std::string &v){std::copy(v.begin(),v.end(),dest.begin());};
        copy(out.room,rid);copy(out.group,gid);copy(out.actuator,aid);
        copy(out.sensor,str(get(r,"sensor_id")));copy(out.output,str(get(a,"output_channel")));copy(out.feedback,str(get(device,"feedback_channel")));
        for(size_t i=0;i<9;++i)out.curve[i]=integer(cJSON_GetArrayItem(curve,i),cl,ch);
        return {"valid_shadow_candidate",out};
    } catch(const Failure &e){return {e.code,{}};}
      catch(const std::bad_alloc &){return {"allocation",{}};}
}
}
