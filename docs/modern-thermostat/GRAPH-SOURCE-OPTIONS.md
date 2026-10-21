# Normal native options -> reviewed SOURCE caller

Stage48 completed the initial native entry/controller caller, but normal options
only recognized graph DATA selection. A GUI enable request for an existing
explicit GraphControllerEntrySource was rejected, and pure config preflight
circularly required the entry already enabled. This increment fixes that real
user-chain gap using the EXISTING options/entry/Store/runtime/one MQTT worker.

No GUI field selects or qualifies SOURCE. The code-selected typed SOURCE bundle
must already exist, match owner/profile/controller policy, the accepted exact
native graph Store tuple, current draft/registry and projected config. Default
NONE, unknown/invalid/ambiguous DATA+SOURCE, different owner/pin/draft and native
entry changes across Store awaits reject enable. Disable does not depend on a
valid profile. Normal setup and fresh exact firmware readback independently
recheck everything; staged control journal or ACK/graph_ready cannot admit control.

## Small necessary internal replacement (Mark11944)
The graph compiler now separates pure DATA representation checking from the
existing active DATA caller. The pure compiler can check a disabled shadow entry
but cannot persist, publish, start listeners, create a transport or grant anything.
The existing async_compile_saved_graph active caller keeps an enable fence before
AND after its awaits. Only the SOURCE caller that independently verifies exact
native reviewed graph data uses the pure preflight. No authority/threshold/
capability/resource or schema limit is relaxed.

ShadowOptionsFlow uses native OptionsFlow. HA2026.10.2 explicitly documents
OptionsFlowWithReload as incompatible with integration update listeners. The
existing integration listener is now sole reload owner; the actual native manager
test observes exactly one intended reload. This is a supported lifecycle
correction, not a claim of a captured live duplicate restart.

## Actual acceptance
231 native HA cases PASS:10new plus the74 caller and147 affected GUI cases,
not231 additional cases to sum with those older reports. Actual native options
manager persists enable, then normal integration setup reaches the actual C++
controller on the original durable graph key with fresh readback and logical
demand. The same10new cases pass with fully ASan/UBSan/leak-instrumented actual
finite C++peer/cJSON. Unchanged C++peer is reused only after source/binary hash
checks. Dynamic OpenSSL SHA provider is external/uninstrumented, no GTest used.

MQTT delivery/clock/platform forwarding and SOURCE/safety/report producers are
declared test boundaries, not real producer, broker, HA frontend, hardware, NVS,
image or physical qualification. No original durable graph rewrite. All physical
outputs false. Default source selection remains NONE.

Historical failures retained: original normal-enable/DATA+SOURCE gap and
preflight circularity; initial test fixture mixed intended options-reload with
an old protocol-only no-reload assertion. The new scoped reload seam counts
intended native options reloads; the old protocol mock/assertion is untouched.
Another test assumed nonexistent automatic_reload=False metadata on OptionsFlow;
it now checks the actual native type and observed single reload. No tests/gates
weakened, no hidden failed runs or runtime intervention.

## Remaining joint candidate work / conditional effort
Initial immutable SOURCE config only. Reviewed graph/target/schedule revision
evolution and an older accepted control journal are still safely rejected pending
a bounded transition/migration contract; roughly4-8engineeringh AFTER pin/
ownership choice, not a release date. One-room graph remains; central/weather/
group/mixer DATA validated but not executed by room projection. Wider graph
execution requires a separate measured bounded contract, no8zone claim.
Actual supported safety/report producer, factory/default selection/qualification
are still absent. No estimate of that integration before an actual contract.
Native frontend desktop/mobile source screenshots require parent host browser/
disposable actual HA frontend (sandbox has none); no browser/performance PASS.
Current-source normal image/resource/callgraph/heap/NVS-GC/8zone/72h/physical and
license/source-offer/productionHA dependency closure OPEN. All14F9 proposals
rejected. Generic size exclusively separate child and does not block E32 work.

## Reproduce / rollback
GRAPH-SOURCE-OPTIONS-RESULT.json binds the exact patch/archive/source and evidence.
verify-graph-source-options.py defaults to10new tests; full exact231 command is in
graph-source-options-evidence/FINAL-COMMANDS.json.
verify-graph-source-options-san.py runs those10against the exact sanitizer peer.
OPENTHERMOSTAT_REVIEW_SOURCE can select independent exact source.
Before dependent activation reverse only this source commit/patch, preserve
Stage48/49 and original graph/control/config/model/Recorder/history. No dataerase/
migration or new dependency/service/scheduler/controller. No live HA/device/
broker/login/flash/install/tag/publish/EMS/Tado/TX/actuator/heating action.
Parent sole canonical writer, wholePLAN in_progress; not a release candidate GO.
