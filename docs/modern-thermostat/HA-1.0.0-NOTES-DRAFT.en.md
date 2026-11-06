# HA 1.0.0 — the first stable release
<!-- user-release-notes:v2:en -->

The same code as HA 1.0.0rc7. Companion of E32 1.0.0 (the same code as
1.0.0-rc.5). Needs Home Assistant 2026.10.0 or newer.

## New

- **A normal release:** HACS now offers it as a regular update. The
  Pre-release switch is no longer needed for it.
- **What 1.0 of the integration brings:** everything from Home Assistant: rooms
  with week programs, house mode and presence, planned holidays, radiator
  valves, daily backups with restore and a daily summary. A dashboard that
  opens with a house card and says in plain words why each room heats, what
  the E32 learned and how it follows your boiler, a Connection page for
  diagnostics, and repairs that say what to do. Dutch, English and Polish.

## Fixed

- No changes since 1.0.0rc7.

## Updating

Update through HACS and restart Home Assistant, then install E32 1.0.0 from the
Firmware entity. HACS checks a repository added by URL only every 48 hours of
Home Assistant uptime, and not at start-up: "Update information" in the
OpenThermostat menu shows a new version at once.

- Settings, rooms and everything learned are kept. From 1.0.0rc7 nothing else
  changes.

## Limitations

Radiator valve control is not yet verified on real valves. EMS Classic boilers
only; EMS+ comes in 1.1. Pairing Bluetooth sensors is done on the E32. HACS
lists OpenThermostat as a custom repository.
