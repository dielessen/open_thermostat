# HA 1.0.0rc5 — holidays, yesterday in figures and a safer link to the E32
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.4 (install both). Needs Home
Assistant 2026.10.0 or newer.

## New

- **Holiday planner** (Configure → House → House mode and holiday): plan
  holidays ahead with their own "Temperature on holiday", stop or shorten a
  running one; the Overview shows the next holiday.
- **Yesterday** (Learning and settings): heating hours, burner starts per
  heating hour, short burner runs, gas for heating (estimate), degree-days,
  and per room "warm 12 min late · 0.3 °C too warm". Also as sensors, created
  once the E32 has a figure for them.
- **Smart warm-up in plain words:** "starts at 07:40 (estimate; it learns
  from every morning) so it is 21 °C at 09:00", "the warm-up time is learned;
  the coolest water is still being learned", and "Yesterday warm at 09:12
  (12 min late); tomorrow 10 % earlier." In the learned overview and in the
  climate entity's smart_warm_up attribute.

## Fixed

- An empty room plan from the E32 (for example right after its restart) no
  longer removes the rooms' devices and entities; a room is removed only
  when two reads a minute apart both miss it.
- One sign-in path to the E32: a wrong E32 password is tried once and shows
  one repair instead of a storm of failed logins from every part of the
  integration; a saved password clears it. A write waiting for a free
  session no longer blocks reads.
- The trial-run (shadow) connection leaves the heating hub's telemetry alone,
  so a flood of retained messages no longer fills its queue.
- Broker outages are logged once instead of every 15 seconds; a failing
  listener logs at most once a minute; the dashboard is rebuilt only for this
  integration's own entities, not for every change in Home Assistant.
- The legacy set_comfort service is offered only for older Home Assistant
  rooms and explains itself on an E32 room.

## Updating

1. Update OpenThermostat in HACS and restart Home Assistant. In HACS, switch
   **Pre-release** on for OpenThermostat, or the update is not offered.
2. Then install E32 1.0.0-rc.4 from the E32's Firmware entity and confirm the
   takeover again (Repairs, or Rooms on the E32).

Entity IDs and history are kept. The Yesterday sensors appear once the E32
has measured a day.

## Limitations

Radiator valve control is not yet verified on real valves. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
Pairing Bluetooth sensors is done on the E32. HACS lists OpenThermostat as a
custom repository, not yet in the default HACS list.
