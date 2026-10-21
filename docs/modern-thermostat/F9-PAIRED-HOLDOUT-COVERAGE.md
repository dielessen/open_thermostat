# F9 coast / curve: paired holdout coverage

This is a finite source-test increment over the existing ThermalResponseModel, ThermalCoastModel, CurveAdaptation, ZoneRegulator, GroupWater and ThermalReplay. It adds no production policy, collector, service, active profile or scheduler. Models remain default disabled; tests explicitly train six separate synthetic calibration episodes, then freeze. A real reviewed model/config/admission owner is still needed before any product binding. Stored calibration is never a heat permission.

The existing coast policy uses completed delivered-heat + known-off windows, comparable weather/water/room/duration, conservative fall/residual-peak/uncertainty bounds and an imminent LOWER UTC schedule transition. Existing curve policy proposes only one observed interior knot, at most the reviewed0.25C bound, idempotently against immutable old curve. No automatic adoption. Model stores use explicit rate-limited readback checkpoints; a reset is not durably committed until its separate checkpoint succeeds. Restore starts disabled. Existing tests cover no binding, replay fences, gaps, clock/owner/target changes, DHW/window/fault/gain, inadequate coverage, weather extrapolation, exact base curve, corrupt/ambiguous writes and reset rate limiting.

## Additional paired holdouts

- Slow-floor proxy: same toy heat balance but stored-heat response0.02/minute instead of0.20/minute. This is not a fitted real floor model or new emitter capability. Calibration is intentionally unchanged; mismatch may not pass benefit gates.
- Known external gains:0.015C/minute added from10:00 through14:59 each synthetic day. Both trajectories receive the same gain; model qualification is invalidated and cached coast/advice cleared during gains. Normal bounded thermostat control is not incorrectly disabled merely because sunlight is present.
- Small-load proxy:17C outside, one-quarter default heat-loss coefficient and half default heater power. Starts, completed burns, coverage and comfort are evaluated, not a declared saving.
- Extended sensor loss: three whole synthetic days have no reported room temperature. Both controllers stop demand; no hidden toy temperature is supplied to the evaluator. Missing intervals reduce coverage and MUST prevent acceptance. Simulator internal state evolves only to create a reproducible post-loss holdout, not fabricated telemetry.

Both trajectories share exact immutable exogenous switches/dynamics hashed with the existing real OpenSSL provider; model choice is endogenous and excluded from scenario identity. Existing score thresholds are unchanged. Output rows include paired MAE, maximum occupied overshoot in centi-C, occupied in-band time, total/compared/excluded/CV-qualified milliseconds, arrival counters, observed starts/CV proxy, model usage and calibration-window counts. A separate scores JSON computes basis-point coverage from exact integer durations; absent denominators stay null. CV is simulated delivery, NOT burner/energy evidence. Physical output flags are always false.

Do not call a PASS of regression tests an accepted adaptive policy. Report each fixed holdout verdict and reason unchanged, including failures. No retuning to make the synthetic experiment green. No real history/comfort/savings, firmware image, hardware heap/NVS or two-week commissioning claim.

## Reproduction / rollback

Dossier verifiers: verify-f9-coverage.py orchestrates sequential actual native replay, same ASan/UBSan replay, and existing real model/store regressions. OPENTHERMOSTAT_REVIEW_SOURCE selects an assembled review checkout. Cached real GTest and unused cJSON object are not instrumented; actual tested models/regulator/water/evaluator/test translation unit is instrumented. Native non-PIE sanitizer flags only; firmware flags unchanged.

Reverse only this test/doc patch or revert its source commit after later dependents. Existing model source, native HA/api1 defaults, immutable older evidence, parent WORKBOARD and Recorder fixes remain untouched. No runtime data changed. Parent canonical review/build/release and all source/physical/TX/EMS/actuator gates remain open.
