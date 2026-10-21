# F9 diagnosis: reference consumption defect, not demonstrated model benefit

This increment reuses the existing ThermalEnabledReplay test/reference execution and actual observe/propose/ZoneRegulator/GroupWater/ThermalReplay code. It is **test/doc-only**. No production model algorithm, owner, profile/default, codec/version, storage/backend/resource budget, wire, control output or runtime binding changed. A production model caller still requires separate qualified integration; this package does not pretend a test-only helper is that caller.

## Proven execution defect

The opt-in reference policy treated every new optimum-start estimate as a continuously required ON command. The actual cold trace starts at replay minute344 with room1936centi-C and model lead984seconds. At minute358, room2004 leaves the start-temperature comparison radius; the actual model returns model_insufficient_evidence/comparable0. The reference immediately drops its previously adopted2100 target back to1900, and regulator demand stops before the scheduled arrival. This is a reference **consumption/lifecycle contract defect**, not proof that the model's comparison gate is wrong. Room warming out of its *starting* comparison band is not by itself loss of source/owner/clock validity.

The separate enabled reference variant now adopts one bounded future schedule target. Existing qualified start evidence is required first; subsequent plan retention is scoped to the same owner-epoch, binding, target generation, current automatic target, next transition/target, exact weather/water and frozen model mode. Unknown reason, lost source/clock, stop, changed scope, expired transition or missing conditions invalidates it. If a later model_insufficient_evidence occurs, eligible count/day/span must STILL meet the existing profile and the room cannot have cooled below adoption temperature: only the known moving-room comparability case is retained. Limits/qualified-permitted controls and the normal regulator still win; this never means unconditional heat. The helper is disabled by default and confined to this test reference. It is not persisted, advertised or an admission token.

The original reference variant and ALL14 previous oracle records remain unchanged for exact comparison. A fourth endogenous Choice switch selects only corrected consumption; it is not added to exogenous weather/plant identity. No calibration, plant parameter, schedule or evaluator gate was tuned.

## Independent insufficiency remains

Six actual observe-qualified SYNTHETIC training episodes span15calendar days. Their declared ramp is10centi-C/minute (600centi-C/hour); this is not a fit to the independently declared holdout plant. Actual first advice in cold requests984seconds for164centi-C deficit; the sampled whole preheat episode has much slower net rise. Mild/half-power/slow-floor holdouts differ still more. The counts/span/domain checks qualifying synthetic records are NOT proof that this model transfers to a house or a different plant.

Cold first arrival becomes20.12→20.16C without prospective curve,20.13→20.21C with it; neither reaches the original20.5C lower comfort boundary for21C arrival. **Every corrected candidate still hits0/14 and every one of the14 assessments remains rejected/insufficient.** Those simulated state changes are not physical comfort/energy/model improvement claims.

At the scheduled target transition the trace can show model_source_not_fresh while permitted remains true: the existing observation deliberately changes targetGeneration and the model rejects that first discontinuous learning/advice frame. This is not a missing thermometer report or an explanation for prior underheating. Arrival temperature is the state reached BEFORE the new target step; the ordinary regulator still receives the valid21C schedule target. That expected reset is retained, not repaired away.

Timing's reason replay_deadline_worse includes the original ABSOLUTE80% hit requirement as well as baseline noninferiority. Baseline0/14 and candidate0/14 are equal but still inadequate; equality is not a PASS. Missing/unqualified arrivals remain in the known14-attempt denominator. No threshold was relaxed.

Cycling checks are not just total starts. In mild+curve both paths have128 synthetic CV-proxy starts, but starts per qualified ON-hour are3.185400→3.218776 and mean completed ON-run1130.156→1118.438seconds. Both original rate/mean-run comparisons fail. Underpowered and coast-only also fail their actual cycling products; DIAGNOSIS.json retains the exact integer left/right products. These are toy CV-proxy observations, NOT actual boiler burner starts.

Slow-floor fails original in-band/100centi-C overshoot constraints; external gain fails no-extra-overshoot noninferiority. Missing sensor days fail90% coverage. Incomparable+5Ctraining/−20Choldout yields zero real comparable counts/no advice; baseline equivalence is expected failclosed behavior, not benefit. Window/DHW/fault/gap cases preserve inhibits, missing observations and fresh-owner requirements.

## Trace/evidence guarantees

- Existing13 tests plus3 new consumption tests: **16 native PASS and SAME16 full GTest+test/model/regulator/evaluator ASan/UBSan PASS**. Native-only nonPIE avoids the already evidenced static-ASan startup issue; no firmware flag change. External actual OpenSSL provider is uninstrumented; no unused cJSON is linked. These are not new image/SDK/wire/physical tests.
- All14 original oracle fields AND the entire original trace-event prefix are unchanged. Final28 scored rows and all native/sanitizer trace rows exactly equal.
- Actual baseline frames form a bounded SHA256 chain using the existing real OpenSSL provider. Every before/after pair has the SAME exogenous digest and SAME baseline frame chain, not merely equal totals. Absent samples have explicit missing markers, not fabricated measurements. Individual frame fingerprints are bounded, no full timeline string accumulated.
- Optional event trace is capped4096 rows per execution; all28 recorded executions report zero dropped rows. Events contain source/proposal reason, actual comparison count/lead, common/effective target, actual regulator-derived toy delivery, arrival and CV edges. Unqualified trace temperatures are internal simulation state, not received physical measurements. The evaluator's original null/exclusion handling is unchanged.
- Native scope unit includes17 stop/binding/owner/target/generation/water/weather/clock/future-reason/mode variants, including replayed start flags after changed scope. No old plan is restored from a model checkpoint. Algorithm/codec versions and store bindings remain protected unchanged source; no new persistence format or8-zone promise.

All experiments are synthetic. Existing immutable model evidence and source/owner-loss negatives remain. Production default-disabled owner/model connection, qualified physical observation/delivery adapters, same-source release gates, heap/callgraph/NVS-GC/8-zone/72h/device/thermal acceptance remain OPEN. No HA/broker/device/TX/EMS/Tado/actuator/login/reboot/flash/publication action.

## Reproduce and rollback

Use dossier verify-f9-trace.py, then --sanitize, then collect-f9-trace.py. These finite native commands compile the SAME existing replay TU and actual GTest, not a second simulator/service/collector daemon. Native/sanitizer commands and source hashes, baseline chains, per-scenario failed gate components and before/after trace are in f9-trace-evidence/. The pre-correction trace is preserved separately.

Rollback only this new two-path test/doc source package before later dependents; no model/Store/NVS/Recorder/settings/history erase or parent WORKBOARD/PLAN overwrite. Parent alone integrates the additive WORKBOARD result. Whole PLAN11785 stays in progress.

## Full scenario result (simulated first arrival state / synthetic CV starts)

|Scenario|First arrival before→after (°C)|Hits before→after|Starts before→after|After rejection|
|---|---:|---:|---:|---|
|cold_warm_coast|20.12→20.16|0/14→0/14|324→323|replay_deadline_worse|
|cold_warm_coast_curve|20.13→20.21|0/14→0/14|326→322|replay_deadline_worse|
|mild_warm_coast|19.60→19.60|0/14→0/14|127→127|replay_deadline_worse|
|mild_warm_coast_curve|19.63→19.63|0/14→0/14|128→128|replay_cycling_worse|
|blocked_source_models_cannot_authorize|14.77→14.77|0/14→0/14|0→0|replay_insufficient_data|
|cold_underpowered_holdout_not_tuned_to_pass|19.47→19.47|0/14→0/14|294→294|replay_cycling_worse|
|cold_coast_only_declared_heat_initial_state|19.15→19.15|0/14→0/14|329→329|replay_cycling_worse|
|slow_floor_storage_holdout|19.72→19.72|0/14→0/14|97→97|replay_comfort_worse|
|known_external_gain_holdout|20.12→20.16|0/14→0/14|254→253|replay_comfort_worse|
|small_load_low_loss_holdout|19.18→19.18|0/14→0/14|28→28|replay_deadline_worse|
|extended_sensor_loss_no_fabricated_samples|20.13→20.21|0/14→0/14|254→251|replay_insufficient_data|
|incomparable_weather_no_extrapolated_advice|18.99→18.99|0/14→0/14|567→567|replay_deadline_worse|
|window_dhw_fault_preempt_enabled_advice|20.13→20.21|0/14→0/14|324→322|replay_deadline_worse|
|absent_telemetry_fresh_reconnect_no_cached_advice|20.13→20.21|0/14→0/14|321→317|replay_deadline_worse|

Blocked-source state is unqualified internal toy state; not an observed arrival measurement. Qualified/missing deadlines and detailed failed clauses are retained separately in DIAGNOSIS.json.

Verifier reruns default to f9-trace-rerun-evidence/ (OPENTHERMOSTAT_F9_TRACE_OUTPUT override), preserving frozen f9-trace-evidence/. The collector compares both current cohorts with the frozen historical before/oracle. --before rejects any source other than its exact originally instrumented source hash; final-source legacy cohort reproduces its score and trace prefix. No historical failure is overwritten.
