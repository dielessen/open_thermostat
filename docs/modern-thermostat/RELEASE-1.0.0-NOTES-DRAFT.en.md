# E32 V2 1.0.0 — the first stable release
<!-- user-release-notes:v2:en -->

The same code as 1.0.0-rc.5, which has controlled the boiler in the
developer's home since 1 November. It is released as 1.0.0 without the planned
14-day trial; fixes follow where needed. Nothing was added or changed; only
the version name is new. Install it with HA 1.0.0, the same code as 1.0.0rc7.

## New

What 1.0 brings, from the release candidates:

- **A thermostat that tunes itself:** it learns per room how fast it warms up
  and cools down, what your boiler does, how your house loses heat and how
  much free heat sun and people give. Smart warm-up is on by default and
  starts early from the first morning, with the coolest water that still
  gets the room warm on time; it checks every morning how it went. The pages
  say in plain words what it knows and what it still lacks.
- **Holidays and away:** plan up to 8 holidays ahead with their own
  temperature; away per room and for the whole house, following who is home.
- **Takeover with a guided boiler test:** a trial run alongside your
  thermostat, then one attended step to active control, with frost protection
  always on and an easy way back.
- **Radiator valves** through Zigbee2MQTT or Home Assistant, set per room.
- **Backups** of the settings, daily and automatic through Home Assistant,
  and a restore on a replacement E32.
- Weather compensation, a daily summary, and "Yesterday in figures" with what
  stood out compared with your usual days.

## Fixed

- No changes since 1.0.0-rc.5.

## Updating

From 1.0.0-rc.5, while someone is home. First install HA 1.0.0 (HACS) and
restart Home Assistant, then press Install on the E32's Firmware entity. Then
confirm the takeover again: a firmware change clears it, and until then the
E32 keeps only frost protection. Repair "Confirm again that the E32 may
control the boiler", or Rooms on the E32.

- HACS checks a repository added by URL only every 48 hours of Home Assistant
  uptime, and not at start-up. "Update information" in the OpenThermostat menu
  shows a new version at once.
- Settings, rooms, programs, sensors, valves and everything it learned are
  kept.

## Limitations

A boiler that does not report the return temperature learns no absorbed heat;
everything else works. The boiler is listened to only while the E32 controls
it, and what it learned from the boiler is not in a settings backup (it is
learned again within days). Radiator valve control is not yet verified on real
valves. Behind an EMS adapter that leaves byte 7 of telegram 0x18 empty (such
as the Bosch EasyControl Adapter) the three-way valve position cannot be seen.
EMS Classic boilers only; EMS+ comes in 1.1. Writing boiler settings comes
after 1.0. Pairing Bluetooth sensors is done on the E32. The E32's charts start empty again after a restart.
