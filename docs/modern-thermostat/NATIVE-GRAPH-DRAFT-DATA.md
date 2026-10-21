# Native saved graph → bounded api2 DATA — F2/F3 source increment

This closes the previously missing bounded native saved-draft path. It reuses the existing RoomBinding, native heating graph normalization/ownership, native UTC schedule compiler, graph validators, journal, source-selected client and SAME NativeShadowConnection worker. No second scheduler, registry service, transport, database, coordination process or physical writer.

## Real native entry path, default unchanged

The existing integration entry dispatcher now accepts an explicitly **source-owned** complete GraphSourceProfile bundle for the matching native entry unique ID. The private source selection defaults to **None**. It is not an entry option, form field, incoming manifest or capability checkbox. The existing default/api1/legacy behavior remains unchanged; graph activation without the source-selected bundle is still refused before IO. A source selection cannot capture another hub/entry, and changing settings to legacy cannot silently reinterpret a graph.

The source bundle contains the complete pinned qualification record AND exact stable native registry references for source/output/feedback. It does not synthesize any power-loss position, failure action, end-switch, bypass, protection, postrun or source evidence from HA values or draft settings. All those facts must already come from independently reviewed source evidence. Current tests deliberately use **synthetic-only** qualification records, never an actual installation qualification.

Product setup/unload uses the same native lifecycle and existing source-selected connection, not an external script. The explicitly selected runtime is **DATA-only**: no temperature/source listeners or expiry timers, no observation forwarding, no active room decisions, no climate setpoint execution. Its transport_ready remains false even after DATA readback. Wrong/default/duck-typed transports cannot attach. Default product selection remains None; nothing was enabled on a running instance.

## Prepare, review, apply and reconcile

1. Native options offers **Prepare saved heating graph DATA** only when an existing selected owner carries a complete source bundle. A forged request cannot supply raw JSON, qualification, profile, references or evidence. Existing native enable options can only choose DATA where a full source/entry pin already exists; no new qualification is granted by that boolean.
2. The SAME bounded worker loads actual native room/heating subentries, normalizes bindings and reuses ownership validation. Only one graph-only room, one unmixed binary-floor group/actuator and the existing bounded profile are supported. Unsupported legacy ownership, extra rooms/groups, other profiles, unknown room policy, physical knob/comfort extensions or missing source bundle fail closed.
3. Selected room temperature/output identities must exactly match the source bundle. Disabled/missing/different registry identities fail; rename preserves stable identity. Feedback comes only from the source-owned native binding. Only opaque stable identity hashes go on the entity-free wire, never native HA entity IDs/display names. Group labels remain native metadata, not silently added to the wire schema.
4. Calendar materialization uses the SAME helper/compiler as api1. Room/graph snapshots and native references are revalidated after awaits. A change during compilation, disconnect, old capability/session or disk ambiguity cannot stage old-owner DATA. Unknown policy cannot be silently dropped. Existing eight-transition/config/wire budgets remain enforced: a daily two-transition15-day export can be too large and is rejected, NOT truncated.
5. Existing shared graph validation checks the complete resulting config/mapping/envelope. The compiler reuses the exact existing qualification hash basis (sources/devices/installation); readiness flags remain separately strict-false. The compiler does not loosen the C++/Python qualification checks or reconstruct physical facts.
6. Preparation persists only the validated staged tuple through native Store, without publishing configuration. The separate Stage24 default-false exact review confirmation is still required for device DATA apply. It is bound under the existing Store lock to exact config/mapping/revision + controller/boot/epoch/session, followed by actual new readback. No optimistic accepted state, automatic apply, blind retry or settings reload on the review/apply action.
7. DATA readback does not enable sources/control/readiness/outputs: client.ready and runtime.transport_ready remain false; actual peer boiler/actuator flags remain false. Native default-false gates, source-profile and physical commissioning remain intact.

## Evidence and scope

Stage26 GRAPH-DRAFT-RESULT dossier:

- 215 actual native HA tests, including24 new draft/source/lifecycle cases and all relevant existing graph/default/room/schedule/comfort cases.
- Actual native saved subentries/registries/Store/OptionsFlow/same worker and actual finite C++ graph peer. One positive case enters the real integration setup/unload/native unload hooks; public MQTT and platform-forwarding are intercepted test IO boundaries, not a browser/device claim.
- Combined existing ha/tests + ha/tests_native discovery:692 passed +68 subtests,1 optional isolated-localhost-MQTT skip,2 exact known parent Recorder barrier cases deselected and their files unchanged. NOT the full canonical no-exclusion CI job.
- Actual valid tuple commit/readback, no-confirmation, missing/changed/disabled source/output/feedback, stable rename, extra room/unsupported profile, source/entry mismatch, no UI qualification, ambiguous readiness values, native finite UTC schedule readback, oversized schedule rejection, draft change/disconnect during await and cleanup. Synthetic source facts explicitly declared.

No C++ production source changed in this increment; previous SDK/ASan evidence is not rerun or counted as new checks. No full new firmware image/link, real MQTT/LAN/HA/browser/frontend/device, production profile selection/qualification or physical proof. Native default is still None; arbitrary multi-room/mixer/TRV source profiles and actual installation qualification are not inferred from this bounded DATA path. Stable contact/person context freshness from Stage23 and enabled-model home benefit remain separate open gates.

Full canonical native/HA/Chromium/temporary-broker/standard E32/ESP32/S3/image/package/next-version checks and real source/control/TX/EMS/actuator/thermal commissioning remain OPEN. Published alpha.6 is not overwritten or republished. No live settings/history/broker/credentials/source-profile/installation/restart/flash/EMS/Tado/heating action.

Rollback only the separate Stage26 core patch/commit, after later dependents. Preserve Stage23/24/25, corrected F5, replay, parent Recorder/CONTROL/docs and prior scoped archives. Parent alone merges canonical WORKBOARD/PLAN; an additive Stage26 delta is supplied outside the source tree.
