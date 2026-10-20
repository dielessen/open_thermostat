# E32 onboarding regression checks

`firmware.cpp` calls the production `SetupNetwork.h`, `WifiDiscovery.h`,
`DeviceNetworkSettings.h` and `DeviceAccess.h` implementations. Only the SDK
radio/clock/NVS/filesystem boundary is replaced. It is not a WiFi driver or RF
simulation and cannot prove phone/ESP32 association stability.

After `pio test -e native`, run:

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
```

Optional `ONBOARDING_SCREENSHOT` saves a mobile-sized success/handoff screenshot.
The HTTP fixture has no backend or real-device access. Production HTTP digest
authentication remains covered by the actual firmware build/native access-policy
tests, not by this mock server.

Physical acceptance: fresh flash -> setup AP -> automatic scan -> wrong password
and retry -> successful DHCP and shown address -> finish -> home-network login ->
power-cycle/reconnect. Record unexpected AP drops and USB logs without home WiFi
credentials. EMS stays disconnected; software pass is not physical acceptance.
