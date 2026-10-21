# Two-room SOURCE contract preparation (Stage42)

## Product boundary

The existing API2 DATA runtime still supports **one unmixed binary-floor room**, with its existing qualification, journal, session owner and Store. API1 is unchanged. This package deliberately chooses the requested **explicit SOURCE contract preparation** alternative: it does not advertise, activate, persist or apply a heterogeneous runtime graph. The existing native CI peer-build step now builds this finite reader alongside its existing peers; the existing full HA test collection includes its tests. Hosted CI was not run here. No production module imports the new preparation/reader. No GUI can select it or grant source qualification.

`graph_topology_review.native_topology_plan()` uses the existing native saved room/heating subentries, `validated_graph()` and real HA registry resolution/ownership checks. `prepare_saved_topology_review()` requires a SOURCE-owned `TopologyReviewContext` with an exact pre-reviewed plan digest and boot/session/epoch/config/registry/source revision tuple. This context is **not** a remote self-asserted grant. A future integration must bind/invalidate it through the real existing owner; these tooling functions do not subscribe to a registry or track sessions themselves.

The separate schema `source_topology_review` contains exactly two independent room projections: radiator/TRV-room-setpoint and floor/binary-valve. It pins the complete native desired draft digest (including all settings/central data) and bounded room targets, group water bounds and hashed stable native registry resources. Groups/actuators/resources cannot overlap; all four resources are unique, including cross input/output roles. Unsupported schedules, comfort features, pumps, mixing, weather, extra rooms/groups/actuators or unknown room features fail rather than disappear from a projection. This is a limited desired topology review, **not an implementation or qualification of the pinned hardware semantics**.

The C++ `GraphTopologyReview.h` reader uses the actual shared canonical cJSON parser and SHA provider. It verifies the same SOURCE tuple and plan digest and returns a fixed two-room accounting result. Exact serialized readback is tested by the finite runner. It never returns `GraphShadowCandidate`, never writes Store and has no demand/schedule/actuator execution interface. `applied`, `admission`, boiler and actuator output flags are false-only. The old apply validator rejects a review document. There is no new scheduler, publisher, worker, service, capability or NVS key.

## Actual measurements (not estimates of a qualified two-room runtime)

| Serialized object | Bytes |
|---|---:|
| Existing real one-room config / qualification | 2,941 / 1,478 |
| Existing one-room envelope / mapping / tuple | 3,284 / 524 / 3,487 |
| Existing one-room config with 8 transitions | 3,241 |
| Actual native saved two-room desired draft | 1,259 |
| Actual two-room control proposal / private registry bindings | 1,281 / 259 |
| Actual two-room plan / review envelope | 1,004 / 1,406 |
| Synthetic shared review fixture envelope | 1,404 |

Existing runtime bounds remain **1 room / 1 group / 1 actuator / 7 streams / 8 transitions, 4,096-byte config, 8,192-byte raw input, 512 parser nodes**. No counts, parser limits, partition or transport buffers were increased. The review has its own 4,096-byte cap, not a new runtime payload allowance. A repeated eight-room review is rejected at the byte gate; three rooms fail the layout gate. Small desired draft/review sizes do not account for future per-device/source/installation qualification and do not prove a two/eight-room config fits.

Pinned Xtensa 8.4 / Arduino2.0.17 actual new reader object: Room **224 B**, Review **452 B**, Result **456 B**, unchanged legacy GraphShadowCandidate **344 B**. Compiler per-function stack: `graph_review::read` **800 B**, wrapper **48 B**, shared parser **160 B**. These are **not additive whole-callgraph peak/loop-stack/heap/ESP/NVS measurements**. Host requested allocator measurements for unchanged one-room cases are 24,631 B and 26,973 B (8 transitions); not ESP heap/cJSON arena proof. The new reader's dynamic parser/string/set allocations and full future callgraph remain unqualified. No eight large controller/model stack objects are created by this package.

## Checks and limitations

- 39 exact shared Python/C++ cases; the same 39 actual reader/cJSON cases under ASan/UBSan with leak detection and no diagnostics.
- 52 native HA cases total, **including those same 39 shared fixture cases**, real registries/subentries and supported native ConfigEntries/Store lifecycle. No broker, network, live HA or board. Exact private entity IDs/unique IDs are absent from the review.
- 98 unchanged existing real C++ graph-validator fixture cases still match their original oracles.
- Missing/disabled/replaced source registry identity, altered draft, cross-entry output owner, cross-room sensor reuse, source/registry/config revision drift and new boot/session reject; no auto-adoption.
- Native ConfigEntries saves/restores the exact desired draft. The fresh offline fixture intentionally has no running registry producer: missing registry identities fail first; explicit fixture producer re-registration is required to reconstruct the same plan. Restored DATA never restores an owner/session/admission. This is not a claim of physical registry availability or actual broker reconnect execution.

Initial harness-only failures are recorded: eight-room fixture first expected a later layout rejection instead of the existing earlier byte rejection; cross-owner test initially used an unsupported switch in a climate-only binding; native HA restart bootstrap needed the normal device registry setup and explicit distinction between saved config and absent fixture registry producer. No existing production safety assertion/threshold/limit was weakened.

## Remaining implementation gates

A real heterogeneous API2 runtime still needs reviewed per-emitter source/device/installation qualification, a shared water/mixing/hydraulic policy, bounded schedule/stream/config codec and storage accounting, owner lifecycle integration, explicit GUI review/apply/readback and real firmware/HA protocol tests. Eight-zone allocation, heap, NVS save/GC/power-loss, actual runtime callgraph and physical room/valve/flow/temperature/72h acceptance remain OPEN. No protection, model benefit, thermal improvement or complete PLAN acceptance is claimed.

Rollback: remove only this seven-file SOURCE preparation package before dependent code is introduced; it has never touched runtime data. Preserve parent Recorder/DHW/restore fixes and canonical WORKBOARD/PLAN.
