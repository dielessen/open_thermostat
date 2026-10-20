#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <string>
#include <climits>
#include <esp_system.h>
#include <bootloader_random.h>
#include <mbedtls/ctr_drbg.h>
namespace heating {
class DeviceAccess {
public:
    bool begin() {
        if(attempted_) return ready_;
        attempted_=true;
        // Explicit owner-requested defaults for this bench build (20 Oct).
        // Ignore legacy generated access secrets, without erasing other NVS.
        admin_="admin"; ap_="openthermostat";
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
    const std::string &password() const { return admin_; }
    const std::string &setupPassword() const { return ap_; }
private:
    static int entropy(void *,unsigned char *out,size_t size) { esp_fill_random(out,size);return 0; }
    bool ready_=false,attempted_=false;
    std::string admin_,ap_;
    mbedtls_ctr_drbg_context random_{};
};
inline DeviceAccess deviceAccess;
}
#endif
