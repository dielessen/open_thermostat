#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "DeviceAccess.h"
#include "config.h"
#include "Network.h"
#include <WiFi.h>
#include <nvs.h>
#include <esp_timer.h>
#include <cJSON.h>

namespace heating {
extern bool wifiAPMode;
// These are owned exclusively by the main Arduino loop / its WebServer callbacks.
inline uint64_t setupUntil=0,setupAttemptUntil=0,setupCloseAt=0;
inline config::WiFiConfig setupCandidate;
inline std::string setupResult="idle";
inline bool setupRebootRequested=false;
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
inline bool readSetupWifi(config::WiFiConfig &cfg) {
    nvs_handle_t h;
    if(nvs_open("ot_wifi",NVS_READONLY,&h)!=ESP_OK) return false;
    size_t size=0;
    auto err=nvs_get_blob(h,"wifi",nullptr,&size);
    if(err!=ESP_OK||size<3||size>768) { nvs_close(h); return false; }
    std::string raw(size,'\0'); err=nvs_get_blob(h,"wifi",raw.data(),&size); nvs_close(h);
    if(err!=ESP_OK||raw.back()!='\0') return false;
    auto root=cJSON_ParseWithLengthOpts(raw.c_str(),raw.size(),nullptr,true);
    if(!root) return false;
    auto ssid=cJSON_GetObjectItemCaseSensitive(root,"ssid"),password=cJSON_GetObjectItemCaseSensitive(root,"password");
    bool ok=cJSON_IsString(ssid)&&cJSON_IsString(password)&&strlen(ssid->valuestring)>0&&strlen(ssid->valuestring)<=32&&strlen(password->valuestring)<=63;
    if(ok) { cfg.ssid=ssid->valuestring; cfg.password=password->valuestring; }
    cJSON_Delete(root); return ok;
}
inline bool startSetupWifi() {
    if(!deviceAccess.ready()||boardEthernetStarted) return false;
    char ssid[32]; snprintf(ssid,sizeof(ssid),"OpenThermostat-%06llx",static_cast<unsigned long long>(ESP.getEfuseMac()&0xffffff));
    WiFi.mode(WIFI_AP); WiFi.setSleep(WIFI_PS_NONE);
    if(!WiFi.softAP(ssid,deviceAccess.setupPassword().c_str())) return false;
    const IPAddress local(10,10,10,1);
    WiFi.softAPConfig(local,local,IPAddress(255,255,255,0));
    wifiAPMode=true; setupUntil=esp_timer_get_time()/1000+15*60*1000;
    setupCloseAt=0; setupResult="ready"; return true;
}
inline bool trySetupWifi(const config::WiFiConfig &cfg) {
    if(!wifiAPMode||cfg.ssid.empty()||cfg.ssid.size()>32||cfg.password.size()>63||(!cfg.password.empty()&&cfg.password.size()<8)) return false;
    setupCandidate=cfg; setupResult="connecting"; setupCloseAt=0;
    setupAttemptUntil=esp_timer_get_time()/1000+30000;
    WiFi.mode(WIFI_AP_STA);
    WiFi.setAutoReconnect(false); WiFi.disconnect(false,false);
    WiFi.begin(cfg.ssid.c_str(),cfg.password.c_str()); return true;
}
inline void pollSetupWifi() {
    if(setupRebootRequested) { delay(250); ESP.restart(); return; }
    const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
    if(setupAttemptUntil) {
        if(WiFi.isConnected() && WiFi.SSID().c_str()==setupCandidate.ssid) {
            const bool saved=saveSetupWifi(setupCandidate);
            config::WiFiConfig readback;
            const bool verified=saved&&readSetupWifi(readback)&&readback.ssid==setupCandidate.ssid&&readback.password==setupCandidate.password;
            setupResult=verified?"connected_saved":"storage_error";
            setupCandidate={}; setupAttemptUntil=0;
            if(verified) { setupCloseAt=now+10000; WiFi.setAutoReconnect(true); }
        } else if(now>=setupAttemptUntil) {
            setupResult="connection_failed"; setupCandidate={}; setupAttemptUntil=0;
            WiFi.disconnect(false,false);
            auto previous=config::getWiFiConfig();
            if(!previous.ssid.empty()) WiFi.begin(previous.ssid.c_str(),previous.password.c_str());
        }
    }
    if(wifiAPMode && ((setupCloseAt&&now>=setupCloseAt)||now>=setupUntil)) {
        WiFi.softAPdisconnect(true); WiFi.mode(WIFI_STA); wifiAPMode=false;
        if(setupResult!="connected_saved") setupResult="setup_expired";
    }
    // Explicit physical USB recovery, no GPIO0 button (Ethernet clock pin).
    static std::string command;
    while(Serial.available()) {
        const char c=Serial.read();
        if(c=='\n'||c=='\r') { if(command=="setup") requestSetupBoot(); command.clear(); }
        else if(command.size()<16) command+=c;
        else command.clear();
    }
}
}
#endif
