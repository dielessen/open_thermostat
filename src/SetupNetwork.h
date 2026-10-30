#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "DeviceAccess.h"
#include "config.h"
#include "Network.h"
#include "WifiDiscovery.h"
#include "DeviceNetworkSettings.h"
#include "DeviceIdentity.h"
#include <WiFi.h>
#include <DNSServer.h>
#include <nvs.h>
#include <esp_timer.h>
#include <cJSON.h>
#include "control/BoundedJson.h"

namespace heating {
extern bool wifiAPMode;
// These are owned exclusively by the main Arduino loop / its WebServer callbacks.
inline uint64_t setupUntil=0,setupAttemptUntil=0,setupCloseAt=0,setupJoinAt=0;
inline config::WiFiConfig setupCandidate;
inline std::string setupResult="idle";
inline bool setupRebootRequested=false;
// Set by the main loop while a restart must wait: an update is running or a
// new image is not confirmed yet (a restart then rolls it back).
inline bool setupRestartHeld=false;
inline DNSServer setupDns;
inline bool setupDnsActive=false;
inline std::string setupSavedSsid;
inline IPAddress setupCloseIP;
inline constexpr uint64_t setupHandoffDelayMs=8000;
inline bool setupConnectionReady() {
    return setupResult=="connected_saved"&&WiFi.isConnected()&&uint32_t(WiFi.localIP())!=0&&WiFi.SSID().c_str()==setupSavedSsid;
}
inline bool requestSetupBoot() {
    nvs_handle_t h; if(nvs_open("ot_wifi",NVS_READWRITE,&h)!=ESP_OK) return false;
    const bool ok=nvs_set_u8(h,"setup_once",1)==ESP_OK&&nvs_commit(h)==ESP_OK; nvs_close(h);
    if(ok) setupRebootRequested=true; return ok;
}
inline bool consumeSetupBoot() {
    nvs_handle_t h; if(nvs_open("ot_wifi",NVS_READWRITE,&h)!=ESP_OK) return false;
    uint8_t flag=0; const bool found=nvs_get_u8(h,"setup_once",&flag)==ESP_OK&&flag==1;
    bool cleared=true;
    if(found) cleared=nvs_set_u8(h,"setup_once",0)==ESP_OK&&nvs_commit(h)==ESP_OK;
    nvs_close(h); return found&&cleared;
}
inline bool saveSetupWifi(const config::WiFiConfig &cfg) {
    auto root=cJSON_CreateObject();
    cJSON_AddStringToObject(root,"ssid",cfg.ssid.c_str()); cJSON_AddStringToObject(root,"password",cfg.password.c_str());
    char *raw=cJSON_PrintUnformatted(root); cJSON_Delete(root);
    if(!raw) return false;
    nvs_handle_t h; bool ok=false;
    if(nvs_open("ot_wifi",NVS_READWRITE,&h)==ESP_OK) {
        ok=nvs_set_blob(h,"wifi",raw,strlen(raw)+1)==ESP_OK && nvs_commit(h)==ESP_OK;
        nvs_close(h);
    }
    cJSON_free(raw); return ok;
}
inline bool selectSetupWifiInterface() {
    // Preserve broker/room settings; explicit WiFi onboarding must not reboot
    // back into a previously selected Ethernet-only mode.
    const auto raw=readDeviceNetworkSettings();
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> root(heating::control::parseNestedJson(raw));
    if(!root||!cJSON_IsObject(root.get())) return false;
    auto item=cJSON_CreateString("wifi"); if(!item) return false;
    if(cJSON_HasObjectItem(root.get(),"interface_mode")) cJSON_ReplaceItemInObjectCaseSensitive(root.get(),"interface_mode",item);
    else cJSON_AddItemToObject(root.get(),"interface_mode",item);
    std::unique_ptr<char,decltype(&cJSON_free)> bytes(cJSON_PrintUnformatted(root.get()),cJSON_free);
    return bytes&&saveDeviceNetworkSettings(String(bytes.get()));
}
inline bool readSetupWifi(config::WiFiConfig &cfg) {
    nvs_handle_t h;
    if(nvs_open("ot_wifi",NVS_READONLY,&h)!=ESP_OK) return false;
    size_t size=0;
    auto err=nvs_get_blob(h,"wifi",nullptr,&size);
    if(err!=ESP_OK||size<3||size>768) { nvs_close(h); return false; }
    std::string raw(size,'\0'); err=nvs_get_blob(h,"wifi",raw.data(),&size); nvs_close(h);
    if(err!=ESP_OK||raw.back()!='\0') return false;
    if(!heating::control::jsonNestingWithin(raw.c_str(),raw.size(),2)) return false;
    auto root=cJSON_ParseWithLengthOpts(raw.c_str(),raw.size(),nullptr,true);
    if(!root) return false;
    auto ssid=cJSON_GetObjectItemCaseSensitive(root,"ssid"),password=cJSON_GetObjectItemCaseSensitive(root,"password");
    bool ok=cJSON_IsString(ssid)&&cJSON_IsString(password)&&strlen(ssid->valuestring)>0&&strlen(ssid->valuestring)<=32&&strlen(password->valuestring)<=63;
    if(ok) { cfg.ssid=ssid->valuestring; cfg.password=password->valuestring; }
    cJSON_Delete(root); return ok;
}
inline bool startSetupWifi() {
    if(!deviceAccess.ready()||boardEthernetStarted) return false;
    // The NIC part of the MAC (the low 24 bits of getEfuseMac() are the vendor prefix).
    char ssid[32]; snprintf(ssid,sizeof(ssid),"OpenThermostat-%s",macSuffix(ESP.getEfuseMac()).c_str());
    WiFi.persistent(false); WiFi.setAutoReconnect(false);
    // HeatingController already initialized Bluetooth. IDF4.4 aborts if STA
    // modem sleep is disabled alongside BLE. Set the Arduino cached policy
    // before mode() starts the radio / its asynchronous STA_START handler.
    // An unchanged policy returns false in Arduino2.0.17; that is not failure.
    WiFi.setSleep(WIFI_PS_MIN_MODEM);
    if(!WiFi.mode(WIFI_AP_STA)) return false;
    WiFi.disconnect(false,false);
    const IPAddress local(10,10,10,1);
    if(!WiFi.softAPConfig(local,local,IPAddress(255,255,255,0))||
       !WiFi.softAP(ssid,deviceAccess.setupPassword().c_str())) return false;
    wifiAPMode=true; setupUntil=esp_timer_get_time()/1000+15*60*1000;
    setupAttemptUntil=setupJoinAt=setupCloseAt=0; setupResult="ready";
    setupSavedSsid.clear(); setupCloseIP=IPAddress();
    setupDns.stop(); setupDns.setTTL(0);
    setupDnsActive=setupDns.start(53,"*",local);
    Serial.printf("Setup WiFi: %s, browser: http://10.10.10.1/ (2.4 GHz home networks; BLE coexistence MIN_MODEM)\n",ssid);
    Serial.printf("Setup captive portal: %s\n",setupDnsActive?"active":"DNS unavailable; open http://10.10.10.1/ manually");
    return true;
}
inline bool trySetupWifi(const config::WiFiConfig &cfg) {
    if(!wifiAPMode||boardEthernetStarted||setupAttemptUntil||wifiScanRunning()||cfg.ssid.empty()||cfg.ssid.size()>32||cfg.password.size()>63||(!cfg.password.empty()&&cfg.password.size()<8)) return false;
    setupCandidate=cfg; setupResult="connecting"; setupCloseAt=0; setupSavedSsid.clear();
    setupJoinAt=networkNow()+750; setupAttemptUntil=setupJoinAt+30000;
    setupUntil=networkNow()+15*60*1000;
    // Reply to POST before association can move the single radio's AP channel.
    return true;
}
inline bool finishSetupWifi() {
    if(!wifiAPMode||!setupConnectionReady()) return false;
    // Called automatically AFTER the page has received and displayed the real
    // DHCP address. Retried/lost responses must not keep moving the deadline.
    if(!setupCloseAt) { setupCloseAt=networkNow()+setupHandoffDelayMs; setupCloseIP=WiFi.localIP(); }
    return true;
}
// Setup ended without a new network: rejoin the saved one at once. A setup
// boot never started the station, and a failed attempt left its candidate in
// the driver, so the loop's WiFi.reconnect() had nothing (or the wrong network)
// to join and the E32 stayed offline until the 15 min wifiLost restart.
inline void rejoinSavedWifi() {
    const auto network=config::getNetworkConfig();
    if(network.interfaceMode=="ethernet"||boardEthernetStarted) return;
    const auto saved=config::getWiFiConfig();
    if(saved.ssid.empty()) return;
    if(!network.hostname.empty()) WiFi.setHostname(network.hostname.c_str());
    WiFi.begin(saved.ssid.c_str(),saved.password.empty()?nullptr:saved.password.c_str());
    WiFi.setAutoReconnect(true);
    Serial.printf("Setup ended: joining the saved Wi-Fi again
");
}
inline void pollSetupWifi() {
    static bool restartHeldNoted=false;
    if(setupRebootRequested&&!setupRestartHeld) { delay(250); ESP.restart(); return; }
    if(setupRebootRequested&&!restartHeldNoted) { restartHeldNoted=true; Serial.printf("Setup restart deferred until the update or the check of new firmware has finished\n"); }
    const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
    if(wifiAPMode&&setupDnsActive) setupDns.processNextRequest();
    pollWifiScan();
    if(setupJoinAt&&now>=setupJoinAt) {
        setupJoinAt=0; WiFi.setAutoReconnect(false); WiFi.disconnect(false,false);
        WiFi.begin(setupCandidate.ssid.c_str(),setupCandidate.password.c_str());
    }
    if(setupAttemptUntil&&!setupJoinAt) {
        if(WiFi.isConnected() && uint32_t(WiFi.localIP())!=0 && WiFi.SSID().c_str()==setupCandidate.ssid) {
            const bool saved=saveSetupWifi(setupCandidate)&&selectSetupWifiInterface();
            config::WiFiConfig readback;
            const bool verified=saved&&readSetupWifi(readback)&&readback.ssid==setupCandidate.ssid&&readback.password==setupCandidate.password;
            setupResult=verified?"connected_saved":"storage_error";
            setupSavedSsid=verified?setupCandidate.ssid:"";
            setupCandidate={}; setupAttemptUntil=0;
            // Wait for the page to receive the address before automatic finish.
            if(verified) WiFi.setAutoReconnect(true);
        } else if(now>=setupAttemptUntil) {
            setupResult="connection_failed"; setupCandidate={}; setupAttemptUntil=0;
            WiFi.disconnect(false,false);
        }
    }
    if(setupCloseAt&&(!setupConnectionReady()||uint32_t(WiFi.localIP())!=uint32_t(setupCloseIP))) setupCloseAt=0;
    if(wifiAPMode && ((setupCloseAt&&now>=setupCloseAt)||now>=setupUntil)) {
        if(wifiScanRunning()) { esp_wifi_scan_stop(); WiFi.scanDelete(); wifiScanState="failed"; }
        setupJoinAt=setupAttemptUntil=0; setupCandidate={};
        setupDns.stop(); setupDnsActive=false; setupCloseAt=0;
        WiFi.softAPdisconnect(false); WiFi.mode(WIFI_STA); wifiAPMode=false;
        if(setupResult!="connected_saved") { setupResult="setup_expired"; rejoinSavedWifi(); }
    }
    // Explicit physical USB recovery, no GPIO0 button (Ethernet clock pin).
    static std::string command;
    while(Serial.available()) {
        const char c=Serial.read();
        if(c=='\n'||c=='\r') {
            if(command=="setup") requestSetupBoot();
            // Physical access only: restores the factory web password "admin".
            else if(command=="password-reset") Serial.printf("%s\n",deviceAccess.resetPassword()?
                "Web password reset to the default (user admin, password admin). Change it under System.":"Web password reset failed: storage error");
            command.clear();
        }
        else if(command.size()<16) command+=c;
        else command.clear();
    }
}
}
#endif
