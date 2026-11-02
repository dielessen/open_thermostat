# Real-data replay

A repeatable check of the E32's learning and self-tuning against recorded house data.
Every change to FlowLearner, AutoTuner, WarmupPlanner or FlowPolicy is replayed on the
owner's real recording before release, before and after the change, and the
differences are explained in the change.

The driver (`replay.cpp`) feeds recorded room temperatures and targets, boiler flow,
return, modulation, hot water, the E32's and the old thermostat's requests and the
outdoor temperature through the firmware's own classes, wired as
`HeatingController::stepHeating` wires them. It reports what they learn, propose and
plan. It only reads `src/` and never contacts a device or Home Assistant.

## Quick start

From Windows (Git Bash), in WSL:

```sh
export MSYS_NO_PATHCONV=1
wsl -e bash -lc 'cd /mnt/c/Users/m.dielessen/Downloads/<worktree> && tools/replay/run.sh out/replay-data/house.csv'
```

Inside WSL or Linux:

```sh
tools/replay/run.sh <data.csv> [more.csv ...] [options]   # build if needed, run, print the summary
tools/replay/run.sh --build-only
python3 tools/replay/test_replay.py -v                    # the fixture check (also: final_check.sh --only replay)
```

`run.sh` compiles `replay.cpp` with
`g++ -std=gnu++2a -O1 -g1 -fsanitize=address,undefined` against `src/`,
`test/test_native/include`, and cJSON and esp32_utilities from `.pio/libdeps/native`
(run `pio pkg install -e native` once). The binary goes to
`/tmp/openthermostat-replay`. It writes `<name>.json` and `<name>.txt` to
`/tmp/openthermostat-replay/out` and prints the text. The build takes about 20 s and a
replay of three days about 1 s. Remove `/tmp/openthermostat-replay` when done.

| Environment | Default | Meaning |
|---|---|---|
| `REPLAY_REV` | (working tree) | Build against `git archive <rev> src`, e.g. the release candidate before the change |
| `REPLAY_BUILD` | `/tmp/openthermostat-replay` | Binary and exported sources |
| `REPLAY_OUT` | `$REPLAY_BUILD/out` | JSON and text output |
| `REPLAY_LIBDEPS` | `.pio/libdeps/native` | cJSON and esp32_utilities (another worktree's copy works) |
| `CXX` | `g++` | Compiler |

Before and after a change:

```sh
REPLAY_REV=<base commit> tools/replay/run.sh out/replay-data/house.csv --plan out/replay-data/plan.json
tools/replay/run.sh out/replay-data/house.csv --plan out/replay-data/plan.json
diff /tmp/openthermostat-replay/out/house-<base>.txt /tmp/openthermostat-replay/out/house.txt
```

Keep the owner's full recordings in `out/replay-data/` of the main checkout. It is
git-ignored and the release cleanup leaves CSV and JSON files alone. Never commit
them: only the anonymised fixture below belongs in the repository.

## Options

| Option | Meaning |
|---|---|
| `--mode shadow,active,recorded` | The runs (default `shadow,active`), each over the whole data |
| `--plan FILE` | A RoomPlan JSON (the API form of `GET /config/heating`). Its room ids name the CSV rooms; each room's first source and its `setpoint_entity` get the CSV values |
| `--schedule JSON` | A week program (`RoomSchedule` array) for every room of the default plan |
| `--emitter floor\|radiator`, `--min-flow N`, `--max-flow N` | The default plan: one active room per CSV room (floor, 30, 60) |
| `--no-grace` | AutoTuner without its 24 h after a boot. By default the E32 boots at the first row |
| `--recorded-request` | Use the CSV's E32 request where known instead of the computed one |
| `--weather-curve`, `--apply-learned` | The FlowPolicy options (default off: advice only, as shipped) |
| `--bridge-hot-water`, `--no-bridge-hot-water` | `FlowLearner::Params::bridgeHotWater` (default on, as in the firmware) |
| `--hold-s N` | A row holds this long; after that the step is a gap and nothing is fed (default 60) |
| `--tz TZ` | POSIX time zone for local days and programs (default `CET-1CEST,M3.5.0,M10.5.0/3`) |
| `--json FILE`, `--text FILE` | Outputs (without either: JSON on stdout) |

Several CSV files are joined in time order; on an equal timestamp the later file wins.

## The modes

Every 10 s step runs, as in `stepHeating`: RoomEngine (the rule), FlowPolicy (the flow
options), FlowLearner, a simplified guard, then AutoTuner with BurnerCycleMonitor. The
boiler values are always the recorded ones.

- **shadow**: the old thermostat drives the boiler. FlowLearner's heating reference is
  its 0x1A (`thermostat_flow_c`). AutoTuner only shows its proposals ("would").
- **active**: the E32 drives the boiler and the old thermostat is off the bus
  (`thermostat_flow_c` is ignored). The guard's last command is the E32 request,
  bounded by the plan's flow limits (0 = no heat). FlowLearner gets it through
  `FlowLearner::heatingReference` when the firmware has it. Older firmware passes the
  absent 0x1A, as HeatingController did. The JSON says which in `firmware` and in each
  run's `learner_reference`. AutoTuner applies its changes, and they take effect at once.
- **recorded**: per row, as the `mode` column says.

On data recorded in shadow mode, the active run shows what the E32 would have learned
and tuned from the same boiler behaviour. The boiler itself followed the old
thermostat.

The tool does not model valves, room overrides, the boiler's 0x16 limit, the HA input
path or the full ActiveHeatGuard. Burner on is modulation > 0, as in
`EmsController::activeHeatView`; the `burner` column counts only where modulation is
unknown.

## CSV format

One header line, then one row per sample. Lines starting with `#` are comments. There
is no quoting. An empty field means unknown. Rows may come at any interval; the driver
steps every 10 s and holds a row for `--hold-s`. A column that is absent is unknown
throughout. An unknown column is reported in `inputs.ignored_columns`.

| Column | Unit | Meaning |
|---|---|---|
| `utc` | s | Unix time (required) |
| `<room>.temp_c` | degC | Room temperature; `<room>` is a plan room id (`[a-z0-9_]`) |
| `<room>.target_c` | degC | Room target (the setpoint the E32 would follow) |
| `flow_c`, `return_c` | degC | Measured boiler flow and return |
| `burner` | 0/1 | Burner bit (only used without `modulation_pct`) |
| `heating_active`, `dhw_active` | 0/1 | Boiler: heating active, hot water active |
| `modulation_pct` | % | Burner modulation |
| `e32_heat`, `e32_flow_c`, `e32_reason` | 0/1, degC, text | The E32's request as recorded (in shadow mode: what it would have asked) |
| `thermostat_flow_c` | degC | The old thermostat's requested flow (0x1A); below 20 = no heat |
| `outdoor_c` | degC | Outdoor temperature |
| `mode` | `shadow`/`active` | Who drove the boiler (default shadow) |

## Output

The JSON (`schema` 1) holds:

- `inputs`, `firmware` and `options`;
- `days`: per local day, what the data itself shows: hours of data, burner starts,
  heating and hot-water burns, heating burn minutes, hot-water minutes, hours of heat
  request by the old thermostat and by the recorded E32, and outdoor min/mean/max;
- `warmups`: every recorded target rise of at least 0.3 degC that held for 10 min.
  For each: the room temperature at the rise, whether a warm-up was needed, the start
  of the controlling heat request's run that reached the target, and how late it was;
- `runs[]`, one per mode, each with:
  - `autotuner`: every day-change evaluation (its full `tuning` status), `proposals`
    (knob, from, to, reason, figure, room, applied) and `final`;
  - `learner`: `by_day` progress per room, `events` (each learned heating or cooling
    segment) and the final `rooms` (`FlowLearner::roomJson`: curve, advice, heat model);
  - `flow_policy`: FlowCompare's daily means (rule, applied, curve, learned) and the
    final `flow` status;
  - `planner`: the hourly `optimumStart` against the plan's program (`schedule`). Every
    15 min it also plans against each recorded rise, using a one-day program made of
    that rise and the drop before it (`rises`: the first and last plan, when "start
    now" began, planned and actual lead). `checks` counts the plans made without a
    cooling model and any that exceeded the default lead.

The text summary is a short overview of the same content.

## Converters

Both write the CSV above, one row every `--step` seconds (default 10), sample and hold.

`from_mqtt.py` reads the read-only MQTT logger's JSON lines
(`out/switchover-*/mqtt-active.jsonl`, `{"t", "topic", "p"}`). It uses
`fw/state/heating` (the request and `active.state`) and `fw/state/boiler_fields/<g>`
(field indexes from `ha/.../boiler_fields.py`; a value's time is the logger time minus
its age in the group). It also reads `fw/state/room/<id>` when logged. `t` is the
logger's local wall time. Give `--utc-offset +01:00`, or `--tz Europe/Amsterdam`, which
needs the system's tz database (WSL has it).

```sh
python3 -I tools/replay/from_mqtt.py out/switchover-20261101/mqtt-active.jsonl out/replay-data/active.csv \
    --room-alias woonkamer=room1
```

`from_ha.py` converts saved `/api/history/period` responses. The E32 entities are found
by their suffix (`_boiler_measured_flow_temperature`, `_heat_request`, ...). Rooms and
anything else come from `--room ID=climate.x` or `--map COLUMN=ENTITY[@ATTRIBUTE]`.

```sh
python3 -I tools/replay/from_ha.py out/replay-data/history-*.json --room room1=climate.living_room \
    --map outdoor_c=weather.home@temperature --mode shadow --out out/replay-data/house.csv
```

### Fetching Home Assistant history (read-only)

Use a long-lived access token from an environment variable. Never write it to a file,
a command history or a repository. Only `GET` requests are needed:

```sh
read -rs HA_TOKEN && export HA_TOKEN      # paste the token; it is not echoed
HA=https://homeassistant.local:8123
E=sensor.<e32_device>_                    # the E32 integration's entity prefix
FROM=2026-10-30T00:00:00+00:00 TO=2026-10-31T00:00:00+00:00
# The E32's sensors: states only.
curl -fsS -G -H "Authorization: Bearer $HA_TOKEN" "$HA/api/history/period/$FROM" \
  --data-urlencode "end_time=$TO" \
  --data-urlencode "filter_entity_id=${E}boiler_measured_flow_temperature,${E}boiler_measured_return_temperature,${E}boiler_reported_burner_modulation,${E}boiler_dhw_active,${E}boiler_heating_active,${E}thermostat_requested_flow_temperature,${E}heat_request" \
  --data-urlencode significant_changes_only=0 --data-urlencode minimal_response --data-urlencode no_attributes \
  -o out/replay-data/history-sensors-1030.json
# The room's climate entity and the weather: with their attributes.
curl -fsS -G -H "Authorization: Bearer $HA_TOKEN" "$HA/api/history/period/$FROM" \
  --data-urlencode "end_time=$TO" --data-urlencode "filter_entity_id=climate.living_room,weather.home" \
  --data-urlencode significant_changes_only=0 -o out/replay-data/history-climate-1030.json
unset HA_TOKEN
```

Fetch one day per request. Climate and weather entities are fetched with their
attributes, because their target and temperature are attributes. A self-signed
certificate needs `--cacert`, not `-k`. `tools/switchover/replay_export.py` fetches
directly into the older `test/learning_replay` format. It reads the token from
`OT_HA_TOKEN`.

## The fixture and its check

`test/fixtures/replay/house-shadow.csv` is about 14.5 h of the owner's shadow-mode
recording, from Fri 30 Oct 22:00 to Sat 31 Oct 12:30 2026 (CET), every 30 s, about
70 KB. Values are rounded and there are no entity ids or names: the room is `room1`.
It contains a night cooling, the morning rise 18.5 -> 21.0 degC, and keep-warm rounds
of the boiler's hot-water store (HRC 22) roughly every 11 minutes. `plan.json` is a
one-room floor plan with the week program 18.5 / 09:00 21.0 / 22:30 18.5.

`test_replay.py` builds the driver and replays the fixture in shadow and active mode
with `--no-grace`, so the one day change is evaluated. It checks:

1. **AutoTuner proposes nothing on the shadow fixture**, and it did evaluate a day.
2. **WarmupPlanner never plans more than its default lead without a cooling model.**
   Without the learned loss rate, the start temperature is the night setpoint, so the
   lead stays within `defaultLeadS` of that shortfall, rounded up to the planner's
   5 min steps. This holds in every plan of both runs.
3. **FlowLearner learns at least `ACTIVE_MIN_SEGMENTS` (2) segments in active mode, with
   the E32's own request as its reference.** At `e33cbbf` the reference is the absent
   0x1A and nothing is learned (0 segments). With `FlowLearner::heatingReference`
   (rc.2) the fixture gives 2, with or without hot-water bridging.

A check for behaviour that is still being built can be listed in `EXPECTED_FAIL` in
`test_replay.py`, with the branch that brings it. While it is listed, a failure counts
as an expected failure. A pass is an "unexpected success" and fails the run (strict),
so the entry is removed in the merge that brings the behaviour. The list is empty at
rc.2. The converters have their own small inline tests in the same file.

`scripts/final_check.sh` runs this as its `replay` step (a few seconds after the
build). Without the fixture the step is skipped.

To cut a new fixture, keep it under 200 KB. Use rows every 30 s, rounded values, and
room ids like `room1`. Use no entity ids, names or addresses. Describe its origin in
`#` lines at the top. Then derive the expected numbers again from a replay and update
the README and `test_replay.py` together.

## Baseline: the owner's recording, 30 Oct - 2 Nov 2026

The replay of the full recording at `e33cbbf`. Sources: HA history 30 Oct 18:10 -
1 Nov 11:27 (shadow), switch-over monitor 20:52-21:43, then the MQTT log of active
control until 2 Nov 08:44. Default plan with the week program above, AutoTuner grace
from the first row:

- The boiler fires mostly for the hot-water store. On 31 Oct (24 h of data), 56 of
  59 burns were hot water (188 min) and 3 were heating.
- FlowLearner learns no heating segment in shadow mode: 97 heating periods, each cut
  by a keep-warm round. In active mode, without `heatingReference`, it also learns 0.
  With it (`d9758d8`) it learns 1, and 5 with `--bridge-hot-water`.
  At rc.2, hot-water bridging is on by default: without a plan, the recording gives
  4 segments in shadow and 4 in active mode (0 and 0 with `--no-bridge-hot-water`).
- AutoTuner proposes `min_off_s` 300 -> 450 for 31 Oct (`many_starts`, 31 heating
  starts), evaluated at midnight. In shadow mode this is shown; in active mode it is
  applied.
- WarmupPlanner, without a learned model, plans default leads of 240-300 min for the
  morning rises. The recorded warm-ups that reached their target (31 Oct 12:49,
  1 Nov 09:00) started at the switch time and were 74 and 109 min late.
