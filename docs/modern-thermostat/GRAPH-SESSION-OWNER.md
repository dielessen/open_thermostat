# Explicit bounded graph session owner — source11785

## Scope, not an installation

This adds an explicitly selected SOURCE-STAGE API2 graph configuration owner.
It completes the config+mapping handshake/commit/readback SOFTWARE boundary,
not full graph source regulation, actuation, model ownership or product acceptance.
The bounded source profile is named `bounded_shadow_1r1f1b`: exactly the shared
one-room/unmixed-floor/binary validator layout, not an automatic8zone capability.
Qualification manifest SHA and controller identity are SOURCE-OWNED pins, not
privileges accepted from an incoming draft/hello. Synthetic fixture evidence IDs
are test inputs, never an actual installation/valve/flow/high-limit qualification.

Existing main/options/setup do NOT supply this profile. No settings/default,
NVS key, partition, actual broker/HA/device change, install/restart or heating action.
Full product graph GUI apply/source qualification/room execution remain open.

## Same transport/queue and no silent fallback

C++ ModernTransport optionally receives a pinned GraphSourceProfile constructor
argument. Null retains original API1 owner/default exactly. Explicit profile selects
/v2/, SAME WiFiClient/PubSubClient, buffer, broker authentication and reconnect loop;
invalid pin failsclosed, never falls back1. Only four relevant graph topics are
subscribed. NvsControlStore selects the existing graph preflight profile, same
4096B key. Old API1 blob is rejected/preserved by graph core, not migrated/reset.
No second connection/bridge/service/worker/watcher or extra credential route.

HA NativeShadowConnection likewise optionally receives a SOURCE-owned immutable
GraphSourceProfile. Null keeps /v1/ and existing ShadowClient; selected2 uses same
MQTT API, one subscription, one bounded64-item queue/worker, timer and native Store.
Explicit stage/apply is enqueued in that SAME worker, not a parallel writer.
Unsupported profile/default, queue full and teardown fail/cancel cleanly. Config/
schedule refresh does not autoapply a graph. No actual product selector added.
Native runtime graph-room GUI/control support still remains unsupported; tests use
an empty runtime at this source hook, not an admitted physical sensor graph.

## Actual protocol and conservative time

Canonical exact API2 hello announces controller/boot/epoch/challenge, bounded source
profile, exact atomic wire, pinned qualification digest and known tuple metadata.
Current challenge plus expected adapter identity and fresh client session/nonce
open one session. Consumed challenges, exact retries, old epochs/configs, unknown
versions/profiles, changed duplicates and owner mismatches cannot reset streams.

SAME SessionAdmission2 primitive binds heartbeat/config/snapshot. Only NEW accepted
whole-shape heartbeat renews lease and anchors next scheduled grant. Optional
API1 negotiated proof logic was extracted to session_grant.py and shared with
graph owner: bounded8 original-send records, exact retries cannot replace time,
one-shot echo, minimum5s rotation fallback and fresh causal send+10 lower bound;
NEVER receipt+10 renewal or production comparison with firmware clock. Empty/
malformed proof, duplicate status, wrong/replayed stream cannot extend authority.

Same whole-graph validator and atomic tuple store apply ONE actual wire carrying
opaque mapping. Result/ACK alone never accepts data: committed revision invalidates
transport and emits new epoch/hello; HA opens anew, heartbeats, checks fresh exact
capability, requests scoped snapshot and reconciles exact immutable staged tuple.
Readback request sequence/current session/grant, mapping/config digests, source
pin, actual Store readback, generation and lease gates all remain required.
Old/retained/unknown snapshots/caps cannot restore admission. Actual online LWT
status after hello is ignored as proof (and does not abort opening); nonretained
offline immediately invalidates. No config, reboot or readback restores a lease.

Graph DATA verification is distinct from source/control: graph_ready means only
fresh peer + known tuple readback; ready remains FALSE, so no source/actuator/
bench/device/climate admission follows. Observation forwarding is unsupported/
no-op and setpoint execution refuses graph_control_contract_unavailable. Physical
boiler/actuator flags remain constantfalse. This is not hidden fallback control.

## Status, privacy and request count

Existing diagnostics supports old journal dict OR explicit graph status. It emits
only source profile/wire name/status/revisions/readback and control=false flags,
not tokens, pinned manifest, entities, mapping/raw data or credential material.
Desired/staged/awaiting/readback/unsupported remain distinct; readback is not a
physical-ready message or source-model qualification.

A matched actualC++/HA six-minute SYNTHETIC2s-clock test caught repeated empty
readback despite unchanged DATA. Bounded same boot/epoch/session/config/mapping
readback key now avoids that; explicit apply or reconnect clears the key, fresh
capability/grant/lease checks remain independent. Before→after:
snapshot requests181→1, all HA requests363→183,
HA payload93030→50879B, FW frames876→516, payload369128→246126B.
Same fixture/scheduling; diagnostic runner expiry introspection adds no wire bytes.
This is source protocol traffic, NOT live E32 GUI speed or actual-time broker soak.

## Reproducible evidence and limits

53actual native C++ tests (6new protocol +47 prior core/tuple/API1/admission/grant/
metrics);6new protocol tests ASan+UBSan with actualcJSON instrumented (cached real
GTest framework uninstrumented). Real HA Store and real C++ finite wire cover
hello/open/heartbeat/capability/snapshot/config/new handshake/reconcile, ambiguous
committed save/reboot, lostACK, stale/owner/mapping/retained/replay/no legacy reset,
same native worker/unload/status redaction, defaultAPI1 lifecycle and grant tests.
Counts overlap; do not add them as independent product scenarios.

Focused final HA group99 checks; graph subset17 also passes with a fully ASan+UBSan
instrumented actual owner/core/finite runner/cJSON (NO GTest framework in runner).
Initial native PIE sanitizer bootstrap stalled intermittently BEFORE ASan Init
finished/main; failures are preserved. Concurrent stderr draining and bounded
cleanup exposed it. Native-runner-only EXEC/nonPIE link (sanitizers still fully
on) then20/20bootstraps+17/17actual scenariosPASS. No Xtensa/product flag changed.
Official native CI now also compiles this finite peer before collecting HA tests;
no hosted CI/release run is claimed by this source-only change.
Pinned current main.cpp real Xtensa/Arduino2.0.17 typecheck and actual connected/
tick/receive compile-to-object pass. Target owner4848B; stack figures only per-
function estimates, not full loop/callgraph/heap/fragmentation/NVS/8zone/model proof.
Typecheck uses previous actual generated webassets ONLY, no new image/link claim.

Run sequentially from dossier:
python3 compile-graph-owner-runner.py
python3 verify-graph-owner-final.py
python3 compile-graph-owner-sanitized-runner.py
python3 verify-graph-owner-sanitized-interop.py
Final runner emits finite JSON on EOF, not a background service.
Full cold/mild enabled start/coast/curve harness is a separate queued followup,
not relabelled complete here. Full8zone/persistent model profile/resource,
actual product GUI apply/source execution, migration/rollback/device/phone/72h/
fortnight/EMS/Tado/TX/physical gates remain OPEN. Whole PLAN continues.
Rollback reverse this stage core patch/revert before later dependent work.
No runtime data/profile was changed; actual future activation requires its own
proven migration/resource/physical checks, never automatic legacy overwrite.
