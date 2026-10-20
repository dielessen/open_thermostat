

#include <WiFi.h>

#include "Network.h"
#include "config.h"
#include "WifiDiscovery.h"

namespace heating {

static const char *getEncryptionStr(wifi_auth_mode_t mode) {
	switch (mode) {
		case WIFI_AUTH_OPEN:
			return "open";
		case WIFI_AUTH_WEP:
			return "WEP";
		case WIFI_AUTH_WPA_PSK:
			return "WPA_PSK";
		case WIFI_AUTH_WPA2_PSK:
			return "WPA2_PSK";
		case WIFI_AUTH_WPA_WPA2_PSK:
			return "WPA_WPA2_PSK";
		case WIFI_AUTH_WPA2_ENTERPRISE:
			return "WPA2_ENTERPRISE";
		default:
			return "open";
	}
}

void getWiFiNetworks(std::ostream &ss) {
#ifdef OPENTHERMOSTAT_E32V2
	// Scanning can power up the radio: never do that beside GPIO0 ETH clock.
	if(boardEthernetStarted) { ss<<"[]"; return; }
	pollWifiScan();
	if(!setupAttemptUntil&&!wifiScanRunning()&&(wifiScanState=="idle"||networkNow()-wifiScanStarted>15000)) startWifiScan();
	ss<<wifiScanRows; return;
#endif
	auto noNetworks = WiFi.scanNetworks();
	std::unique_ptr<cJSON,decltype(&cJSON_Delete)> rows(cJSON_CreateArray(),cJSON_Delete);
	for (auto n = 0; n < noNetworks; ++n) {
		auto row=cJSON_CreateObject(); cJSON_AddItemToArray(rows.get(),row);
		cJSON_AddStringToObject(row,"ssid",WiFi.SSID(n).c_str());
		cJSON_AddNumberToObject(row,"rssi",WiFi.RSSI(n)); cJSON_AddNumberToObject(row,"channel",WiFi.channel(n));
		cJSON_AddStringToObject(row,"encryption",getEncryptionStr(WiFi.encryptionType(n)));
	}
	std::unique_ptr<char,decltype(&cJSON_free)> bytes(cJSON_PrintUnformatted(rows.get()),cJSON_free);
	ss << (bytes?bytes.get():"[]"); WiFi.scanDelete();
}

void getWiFiSSID(std::ostream &ss) {
	auto wifiConfig = config::getWiFiConfig();
	std::unique_ptr<cJSON,decltype(&cJSON_Delete)> row(cJSON_CreateObject(),cJSON_Delete);
	cJSON_AddStringToObject(row.get(),"ssid",wifiConfig.ssid.c_str());
	std::unique_ptr<char,decltype(&cJSON_free)> bytes(cJSON_PrintUnformatted(row.get()),cJSON_free);
	ss << (bytes?bytes.get():"{}");
}

}

#ifdef OPENTHERMOSTAT_E32V2
#include "Board.h"
#include <ETH.h>
#include <esp_netif.h>
#include <esp_netif_net_stack.h>
#include <lwip/netif.h>
#include <lwip/tcpip.h>

namespace heating {
bool boardEthernetStarted=false;
void startBoardEthernet() {
    // Arduino 2.x signature; not the Arduino 3.x EMS-ESP signature.
    WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t) {
        if (event == ARDUINO_EVENT_ETH_START) {
            const auto config = config::getNetworkConfig();
            ETH.setHostname(config.hostname.c_str());
        }
    }, ARDUINO_EVENT_ETH_START);
    if (!ETH.begin(board::phyAddress, board::phyPower, board::phyMdc,
                   board::phyMdio, ETH_PHY_LAN8720, ETH_CLOCK_GPIO0_OUT)) {
        Serial.println("E32V2: Ethernet initialization failed; use USB setup recovery");
    } else {
        boardEthernetStarted=true;
    }
}

bool networkConnected() {
    return (ETH.linkUp() && uint32_t(ETH.localIP()) != 0) || WiFi.isConnected();
}

bool pollBoardNetwork() {
    static NetworkInterface previousInterface = NetworkInterface::none;
    static uint32_t previousIP = 0;
    static uint32_t lastCheck = 0;
    if (uint32_t(millis() - lastCheck) < 1000) return false;
    lastCheck = millis();
    const auto active = chooseNetwork(ETH.linkUp(), uint32_t(ETH.localIP()) != 0, WiFi.isConnected());
    const bool ethernet = active == NetworkInterface::ethernet;
    const uint32_t ip = ethernet ? uint32_t(ETH.localIP())
        : active == NetworkInterface::wifi ? uint32_t(WiFi.localIP()) : 0;
    const bool changed = active != previousInterface || ip != previousIP;
    previousInterface = active;
    previousIP = ip;
    if (active == NetworkInterface::none) return false;
    // Reassert periodically: a secondary WiFi GOT_IP can change IDF's route.
    auto netif = esp_netif_get_handle_from_ifkey(ethernet ? "ETH_DEF" : "WIFI_STA_DEF");
    if (netif) {
        // IDF 4.4 has no esp_netif_set_default_netif. Use the lwIP TCP/IP
        // thread, never change its default netif from the Arduino loop task.
        tcpip_callback([](void *value) { netif_set_default(static_cast<struct netif *>(value)); },
                       esp_netif_get_netif_impl(netif));
    }
    return changed;
}
}
#endif
