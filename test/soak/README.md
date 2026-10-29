# E32 control soak test

A host-only long-run test of the E32 control modules. It looks for problems
that only show up after days or weeks: crashes, hangs, leaks, time wrap, day
rollovers and DST, payload growth, and safety rules that slowly drift. It
simulates a house, a boiler, a tado, Home Assistant and Bluetooth sensors for
up to 60 days at the firmware's 10 s cadence, and checks invariants on every
step. It never talks to a device.

```sh
# from Windows (Git Bash), any working directory:
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash /mnt/c/Users/m.dielessen/Downloads/open_thermostat-vscode-20261021/test/soak/run.sh
# inside WSL/Linux:
test/soak/run.sh [full|smoke|build|repro]
```

The binary is built with `g++ -std=gnu++2a -O1 -g1 -fsanitize=address,undefined`
into `/tmp/soak-build` (`SOAK_BUILD`). It uses the cJSON and esp32_utilities
copies in `.pio/libdeps/native`, so run the PlatformIO native environment once
first. Logs go to `/tmp/soak-out/<mode>/<scenario>.log` and `.err`.
Allocation-failure crash reports go to `oom-<scenario>-<builder>.log`.

| Mode | What runs | Wall time (28-core WSL) |
|---|---|---|
| `full` (default) | every scenario below, in parallel | about 100 s (about 7 min run one after another) plus a 30 s cold build |
| `smoke` | 1.5-day chains around a DST change and the 32-bit wrap, plus guard, flow, supervisor, sizes and repro | 5 s plus a 30 s cold build |
| `repro` | only the deterministic reproducers of known findings | under 1 s |

Environment: `SOAK_SEED` (added to every seed), `SOAK_JOBS`, `CXX`, and
`SOAK_ALLOW`, a comma-separated list of invariant ids that are reported but
do not fail the run (for known defects while their fix is pending). Exit
status 0 means every scenario passed, with no sanitizer report and no crash.

## Scenarios

| Name | Simulation |
|---|---|
| `chain-ams` | 60 days at 10 s (518,400 steps), CET/CEST from 2026-09-20 (includes the October DST change), plus the allocation-failure sweep at the end |
| `chain-nyc-wrap` | 60 days, EST/EDT (March DST change). Uptime starts at 2^32 ms - 30 min. Live DHW flow, boiler outdoor sensor (0x19) |
| `chain-lordhowe` | 30 days, `<+1030>` with a 30-minute DST shift (a 24.5 h day) |
| `chain-santiago` | 21 days, DST change at 24:00 (the local midnight is repeated) |
| `chain-sydney-churn` | 20 days, southern hemisphere, a plan edit every 15 min |
| `chain-kathmandu-30s` | 60 days, +05:45, 30 s steps (the larger step that ShadowComparison and FlowLearner allow) |
| `guard` | ActiveHeatGuard alone for 60 days: mode switches, confirmations, the tado reconnecting, route flaps, failing writes, boiler limit 60/55/25/unknown, measurement loss, frost |
| `flow` | FlowDemand alone for 60 days: random demand flips, missing errors, loop stalls, flow-limit edits |
| `supervisor` | SupervisorPolicy for 60 days at 5 s: Wi-Fi, broker, gateway, loop stall, stuck update and Bluetooth faults, with reboots and backoff counters |
| `sizes` | fw/telemetry/heating and plan size for a realistic 8-room plan and two worst-case valid plans |
| `repro` | deterministic reproducers of the findings listed below |

### The chain

The chain runs every module as `HeatingController::stepHeating()` wires them.
That covers RoomEngine, RoomDemand, ZoneRegulator, FlowDemand, ShadowComparison
and FlowLearner. It also covers WarmupPlanner, DhwEpisodes and
BurnerCycleMonitor (fed by real ClassicBoilerMonitor and EmsTelegram 0x18,
0x34, 0x16 and 0x19 telegrams), ForeignBoilerRequest, ActiveHeatGuard and
ManagedBleObserver (synthetic pvvx BTHome v2 adverts, both plain and
"encrypted" through a deterministic AES-CCM stand-in). Finally it covers
HeatingInputRoute/HeatingInput (real `ha/heating_input` JSON) and
HeatingTelemetry.

The house has 8 rooms: a floor-heated living room and kitchen, 5 radiator rooms
with TRVs, and an unheated attic that drops below 8 °C during frost spells. The
outdoor temperature follows a daily sine plus season, multi-day weather and a
guaranteed frost spell. Gains come from sun and opened windows. A tado runs the
boiler in shadow mode (0x1A every 60 s at 31-43 °C). DHW taps and keep-warm
reheats happen several times a day. A gas meter reports hourly with a true
boiler input of 24 kW against the configured 22 kW. The learner reaches `ready`
for all 8 rooms in 4-20 days and calibrates to 1.091 (the truth).

Injected events:
- **Home Assistant**: outages of 0.5-6 h, `null` temperatures, and junk or
  too-deep payloads.
- **Plan edits** every few hours, sent as JSON with a revision exactly like
  `setHeatingPlan`: source reorder, removal and restore, foreign sensors,
  pauses with `inactive_until`, setpoint entity, limits (some get refused),
  week programs with points in the DST hour, flow limits, room
  removal/addition/rename/reorder, emitter change, stale revisions and
  identical resends.
- **Active-mode phases**: the owner confirms. The tado sometimes stays or comes
  back (a foreign controller). Writes fail at 5 % and the route flaps.
- **Bluetooth faults**: counter resets, garbage, truncated, out-of-range,
  unknown-object, forged, downgraded, replayed and duplicate-service frames;
  queue bursts; future stamps and clock rollbacks; sensor silence.
- **EMS bus dropouts**.
- **Loop stalls** of 2-6 min (an OTA upload).
- **NTP steps** of ±20 s.

## Invariants (checked continuously)

- No ASan or UBSan report, and no crash. `run.sh` counts `runtime error:` and
  `ERROR: AddressSanitizer|LeakSanitizer` lines.
- **Heap**: the process heap, sampled at each local midnight, may not grow by
  more than 8 KB from days 3-9 to the last 7 days. Exactly 0 cJSON blocks are
  live after every publish (counting cJSON hooks).
- **Allocation-failure sweep**: every builder is run once with each cJSON
  allocation failing in turn (400 probes plus 400 spread for large builders),
  each in a forked child. A crash, a leaked block or invalid JSON is a
  failure. The builders are RoomEngine, ShadowComparison, ActiveHeatGuard,
  FlowLearner, learnedJson/WarmupPlanner, the learned-room and summary
  telemetry, DhwEpisodes, RoomPlan json/parse, RoomSchedule, HeatingInput, and
  the compact and full status.
- **JSON**: every payload parses back with cJSON. Size bounds: fw/telemetry/heating
  ≤ 7900 B, heating_learned/<id> ≤ 900 B, heating_summary ≤ 600 B, and the
  stored plan ≤ 4095 B. Shape changes of the MQTT payload are reported (a
  documented `{..}|null` value does not count).
- **RoomEngine/RoomDemand against an oracle**: the leading source, status
  (ok/fallback/stale/lost/inactive), temperature and setpoint
  (HA < 15 min, else the week program, else the fallback, clamped). The oracle
  carries readings across plan edits as `setPlan` does. Pauses end at
  `inactive_until`. `no_demand` holds exactly when no room is usable.
- **FlowDemand**: a heat request lies within [plan min, plan max] and ≤ 60 °C,
  and off means 0. Minimum on and off times hold (except after a flow-limit
  edit rebuilds it). Sustained demand always heats (no stuck-off state).
- **ActiveHeatGuard**: it never sends a positive flow in shadow mode, without
  confirmation, after a foreign 0x1A that followed the confirmation, with the
  route not ready, or within the boot holdoff. The flow is ≤ min(plan max, 60,
  boiler limit) and ≥ the plan minimum (unless the boiler limit is lower).
  Frost: a fresh room below 8 °C (also inactive) gets at least the minimum
  flow while the guard owns the boiler (8.0/9.0 °C hysteresis). A release
  leaves the boiler with a zero.
- **Time**: `RoomSchedule::localAt/localDay` match `localtime_r` on every step.
  ShadowComparison and DhwEpisodes roll over exactly once per local midnight
  into the right day. A completed day lasts exactly as long as its local day
  (82,800/84,600/86,400/88,200/90,000 s). Day totals match an oracle: seconds,
  E32 heat seconds, E32 and tado starts, and partitions add up. There is no 32-bit
  wrap trouble around 2^32 ms.
- **WarmupPlanner**: `nextRise` matches a brute-force minute walk of the local
  clock (DST included). Lead ≤ 8 h, flows stay within the plan, and gas is finite
  and not negative.
- **FlowLearner**: segments, periods and gas intervals are monotonic, and
  readiness never regresses for the same room and emitter. Loss is in
  [0.002, 0.2] and capacity is above 0, both finite. Advice and rule flows stay
  within the plan, calibration is in [0.5, 2], and at least 3 rooms are `ready`
  after 30 days.
- **DhwEpisodes**: tapping and keep-warm counts and seconds per local day match
  the generator. BurnerCycleMonitor starts in the last hour match an edge
  oracle (capacity 24), and short cycling is flagged at ≥ 6 heating starts.
- **ManagedBleObserver**: a reported temperature always comes from a good
  frame at exactly its reported age. It is never taken from a forged, replayed,
  downgraded or malformed frame. Readings stay fresh (≤ 5 adverts old) outside
  fault windows. After a counter reset, readings are accepted again within
  10 min + 5 adverts. All counters are monotonic.
- **SupervisorPolicy**: no restart while healthy or during an update shorter
  than 20 min. A persisting fault restarts within its (backed-off) limit + 10 s.
  Backoff arithmetic is safe for every stored counter value.

A mutation check (scratch copies of headers with one planted bug each:
minimum on/off, reading carry-over, stale hold, day roll, DST offset, foreign
check, frost, cap, re-anchoring, BLE value lifetime, a failure-path leak) was
caught by these invariants 14 of 14 times.

## Known findings (state 2026-10-29)

These currently make `full` fail. Their ids for `SOAK_ALLOW` are:
`oom_crash_room_engine_json`, `oom_crash_status_mqtt_compact`, `oom_crash_status_full`,
`repro_room_engine_json_oom`, `guard_released_with_positive_at_boiler`,
`repro_guard_stop_without_zero`, `dhw_counts`, `dhw_seconds`, `repro_dhw_reheat_counted_as_tap`,
`warmup_night_gas`, `mqtt_heating_exceeds_limit_worst_case_printable`,
`mqtt_heating_exceeds_limit_worst_case_escaped_names`.

1. **RoomEngine::json() crashes when an allocation fails.** If
   `cJSON_AddArrayToObject(root, "ha_entities")` returns null, `addEntity`
   reads `entities->child` (RoomEngine.h:127). It is reached from
   fw/telemetry/heating and /status/heating. Fix: return nullptr (after
   deleting root) when `entities` is null.
2. **ActiveHeatGuard ends its stop window without a delivered zero.** In
   `stopping`, the guard moves to shadow 60 s after `enter(stopping)` even
   when every zero write failed or the route was not ready. The boiler keeps
   the last positive 0x1A, how long depends on its own timeout. Fix: stay in
   `stopping` (keep repeating zero) until a zero was transmitted ok, with a
   long bound and a warning.
3. **DhwEpisodes counts a reheat right after a short tap as a second tap.** The
   2-minute look-back reference reaches back before the tap, so the reheat
   "falls" 30 K. Fix: ignore look-back samples older than the end of the
   previous episode (or clear `temps_` in `close()`).
4. **WarmupPlanner::night() can report negative gas.** When the outdoor
   temperature is above the room or target temperature (for example an
   unheated attic or a mild afternoon), `ua * (T - To)` is negative. Fix:
   clamp the heat per step at 0. Related: `saving_m3`/`saving_eur` turn negative
   when the program's own setback is not on time (reported as a note).
5. **fw/telemetry/heating can exceed 7900 B for a valid plan.** 8 rooms × 4 HA
   sources with long entity ids give 8055 B, and escaped names give 8375 B.
   ModernTransport then drops every heating status. Fix: bound it at plan
   validation, or move `ha_entities` to its own topic.

Notes (not failures):
- A realistic 8-room plan with 4 switch points per day is 4964 B, so
  `setHeatingPlan` refuses it as `plan_too_large`.
- In the 24 h before a DST change, WarmupPlanner converts every minute
  separately: 2,886 `localtime_r` calls per heating_learned room payload
  (normally about 30) and up to 19,000 per /status/heating.
- The burner's `starts_last_hour`/`heating_starts_last_hour` keys disappear
  from fw/telemetry/heating while the burner state is unknown.
- A heating_learned payload reaches about 904 B with a 32-character room id.

## Limits

- `HeatingController` and `ModernTransport` are not host-buildable. The status
  JSON is a replica of `HeatingController::heatingStatusJson()` (keep it in sync).
- The host has a 64-bit `time_t`. The device's newlib under IDF 4.4 likely has
  a 32-bit one, so 2038 behaviour of `localtime_r` is not covered.
- FlowLearner and the guard confirmation live in RAM. Reboots are not
  simulated in the chain (a reboot simply starts over).
