#pragma once
#ifdef OPENTHERMOSTAT_E32V2
// POST /config/backup (behind the web sign-in and CSRF gate of REST::route):
//   {"action":"export"[,"passphrase":".."][,"language":"en"|"nl"]} -> the backup file
//   {"action":"validate","backup":{..}[,"passphrase":".."]}      -> the summary + fingerprint
//   {"action":"apply","backup":{..},"fingerprint":".."[,"passphrase"]} -> applied, restart scheduled
// Logic and validation: control/ConfigBackup.h; the request itself is in its own
// translation unit (ConfigBackupRoute.cpp), so the main object (REST, controller)
// does not grow: its literal pools are already near the l32r reach. The REST
// adapter is in ConfigBackupRest.h.
#include <cJSON.h>
#include <cstddef>
#include <string>
#include <string_view>

namespace heating {
// What the request needs from the controller (implemented below for REST).
class ConfigBackupHost {
public:
    virtual std::string plan() = 0;
    virtual const char* setPlan(const cJSON* root) = 0;
    virtual std::string flow() = 0;
    virtual const char* setFlow(const cJSON* root) = 0;
    virtual void stopBluetooth() = 0;
    virtual bool modernMode() = 0;
    virtual bool boilerClaimed() = 0; // active heat (ActiveHeatGuard::claimsBoiler), a boiler test or settings write
    virtual std::string wifiSsid() = 0;
    virtual const char* firmware() = 0;
protected:
    ~ConfigBackupHost() = default;
};
struct ConfigBackupResponse {
    int code = 503;
    char* text = nullptr; // cJSON_PrintUnformatted (PSRAM)
    ConfigBackupResponse() = default;
    ConfigBackupResponse(const ConfigBackupResponse&) = delete;
    ConfigBackupResponse& operator=(const ConfigBackupResponse&) = delete;
    ~ConfigBackupResponse() { if (text) cJSON_free(text); }
};
void configBackupRequest(const char* body, std::size_t size, ConfigBackupHost& host, ConfigBackupResponse& out);

}
#endif
