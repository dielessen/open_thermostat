# Joint warm/coast/curve resource and checkpoint admission (source only)

This is NOT learning, provenance, graph-capability, heating or output admission.
Default unreviewed/schema0/zero-zone plans fail closed. Existing API1, main runtime,
partitions and production model call sites are unchanged (no active model caller
is introduced). Do not advertise model support just because this source gate passes.

## Explicit bounded owner

A single noncopyable ModelResourceGate owns an explicit schema1 reservation for
1..8 resource-zone slots and 0..8 warm/coast/curve slots of each kind, each count
no greater than the zone count, at least one model. Each curve object already
contains its full bounded multi-zone observation state; a shared group may be
conservatively over-reserved, never omitted. Unknown profile/kind/schema and
SIZE_MAX/count/budget overflow are rejected before IO/multiplication.

Two distinct profiles:
- bounded_memory_shadow_v1: source/native fixture with explicit RAM persistence;
  NOT an available E32 backend or an NVS allocation.
- e32_nvs_shadow_v1: reuse the EXISTING ControlPartitionBudget 20KiB/5x126-entry
  ledger, old+new configuration, network and GC reservations, PLUS one largest
  model replacement. No key/namespace/partition factory or creation exists here.
  Eight of all three models fail that ledger. Do NOT increase partitions to turn
  this into a pass. Actual fresh backend stats are required on EVERY attempted
  mutation and successful set/commit/readback is still required.

The gate must outlive stores, models must outlive their registration. Unique
(kind,slot) owners are enforced. Duplicate/nested transaction fails and disables
all registered model modes/admission. Store destruction first disables model mode/admission, without erasing bytes,
then unregisters; checkpoint high-water/quota survives for this owner. One owner/event-loop only:
this is not a thread-safe mutex or permission to add another worker.

## Source resource ledger

For explicitly reserved counts:
- resident = sizeof(gate) + sum(count x (sizeof(model) +128B store allowance
  +128B backend-resident allowance +2x codec-max durable cache +32B allocator
  allowance)). Memory-fixture profile ALSO charges 2x persisted payload +32B/key.
- scratch = two bounded codec/readback strings (2x max capacity +32B each),
  one largest snapshot, one fixed64B hash output and4096B external-provider
  workspace allowance.
- separate declared stack >=4096B, validated against actual pinned individual
  compiler frames. This is NOT a summed external callgraph/loop-stack proof.
- persisted payload quotas explicitly sum codec maxima426/554/412B; NVS entry
  overhead is checked separately by the existing conservative partition ledger.
  Eight triples require11136B payload alone (before NVS overhead/GC/old values).

User budgets must cover these source requirements and remain inside hard caps
resident128KiB/scratch16KiB/stack16KiB/payload64KiB (NVS <=20KiB). These are source
reservation ceilings, NOT measurements of available E32 memory or a proof that
a backend/callback respects its reviewed contract. All actual model objects and
stores remain caller-owned; gate holds only24small pointers/counters, no model
array and no8large stack objects.

The three existing stores REQUIRE an explicit shared gate and slot. Hash callback
is now fixed-output64hex, non-owning function pointer (no captured std::function
heap state). Existing codec bytes/schema/SHA integrity contract are unchanged.
Hashes consume a string_view, not an extra body copy. SHA is integrity, not
authentication. A qualified production backend/provider must independently
prove its own resident/transient workspace <=reserved allowances; gate cannot
sandbox arbitrary C++ virtual/callback implementations.

ControlStore's model-only loadBounded/saveBounded opt-in contract checks stored
length BEFORE allocation/copy; defaults fail without invoking old config load/save.
Thus the existing NVS config store cannot accidentally become a model key.
Store-owned strings reserve a known codec max, enforce size<=max and
capacity<=2x max; no input-sized allocation in the core. One transaction serializes
snapshot, hash, current durable precondition and exact readback. A storage/hash/
readback failure disables ALL registered model modes and latches owner fault;
no automatic retry/refund/old-data overwrite or model-data deletion.

## Checkpoint schedule and restore

Source owner uses boot-local monotonic time. Per-model minimum30min between
attempts, joint spacing explicitly60s..30min, fixed one-hour window quota1..24
attempts and explicit maximum bytes554..13296/hour. These are fixed windows,
not rolling-hour/wall-clock flash-wear evidence. Attempts reserve quota BEFORE
IO; ambiguous writes latch fault and never refund. Decreasing/wrapped time fails.
Hourly window and high-water do not survive a new boot owner; they are NOT
persisted into new NVS keys. Repeated boot/reset wear requires product testing.

Only completed-model or explicit user reset calls checkpoint; observe/sample
contains NO storage call. Unchanged bytes are idempotent, never write/consume
quota. Deferred budget leaves data pending, never pretends durable completion.
Actual saved precondition must still match before mutation.

Loading ANY model, including an empty key, disables mode/live admission and
validates actual reviewed profile/binding/schema. Valid restore never reenables
learning or old owner evidence. Future learning owner must separately qualify
source, profile, observations, freshness, safety and explicit user mode; this
resource gate does not confer any of them.

## Evidence and gates

Native tests exercise all three actual models/codecs and shared gate, real SHA,
max24codecs/8-zone memory fixture, exact quota/spacing boundaries, duplicate owner,
unknown/unreviewed profile/schema, budget overflow, clock reverse, corrupted/failed
save/readback/oversize, disabled restore. Existing model/group/mixer/real-wire
regressions retained. Sanitizer repeats new actual header cases; framework/provider
instrumentation boundaries are documented in the dossier.

Pinned Xtensa sizeof and compiler per-function .su are reproducible source
budgets, NOT complete callgraph/allocator/hash/backend peak heap, NVS-GC/contiguous
pages/8-zone runtime/image latency or hardware qualification. These gates remain
OPEN, as do production model binding, profile/graph advertisement, physical
source/floor/flow/safety/TX/EMS/actuator and comfort benefit. No deployment.

Rollback only the scoped source packet before deployment; preserve existing
model bytes, settings/configuration, parent Recorder/DHW fixes and canonical
WORKBOARD. Do not erase/rewrite model history to roll back this source gate.


## Stage33 correction: nonempty decode callback fault is sticky

Original Stage32 is rejected: init/save callback tests missed nonempty decode
hash reentry. Hashing could fault shared owner and then restore(candidate)
cleared model storageFault before load returnedtrue. All3stores now check gate
AFTER decode/hash BEFORE restore, after restore and before loaded_/true. Fault
cannot be erased or successful load reported; no extra IO or retry. Three new
nonempty warm/coast/curve regressions include other registered models/fault
status, exactly1backendread/0writes/2hashcalls, disabled mode and no second load.
Original independent parent CPP is preserved and rerun without edits. Budgets,
quotas, algorithms/schema/codec and current data unchanged; no runtime actions.
