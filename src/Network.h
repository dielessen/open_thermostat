#pragma once

#include <ostream>

namespace heating {
void getWiFiNetworks(std::ostream &ss);
void getWiFiSSID(std::ostream &ss);

}

#ifdef OPENTHERMOSTAT_E32V2
namespace heating {
enum class NetworkInterface { none, wifi, ethernet };
constexpr NetworkInterface chooseNetwork(bool ethernetLink, bool ethernetHasIP, bool wifiHasIP) {
    return ethernetLink && ethernetHasIP ? NetworkInterface::ethernet
         : wifiHasIP ? NetworkInterface::wifi : NetworkInterface::none;
}
void startBoardEthernet();
bool networkConnected();
// Select default route and report changes of active interface/address in loop().
bool pollBoardNetwork();
}
#endif
