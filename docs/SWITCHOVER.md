# Attended switch-over: the E32 takes over the boiler

Status: draft procedure (29 October 2026), not yet carried out. The detailed
engineering checklist is in Dutch:
[OVERSCHAKELING.nl.md](modern-thermostat/OVERSCHAKELING.nl.md).

Up to beta.18 the E32 runs in **shadow mode**: it calculates the boiler request
but the existing thermostat (here a tado, EMS address 0x17) keeps controlling
the boiler. Active control is built in (`ActiveHeatGuard`) but locked by
`board::emsActiveHeatAllowed = false`. The switch-over is done once, in one
afternoon, with the owner present at the boiler.

Reference installation: Nefit EcomLine HRC 22H behind a Bosch EasyControl
Adapter (EMS 0x08); living room floor heating with its own manifold, pump and
thermostatic valve (~50 °C); three radiators upstairs on the same circuit.

## Decide before the switch-over

1. **Boiler heating limit after a restart.** The E32 only knows the limit
   (type 0x16) when it was reported this boot; until now only the tado asked
   for it. Without it the E32 requests no heat and gives no frost protection.
2. **Persisting the "thermostat disconnected" confirmation.** It is kept in RAM
   only: after every restart the E32 sends nothing until the owner confirms
   again.
3. **Burner feedback counts hot water.** A hot-water tap can mask a boiler that
   does not respond to a heating request (warning only).
4. **Supervisor restarts while active.** Wi-Fi lost 15 min, broker lost 15 min,
   no IP traffic 3 min and Bluetooth silent 30 min each restart the E32, which
   with (2) ends active control.
5. **Disconnect the tado physically, or set it to not control.** Any 0x1A from
   another address blocks the E32, even a zero request, so "not controlling"
   only works if the tado then sends no 0x1A at all.
6. **After measuring:** what the EasyControl Adapter does when the E32 stops
   sending (holds the last request or times out), and whether that is
   acceptable for unattended use.
7. **Build Home Assistant alerts** for the active state and warnings; the HA
   "Boiler request (E32)" sensor shows the calculated, not the sent, request.

## Prerequisites

- Shadow period passed: 72 h without hang or restart, at least 10 compared
  heating periods, similar decisions, Bluetooth fallback has taken over once.
- A published beta with the gate opened and decisions 1–5 and 7 implemented.
- Backups: Home Assistant, the room plan (`GET /config/heating`), the shadow
  firmware ZIP for local upload, photos of the wiring.
- Boiler pressure 1.1–2.5 bar, no active fault; owner at the boiler; an
  independent stop (boiler heating switch or main switch).
- Room plan: living room active (tado via HA, then Bluetooth), week program
  and "temperature without Home Assistant" set, bathroom inactive, flow 30–60 °C.

## Steps

1. Disconnect the tado from the adapter while it requests no heat (boiler off
   while rewiring). It stays in Home Assistant as a sensor and setpoint.
2. Observe 10–15 minutes without any controller: boiler telemetry still
   arrives, the boiler stays idle, hot water still works.
3. If the E32 restarted, read the boiler heating settings (My boiler).
4. Rooms → Active control → **My thermostat is disconnected from the boiler —
   let the E32 take over**. Expected within a minute: "The E32 controls the
   boiler.", no warnings.

## Test matrix

| Test | Pass when |
| --- | --- |
| Start | Heating active within 2 min (up to ~10 min boiler anti-cycling), flow rises ≥ 3 °C within 15 min |
| Stop | Minimum burner time 5 min respected; heating off within ~30 s of the first zero; no restart within 5 min |
| Modulation | Flow follows the request (30–60 °C) within ±3 °C; never above the plan limit, 60 °C or the boiler limit; 60 s refresh keeps heating continuous |
| Hot water while heating | Hot water has priority; heating resumes within 5 min; no stop or warning |
| Hand-back button | Zero for one minute, then shadow mode; heating off |
| Home Assistant off | Bluetooth sensor and E32 week program take over within 15 min; control continues |
| Bluetooth sensor off | Stale after 15 min, no heat request plus warning after 30 min, automatic resume when it returns |
| Wi-Fi off (10 min) | Control continues; no restart |
| Frost protection (simulated) | Minimum flow when any room reads < 8 °C, off at 9 °C |
| E32 restart / power cut | The adapter's behaviour without requests is measured and timed (hold vs time-out) |
| Foreign controller | Reconnecting the tado makes the E32 stop and warn by itself |
| Hand back to the tado | Shadow mode; the tado's requests and 55 °C hot water return |

## Abort and roll back

Abort on flow above 62 °C while heating, pressure outside 1.0–2.7 bar, a
boiler fault, short cycling, unexplained `transmit_failed` or
`boiler_no_response`, a foreign request while the tado is disconnected, or
any doubt. Roll back in this order: **Hand back to the thermostat**, then
reconnect the tado; if the page is unreachable, power off the E32 and
reconnect the tado; if the boiler keeps heating, switch heating off at the
boiler; reinstall the shadow firmware if a firmware fault is suspected.

## Afterwards

Record times, screenshots, `/status/heating` snapshots, the black box after
each restart and the Home Assistant history. Then one to two weeks of daily
checks (state and warnings, restarts, room temperature against target, burner
starts and short cycling, flow range, pressure, hot water, daily gas use)
before a first non-beta release.
