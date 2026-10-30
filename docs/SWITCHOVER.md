# Attended switch-over: the E32 takes over the boiler

Status: procedure for beta.19 (the 1.0 candidate), updated 29 October 2026,
not yet carried out. Applies to EMS Classic boilers only. The owner's
engineering checklist for the reference installation is in Dutch:
[OVERSCHAKELING.nl.md](modern-thermostat/OVERSCHAKELING.nl.md). The live
monitor for the first 48 hours is in [tools/switchover](../tools/switchover/README.md).

Until the switch-over the E32 runs in **shadow mode**: it calculates the
boiler request but your existing thermostat keeps controlling the boiler. The
switch-over is done once, in one afternoon, with someone at the boiler. After
it, the E32 is the only controller of the boiler.

Items marked *(beta.19, verify on the device)* are built and covered by the
host and soak tests, but only a live bus recording or the switch-over day
itself can confirm them. Check them against the published release before you
start.

Values such as addresses, temperatures and intervals in examples come from the
reference installation (an EMS Classic boiler behind a Bosch EasyControl
Adapter, with a tado thermostat as the existing controller). They are
examples; use your own.

## How active control behaves

- **One controller.** Your existing thermostat keeps control until it is
  **physically disconnected** from the boiler bus. Any heat request (EMS type
  0x1A) from another controller after the takeover makes the E32 stop, warn and
  forget the confirmation.
- **Explicit confirmation.** The E32 takes over only after you press
  **My thermostat is disconnected from the boiler — let the E32 take over** on
  its Rooms page. The confirmation is kept across restarts, stored with the
  firmware it was given under (version and build hash). It is cleared by a
  foreign 0x1A, by handing back, and by any firmware change, even a rebuild of
  the same version.
- **After a restart.** With a stored confirmation the E32 asks heat (or frost
  protection) again only after **2 minutes of continuous reception from the
  boiler without a foreign 0x1A** (boiler frames at most 30 s apart; about
  130 s after boot), and within about a minute of the first valid room
  reading. A foreign 0x1A in that window clears the confirmation before the
  E32 sends anything, so a thermostat reconnected while the E32 was off always
  wins.
- **Measurement loss.** Without a usable room temperature for 30 minutes the
  E32 asks no heat. It resumes by itself when a reading returns.
- **Flow.** As low as the rooms allow, up to the plan maximum, and never above
  `min(plan maximum, 80 °C, the boiler's own maximum)`. The E32 reads the boiler's
  maximum (type 0x16) itself: one read-only request `0B 88 16 00 02` at the
  first bus poll after boot, again when no 0x16 report was seen for 6 hours
  (an answer to another master counts too), retried after 5 minutes when
  unanswered. Without it, it asks no heat (`boiler_limit_unknown`). The flow
  options (weather curve, learned flow) stay within the same ceiling.
  *(beta.19, verify on the device: a bus recording after a restart)*
- **Frost protection.** Minimum flow when any room, including an inactive one,
  reads below 8 °C, off again at 9 °C.
- **No automatic restarts while active.** While the E32 owns the boiler, Wi-Fi,
  MQTT broker or Bluetooth problems no longer restart it (no `wifi_lost`,
  `broker_lost`, `network_dead` or `bluetooth_silent`). Only a real hang (loop
  stall, watchdog) or a stuck update does.
- **Planned restarts withdraw first.** Before a restart it plans (an update,
  a firmware upload from Home Assistant, Restart device, new Bluetooth
  settings, a settings restore, a controlled restart or a rollback of
  unconfirmed firmware) the E32 stops with its zero window and restarts once a
  zero was delivered, at most 90 s later; until then it does not take over
  again. In shadow mode nothing changes.
- **The active gate.** Released firmware ships with active control locked
  (`board::emsActiveHeatAllowed = false`). It is opened only on the switch-over
  day, in a separate, explicitly approved build that differs only in that
  constant. Until then the Rooms page says "Active control is not enabled in
  this firmware."

States (Rooms → **Active control**, and `GET /status/heating` → `active.state`):

| State | Page text | Sends to the boiler |
| --- | --- | --- |
| `shadow` | Shadow mode: your thermostat controls the boiler. | nothing |
| `awaiting_confirmation` | Waiting for your confirmation that your thermostat is disconnected from the boiler. | nothing, **not even frost protection** |
| `arming` | Taking over: waiting for fresh room readings and the boiler bus. | nothing: at least 60 s after a boot; with a confirmation restored after a restart, until 2 min of boiler reception without a foreign 0x1A (about 130 s after boot; `active.confirmation.restored`, `listened_s`) |
| `active` | The E32 controls the boiler. | its request every 60 s, at once on start and stop |
| `stopped_measurement_lost` | No room measurements: the E32 asks the boiler for no heat until a reading returns. | zero; resumes by itself |
| `stopping` | Stopping: the E32 asks the boiler for zero for one minute. | zero every 10 s until delivered |
| `blocked_foreign_controller` | Stopped: another controller sent a boiler request after the takeover. | nothing; confirm again after fixing it |

Warnings (`active.warnings`): `foreign_controller`, `measurement_lost`,
`boiler_no_response` (15 min of requested heat without burner or a 3 °C flow
rise), `transmit_failed` (3 min without a successful send),
`boiler_limit_unknown`.

Where to look:

| What | E32 page | REST | MQTT (`<prefix>/v1/fw/telemetry/…`) | Home Assistant |
| --- | --- | --- | --- | --- |
| State, request, last sent, warnings | Rooms → Active control | `/status/heating` → `active` | `heating` | Heating problem (after 5 min) |
| Confirmation kept | — | `active.awaiting_confirmation`, `active.confirmation {age_s, restored, listened_s}`, `active.confirmation_stored` | `heating` | — |
| Boiler maximum | Rooms (flow limits) | `active.boiler_limit {flow_c, age_s, reads}` (`reads`: the E32's own 0x16 requests this boot) | `heating` | — |
| Rooms | Rooms | `rooms[]` | `heating` | Temperature, Target temperature, Control status, Heat demand |
| Boiler | Boiler | `/status/ems/telemetry` → `fields` | `boiler_fields` | Flow temperature, Selected flow temperature, Heating active, Hot water active, Burner modulation, Water pressure |
| Starts | — | `/status/heating` → `burner` | `heating` | Burner starts last hour, Burner short cycling |
| Restarts, memory, MQTT | System → System log | `/status/logs` → `previous_boot`, `runtime` | `device_status` | uptime |

"On the bus" in the tests below means what the boiler reports back: its
**Selected flow temperature** (from its 0x18 monitor) follows the E32's request,
`transport.transmitted_frames` grows while active, and the age of the last
foreign 0x1A keeps growing. Also check the boiler's own display.

## Prerequisites

- **Shadow period passed** (at least 3 days, preferably 5):
  1. at least 72 hours without a hang or restart;
  2. at least 10 heating periods compared, including a night setback, a
     morning warm-up and a period without demand;
  3. similar decisions: heat at about the same moments (minutes apart), flow
     in the same range, not more on/off cycles than the thermostat;
  4. the sources work, and a fallback source (for example a Bluetooth sensor)
     has taken over at least once.
  Without an EMS thermostat to compare with, judge the period on the room
  temperatures and the calculated request.
  `tools/switchover/shadow_exit.py` checks these criteria read-only from the
  Home Assistant history (and optionally the E32's MQTT topics) and prints
  PASS, FAIL or WAIT (not enough data yet) for each; see its README.
- The release with the gate **closed** installed and stable in shadow mode for
  at least 24 hours; host tests and the soak test green.
- After an E32 restart in shadow mode, `active.boiler_limit.flow_c` is known
  and `reads` is at least 1 (the E32 read 0x16 itself).
- MQTT is stable: `mqtt_budget_disconnects` does not grow over 24 hours, and the
  minimum free internal heap stays at or above 20000 bytes.
- The room plan: the rooms to heat are active with a fresh source, a week
  program and a "temperature without Home Assistant", unused rooms are
  inactive, and the flow limits suit the emitters (floor heating without a
  mixing valve usually at most 45–50 °C).
- Someone at the boiler, an independent stop (the boiler's heating switch or
  main switch), normal water pressure, no active fault, and a day with heat
  demand.

## Preparation

1. **Backups:** Home Assistant (if used), `GET /config/heating` and
   `GET /config/heating/flow`, the Bluetooth pairings.
2. **Known-good firmware to fall back to:** the released build with the gate
   closed (and the previous release) as files on your laptop, so you can
   reinstall it through System → Firmware update without internet.
3. **Reconnecting the old thermostat:** photograph the wiring at the boiler or
   its adapter, label the thermostat's two wires and the E32's wires, and keep
   connectors ready. Put the hand-back steps below on a card at the boiler.
4. **Rehearse the monitor in shadow mode** for an hour:
   `OT_E32_PASSWORD=… python3 -I tools/switchover/monitor.py --host http://<e32> --duration-h 1`.

## Switch-over

1. Install the approved build with the gate open. The Rooms page now shows the
   takeover button. The confirmation always starts empty after a firmware change.
2. Start the monitor for 48 hours.
3. Wait until the old thermostat requests no heat. Switch the boiler off,
   disconnect only the thermostat's wires, insulate and label them, and switch
   the boiler on again.
4. Observe 10–15 minutes in shadow mode: boiler telemetry still arrives, the
   boiler stays idle, hot water still works, the boiler maximum stays known.
   If telemetry stops or the boiler heats by itself, stop and reconnect.
5. Rooms → Active control → **My thermostat is disconnected from the boiler —
   let the E32 take over**, and confirm the dialog. Expected within a minute:
   "The E32 controls the boiler.", a boiler request and "last sent … ago", no
   warnings.

## Attended tests

| Test | Do | Pass when | Check |
| --- | --- | --- | --- |
| Start | Target ~1 °C above the room | Heating active within 2 min (up to ~10 min boiler anti-cycling); flow rises ≥ 3 °C within 15 min | Page: request and last sent; HA: Heating active, Flow temperature; bus: Selected flow = request |
| Modulation | Target +1, +2, +3 °C | Flow follows the request within ±3 °C; never above the ceiling; heating stays on across the 60 s refresh | HA: Boiler request (E32) vs Flow and Selected flow; monitor: no `request_above_limit` |
| Stop | Target ≥ 0.5 °C below the room | Minimum burner time respected; heating off within ~30 s of the first zero; no restart within 5 min | Page: reason; HA: Heating active, Burner starts last hour |
| Hot water while heating | Open a hot tap 3 min | Hot water has priority; heating resumes within 5 min; no stop, no warning | HA: Hot water active, Heating active; page stays `active` |
| Hand-back button | Press **Hand back to the thermostat** | Zero for at least a minute, then shadow mode; nothing sent afterwards | Page text; `transmitted_frames` stops; monitor `handed_back` |
| E32 restart | System → Restart device while heating | `arming` with `confirmation.restored`, then back to `active` about 130 s after boot (2 min of boiler reception without a foreign 0x1A), within ~4 min, **without** a new confirmation; record what the boiler does in the gap | Monitor `e32_restarted` with reset reason; page |
| E32 power cut | Remove the E32's power, up to 30 min | What the boiler or adapter does without requests is measured and timed (holds the request or times out) | Boiler display and flow pipe; after power-on as above |
| Wi-Fi off (20 min) | Switch the access point off | Control continues on the fallback sensor and week program; **no restart** afterwards | Uptime keeps counting; monitor shows no restart |
| Home Assistant off | Stop HA Core (and separately the broker) | Fallback source and week program within 15 min; no stop, no restart; HA source back within 5 min after restart | Page: room status "Fallback source" |
| Measurement lost | Remove the fallback sensor's battery while HA is off | "Last value (source lost)" at 15 min; zero and `stopped_measurement_lost` at 30 min; resumes by itself when the reading returns | Page, monitor `guard_stopped` then resolved |
| Foreign controller | Reconnect the old thermostat while active | The E32 stops and warns by itself within about a minute; after a restart it waits for confirmation | Page: `blocked_foreign_controller`, `foreign_controller` warning |
| Frost (simulated) | Cool a sensor of an inactive room below 8 °C | Minimum flow with reason `frost_minimum`; off again at 9 °C | Page: request; monitor: no `frost_not_protected` |

**Abort** and hand back on: flow above the ceiling while heating (not hot
water), a request above the ceiling, pressure outside the normal range, a
boiler fault, short cycling, unexplained `transmit_failed` or
`boiler_no_response`, a foreign request while the thermostat is disconnected,
the boiler heating without a request, the E32 unreachable for more than 3
minutes, a room well above target while the E32 still asks heat, or any doubt.

## Hand back to the old thermostat

**Normal (the E32 page works):**
1. Open the E32 page, menu **Rooms**, section **Active control**.
2. Press **Hand back to the thermostat (the E32 asks for zero for one minute)**.
3. Wait for **Shadow mode: your thermostat controls the boiler.** (about 70 s).
   If it keeps saying "Stopping", use the emergency steps.
4. Switch the boiler off, reconnect the thermostat's two labelled wires as in
   the photo, and switch the boiler on.
5. Within 2 minutes the thermostat requests again (Home Assistant: "Requested
   flow temperature (thermostat)" has a value; the E32 page shows "last request
   from your thermostat"). Check hot water.

**Emergency (page unreachable, the E32 misbehaves, or the boiler keeps heating):**
1. Switch the boiler off (main switch or heating switch). Heating stops at once.
2. Remove the E32's power (or its two bus wires, labelled).
3. Reconnect the thermostat's wires, switch the boiler on, check hot water,
   pressure and the display.
4. Leave the E32 off until the cause is known. When it comes back with the
   thermostat connected, it sees the thermostat's requests and stays silent.
   With its stored confirmation it waits for 2 minutes of boiler reception
   without a foreign 0x1A before it asks anything; the thermostat's first
   request in that window clears the confirmation. Press **Hand back** anyway
   so the plan returns to shadow mode.
5. Suspect firmware? Reinstall the known-good build. A firmware change clears
   the confirmation, so the E32 then sends nothing.

## The first 48 hours and the first two weeks

**48 hours:** keep `tools/switchover/monitor.py` running. It logs rooms,
targets, requested and measured flow, burner and modulation, hot water, the
active-control state and warnings, the confirmation, the boiler maximum,
restarts with reasons, heap and stack minimums and MQTT disconnects, and it
alarms on missing heat, too-high flow, short cycling, rooms too cold or too warm,
active control stopping or waiting for confirmation, the E32 being
unreachable, restarts, MQTT disconnects and low heap. Check at +1 h, +4 h, the
first night setback, the first morning warm-up, +24 h and +48 h, using the
daily `summary-<day>.json`.

**Two weeks:** a short daily check (state and warnings, restarts, room
temperature against target, burner starts and short cycling, flow range,
pressure, hot water, gas use) and a weekly comparison with the shadow period.
Change parameters only with a noted reason. Learned flow stays advice for the
first two weeks. Firmware updates in this period are attended only: a new
firmware clears the confirmation, so confirm again right after the update.

A release can become 1.0 after 14 days of active control without a hang or
unexpected restart, all attended tests passed, at least one update through the
official route, and an installation guide that someone else has followed.
