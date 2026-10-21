#pragma once
#include "GraphControlStoreView.h"
#include "TopologyControlStoreView.h"

namespace heating::control {
// Explicit SOURCE pin, not an API2 capability or GUI-created authority.
// ONE persisted floor DATA record plus separately reviewed native TRV target.
struct GraphFloorControlHandoffSource {
    static constexpr const char* version="graph-floor-native-trv.v1";
    std::string profileVersion,reviewJson;
    GraphControlHandoffSource data;
    TopologyControlHandoffSource topology;
    bool valid()const {
        return profileVersion==version&&reviewJson.size()<=4096&&!reviewJson.empty()
            &&data.valid()&&topology.valid()&&data.controllerId==topology.context.controllerId
            &&data.adapterId==topology.adapterId&&data.profileDigest==topology.profileDigest
            &&data.revision==topology.context.configRevision+1
            &&data.mappingRevision==topology.context.registryRevision;
    }
};
// Same backing key, no write/migration/new owner. Existing authoritative graph
// reader validates exact durable DATA, existing topology view projects TWO
// independently SOURCE-pinned targets into the existing ShadowController.
class GraphFloorControlStoreView final:public ControlStore {
    class ReviewSnapshot final:public ControlStore {
    public:
        ReviewSnapshot(const std::string& bytes,const bool& fault):bytes_(bytes),fault_(fault){}
        bool load(std::string& out)override{out.clear();if(fault_)return false;out=bytes_;return true;}
        bool save(std::string_view)override{return false;}
    private:const std::string& bytes_;const bool& fault_;
    };
public:
    using Hash=heating::graph_test::Hash;
    GraphFloorControlStoreView(const std::string& controller,const std::string& adapter,
        ControlStore& backing,Hash hash,const GraphFloorControlHandoffSource& source,
        const SeasonalControllerSource& policy)
        :backing_(backing),hash_(std::move(hash)),review_(source_.reviewJson,fault_) {
        if(!source.valid()||!hash_||controller!=source.data.controllerId||adapter!=source.data.adapterId
            ||!policy.valid()||policy.count!=2||policy.controllerId!=controller
            ||policy.profileDigest!=source.data.profileDigest) {fail("bridge_source_invalid");return;}
        source_=source; // All dynamic SOURCE pins bounded before copy.
        projected_=std::make_unique<TopologyControlStoreView>(controller,adapter,review_,hash_,source_.topology,policy);
        if(projected_->faulted())fail("bridge_topology_source_invalid");
    }
    bool load(std::string& out)override {
        out.clear();
        if(fault_||busy_)return fail("bridge_fault");
        busy_=true;
        try {
            std::string raw;
            if(!backing_.load(raw)||fault_||raw.empty()||raw.size()>GraphShadowConfiguration::maximumStoreBytes)
                return finish(false,"bridge_read_failure");
            class Snapshot final:public ControlStore {
            public:
                explicit Snapshot(const std::string& raw):raw_(raw){}
                bool load(std::string& out)override{out=raw_;return true;}
                bool save(std::string_view)override{return false;}
            private:const std::string& raw_;
            } snapshot(raw);
            auto graph=std::make_unique<GraphShadowConfiguration>(source_.data.controllerId,"source_projection",
                source_.data.adapterId,source_.data.qualificationDigest,snapshot,hash_);
            if(!graph->initialize()||graph->faulted()||fault_)return finish(false,"bridge_graph_invalid");
            const auto& pin=source_.data;
            if(graph->revision()!=pin.revision||graph->mappingRevision()!=pin.mappingRevision
                ||graph->configDigest()!=pin.configDigest||hash_(graph->mappingBytes())!=pin.mappingDigest||fault_)
                return finish(false,"bridge_graph_tuple_conflict");
            if(hash_(source_.reviewJson)!=source_.topology.reviewDigest||fault_)
                return finish(false,"bridge_review_conflict");
            auto checked=heating::graph_review::read(source_.reviewJson,source_.topology.context,hash_);
            if(std::string_view(checked.code)!="source_topology_review_only"||fault_)
                return finish(false,"bridge_review_invalid");
            using namespace heating::graph_test;
            const auto reviewFloor=std::find_if(checked.review.rooms.begin(),checked.review.rooms.end(),
                [](const auto& r){return r.floor;});
            if(reviewFloor==checked.review.rooms.end())return finish(false,"bridge_floor_missing");
            const auto i=static_cast<size_t>(reviewFloor-checked.review.rooms.begin());
            const auto& f=*reviewFloor;
            auto config=parse(graph->configBytes()),mapping=parse(graph->mappingBytes());
            const auto r=cJSON_GetArrayItem(get(config.get(),"rooms"),0);
            const auto a=cJSON_GetArrayItem(get(config.get(),"actuators"),0);
            const auto g=cJSON_GetArrayItem(get(config.get(),"groups"),0);
            const auto bounds=get(g,"supply_limits");
            if(!cJSON_IsNull(get(r,"schedule"))||str(get(a,"profile"))!="binary_valve"
                ||str(get(g,"emitter"))!="floor"
                ||str(get(r,"zone_id"))!=f.zone.data()||str(get(r,"sensor_id"))!="s_"+std::string(f.zone.data())
                ||str(get(a,"actuator_id"))!=f.actuator.data()||str(get(a,"group_id"))!=f.group.data()
                ||integer(get(r,"base_centi_c"),500,3500)!=f.base
                ||integer(get(r,"minimum_target_centi_c"),500,3500)!=f.minimum
                ||integer(get(r,"maximum_target_centi_c"),500,3500)!=f.maximum
                ||integer(get(r,"max_age_ms"),1000,86400000)!=f.maximumAge
                ||str(get(r,"report_evidence"))!=source_.topology.evidence[i]
                ||integer(get(bounds,"minimum_centi_c"),500,9000)!=f.supplyMinimum
                ||integer(get(bounds,"maximum_centi_c"),500,9000)!=f.supplyMaximum)
                return finish(false,"bridge_floor_conflict");
            const auto channel=[&](const std::string& id)->std::string {
                const auto list=get(mapping.get(),"channels");
                for(auto c=list->child;c;c=c->next)
                    if(str(get(c,"channel_id"))==id)return str(get(c,"resource_id"));
                return {};
            };
            if(channel(str(get(r,"sensor_id")))!=f.sensorResource.data()
                ||channel(str(get(a,"output_channel")))!=f.outputResource.data()||fault_)
                return finish(false,"bridge_mapping_conflict");
            const auto allChannels=get(mapping.get(),"channels");
            for(auto c=allChannels->child;c;c=c->next) {
                const auto id=str(get(c,"channel_id"));
                if(id==str(get(r,"sensor_id"))||id==str(get(a,"output_channel")))continue;
                const auto resource=str(get(c,"resource_id"));
                for(const auto& room:checked.review.rooms)
                    if(resource==room.sensorResource.data()||resource==room.outputResource.data())
                        return finish(false,"bridge_resource_overlap");
            }
            if(!projected_->load(out)||projected_->faulted()||fault_) {
                out.clear();return finish(false,"bridge_projection_failure");
            }
            if(fault_){out.clear();return finish(false,"bridge_fault");}
            return finish(true,"bridge_two_target_projection_no_admission");
        }catch(...){out.clear();return finish(false,"bridge_dependency_fault");}
    }
    bool save(std::string_view)override{return fail("bridge_read_only");}
    bool faulted()const{return fault_;}
    const char* status()const{return status_;}
private:
    bool fail(const char* status){fault_=true;status_=status;return false;}
    bool finish(bool ok,const char* status){busy_=false;if(!ok)return fail(status);status_=status;return true;}
    ControlStore& backing_;Hash hash_;GraphFloorControlHandoffSource source_;
    bool fault_=false,busy_=false;
    ReviewSnapshot review_;
    std::unique_ptr<TopologyControlStoreView> projected_;
    const char* status_="bridge_uninitialized";
};
}
