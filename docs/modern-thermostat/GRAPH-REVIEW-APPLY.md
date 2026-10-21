# Native HA graph DATA review/apply — F2/F3 source increment

Extends the existing GraphShadowJournal, GraphShadowClient and NativeShadowConnection. No new worker, service process, coordinator, scheduler, database, profile activation or source/actuator qualification. Parent owns canonical WORKBOARD integration.

## Native flow and actual owner

When an **existing source-selected** NativeShadowConnection owns a live GraphShadowClient, the native integration options form offers settings, staged graph review and graph DATA status. It does not instantiate that profile or accept a qualification pin from the form. Default/api1/no connection cannot use this path.

Review shows only accepted/staged revisions, staged configuration digest and non-secret status. The actual full candidate already lives in the existing native Store, validated by existing shared bounded graph/schema/capability/mapping validators. This is not a JSON editor or generic graph translator.

The explicit confirmation defaults false. It is bound privately to the same connection and exact controller/boot/epoch/adapter/session plus candidate revision/config digest/mapping digest. Those private session fields and qualification pins are never form placeholders or diagnostics. A direct forged submit without first reviewing is rejected. Review tokens are ephemeral, not persisted or reconstructed after restart.

The confirmation calls the **same bounded native worker** used for stage/apply/messages. GraphShadowJournal copies the review token before waiting, then rechecks it **inside its existing Store transaction lock, after awaited durable readback and fresh capability/generation validation, immediately before publication**. Another flow's commit/new staged revision, source connection replacement, reconnect/new session, stale capability or disk drift cannot silently approve different DATA. Ordinary grant rotation can use the same reviewed candidate only with newly admitted fresh capability.

Native graph disconnect callback immediately invalidates only api2 DATA admission before enqueueing its normal owned cleanup: a disconnect cannot wait behind an in-flight Store await and allow stale send. Api1 callback behavior unchanged; same worker/listeners/timer/queue retained and removed on unload.

Apply reports pending/unverified until actual new C++ tuple commit + fresh session/config readback is reconciled by the existing owner. No options-entry creation/reload, no setting/profile changes and no optimistic accepted result. Lost ACK/send completion does not cause a blind resend: status remains unconfirmed/awaiting readback; reconnect reconciles only known immutable durable DATA. An IO error may have reached the peer, so UI must not claim no effect. Close/reopen native status to refresh.

## Boundaries

GraphShadowClient.ready remains false: graph_ready is **DATA readback only**, never running source/control/hydraulic readiness. All boiler/actuator flags remain false. Existing single-room/unmixed binary-floor synthetic profile/capability/qualification budgets are unchanged. No generic graph capability is inferred from this UI.

The default product owner still selects api1. Production api2 source selection, native arbitrary heating-draft to qualified tuple translation, real device resources/feedback/source admission, full graph control and hardware commissioning remain separately gated. This increment supplies a real executable native UI path **for an already source-selected owner/staged tuple**, not a claim that arbitrary product graph drafts can run. Physical dependencies do not prevent further source/release-quality work.

## Evidence

Stage24 GRAPH-REVIEW-RESULT dossier: actual HA2026.10.2 native OptionsFlow/Store, same NativeShadowConnection and freshly compiled actual C++ GraphSessionOwner process. Native MQTT public IO is intercepted at the finite test boundary; no real broker/LAN/device/browser actions.

Tests cover default/no connection, no confirmation, forged direct submission, exact private key fields, same-worker cleanup, two competing flows/revision change, stale review/capability, reconnect/new session, mutable caller token, disk drift, disconnect during awaited native Store load, lost actual commit ACK and uncertain publication with actual peer readback. No duplicate physical acceptance claim. No E32 source changed in this package, so prior SDK/controller sanitizer evidence is preserved rather than repeated.

Rollback only the separate Stage24 core patch/commit, after undoing later dependents; preserve Stage23 and parent docs/Recorder/F5/CONTROL corrections. No runtime rollback was needed or performed.
