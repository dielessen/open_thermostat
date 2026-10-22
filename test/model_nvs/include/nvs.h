#pragma once
// SDK I/O fault boundary ONLY. Production NvsModelStore header is not replaced.
// No flash/GC/atomicity/physical persistence claim from this in-memory fixture.
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
#include <cstring>
#include <functional>
using esp_err_t=int;
using nvs_handle_t=uint32_t;
constexpr int ESP_OK=0,ESP_ERR_NVS_NOT_FOUND=1,ESP_FAIL=2,NVS_READONLY=0,NVS_READWRITE=1;
struct nvs_stats_t {size_t used_entries=0,free_entries=0,total_entries=0,namespace_count=0;};
namespace modelNvsFixture {
using Values=std::map<std::string,std::vector<unsigned char>>;
struct Handle {std::string name;Values pending;};
inline std::map<std::string,Values> data;
inline std::map<nvs_handle_t,Handle> handles;
inline unsigned next=1,opens=0,closes=0,lengths=0,copies=0,sets=0,commits=0,statsCalls=0;
inline bool badOpen=false,badLength=false,badRead=false,badSet=false,badCommit=false,
 commitDespiteError=false,corruptReadback=false,missingPartition=false,badStats=false,growAfterLength=false;
inline bool overrideReportedSize=false;
inline size_t reportedSize=0,partitionBytes=20480;
inline nvs_stats_t stats{20,610,630,1};
inline std::function<void()> onOpen,onLength,onSet,onStats;
inline void reset(){
 data.clear();handles.clear();next=1;opens=closes=lengths=copies=sets=commits=statsCalls=0;
 badOpen=badLength=badRead=badSet=badCommit=commitDespiteError=corruptReadback=missingPartition=badStats=growAfterLength=false;
 overrideReportedSize=false;reportedSize=0;partitionBytes=20480;stats={20,610,630,1};
 onOpen=onLength=onSet=onStats={};
}
}
inline esp_err_t nvs_open(const char* name,int mode,nvs_handle_t* handle){
 using namespace modelNvsFixture;++opens;if(badOpen)return ESP_FAIL;
 if(onOpen)onOpen();
 if(mode==NVS_READONLY&&!data.count(name))return ESP_ERR_NVS_NOT_FOUND;
 if(mode==NVS_READWRITE&&!data.count(name)){data[name];++stats.used_entries;--stats.free_entries;}
 *handle=next++;handles[*handle]={name,{}};return ESP_OK;
}
inline void nvs_close(nvs_handle_t h){using namespace modelNvsFixture;++closes;handles.erase(h);}
inline esp_err_t nvs_get_blob(nvs_handle_t h,const char* key,void* out,size_t* size){
 using namespace modelNvsFixture;
 const auto ns=handles.at(h).name;
 auto item=data[ns].find(key);
 if(!out){++lengths;if(onLength)onLength();if(badLength)return ESP_FAIL;}
 else {++copies;if(badRead)return ESP_FAIL;}
 if(item==data[ns].end())return ESP_ERR_NVS_NOT_FOUND;
 if(!out){*size=overrideReportedSize?reportedSize:item->second.size();return ESP_OK;}
 const auto actual=item->second.size()+(growAfterLength?1:0);
 if(*size<actual){*size=actual;return ESP_FAIL;}
 std::memcpy(out,item->second.data(),item->second.size());*size=item->second.size();
 if(corruptReadback&&commits&&*size)static_cast<unsigned char*>(out)[0]^=1;
 return ESP_OK;
}
inline esp_err_t nvs_set_blob(nvs_handle_t h,const char* key,const void* in,size_t size){
 using namespace modelNvsFixture;++sets;if(onSet)onSet();if(badSet)return ESP_FAIL;
 const auto* p=static_cast<const unsigned char*>(in);handles.at(h).pending[key]={p,p+size};return ESP_OK;
}
inline esp_err_t nvs_commit(nvs_handle_t h){
 using namespace modelNvsFixture;++commits;
 if(!badCommit||commitDespiteError)for(auto& [key,value]:handles.at(h).pending)data[handles.at(h).name][key]=value;
 return badCommit?ESP_FAIL:ESP_OK;
}
inline esp_err_t nvs_get_stats(const char*,nvs_stats_t* out){
 using namespace modelNvsFixture;++statsCalls;if(onStats)onStats();if(badStats)return ESP_FAIL;*out=stats;return ESP_OK;
}
