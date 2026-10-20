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

Existing sensor IDs/field names are retained; names explicitly say estimated.
Energy and integrated water use total_increasing: reset on controller boot is
intentional and HA handles that counter reset. Mean flow remains measurement.
Native HA rejects old/unknown metricsSchema for these counters/rates, so old
consuming deltas cannot silently become new cumulative statistics. Historical
statistics already written by old firmware cannot be repaired automatically;
review/export them separately. No live recorder/registry/config changes performed.
No persistence of current data across boot or fabricated all-time totals.

## Evidence and remaining acceptance

Actual native EMS parser + EmsMetrics tests and actual HA sensor metadata/schema
tests are in the11774dossier, with before-source reproduction.
No product performance claim; no live meter/counter acceptance, Classic flow
qualification, physical time series, mobile graph/CSV/recordervolume proof or
firmware build/install is implied. Existing protocol locks and writers untouched.
