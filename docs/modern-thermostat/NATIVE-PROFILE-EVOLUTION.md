# Explicit native logical profile evolution

Extends the existing native HA options → Store → ONE worker → actual C++ ShadowController/ControlStore path. No second scheduler/transport, no compiled per-configuration SOURCE pin, no runtime installation or physical producer qualification. Factory1be9082 remains the immutable predecessor evidence.

## Separate version spaces and review

Normal local descriptor `native.source.local.v1` and ordinary config schema2 are unchanged. Explicit migration uses `["native.source.evolution.v1", previous_plain_descriptor, current_plain_descriptor]`; exactly ONE previous CURRENT profile, never recursive history. New mapping revision must be previous+1 and both complete profiles must validate for the identical entry/controller/adapter. Local authenticated E32 settings independently compare the exact previously selected CURRENT descriptor and enforce the final secret-merged2048B record limit. No new persistent key/partition/quota.

HA stores this selection in existing entry options, schema2 with exact previous schema1 selection. Existing native form adds an explicit replacement confirmation and displays both SHA identities/readback-only scope. Runtime must already be OFF; save selects the logical profile only, never sends config or restarts the E32. Any source/layout/registry/entry drift before confirm refuses. The existing independently authorized local settings/restart steps are still necessary in a real installation.

Firmware metadata schema4/kind `installation.shadow.v3` declares the exact `predecessor_profile_digest` and `control.plan.profile_evolution.v1`. New config remains schema2/control.plan.v1; old metadata/capability/mismatched SHA cannot satisfy the HA session. This is NOT a new physical permission.

## Actual journal/load/apply behavior

The [explicit local SOURCE-only runtime selection](NATIVE-LIVE-SOURCE.md) now removes the device-reboot requirement for an already running local native profile, without changing this lineage/journal contract. Initial/unsupported selection and general network changes do not silently hot-apply.

The SAME controller validates saved old schema2 using the exact independently reviewed predecessor, including mapping, supply/control/target bounds and schedule/comfort schema. It retains only revision and exact canonical bytes/digest for fresh readback. ZERO active zones/mapping readiness, no restored grants, observations, overrides or learning. Unknown/future/incompatible bytes fault without erase/retry/rewrite.

The SAME HA journal accepts only already-known exact accepted/staged records. A requested, typed, current boot/session/grant readback may reconcile an exact old staged record, but remains NOT ready. Unknown remote bytes remain conflict and cannot stage/overwrite. Only normal explicit prepare/review/apply persists complete current config at N+1, commits via existing Store/readback, and then establishes fresh exact readback before ready. ACK alone never promotes success. Owner/registry/selection rechecked AFTER final Store load before mirror stage/send; failed saves preserve pending/conflict semantics.

A subsequent explicitly reviewed change FLATTENS source metadata to the immediately preceding CURRENT profile, not a growing chain. Existing current accepted bytes must pass under that exact pin; older historical bytes cannot be revived. Reopening unchanged review is idempotent; ordinary target/supported schedule revisions do not change SOURCE. Legacy schema1 quarantine remains its separately reviewed historical contract; combining that legacy extension with this migration is explicitly unsupported, not silently weakened. Config-schema upgrades beyond supported1→2 remain refused.

## Proof and remaining gates

Actual HA2026.10.2 options/registry/Store/reload and freshly compiled finite C++controller/cJSON peer exercise profile and temperature-binding edits, exact readback, successive reviewed revisions, stop/UNKNOWN safety, stale proof/old capability, final-await owner/registry/selection loss, lostACK/doubleapply, rejected/ambiguous commit recovery, old journal, incompatible bytes and real cJSON allocation faults. SOURCE/safety/report/clock/MQTT/storage/boot are explicitly finite synthetic seams. No live HA/device, browser/screenshots/performance, actual NVS/heap/72h or physical protection claim. HA frontend remains absent in pinned test runtime; actual browser acceptance remains OPEN. Runtime safety producer stays UNKNOWN and every physical output flag false. More than2zones and more than8 total schedule transitions remain unsupported; full-week/horizon refresh and actual producers are separate product work. All14 F9 candidates remain rejected.

Settings2048/config4096/wire8192/JSON/queue/NVS quotas unchanged. Full target callgraph/peak heap/GC and composed normal final image/resource verification remain separate. SDK object/individual frame evidence is not fullimage or hardware capacity proof. No threshold/partition/flag changes or generic-size duplicate ownership.

Rollback: reverse only this source delta before dependent source use. Preserve existing journal/config/entry identities, local source selection, model/history/Recorder/DHW data. Older code explicitly refuses unknown evolution metadata; do not silently deploy/downgrade/erase to hide it. Parent alone updates canonical PLAN/WORKBOARD; whole PLAN remains in progress.
