# E32 V2 software validation — 2026-10-17

**Software scope passed. Hardware scope unvalidated; EMS TX remains locked.**
Baseline `8f3a1ca33d26ac4b225ea6d3d2cb1a9708fd6cd6`.
Local toolchain: PlatformIO Core, version 6.2.0, Python 3.12, espressif32 6.10.0,
Arduino-ESP32 2.0.17 (`3.20017.241212+sha.dcc1105b`), Xtensa GCC 8.4.0.
Dependencies retained: PubSubClient 2.8.0, ESPPubSubClientWrapper 1.0.2,
RTClib 2.1.4, NimBLE-Arduino 2.5.1, esp32_utilities `9186b65`.

## Executed commands / results

| Command | Result | Linked flash bytes / slot | RAM bytes |
| --- | --- | --- | --- |
| `pio run -e e32v2` | PASS | 1,746,797 / 3,670,016 | 64,464 |
| `pio run -e esp32dev` | PASS | 1,700,161 / 1,703,936 | 64,344 |
| `pio run -e esp32s3` | PASS | 1,591,673 / 3,670,016 | 59,180 |
| `pio test -e native` | PASS: 62/62 test cases | n/a | n/a |
| `pio run -e e32v2 -t buildfs` | PASS | 4,653,056-byte SPIFFS image | n/a |
| `python scripts/verify_e32v2.py` | PASS | actual app binary 1,753,376 / 3,670,016 | n/a |
| `python scripts/test_e32v2_verifier.py` | PASS: 5/5 fault/control cases | n/a | n/a |
| actionlint 1.7.12 | PASS, no diagnostics | n/a | n/a |
| `git diff --check` | PASS | n/a | n/a |

No `warning:` or `error:` diagnostics in the final three firmware build logs.
The app .bin includes image metadata/padding; do not confuse its file size with
PlatformIO's linked flash-usage figure. Both fit each E32 OTA slot.

## Independent/regression evidence

* Untouched upstream worktree: `esp32dev` PASS, exactly the same 1,700,161 flash /
  64,344 RAM as the feature build; upstream native suite 59/59 PASS.
* Original `esp32dev`, `esp32s3`, `native` environment dictionaries unchanged.
* BoilerController, HeatingCurve, Room, HeatingController and EmsController.cpp
  byte-identical to baseline: no heating algorithm/telegram payload modifications.
* Compiled E32 project objects have no references to `uart_write_bytes`,
  `uart_send_break`, `uart_tx_chars` or `uart_write_bytes_with_break`.
  Existing ESP32 objects **retain** their original TX references.
* Actual partition binary matches CSV; alignment, non-overlap and 16 MB bounds,
  dual OTA, equal dual SPIFFS and generated app header (DIO, 16 MB, 80 MHz) checked.
* Generated filesystem has no boiler/valve/expander/I2C/forwarder outputs enabled.
* Five verifier cases: valid control; reject a 4 MB image header; reject a changed
  compiled partition offset; reject unsafe GPIO5 defaults; reject an actual
  newly compiled object referring to UART transmit. No device/simulator involved.
* Known credential/private-key pattern scan plus manual review of all new/changed
  files; no supplied credentials or private configuration added. Generated data,
  dependencies and binaries are not committed.

## Development failures (resolved, not hidden)

* An initial overlapping local PlatformIO invocation lost build-directory files.
  It was a development orchestration error, not a successful baseline result.
  Clean upstream baseline and final builds were rerun in isolated/sequential
  checkouts. CI uses isolated jobs. Do not overlap builds in one checkout.
* First Ethernet compile exposed unavailable IDF-5 default-route APIs in this
  IDF-4.4 core. Resolved using the bundled netif implementation accessor and
  lwIP TCP/IP callback, without upgrading existing targets.
* Initial MQTT build middleware read a virtual SCons variant path rather than
  its source node. Corrected to `node.srcnode()`; final generated dependency
  compiled and linked. Source hash guard rejects unreviewed wrapper changes.

No remaining failed or unexecuted **requested local software build/test**.
Remote CI status is tracked separately in repository Actions and PR checks; these local
results do not imply GitHub Actions execution or physical hardware success.

## Intentionally untested / open

Ethernet link/DHCP/DNS, WiFi radio, simultaneous interfaces, MQTT/HA, NTP/mDNS,
PSRAM detection/usable memory, serial startup, physical UART receive/transmit,
EMS loading/inversion/timing/collisions, OTA/power-fail recovery and actual boiler
compatibility have **not** been tested on hardware. No device was flashed or
connected to a boiler. Espressif explicitly warns about GPIO0 output-clock plus
WiFi stability with this core; simultaneous use is not guaranteed. Exact module
SKU, transceiver/BOM and physical PCB revision remain unknown. The current
classic-ESP32 upstream target is already 99.8% full; its layout was not changed.

This target deliberately disables local GPIO/I2C zones/RTC and EMS transmit;
BLE/MQTT room logic, schedules, web/REST/OTA and existing algorithms are retained,
but it cannot currently function as an active EMS heating controller.

See [hardware, backup/recovery and physical gates](BBQKEES_E32V2.md).
No release is published. This report used upstream `8f3a1ca` as its comparison
baseline. After the initial draft review, the fork owner chose to keep the E32 V2
adaptations on the fork's own `main`; upstream remains the original source remote.
The baseline in this report is not a claim that current fork main is unchanged.

## E32 artifact SHA-256 (built locally, not release binaries)

* Firmware: `bf8b9cc1025a7f75fa388f53d5cccca63ad3bd93beef43834924be890887cd4a`
* SPIFFS: `e0fe17042075473999242ea89530f26acbec21ab0452539eb7dd105f2b87d3c1`
* Partition table: `f43dbb2af2508c2e02dfe6870f54c2ff7df9f7f091608ce82fc909485a6d615f`
