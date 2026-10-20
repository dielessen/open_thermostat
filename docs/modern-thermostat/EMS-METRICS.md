# EMS metric integrity — source increment11785

Boot-local counters, not persisted energy/meter readings. metricsSchema2 explicitly
changes the old consuming interval semantics. No additional storage writer.

## Semantics

- Energy is estimated nominal factory kW × reported modulation while fresh reported
  Plus flame is true. NOT a measured gas/heat meter, calibrated fuel model or
  efficiency/cost claim. Missing nominal/power/flame gives no inferred energy.
- Each admitted real observation advances previous samples only to their30second
  freshness deadlines. Reads never advance, renew or reset totals. A gap is not
  filled indefinitely; a later report may account the bounded previously fresh
  tail. Counters are therefore observation-driven, not read-rate-dependent.
- CV/DHW split uses the previous interval's fresh exclusive mode. Simultaneous/
  unknown mode is unattributed; neither doubles the total. Flame-off stops the
  estimate even if an unchanged modulation value remains.
- Water volume integrates reported tenths L/min into litres. warmWaterAvgFlow is
  the cumulative mean over observed/fresh intervals, not the polling interval.
  warmWaterFlow is the instantaneous fresh reported rate. Unknown/invalid values
  are null, not fabricated zero; real zero remains valid. No division by zero.
- observedBurnerSeconds integrates fresh Plus reported flame only, null before
  observation. This is no independent physical flame sensor.
- Outdoor is signed tenths Celsius, invalid sentinel/range rejected and180s TTL.
- Source address08 and data operation required. Fragments cannot refresh absent
  fields; malformed/unavailable power/flow invalidate their samples. Backwards
  monotonic input invalidates volatile samples without subtracting totals.
- Scope is Plus. Existing Classic normalized boiler fields keep their own
  quality/TTL; unreliable Classic flame/flow/counters are NOT promoted to metric
  truth. Classic consumption remains unsupported rather than fabricated.

## HA / discovery compatibility

Corrected numeric fields and HA/Discovery IDs are explicitly versioned. Root
metricsSchema2 AND counterDefinition observation-total-v2 identify the new
definition. Corrected field names append V2; corresponding hub/Discovery IDs
append _v2 and names say definitionv2. Unversioned legacy numeric field names
are explicitly null, not new totals and not zero: retained old Discovery
templates therefore become native MQTT unknown, never new numerical totals
under old statistic IDs. Outdoor/status identity remains unchanged.

Existing custom-integration registry IDs/history are preserved as unavailable
diagnostic compatibility aliases with no state_class, ONLY if already owned by
that entry. Fresh setup creates onlyV2entities; no cross-entry identity takeover.
A native persistent migration Repair explains choosing new IDs in user-managed
cards. User dashboards/history are not rewritten. New v2 energy/water/time
TOTAL_INCREASING statistics handle boot reset, mean flow stays MEASUREMENT;
native counter aggregate charts include v2 IDs only, with no legacy backfill.

This corrects the incomplete earlier same-ID schema gate: HA Recorder reuses
prior sum/state for a statistic ID, so only hiding graphs/adding a Repair was
not enough to isolate background sums. No actual home-history contamination
was queried or claimed. Historical old data remains unverified/untouched.
Older firmware + new HA version produces unknown version2counters and explicit
guidance, not reinterpreted deltas. Firmware/integration update/publication is a
separate operation; this source increment installs nothing.

## Evidence and remaining acceptance

Actual native EMS parser + EmsMetrics tests and actual HA sensor metadata/schema
tests are in the11774dossier, with before-source reproduction.
No product performance claim; no live meter/counter acceptance, Classic flow
qualification, physical time series, mobile graph/CSV/recordervolume proof or
firmware build/install is implied. Existing protocol locks and writers untouched.
