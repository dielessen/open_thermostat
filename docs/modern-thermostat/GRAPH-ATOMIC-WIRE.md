# API2 atomic graph tuple — source boundary, not an active profile

## Proven missing link

GraphShadowJournal previously sent only the inner config envelope. The firmware
core also required mapping bytes, supplied out-of-band by the finite interop
runner. That runner was not an actual MQTT transport proof.

Explicit transport identifier: `atomic_mapping_tuple.v1`. One canonical API2
envelope adds exactly one root `mapping` object. It adds no nesting level, no
separate prepare/commit writer and no HA entities/services/names/secrets.
The config digest binds the config, whose mapping_digest binds the complete
canonical opaque mapping. Wire bytes remain bounded to8192,512 nodes,depth8,
64-character strings using the SAME shared parser/semantic validators.

## Ownership and transaction

The encoder validates the entire inner config+mapping against the SAME
reviewed-owner context before publication. The decoder checks canonical shape
and mapping integrity ONLY; decoding does not establish authority, session,
grant, lease, source freshness, device readiness or physical qualification.
GraphShadowConfiguration.applyTuple then passes BOTH recovered immutable parts
through the existing whole-graph validator, SessionAdmission and one atomic
4096-byte maximum store/CAS/readback transaction. Malformed/changed mapping must
not consume config admission. Expired/disconnected/replayed packets cannot write.

GraphShadowJournal.async_apply_tuple requires the explicitly supplied exact
transport identifier. It uses the SAME native Store lock, immutable staged record,
post-await durable readback, context generation and fresh capability checks.
It encodes the staged mapping itself, not a caller-provided replacement.
It sends once and requires later exact readback: ACK is not acceptance.
The original inner-form source method remains compatible; neither method starts
or advertises a transport. Unsupported transport is rejected before sending.

## Actual evidence and limits

Focused tests pair real HA2026.10.2 Store files and the real C++ configuration core
through finite stdin/EOF. One wire carries mapping, commits once, and reconciles
to the staged tuple. Corrupt mapping, private/unknown fields, canonical/total
budget failures, wrong owner/anchor, disconnect/stale capability/disk drift,
expired lease, replay, ambiguous save and reboot-no-admission are covered.

Actual native requested-allocation probe uses real cJSON and C++ allocation
hooks, every reached cJSON allocation fault, exact bytes and leak/recovery checks.
It is NOT the ESP allocator/heap/fragmentation proof. For the identical3819-byte
shared fixture, encoder peak fell55481→29094 requested bytes after transferring
owned JSON subtrees and releasing the parse tree before total-budget reparse.
Encoder fault sites1740→1378; decoder unchanged415 and25251 requested peak.
No accepted fault, leaked run or untriggered site. Absolute figures are native64-bit.

Pinned real Xtensa/Arduino2.0.17 compile-to-object measures cJSON node40B,
graph candidate344B, decoded parts48B, GraphShadowConfiguration4472B.
Compiler stack figures are per-function estimates, NOT whole loop/callgraph,
8zone/model heap, NVS reservation, image/link or physical acceptance.

No active factory selection, new NVS key, profile/capability advertisement,
HA setup/listener/socket/worker, install, restart, config or heating action.
API1 default remains unchanged. Current shared layout is ONLY1room/1unmixedfloor/
1binary actuator/8transitions/7streams; it is not automatically a product profile.
A valid config under4096B alone does not promise the complete stored tuple fits;
the existing firmware4096B tuple check remains authoritative.

## Following owner/profile work

Actual API2 hello/open/heartbeat/grant/config/readback, pinned qualification
manifest, source-profile/factory selection and conservative real partition/
migration budget remain separate work. They must reuse the existing native
MQTT owner/queue and admission, explicitly negotiate this wire, never fall back
from selectedAPI2 toAPI1, never reinterpret/reset old API1 blobs, and never renew
source/actuator readiness from readback or cache. All physical gates stay open.

Rollback: reverse this stage's focused core patch before any later dependent
stage; there is no runtime/persistence-format change to undo.
