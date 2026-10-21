# Paired thermal replay evaluator — source11785

ThermalReplay is a constant-memory OFFLINE paired-trace assessment kernel, not a
production model/source admission or heat command. No active firmware/HA caller,
factory, IO/service/watcher, parameter adoption or permission is added.

Both result streams must identify SAME exogenous scenario and share ordered UTC/
monotone timestamps, target/occupancy context. Invalid/repeated/backwards/clock/
budget/unpaired traces latchfailed. Missing/sequencegap/too-long intervals are
excluded but remain in coverage denominator. No absent temperature ->zero.
Sampled trapezoidal ABS error and BOTH-endpoint in-band time are not continuous
physical measurement. Qualified occupied points retain max overshoot. CVqualified
observed transitions/time and COMPLETE observed runs stay separate from temperature
coverage; first already-running or gaps never invent a start/complete burn. Unknown
combustion yields cycling unavailable, not zero/good proof. Classic/inferred data
may not silently be marked physically qualified.

Only immutable fresh arrival events qualify timing. Unknown event not a hit,
repeated later warm data cannot revise it, skipped IDs countmissing attempts.
Safety violations count EVEN on excluded/unqualified fault frames, cannot hide
behind coverage. Evaluate independently coverage/MAE/in-band/overshoot, starts per
observedCVhour/completedmeanrun, deadlinehits, safety. Overall pass requires ALL
criteria and minimum3complete observed runs per side and10qualified arrivals.
Bounded profile tolerances are explicit reviewed testcriteria, NOT learned or
installation defaults. Scenario IDs/asserted quality aren't authentication or
proof that a dataset represents a real home; owner provenance remains necessary.

## Actual code results, SYNTHETIC input only

12new actual GCC checks +same12ASan/UBSan PASS; actual cJSON report writer and
cached realGTest uninstrumented, actual scorer/regulator test TU instrumented.
12semantic scenario reports identical normal/sanitizer. Real ZoneRegulator runs
against transparent two-state SYNTHETIC identical-physics plants in two climates;
candidate uses DEFAULTDISABLED adaptation (equivalence regression, NOT evidence
of enabled start/coast/curve benefit).

|24h toy plant|Sampled MAE|Maxovershoot|ObservedCVstarts|Mean completeCVrun|
|---|---:|---:|---:|---:|
|Cold; identical baseline/candidate|0.1662C|0.33C|27|660s|
|Mild; identical baseline/candidate|0.2022C|0.45C|11|600s|

Both11arrival attempts/10qualified/10hits; deliberately unqualified10min fault
includes one arrival. First fixture with only9qualified was CORRECTLY refused;
REPLAY-FIRST-* preserved, final adds one independent synthetic arrival, no weaker
gate/assertion or removed fault. Separate9known test must still refuse.

Deliberately fault-bypassing candidate has LOWERsampledMAE0.1587vs0.1638C but
5safetyviolations and is REJECTED. Independent inside-band-worseMAE, overshoot,
double-cycling,7/10arrival, missing data/combustion and unpaired/clock/gap cases
also refuse relevant acceptance. Thus favorable comfort alone is not a safetyGO.

Pinned actual Xtensa add/assessment compile-to-object PASS; real comparator392B,
assessment184B. Offline use only, no full firmware link/8zone resource/real-time/
actual home historical replay/fortnight/live comfort/physical or savings claim.
Enabling adaptive models and representative paired counterfactual/actual historical
noninferiority remain OPEN; do NOT relabel this disabled-default regression as that.
Whole F9 and full PLAN remain in progress.

Run sequentially: python3 verify-replay-native.py; python3 verify-replay-sanitizer.py;
python3 verify-replay-e32-object.py. Sanitizer reuses known actual cachedGTest
framework object hashes/compile provenance in REPLAY-SANITIZER-COMMANDS.json.
Rollback reverse replay-only-core.patch/revert source commit. No runtime/device/
HA/broker/EMS/Tado/config/credentials action. Parent sole canonical merger.
