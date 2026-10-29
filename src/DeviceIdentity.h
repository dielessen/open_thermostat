#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
namespace heating {
// The last three MAC bytes as printed (aa:bb:cc:dd:ee:ff -> "ddeeff"): the
// setup WiFi suffix. efuseMac is ESP.getEfuseMac(): MAC byte 0 in the lowest bits.
inline std::string macSuffix(uint64_t efuseMac) {
    char text[8];
    std::snprintf(text, sizeof text, "%02x%02x%02x", unsigned(efuseMac >> 24 & 0xff), unsigned(efuseMac >> 32 & 0xff),
                  unsigned(efuseMac >> 40 & 0xff));
    return text;
}
// The hostname and MQTT client ID of a new install (stored settings win), so two
// controllers never share them: "openthermostat-ddeeff".
inline std::string defaultDeviceName(uint64_t efuseMac) { return "openthermostat-" + macSuffix(efuseMac); }
// Setup access point of a board without a stored one (esp32dev/esp32s3 cfgap.json):
// the same name and documented password as the E32 setup Wi-Fi (SetupNetwork.h).
inline std::string setupWifiName(uint64_t efuseMac) { return "OpenThermostat-" + macSuffix(efuseMac); }
inline constexpr const char *setupWifiPassword = "openthermostat";
}
