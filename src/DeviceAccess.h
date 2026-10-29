#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <string>
#include <string_view>
#include <climits>
#include <esp_system.h>
#include <bootloader_random.h>
#include <nvs.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/md.h>
#include <mbedtls/pkcs5.h>
#include "control/WebPassword.h"
namespace heating {
class DeviceAccess {
public:
    // factory: no stored password, "admin" applies. unreadable: a stored record
    // that cannot be read back; no password is accepted until the USB console
    // command password-reset restores the factory password (physical access).
    enum class PasswordState : uint8_t { factory, stored, unreadable };
    bool begin() {
        if(attempted_) return ready_;
        attempted_=true;
        // The setup Wi-Fi password stays the documented default. Legacy
        // generated access secrets ("ot_access"/"secret") are ignored, not erased.
        ap_="openthermostat";
        loadPassword();
        // Called first in setup(), BEFORE RF/ADC/I2S initialization. Seed once
        // with the documented boot entropy source, also in Ethernet-only mode.
        // Never switch that ADC entropy source on while the application is running.
        mbedtls_ctr_drbg_init(&random_);
        bootloader_random_enable();
        constexpr unsigned char purpose[]="OpenThermostat web sessions/v1";
        const auto result=mbedtls_ctr_drbg_seed(&random_,entropy,nullptr,purpose,sizeof(purpose)-1);
        bootloader_random_disable();
        // Retain the boot-seeded CSPRNG state; do not reseed from a radio-off RNG.
        mbedtls_ctr_drbg_set_reseed_interval(&random_,INT_MAX);
        ready_=result==0;
        return ready_;
    }
    bool ready() const { return ready_; }
    bool randomBytes(unsigned char *out,size_t size) {
        return ready_&&mbedtls_ctr_drbg_random(&random_,out,size)==0;
    }
    PasswordState passwordState() const { return state_; }
    bool defaultPassword() const { return state_==PasswordState::factory; }
    bool verifyPassword(std::string_view password) const {
        if(state_==PasswordState::stored) return control::WebPassword::verify(record_,password,pbkdf2);
        if(state_!=PasswordState::factory) return false;
        const auto expected=control::WebPassword::factoryDefault;
        unsigned char difference=password.size()!=expected.size();
        for(size_t i=0;i<password.size()&&i<expected.size();++i) difference|=password[i]^expected[i];
        return difference==0;
    }
    // Salt from the boot-seeded CSPRNG; durable only after NVS commit and readback.
    bool storePassword(std::string_view password) {
        if(!ready_||control::WebPassword::checkNew(password)!=control::WebPassword::Length::ok) return false;
        control::WebPassword::Record record;
        if(!randomBytes(record.salt.data(),record.salt.size())||!control::WebPassword::derive(record,password,pbkdf2)) return false;
        const auto blob=control::WebPassword::encode(record);
        nvs_handle_t h;
        if(nvs_open(nvsNamespace,NVS_READWRITE,&h)!=ESP_OK) return false;
        bool ok=nvs_set_blob(h,nvsKey,blob.data(),blob.size())==ESP_OK&&nvs_commit(h)==ESP_OK;
        nvs_close(h);
        control::WebPassword::Record readback;
        ok=ok&&readRecord(readback)==PasswordState::stored&&readback.hash==record.hash&&readback.salt==record.salt;
        if(ok) { record_=record; state_=PasswordState::stored; }
        else loadPassword(); // whatever NVS now holds decides; never a half-written state
        return ok;
    }
    bool resetPassword() {
        nvs_handle_t h;
        if(nvs_open(nvsNamespace,NVS_READWRITE,&h)!=ESP_OK) return false;
        const auto erased=nvs_erase_key(h,nvsKey);
        const bool ok=(erased==ESP_OK||erased==ESP_ERR_NVS_NOT_FOUND)&&nvs_commit(h)==ESP_OK;
        nvs_close(h);
        loadPassword();
        return ok&&state_==PasswordState::factory;
    }
    const std::string &setupPassword() const { return ap_; }
private:
    static constexpr const char *nvsNamespace="ot_access", *nvsKey="web_pw";
    static int entropy(void *,unsigned char *out,size_t size) { esp_fill_random(out,size);return 0; }
    // PBKDF2-HMAC-SHA256 from the already linked SDK mbedTLS (md.c, pkcs5.c).
    static bool pbkdf2(std::string_view password,const uint8_t *salt,size_t saltSize,uint32_t iterations,uint8_t *out) {
        mbedtls_md_context_t md; mbedtls_md_init(&md);
        const auto *info=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
        const bool ok=info&&mbedtls_md_setup(&md,info,1)==0&&mbedtls_pkcs5_pbkdf2_hmac(&md,
            reinterpret_cast<const unsigned char *>(password.data()),password.size(),salt,saltSize,
            iterations,control::WebPassword::hashBytes,out)==0;
        mbedtls_md_free(&md);
        return ok;
    }
    static PasswordState readRecord(control::WebPassword::Record &out) {
        nvs_handle_t h;
        const auto opened=nvs_open(nvsNamespace,NVS_READONLY,&h);
        if(opened==ESP_ERR_NVS_NOT_FOUND) return PasswordState::factory;
        if(opened!=ESP_OK) return PasswordState::unreadable;
        uint8_t blob[control::WebPassword::recordBytes];
        size_t size=0;
        auto err=nvs_get_blob(h,nvsKey,nullptr,&size);
        if(err==ESP_OK&&size==sizeof(blob)) err=nvs_get_blob(h,nvsKey,blob,&size);
        nvs_close(h);
        if(err==ESP_ERR_NVS_NOT_FOUND) return PasswordState::factory;
        return err==ESP_OK&&control::WebPassword::decode(blob,size,out)?PasswordState::stored:PasswordState::unreadable;
    }
    void loadPassword() { control::WebPassword::Record r; state_=readRecord(r); record_=state_==PasswordState::stored?r:control::WebPassword::Record{}; }
    bool ready_=false,attempted_=false;
    PasswordState state_=PasswordState::factory;
    control::WebPassword::Record record_{};
    std::string ap_;
    mbedtls_ctr_drbg_context random_{};
};
inline DeviceAccess deviceAccess;
}
#endif
