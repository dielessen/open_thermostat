#pragma once
#include <cstdint>
#include <string_view>
#include <string>
namespace heating::control {
// Method/origin decisions separate from Arduino networking for direct tests.
inline bool allowedHttpMethod(std::string_view path,std::string_view method) {
    if(path=="/boiler/test/read_identity")return method=="POST";
    if(path=="/boiler/test/read_configuration"||path=="/boiler/test/prepare_zero"||path=="/boiler/test/prepare"||path=="/boiler/test/start"||path=="/boiler/test/keepalive"||path=="/boiler/test/stop"||path=="/boiler/test/close_fault") return method=="POST";
    if(path=="/boiler/settings/write") return method=="POST";
    if(path=="/config/bluetooth/scan"||path=="/config/heating/handover"||path=="/config/heating/takeover-test") return method=="POST";
    if(path=="/logs/clear"||path=="/diagnostics/sessions/end-idle") return method=="POST";
    if(path=="/auth/login"||path=="/auth/logout"||path=="/auth/password") return method=="POST";
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
// DNS rebinding: a page of another site can resolve its own name to the E32
// and then send it same-origin requests. Every request (outside the setup
// access point) must therefore name this device in its Host header: the IP
// the request arrived on, the setup access point's IP, the configured
// hostname, or that hostname with .local or a home-router suffix (the names
// Home Assistant accepts for the E32), each with an optional port that must be
// the listening port. Names compare case-insensitively; one trailing dot is fine.
inline constexpr std::string_view localHostSuffixes[] = {
    ".local", ".fritz.box", ".home.arpa", ".localdomain", ".internal", ".lan", ".home"};
inline bool knownHostHeader(std::string_view host, std::string_view deviceIp, std::string_view apIp,
                            std::string_view hostname, uint16_t port) {
    if(host.empty()||host.size()>255||host.front()=='[') return false;
    if(const auto colon=host.rfind(':');colon!=std::string_view::npos) {
        const auto digits=host.substr(colon+1);
        if(digits.empty()||digits.size()>5) return false;
        uint32_t value=0;
        for(char c:digits) { if(c<'0'||c>'9') return false; value=value*10+uint32_t(c-'0'); }
        if(value!=port) return false;
        host=host.substr(0,colon);
    }
    if(!host.empty()&&host.back()=='.') host.remove_suffix(1);
    if(host.empty()) return false;
    const auto same=[](std::string_view a,std::string_view b) {
        if(a.size()!=b.size()) return false;
        for(size_t i=0;i<a.size();++i) {
            char x=a[i],y=b[i];
            if(x>='A'&&x<='Z') x=char(x-'A'+'a');
            if(y>='A'&&y<='Z') y=char(y-'A'+'a');
            if(x!=y) return false;
        }
        return true;
    };
    for(auto ip:{deviceIp,apIp}) if(!ip.empty()&&ip!="0.0.0.0"&&host==ip) return true;
    if(hostname.empty()) return false;
    if(same(host,hostname)) return true;
    for(auto suffix:localHostSuffixes)
        if(host.size()==hostname.size()+suffix.size()&&same(host.substr(0,hostname.size()),hostname)
           &&same(host.substr(hostname.size()),suffix)) return true;
    return false;
}
inline bool safeStaticPath(std::string_view path) {
    if(path.empty()||path[0]!='/'||path.find("..")!=std::string_view::npos) return false;
    for(char c:path) if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='/'||c=='.'||c=='_'||c=='-')) return false;
    return true;
}
}
