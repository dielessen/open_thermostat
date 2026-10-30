# Switch-over monitor

`monitor.py` watches the E32 during the first 48 hours after the attended
switch-over ([docs/SWITCHOVER.md](../../docs/SWITCHOVER.md)). It polls the E32
every 30–60 s, writes everything it sees to JSONL files, raises alarms in the
terminal and, if you want, on your phone through a Home Assistant webhook, and
writes a summary per day.

It is **read-only**. It only sends GET requests, plus one `POST /auth/login`
to open a session. It never changes settings, the room plan, the takeover
confirmation or the boiler. You can stop it at any time with Ctrl+C, and you
can run it in shadow mode as a rehearsal.

Requirements: Python 3.9 or newer, standard library only. MQTT is optional:
with [paho-mqtt](https://pypi.org/project/paho-mqtt/) installed and
`--mqtt-host` given, it also listens to the E32's MQTT telemetry. Without paho
it uses HTTP only.

## Run it

```sh
export OT_E32_PASSWORD='your E32 web password'     # or leave it unset and type it at the prompt
export OT_NOTIFY_URL='http://homeassistant.local:8123/api/webhook/<your-webhook-id>'   # optional
python3 -I tools/switchover/monitor.py --host http://192.168.1.50
```

Windows PowerShell: `$env:OT_E32_PASSWORD = '...'`, then `py -I tools\switchover\monitor.py --host http://192.168.1.50`.

By default it runs for 48 hours and writes to `out/switchover-<UTC date>/` in
the repository (kept by the release cleanup; see AGENTS.md). One sample, printed
and not stored: `--once`.

The address `192.168.1.50` is an example. Use your E32's address.

### Passwords

- The E32 password comes from `OT_E32_PASSWORD` or an interactive prompt.
- The MQTT password (only with `--mqtt-user`) comes from `OT_MQTT_PASSWORD` or a prompt.
- There is no command-line option for a password. Passwords, the session cookie
  and the webhook URL are never written to a file or printed.
- The webhook URL contains a secret id, so prefer `OT_NOTIFY_URL` over `--notify-url`.

The E32 allows four browser sessions at a time, and the monitor uses one. Sessions
live in RAM, so after an E32 restart the monitor logs in again (at most once per 2 min).

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--host` | `OT_E32_HOST` | E32 address, `http://<ip or name>` without a path |
| `--user` | `admin` | E32 web user |
| `--interval` | `60` | seconds between samples, 30–60 |
| `--duration-h` | `48` | stop after this many hours; `0` = until Ctrl+C |
| `--out` | `out/switchover-<date>` | output folder |
| `--once` | | take one sample, print it as JSON, store nothing |
| `--notify-url` | `OT_NOTIFY_URL` | Home Assistant webhook for alarms |
| `--mqtt-host`, `--mqtt-port`, `--mqtt-user` | –, `1883`, – | listen to `<prefix>/+/fw/telemetry/heating` and `device_status` |
| `--mqtt-prefix` | `ib-therm` | the E32 MQTT prefix (new installations: `openthermostat`) |

Alarm thresholds (all optional):

| Option | Default | Alarm |
| --- | --- | --- |
| `--no-heat-min` | `20` | minutes an active room may stay below target without a heat request |
| `--below-target-c` | `0.5` | how far below target counts as "below target" for that alarm |
| `--room-cold-c`, `--room-warm-c` | `1.0`, `1.5` | a room this far below or above its target ... |
| `--room-hold-min` | `30` | ... for this long (too warm while still heating: 5 min) |
| `--flow-margin-c` | `3.0` | measured flow above the limit by more than this, two samples in a row |
| `--max-starts-per-hour` | `6` | heating burner starts in the last hour |
| `--unreachable-min` | `3` | E32 not answering over HTTP this long |
| `--repeat-min` | `60` | a standing alarm is repeated this often |
| `--heap-minimum-bytes` | `20000` | minimum free internal heap since boot |

## What it reads

| Request | Used for |
| --- | --- |
| `GET /status/heating` | rooms (temperature, target, source, status), calculated request, `active` block (guard state, command, last sent, warnings, confirmation, `confirmation_stored`, `boiler_limit`), burner starts and short cycling, Home Assistant link |
| `GET /status/ems/telemetry` | measured flow and return, selected flow, modulation, heating and hot-water bits, hot-water temperature, pressure, the boiler's configured heating temperature, display code |
| `GET /status/logs?after=<n>` | boot id, reset reason and the previous boot's black box, free heap and its minimum, task stack minimums, `mqtt_budget_disconnects`, `heating_telemetry_dropped`, new error and warning log lines |
| `GET /status` | uptime |
| `GET /config/heating` (every 10th sample) | plan flow limits |

If HTTP fails but MQTT has a fresh `fw/telemetry/heating` (under 2 min old),
the sample comes from MQTT (`heating_source: "mqtt"`), and the
`e32_unreachable` alarm is still raised.

## Alarms

Each alarm is raised once when its condition starts (after its hold time), is
repeated every `--repeat-min` while it stands, and is reported as resolved
when it ends. Severities: `alarm` (act now), `warning` (look today), `info`.

| Key | Severity | When |
| --- | --- | --- |
| `no_heat_request` | alarm | an active room is below target and the E32 asks no heat for `--no-heat-min` (in shadow mode: the calculated request) |
| `request_above_limit` | alarm | the E32 requests or sent a flow above min(plan maximum, 80 °C, boiler limit) |
| `flow_above_limit` | alarm | measured flow above that limit + margin while heating (not during hot water), two samples in a row |
| `short_cycling` | alarm | the E32 reports short cycling, or too many heating starts in the last hour |
| `room_cold_<id>`, `room_warm_<id>` | alarm | an active room too cold or too warm (see the thresholds) |
| `frost_not_protected` | alarm | in active mode a room reads below 8 °C and the E32 asks no heat |
| `guard_stopped` | alarm | active control left `active` (stopping, measurement lost, blocked by a foreign controller, or arming for more than 4 min: after a restart the E32 first listens 2 min for another thermostat) |
| `awaiting_confirmation` | alarm | the plan is active but the E32 waits for the takeover confirmation (no heat, no frost protection) |
| `warning_<name>` | alarm | a warning of active control: `foreign_controller`, `measurement_lost`, `boiler_no_response`, `transmit_failed`, `boiler_limit_unknown` |
| `e32_unreachable` / `e32_back` | alarm / info | no HTTP answer for `--unreachable-min`; reachable again |
| `e32_restarted` | alarm | new boot id or smaller uptime, with the reset reason and the previous boot's supervisor reason |
| `mqtt_budget_disconnects` | warning | the E32 dropped its MQTT connection (socket write budget); first increase per hour notified, later ones logged as `logged` |
| `heating_telemetry_dropped` | warning | heating telemetry messages too large for MQTT |
| `heap_low` | warning | minimum free internal heap since boot below 20000 B |
| `stack_low` | warning | a task stack minimum below 512 B |
| `mqtt_silent` | warning | with MQTT on: no heating telemetry for 5 min |
| `handed_back` | info | the plan went back to shadow mode |

The webhook gets a JSON body
`{"title","message","key","event","severity","at_utc"}`. A Home Assistant
automation with a webhook trigger can forward it, for example:

```yaml
# Example: forward monitor alarms to the phone.
triggers:
  - trigger: webhook
    webhook_id: <your-webhook-id>
    local_only: true
actions:
  - action: notify.mobile_app_<your_phone>
    data:
      title: "{{ trigger.json.title }}"
      message: "{{ trigger.json.severity }}: {{ trigger.json.message }}"
```

## Output files

| File | Content |
| --- | --- |
| `samples-<day>.jsonl` | one line per sample (`reachable: false` lines when the E32 did not answer) |
| `alarms.jsonl` | every alarm event: `raised`, `repeat`, `cleared`, `logged` |
| `summary-<day>.json` | per local day: guard-state shares, heat-request, burner and hot-water shares, flow range while heating, highest request, most starts per hour, boiler limits seen, restarts, alarm counts, heap and stack minimums, MQTT disconnects, and per room min/max/mean and mean deviation from target. Rewritten every 10 samples, at the day change and on exit |

## Shadow exit criteria

`shadow_exit.py` answers "may the E32 take over?" after the shadow period. It
reads Home Assistant's history (GET only, a long-lived token in
`OT_HA_TOKEN`) and prints PASS, FAIL or WAIT per criterion: 72 h without a
restart, at least 10 thermostat heating periods with a night setback, a
morning warm-up and a quiet period, start/stop timing within minutes, the
E32's flow request in the 31–43 °C band, and no more heat periods than the
thermostat. With `--mqtt-log` (the output of a read-only MQTT listener) it
also checks availability and the 60 s heartbeat.

```sh
export OT_HA_TOKEN='your long-lived token'
python3 -I tools/switchover/shadow_exit.py --ha-url https://homeassistant.local:8123     --climate climate.living_room --since 2026-10-30T17:10:00Z --json shadow-exit.json
```

`--since` starts at the install of the current firmware (default: the last
`--days 3`). `--insecure` accepts a self-signed certificate on your own
network. The E32 entities are found by their suffix; pass `--uptime`,
`--e32-request` or `--thermostat-request` when you have more than one E32.

## Tests

```sh
python3 -I -m unittest discover -s tools/switchover -p "test_*.py" -v
```

The tests run the monitor against a mocked E32 HTTP server on 127.0.0.1, with
fixtures in the shape of the real `/status/heating`, `/status/ems/telemetry`
and `/status/logs` replies. They need no device and no network.
