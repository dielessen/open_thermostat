#pragma once
#include "control/BoundedJson.h"
#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>
namespace heating::update {
inline constexpr char repository[]="https://github.com/dielessen/open_thermostat";
inline constexpr char releaseApi[]="https://api.github.com/repos/dielessen/open_thermostat/releases?per_page=2";
inline constexpr uint32_t maxImageBytes=3670016;
inline bool mutationBlocked(std::string_view path,bool working,bool staged,bool pending) {
    if(path=="/ota"||path=="/otafs")return working||staged||pending;
    if(path=="/config/reboot"||path=="/setup/reenter")return working;
    return false;
}
inline bool hex(std::string_view value,size_t size) {
    return value.size()==size&&std::all_of(value.begin(),value.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
inline bool validTag(std::string_view value) {
    return value.size()>1&&value.size()<48&&value.front()=='v'&&value[1]>='0'&&value[1]<='9'&&
      std::all_of(value.begin(),value.end(),[](char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='-';});
}
inline bool allowedDownloadUrl(std::string_view url) {
    for(auto prefix:{"https://api.github.com/","https://github.com/","https://release-assets.githubusercontent.com/","https://objects.githubusercontent.com/"})
        if(url.substr(0,std::strlen(prefix))==prefix&&url.size()<=4096&&url.find_first_of("\r\n\\")==std::string_view::npos) return true;
    return false;
}
inline std::string assetUrl(const std::string &tag,const char *name) {
    return validTag(tag)?std::string(repository)+"/releases/download/"+tag+"/"+name:"";
}
inline const cJSON *field(const cJSON *root,const char *key){return cJSON_GetObjectItemCaseSensitive(root,key);}
inline std::string string(const cJSON *root,const char *key){auto p=field(root,key);return cJSON_IsString(p)?p->valuestring:"";}
struct Manifest {
    std::string tag,source,webSha,sha256; uint32_t size=0;
    std::string marker() const {return "OT_E32V2_OTA_V1:"+tag+":"+source+":"+webSha+":END";}
};
inline bool parseManifest(std::string_view bytes,std::string_view selected,Manifest &out) {
    auto doc=control::parseControlJson(bytes,true);
    if(!doc||!cJSON_IsObject(doc.get())||cJSON_GetArraySize(doc.get())!=11) return false;
    const auto root=doc.get();
    auto integer=[&](const char *key,uint32_t expected) {auto p=field(root,key);return cJSON_IsNumber(p)&&p->valuedouble==expected;};
    if(!integer("update_schema",1)||!integer("settings_schema",1)||string(root,"board")!="bbqkees_e32v2"||
       string(root,"layout")!="e32v2-dual-app-spiffs-v1"||string(root,"ui")!="embedded"||string(root,"asset")!="firmware.bin") return false;
    Manifest m;m.tag=string(root,"version");m.source=string(root,"source_commit");m.webSha=string(root,"web_sha256");m.sha256=string(root,"sha256");
    auto size=field(root,"size");
    if(!validTag(m.tag)||m.tag!=selected||!hex(m.source,40)||!hex(m.webSha,64)||!hex(m.sha256,64)||!cJSON_IsNumber(size)||
       size->valuedouble<1024||size->valuedouble>maxImageBytes||size->valuedouble!=uint32_t(size->valuedouble)) return false;
    m.size=uint32_t(size->valuedouble);out=std::move(m);return true;
}
// Bound the untrusted public GitHub response BEFORE cJSON recursion/allocation.
inline control::ControlJson releaseJson(std::string_view bytes) {
    const auto reject=[] {return control::ControlJson(nullptr,cJSON_Delete);};
    if(bytes.empty()||bytes.size()>24576||bytes.find("\\u0000")!=std::string_view::npos) return reject();
    bool quoted=false,escaped=false;unsigned depth=0,nodes=0;
    for(unsigned char c:bytes) {
        if(quoted) {if(escaped)escaped=false;else if(c=='\\')escaped=true;else if(c=='"')quoted=false;else if(c<32)return reject();continue;}
        if(c=='"'){quoted=true;if(++nodes>1024)return reject();}
        else if(c=='{'||c=='['){if(++depth>16||++nodes>1024)return reject();}
        else if(c=='}'||c==']'){if(!depth)return reject();--depth;}
        else if(c==','||c==':'){if(++nodes>1024)return reject();}
    }
    if(quoted||escaped||depth)return reject();
    const std::string raw(bytes);
    return control::ControlJson(cJSON_ParseWithLengthOpts(raw.c_str(),raw.size()+1,nullptr,true),cJSON_Delete);
}
}
