#pragma once
#include "Arduino.h"
#include <cassert>
struct DNSServer {
    bool active=false,startOk=true;
    int polls=0,starts=0,stops=0; uint32_t ttl=99; uint16_t port=0;
    std::string domain; IPAddress resolved;
    void setTTL(uint32_t t){ttl=t;}
    bool start(uint16_t p,const String &d,const IPAddress &ip){++starts;port=p;domain=d;resolved=ip;return active=startOk;}
    void stop(){++stops;active=false;}
    void processNextRequest(){assert(active);++polls;}
};
