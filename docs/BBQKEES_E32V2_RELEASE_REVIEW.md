# E32 V2 alpha.1 — board and release re-review

Reviewed 2026-10-18. Release source: `56130e796178c9804c612fc612f64e9a86970843`.
[Release](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.1)
and [original CI](https://github.com/dielessen/open_thermostat/actions/runs/39039500509).

**Result: no incorrect board-family or pin mapping found in this review. One
technical flashing-instruction defect corrected. Hardware compatibility is
still NOT VALIDATED; this is not approval for heating or boiler connection.**

## Confirmed software/package checks

- Manufacturer documentation identifies the E32 V2 as the original ESP32 with
  16 MB flash and 8 MB physical PSRAM, not ESP32-S3 or the old 4 MB E32.
- Pinned official EMS-ESP `E32V2` and `E32V2_2` profiles agree on EMS RX/TX 4/5,
  LAN8720 address 0, PHY parameter 15 and GPIO0 output-clock mode. MDC/MDIO are
  23/18. Revision-specific LED/analog peripherals remain unused.
- Flash pins 6–11 and PSRAM pins 16/17 are not assigned to EMS or Ethernet clock.
  The classic SPI PSRAM build flag is present; the rebuilt Arduino startup
  object references `psramInit`. This is not a measured PSRAM detection result.
- All three release assets were downloaded again and their GitHub digests and
  manifests checked. Source commit, original ESP32 chip IDs, DIO/16MB/80MHz image
  headers, partition bounds, two app/filesystem slots, merged component offsets
  and erased initial NVS passed. **51/51 package/source checks passed.**
- Independently unpacked released SPIFFS passed **14/14 checks**: fixed EMS pins,
  disabled EMS/forwarder/RTC/MQTT, no auxiliary outputs/example rooms/private WiFi
  credentials, expected AP details and required recovery web assets.
- A fresh isolated build of the exact release source passed, including buildfs.
  The existing compiled-UART-TX/layout/defaults verifier passed; **5/5 verifier
  fault/control tests** and **62/62 native tests** passed again. Resolved firmware
  dependency versions matched the release package. Rebuilt images have their
  own build metadata; they were not substituted for the published images.
- Current main and the release have identical firmware, board, partition and
  verifier/middleware source. This correction changes documentation only.

Reproduce the build checks from the exact release source in an isolated checkout:

```sh
pio run -e e32v2
pio run -e e32v2 -t buildfs
python scripts/verify_e32v2.py
python scripts/test_e32v2_verifier.py
pio test -e native --verbose
```

Use the documented pinned PlatformIO environment; never run overlapping builds
in the same checkout. These commands do not flash a device.

## F1 — technical flashing commands restarted too early (corrected)

The archived technical guide used esptool 4.5.1's default post-write hard reset
before verifying the whole merged image. First boot can modify NVS/SPIFFS inside
that image, making the subsequent full-image comparison invalid.

The [corrected technical guide](BBQKEES_E32V2_TEST_RELEASE.md) explicitly uses
`--after no_reset` for erase/write/verify and starts the firmware only after
verification. The commands were parsed with the actual esptool 4.5.1 parser,
intercepted before serial execution, and its reset implementation was inspected.
The [easy browser guide](FLASHING.md) already requires verification before boot.

The original release ZIP, tag and binaries remain unchanged for provenance.
**Do not use the archived ZIP's uncorrected esptool command sequence.** Use the
corrected linked guide or the easy browser guide. This is a documentation
erratum, not a newly built firmware release.

## Remaining compatibility gates

1. **GPIO0 clock/radio limitation:** the pinned Arduino/IDF core has a documented
   Ethernet-output-clock/WiFi stability limitation. This image always starts
   WiFi AP/STA and then Ethernet. Choosing one connection or unplugging a cable
   does not disable the other hardware. True radio-off/clock-off isolation needs
   a separately reviewed mode/source change; moving the clock to PSRAM pins is
   not a valid workaround. Network selection unit tests do not prove stability.
2. **Exact installed hardware:** PCB/module revision, PSRAM operation, electrical
   bus-side TX bias/inactivity and boot/reset waveforms remain unmeasured. The
   common official profile is not proof of the particular physical board.
3. **Physical bench/recovery:** full same-device backups, first boot, Ethernet/
   WiFi/BLE/MQTT under load, OTA failure/recovery and restoring original EMS-ESP
   remain NOT TESTED. Follow the existing physical acceptance plan; stop on any
   instability or output activity.
4. **Heating remains unavailable:** EMS TX/forwarding/reset breaks and auxiliary
   GPIO/I2C/RTC stay locked. Full classic EMS support is still incomplete. No
   boiler action, heating performance or unattended-operation claim is made.

No gateway was flashed, restored, electrically measured or connected to a boiler
for this review. Software results cannot establish that a release is error-free
on physical hardware.

## Primary references

- [Manufacturer E32 V2 hardware announcement](https://bbqkees-electronics.nl/2024/01/19/gateway-model-e32-v2-now-available/)
- [Manufacturer USB-C programming/recovery guidance](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2)
- [Pinned EMS-ESP board profiles](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/src/core/system.cpp#L3050)
- [Pinned Arduino 2.0.17 Ethernet implementation](https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/Ethernet/src/ETH.cpp)
- [IDF 4.4 Ethernet clock warning](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/network/esp_eth.html)
- [Detailed hardware constraints and physical acceptance plan](BBQKEES_E32V2.md)
