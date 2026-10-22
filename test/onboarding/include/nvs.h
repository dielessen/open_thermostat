#pragma once
#include <map>
#include <string>
#include <vector>
#include <cstring>
using nvs_handle_t=int; using esp_err_t=int;
constexpr int ESP_OK=0,ESP_ERR_NVS_NOT_FOUND=1,NVS_READWRITE=1,NVS_READONLY=0;
namespace testNvs {
using Values=std::map<std::string,std::vector<unsigned char>>;
inline std::map<std::string,Values> committed;
struct Handle {std::string name;Values staged;};
inline std::map<int,Handle> handles;
inline std::string failCommit,corruptRead; inline int next=1;
}
inline int nvs_open(const char* name,int mode,nvs_handle_t* h){
 if(mode==NVS_READONLY&&!testNvs::committed.count(name))return ESP_ERR_NVS_NOT_FOUND;
 *h=testNvs::next++;testNvs::handles[*h]={name,{}};return ESP_OK;
}
inline void nvs_close(int h){testNvs::handles.erase(h);}
inline int nvs_set_blob(int h,const char* key,const void* data,size_t size){auto p=(const unsigned char*)data;testNvs::handles.at(h).staged[key]={p,p+size};return ESP_OK;}
inline int nvs_commit(int h){auto &x=testNvs::handles.at(h);if(x.name==testNvs::failCommit)return 2;for(auto &[k,v]:x.staged)testNvs::committed[x.name][k]=v;return ESP_OK;}
inline int nvs_get_blob(int h,const char* key,void* data,size_t* size){
 auto name=testNvs::handles.at(h).name;
 auto space=testNvs::committed.find(name);if(space==testNvs::committed.end())return ESP_ERR_NVS_NOT_FOUND;
 auto found=space->second.find(key);if(found==space->second.end())return ESP_ERR_NVS_NOT_FOUND;
 if(!data){*size=found->second.size();return ESP_OK;}
 if(*size<found->second.size())return 2;
 std::memcpy(data,found->second.data(),found->second.size());*size=found->second.size();
 if(name==testNvs::corruptRead&&*size>2)((char*)data)[1]='!';return ESP_OK;
}
inline int nvs_set_u8(int h,const char* key,uint8_t value){return nvs_set_blob(h,key,&value,1);}
inline int nvs_get_u8(int h,const char* key,uint8_t* value){size_t n=1;return nvs_get_blob(h,key,value,&n);}
