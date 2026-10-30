# USB installation, backup and recovery

**Installing OpenThermostat for the first time?** Follow the
[installation guide](INSTALL.md). It covers downloading the release, flashing
`e32v2-factory.bin` over USB, the first start and everything after it.

This page covers the less common USB tasks: a full backup before the first
installation, a clean reinstall, and going back to the original firmware.

| Task | Where |
| --- | --- |
| First installation on a new E32 V2 | [Installation guide, section 2](INSTALL.md#2-install-the-firmware-on-a-new-e32-usb) |
| Normal firmware update (keeps settings) | [Installation guide, section 9](INSTALL.md#9-updates) |
| Forgotten web password (`password-reset`) | [Installation guide, section 10](INSTALL.md#10-forgotten-password-and-wi-fi-recovery-over-usb) |
| New router or Wi-Fi password (`setup`) | [Installation guide, section 10](INSTALL.md#10-forgotten-password-and-wi-fi-recovery-over-usb) |
| Full backup before the first installation | [Below](#make-a-full-backup-first) |
| Clean reinstall (erases all settings) | [Below](#clean-reinstall) |
| Back to the original EMS-ESP firmware | [Below](#go-back-to-the-original-firmware) |

The steps below use the browser tool
[ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/) in Chrome
or Edge, as in the installation guide. ESPConnect is made by an independent
developer. `esptool` can do the same; see the
[hardware guide](BBQKEES_E32V2.md#backup-before-any-future-physical-experiment)
for its backup commands.

## Make a full backup first

A BBQKees E32 V2 usually comes with EMS-ESP. Installing OpenThermostat erases
it. Make this backup if you may want to go back.

1. In the EMS-ESP web interface, download its settings (**Settings →
   Upload/Download**; the wording may differ between EMS-ESP versions), and take
   a screenshot of its system information (version and board profile).
2. Disconnect the E32 from the boiler and any other power supply, and connect
   its USB-C port to your computer.
3. Open ESPConnect, connect at **115200** baud and check **Device Info**: an
   **ESP32** with **16 MB** flash. In the security information, **Flash
   Encryption** and **Secure Boot** must be off. If they are on, or you cannot
   tell, stop: a raw backup may not be restorable.
4. Go to **Flash Tools → Flash Backup & Erase**. Enter start offset `0x0` and
   length `0x1000000` (the full 16 MB). Click **Download Flash Region** and
   save the file as `e32-backup-a.bin`. This takes a while; keep the computer
   awake and the cable connected.
5. Read it a second time with the same values and save it as
   `e32-backup-b.bin`. Do not copy the first file.
6. Both files must be exactly **16,777,216 bytes** and identical. On Windows,
   open PowerShell in that folder and run:

   ```powershell
   Get-FileHash .\e32-backup-a.bin, .\e32-backup-b.bin -Algorithm SHA256
   ```

   On macOS use `shasum -a 256 e32-backup-a.bin e32-backup-b.bin`, on Linux
   `sha256sum e32-backup-a.bin e32-backup-b.bin`. The two hashes must be the
   same.

Keep a copy somewhere other than this computer. A backup can contain your
Wi-Fi and other passwords: never upload it to GitHub or share it.

## Clean reinstall

Flashing `e32v2-factory.bin` again gives a factory-fresh E32: Wi-Fi, password,
rooms, paired sensors and all other settings are erased. Use it only when an
ordinary update or the USB commands cannot help. Follow
[section 2 of the installation guide](INSTALL.md#2-install-the-firmware-on-a-new-e32-usb)
and then continue with the first start. If Home Assistant was connected, use
**Configure → Connect E32** again afterwards.

## Go back to the original firmware

You need a complete, verified backup of **this same E32** (see above), or
BBQKees' official EMS-ESP recovery route.

1. Disconnect the E32 from the boiler and connect it to ESPConnect over USB.
2. Go to **Flash Tools → Flash Firmware**, select `e32-backup-a.bin`, set the
   offset to `0x0`, tick **Erase entire flash before writing** and flash.
3. Before restarting, read the full 16 MB back (start `0x0`, length
   `0x1000000`) into a new file such as `e32-restore-a.bin`, without
   overwriting the backups. Its SHA-256 must equal that of the backup.
4. Restart and check the EMS-ESP web interface, its settings, board profile
   and network.

Without a working backup, reinstall EMS-ESP as BBQKees describes in its
[firmware update and downgrade guide](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2)
and import the settings you downloaded in step 1 of the backup.

Check the EMS-ESP settings before you connect the E32 to the boiler again: a
restored backup also restores EMS-ESP's own settings for sending on the bus.

## If the USB connection fails

- Use a USB-C cable that carries data, plug it in fully and connect directly
  to the computer.
- Close other programs and browser tabs that use the same serial port.
- If no port appears, install the USB driver BBQKees recommends for the
  gateway.
- If the tool still cannot connect, follow BBQKees' instructions for starting
  the board in download mode. Do not bridge pins on the board.

More technical background: [E32 V2 hardware, backup and recovery](BBQKEES_E32V2.md).
