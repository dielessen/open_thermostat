# two-room-targets.v1 — actual SOURCE readback/controller prerequisite

This is the next concrete implementation after Stage42 review and Stage47-50
one-room handoff. The EXISTING native HA saved graph (radiator + unmixed binary
floor, separate room sensors and targets) can be checked by an explicit versioned
SOURCE bundle, projected by a read-only view into the EXISTING ShadowController,
then used by the SAME native entry/runtime/one MQTT worker/client. No new planner,
coordinator, worker, database, key, service, physical profile or scheduler.

## Exact scope and trust boundary
Source policy/profile/config pins and the version two-room-targets.v1 are
independent of the inert topology DATA. Both native Python and actual C++ enforce
the version, two distinct rooms/resources, exact plan/registry/source/config
revisions, independent policy digest, target bounds, bindings and existing report
evidence. Radiator localTRV and floor slow-binary policy are explicitly SOURCE
selected; they are not inferred physical capability from UI/entity state.

The existing one-room API2 graph validator/writer is UNCHANGED. Review-only DATA
does not become a validated graph candidate or select a profile. Runtime factories
still supply NONE. Explicit SOURCE2 is a separate narrower target/readback profile,
not a general two-room heating graph, group/mixer/central/weather execution or
eight-zone rollout. Full desired draft digest stays pinned, including declarations
not executed by the target-only projection. Unsupported features failclosed.

IMPORTANT: the finite test SOURCE factory PRELOADS the exact immutable topology
review into its existing ControlStore backing key. Current API2 graph writer and
GUI cannot yet produce/provision this new review record. This is a real software
prerequisite with actual native entry and actual C++control, NOT proof of a
production two-room apply/persistence/transport negotiation or actual NVS. Do not
work around that missing writer by enlarging the one-room parser or rewriting old
config. Default binding/advertisement remains absent.

## Actual user-chain behavior
Native entry requires typed explicit SOURCE2 and exact current native saved graph
and registry identities. Its existing control Store starts STAGED only; only a
fresh exact real C++snapshot reconciles it. No ha/config publication/adoption,
second owner or blind retry. The read-only view rejects writes and keeps a sticky
fault through failed read/provider/hash/decode, reentry and attempted save.
Nonempty hash callback reentry is checked after reader/hash and before returning
bytes to controller restoration. Corrected later bytes cannot heal that fault.

Native config/subentry updates immediately fence an existing SOURCE owner before
awaiting the existing reload. Registry changes fence it through the existing
listener. Reconnect cannot clear review-required. Boot/reload needs a new grant/
readback; old grant/observation/temporary target is not replayed. No extra listener.

A/B replay uses actual different base targets21/19C. A-only/B-only/together/idle,
off/DHW/safetyexpiry, unknown second-room sensor, registry/config/profile mismatch,
reload/reconnect/oldsample and typed-context negatives are checked. Existing
minimum-off120s is honored from the last denied/reset step, NOT boot0. Simulation
feeds121seconds of fresh heartbeat/safety/report events without reducing any
timing/comfort/plant threshold. Source facts are declared synthetic fixtures,
not real physical source/installation qualification. All physical flagsfalse.
No model/admission/learning rights are granted merely by DATA or resource PASS.

Per-room OFF is additionally verified through the existing owned wire command
with its normal Future/ACK contract; an ignored5C target does not override SOURCE
limits or delay stop. This is not a browser test. The native climate frontend is
still HEAT-only for this narrow no-comfort profile; GUI OFF/comfort/schedule
integration remains separate product work. The first OFF test omitted the
existing required Future; that fixture failure is retained, not a productfix claim.

## Resource evidence and limits
Actual fixture: review1394bytes, projected controller config466bytes, native mirror
record1229bytes. Existing config4096 and payload8192 ceilings remain unchanged.
Host view408bytes. Pinned Xtensa8.4/Arduino2.0.17 object: view292, SOURCE pin256,
policy1040, reader result456, existing controller4640bytes. Compiler individual
load frame1296bytes and ctor64bytes. These are actual layout/per-function facts,
NOT full callgraph/peak stack, dynamic cJSON/string/copy heap, NVS GC/quota/runtime
or8zone proof. Policy still uses the existing fixed8slots but rejects any hidden
strings in unused slots before copying. Used pins/count are exactly2, no8zone
admission. Default controllers/partitions/resource limits/locks stay intact.
Pinned real SDK SHA object and current main/ModernTransport syntax are separate
checks, NOT a normal full image/link or installed firmware.

## Honest failed-before evidence
Initial new mapping emitter inserted mapping_schema before mapping_revision,
so the real C++hash disagreed with canonical Python and correctly refused ready.
Only new serialization order fixed. Subsequent replay initially assumed immediate
floor-on / too-short wait; the real existing regulator starts minimum-off at its
last reset. Replay clock now respects that original120s contract, no profile
retune. Actual native draft update initially left old SOURCE ready until queued
reload; targeted1FAIL retained, immediate existing-listener fence fixed it.

## Remaining exact blockers and next path
1. Existing API2/data codec+writer+journal must negotiate a separate bounded
   two-room target-review DATA record and exact apply/readback, then explicit
   same-owner SOURCE phase selection. No automatic qualification/adoption. Existing
   one-room schema/old unknown config must remain failclosed, not auto-migrated.
2. Actual supported temperature/safety/readiness producers and SOURCE/factory/
   installation profile qualification are absent. Test policy truth is not proof.
3. Full heterogeneous group/valve/mixer/central execution, schedules/comfort within
   this narrow SOURCE2 profile, eight-zone/callgraph/heap/NVS-GC/72h gates OPEN.
4. Native HA/E32 desktop/mobile source-browser acceptance requires parent existing
   host Chromium + actual disposable HA frontend; this sandbox lacks Node/browser/
   frontend. No custom renderer/browserPASS/latency/physical acceptance claim.
5. Current-source full composed images/release/provenance/productionHA closure
   remain parent gates; all14F9models still rejected. Generic exclusive otherchild.

Conditional software estimate, not release promise: negotiated writer/journal/
owner transition roughly6-12engineeringh after exact DATA-record/provisioning
contract review; frontend polish2-4h IF existing native frontend is available.
No actual producer/physical-duration estimate without concrete supported contract.
WholePLAN in_progress, not done after admission/prerequisite.

## Reproduction / rollback
TWO-ROOM-CONTROLLER-RESULT.json binds frozen patch/archive/before-after/protected/
evidence hashes and exact commands. Run verify-two-room-controller.py and
--sanitize (peer/core/newview/cJSON fully instrumented; external dynamic OpenSSL
SHA provider uninstrumented; no GTest used). Fault probes and actual pinned target
object/main syntax have separate verifiers. Parent alone canonical writer.

Before dependents, reverse only this bounded source commit/patch. Never delete/
rewrite config/model/Recorder/journals or accepted Stage43 FINAL backend. Because
nothing is installed/provisioned, no runtime data migration is performed. Future
deployment of this distinct stored review would require an explicit rollback/data
migration contract; not silent legacy adoption/reset. No live HA/device/broker/
login/flash/install/publish/EMS/TX/Tado/actuator/heating action.
