// Finite shared-fixture validator + native allocation accounting, NOT a service.
// cJSON and C++ allocation hooks count requested bytes, not libc arena/ESP heap.
#include <cstdlib>
#include <new>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <iostream>
#include <string>
#include <cJSON.h>
#include "control/GraphShadowValidation.h"
#include "ControlTestHash.h"

namespace memory_probe {
struct alignas(std::max_align_t) Header { size_t bytes; bool cjson; };
size_t live=0,peak=0,blocks=0,peakBlocks=0,cjsonLive=0;
bool countCjson=false;
size_t cjsonAttempts=0,failAt=std::numeric_limits<size_t>::max();
void *allocate(size_t n,bool cjson=false) {
    if(n>std::numeric_limits<size_t>::max()-sizeof(Header))return nullptr;
    auto p=static_cast<Header*>(std::malloc(n+sizeof(Header)));
    if(!p)return nullptr;
    p->bytes=n;p->cjson=cjson;if(cjson)++cjsonLive;live+=n;++blocks;peak=std::max(peak,live);peakBlocks=std::max(peakBlocks,blocks);
    return p+1;
}
void release(void *raw) {
    if(!raw)return;
    auto p=static_cast<Header*>(raw)-1;if(p->cjson)--cjsonLive;live-=p->bytes;--blocks;std::free(p);
}
void *cjsonAllocate(size_t n) {
    if(countCjson&&cjsonAttempts++==failAt)return nullptr;
    return allocate(n,true);
}
}
void *operator new(size_t n) {if(auto p=memory_probe::allocate(n))return p;throw std::bad_alloc();}
void operator delete(void *p) noexcept {memory_probe::release(p);}
void operator delete(void *p,size_t) noexcept {memory_probe::release(p);}
void *operator new[](size_t n){return ::operator new(n);}
void operator delete[](void *p) noexcept {::operator delete(p);}
void operator delete[](void *p,size_t) noexcept {::operator delete(p);}
using namespace heating::graph_test;
int main() {
    cJSON_Hooks hooks{memory_probe::cjsonAllocate,memory_probe::release};cJSON_InitHooks(&hooks);
    controlTestHash("warmup");
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>40000)return 2;
        Json f(cJSON_Parse(line.c_str()),cJSON_Delete);if(!f)return 3;
        auto cx=get(f.get(),"context");if(!cx)return 4;
        const auto num=[cx](const char *key){return uint32_t(integer(get(cx,key),0,UINT32_MAX));};
        Context context{str(get(cx,"controller_id")),str(get(cx,"boot_id")),str(get(cx,"adapter_id")),
            str(get(cx,"adapter_session_id")),str(get(cx,"grant_id")),num("epoch"),num("grant_sequence"),
            num("current_revision"),num("mapping_revision"),str(get(cx,"mapping_digest")),str(get(cx,"qualification_digest"))};
        const std::string_view raw=get(f.get(),"raw")->valuestring;
        const std::string_view mapping=get(f.get(),"mapping_raw")->valuestring;
        if(cJSON_IsTrue(get(f.get(),"fault_sweep"))) {
            // Same exact shared raw/config/mapping/anchor; only allocator hook changes.
            const auto rawHash=controlTestHash(raw),mappingHash=controlTestHash(mapping);
            const Context saved=context;
            const auto baseline=memory_probe::cjsonLive;
            memory_probe::countCjson=true;memory_probe::cjsonAttempts=0;
            memory_probe::failAt=std::numeric_limits<size_t>::max();
            auto initial=validate(raw,mapping,context,controlTestHash);
            const auto attempts=memory_probe::cjsonAttempts;
            memory_probe::countCjson=false;
            if(initial.code!="valid_shadow_candidate"||memory_probe::cjsonLive!=baseline)return 5;
            size_t leakedRuns=0,leakedBlocks=0,validOnFault=0,untriggered=0,badFlags=0;
            std::array<std::string,4> referenceCodes;
            const std::array<size_t,4> referenceSites{416,472,500,526};
            for(size_t index=0;index<attempts;++index) {
                const auto liveBefore=memory_probe::cjsonLive;
                memory_probe::countCjson=true;memory_probe::cjsonAttempts=0;memory_probe::failAt=index;
                auto failed=validate(raw,mapping,context,controlTestHash);
                const auto reached=memory_probe::cjsonAttempts>index;
                memory_probe::countCjson=false;
                if(!reached)++untriggered;
                if(failed.code=="valid_shadow_candidate")++validOnFault;
                if(failed.candidate.actuatorOutputEnabled||failed.candidate.boilerOutputEnabled)++badFlags;
                if(memory_probe::cjsonLive!=liveBefore) {
                    ++leakedRuns;
                    if(memory_probe::cjsonLive>liveBefore)leakedBlocks+=memory_probe::cjsonLive-liveBefore;
                }
                for(size_t i=0;i<referenceSites.size();++i)if(index==referenceSites[i])referenceCodes[i]=failed.code;
            }
            memory_probe::failAt=std::numeric_limits<size_t>::max();
            const bool contextIntact=saved.controllerId==context.controllerId&&saved.bootId==context.bootId&&
                saved.adapterId==context.adapterId&&saved.sessionId==context.sessionId&&saved.grantId==context.grantId&&
                saved.epoch==context.epoch&&saved.grantSequence==context.grantSequence&&
                saved.currentRevision==context.currentRevision&&saved.mappingRevision==context.mappingRevision&&
                saved.mappingDigest==context.mappingDigest&&saved.qualificationDigest==context.qualificationDigest;
            Json summary(cJSON_CreateObject(),cJSON_Delete);
            cJSON_AddBoolToObject(summary.get(),"fault_sweep",true);
            cJSON_AddNumberToObject(summary.get(),"allocation_positions",attempts);
            cJSON_AddNumberToObject(summary.get(),"leaked_runs",leakedRuns);
            cJSON_AddNumberToObject(summary.get(),"leaked_cjson_blocks",leakedBlocks);
            cJSON_AddNumberToObject(summary.get(),"valid_on_fault",validOnFault);
            cJSON_AddNumberToObject(summary.get(),"untriggered",untriggered);
            cJSON_AddNumberToObject(summary.get(),"bad_output_flags",badFlags);
            cJSON_AddBoolToObject(summary.get(),"inputs_intact",rawHash==controlTestHash(raw)&&mappingHash==controlTestHash(mapping)&&contextIntact);
            auto sites=cJSON_AddArrayToObject(summary.get(),"original_leak_sites");
            for(size_t i=0;i<referenceSites.size();++i) {
                auto site=cJSON_CreateObject();cJSON_AddItemToArray(sites,site);
                cJSON_AddNumberToObject(site,"index",referenceSites[i]);
                cJSON_AddStringToObject(site,"code",referenceCodes[i].c_str());
            }
            // Ensure a failure does not poison subsequent successful validation.
            auto recovered=validate(raw,mapping,context,controlTestHash);
            cJSON_AddStringToObject(summary.get(),"recovery_code",recovered.code.c_str());
            std::cout<<print(summary.get())<<std::endl;
            continue;
        }
        size_t contextHeap=0;
        for(auto v:{&context.controllerId,&context.bootId,&context.adapterId,&context.sessionId,
                    &context.grantId,&context.mappingDigest,&context.qualificationDigest}) {
            const auto ptr=reinterpret_cast<uintptr_t>(v->data()),start=reinterpret_cast<uintptr_t>(v);
            if(ptr<start||ptr>=start+sizeof(std::string))contextHeap+=v->capacity()+1;
        }
        auto before=memory_probe::live;auto beforeBlocks=memory_probe::blocks;
        memory_probe::peak=before;memory_probe::peakBlocks=beforeBlocks;
        auto result=validate(raw,mapping,context,controlTestHash);
        auto peak=memory_probe::peak-before;
        auto peakBlocks=memory_probe::peakBlocks-beforeBlocks;
        Json out(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddStringToObject(out.get(),"name",str(get(f.get(),"name")).c_str());
        cJSON_AddStringToObject(out.get(),"code",result.code.c_str());
        cJSON_AddNumberToObject(out.get(),"candidate_bytes",sizeof(GraphShadowCandidate));
        cJSON_AddNumberToObject(out.get(),"transition_bytes",sizeof(Transition));
        cJSON_AddNumberToObject(out.get(),"context_bytes",sizeof(Context));
        cJSON_AddNumberToObject(out.get(),"cjson_node_bytes",sizeof(cJSON));
        cJSON_AddNumberToObject(out.get(),"allocation_header_bytes",sizeof(memory_probe::Header));
        cJSON_AddNumberToObject(out.get(),"incremental_peak_requested_bytes",peak);
        cJSON_AddNumberToObject(out.get(),"incremental_peak_blocks",peakBlocks);
        cJSON_AddNumberToObject(out.get(),"caller_raw_bytes",raw.size()+mapping.size()+2);
        cJSON_AddNumberToObject(out.get(),"caller_context_heap_bytes",contextHeap);
        cJSON_AddNumberToObject(out.get(),"revision",result.candidate.revision);
        cJSON_AddNumberToObject(out.get(),"mapping_revision",result.candidate.mappingRevision);
        cJSON_AddNumberToObject(out.get(),"transitions",result.candidate.transitionCount);
        cJSON_AddNumberToObject(out.get(),"streams",result.candidate.streamCount);
        cJSON_AddBoolToObject(out.get(),"actuator_output_enabled",result.candidate.actuatorOutputEnabled);
        cJSON_AddBoolToObject(out.get(),"boiler_output_enabled",result.candidate.boilerOutputEnabled);
        std::cout<<print(out.get())<<std::endl;
    }
}
