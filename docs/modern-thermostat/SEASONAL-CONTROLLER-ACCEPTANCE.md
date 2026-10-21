# Parent followup acceptance — existing product package, no duplicate implementation

Baseline Stage39 ff93667c0dc010f2ec83112d0eced05d218b594a. Parent reports Stage23 comfort source498a5fb0 independently accepted/canonical3b4e19b; that acceptance is preserved, not repeated or expanded into physical/source acceptance. Whole PLAN11785 continues. Generic-size remains the independent11831child's scope.

## Existing exact deliveries

Same shared dossier `open-thermostat-restart-graph-11774-20261020`:

| Scope | Existing source / manifest | Actual scope |
|---|---|---|
| Native API2 GUI apply/readback/reconnect | Stage36 0db60d12b89a75d57f599307038c6158ccb76243 / GRAPH-GUI-ONCE-RESULT.json |96nativeHA, one explicit send reservation; draft/stage/ACK-unverified/exact readback/conflict; reconnect cannot restore admission; original lost-ACK/doubleclick failures preserved. Actual Store/options/realCpppeer with mocked MQTT IO, not live frontend/device.|
| F9 diagnosis | Stage37 36ffd95e07d090520e71cb32583d2352c1a21109 / F9-TRACE-RESULT.json |16native+same16fullGTest/TUASan; same14exogenous/baseline chains and original14oracles;28scoredrows. Reference consumption defect corrected separately, ALL14corrected candidates still0/14 and rejected/insufficient. No threshold/plant/training retune or model benefit.|
| Stable logical context source plumbing | Stage38 9caeff3411e53b20310ae483ff4c0e6641f50e2e / CONTEXT-SOURCE-RESULT.json |83nativeHA/31new, real event/lifecycle/wire. SOURCE-only immutable producer callback pins; no generic trust in last_reported/polls. Default empty, old conservative120s fallback remains; no concrete producer qualified. Not a physical stable-context acceptance.|
| Actual seasonal/controller selection | Stage39 ff93667 / SEASONAL-PRODUCT-RESULT.json |61native+same61fullGTest/controller/cJSONASan,85nativeHA incl2actualsource-selectedCpp→HA cases, actual pinnedE32main syntax. Fixed reviewed shadowconfig/source pins, no actual factory selected, no full current image.|

For Stage39 use `seasonal-product-only-core.patch` SHA256 `1c3de76e6b7c07f19265234abb30f29060c39a26ca3193b243954998abae1f5a`; exact8-path archive SHA256 `a822544e582ab7f421d89290dfef343ce338f1be708750014947f0d08dbb6e97`. Baseline9caeff3. Frozen offline verifier: `python3 verify-seasonal-product-evidence.py`. Its before/source hashes,415protected source paths and genuine Git apply/reverse proof retain parent Recorder/metricsrestore/PLAN/partitions/flags. Do not reimplement or silently call it independently merged.

## This followup changes only tests/documentation

Three NEW actual controller/admission/wire tests reuse the original fixture/core and production bytes without a new controller/policy/kernel/scheduler/service:

1. Summer inhibits existing boost AND a NEW authenticated higher boost; then source all-off cannot be revoked by a further boost. Existing effective manual target remains visible but demand staysfalse; stop restriction survives, no physical output.
2. Two-zone selected controller explicitly traverses A-only→together→B-only→all-off. Unknown B never generates demand. Actual per-zone demand and controller aggregate request are checked at each transition; unqualified supervisor remains inhibited/outputflagsfalse.
3. Tiny slow-binary PI load over three complete synthetic600s cycles (901current admitted source reports/heartbeats over30synthetic minutes) never rounds a too-small pulse into minimumON. Source/safety restrictions remainzero so unknown-data inhibition cannot trivially explain the result. No per-sample storage writes: only original config save. Clock/safety/temperature are declared finite fixture inputs, NOT a physical30-minute run or protection proof.

Only these3 cases are executed natively and the SAME3 under full actual GTest/test/controller/realcJSON ASan/UBSan+leak detection. Original61/85 suites are not redundantly rerun; their frozen package integrity is checked. External dynamically loaded actual OpenSSL provider is uninstrumented. Native-only nonPIE/static sanitizer flags are not firmware build changes. Command/source hashes and results are frozen separately; native synthetic runtime duration is not E32 latency/performance. No production code/schema/parameters/model calibration/plant/threshold/profile budget/HA source/default/partition/flags changes.

## Acceptance coverage is NOT whole F4 completion

- Actual controller: summer/boost/off, explicit same frost versus window/summer/limits/off, current-source age/restore/owner/reconnect/preemption, new A/B/together/off and smallest-load pulse tests.
- Connected HA: original Stage39 two selected realCpp cases prove DHW priority and observerTTL expiry drop simulated demand while preserving target; current native HA85 is NOT repeated and NOT liveHA/physical source qualification.
- Existing corrected seasonal/HydraulicSupervisor pure core20 cases prove bounded naloop, DHW/fault/readiness/flow/minoff/monotone concurrent restrictions. **The actual ShadowController still owns a default UNQUALIFIED HydraulicSupervisor.** These pure-core tests are NOT a qualified controller-level physical hydraulic path or actual driver/valve/flow proof.
- Consequently real all-valves-closed/minimum-flow/heatdump/fault-clear/pump/actuator positions and actual group/supervisor profile/graph/feedback admission remain OPEN. No safe actuator position, flow or readiness is invented; logical zone demand cannot grant any of these. Frozen source flags are alwaysfalse.
- Current normal fullimage/stack/heap/8zoneNVS/GC/72h/real producer/browser/device/installation/source/TX/EMS/actuator/release gates remainOPEN. Parent8b364f21 E32/S3 image receipt is not a build of newerff93667. Physical dependencies do not become fictitious PASS; independent executable source work remains authorized.

Rollback only this new test/doc commit/patch before dependents; production/runtime data, graph/room/Recorder/model/settings and parent PLAN fixes stay intact. Parent alone merges canonical source/WORKBOARD; supply additive result/coverage map, never overwrite canonical old headers. No liveHA/broker/device/login/reboot/flash/install/publication/Tado/EMS/TX/actuator actions. Reproduce only new native cases with dossier `verify-seasonal-acceptance.py`, then `--sanitize`; outputs default to seasonal-acceptance-rerun-evidence, preserving originals. Model efficacy/admission is not completion.
