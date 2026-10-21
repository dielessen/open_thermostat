# Reviewed graph DATA to SOURCE controller: bounded storage prerequisite

## Current follow-up: Stage48

The initial reviewed one-room native HA caller is now independently source-tested
and accepted; see [GRAPH-NATIVE-CALLER](GRAPH-NATIVE-CALLER.md) and WORKBOARD Stage48.
The normal entry/Store/one-worker path stages a separately pinned SOURCE projection
and requires fresh exact actual C++ readback. This does not qualify a real factory,
producer, device, general editing lifecycle or multiroom graph execution.
The Stage47 observations and estimates below are historical prerequisites, not a
claim that the initial caller is still absent. Current next software gaps are
reviewed config/pin revision evolution and older control-journal reconciliation,
GUI quality and actual supported producer/factory integration. No release date
or physical/heating permission follows.

## What is implemented

The actual storage incompatibility is addressed without another durable key,
writer, transport worker, scheduler or controller implementation. The existing
GraphShadowJournal/GraphShadowClient now provide an explicit, read-only
async_reviewed_handoff_data(exact_review) operation. It requires the existing
fresh session/capability, known immutable accepted tuple, native Store equality,
and exact current review key. Staged data, ACK alone, unknown readback, changed
review, Store drift, disconnect and expiry during an await fail closed. No
Store write, profile selection, API1 journal adoption or authority is created.

GraphControlStoreView reads the same existing ControlStore once per load, uses
the authoritative GraphShadowConfiguration/shared validator to restore DATA
without admission, and compares separate reviewed SOURCE pins for controller,
owner, qualification, graph config/mapping digests/revisions and named policy.
It checks exact SOURCE room/sensor/actuator bindings and target limits, projects
the bounded room config into the existing API1 schema, and compares its exact
independently reviewed SOURCE digest. It never rewrites the graph record.
All save attempts fail with a sticky fault; reentrant hash/read/write faults
cannot return success or clear the latch.

ModernTransport has an optional explicit SOURCE handoff argument. It selects
this view for its EXISTING ShadowController INSTEAD OF the graph owner, on the
same existing connection. Concurrent graph/controller selection is refused.
Default factories, ordinary API1 behavior, graph DATA-only mode, broker/TX locks,
partitions, wire/config ceilings and model/resource gates are unchanged.
The real default MQTT factory still supplies NONE; no deployment was enabled.

The new SOURCE target bounds default to the old 500..3500 range. For the selected
projection, they must equal the accepted graph's bounds. Stored base/schedule
targets and meaningful temporary/comfort targets outside them are rejected
before sequence consumption. An off/auto command does not become blocked by an
ignored target. Existing seasonal stop, source age, DHW, owner and supervisor
gates are reused. Frost advice is NOT inferred from the floor graph.

## Important semantic and product boundaries

This is room-target STORAGE/CONTRACT adaptation, NOT complete graph control.
Central/weather-curve, group/mixer/pump/actuator settings are fully validated and
hash-pinned as DATA but are not newly executed by this projection. Existing
SOURCE policy controls the selected logical regulator; hydraulics remain
unqualified and every physical output flag remains false. The named profile
digest is a reviewed public logical identifier, not physical attestation.

HA still rejects graph-draft rooms in async_build_configuration. A production
caller for explicit same-owner phase change, reviewed SOURCE profile/config
selection, stop of DATA mode, API1 journal STAGING (not unreviewed adoption),
fresh projected-config readback and native room mapping remains OPEN. There is
no GUI action secretly selecting a physical profile, nor automatic mode switch
when graph_ready becomes true. GraphShadowClient.ready is still always false.

The HA/C++ probe follows normal native graph options/review/Store and an actual
C++ graph-owner commit/readback into a declared synthetic SOURCE constructor.
The probe has NO admitted control session. Separate strict C++ tests exercise
the actual controller handshake/readback/observation/stop/expiry/reconnect path
over the same read-only view. Do not combine these boundaries into a claim that
the entire HA production control handoff or an actual device has passed.

Only the existing bounded one-room/unmixed binary-floor DATA contract is
supported. Two-zone SOURCE tests elsewhere do not enlarge this graph contract.
No eight-zone persistence/heap/stack/NVS-GC/72-hour claim follows.

## Measured verification scope

The native HA fixture's durable graph is 3629 bytes, the projected API1 config
299 bytes, and the host view object 272 bytes. These are that fixture and host
ABI measurements, not maxima or Xtensa heap/stack/runtime evidence. The existing
4096-byte durable/config and 8192-byte wire ceilings are NOT enlarged.
Projection creates bounded temporary string/tree copies and a heap-owned
validator/SOURCE bundle; real callgraph/heap/NVS budgets remain open. There are
no eight large automatic stack model objects or per-sample persistent writes.

The finite graph-control verifier covers the new C++ handoff/target cases and
existing graph Store compatibility only; it does not repeat the old 61/85
seasonal acceptance suites. Native HA uses newly compiled real C++/cJSON peers,
actual HA Store/options, and explicitly synthetic IO/SOURCE/safety fixtures.
A test-harness outer JSON parser was corrected to carry escaped durable bytes;
the strict product graph parser and all its budgets were retained unchanged.
Frozen failed-before boundary evidence is retained.

The old E32/S3 image receipts identify source8b364f2, NOT this source candidate
or immutable published alpha.6. Current pinned SDK syntax checks are not full
image/resource proof. Parent owns the normal composed release/build review.

## Joint HA/E32 candidate dependencies and remaining effort

1. **Next software prerequisite**: the native graph-room/Source selection and
   staged journal/room-mapping lifecycle above, through the existing owner.
   Evidence: current async_build_configuration still rejects graph rooms, while
   graph DATA and selected SOURCE are intentionally mutually exclusive.
   Rough engineering range: 4–8 hours for a bounded one-room implementation and
   actual composed negative/interop tests after protocol/pin review.
2. **SOURCE producers/factory**: an actual reviewed report/safety provider and
   explicit local factory bundle are absent; DATA cannot manufacture them.
   Once a concrete supported producer contract is supplied, a bounded software
   binding/negative-test package is roughly 2–4 hours. Physical correctness and
   availability cannot be estimated/certified by this harness.
3. **Full graph execution / wider topology**: central/weather/group/mixer and
   multiroom control binding plus payload/resource qualification remain separate.
   The current one-room DATA validator and SOURCE contracts are concrete limits,
   not permission to auto-expand to eight zones. No reliable whole-plan duration
   is supported by current evidence.
4. **Release and quality gates**: new-source E32/S3 fullimages/resources, dirty SDK
   source/notice/offer and CA/S3FS provenance, production HA dependency resolution,
   actual phone/browser/config retention, heap/NVS-GC/soak and physical admission
   remain distinct OPEN/BLOCKED gates. Generic size has a separate owner and
   does not block E32 software progress. All fourteen model candidates remain
   rejected/insufficient; no model benefit or adoption.

These ranges are conditional software estimates, not a release date, overnight
completion promise, physical commissioning time or heating GO.

## Review and rollback

The Stage47 manifest binds patch, full source archive, before/after hashes,
exact commands/results and retained failures. It depends on Stage46 source8afd0d7f.
Parent is sole canonical WORKBOARD/PLAN writer; use the additive handoff note.

Before dependent changes, reverse only this bounded source commit/patch.
Keep the original graph record, journal/config/model/Recorder histories, parent
fixes, credentials and partition data. No publication, login, live HA/device,
broker, restart, flash, TX, EMS, Tado or actuator action is included.
