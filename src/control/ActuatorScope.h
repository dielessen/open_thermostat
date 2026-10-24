#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>

namespace heating::control {
// Shared LOCAL session/config/binding identity; not physical authorization.
struct ActuatorScope {
    std::string controller,boot,adapter,session,digest,binding;
    uint32_t epoch=0,revision=0;
    bool valid()const {
        return validId(controller)&&validId(boot)&&validId(adapter)&&validId(session)&&validHex(digest)
            &&validId(binding)&&epoch&&revision;
    }
    bool operator==(const ActuatorScope& o)const {
        return controller==o.controller&&boot==o.boot&&adapter==o.adapter&&session==o.session
            &&digest==o.digest&&binding==o.binding&&epoch==o.epoch&&revision==o.revision;
    }
    static bool validId(std::string_view value) {
        if(value.empty()||value.size()>32)return false;
        for(unsigned char c:value)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||
                (c>='0'&&c<='9')||c=='_'||c=='-'))return false;
        return true;
    }
    static bool validHex(std::string_view value) {
        if(value.size()!=64)return false;
        for(char c:value)if(!((c>='a'&&c<='f')||(c>='0'&&c<='9')))return false;
        return true;
    }
};

struct ActuatorSessionContext {
    ActuatorScope scope;
    uint64_t leaseUntil=0,grantUntil=0;
    uint64_t validUntil()const{return std::min(leaseUntil,grantUntil);}
    // A live session/config cannot qualify a physical installation.
    bool authorizesActuation()const{return false;}
};
}
