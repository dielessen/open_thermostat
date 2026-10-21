# Native graph GUI apply — single attempt and unverified device results

This is a bounded completion of the existing native options/subentry path, not a second graph implementation. Default/API1 and source qualification/profile selection are unchanged. No new service, listener, worker, persistent schema or device capability.

## Proven gap and correction

The actual native HA options flow, same worker and freshly built C++ GraphSessionOwner peer reproduced two config publications from simultaneous confirm clicks, both on one flow and on two independent review flows. The real firmware wrote once; that did not make the HA send count correct. Initial two failing cases and machine rows are retained as GRAPH-GUI-ONCE-RED.*.

Inside the existing GraphShadowJournal transaction, after all durable Store, generation, freshness, exact review and codec checks, reserve one bounded `(owner/boot/epoch/session + revision/config/mapping tuple, sequence)` immediately BEFORE send. Reject a repeated same tuple/session as graph_apply_pending; the ordinary options flow shows status rather than enqueueing another config publication. Reservation survives identical restage, grant rotation, uncertain send completion and cancellation. It is not saved as data or admission. A new owner/session plus fresh matching remote baseline/readback and new visible consent can recover an uncommitted send; reconnect/reload never sends automatically. A later accepted revision is a different bounded tuple. No unbounded retry cache.

## Native GUI/state path

1. Save native heating/zone subentries through the existing APIs. These are local desired DATA, not physical qualification.
2. With an already source-qualified native connection only, Options → prepare compiles those saved references/mapping/config with existing validators and Store, then presents the exact staged revision/digest for separate confirmation.
3. Confirm once → staged/awaiting readback. No optimistic applied state from send completion.
4. A strictly scoped actual firmware config_result can show acknowledged_unverified. The real core reports the NEW committed DATA tuple using the OLD request owner/grant: this diagnostic needs its own exact pending-sequence/owner/target/TTL correlation, not relaxation of ordinary session scope. Only the known commit result or bounded revision/mapping conflict is presented. Arbitrary payload/status/extra private fields are never echoed.
5. ACK never reconciles Store, changes accepted config, extends grant/lease, provides sources/metrics or changes output readiness. Old/retained/stale/malformed/nonmatching results cannot promote it. ACK correlation clears on session reset and cannot be replaced by a rejected duplicate send. Conflict is explicit and does not overwrite/adopt remote data or retry.
6. Only the existing new handshake + exact fresh config/mapping readback accepts DATA. Control/boiler/actuator readiness remains false even then.

## What is actually tested

Actual HA2026.10.2 **OptionsFlowManager.async_init/async_configure**, actual custom integration loader/platform, saved native ConfigSubentry, existing worker and native Store, and a real source-built C++ peer. MQTT IO alone is intercepted into finite stdin/stdout; no LAN/broker/device/HA production. The native form JSON/description placeholders and state rows are source GUI evidence, not a screenshot/actual HA frontend/phone result. The fixture loads the actual config-flow module with native loader.async_get_integration/async_get_platform; it does not start HTTP/auth/MQTT dependencies or replace the flowmanager. Initial fixture dependency-loader failure is retained, not a product failure.

The targeted final group has **96 PASS**,0skip/0exclusion:18 new cases and78 directly relevant existing graph review/native-draft/Store/native-connection cases. Initial2 RED demonstrate the bug. Eighteen final machine rows cover one/two-flow clicks; real native flowmanager prepare/consent/persist/exactreadback; actual ACK-only with duplicate/nonextended deadlines and redacted diagnostics;8 wrong/stale/retained/malformed results; actual C++ revision conflict;4 uncertainty/cancel/grant/restage reservations; dropped uncommitted send requiring new session AND new consent. Existing lostACK, reconnect, parallel edit, Store-await/disconnect, expiry, future/corrupt Store and source/default fallback gates remain in the same targeted group. Counts overlap prior package coverage; do not add as new entire-plan functionality.

No firmware bytes, partitions, compiler flags, alpha assets, model algorithms, source-profile defaults, output locks, parent DHW guard or Recorder barriers changed. No new full build claim or rerun of the already memory-blocked release build. Native source acceptance is not physical/API2 deployment: source-owned profile selection, full canonical checks, installed behavior, real HA frontend/phone, heap/8-zone/NVS/72h/physical gates remain OPEN.

## Verify / rollback

Run dossier `python3 verify-graph-gui-once.py` against exact candidate or OPENTHERMOSTAT_REVIEW_SOURCE; this builds the real finite C++ peer with existing pinned dependencies and runs only the relevant native HA group. `--no-compile` reuses that exact peer when C++ source has not changed. `--red` is meaningful only on the pre-correction source with the new two regression cases; do not relabel it as a current-source failure.

Rollback only this scoped graph-GUI source commit before deployment, reviewing dependents. No journal/schema/model/settings/Recorder/history reset. Parent alone merges canonical WORKBOARD; additive stage result supplied in the dossier, not a competing workboard.
