#pragma once
// SOURCE-only heterogeneous two-room review reader; never a control grant.
// Explicit TopologyControlStoreView may consume it with independent SOURCE pins,
// never by default or a DATA flag. Existing graph layout/parser limits stay
// unchanged; this reader never returns a GraphShadowCandidate.
#include "GraphShadowValidation.h"

namespace heating::graph_review {
namespace gt=heating::graph_test;
struct Context {
    std::string controllerId,bootId,sessionId,planDigest;
    uint32_t epoch=0,configRevision=0,registryRevision=0,sourceRevision=0;
};
struct Room {
    std::array<char,9> zone{};
    std::array<char,33> group{},actuator{};
    std::array<char,65> sensorResource{},outputResource{};
    int16_t base=0,minimum=0,maximum=0,supplyMinimum=0,supplyMaximum=0;
    uint32_t maximumAge=0;
    bool floor=false;
};
struct Review {
    static constexpr size_t maxBytes=4096,roomCount=2;
    std::array<Room,roomCount> rooms{};
    // No demand, schedule execution, safe-position or readiness representation.
    bool boilerOutputEnabled=false,actuatorOutputEnabled=false,admission=false,applied=false;
};
struct Result {
    const char* code="review_invalid";
    Review review{};
};
template<size_t N> inline void copy(std::array<char,N>& out,const std::string& s) {
    gt::need(s.size()<N,"reference");std::copy(s.begin(),s.end(),out.begin());
}
inline Result read(std::string_view raw,const Context& context,const gt::Hash& hash) {
    try {
        gt::need(raw.size()<=Review::maxBytes,"budget_exceeded");
        const auto root=gt::parse(raw);const auto v=root.get();
        gt::object(v,{"schema","mode","controller_id","boot_id","adapter_session_id","epoch",
            "config_revision","registry_revision","source_revision","plan_digest","plan",
            "boiler_output_enabled","actuator_output_enabled","admission","applied"});
        gt::need(gt::integer(gt::get(v,"schema"),1,UINT32_MAX)==1,"unsupported_schema");
        gt::literal(gt::get(v,"mode"),"source_topology_review","unsupported_schema");
        for(auto p:{std::pair{"controller_id",&context.controllerId},{"boot_id",&context.bootId},
                    {"adapter_session_id",&context.sessionId},{"plan_digest",&context.planDigest}})
            gt::literal(gt::get(v,p.first),p.second->c_str(),"context_conflict");
        for(auto key:{"controller_id","boot_id","adapter_session_id"})gt::identifier(gt::get(v,key));
        for(auto p:{std::pair{"epoch",context.epoch},{"registry_revision",context.registryRevision},
                    {"source_revision",context.sourceRevision}}) {
            gt::need(gt::integer(gt::get(v,p.first),1,UINT32_MAX)==p.second,"context_conflict");
        }
        gt::need(gt::integer(gt::get(v,"config_revision"),0,UINT32_MAX-1)==context.configRevision,"context_conflict");
        for(auto key:{"boiler_output_enabled","actuator_output_enabled","admission","applied"})
            gt::falseValue(gt::get(v,key),"review_only");
        const auto plan=gt::get(v,"plan");
        gt::object(plan,{"draft_digest","rooms"});
        gt::need(gt::hex(gt::str(gt::get(plan,"draft_digest")))&&gt::hex(context.planDigest),"source_conflict");
        gt::need(hash(gt::print(plan))==context.planDigest,"source_conflict");
        const auto rooms=gt::get(plan,"rooms");
        gt::need(cJSON_IsArray(rooms)&&cJSON_GetArraySize(rooms)==2,"review_layout_limit");
        Review review;
        std::set<std::string> ids,resources,emitters;
        std::string previous;
        size_t i=0;
        for(auto r=rooms->child;r;r=r->next,++i) {
            gt::object(r,{"zone_id","group_id","actuator_id","emitter","actuator_profile",
                "sensor_resource","output_resource","base_centi_c","minimum_target_centi_c",
                "maximum_target_centi_c","max_age_ms","minimum_supply_centi_c","maximum_supply_centi_c"});
            const auto rid=gt::str(gt::get(r,"zone_id"));
            gt::need(gt::hex(rid,8)&&rid>previous,"reference");previous=rid;
            for(auto key:{"zone_id","group_id","actuator_id"}) {
                const auto val=gt::str(gt::get(r,key));gt::identifier(gt::get(r,key));
                gt::need(val!="adapter"&&val!="config"&&val!="snapshot"&&ids.insert(val).second,"owner_conflict");
            }
            const auto emitter=gt::str(gt::get(r,"emitter")),profile=gt::str(gt::get(r,"actuator_profile"));
            gt::need(((emitter=="radiator"&&profile=="trv_room_setpoint")||
                      (emitter=="floor"&&profile=="binary_valve"))&&emitters.insert(emitter).second,"unsupported_topology");
            for(auto key:{"sensor_resource","output_resource"}) {
                const auto val=gt::str(gt::get(r,key));gt::need(gt::hex(val),"reference");
                gt::need(resources.insert(val).second,"owner_conflict");
            }
            auto& out=review.rooms[i];
            copy(out.zone,rid);copy(out.group,gt::str(gt::get(r,"group_id")));
            copy(out.actuator,gt::str(gt::get(r,"actuator_id")));
            copy(out.sensorResource,gt::str(gt::get(r,"sensor_resource")));
            copy(out.outputResource,gt::str(gt::get(r,"output_resource")));
            const auto minimum=gt::integer(gt::get(r,"minimum_target_centi_c"),500,3499);
            const auto maximum=gt::integer(gt::get(r,"maximum_target_centi_c"),minimum+1,3500);
            out.minimum=minimum;out.maximum=maximum;
            out.base=gt::integer(gt::get(r,"base_centi_c"),minimum,maximum);
            out.maximumAge=gt::integer(gt::get(r,"max_age_ms"),1000,86400000);
            const auto low=gt::integer(gt::get(r,"minimum_supply_centi_c"),500,8999);
            out.supplyMinimum=low;out.supplyMaximum=gt::integer(gt::get(r,"maximum_supply_centi_c"),low+1,9000);
            out.floor=emitter=="floor";
        }
        return {"source_topology_review_only",review};
    } catch(const gt::Failure& error) {return {error.code,{}};}
      catch(const std::bad_alloc&) {return {"allocation",{}};}
      catch(...) {return {"review_invalid",{}};}
}
} // namespace heating::graph_review
