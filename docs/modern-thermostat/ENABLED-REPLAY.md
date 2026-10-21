# Enabled-advisory paired source harness — not production adaptive control

This is the queued followup to default-disabled equivalence. The new
`test/test_native/test_thermal_enabled_replay.cpp` executes actual
ThermalResponseModel / ThermalCoastModel / CurveAdaptation observe/propose code,
ZoneRegulator, GroupWaterPolicy and the unchanged ThermalReplay evaluator.
No production source, model mode, transport caller, store or profile is changed.

## Declared experiment

- Six independent **synthetic** calibration episodes per model, across a
  compressed 15-day calendar, are admitted through actual observe() methods,
  not injected snapshots. These are not Mark's history or physically observed
  delivery. A new actual four-hour synthetic quorum window is required before
  the prospective single +0.20 °C curve-knot proposal.
- Models then operate frozen; their advice is consumed only by a test reference
  policy. Warm-up can raise the simulated target early; coast can suppress
  simulated delivery before a lower transition; a curve proposal becomes a
  prospective local candidate parameter copy, not live source-owner adoption.
- Baseline/candidate have separate endogenous room/storage states and receive
  identical exogenous schedule, weather, synthetic plant parameters and
  faults/source gaps. Actual existing OpenSSL SHA256 binds all exogenous switches
  (including holdout power, blocked source and declared initial episode), not
  model choices.
- The toy plant is transparent: first-order heat storage (.20/min), room loss
  (.001/min), heat gain .08 scaled with supply-water temperature. It is not fitted
  to the synthetic calibration or to any home. Initial conditions and the
  coast-only prehistory are explicit. Counterfactual model validity is NOT proven.
- 14 logical days at one-minute sampling are a finite native loop, not 14 days
  of actual operation. CV bits are a **synthetic delivered-heat proxy**, not
  measured burner/flame activity, kWh, efficiency or heat savings.
- Fault/source loss suppresses the reference policy, clears any held coast,
  and reaches the actual regulator/water-policy inhibits. Blocked source cannot
  become admitted merely because stored models / enabled flags exist.
- A separate coast-only declared prior-heat episode exercises actual coast
  advice plus both actual regulator latches and changes paired plant trajectories.
  In ordinary daily warm/combined fixtures coast prerequisites are never met:
  coast-use count is honestly zero, not asserted as a combined coast benefit.

## Measured outcome — policy is NOT accepted

Six real native tests and the same six with model/reference-policy TU under
ASan+UBSan pass. Seven native/sanitizer scenario rows match exactly. The tests
pass because they check branch exercise, invariants and rejection, NOT because
the candidate policy is good.

| Synthetic scenario | Sampled occupied MAE baseline → candidate (°C) | Candidate outcome |
| --- | --- | --- |
| Cold warm advice | 0.1948 → 0.1729 | arrival gate fails: 0/14 hits |
| Cold warm + prospective curve | 0.1948 → 0.1741 | arrival gate fails: 0/14 |
| Mild warm advice | 0.2043 → 0.1705 | arrival gate fails: 0/14 |
| Mild warm + prospective curve | 0.2043 → 0.1720 | cycling gate fails; also 0/14 arrivals |
| Underpowered cold holdout | 0.1901 → 0.1776 | cycling/arrival fail |
| Coast-only declared heat initial state | 0.1945 → 0.1937 | cycling gate fails |
| Source blocked | unavailable | insufficient comparison, no demand/advice |

Lower MAE is NOT a release waiver. Warm/curve advice is actually used, with
different demand/water trajectories, but the deliberately non-fitted calibration
underpredicts arrival warm-up. No score threshold, source coverage, minimum
deadline count or fallback was weakened to make this green. Additional
calibration/model-policy work remains necessary; this packet does not install or
recommend these reference policy choices.

## Reproduction and boundaries

From the shared dossier run `python3 verify-enabled-replay-final.py`.
Native compiler/actual GTest and existing OpenSSL are the documented local pinned
environment. Sanitizer instruments the new test/reference-policy and actual
inline model/control/evaluator code; cached real GTest objects and external
OpenSSL are uninstrumented. Test-runner-only non-PIE avoids the previously
evidenced GCC12 static-ASan pre-main PIE hang. No firmware compiler flags changed.
No hosted CI, SDK/current full image, actual home fortnight, enabled production
model owner, physical safety/comfort/energy-benefit claim.

The existing native CI automatically collects the new test file. Parent owns
independent review/merge and canonical workboard integration. Reverse only the
test/doc source patch to roll back; no runtime data exists to undo. The complete
PLAN11785 continues; real configuration/apply/source/physical/release gates stay open.
