#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "Network.h"
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <cJSON.h>
#include <memory>
#include <string>

namespace heating {
extern uint64_t setupAttemptUntil;
inline std::string wifiScanState="idle",wifiScanRows="[]";
inline uint64_t wifiScanStarted=0;
inline uint64_t networkNow() { return esp_timer_get_time()/1000; }
inline bool wifiScanRunning() { return wifiScanState=="scanning"; }
inline bool startWifiScan() {
    if(boardEthernetStarted||setupAttemptUntil||WiFi.getMode()==WIFI_OFF) return false;
    if(wifiScanRunning()) return true;
    WiFi.scanDelete(); wifiScanRows="[]"; wifiScanStarted=networkNow();
    // Keep the HTTP loop responsive. AP+STA was enabled before clients joined;
    // short active dwells avoid the old blocking, ten-second HTTP scan.
    const auto count=WiFi.scanNetworks(true,false,false,120);
    wifiScanState=count==WIFI_SCAN_FAILED?"failed":"scanning";
    return wifiScanRunning();
}
inline void pollWifiScan() {
    if(!wifiScanRunning()) return;
    const auto count=WiFi.scanComplete();
    if(count==WIFI_SCAN_RUNNING&&networkNow()-wifiScanStarted<10000) return;
    if(count<0) {
        esp_wifi_scan_stop(); WiFi.scanDelete(); wifiScanState="failed"; return;
    }
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> rows(cJSON_CreateArray(),cJSON_Delete);
    if(!rows) { WiFi.scanDelete(); wifiScanState="failed"; return; }
    for(int i=0;i<count&&i<40;++i) {
        const auto ssid=WiFi.SSID(i);
        if(ssid.length()==0) continue; // Hidden SSIDs use manual entry.
        auto row=cJSON_CreateObject(); if(!row) break;
        cJSON_AddItemToArray(rows.get(),row);
        cJSON_AddStringToObject(row,"ssid",ssid.c_str());
        cJSON_AddNumberToObject(row,"rssi",WiFi.RSSI(i));
        cJSON_AddNumberToObject(row,"channel",WiFi.channel(i));
    }
    std::unique_ptr<char,decltype(&cJSON_free)> bytes(cJSON_PrintUnformatted(rows.get()),cJSON_free);
    wifiScanRows=bytes?bytes.get():"[]"; wifiScanState=bytes?"done":"failed";
    WiFi.scanDelete();
}
}
#endif
