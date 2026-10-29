# E32 V2 experimental test-release guide

**Current release route (23 October 2026):** alpha17 / HA dev23 is the verified
installed baseline. Use the normal in-device HTTPS updater for future verified
app updates; preserve settings. The first boiler-test beta is being prepared.
The USB and alpha.1 instructions below are historical/recovery guidance, not a
request to flash another image now. See the current modern-thermostat WORKBOARD.


**Modern development candidate:** the integrated shadow-test branch changes
setup/security/network defaults. Use [its dedicated guide](modern-thermostat/INTEGRATED-TEST.nl.md).
The shared example AP password and simultaneous-network description below refer
to the historical published alpha.1, not that candidate.

**[Easy click-by-click USB-C flashing guide](FLASHING.md).**

For the **BBQKees E32 V2 / original ESP32 with 16 MB flash**, not ESP32-S3 or
the old E32. Identify your actual PCB/module before proceeding.
This is a **bench-test prerelease, not a working heating replacement**.
EMS transmission, forwarding, local GPIO outputs and RTC/I2C remain locked.
Hardware operation has not yet been validated. No device was flashed to make
this release. Keep it disconnected from the boiler/EMS bus during initial tests.

## Package and provenance

Download the versioned E32 V2 ZIP from this fork's GitHub Releases and extract it.
`SOURCE_COMMIT.txt` identifies the source; `BUILD_PACKAGES.txt` records resolved
packages. CI runs compiled-TX/layout checks on the actual build.
`SHA256SUMS.txt` covers every included payload file. From the extracted directory:

```sh
sha256sum -c SHA256SUMS.txt
```

`e32v2-factory.bin` is a merged **installation image at address 0x0**, containing:

| Component | Offset |
| --- | --- |
| bootloader.bin | 0x1000 |
| partitions.bin | 0x8000 |
| boot_app0.bin (initial OTA selection) | 0xe000 |
| firmware.bin (app0) | 0x10000 |
| spiffs.bin (spiffs0, inert E32 defaults) | 0x710000 |

Individual binaries are also supplied for inspection/recovery planning.
The merged image does not initialize alternate app/filesystem slots; the initial
erase clears them. It is **not** an EMS-ESP-compatible OTA image.
Do not upload it, or this app alone, through the installed EMS-ESP web updater:
this port uses a different partition layout.

## Before installation: backup and recovery

Follow the full [hardware/backup/recovery guide](BBQKEES_E32V2.md), especially
"Backup BEFORE any future physical experiment". Export EMS-ESP settings, save
matching official ESP32 16MB+ recovery firmware, identify the exact serial port
and check flash size/security. On an isolated bench read all 16 MB **twice**,
compare the copies and save an off-device copy and checksums. Preserve original
partition/NVS/configuration data privately; it may contain credentials.
Stop if reads differ, encryption/secure boot prevents recovery, or the original
firmware cannot be restored by a documented matching procedure.
This prerelease contains no backup of your installed gateway.

## Initial serial installation (manual operator action)

Only after the preceding checks, with the boiler/EMS bus disconnected and the
manufacturer-approved programming/power arrangement. Do not attach competing
power sources or an arbitrary USB-TTL adapter. Use the manufacturer's method for
entering the bootloader. The commands below **erase installed firmware and
settings**; they were not run to create this release.

In a dedicated Python environment install esptool 4.5.1, then run from the
extracted package. Replace `/dev/ttyUSB_EXACT` with the positively identified
port, never a wildcard. On Windows use the exact `COM` port.

```sh
python -m pip install esptool==4.5.1
python -m esptool --chip esp32 --port /dev/ttyUSB_EXACT flash_id
# STOP unless this is the expected recoverable 16 MB ESP32 and backups passed.
python -m esptool --chip esp32 --port /dev/ttyUSB_EXACT --after no_reset erase_flash
python -m esptool --chip esp32 --port /dev/ttyUSB_EXACT --baud 115200 --after no_reset write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 e32v2-factory.bin
python -m esptool --chip esp32 --port /dev/ttyUSB_EXACT --after no_reset verify_flash \
  0x0 e32v2-factory.bin
```

**Keep the device in the bootloader until verification succeeds.** esptool 4.5.1
normally hard-resets after an operation; `--after no_reset` prevents that.
The first normal boot can change NVS/filesystem bytes inside the merged image,
so verifying the whole installation image after that boot is not a valid check
against the original file. Only after successful verification, unplug/reconnect
USB to start the test firmware, still disconnected from the boiler/EMS bus.

**alpha.1 documentation erratum (2026-10-18):** the original ZIP and the guide at
the immutable release source omit these `--after no_reset` options. Use the
corrected commands above or the easy browser guide, not that archived command
sequence. The release binaries, tag and checksums are unchanged.

Stop on any write/verify error. Never restore old EMS-ESP NVS into this layout.
Keep original backups separate from these release images.

## First test session: record outcomes

1. Capture serial output at **115200 baud**. Record release/source commit, board
   revision, detected flash/PSRAM size and usable heap. Stop on boot loops,
   exceptions, unstable power or unexpected output activity.
2. With no WiFi credentials, first boot starts the setup network
   `OpenThermostat-xxxxxx` (unique per device) with the setup password
   `openthermostat`. Open `http://10.10.10.1/` locally, sign in with admin/admin
   and choose your own web password before network use. (Early alpha test builds
   used `IntuiBaseHeating`.)
   EMS reception, forwarder, RTC and MQTT start disabled; rooms are empty.
3. Test isolated Ethernet DHCP/web access and WiFi configuration/web access,
   cable removal/reconnection and reboot persistence. Record addresses/logs.
   Simultaneous Ethernet/WiFi remains experimental: GPIO0 output-clock/radio
   stability is a known limitation of this core.
   **Only using one network is not the same as disabling the other hardware:**
   this alpha always starts WiFi AP/STA and then Ethernet. Removing the cable
   does not disable the Ethernet clock, and using Ethernet does not turn WiFi
   off. A true radio-off or Ethernet-clock-off test needs a separately reviewed
   mode/source change; the current image does not provide one.
4. Use a test MQTT broker with a unique client ID/base topic. Check reconnect,
   discovery and BLE sensor data if used. Do not replace the live EMS-ESP
   integration or infer real boiler action from software demand state.
5. Verify measured GPIO5 electrical inactivity and the physical gates in the
   hardware guide before any EMS simulator connection. Passive reception needs
   explicit configuration and separate validation. No setting can unlock TX.
6. Perform application/filesystem OTA and failed-update/recovery tests only as
   a deliberate follow-up with working serial recovery and recorded evidence.
   A boot is not proof of OTA safety or suitability for heating.

Report revision, source commit, credentials-redacted serial log, interface,
exact steps and observed/expected results. Mark Ethernet/WiFi/PSRAM/MQTT/BLE/OTA/
EMS checks separately PASS, FAIL or NOT TESTED.

## Rollback

Stop on unsafe/unstable behavior and keep the gateway off the EMS bus. Restore
the same-device verified whole-flash backup, or matching official complete
EMS-ESP recovery installation plus compatible settings as described in the
hardware guide. Restore the original layout, not just an app over this table.
Verify profile, settings, network and MQTT with EMS TX disabled before any later
reconnection. `e32v2-factory.bin` is not an EMS-ESP recovery image.
