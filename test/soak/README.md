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
| `smoke` | 1.5-day chains around a DST change and the 32-bit wrap, plus guard, active (3 runs per case), flow, supervisor, sizes and repro | 5 s plus a 30 s cold build |
| `repro` | only the deterministic reproducers of known findings | under 1 s |

CI runs `smoke` in the `soak-smoke` job; a release waits for it.

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
| `chain-ams-options` | 60 days like `chain-ams`, with both flow options on (weather curve and learned flow/optimum start, `--flow-options`) and the boiler's outdoor sensor |
| `chain-ams-holding` | rc.5: 60 days like `chain-ams-options` with the "0Y" boiler and free gains (`--profile=holding,gains`), the E32 driving most of the time (`--mostly-active`, first from 6 h) |
| `chain-ams-no-return` | rc.5: the same with a boiler that reports no return (`--profile=no_return,gains`) |
| `chain-ams-radiators` | rc.5: 30 days from 1 November, every heated room on radiators with valves, the "0Y" boiler, the outdoor from HA (`--profile=radiators_only,holding,gains`) |
| `chain-ams-floor` | rc.5: 30 days from 1 November, every heated room on a floor, no return (`--profile=floor_only,no_return,gains`) |
| `chain-kathmandu-30s` | 60 days, +05:45, 30 s steps (the larger step that ShadowComparison and FlowLearner allow) |
| `guard` | ActiveHeatGuard alone for 60 days: mode switches, confirmations, the tado reconnecting, route flaps, failing writes, boiler limit 60/55/25/unknown, measurement loss, frost |
| `active` | The switch-over failure cases, scripted, 200 runs each with random timing (see below) |
| `flow` | FlowDemand alone for 60 days: random demand flips, missing errors, loop stalls, flow-limit edits |
| `supervisor` | SupervisorPolicy for 60 days at 5 s: Wi-Fi, broker, gateway, loop stall, stuck update and Bluetooth faults, with reboots and backoff counters |
| `sizes` | fw/telemetry/heating and plan size for a realistic 8-room plan and two worst-case valid plans |
| `repro` | deterministic reproducers of the findings listed below |

Smoke runs `chain-ams-holding` for 1.5 days with `--profile=holding,no_return,gains` and the
E32 driving from the second hour (`--active-from-h=2`).

### Boiler profiles (`--profile=a,b,...`, rc.5)

The chain's boiler and emitters. Without the option the boiler is the owner's kind: a small
hot-water store kept warm several times a day, the return reported, a mixed house (a
floor-heated living room and kitchen, five radiator rooms with valves). Tokens combine:

| Token | Effect |
|---|---|
| `store` | the default above (only for clarity in a list) |
| `no_return` | 0x18 reports the return as "not available" (0x8000), as a boiler without that sensor |
| `holding` | the "0Y" boiler: it modulates down to 30 % and no further; when the open emitters take less (the default boiler's `wanted`: load x (request - 25) / 20), the water rises past the request; at the request + 5 K the burner stops, its own anti-cycle keeps it off for 10 min whatever is asked (display code `0Y`, also in 0x18), then it fires once the water is below the request. Resting, the open emitters cool the water, slowly when most valves are closed. Counters: `boiler_0y_stops`, `boiler_0y_stops_counting` (the E32's own request, settled, no hot water in the last 5 min, lead shortfall under 1 K), `boiler_0y_heating_starts`, `boiler_0y_rest_s` |
| `radiators_only` | every heated room on radiators with valves (living room and kitchen valves above their programs) |
| `floor_only` | every heated room on a floor, no valves |
| `gains` | free heat: up to 1 K/h of afternoon sun in the living room on a warm (sunny) day and 1.5 K/h of cooking in the kitchen at 17:30-18:30, so FreeHeat (P3) has evidence |

`--active-from-h=H` switches the plan to active mode after H hours instead of 3-6 days;
`--mostly-active` keeps the E32 driving most of the time (active phases of 2-7 days, shadow
phases of about 7 h) instead of the switch-over era's mostly shadow phases. BoilerResponse
only learns while the E32 drives the boiler.

### Active mode (`active`)

The switch-over failure cases of `docs/modern-thermostat/OVERSCHAKELING.nl.md`
(owner decisions of 29 October), wired as `HeatingController::stepActiveHeat`
and `EmsController::processBoilerTestPoll` wire them: RoomEngine,
ActiveHeatGuard, ActiveHeatPollDriver at the boiler's polls of 0x0B (real
Classic encoder), BoilerLimitRead for 0x16, HandoverConfirmation over an NVS
stand-in that survives reboots, and SupervisorPolicy. The active gate is forced
on in this host build only (`hostActiveGate`; a `static_assert` keeps
`board::emsActiveHeatAllowed` false outside the E32 build). One living room
(HA climate entity, then a pvvx sensor) and an inactive bathroom (pvvx). The
boiler holds the last 0x1A it received, reports 0x18 every 10 s and answers the
0x16 read. Every case first lets the owner confirm, then:

| Case | Checks |
| --- | --- |
| `ha_gone` | HA Core stops for 1-3 h: the pvvx leads (fallback), the fallback setpoint applies, no stop, no warning, no restart |
| `measurement_gone` | HA and pvvx silent: `stopped_measurement_lost` 30-32 min after the last reading, zero at the boiler, warning, no Bluetooth restart while owning; heat resumes by itself within 10 min of the next reading |
| `reboot` | E32 restart while active (40 % with a freezing bathroom): the stored confirmation is restored; heat or frost protection resumes after 2 min of boiler reception without a foreign 0x1A (about 130 s after boot) and within 1 min (+ one step) of the first valid measurement. A firmware change asks again |
| `reboot_tado_back` | Review A6: the E32 is without power, the owner plugs the tado in again, the E32 restarts with its stored confirmation. The tado's first 0x1A (random phase, every 40 s) falls inside the 2-minute window: no 0x1A from the E32 at all (also no frost minimum), `blocked_foreign_controller`, NVS cleared. Without the tado, sometimes with a silent boiler for 1-20 min: no heat until the boiler was heard for 2 min, then within 150 s |
| `wifi_gone` | Access point off for 0.5-5 h: no restart while owning, regulation continues on the pvvx; the same outage restarts once released |
| `foreign_1a` | The tado sends 0x1A again: stop with zero within one step, warning, confirmation cleared in NVS, no positive afterwards, `blocked_foreign_controller`, after a restart `awaiting_confirmation` |
| `dhw` | A hot tap of 1-6 min while heating: still active, refreshed, no `boiler_no_response` or `transmit_failed` |
| `frost` | Frost minimum (30 °C) within one advert below 8 °C, held at 8.5 °C, off at 9 °C |
| `stop_until_delivered` | Hand-back while every write fails for 2-30 min: the guard keeps claiming the boiler, repeats zero every step and warns; the first delivered zero ends it. A normal hand-back: 6+ zeros in 70 s, then silence |
| `boiler_limit` | The boiler does not answer 0x16: no heat (`boiler_limit_unknown`), a retry every 5 min; heat once it answers; a lowered boiler setting (45 °C) applies after the next 6-hourly read |

Every step also checks: a positive request only with the confirmation, a known
0x16 limit, after the boot holdoff and ≤ min(plan max, 80, limit); the stored
confirmation equals the guard's; with a restored confirmation, no write after a foreign 0x1A of this boot and no heat before 2 min of continuous boiler reception; each 0x16 read is exactly `0B 88 16 00 02`;
at most one read per boot and per 6 h while the boiler answers; no supervisor
restart while the E32 claims the boiler. A mutation check (supervisor ignoring
ownership, no restore, no erase, no 6-hourly refresh, frost without
hysteresis, a 50 s listening window, a restore without listening) was caught 7
of 7 times. A 120 s boot holdoff is no longer visible here: after a restart the
2-minute listening window comes later anyway.

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

Since rc.5 it also follows HeatingController where it had fallen behind: FlowPolicy
gets the plan (`setPlan`, so the arrival feedback runs), the learned context carries
the arrival feedback (`plan.arrival` in heating_learned/<id>), FlowLearner gets the
E32's own command as its heating reference and `ownRequest` while the guard drives
the boiler (`heatingReference`, BoilerMinimumFlow), and the guard's lowest flow is
the learned boiler minimum (`effectiveMinimumC`).

The rc.5 learners join as soon as their headers exist (`__has_include`; until then
the hooks compile out, and the run's second line says which are on):

- **BoilerResponse** (P1, `control/BoilerResponse.h`, `control/RestFloor.h`): sampled
  after FlowLearner as `HeatingController::stepBoilerResponse` does (the guard's
  command and output, the usable rooms' mean, demand and lead shortfall, the ceiling's
  bounds); its ceiling goes into FlowPolicy while the guard drives (`ownRequest`,
  `ceilingC`); RestFloor raises min_off_s in place each step it changes; "boiler"
  joins fw/telemetry/flow.
- **HouseModel** (P2, `control/HouseModel.h`, `control/Knowledge.h`): the Scoreboard
  is stepped with the learner's heating energy and the judged mornings; HouseModel
  updates hourly, at the scoreboard's day change and after a plan edit; its slope goes
  into FlowPolicy (`houseSlope`); fw/telemetry/insight is built with
  `Knowledge::percent` and `addInsightJson` and split as TelemetryPublisher does.
- **FreeHeat** (P3, `control/FreeHeat.h`): the instance FlowPolicy owns
  (`FlowPolicy::freeHeat()`) is sampled after FlowLearner with
  `FreeHeat::heatDelivered`; the learned context points at it ("free_heat" per room).

Hooks the plan's contract left open are detected rather than assumed (FlowPolicy's
inputs and owned FreeHeat, Sample fields beside the contract, RestFloor, Scoreboard's
day change); a module without its hook is reported as a `rc5_hook_missing` note.

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
  ≤ 7900 B, heating_learned/<id> ≤ 1000 B, the whole summary document ≤ 1300 B
  (the publisher splits it into summary, flow, tuning and scoreboard topics of at most 1 KB each), and the
  stored plan ≤ 4095 B. Shape changes of the MQTT payload are reported (a
  documented `{..}|null` value does not count).
- **RoomEngine/RoomDemand against an oracle**: the leading source, status
  (ok/fallback/stale/lost/inactive), temperature and setpoint
  (the week program once the clock is known, else HA < 15 min, else the
  fallback, clamped). The oracle
  carries readings across plan edits as `setPlan` does. Pauses end at
  `inactive_until`. `no_demand` holds exactly when no room is usable.
- **FlowPolicy** (`HeatingController::applyFlowPolicy`, between RoomEngine and
  the shadow comparison/guard): with both options off the applied request is
  exactly the rule's (`capped` included); on or off, every heat request stays
  within [plan min, min(plan max, 80, the boiler's 0x16 limit)]; off means 0.
- **The rule and the boiler's limit**: the room engine's request never exceeds
  a known 0x16 limit (`rule_flow_above_boiler_limit` is a failure), and
  `capped` (`request.capped_by: "boiler_limit"`) is set exactly when that limit
  lowered the flow. The `flow` scenario changes the limit (25-80 °C or unknown)
  at random. `request.capped_by` appearing in the MQTT payload while capped is
  the documented shape change. heating_summary (with the
  `flow` and `night_gas` blocks) stays ≤ 1100 B.
- **Plans** are stored as `RoomPlan::storedJson()` (week programs packed when
  the API form does not fit), at most `storeBytes` - 1, and load back to the
  same plan; a request body above `requestBytes` (8192) is refused.
- **FlowDemand**: a heat request lies within [plan min, min(plan max, 0x16 limit)]
  (below the plan minimum only for a lower limit),
  and off means 0. Minimum on and off times hold (except after a flow-limit
  edit rebuilds it). Sustained demand always heats (no stuck-off state).
- **ActiveHeatGuard**: it never sends a positive flow in shadow mode, without
  confirmation, after a foreign 0x1A that followed the confirmation, with the
  route not ready, or within the boot holdoff (60 s). The flow is ≤ min(plan max, 80,
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
- **rc.5 documents**: fw/telemetry/flow (the summary's "flow" and "night_gas", with
  P1's "boiler") ≤ 1024 B, fw/telemetry/insight ≤ 700 B, "boiler" ≤ 140 B, "house"
  ≤ 110 B and every room's "free_heat" ≤ 90 B; heating_learned/<id> keeps its 1000 B
  with or without "free_heat" (P3 leaves it out of a message it would push over).
- **BoilerResponse** (P1): while the E32 drives the boiler with Smart warm-up on, no
  request (rule, curve, learned flow or optimum start) goes above max(the learned
  ceiling for the outdoor band, the plan's minimum) (`boiler_request_above_ceiling`),
  except during a warm-up: while the lead room (the usable room with the largest
  error) is 1 K or more below its target the ceiling does not apply (comfort first;
  `boiler_ceiling_warmup_steps` counts those steps);
  the rest floor is min(rest, 900 s) and never while a room is cold; the state is one
  of collecting/learned/no_return/not_driving, the rest 60..1800 s, the absorbed kW
  and kW per K finite and sane, both absent without a return, every band's ceiling in
  20..80; the stored frame is ≤ 48 B and restores to itself (daily); with the holding
  boiler, 20 held targets of the E32's own settled request are heard at least once
  (`boiler_response_never_heard`).
- **HouseModel** (P2): the slope within WeatherCurve's 0.2..2.5, UA and the emitters'
  kW per K finite and positive, the state collecting or learned.
- **FreeHeat** (P3): no lead shortened below half: hourly, for every room with a
  planned start, `shortenLeadS` at the rise's and the opposite daypart with the
  plan's implied warm-up rate and with 0, 0.01, 0.5 and 5 K/h stays within
  [lead/2, lead] (`free_heat_lead_below_half`); every daypart's rate is finite and not
  negative; the stored frame is ≤ 360 B and restores to itself (daily).
- The allocation-failure sweep includes the flow and insight topics and the three
  modules' addJson.

The rc.5 invariants were proven against stand-ins of the three modules with the
plan's hunks applied (not committed): removing the ceiling hunk from FlowPolicy was
caught (`boiler_request_above_ceiling`, 61,512 times in 20 days of `holding`), and a
FreeHeat that shortens to 20 % was caught (`free_heat_lead_below_half`).

A mutation check (scratch copies of headers with one planted bug each:
minimum on/off, reading carry-over, stale hold, day roll, DST offset, foreign
check, frost, cap, re-anchoring, BLE value lifetime, a failure-path leak) was
caught by these invariants 14 of 14 times.

## Findings (state 2026-10-29, all fixed)

`full` passes. The repro scenario keeps the deterministic reproducers, and
each fix has its own native regression test:

1. **RoomEngine::json() crashed when an allocation failed** (`ha_entities`
   array null). It now returns nullptr (`RoomEngine.JsonSurvivesEveryAllocationFailure`).
2. **ActiveHeatGuard ended its stop window without a delivered zero.** While
   the boiler may still hold a positive request, `stopping` now lasts until a
   zero was transmitted ok, with no time limit, and warns `transmit_failed`
   after the window (`ActiveHeatGuard.StopKeepsRepeatingZeroUntilOneIsDelivered`).
3. **DhwEpisodes counted a reheat right after a tap as a second tap.** The
   look-back now ignores samples from before the previous episode's end
   (`DhwEpisodes.ReheatRightAfterATapIsKeepWarmNotASecondTap`).
4. **WarmupPlanner::night() could report negative gas.** The heat per step is
   clamped at 0, and `saving_m3`/`saving_eur` are never negative (0 when the
   program's own setback is late) (`WarmupPlanner.NightEconomicsNeverReportNegativeGasOrSaving`).
5. **fw/telemetry/heating over 7900 B** came from plans that setHeatingPlan
   refuses (`plan_too_large`, 5972 and 6292 B). The `sizes` scenario now trims
   its worst cases to the largest storable plan. Any plan within the
   4095-byte store gives at most about 7100 B (`HeatingTelemetry.AnyStorablePlanFitsTheMainPayload`).

The notes were resolved as well:
- The burner keys keep their shape while the state is unknown: `null` values,
  which HA reads as unknown.
- heating_learned/<id> names its room once (HA takes the topic's id), so a
  32-character id stays under 1000 B (rc.4: with its arrival feedback). The chain checks this extrapolation
  (`mqtt_learned_room_32_char_id`).
- Near a DST change WarmupPlanner reads the UTC offset hourly and bisects the
  change, so it no longer converts each minute (about 30 instead of 1,440
  `localtime_r` calls per walk).

Still a note: a realistic 8-room plan with 4 switch points per day is
4964 B, so `setHeatingPlan` refuses it as `plan_too_large`.

## Findings of rc.5 (state 2026-11-04, open)

6. **heating_learned/<id> over 1000 B with a long room id.** Since the chain passes
   the arrival feedback as HeatingController does, a learned room with the longest
   advice reasons in both "advice" and "now" (`above_learned_range`,
   `below_learned_range`, `not_reachable_in_time`) and a judged morning is 977 B with
   the id "hal": 1006-1008 B with a 32-character id (`mqtt_learned_room_32_char_id`
   in the 60-day chains with the flow options). The per-room budget test's worst case
   has shorter reasons. Below the publisher's soft limit (1024 B), but over the
   budget; P3's "free_heat" is only added within it.
7. **TelemetryPublisher::summary() leaks a part when its key copy fails.**
   `cJSON_AddItemToObject(flow/tuning/board, key, part)` returns false when the key's
   strdup fails, and the detached part is then nobody's. The soak's replica of the
   split (the flow topic) leaked 43 cJSON blocks at one allocation of the sweep until
   it deleted the part on that failure.

## Limits

- `HeatingController` and `ModernTransport` are not host-buildable. The status
  JSON is a replica of `HeatingController::heatingStatusJson()` (keep it in sync).
- The host has a 64-bit `time_t`. The device's newlib under IDF 4.4 likely has
  a 32-bit one, so 2038 behaviour of `localtime_r` is not covered.
- FlowLearner lives in RAM. Reboots are not simulated in the chain (a reboot
  simply starts over); the `active` scenario simulates them with the stored
  confirmation. The rc.5 learners' stored frames are checked by a daily round trip.
- The chain runs no AutoTuner: the knobs are the built-in ones (with P1's rest
  floor), and P2's insights (judged with AutoTuner's day) stay empty here; their worst
  case is P2's unit test. The replay wires both.
