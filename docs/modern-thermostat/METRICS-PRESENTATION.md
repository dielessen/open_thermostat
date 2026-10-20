# F5 native graphs / export / history boundary —11785 source

Existing optional integration-owned RoomDashboard gains native Rooms, Heating,
Boiler observations, Analysis and Diagnostics views. It only edits its own
managed dashboard, not user dashboards. Registry IDs follow renames, disabled
hub entities are excluded, nonexistent return/request/flow sensors are not
fabricated. Shadow mode still forwards only its existing climate platform;
this package does NOT claim a new active shadow dashboard/metrics transport.

Native history cards separate room target/observed temperature, boiler-reported
selected/current flow, reported burner modulation percent and reported CV/DHW/
flame/pump bits. Selected flow is not an acknowledged E32 water command. Legacy
raw status may lack per-field TTL; Classic flame/flow and physical operation stay
unqualified. No inferred bit or raw stale status is made actuative by a chart.
Modulation is not electrical power-factor or kW: both HA sensor metadata and
existing MQTT Discovery label/class are corrected without identity changes.

Analysis shows CURRENT boot-local estimated/integrated counters with explicit
not-meter labels. Adds previously emitted unattributed-energy and observed-
reported-flame-time fields as optional sensors. Numeric strings, nonfinite/
negative cumulative values and out-of-range modulation are unknown; real zero
and signed outdoor values retain meaning. Per-payload schema/protocol quality
is exposed. Cumulative total-increasing boot reset semantics remain unchanged.

## Historical statistics are not silently certified

Actual old-schema numeric EMS receipt creates one persistent native nonfixable
Repair per entry, with no credential payload. It is not auto-cleared when new
schema2 arrives because that cannot repair old records. Diagnostics exposes the
observed issue and explicitly says historical definitions are NOT verified.
No issue by itself is not a clean-history claim.

Counter aggregate charts are NEVER enabled for retained unversioned statistic
IDs. Subsequent METRIC-DEFINITION-V2.md implements explicit new numeric fields/
entity/Discovery/statistic IDs, old aliases unavailable/no statistics, v2-only
new aggregate charts and native migration guidance. No automatic delete, rewrite,
backfill or retention change. Old history is not certified; existing registry
references are retained, user-managed cards can explicitly select new entities.

## Native response-only CSV

Admin Developer Tools action open_thermostat.export_metrics_csv takes loaded
entry_id, explicit timezone-aware start/end (past, nonempty,max24h), optional
exact enabled integration-owned entity_ids (max64) and limit1..5000(default1000).
It returns CSV text plus queried/unqueried entities, rows, truncation and quality/
retention warnings. No extra endpoint, file writer, DB/driver, service proxy or
external entity export. It uses existing native Recorder executor and public
state_changes_during_period(read_only session, no attributes, bounded SQL limit).
No HA DB or statistics write is requested by the handler; normal HA service
audit recording remains HA's behavior.

CSV contains UTC, entity_id, state, definition_quality, never arbitrary state
attributes/entry credentials. Text formula prefixes are escaped; true negative
numbers are retained. UTF8 output limit1MiB and row truncation are explicit.
It is state CHANGE export, no inferred interval coverage/initial baseline,
and hourly LTS cannot recreate purged on/off detail. Legacy counter definition
cannot be established from attribute-free historic rows and is labeled unproven,
never silently called corrected schema2.

## Evidence / rollback / remaining

verify-metrics-presentation.py: actual HA2026.10.2 registry/cards/services/
AuthManager(nonowner user denial)/Repairs/lifecycle/redaction; actual temporary
on-disk SQLite Recorder roundtrip and native bounded read. Some executor-boundary
negative tests intentionally inject query output; that is not the SQLite claim.
Only local test database/user/config was created, no production action.
Five upstream dependency deprecations are reported, no skipped tests.

Open: actual native Lovelace browser visual check, shadow metrics/platform/status
owner, E32 requested-water/return freshness capabilities, reliable Classic fields,
historical migration decision, real Recorder size/write-rate/retention measurement
and installed device/phone graphs. No speed, installed frontend or heat proof.
Rollback reverse metrics-presentation-only-core.patch/revert this source commit;
preserve parent WORKBOARD and no production history needs restoration.

## Subsequent source correction
Stage10 chart gating alone was insufficient to isolate Recorder background sums. See METRIC-DEFINITION-V2.md and METRICS-V2-RESULT.json for actual numeric field/identity separation. Original2fb source/evidence remains a distinct frozen historical increment.
