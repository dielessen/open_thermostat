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
#include "control/GraphWireTuple.h"
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
    controlTestHash("warmup");std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>40000)return 2;
        Json input(cJSON_Parse(line.c_str()),cJSON_Delete);if(!input)return 3;
        auto cx=get(input.get(),"context");if(!cx)return 4;
        const auto num=[cx](const char *key){return uint32_t(integer(get(cx,key),0,UINT32_MAX));};
        Context context{str(get(cx,"controller_id")),str(get(cx,"boot_id")),str(get(cx,"adapter_id")),
            str(get(cx,"adapter_session_id")),str(get(cx,"grant_id")),num("epoch"),num("grant_sequence"),
            num("current_revision"),num("mapping_revision"),str(get(cx,"mapping_digest")),str(get(cx,"qualification_digest"))};
        const auto raw=str(get(input.get(),"raw")),mapping=str(get(input.get(),"mapping_raw"));
        const auto wire=heating::control::encodeGraphTuple(raw,mapping,context,controlTestHash);
        Json reply(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddStringToObject(reply.get(),"wire",wire.c_str());
        for(const char* op:{"encode","decode"}) {
            const auto action=[&]{
                if(std::strcmp(op,"encode")==0) {
                    auto actual=heating::control::encodeGraphTuple(raw,mapping,context,controlTestHash);
                    need(actual==wire,"roundtrip");
                }else {
                    auto parts=heating::control::decodeGraphTuple(wire,controlTestHash);
                    need(parts.message==raw&&parts.mapping==mapping,"roundtrip");
                }
            };
            const auto baseLive=memory_probe::live,baseBlocks=memory_probe::blocks;
            memory_probe::peak=baseLive;memory_probe::peakBlocks=baseBlocks;
            memory_probe::countCjson=true;memory_probe::cjsonAttempts=0;
            memory_probe::failAt=std::numeric_limits<size_t>::max();action();
            memory_probe::countCjson=false;
            const auto attempts=memory_probe::cjsonAttempts,peak=memory_probe::peak-baseLive;
            const auto peakBlocks=memory_probe::peakBlocks-baseBlocks;
            need(memory_probe::live==baseLive,"native_leak");
            size_t leaks=0,accepted=0,missed=0;
            for(size_t i=0;i<attempts;++i) {
                const auto before=memory_probe::live,blocks=memory_probe::blocks;
                memory_probe::countCjson=true;memory_probe::cjsonAttempts=0;memory_probe::failAt=i;
                try{action();++accepted;}catch(const Failure&){}catch(const std::bad_alloc&){}
                if(memory_probe::cjsonAttempts<=i)++missed;
                memory_probe::countCjson=false;memory_probe::failAt=std::numeric_limits<size_t>::max();
                if(memory_probe::live!=before||memory_probe::blocks!=blocks)++leaks;
            }
            action();
            auto out=cJSON_AddObjectToObject(reply.get(),op);
            cJSON_AddNumberToObject(out,"allocation_positions",attempts);
            cJSON_AddNumberToObject(out,"incremental_peak_requested_bytes",peak);
            cJSON_AddNumberToObject(out,"incremental_peak_blocks",peakBlocks);
            cJSON_AddNumberToObject(out,"leaked_runs",leaks);
            cJSON_AddNumberToObject(out,"accepted_on_allocation_failure",accepted);
            cJSON_AddNumberToObject(out,"untriggered",missed);
            if(leaks||accepted||missed)return 7;
        }
        cJSON_AddNumberToObject(reply.get(),"wire_bytes",wire.size());
        cJSON_AddNumberToObject(reply.get(),"inner_bytes",raw.size());
        cJSON_AddNumberToObject(reply.get(),"mapping_bytes",mapping.size());
        std::cout<<print(reply.get())<<std::endl;
    }
}
