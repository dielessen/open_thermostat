# Home Assistant parity audit for rc.3

Owner, 3 Nov 2026: "Everything that can be configured must also be possible from Home Assistant.
Make rc.3 a lot more complete."

This audit lists every setting a user can change on the E32 web pages (`data/html/*.html` and their
scripts, the routes in `src/REST.h`) and says where it is in Home Assistant. Base:
`release-1.0` 88edbb8 (E32 1.0.0-rc.2, HA 1.0.0rc2). Branch: `rc3-ha-parity`.

Decisions:

- **ALREADY**: Home Assistant can set it today.
- **ADD (rc3-ha-parity)**: added on this branch.
- **COVERED by `<branch>`**: another rc.3 branch adds it.
- **LATER**: worth adding, but not in this branch (reason given).
- **E32 ONLY**: stays on the E32 on purpose (reason given).

"Configure" means Settings → Devices & services → OpenThermostat → Configure.

## Overview and Home (house)

| E32 setting (page) | Home Assistant today | Decision |
|---|---|---|
| House mode: automatic / at home / away / holiday (Home) | "House mode" select on the E32 device, dashboard | ALREADY |
| Holiday until (Home) | "Holiday until" datetime on the E32 device | ALREADY |
| Away temperature for the house (Home) | "Away temperature" number on the E32 device; Configure → Home → Presence | ALREADY (number); the form is COVERED by `rc3-ha-config` |
| Presence: who is home (Home) | Configure → Home → Presence (the E32 only hears "someone home") | ALREADY (it can only be set in HA) |
| Room override / boost / until next switch point (Overview) | climate entity per room, actions `set_room_override` / `clear_room_override` | ALREADY |
| Water temperature limits, lowest/highest flow (Home → Heating settings) | Configure → Home → Heating and boiler | ALREADY |
| Follow outdoor temperature (heating curve) (Home) | switch "Weather-compensated heating curve" | ALREADY |
| Water temperature at −10 °C outside (Home) | select "Flow at −10 °C" | ALREADY |
| "Warm on time with the coolest water" (learned flow, optimum start) (Home) | switch on the E32 device | ALREADY; rename and default on COVERED by `rc3-warm-on-time` |
| Comfort and boiler care: each automatic knob automatic or set by you (7 knobs) (Home) | read-only (learned overview sensor) | **ADD (rc3-ha-parity)**: Configure → Home → Comfort and boiler care |
| Comfort and boiler care: the three fixed knobs (curve correction, accepted warm-up time, night saving) (Home) | read-only | **ADD (rc3-ha-parity)**, same step |
| Back to automatic for all / back to start values (Home) | — | **ADD (rc3-ha-parity)**, same step, with a confirmation |
| Energy: boiler power, gas meter, gas price, outdoor temperature (Home says "set in HA") | Configure → Home → Energy | ALREADY (HA only) |

## Rooms

| E32 setting (page) | Home Assistant today | Decision |
|---|---|---|
| Add / remove room, name, state (active / inactive / inactive until), heating type (Rooms) | Configure → Rooms; select and datetime per room | ALREADY |
| Temperature sources (HA entities, Bluetooth sensors, order) (Rooms) | Configure → Rooms → the room (also the Bluetooth sensor's room assignment) | ALREADY |
| Setting device in HA, fallback temperature, target limits (Rooms) | Configure → Rooms → the room; fallback number per room | ALREADY |
| Week program per room (Rooms) | Configure → Rooms → the room; the week planner card | ALREADY |
| Comfort / eco / night levels of the week planner (Rooms) | the week planner card on the dashboard (stored per room) | ALREADY |
| Window and door contacts, pause delay per room | Configure → Rooms → the room | ALREADY (HA only) |
| Persons per room | Configure → Rooms → the room → Persons | ALREADY; away temperature per room COVERED by `next-room-away` |
| Radiator valves per room, model, "drive these valves from the E32" (Rooms) | Configure → Rooms (valves), valve switch per room | ALREADY; valves as a section of the room form and valve choice by entity COVERED by `rc3-ha-config` |
| Defaults for rooms without a program, override duration | Configure → Home → Defaults for rooms and timing | ALREADY |

## Boiler

| E32 setting (page) | Home Assistant today | Decision |
|---|---|---|
| Boiler model (display model profile) (Boiler → My boiler) | not settable | **ADD (rc3-ha-parity)**: Configure → Home → Heating and boiler → Boiler model (catalog of `rc3-boiler-name`, merged here); the boiler device is renamed at once |
| Attended boiler test (prepare, start, stop, close fault) (Boiler) | — | E32 ONLY: someone must stand at the boiler and watch it; test memory COVERED by `rc3-boiler-test` |
| First takeover confirmation ("my old thermostat is disconnected") (Rooms → Active control) | — (only the re-confirmation after an update, Repairs) | E32 ONLY: it is a physical statement about the wiring at the boiler |
| Give control back to the old thermostat (handover off) (Rooms) | — | E32 ONLY: the old thermostat must be reconnected at the boiler first; from afar it could leave the house without heat |
| "Show anyway" for a boiler field the profile marks as not fitted (Boiler) | — | LATER: presentation only; low value next to the HA entity settings |
| EMS boiler settings write (All boiler data) | — | LATER: planned after 1.0 with verified writes (EMS writable settings plan; branch `next-ems-setting-descriptions`) |

## System

| E32 setting (page) | Home Assistant today | Decision |
|---|---|---|
| Wi-Fi network and password, Wi-Fi setup (Settings, setup) | — | E32 ONLY: a wrong value cuts the connection HA would need to put it right; Wi-Fi recovery is on the device |
| Hostname, listen port, Wi-Fi or Ethernet (Settings → Connection) | — | E32 ONLY: changes the address HA connects to |
| MQTT broker, user, password, client ID, base, keep-alive, interval (Settings → MQTT) | — | E32 ONLY: this is the link HA uses; HA checks it at Connect E32 and explains how to set it |
| HA link in trial run, adapter ID, installation profile (Settings → Home Assistant) | Configure → E32 connection (written by HA itself) | ALREADY |
| E32 password | Repairs "Choose a new E32 password" (factory password); re-authentication after a change on the E32 | ALREADY for those two; any other change E32 ONLY (security: HA never chooses a new password unasked) |
| Time zone (Settings → Time) | — | **ADD (rc3-ha-parity)**: Configure → Advanced and diagnostics → E32 time zone (Home Assistant's own zone first; one restart), and a Repairs issue "The E32 uses another time zone" with a one-step fix |
| NTP on/off, NTP server, POSIX text, UTC offsets (Settings → Time, advanced) | — | E32 ONLY: technical; the time zone above covers the everyday need |
| Battery clock, EMS bus on/off, EMS forwarder (Settings → Advanced) | — | E32 ONLY: hardware and diagnosis switches; switching the bus off from afar stops the heating data |
| Bluetooth scan time and interval (Settings → Advanced) | — | E32 ONLY: radio timing, normally never changed |
| Debug log stream (socket) (Settings → Advanced), debug settings | — | E32 ONLY: developer tools |
| Legacy OpenWeatherMap (Settings, legacy mode only) | Configure → Home → Energy (outdoor temperature) | ALREADY (the HA route replaces it) |
| Backup and restore (System → Backup) | daily backups, button "Back up E32 settings now", Configure → Advanced → Restore settings to this E32 | ALREADY |
| Firmware update, check (System → Firmware update) | update entity (install over HA) | ALREADY |
| Firmware rollback, file upload (/ota, /otafs) (Firmware update) | — | E32 ONLY: recovery actions done while watching the device |
| Restart (System, after saves) | — | **ADD (rc3-ha-parity)**: button "Restart E32" (configuration) on the E32 device |
| Syslog forwarding: on, server, port, level, E32 / boiler-bus messages, mark interval (Diagnostics and system log) | — | **ADD (rc3-ha-parity)**: Configure → Advanced and diagnostics → E32 system log |
| Level kept on the E32 log page (Diagnostics and system log) | — | **ADD (rc3-ha-parity)**, same step |
| Clear the local log, end idle web sessions (Diagnostics) | HA diagnostics download | E32 ONLY: on-device housekeeping; HA itself never leaves sessions open |
| Bluetooth sensors: scan, pair, bindkey (System → Bluetooth sensors) | — | E32 ONLY: pairing needs the sensor next to the E32 and the key is a secret |
| Bluetooth sensor name, forget a sensor (System → Bluetooth sensors) | — | **ADD (rc3-ha-parity)**: Configure → Advanced and diagnostics → Bluetooth sensors (changes collected, one save = one E32 restart ~30 s later); room assignment is ALREADY in the room form |
| Page language (all pages) | — | not a device setting: the browser's choice; HA uses its own language |
| Device name | Configure → Dashboard and name (the HA name) | ALREADY; the E32 hostname is E32 ONLY (above) |
| Hardware page, GPIO and I²C tests, legacy programs and curve pages | — | E32 ONLY: legacy mode and bench tools |

## What rc3-ha-parity adds

1. **Configure → Home → Comfort and boiler care** (`e32_care.py`): the overview of all ten knobs in
   plain words with "(automatic)", "(set by you)" or "(standard value)"; "Change a setting" (the
   automatic knobs: Automatic on/off plus your value; the fixed knobs: a value); "Back to automatic
   for all" (only while one is set by you) and "Back to start values", both with a confirmation.
   Requests are the E32 page's own partial changes on `POST /config/heating/flow`:
   `{"tuning": {knob: value}, "tuning_manual": [...]}`, `{"tuning_manual": [...]}`,
   `{"tuning": {knob: value}}`, `{"tuning_manual": []}`, `{"tuning": null}`. Burner times are
   entered in minutes and stored in seconds, as on the E32 page. Firmware without
   `tuning_manual` (before rc.2) gets "update the E32 first" and, once known, the menu entry is
   hidden. The dashboard's learned note now points here.
2. **Configure → Advanced and diagnostics → E32 system log** (`e32_system.py`): syslog on/off,
   server (IPv4, checked like the E32 does), UDP port, level, the E32's own and the boiler-bus
   messages (only on firmware that reports them), the level kept on the E32, the mark interval.
   One `POST /config/logging` with all fields; the answer must match.
3. **Configure → Advanced and diagnostics → E32 time zone** (`e32_system.py`): the E32 page's
   list, Home Assistant's own zone pre-selected. In one sign-in: read `/config/device` (ETag), save
   it back with only `timeZone` changed (the redacted secrets stay on the E32; a change made on the
   E32 meanwhile is refused with 412 and nothing is written), read back, restart.
4. **Configure → Home → Heating and boiler → Boiler model** (`e32_boiler_model.py`): Heating and
   boiler is now a menu (Water temperature limits, Boiler model). The list is the shipped catalog
   (`ems_products.json` `boiler_models`, now with `selectable`): the models a new choice may pick,
   the current one, and "No boiler selected yet". `POST /config/boiler-display {"model": id}`, the
   answer is the read-back; the boiler device is renamed at once (ems_devices, `MODEL_CHOSEN`).
5. **Configure → Advanced and diagnostics → Bluetooth sensors** (`e32_bluetooth.py`): rename and
   forget, collected in the flow and saved together, because each save restarts the E32 about 30 s
   later. The save reads `/config/bluetooth` again in the same sign-in, checks the list is still
   the one shown, and posts the remaining sensors with that ETag and `"key_action": "keep"` (no
   bindkey passes through HA). Pairing stays on the E32. The forget form lists the rooms that measure
   with a sensor.
6. **Repairs "The E32 uses another time zone"** (`e32_system.py`): checked from the daily settings
   backup (its network section), the time zone step and every change of Home Assistant's time zone;
   only for a Home Assistant zone the E32 lists. The fix sets the E32 to Home Assistant's zone (same
   write as the step, one restart); the issue clears itself when the zones match.
7. **Button "Restart E32"** (`e32_system.py`, device class restart, entity category config): the
   E32's controlled restart (`POST /updates/reboot`), refused with a clear message while it updates.

Every request goes through the room-plan link's lock and one sign-in that ends with a logout; a
change waits for a free E32 web session (`claim`), a read does not. All texts are in English, Dutch
and Polish; `strings.json` equals `translations/en.json`. No entity is renamed or removed; the only
new entity is the restart button (unique ID `<prefix>_e32_restart`).

## Open questions

- A time zone changed on the E32 page is seen by the next daily backup (at most a day later), not at once.
