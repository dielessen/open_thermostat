# HA 1.0.0rc4 — <!-- pending: one-line title --> a tidier Configure menu and dashboard, and clearer reasons
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.3; the E32 itself is unchanged. Needs
Home Assistant 2026.10.0 or newer.

## New

- <!-- pending: Configure menu restructured: about 6 items, "← Back" and "Done", every setting still there (house mode, holiday, Smart warm-up, Weather compensation) -->
- <!-- pending: dashboard restructured into Overview, Rooms, Week program, Boiler, Learning and settings (plus Diagnostics) -->
- <!-- pending: per room, a status line says why it heats or not -->
- <!-- pending: the heating problem tile shows the reason -->
- <!-- pending: short cycling is shown as learning information, not as a problem -->
- <!-- pending: "Follow outdoor temperature" is now called Weather compensation; new setting "Water temperature in hard frost (-10 °C)" -->
- <!-- pending: plainer texts throughout -->

## Fixed

- <!-- pending: Repairs only appear for real problems -->
- <!-- pending: HACS no longer offers the main branch (a commit such as 5043af7) as an update -->

## Updating

1. Update OpenThermostat in HACS and restart Home Assistant. In HACS, switch
   **Pre-release** on for OpenThermostat, or the update is not offered.
2. The E32 stays on 1.0.0-rc.3: no firmware update and no need to confirm
   the takeover again.
3. If HACS shows a commit such as 5043af7 as the installed version, download
   the release version once (Redownload, pick 1.0.0rc4).

Entity IDs and history are kept. <!-- pending: any renamed entity or removed dashboard view -->

## Limitations

Radiator valve control is not yet verified on real valves. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
HACS lists OpenThermostat as a custom repository, not yet in the default
HACS list. <!-- pending: further limitations -->

