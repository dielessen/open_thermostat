#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <string>
namespace heating {
class DeviceAccess {
public:
    bool begin() {
        // Explicit owner-requested defaults for this bench build (20 Oct).
        // Ignore legacy generated access secrets, without erasing other NVS.
        admin_="admin"; ap_="openthermostat"; ready_=true;
        return true;
    }
    bool ready() const { return ready_; }
    const std::string &password() const { return admin_; }
    const std::string &setupPassword() const { return ap_; }
private:
    bool ready_=false; std::string admin_,ap_;
};
inline DeviceAccess deviceAccess;
}
#endif
