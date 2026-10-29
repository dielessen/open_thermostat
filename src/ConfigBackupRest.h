#pragma once
#ifdef OPENTHERMOSTAT_E32V2
// REST adapter of POST /config/backup (ConfigBackupRoute.h): the controller
// behind ConfigBackupHost, and the reply. Included by REST.h only.
#include "ConfigBackupRoute.h"
#include "EmbeddedWebAssets.h"
#include "SetupNetwork.h"
#include <string_view>

namespace heating {
template<class Server, class Controller>
void configBackupRoute(Server& server, Controller& controller) {
    struct Host final : ConfigBackupHost {
        Controller& c;
        explicit Host(Controller& controller) : c(controller) {}
        std::string plan() override { return c.heatingPlanJson(); }
        const char* setPlan(const cJSON* root) override { return c.setHeatingPlan(root); }
        std::string flow() override { return c.flowSettingsJson(); }
        const char* setFlow(const cJSON* root) override { return c.setFlowSettings(root); }
        void stopBluetooth() override { c.stopManagedBle(); }
        bool modernMode() override { return c.modernMode(); }
        bool boilerClaimed() override { return c.claimsBoiler() || c.boilerTestActive() || c.boilerSettingsActive(); }
        std::string wifiSsid() override {
            config::WiFiConfig wifi;
            const bool saved = readSetupWifi(wifi);
            for (auto& ch : wifi.password) ch = 0;
            return saved ? wifi.ssid : std::string();
        }
        const char* firmware() override { return embedded::version; }
    } host(controller);
    const auto body = server.arg("plain");
    ConfigBackupResponse reply;
    configBackupRequest(body.c_str(), body.length(), host, reply);
    server.sendHeader("Cache-Control", "no-store");
    if (!reply.text) {
        server.send(reply.code == 201 ? 201 : 503, "application/json", reply.code == 201 ? "{\"applied\":true}" : "{\"error\":\"out_of_memory\"}");
        return;
    }
    server.sendView(reply.code, "application/json", std::string_view(reply.text));
}
}
#endif
