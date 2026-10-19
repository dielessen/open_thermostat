#pragma once
namespace heating::control {
struct NetworkBootPlan { bool setupAp,wifi,ethernet; };
constexpr NetworkBootPlan networkBootPlan(bool ethernetConfigured,bool wifiCredentials,bool setupRequested) {
    if(setupRequested) return {true,true,false};
    if(ethernetConfigured) return {false,false,true};
    return {!wifiCredentials,true,false};
}
}
