#pragma once
#include <string_view>
#include <string>
namespace heating::control {
enum class PortalAccess { Authenticated, Redirect, Setup };
inline bool captiveProbe(std::string_view path) {
    for(auto probe:{"/generate_204","/gen_204","/hotspot-detect.html","/library/test/success.html",
                   "/success.html","/ncsi.txt","/connecttest.txt","/redirect","/fwlink","/canonical.html"})
        if(path==probe) return true;
    return false;
}
// A spoofed Host header alone can NEVER enable the AP-only exception. The
// caller must verify the socket's local interface address, not the remote IP.
inline PortalAccess portalAccess(bool active,bool apInterface,std::string_view host,
                                 std::string_view canonicalHost,std::string_view path,std::string_view method) {
    if(!active||!apInterface) return PortalAccess::Authenticated;
    if(method=="GET"&&(path=="/"||captiveProbe(path)||host!=canonicalHost)) return PortalAccess::Redirect;
    if(host!=canonicalHost) return PortalAccess::Authenticated;
    if(method=="GET"&&(path=="/setup"||path=="/setup.html"||path=="/setup.js"||path=="/ui-language.js"||path=="/ui-messages.js"||path=="/setup/status"||path=="/setup/scan")) return PortalAccess::Setup;
    if(method=="POST"&&(path=="/setup/scan"||path=="/setup/network"||path=="/setup/finish")) return PortalAccess::Setup;
    return PortalAccess::Authenticated;
}
}
