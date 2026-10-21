# Residual/cooling and coast advisory — source11785

ThermalCoastModel reuses ThermalObservation/LearningMode/UtcSchedule. Normal actual
DELIVERY qualification is an owner input, never inferred from a request/TRV ratio,
heartbeat or metrics receipt. Fixed reviewed profile; binding digest must include
zone/source/emitter/profile/algorithm identity. No active api1 caller/capability/
model owner/namespace/GUI or physical control application.

Defaultdisabled, independentfrozen/shadow/reset, monotone admission/report highwater
survives bad input/mode/reset. A full observed heat period (last KNOWN heat timestamp,
not first off timestamp) then full known-off window is necessary. Restarted heat,
gaps/target/clock changes, DHW/window/fault/manual/gain/source/delivery/conditions
loss reject partial windows. Negative weather valid; cannot train from walltime alone.

16complete independent windows max, >=6cycles/6distinctdays/14span and varied outside
conditions plus>=3comparable weather/water/room/preceding-heat-duration windows.
No current-heat startup or long-duration extrapolation. Robust median OBSERVED
whole-window net cooling rate is a diagnostic proxy, not identified physical b.
Maximum residual rise and MINIMUM whole-window delta across comparable windows,
not optimistic median/sub-window interpolation, bound a coast proposal. Additional
reviewed rate×two maximum report gaps +uncertainty accounts conservatively for
transition timing and missed extrema; empirical assumptions are NOT physical proof.

Only actual active imminent LOWER UTC schedule transition; the CURRENT occupied
target's comfort lower bound and overshoot upper bound must hold until transition.
Start-model qualification defaults false and must be derived by the SAME admitted
reviewed owner/binding/model generation, NEVER copied from an untrusted API flag.
No active owner exists yet: this bool does NOT close start-model/product admission.
coastNow is explanatory shadow advice, never heat withdrawal/actuator intent.
A real paired baseline/counterfactual replay and actual comfort acceptance remain OPEN.

CoastModelStore uses existing ControlStore interface and real SHA hex, separate
versioned/binding-bound bounded554B codec. Explicit checkpoint>=30min, no per-report
writes, exact precondition/readback, ambiguous failure disables/latches without
retry; restore data startsdisabled/noadmission. No actual NVS key allocation.
Reverting data/reset in RAM is not durable before successful checkpoint. Snapshot
hash is integrity, not authentication. Existing warm model/store untouched.

## Verification and resource boundary

40actual GCC C++ checks=21newcoast/store+19unchangedwarm/store. Same40 PASS under
ASan/UBSan instrumentation of actual model/test translation units (real GTest
framework uninstrumented, actual OpenSSL SHA provider). Counts overlap.
Pinned Xtensa/Arduino2.0.17 compile-to-object of actual new observe/propose/checkpoint
methods PASS; real target sizeof model696B, snapshot484B, codec max554B. Compiler
per-function estimates: proposal240B, checkpoint592B, observe wrapper48B; NOT full
callgraph/loop/8zone heap/NVS GC capacity. No active factory allocation. All-model/
8zone persistent budget remains a real admission gate, not silent unlimited storage.

Initial parallel sanitizer+native+Xtensa attempt hit512MiB test environment limit;
target55s timeout and stopped sanitizer explicitly recorded. Sequential final
object compile and instrumented checks PASS; no product workaround/config change.
No normal full firmware link/release, real-time fortnight, home historical replay,
live comfort/savings, physical climate/boiler/phone or runtime action claim.

Reproduce: python3 verify-coast-native.py; python3 verify-coast-sanitizer.py;
python3 verify-coast-e32-object.py, SEQUENTIALLY within512MiB.
Rollback: reverse coast-only-core.patch/revert source commit before deployment;
no live data/config/device action. Parent sole canonical merger.
