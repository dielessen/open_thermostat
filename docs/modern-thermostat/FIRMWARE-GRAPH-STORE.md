# Graph-shadow firmware configuration transaction —11785 source increment

This is the actual C++ durable configuration/admission counterpart to native HA
GraphShadowJournal, NOT a new transport, wrapper, watcher or daemon.
GraphShadowConfiguration reuses the shared strict cJSON validator, ControlStore
atomic-key abstraction and SessionAdmission. It is NOT instantiated/selected by
active ModernTransport/api1. No capability advertisement, provisioning/GUI apply,
NVS factory/key or physical output path is added by this increment.

## Scope, owner and versions

A separately authenticated existing local handshake owner supplies controller/
boot/adapter/session/epoch, then a real issued grant and fresh admitted heartbeat.
The class does not authenticate MQTT clients. SessionAdmission selects major2
only for this explicitly constructed instance; default remains1 and rejects2,
unknown configured majors cannot begin. Identity/revision/binding/grant/lease/
sequence/changed-duplicate fences remain the same primitive, with local monotonic
rollback latched. Repeated local handshake cannot erase watermarks.

Only the bounded shared1room/1floor/1binary-actuator/8transition TEST profile is
supported here. Its six graph feature names describe validated DATA structure,
not an installed device, hydraulic qualification or active service capability.
Only heartbeat/config admission is implemented; observation/actuator/result
streams, complete profile execution and actual negotiated advertisement remain
OPEN. No generic GPIO/service/EMS proxy or new bus writer exists.

## One atomic tuple

Canonical config+mapping+digest+controller+adapter owner+format version fit one
4096-byte maximum tuple. Full shared validation and tuple budget precede admission/
write. Before mutation, old durable bytes must exactly match; save and readback
must succeed before in-memory revision is promoted. Ambiguous save, corruption,
external drift, wrong anchor/owner/controller/version/schema/hash or allocation/
provider failure closes admission; no blind retry or rollback over an ambiguous
commit. A failed write may have committed, so a fresh object reloads actual DATA
and still requires a new verified session/readback.

The fixed qualification anchor must come from the installation/source owner,
not a self-asserted incoming manifest. Tests explicitly use synthetic proof IDs.
Legacyapi1 blobs/unknown formats are refused untouched; no implicit migration,
erase or settings reset. Future NVS integration requires a separately budgeted
key plus explicit migration/rollback choice; do NOT pass a live legacy config key
to change its meaning. There is no such active key allocation in this package.

Restore reconstructs an envelope ONLY to revalidate durable DATA against the same
validator; the artificial restore identifiers are NEVER passed into admission.
Stored grants/leases/sessions do not exist. Commit invalidates admission before
reuse. All boiler/actuator output accessors are constantfalse. No retained config/
readback or model history proves source freshness, flow or physical readiness.

## Real interop and limits

The finite stdin/EOF test runner owns only memory and actual C++ core; no network,
server or persistent process. Actual HA2026.10.2 native Store stages the tuple
before one explicit send to this compiled core, then promotes only exact real
core readback. Lost/ambiguous ACK, both object/HA restart and disconnect are tested.
The test supplies synthetic capability/handshake metadata; this is NOT a live
MQTT/board or complete API2 handshake claim.

verify-graph-config.py:33 actual C++ cases (9new +11existing admission +13actual
api1 ShadowController). verify-graph-config-interop.py:34actual HA checks
(3new C++/HAcore interop +30native journal +1active-boundary). Counts overlap
earlier suite results. Real cJSON/OpenSSL used, no mock C++ headers.
GRAPH-CONFIG-RESOURCE.json records exact tuple/config/mapping byte lengths and
native64bit sizeof; NOT ESP peak heap/stack/NVS-GC proof. New finite runner is
compiled by existing CI, full generic/E32/normalnative matrix remains a later gate.

Open: active existing-MQTT/API2 owner/hello/open/observations/feedback/result/
snapshot/capabilities, profile-to-core execution, approved key/resource limits,
GUI desired/applied/conflict binding, real board/source/physical and powerloss
acceptance. No source-only callback result is a physical ACK. WholeF2/F3 staysopen.
Rollback reverse firmware-graph-only-core.patch/revert this source commit,
preserving parent's canonical WORKBOARD; no runtime state was written.
