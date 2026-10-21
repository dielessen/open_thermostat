# Native GUI flow correctness — visual acceptance OPEN

This bounded increment uses the existing native HA flows and public
FlowHandler.add_suggested_values_to_schema. Validation errors retain submitted
room/central/group/mixer/actuator/time-block fields. Cleared optional selectors
are not repopulated with old suggestions. This changes display hints only:
validation, input limits, registry checks and explicit Save/Cancel stay intact.

## Proven data-loss repair
The week editor rebuilt a room for final validation without its comfort fields,
window contact or person binding. Saving the program silently dropped that
existing configuration. It now includes those selected fields in final native
validation. Missing/disabled references reject Save rather than dropping policy.
Cancel does not mutate the original subentry. Existing native HA Store flush/
restart tests remain in the scoped suite; no production data is migrated.

## Read-only refresh
The existing DATA status form has explicit Refresh status / Close status choices.
Refresh reads the same existing client state, never reapplies/publishes/saves/
reloads or creates a worker. Pending ACK vs fresh exact readback remains distinct.
DATA verification never grants controller/model/readiness/physical authority.
No second apply flow, scheduler, frontend framework or dependency.

## Evidence
Initial focused baseline:6FAIL/1PASS, preserved; final scoped suite147PASS including
10new native form/lifecycle cases and existing native graph options/Store/actual
finite C++peer tests. One old test assumed empty Submit closes status; now native
default is Refresh. Its assertion explicitly checks Refresh then Close and retains
the original one-write/exact-readback assertions. The first146PASS/1FAIL run is
preserved, not hidden or treated as product success.

The actual native HA2026.10.2/Python3.14.8 backend and existing freshly compiled
actual C++peer are used. MQTT/qualified SOURCE producer boundaries remain fixtures.
No new production C++ or E32 HTML changes, no new full firmware build needed for
these HA-only source edits. This is NOT a native frontend screenshot/visual/
performance/liveHA/E32/physical proof.

## Required host browser check (OPEN)
Sandbox has no Node, Chromium, HA frontend or callable browser capability. Use the
existing parent host Chromium and a disposable native HA frontend test instance,
not production HA/device/login and not a custom form renderer.
At desktop1280x800/mobile390x844 check real native:
room/central/group/mixer/time-block invalid submission retains fields and clear;
Save/Cancel/reload preserves policy/room data; normal DATA draft->review->explicit
apply->pending/ACK->exact readback->read-only Refresh->Close; conflict/offline/empty
states. Screenshots, pageerrors, requestmethod/count and viewportoverflow needed.
Public MQTT/test peer boundaries may remain intercepted and must be labelled.
Existing E32 source-preview runner can separately test unchanged E32 GUI; it does
not prove native HA frontend operation. No browser/securityflag/newframework
installation or repeated device sessions to manufacture PASS.

## Product limits / rollback
Default source profile selection remains NONE. Graph is bounded1room; graph DATA
alone never selects SOURCE. Stage48 initial immutable reviewed handoff remains
separate from reviewed config revision evolution and wider graph execution.
Actual supported producer/factory/qualification/resource/72h/physical gates OPEN;
all14 enabled F9 policies remain rejected. No wholePLAN/release completion claim.

Before dependents reverse only this source patch/commit. No journal/config/model/
Recorder/history deletion/migration, no runtime action. Preserve Stage48, parent
fixes/docs and license provenance. Parent is canonical writer. WholePLAN in_progress.
