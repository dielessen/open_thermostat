#pragma once
#include <string_view>
#include <string>
namespace heating::control {
// Method/origin decisions separate from Arduino networking for direct tests.
inline bool allowedHttpMethod(std::string_view path,std::string_view method) {
    if(path=="/boiler/test/read_identity")return method=="POST";
    if(path=="/boiler/test/read_configuration"||path=="/boiler/test/prepare_zero"||path=="/boiler/test/prepare"||path=="/boiler/test/start"||path=="/boiler/test/keepalive"||path=="/boiler/test/stop"||path=="/boiler/test/close_fault") return method=="POST";
    if(path=="/boiler/settings/write") return method=="POST";
    if(path=="/config/bluetooth/scan"||path=="/config/heating/handover") return method=="POST";
    if(path=="/logs/clear") return method=="POST";
    if(path=="/auth/login"||path=="/auth/logout") return method=="POST";
    if(path=="/updates/check"||path=="/updates/install"||path=="/updates/reboot"||path=="/updates/rollback")return method=="POST";
    if(path=="/setup/scan") return method=="GET"||method=="POST";
    if(path=="/config/reboot"||path=="/setup/reenter"||path=="/setup/network"||path=="/setup/finish"||path=="/ota"||path=="/otafs") return method=="POST";
    if(path=="/config/temporary"||path=="/hardware/test/gpio") return method=="POST"||method=="DELETE";
    if(path.substr(0,17)=="/config/programs/") return method=="GET"||method=="POST"||method=="DELETE";
    if(path.substr(0,8)=="/config/") return method=="GET"||method=="POST";
    return method=="GET";
}
inline bool boilerTestMutationBlocked(std::string_view path, bool active) {
    return active && path!="/boiler/test/read_configuration" && path!="/boiler/test/read_identity" && path!="/auth/logout" && path!="/boiler/test/prepare_zero" && path!="/boiler/test/prepare" && path!="/boiler/test/start"
        && path!="/boiler/test/keepalive" && path!="/boiler/test/stop" && path!="/boiler/test/close_fault";
}
inline bool boilerSettingsMutationBlocked(std::string_view path,bool active){
    return active&&path!="/boiler/settings/write"&&path!="/auth/logout"
        &&path!="/boiler/test/stop"&&path!="/boiler/test/close_fault";
}
inline bool legacyControlWrite(std::string_view path,std::string_view method) {
    return method!="GET" && (path=="/config/temporary"||path=="/config/rooms"||path=="/config/program/current"||
        path=="/config/boiler"||path=="/config/hardware"||path.substr(0,17)=="/config/programs/");
}
inline bool sameOrigin(std::string_view origin,std::string_view host,std::string_view fetchSite) {
    if(fetchSite=="cross-site") return false;
    if(origin.empty()) return true;
    return origin==std::string("http://")+std::string(host);
}
inline bool safeStaticPath(std::string_view path) {
    if(path.empty()||path[0]!='/'||path.find("..")!=std::string_view::npos) return false;
    for(char c:path) if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='/'||c=='.'||c=='_'||c=='-')) return false;
    return true;
}
}
