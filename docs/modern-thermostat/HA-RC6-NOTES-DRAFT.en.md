# HA 1.0.0rc6 — the companion of E32 rc.5: what the E32 knows, in Home Assistant
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.5 (install both). Needs Home
Assistant 2026.10.0 or newer.

## New

- **Knowledge** (a sensor on the E32 device): how much of your house the E32
  has learned, in %, and what it still has to learn in words ("It still has to
  see how fast the living room warms up"). The Learning and settings tab now
  starts with **What the E32 knows**: a ring with "The E32 knows your house:
  70 %" and the missing items.
- **Boiler response** (a sensor on the E32 device): Still listening, Learned,
  No return temperature, or E32 not controlling the boiler. Its attributes
  show how often the boiler held its temperature today, its own rest, the
  ceiling it learned for this outdoor temperature, the heat the house takes
  (kW) and kW per °C of water temperature, with one sentence: "Your boiler
  rests about 6 min each time it reaches its temperature; the E32 asks at most
  41 °C now, so it starts less often."
- **Yesterday compared with usual:** one notification per insight ("Yesterday
  used 35 % more gas per degree of cold than usual", with what can cause it)
  and the same list on the Learning and settings tab. It is information, not a
  Repair: dismiss it and it stays dismissed until the insight changes.
- **Water temperature by outdoor temperature:** a new chart card on the
  Learning and settings tab, with the standard line (dashed), the line learned
  for your house (solid), the point of now and the value at −10 °C. You can
  also add it to your own dashboard (`custom:openthermostat-heating-curve`).
- **In the learned overview:** the free heat a room gets from sun, cooking and
  people (when the E32's report for that room has room for it; the E32 page
  always shows it), and the Weather compensation line estimated from your
  house ("for now, learning more (2 of 6 steady periods)").
- English, Dutch and Polish texts for all of it.

## Fixed

- The integration itself has no fixes in this release. The step that publishes
  the releases now waits for GitHub to list a release or a file it has just
  created, the likely reason its first attempt failed for rc.4 and needed a
  re-run.

## Updating

1. Update OpenThermostat in HACS and restart Home Assistant. In HACS, switch
   **Pre-release** on for OpenThermostat, or the update is not offered.
2. Then install E32 1.0.0-rc.5 from the E32's Firmware entity and confirm the
   takeover again (Repairs, or Rooms on the E32).

Entity IDs and history are kept. The two new sensors read unknown, and the new
section stays hidden, until the E32 runs rc.5 and has reported what it knows.

## Limitations

Everything new needs the E32 on 1.0.0-rc.5. A boiler without a return
temperature gets no figure for the heat the house takes. 1.0.0 follows once
E32 rc.5 has run 14 days unchanged. Radiator valve control is not yet verified
on real valves. EMS Classic boilers only; EMS+ comes in 1.1. Writing boiler
settings comes after 1.0. Pairing Bluetooth sensors is done on the E32. HACS
lists OpenThermostat as a custom repository, not yet in the default HACS list.
