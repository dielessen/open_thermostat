#pragma once
#include "Arduino.h"
constexpr int WIFI_OFF=0,WIFI_STA=1,WIFI_AP=2,WIFI_AP_STA=3,WIFI_PS_NONE=0;
constexpr int WIFI_SCAN_RUNNING=-1,WIFI_SCAN_FAILED=-2;
struct FakeWiFi {
    int modeValue=0,modeChanges=0,joins=0,scans=0,complete=-1;
    bool connected=false,ap=false,persist=true,reconnect=true,scanAsync=false,modeOk=true,apOk=true;
    std::string joined,apPassword; IPAddress ip;
    struct Row {std::string ssid;int rssi,channel;}; std::vector<Row> rows;
    int getMode(){return modeValue;}
    bool mode(int m){++modeChanges;if(!modeOk)return false;modeValue=m;return true;}
    void persistent(bool p){persist=p;}
    void setAutoReconnect(bool r){reconnect=r;}
    void setSleep(int){}
    bool disconnect(bool,bool){connected=false;ip={};return true;}
    bool softAPConfig(IPAddress,IPAddress,IPAddress){return true;}
    bool softAP(const char*,const char* p){ap=apOk;apPassword=p;return apOk;}
    void softAPdisconnect(bool){ap=false;}
    int scanNetworks(bool async,bool,bool,unsigned dwell){++scans;scanAsync=async;if(dwell>120)throw std::runtime_error("long scan dwell");return complete;}
    void scanDelete(){rows.clear();}
    int scanComplete(){return complete;}
    String SSID(int i){return rows.at(i).ssid;}
    String SSID(){return joined;}
    int RSSI(int i){return rows.at(i).rssi;}
    int channel(int i){return rows.at(i).channel;}
    bool isConnected(){return connected;}
    IPAddress localIP(){return ip;}
    void begin(const char* name,const char*){++joins;joined=name;}
};
inline FakeWiFi WiFi;
