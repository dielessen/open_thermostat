# E32 V2 alpha.4 — Automatic restart after firmware update

Experimental bench-test prerelease. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This release is not approved for heating.**

- After a successful GitHub firmware install or manual app upload, the E32
  schedules its own restart after three seconds. No second confirmation or
  open browser is required. Failed updates do not schedule a restart; an active
  GitHub flash worker cannot be interrupted by the restart timer.
- The updater shows automatic restart, polls for the installed version and
  reloads the matching UI on version readback. SPIFFS behavior is unchanged.
- **Updating FROM alpha.3 or earlier still requires one manual restart**:
  that installation runs the old updater. Automatic restart applies to updates
  performed by alpha.4 onward.
- Preserves the alpha.3 Rooms spinner repair with the
  shipped Bootstrap CSS. The previous alpha.2 did not contain this correction.
- Rooms and Programs initial configuration reads time out after 10 seconds;
  failed reads show an error and explicit retry instead of endless loading or
  automatic program retry loops. Retry does not modify saved configuration.
- Regression coverage includes the actual combined tab page, real bundled CSS,
  initial request failures, recovery and nonresponding request timeouts.
- No changes to Home Assistant entity bindings, MQTT transport, room/program
  storage format, regulation, hardware profile or output safety blocks.

Inherited from earlier releases:

- Check/select compatible GitHub releases from the authenticated device UI.
- User-started HTTPS download, exact size/board/source/UI checks, SHA256 and
  native inactive-slot OTA with independent flash readback before boot selection.
- Web interface travels in the app image: ordinary updates no longer replace
  SPIFFS, rooms, programs or NVS settings. No credentials are embedded.
- Previous VALID-slot recovery and bounded native boot-health
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
