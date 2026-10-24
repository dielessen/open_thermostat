// Finite stdin/stdout protocol peer for native HA interoperability; no network.
#include "control/ActuatorIntent.h"
#include <iostream>
using heating::control::ActuatorIntent;
int main() {
    ActuatorIntent::Scope scope{"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};
    ActuatorIntent owner(scope,[]{return true;});
    std::string grant;
    if(!std::getline(std::cin,grant))return 2;
    if(!owner.accept(grant,scope,1000,1000,16000))return 3;
    auto raw=owner.command(2100,scope,1001,16000);
    if(raw.empty())return 4;
    std::cout<<raw<<'\n';
    // A repeated grant cannot manufacture another action or any readiness.
    if(owner.accept(grant,scope,1002,1002,16002))return 5;
    if(!owner.command(2200,scope,1002,16002).empty())return 6;
    return 0;
}
