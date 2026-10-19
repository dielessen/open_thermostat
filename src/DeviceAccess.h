#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <nvs.h>
#include <esp_system.h>
#include <Arduino.h>
#include <string>
namespace heating {
class DeviceAccess {
public:
    bool begin() {
        nvs_handle_t h;
        if(nvs_open("ot_access",NVS_READWRITE,&h)!=ESP_OK) return false;
        size_t size=sizeof(secret_);
        auto err=nvs_get_blob(h,"secret",secret_,&size);
        if(err==ESP_ERR_NVS_NOT_FOUND) {
            esp_fill_random(secret_,sizeof(secret_));
            err=nvs_set_blob(h,"secret",secret_,sizeof(secret_));
            if(err==ESP_OK) err=nvs_commit(h);
        }
        nvs_close(h);
        if(err!=ESP_OK||size!=sizeof(secret_)) return false;
        admin_=hex(secret_,16); ap_=hex(secret_+16,16); ready_=true;
        return true;
    }
    bool ready() const { return ready_; }
    const std::string &password() const { return admin_; }
    const std::string &setupPassword() const { return ap_; }
private:
    static std::string hex(const uint8_t *bytes,size_t count) {
        static constexpr char d[]="0123456789abcdef"; std::string s(count*2,'0');
        for(size_t i=0;i<count;++i) {s[2*i]=d[bytes[i]>>4];s[2*i+1]=d[bytes[i]&15];} return s;
    }
    uint8_t secret_[32]{}; bool ready_=false; std::string admin_,ap_;
};
inline DeviceAccess deviceAccess;
}
#endif
