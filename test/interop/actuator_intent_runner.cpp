// Finite stdin/stdout protocol peer for native HA interoperability; no network.
#include "control/ActuatorIntent.h"
#include <iostream>
#include <cmath>
using heating::control::ActuatorIntent;
int main(int argc,char** argv) {
    ActuatorIntent::Scope scope{"ctrl","boot","ha","session",std::string(64,'a'),"valve",1,4};
    std::string grant;
    if(!std::getline(std::cin,grant))return 2;
    // Test-only scope import for the actual native-worker session fixture.
    // Production scope must come from the local controller, never the broker.
    if(argc==2&&std::string_view(argv[1])=="--fixture-scope") {
        auto root=heating::control::parseControlJson(grant);
        if(!root)return 7;
        auto text=[&](const char* key) {
            const auto value=cJSON_GetObjectItemCaseSensitive(root.get(),key);
            return cJSON_IsString(value)?std::string(value->valuestring):std::string{};
        };
        auto number=[&](const char* key) -> uint32_t {
            const auto value=cJSON_GetObjectItemCaseSensitive(root.get(),key);
            if(!cJSON_IsNumber(value)||!std::isfinite(value->valuedouble)
                    ||value->valuedouble<1||value->valuedouble>UINT32_MAX
                    ||value->valuedouble!=static_cast<uint32_t>(value->valuedouble))return 0;
            return static_cast<uint32_t>(value->valuedouble);
        };
        scope={text("controller_id"),text("boot_id"),text("adapter_id"),
            text("adapter_session_id"),text("config_digest"),text("binding_id"),
            number("epoch"),number("config_revision")};
    } else if(argc!=1)return 8;
    ActuatorIntent owner(scope,[]{return true;});
    if(!owner.accept(grant,scope,1000,1000,16000))return 3;
    auto raw=owner.command(2100,scope,1001,16000);
    if(raw.empty())return 4;
    std::cout<<raw<<'\n';
    // A repeated grant cannot manufacture another action or any readiness.
    if(owner.accept(grant,scope,1002,1002,16002))return 5;
    if(!owner.command(2200,scope,1002,16002).empty())return 6;
    return 0;
}
