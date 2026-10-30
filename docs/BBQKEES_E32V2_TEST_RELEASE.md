# E32 V2 release package: technical notes

**To install or update OpenThermostat, follow the [installation guide](INSTALL.md).**
It covers the first USB installation, the setup Wi-Fi, the boiler connection,
Home Assistant, updates and recovery. For backups and going back to EMS-ESP,
see [USB backup and recovery](FLASHING.md).

This page used to be the guide for the first bench-test releases (alpha.1 to
alpha.17). Those instructions are out of date and have been removed; they
remain available in the history of this file. What follows are the technical
facts about the release package that still apply.

## What the release contains

Each E32 V2 release on the
[releases page](https://github.com/dielessen/open_thermostat/releases) has:

- `firmware.bin`: the application with the embedded web interface. This is
  the file for updates, from Home Assistant or the E32's update page. Updates
  keep settings.
- `open-thermostat-e32v2-<version>.zip`: the complete package, including
  `e32v2-factory.bin`, `FACTORY-CHECK.txt`, `SHA256SUMS.txt`, symbols and the
  source and licence material.
- `RELEASE-SHA256SUMS.txt` with the checksums of the release files.

From the extracted ZIP you can check every file:

```sh
sha256sum -c SHA256SUMS.txt
```

## The factory image

`e32v2-factory.bin` is a merged installation image written at address `0x0`.
Writing it with a full erase deletes all settings. It contains:

| Component | Offset |
| --- | --- |
| bootloader.bin | 0x1000 |
| partitions.bin | 0x8000 |
| boot_app0.bin (initial OTA selection) | 0xe000 |
| firmware.bin (app0) | 0x10000 |
| spiffs.bin (spiffs0, default settings) | 0x710000 |

`FACTORY-CHECK.txt` gives the image length and its MD5 checksum. Check the
written image before the first start: at the first start the E32 writes its
own settings, after which the checksum no longer matches.

The factory image is **not** an update file and **not** an EMS-ESP image. Never
upload it through an update page, and never upload it or OpenThermostat's
`firmware.bin` through the EMS-ESP web updater: OpenThermostat uses a
different partition layout. Going back to EMS-ESP needs a full restore, as
described in [USB backup and recovery](FLASHING.md#go-back-to-the-original-firmware).

## Board

Releases are built for the **BBQKees E32 V2** only: a classic ESP32 with 16 MB
flash and PSRAM. It is not the original E32 and not an ESP32-S3. See
[E32 V2 hardware](BBQKEES_E32V2.md) for pins and recovery details.
