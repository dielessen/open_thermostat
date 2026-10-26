# BBQKees Gateway E32 V2 — experimental native port

**Physical transmission and autonomous heating remain unqualified.**
The initial port investigation below describes the disconnected development
scope of 17 October 2026. Since then, the passive alpha23/dev29 baseline has
been installed and Classic reception observed on the user's E32. Current
installation/release evidence is recorded in
[WORKBOARD](modern-thermostat/WORKBOARD.nl.md); that passive evidence does not
qualify transmission, Ethernet coexistence, physical hydraulics or fail-safe stop.
The model-specific remaining acceptance is in the
[pre-TX installation card](modern-thermostat/ECOMLINE-PRE-TX-ACCEPTATIE.nl.md). There is deliberately **no runtime setting or build flag to
enable EMS transmission**. Enabling `emsEnabled` permits reception only.

## Scope and sources (checked 2026-10-17)

Baseline: intuibase/open_thermostat `8f3a1ca` (see Git history for full SHA).
Existing `esp32dev` and `esp32s3` environment sections and heating algorithms,
telegram payloads, burner modulation and curves are unchanged. Their existing
hardware behavior is retained. This is a standalone firmware, **not** an EMS-ESP
plugin or an alternative SAT backend. Existing OpenThermostat Home Assistant
integration is retained; it does not inherit EMS-ESP MQTT topics automatically.

Authoritative sources:

* [BBQKees E32 V2 announcement](https://bbqkees-electronics.nl/2024/01/19/gateway-model-e32-v2-now-available/):
  original ESP32, WiFi + LAN, 16 MB flash, **8 MB physical PSRAM**, only about
  **4 MB directly available** in the classic ESP32 configuration. Not ESP32-S3.
* [EMS-ESP board profiles](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/src/core/system.cpp#L3050):
  `E32V2` and `E32V2_2`, distinct from old `E32`.
* [EMS-ESP PSRAM board](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/boards/s_16M_P.json):
  ESP32, DIO flash, 80 MHz flash, `BOARD_HAS_PSRAM`. Our board metadata follows
  these fields; app size is instead our OTA-slot size. No S3 OPI flags.
* [EMS-ESP Ethernet setup](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/src/core/network.cpp#L725)
  and [UART](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/src/uart/emsuart_esp32.cpp).
* [Arduino-ESP32 2.0.17 Ethernet](https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/Ethernet/src/ETH.cpp)
  and [IDF 4.4 RMII wiring](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/network/esp_eth.html):
  fixed MAC signals and the Arduino 2.x `ETH.begin` argument order.
* [BBQKees interface-board connections](https://bbqkees-electronics.nl/wiki/interface-board/board-connections.html):
  logic-level UART needs a real EMS transceiver; never connect ESP GPIO to the
  EMS bus. Generic interface-board instructions do not establish E32 V2 BOM.

### Wiring

| Function | GPIO / setting | Evidence / policy |
| --- | --- | --- |
| EMS RX | 4 | EMS-ESP E32V2 and E32V2_2 |
| EMS TX | 5 | Same; **input/high impedance**, not connected to UART output |
| PHY | LAN8720, address 0 | Official E32V2 profile |
| PHY enable/power/reset parameter | 15 | Official profile; passed to Arduino ETH driver |
| PHY MDC / MDIO | 23 / 18 | EMS-ESP Ethernet setup |
| RMII REF_CLK | 0, `ETH_CLOCK_GPIO0_OUT`, 50 MHz | Official clock mode 1; **not input mode** |
| RMII TX_EN / TXD0 / TXD1 | 21 / 19 / 22 | Fixed ESP32 MAC pins |
| RMII CRS_DV / RXD0 / RXD1 | 27 / 25 / 26 | Fixed ESP32 MAC pins |
| PSRAM | 16 / 17 reserved | Classic ESP32 SPI PSRAM, not S3 OPI |
| Internal flash | 6–11 reserved | Never assign to application GPIO |
| Dallas connector | 14 | Official profile; this project has no native Dallas driver |
| Button | 34 | Official profile; input only, not used here |
| LED | V2: 2; V2.2: RGB 32 | Revision-specific, LED startup disabled here |

`Board.h` fixes bus wiring regardless of uploaded `cfgpins.json`. GPIO0, 2, 5,
12 and 15 are bootstrapping pins: no arbitrary pull resistors/peripherals. Keep
GPIO1/3 for console/programming. V2.2 additionally has internal analog/LED
hardware; no automatic revision detection or sensor activation is attempted.

**Uncertainty:** the sources establish chip family, not the exact module SKU,
PSRAM manufacturer/part number or the installed device’s physical board revision. Classic SPI
PSRAM initialization is selected by the official-style `BOARD_HAS_PSRAM` flag;
Arduino initializes it before `setup()`. Startup logs `ESP.getPsramSize()`; do not
expect all 8 MB to be heap addressable or enable bank switching/HIMEM blindly.
The current [manufacturer feature matrix](https://bbqkees-electronics.nl/wiki/gateway/hardware-details.html)
assigns both E32 V2 (PCB2.0/2.1) and V2.2 to EMS circuit generation **Gen3a**.
This identifies the documented circuit family, not this unit's inspected revision
or its inactive TX bias. No public E32 V2 schematic/BOM was established in this investigation. The exact
transceiver topology, inactive TX bias, polarity at its electrical bus side,
PHY reset/power circuitry and boot-time waveforms require inspection or scope
measurements. GPIO15 is the official firmware parameter, not proof of a separate
switched power rail. These unknowns do not prevent a **TX-locked** software build.

The isolated `manual-route-compile` CI job also builds the otherwise eliminated
manual route with the actual ESP32 toolchain. It changes only the manual
permission in its disposable checkout, retains the general TX and installation
locks, and checks that only `EmsController.cpp.o` references `uart_write_bytes`.
Other UART transmit primitives are rejected. This job never uploads firmware;
its image is discarded, and E32 publication depends on its success. The standard
RX-only image still passes the unchanged no-project-TX verifier. This compile
probe does not qualify hardware or authorize a manual trial.

## EMS compatibility and lock

Upstream uses UART2, 9600 baud, 8N1, no flow control; 129-byte RX ring, per-byte
RX events (threshold 1), RX timeout disabled, UART_BREAK frame delimiter,
33-byte telegram buffer, FIFO/buffer overflow flushing. This largely matches
the older EMS-ESP UART design. Normal RX/TX polarity is selected in official
E32V2 builds (no board-specific inversion flags); do not add a second inversion
merely because the analog transceiver inverts internally.

The legacy OpenThermostat TX route uses HT3 timing: 104 us bit time, 17 bit-times
between writes and 11 bit-times BREAK. The source candidate now has a separate
E32 Classic route: bounded 13us echo-buffer polls (at most160 per byte), checked
UART results and 10-bit BREAK, following the pinned EMS-ESP UART EMS1 mode.
The pinned driver uses10bits in EMS1 mode, whereas its HT3 mode and the
general bus description use11; mode-specific timing still requires the physical
trial. It remains disabled by the board lock. The candidate now consumes and
compares each echo byte before sending the suffix. Its UART owner retires the
corresponding queued DATA counts exactly once; unexpected trailing data or
unretired counts at BREAK force resynchronization. A matching local echo is not
a bus ACK or proof of boiler action. The current EMS-ESP driver additionally selects
EMS/EMS+/HT3 modes. Legacy builds retain coarse unconfirmed-TX tracking.
The E32 checked writer consumes its own echoes, so it does not enqueue those
bytes again for that legacy counter. Neither mechanism establishes physical
collision qualification or a boiler acknowledgement. Its 33-byte framing/break-byte assumptions and
poll/ack latency need measured comparison. E32 poll recognition now derives the
opposite MSB from a CRC-valid boiler broadcast; unknown convention and poll
acknowledgements do not open a send opportunity. This follows the
[EMS-bus protocol description](https://emsesp.org/EMS-bus) and does not enable TX. Hardware flow control is disabled;
half-duplex is bus-arbitrated, not an RS485 direction pin. UART buffering and
task scheduling under simultaneous BLE/Ethernet load are unvalidated.

For E32 V2 only:

* Ordinary `writeToEms` refuses every send, including pongs and forwarding.
* A private commissioning path has its own source-reviewed permission, currently
  false; the general permission also remains false. Enabling the manual path
  cannot enable legacy startup/queue/forwarder/reset-BREAK routes.
* Startup leaves TX unmapped and GPIO5 input. The prepared, disabled manual path
  maps it only for one admitted six-byte Classic setpoint/configuration-read
  frame or its separately admitted one-byte transaction completion, then disconnects
  it with `gpio_reset_pin`, input direction and floating pull. IDF4.4's installed
  `driver/gpio.h` documents that reset disconnects peripheral GPIO-matrix output.
* A failed pin release latches a manual transport fault; normal UART recovery
  attempts release but never clears that fault. Reset is not physical acceptance.
* UART reset/5-second idle timeout cannot generate a break.
* Forwarder UART cannot start, even if old settings request it.
* Command queue insertion is dropped, avoiding a buildup/repeated queue resets.
* No configured boiler/valve GPIOs, I2C expanders, RTC I2C or startup LED are
  initialized. No safe expansion connector is assumed. Existing GPIO configs
  cannot commandeer Ethernet, PSRAM or bus pins. REST I2C scans and manual GPIO
  tests return HTTP 403 instead of touching the hardware.
* Empty break events are ignored before forwarding/parsing.

No boiler commands/temperature curves were changed. In particular upstream
startup requests include an external-controller WRITE; the lock blocks this as
well as heat commands. **This build cannot actually heat the house via EMS.**
Passive reception needs `emsEnabled=true` and still needs bench validation.
A `boilerStarted` software state is a demand indication, not proof of bus action.
This port does not prove that upstream EMS+ boiler commands support a particular
Nefit Classic/UBA. Local wired zones/RTC are deliberately unavailable on this
target pending a separately reviewed safe hardware expansion design. BLE room
sensors, schedules, MQTT zones and existing algorithms remain in the code.

## Ethernet + WiFi

`e32v2` initializes LAN8720 once with the official wiring. WiFi station settings
remain available, with auto reconnect. With no SSID, the existing configuration
AP remains available while Ethernet starts independently; E32 keeps BLE enabled
in AP mode so Ethernet-only operation does not disable room sensor scans. Do not deploy with
the example AP password unchanged. HTTP/REST/firmware OTA/filesystem recovery
share the existing wildcard WebServer; they are serviced when Ethernet, WiFi or
the configuration AP is available. NTP and mDNS startup run on effective route/IP
changes in the main loop, not twice in WiFi/Ethernet event callbacks.

Ethernet with link and DHCP address is preferred; otherwise WiFi STA. Route
selection is reasserted once per second on the lwIP TCP/IP thread (IDF 4.4), so a
secondary WiFi GOT_IP does not silently keep WiFi preferred. Existing TCP sockets
may finish or time out on the old route before reconnecting; sessions are not
seamlessly migrated. DHCP/DNS, cable reconnect and simultaneous-radio behavior
need physical tests. Espressif IDF 4.4 explicitly warns: "If you want the Ethernet to work with WiFi,
don’t select GPIO0 output mode for stability." This is a known simultaneous-radio
limitation, not merely a missing test. For the classic-ESP32 clock, the official E32V2 clock choice is followed, **not** proof that
simultaneous Ethernet/WiFi works reliably with this older Arduino core.

Arduino `WiFiClient`/`WiFiServer` are lwIP sockets, not STA-bound sockets; replacing
these classes is unnecessary. However ESPPubSubClientWrapper 1.0.2's state
machine explicitly gates on `WiFi.status()`. `e32v2_mqtt.py` uses official
PlatformIO build middleware to compile a generated copy with **only that gate**
changed to `networkConnected()`. It does not edit installed libraries, the other
targets, MQTT protocol behavior or credentials. It rejects unexpected dependency
source changes. Existing library dependencies and Home Assistant discovery are
retained. MQTT reconnect/subscription replay remains the library's own logic.
Runtime MQTT, HA, NTP, DNS, OTA and HTTP on **both** interfaces remain unverified.

## Build and automated checks

Use an isolated Python environment (no gateway/serial port is required):

```sh
python3 -m venv ~/.venvs/open-thermostat-pio
. ~/.venvs/open-thermostat-pio/bin/activate
pip install platformio==6.2.0
pio run -e e32v2
pio run -e e32v2 -t buildfs
python scripts/verify_e32v2.py
python scripts/test_e32v2_verifier.py
pio run -e esp32dev
pio run -e esp32s3
pio test -e native
```

Do not run concurrent PlatformIO invocations in one checkout: its build-directory
cleanup can remove another environment's active files. CI uses separate jobs.
The E32 target inherits the original ESP32 environment/dependencies/toolchain;
`BOARD_HAS_PSRAM` comes from its separate board metadata. Safe filesystem staging
copies web assets to `.pio/build/e32v2/data_e32v2`, disables EMS/forwarder/RTC/MQTT,
removes sample rooms and replaces pin settings. Original `data/` is not modified.
Use **this target's** `spiffs.bin`, not the other targets' image. Runtime fixed
wiring/output locks also protect against a mistakenly restored older config.

The post-build verifier checks partition overlap/alignment/bounds, actual image
sizes and actual binary partition/image headers, inert staged defaults, PSRAM
metadata, MQTT gate and absence of UART TX
primitive references in compiled project objects. Native tests cover board locks,
pin conflicts and network selection/fallback plus the upstream regression suite.
Five verifier tests include deliberate wrong flash/partition data, unsafe GPIO
settings and a compiled UART-TX regression; all must be rejected. These are
software checks, **not electrical or on-device network tests**.
See [validation report](BBQKEES_E32V2_VALIDATION.md) for actual outcomes/warnings.
CI builds all three firmware targets and runs native tests plus E32 buildfs/checks.

## Flash layout / OTA

Separate `partitions_e32v2.csv`, 16 MB total; follows upstream dual-filesystem
layout to retain its NVS-based slot selection and verified update/recovery paths.

| Label | Offset | Size |
| --- | --- | --- |
| nvs | 0x009000 | 0x005000 |
| otadata | 0x00E000 | 0x002000 |
| app0 (ota_0) | 0x010000 | 0x380000 (3.5 MiB) |
| app1 (ota_1) | 0x390000 | 0x380000 (3.5 MiB) |
| spiffs0 | 0x710000 | 0x470000 (4.4375 MiB) |
| spiffs1 | 0xB80000 | 0x470000 (4.4375 MiB) |
| coredump | 0xFF0000 | 0x010000 |

Application OTA selects the other app slot. Filesystem OTA validates the inactive
slot before selecting it in NVS. Boot tries the alternate valid filesystem on
mount failure. This is not proof of power-fail atomicity or automatic rollback
from an application crash; hardware recovery testing remains mandatory.
`SPIFFS.begin(false, ...)` does not silently format damaged/foreign user data.
No automatic EMS-ESP partition/config migration or factory-reset is provided.
An ordinary OTA firmware upload **does not install this partition table**.
The initial partition-layout change needs a later explicitly planned wired
installation, backup and full recovery check, not an in-place EMS-ESP web OTA.

## Backup BEFORE any future physical experiment

The following are operator instructions only; no device commands were run.

1. Record PCB revision, module markings, EMS-ESP version/build, `E32V2` versus
   `E32V2_2` profile, network settings, custom entities, HA/MQTT configuration and
   application settings. Export available EMS-ESP settings/files from its UI.
   Treat exported credentials as secrets; store locally, not in this repository.
2. Obtain the matching official **ESP32 16MB+** EMS-ESP release and recovery image
   from [official releases](https://github.com/emsesp/EMS-ESP32/releases) and
   [official installer](https://install.emsesp.org/), not an ESP32-S3 or old E32
   image. Save release instructions, binaries and local SHA-256 checksums.
   A normal application `.bin` is not necessarily a full flash/recovery image.
3. Disconnect the gateway from the boiler/EMS bus and all conflicting power
   sources. Follow the manufacturer's isolated bench-power/programming procedure.
   Do not connect a logic analyzer directly to the powered boiler bus. Verify
   flash security/encryption/secure-boot state before assuming raw restore works.
4. Only after a later authorization, use esptool with an explicitly identified
   serial port. Read **all 16 MB twice**, without erase/write. Example with
   esptool 4.x (replace the placeholder port, never use a wildcard):

   ```sh
   python -m esptool --chip esp32 --port <PORT> flash_id
   python -m esptool --chip esp32 --port <PORT> read_flash 0 0x1000000 e32v2-full-a.bin
   python -m esptool --chip esp32 --port <PORT> read_flash 0 0x1000000 e32v2-full-b.bin
   cmp e32v2-full-a.bin e32v2-full-b.bin
   sha256sum e32v2-full-a.bin e32v2-full-b.bin
   ```

   Stop if size/security differs, reads differ or a backup cannot be verified.
   A whole-flash dump includes bootloader, partition table, OTA state, NVS and
   filesystem/configuration. Keep a private off-device copy. It contains secrets.
5. Decode the **original** partition table offline using the matching ESP-IDF
   `gen_esp32part.py`. Verify its table offset from the installed build/recovery
   documentation (commonly 0x8000, not assumed). Extract the table bytes from the
   full dump, decode them, then separately save the actual NVS, NVS-key (if any),
   filesystem and OTA-data ranges. Never use this port's offsets to extract a
   different firmware's NVS. Preserve both the raw data and human-readable
   settings export. Do not restore incompatible NVS blindly into OpenThermostat.
6. Plan restoration **before** changing partitions. A verified raw whole-flash
   backup may restore the same chip/layout with the official esptool procedure;
   an encrypted/secured device may require a different manufacturer-supported
   route. Alternatively use the official complete recovery installer/image for
   the exact board, recreate its official partition layout and restore matching
   exported settings. Do not upload only an app image over this custom layout.
   Erase/write operations are destructive and require separate authorization;
   they are intentionally not automated here. Check boot, profile, Ethernet,
   WiFi, MQTT and settings with EMS TX disabled before reconnecting any bus.

## Mandatory physical validation / stop gates

1. Identify actual PCB/module/revision and obtain missing schematic/bias details.
2. On an isolated powered bench, verify 16 MB flash, PSRAM initialization/usable
   heap, bootstraps, reset/boot loop and GPIO0 50 MHz clock. Confirm **no GPIO5
   drive/pulses** at power-on, bootloader, idle, UART reset, forwarder attempts,
   invalid/malicious pin config and firmware/filesystem recovery.
3. Test Ethernet-only, WiFi-only and simultaneous operation, DHCP/DNS/NTP/mDNS,
   HTTP/REST, MQTT/HA discovery/reconnect, cable unplug/replug, AP fallback,
   router loss, BLE scan load and long-running stability. Verify route selection
   and current TCP reconnect behavior; resolve APLL/radio issues before use.
4. Exercise app OTA and filesystem inactive-slot update, missing/corrupt slots,
   failed/oversized upload, interrupted upload, NVS selection and wired recovery.
   Verify backups can be used to restore official EMS-ESP on this same device.
5. With an isolated EMS simulator/test interface, compare RX idle polarity, 9600
   8N1 edges, break duration/extra-byte semantics, CRC/length limits, overflow
   recovery, UART event ordering, polls/acks and collision/echo behavior against
   official EMS-ESP captures. Check electrical loading even in RX-only mode.
6. Only a **new reviewed source change** may later unlock TX after measuring
   idle/break polarity, output-stage inactive bias, byte timing, arbitration,
   collision handling and correct EMS-versus-HT3 mode. No silent bypass flag.
   Then validate payload compatibility for the exact boiler, minimum flow,
   independent stop/fallback and sole bus-controller ownership before any
   separately authorized real-boiler test. Do not equate a build with this proof.

Merging this experimental port into the fork main is not a release or approval
for unattended heating deployment. The physical gates above still apply.
