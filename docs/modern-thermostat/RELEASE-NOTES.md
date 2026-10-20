# E32 V2 alpha.2 — GitHub updates and simpler WiFi setup

Experimental bench-test prerelease. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This release is not approved for heating.**

- Check/select compatible GitHub releases from the authenticated device UI.
- User-started HTTPS download, exact size/board/source/UI checks, SHA256 and
  native inactive-slot OTA with independent flash readback before boot selection.
- Web interface travels in the app image: ordinary updates no longer replace
  SPIFFS, rooms, programs or NVS settings. No credentials are embedded.
- Explicit restart and previous VALID-slot recovery; bounded native boot-health
  confirmation. Physical update/rollback/power-loss acceptance remains open.
- Includes WiFi/Bluetooth modem-sleep repair, captive portal, automatic setup AP
  handoff, room lifecycle and legacy HA room-presence repairs from prior tests.

**Existing OpenThermostat E32 V2 test installation:** upload the standalone
`firmware.bin` once using its existing Firmware upload, then reboot. Do not
upload SPIFFS or erase flash for this transition. Use the matching 16MB layout.
`e32v2-update.json` / `RELEASE-SHA256SUMS.txt` identify the exact app bytes.

The ZIP also contains a separate `e32v2-factory.bin` for CLEAN USB installations
at 0x0. **That route deletes settings; never use the factory image as app OTA.**
Read `docs/modern-thermostat/GITHUB-UPDATES.nl.md` for procedure and limits.
