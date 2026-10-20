# E32 onboarding regression checks

`firmware.cpp` calls the production `SetupNetwork.h`, `WifiDiscovery.h`,
`DeviceNetworkSettings.h` and `DeviceAccess.h` implementations. Only the SDK
radio/clock/NVS/filesystem boundary is replaced. It is not a WiFi driver or RF
simulation and cannot prove phone/ESP32 association stability.

After `pio test -e native`, run:

Run PlatformIO native tests and firmware builds sequentially in one checkout:
the test runner can clean `.pio/build` and collide with another environment's
build. Browser checks and the standalone boundary binary may run alongside builds.

```sh
g++ -std=c++20 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
  -Itest/onboarding/include -Isrc -I.pio/libdeps/native/cJSON \
  -I.pio/libdeps/native/esp32_utilities/src \
  test/onboarding/firmware.cpp .pio/libdeps/native/cJSON/cJSON.c \
  -o /tmp/open-thermostat-onboarding-test
/tmp/open-thermostat-onboarding-test
```

`browser.cjs` executes the shipped HTML/JS in real Chromium with explicitly
simulated HTTP results. Requires maintained Playwright Core plus Chromium:

```sh
CHROMIUM_PATH=/path/to/chrome NODE_PATH=/path/to/node_modules \
  node test/onboarding/browser.cjs
CHROMIUM_PATH=/path/to/chrome NODE_PATH=/path/to/node_modules \
  node test/onboarding/network-browser.cjs
```

Optional `ONBOARDING_SCREENSHOT` saves a mobile-sized success/handoff screenshot.
The HTTP fixture has no backend or real-device access. Production HTTP digest
authentication remains covered by the actual firmware build/native access-policy
tests, not by this mock server.

Physical acceptance: fresh flash -> setup AP -> OS captive portal auto-opens -> automatic scan -> wrong password
and retry -> successful DHCP and shown address -> automatic 8-second AP shutdown -> home-network login ->
power-cycle/reconnect. Record unexpected AP drops and USB logs without home WiFi
credentials. EMS stays disconnected; software pass is not physical acceptance.

The official Arduino DNSServer is faked only at its boundary: start/wildcard/IP,
TTL, polling, failure and stop are exercised through production SetupNetwork.
This is not a real UDP/DNS exchange. Native CaptivePortalPolicy tests cover OS
probe paths, canonical host, socket-interface requirement, and the strict AP-only
setup allowlist. Production REST applies method/same-origin checks before its
login exception; normal LAN requests still require digest authentication. Actual
phone auto-open/mini-browser behaviour must be recorded on hardware.
