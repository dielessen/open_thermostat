# Thermal response / optimum-start —11785 source increment

Default disabled. Frozen means historical advice only; shadow observes qualified
runs and computes advice. No mode in this increment applies PI gains, setpoints,
water parameters, boiler/actuator commands or model-confidence physical claims.
The existing api1 controller does not advertise or instantiate this model.

## Input and replay boundary

The future owner supplies profile/source/clock/heat-delivery/normal-control
admission after existing provenance/session checks; a naked room change or MQTT
receipt is not delivery evidence. A monotonically increasing boot-local
admission epoch, report high-water mark and target generation fence reconnects,
cached reads and schedule changes. Invalid frames and mode changes cannot clear
the high-water marks. New ownership/epoch must itself be verified by the owner.

A continuous known-off interval precedes every independent warm-up. Every segment
needs fresh conditions, known actual delivery, stable outdoor/water conditions,
bounded room rate and continuous monotonic/UTC agreement. DHW, window, fault,
manual tests, unknown conditions or unexplained gains abort the run. A gap/clock
jump/target change cannot produce immediate advice. Rate learning uses completed
runs, time-weighted weather/water, never a getter or poll.

## Bounded advisory

Fixed16 runs; explicitly reviewed profile and nonzero32-byte binding/profile
digest. Forecast requires at least6 independent starts and6 distinct UTC days,
a profile minimum of14–60 covered days, outdoor variation and at least3 comparable
water/outdoor/starting-room conditions. The requested rise cannot exceed each
selected observed rise. Old/future runs excluded. Upper median of comparable
observed time/rise gives a conservative simple response estimate plus explicit
margin, not identified physical a/b coefficients or a savings claim.

Uses only a valid future transition from existing UtcSchedule. Expired/past/
time-invalid schedules and stale observations cannot replay an old boost.
Emitter lead over the profile ceiling is rejected, not silently clipped.
Result carries planned UTC, lead, coverage/counts, late/start-now and reason;
these are advice, never output permission. There is no coast/curve/gain change
or automatic live optimum-start enable in this increment.

## Persistence and reset

The unchanged ControlStore interface is extracted into its own pure header.
ThermalModelStore requires an explicitly supplied SEPARATE atomic model key;
no NVS key/factory, config namespace write or migration is installed here.
FormatOTTM0001 contains version/count/binding, at most16 fixed20-byte LE records
and a real SHA256-hex integrity digest; maximum426 bytes per model. SHA256 is
integrity, not firmware authentication. Binding must include source, emitter,
algorithm and the complete reviewed model profile.

Load refuses unknown format/version/binding, bad chronology/rates or corrupted/
truncated bytes without replacing configuration. Restored history always
disables learning and restores no source/session/live readiness. Checkpoint is
explicit after completed runs/reset, minimum30min between changed writes.
A rate-limited reset is immediate in RAM but NOT durable until a later successful
checkpoint; the caller must show pending persistence. No per-sample writes.
Before write, exact previously loaded bytes must still match; ambiguous commit,
readback mismatch or provider error latches disabled storage-fault with no retry.
An old incompatible model requires a separately reviewed owner reset/migration,
not an automatic erase.

## Evidence and remaining product work

verify-thermal-model.py compiles real C++17/GTest with strict warnings, actual
OpenSSL SHA256 via existing ControlTestHash (dynamic runtime ABI, no new crypto
headers/linker requirement) and real-cJSON ShadowController regression cases.
Tests simulate clocks/reports, not actual fortnight-long measurements.
The independent20min expected warm-up, robust outlier, bounded floor/emitter
lead, gaps, invalid inputs, replay fences, storage faults and exact signed codec
are covered. No historical home data was invented or used.

Open: active versioned graph/wire owner and approved key/resource allocation,
HA learning controls/status, cooling response/coast, slow curve adaptation,
baseline/comfort/start-rate evaluation on representative replay, actual14day+
qualified observations and physical commissioning. F9/R12–14 remain product OPEN.
Rollback: reverse thermal-only-core.patch/revert its source commit; no runtime
storage or installed firmware was changed.
