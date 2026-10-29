# Flash the E32 V2 — easy step-by-step guide

**Current release route (23 October 2026):** alpha17 / HA dev23 is the verified
installed baseline. Use the normal in-device HTTPS updater for future verified
app updates; preserve settings. The first boiler-test beta is being prepared.
The USB and alpha.1 instructions below are historical/recovery guidance, not a
request to flash another image now. See the current modern-thermostat WORKBOARD.


**Modern shadow candidate:** first read [the candidate guide](modern-thermostat/INTEGRATED-TEST.nl.md).
The 20 October WiFi-fix build uses owner-requested fixed local credentials;
see [its short installation guide](modern-thermostat/WIFI-FIX.nl.md).
Its checksum, SSID and network modes differ from historical alpha.1 below.

**Use a USB-C data cable and a browser. No Python, PlatformIO or separate programmer needed.**

> This guide is for **test release v0.1.0-e32v2-alpha.1** on a **BBQKees E32 V2 with 16 MB flash**.
> This version **cannot control the boiler**: EMS transmission is locked and full classic EMS support is still missing.
> Keep the gateway **disconnected from the boiler/EMS bus** throughout this test. Flashing erases the current firmware and settings.

## What you need

- The E32 V2 and a **USB-C cable that supports data**, not just charging.
- A computer with **Chrome or Edge**. Safari and Firefox do not support this browser-based route.
- The free, open-source browser tool [ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/).
- A folder on your computer, such as **E32-test**, for the firmware and backups.

Use the regular ESPConnect page, **not the preview version**. The button labels below are in English.

## 1. Save your current settings first

1. Open the existing **EMS-ESP web interface** while it is still accessible normally.
2. Go to **Settings → Upload/Download** and download the configuration. The wording may differ between EMS-ESP versions.
3. Save your current EMS-ESP version and board profile too: take a screenshot of the system information.
4. Save the matching official **EMS-ESP ESP32-16MB+ recovery firmware** and the [recovery procedure](BBQKEES_E32V2.md#backup-before-any-future-physical-experiment).

**Important:** a settings export is not a full firmware backup. We will make that in step 3.

## 2. Connect the gateway to your computer

1. Disconnect the **EMS/boiler cable and any separate power supply** from the gateway.
2. Connect the **external USB-C port** on the E32 V2 to your computer.
   USB supplies power during flashing; no extra power adapter is needed.
3. Open [ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/) in Chrome or Edge.
4. Select **115200** baud if available and click **Connect**.
5. Select the gateway's USB/serial port and confirm with **Connect**.
6. Check **Device Info**: it must show **ESP32** and **16 MB flash**, not ESP32-S3 or 4 MB.

In the security information, **Flash Encryption** and **Secure Boot** must be disabled.
If either is enabled, or you cannot confirm their status, **stop before erasing or writing** and have the recovery route checked first.

## 3. Make two complete backups

This is the most important preparation. **Do not click Erase or Flash Firmware yet.**

1. Open **Flash Tools** on the left.
2. Find **Flash Backup & Erase** and enter:

   | Field | Value |
   | --- | --- |
   | Start offset | `0x0` |
   | Length (bytes) | `0x1000000` |

3. Click **Download Flash Region** and wait for the download to finish completely.
4. Save the file in **E32-test** as **e32-backup-a.bin**.
5. Click **Download Flash Region again**, using the same values. Save this file as **e32-backup-b.bin**.
   Do not copy the first file: this must be a second read from the device. Do not let the gateway boot normally between reads.
   A full read can take a long time, especially at 115200 baud. Keep the computer awake and do not unplug the cable.
6. Both files must be exactly **16,777,216 bytes**. In file properties, check the actual size, not “size on disk”.
7. Check that their contents match. The following short command is the only computer command needed for this backup check; nothing needs installing.

**Windows:** open **E32-test** in File Explorer, click the address bar, type `powershell` and press Enter. Paste:

```powershell
Get-FileHash .\e32-backup-a.bin, .\e32-backup-b.bin -Algorithm SHA256
```

The two values under **Hash** must be **exactly the same**.

<details>
<summary>Using macOS or Linux? Click here.</summary>

Open a terminal in the folder containing the backups.

macOS:

```sh
shasum -a 256 e32-backup-a.bin e32-backup-b.bin
```

Linux:

```sh
sha256sum e32-backup-a.bin e32-backup-b.bin
```

The two hashes must be identical.

</details>

**Continue only with two complete, identical backups and a documented recovery route.**
Keep an extra copy outside this computer. Backups may contain passwords: **do not upload them to GitHub**.
Do not rely only on **Download Flash Backup** or **Download All Partitions**: this guide explicitly uses the full range shown above.

## 4. Download our firmware

1. Open [the E32 V2 test release on GitHub](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.1).
2. Under **Assets**, download **open-thermostat-e32v2-v0.1.0-e32v2-alpha.1.zip**.
   Do not choose the automatically generated **Source code** files.
3. Extract the ZIP into **E32-test**. The file you will select for flashing is **e32v2-factory.bin**.

This single file contains the bootloader, partition layout, firmware and web interface.
You **do not need to flash the other `.bin` files separately**.
This file is **not** for the existing EMS-ESP web updater or a flasher that automatically adds EMS-ESP partitions.

## 5. Flash one file

**From this step onward, the current firmware and settings will be erased.** The backups and recovery route from steps 1–3 must be ready.

1. In ESPConnect, go to **Flash Tools → Flash Firmware**.
2. Under **Firmware binary (.bin)**, select the extracted **e32v2-factory.bin**.
3. Set **Flash offset** to exactly **`0x0`**. Do **not** choose an app/OTA offset preset.
4. Check **Erase entire flash before writing**.
5. Click **Flash Firmware** and double-check the filename and **`0x0`** in the confirmation.
6. Confirm with **Flash** and wait for successful completion with no errors.

Keep the cable connected and the browser open. **Do not restart the gateway yet:** complete step 6 first.
If an error or interruption occurs, do not connect it to the boiler. Save the log and have the failure checked before restoring or retrying.

## 6. Check that the firmware was written correctly

Before the first normal restart, go to **Flash Tools → Flash Integrity**:

| Field | Value |
| --- | --- |
| Start offset | `0x0` |
| Length (bytes) | `0xB80000` |

Click **Compute MD5**. For **alpha.1**, the result must be exactly:

```text
3b8e061b32ea05f1886a4993028bfc8c
```

This checks all **12,058,624 bytes** of the combined installation image on the chip.
If the result differs, **stop**: a correct write has not been proven.
This value applies only to this release. Settings may change after normal startup, so perform this check before the first restart.

## 7. Start the test firmware

1. Click **Disconnect**. Unplug the USB cable and reconnect it.
2. Keep the gateway **disconnected from the boiler/EMS bus**.
3. On your computer or phone, find the setup Wi-Fi network **OpenThermostat-xxxxxx**
   (the last six characters are unique per device).
4. Connect using the setup password **openthermostat**.
5. Open **http://10.10.10.1/** in your browser and sign in with **admin / admin**.
6. Choose your own web password under System before using the gateway further on a
   network (a `password-reset` command on the USB console restores the default).

**The web page should become accessible.** The LED does not need to blink: LED control is disabled in this test firmware.
This first test checks startup and the web interface, not working heating control.

## Restore the old firmware

This requires a complete, verified backup from **the same gateway**, without flash encryption or secure boot.

1. Keep the gateway disconnected from the boiler and reconnect it to ESPConnect using USB-C.
2. Select **e32-backup-a.bin** under **Flash Firmware**.
3. Set **Flash offset** to **`0x0`** and check **Erase entire flash before writing**.
4. Flash and wait for successful completion. Before restarting, read back the entire restored 16 MB twice using **Download Flash Region**, with start `0x0` and length `0x1000000`.
   Save the new files as **e32-restore-a.bin** and **e32-restore-b.bin**. **Do not overwrite the original backups.**
   Compare their hashes with the original backup; on Windows, from the same folder:

   ```powershell
   Get-FileHash .\e32-backup-a.bin, .\e32-restore-a.bin, .\e32-restore-b.bin -Algorithm SHA256
   ```

   All three hashes must be identical. On macOS/Linux, use the command from step 3 with these three filenames.
5. Restart only after the hashes match. Then check the old EMS-ESP web interface, settings, board profile and network.

**Do not reconnect to the boiler without checking first.** The old backup also restores the old transmission settings. Have those settings and the restoration checked before reconnecting the bus.
If restoration fails, use the [official recovery route](BBQKEES_E32V2.md#backup-before-any-future-physical-experiment) saved during preparation.

## If the connection fails

- Try another **data cable**, connect directly to the computer and fully insert the USB-C plug into the slightly recessed port.
- Close other serial programs and browser windows using the same port.
- Disconnect and reconnect at **115200** baud. If no port appears, check the USB driver according to the manufacturer's instructions.
- If the bootloader still does not connect, follow the BOOT/RESET instructions for your exact board. Do not bridge arbitrary pins.

## Verification and sources

This guide was checked against the release files, manufacturer documentation and **ESPConnect v1.1.23** source code.
The browser tool is maintained by an independent developer; we are not building a custom flasher.
**No physical flashing or restoration test has been performed on an E32 V2.** These instructions do not claim that this firmware already works on hardware.

- [BBQKees: E32 V2 using external USB-C, without a separate power supply](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2)
- [ESPConnect: usage and features](https://github.com/thelastoutpostworkshop/ESPConnect/tree/v1.1.23)
- [Detailed technical installation guide](BBQKEES_E32V2_TEST_RELEASE.md)
- [Hardware, full backup and recovery](BBQKEES_E32V2.md)
