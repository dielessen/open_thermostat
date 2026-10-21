# F10 / R31 — domestic hot water presentation contract

This increment exposes read-only information through the existing native HA options flow, diagnostics, Sensor platform and integration-managed Lovelace dashboard. It does not add a water-heater/number/switch/select control, service, scheduler, collector, subscription, HTTP poll or firmware capability advertisement. Boiler DHW priority, source observation admission, all hardware/TX locks and api1 defaults remain unchanged.

## What the source actually supplies

Observed EMS family comes only from EmsController's existing protocolProfile (BoilerCapabilities). It is an observed telegram family, NOT the hardware boiler series. A generic HA model name, protocolVersion, metric counter or incoming writeSupported flag cannot select a DHW write capability. Observed family alone does not mark optional fields supported: a valid typed/range-bounded reading must actually have been received (or Plus activity must pass the existing observation validator). Missing/malformed optional fields remain unknown and are not displayed as supported. No physical profile is qualified here.

|Field / transport|Classic observed|Plus observed|Unknown / conflict / old firmware|Shadow counter transport|
|---|---|---|---|---|
|Selected DHW temperature|Last reported, °C; physical source age unknown|Same|Unknown, no inferred support|No field contract|
|Current DHW temperature|Last reported raw tenths °C converted to °C; physical source age unknown|Same|Unknown|No field contract|
|Enabled flag|Strict reported boolean, not a control|Same|Unknown, not false|No field contract|
|Activity|Inferred adapter state, explicitly unqualified|Only existing qualified roomEstimateObservation DHW flag is shown as source-bounded; raw cached flag cannot qualify it|Unknown|No field contract|
|Flow|Unreliable; numeric value suppressed|Last reported L/min, source age unknown|Unknown|Only separate integrated reported-flow metrics; not a DHW configuration grant|
|Comfort mode / DHW schedule / runtime|Unsupported on this HA transport|Unsupported on this HA transport|Unsupported|Unsupported|
|Temperature/comfort/time writes or reset|NONE|NONE|NONE|NONE|

ClassicBoilerMonitor separately contains diagnostic counters that are marked unreliable and a monitor-reported target. Their existence at the authenticated diagnostic HTTP endpoint does NOT create an MQTT/HA control or timer capability; this implementation does not poll that endpoint. No model-generic support is invented from those offsets. Current firmware can report useful temperatures without supplying genuine per-field observation age in ems_status; cached values are therefore never labelled live/source-qualified. A 30-second packet receipt bound is exactly that: packet freshness, NOT boiler measurement freshness. Repeated publications may refresh receipt state, never qualify a physical sample or renew the room model.

## Native product path

- Existing HeatingTracker receives the same ems_status/status subscriptions. A bounded allowlisted presentation cache shares its existing listener/timer and expires after30s, including when no rooms exist. No extra IO or periodic worker.
- One read-only diagnostic Sensor, existing-prefix_hub_dhw_capabilities, has no unit, state_class or writable features. Stable profile/status + fixed allowlisted fields/quality are exposed; unchanged snapshots do not produce a state write per poll. Unknown/stale/offline/retained/malformed/clock reversal is explicit; no numeric zero/off fallback.
- Options -> Domestic hot water (read-only) shows current capability limitations with an empty information form. Closing it aborts informationally, never creates options/reloads/config writes. Incoming temperature/mode fields cannot enable a writer.
- Diagnostics uses the same whitelist, never forwards raw source payload, broker credentials, session IDs, unknown profile strings or entity names.
- The managed Diagnostics dashboard displays only supported-read fields from the integration-owned registry entity, follows rename and excludes disabled/foreign entries. Temperatures/enabled are clearly LAST REPORTED with unknown source age; Classic activity/flow have their separate warning. No custom frontend/card or action call. Native Jinja rendering is tested; this is not a physical browser screenshot claim.

## Compatibility / migrations

Existing DHW numeric/binary registry IDs, units and user-owned dashboards/history are not rewritten, renamed, backfilled, reset or deleted. Raw old entities remain available to existing consumers, not silently certified as physically fresh. The integration-managed generic EMS list no longer duplicates the four unqualified temperature/flow/enabled rows; the explicit quality-labelled DHW panel replaces that presentation only. No old statistics definitions are repurposed; the new status sensor has no statistics. No new persistent settings or model selection; restarting the integration begins unknown until a fresh non-retained observation.

Exact parent test-only Recorder SynchronizeTask barriers from e809264 were imported separately as local9fd933d. Keep them on rollback. The original105/107 failure evidence is preserved. These test barriers are not Recorder/core/product changes and no live Recorder history is altered.

## Gates and rollback

Reproduce from the source dossier: verify-dhw-ha.py for native supported/unknown/invalid/stale/retained/migration/redaction/lifecycle/options/Recorder regressions; verify-dhw-integrated.py for existing combined discovery with fresh actual C++ peers and no Recorder deselections. Only public MQTT/platform IO is intercepted in finite offline tests. No host frontend/real device/broker/EMS action is claimed.

The firmware producers/parsers/telemetry formats/writers are unchanged. Actual source age qualification for DHW temperature/comfort/time, any future writer contract, installed hardware/boiler compatibility and physical controls remain independent product gates. Normal canonical review/image/build/size/browser/device acceptance remains required; previous parent build results are not a build of this new source. Parent owns the generic size correction; no duplicate optimization or partition widening here.

Reverse only the new DHW source commit/core patch after later dependents; preserve the separate parent Recorder test sync, previous source/canonical docs and all runtime data. Stage28 concurrent-inhibit review correction is a separate subsequent packet; this HA-only DHW patch does not depend on seasonal policy acceptance. No runtime/publish/flash/HA deployment or heating action.

### Independent canonical input-bound correction

Parent review reproduced an OverflowError for valid JSON integers of 401 digits in selected/current temperature and flow. Bound checks now precede float finiteness conversion; six positive/negative oversized-integer cases use the actual tracker MQTT callback and verify unknown readings, no write grant and recovery on the next valid packet. All six fail against the original implementation and pass with the fix. Corrected canonical targeted HA:99PASS; full discovery734PASS+68subtests,1optional brokerSKIP, no deselections. The original Stage30 source manifest is preserved as delivery evidence, not an unchanged acceptance claim. No device/runtime or browser qualification follows from these native tests.
