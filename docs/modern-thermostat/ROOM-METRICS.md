# Bounded room / boiler reporting and Recorder sample (source only)

## Definition and limits

The existing legacy MQTT topics remain the only connection: `room_data` adds
`roomObservation`, `ems_status` adds `roomEstimateObservation`. The strict
24-field schema-2 `ems_metrics` payload and api1/api2 control contracts are not
changed. No new DB, topic, broker connection, service identity or persistent key.

A complete admitted Plus 0xE4 frame (source 8, not READ/READ_WITH_DATA) supplies
selected flow °C, supply tenths °C converted to °C, modulation %, CH/DHW/flame/pump
bits. Missing partial frames do not renew a complete observation. Sentinel /
out-of-range data is unknown, never clipped. Boiler bits are reports, not
independent flame detection or physical flow/delivery proof. Classic/raw status
has no implicit fallback into these qualified readings. Unsupported Classic
fields remain unqualified; this is not full Classic/EMS-ESP telemetry parity.

The informational 128-bit boot ID is generated once for the reporter owner with
the existing SDK random API. It is not an authentication token, credential,
actuator admission or NVS value. Sequence/observed time advance only on an actual
admitted complete telegram. GET / repeated publish cannot refresh the observation.
The room envelope captures source time before serialization; the existing
`currentTempAgeMs` supplies temperature sample age.

HA uses monotonic source-age + receipt windows:
- EMS observation: strictly less than 30 s.
- Room scheduler snapshot: strictly less than 45 s.
- Room temperature: strictly less than 300 s, range −20..60 °C.
- Supply: 0..110 °C; configured aggregate radiator rating: 0..20000 W.
- Room and EMS boot IDs must match for room modeling.
- Retained messages are not current liveness/source observations.
- Duplicate sequence/snapshot time never extends validity. Offline invalidates
  both deadlines. Counter integration clips the previous interval at the earliest
  deadline before applying new values, with no gap backfill.
- One native HA timer provides expiry even without further traffic; boiler-only
  reporting does not depend on a configured room.
- Network transit delay is not measured. These reporting windows are NOT an
  end-to-end freshness / control / commissioning guarantee.

Room “heating time” means qualified room request coinciding with reported CH
without DHW, not actual heat received. Output/energy uses an EN 442-style model:
rated output × (max(supply − 5 − room, 0) / 50)^1.3; return temperature is assumed
10 °C below supply. No measured return, thermal meter, real water flow or
hydraulic path is invented. Missing rated power / invalid inputs are unknown,
not 0 W. Qualified inactive is real 0 W. No model output drives a controller.

## Statistics / migration

Room time, power and energy and the qualified request binary sensor use new
`_v2` entity unique IDs. Old room totals are never restored into the new
definition. Only an actually existing integration-owned old sensor identity gets
a non-numeric/unavailable compatibility entity with no state class. A persistent
native Repairs issue asks users to review their own cards. Native managed cards
select only new room IDs and explain assumptions/gaps in English. Old history
is retained, not deleted, rewritten, backfilled or silently relabeled.

Existing boiler v2 boot-counter migration remains unchanged. Actual native
TOTAL_INCREASING handling of boot reset is tested with real temporary Recorder
history/statistics. Numeric source definition is distinct from qualified-current
availability. Historical freshness is not certified retroactively.

## Native CSV

Existing admin-only response service `open_thermostat.export_metrics_csv` keeps
ownership/row/entity/byte/window checks, formula escaping, cancellation behavior
and no live DB writes. Rows append `unit` / `unit_basis`. UTC timestamps are
explicitly normalized. Unknown/unavailable and real 0 remain distinct.

Default queries still request no attributes: row unit is blank / not_requested.
`include_units: true` uses the same bounded public Recorder history query with
attributes internally; only an allowlisted recorded unit leaves the boundary.
No other attributes are emitted. Current display/native definition units cannot
certify historical units: HA may have converted kWh to Wh. Export never converts
values. Advisory `definition_units` are separate response metadata, not assigned
to historical rows. Missing / unrecognized recorded units remain blank.
Query failure returns a controlled error, not partial CSV or private SQL text.

## Evidence scope

`verify-room-metrics-final.py` compiles the real EMS parser and source tests,
builds a finite C++ serializer peer, consumes its exact wire in native HA, runs
metadata/registry/expiry/restore/unload/CSV tests plus the actual temporary SQLite
sample, and typechecks the actual firmware main/MQTT wiring against pinned SDK.
No actual E32/broker/production HA calls. No hosted-CI/full image/link/browser/
physical acceptance claim. Existing CI now prepares the same finite peer before
native HA collection.

The native Recorder sample uses 5 entities × 60 logical source ticks × 3 exact
duplicate state reports = 900 StateMachine attempts. Native Recorder stores 300
new-definition history rows plus one old-alias unavailable transition. A FIFO
SynchronizeTask commits the actual queue before reads. Logical 30 s source
cadence is compressed into a finite wall-clock event fixture, NOT 30 min or 72 h
of physical use. Counts/page sizes/file/WAL bytes and native metadata/boot-reset
sum are recorded per run. commit_interval=0 is test configuration, not a
production write-rate/retention recommendation. WAL/checkpoint sizes vary.
No linear production storage forecast is inferred.

## Rollback and remaining gates

Revert only this source commit / reverse its core patch; keep parent workboard
updates. No runtime data was changed. Rolling back code does not authorize
combining new/old statistics. Keep both histories isolated until an explicit
operator review/export; no live Recorder rewrite is proposed or executed.

Parent independent canonical review/browser presentation, regular release build,
real MQTT/source cadence and delays, actual device/client latency, real retention
period, Classic parity, room-model calibration/benefit and all actuator/TX/EMS/
physical installation gates remain open. Whole PLAN11785 continues.

## Independent parent restore review — correction required before merge

Original Stage21 5d413549 was independently rejected despite its parser/HA suite:
RoomEstimatedEnergy / RoomHeatingTime read converted display State without its
unit. Parent proved1000Wh became1000kWh and600s became2160000s. It was not
accepted/merged/deployed. Those original tests did not exercise new counter
restoration through actual native sensor-unit preferences.

Corrected room sensors inherit the supported native HA RestoreSensor.
async_get_last_sensor_data supplies the native value AND native unit. The native
HA EnergyConverter / DurationConverter convert only explicitly compatible units
to canonical trackerkWh/seconds, with finite/nonnegative bounds (1e9kWh,1e12s).
Unknown/missing/incompatible/nonfinite/negative/overflow native data is rejected.
There is deliberately NO display-State fallback. Missing native extras start a
new current counter at0; no old displayed value or legacy total is imported.
In particular, a display-only1000Wh or600s is NOT restored; compatible explicit
native extra data1000Wh restores1kWh and600s restores600seconds.

Native counter values are no longer rounded before native extra-state storage;
suggested display precision is4(time) /5(energy). This avoids accumulated rounding
from unit-converted display values. Legacy aliases never invoke either restore
getter or feed new totals.

The correction includes35 actual HA EntityPlatform / RestoreSensor lifecycle
cases (add/remove/readd, native registry unit preferencesWh/kWh,s/min/h, Decimal,
missing/incompatible/nonfinite/negative/overflow units/data). Only the initial
persisted native restore-cache boundary is populated. Restore getters, unit
conversion, entity lifecycle and subsequent remove/readd native snapshots are
actual HA implementations, not monkeypatched. This is a temporary native HA
fixture, not a production restart/history modification.

Corrected combined targeted HA suite:120PASS; parent's two Recorder tests remain
byte-unchanged. One old parent-owned race fixture remains excluded locally as
before; parent has its own accepted FIFO test-only fix. Firmware/parser/SDK source
bytes are unchanged by this correction. Full corrected Stage21 core patch
excludes Stage22 test-only replay, parent workboard and all old Recorder tests.
