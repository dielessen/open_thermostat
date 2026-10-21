# Negotiated shadow comfort — F10 / R19–21 source increment

This extends the existing EffectiveTarget, ShadowController and native HA room/climate path. It is not a new scheduler, service process, presence tracker or physical protection capability. No default mode/source profile changes. All boiler, actuator and physical-output flags remain false.

## Opt-in and compatibility

Old room dictionaries and their schema1 config/commands remain byte-shape compatible. A room may explicitly enable bounded comfort in its native subentry form: away target, frost target, override minutes, optional window binary_sensor and optional HA person. The profile uses the room's validated min/max target limits. Existing rooms omit all new wire fields. Graph-only draft rooms cannot enable this api1 profile.

Firmware advertises `comfort.target.v1` in `control_capabilities`. HA refuses a configured comfort room on an older peer before any config write; no silent fallback to unbounded or legacy operation. The optional `comfort` zone object is included in the existing canonical digest, Store journal, NVS configuration commit/readback and owner invalidation path. Existing 4096-byte config/8192-byte envelope/8-zone budgets remain enforced; large schedule/profile combinations can be rejected, not truncated. This is an optional api1 extension, not an api2 heating capability.

## Priority and expiry

- Controller owner/admission, software stop and configured bounds cannot be bypassed. Explicit off suppresses normal room demand, not boiler/DHW safety functions.
- Explicitly selected frost requests only its bounded configured target, before window inhibition. It does not assert frost risk, independent protection, flow, wiring or physical readiness. Selecting a different mode replaces that choice.
- A known open zone window inhibits normal comfort targets. Unknown/stale/future/restored window context also inhibits; no inferred closed state.
- Temporary/boost wins over presence/away until its own monotonic deadline. Window inhibition does not pause that deadline. Presence changes do not end or renew an explicit local override. The firmware publishes `comfort_mode`, `override_remaining_ms`, `vacation_until_utc` and effective target source; HA never treats an ACK as target readback.
- Explicit away/vacation resumes after a temporary/boost override. Vacation requires bounded future trusted UTC (at most366 days); UTC loss/reversal inhibits that background policy, does not prolong a temporary override, and expired vacation cannot revive. A temporary command cannot lower the vacation UTC high-water mark.
- Known opted-in person `not_home` selects away; `home` permits the compiled week/base target. Other named zones, unknown/unavailable, stale/future/restored are unknown, never guessed absent. Unknown presence inhibits automatic demand, but not a valid explicit temporary/boost.
- Existing compiled UTC schedule owns DST/calendar membership; no HA scheduler added. Base is fallback only where no schedule is configured. Invalid/expired schedule stays unavailable.

Temporary defaults to the room's visible1..720 minutes. Boost defaults to the configured room maximum target and bounded duration (at most4h); explicit service target/duration can be lower. All modes and observations are owner/lease/grant/sequence-bound. Only exact-byte current-grant duplicate retries are acknowledged; they never restart an expiry, including an already-expired vacation ACK retry. New invalid commands do not consume a sequence.

Boot, reconnect, config generation or owner loss drops all commands/contexts. No override/mode restore, replay or NVS token state. Durable room policy/schedule config survives through the pre-existing store. This does not qualify a physical TRV/wall knob as a command source; those profiles remain gated.

## Native HA operation and logical context scope

Native climate target setting uses a bounded temporary override. Presets: follow schema (`none`), boost, away, frost, off. Native integration entity action `open_thermostat.set_comfort` additionally supports an optional duration in minutes, `auto` and explicit future vacation date/time with timezone (no ambiguous local DST time). It targets only existing native climate entities; an admitted feature/mapping is still required. No optimistic target or second control coordinator.

Optional contacts/person are **logical native HA context**, never physical safety/readiness evidence, nor qualified temperature reports. State age is captured from `last_changed` once per native state identity and then increases monotonically. Re-reading/re-reporting the same cache cannot refresh it; receiver conservatively adds grant transit time. The fixed120s context TTL is intentionally restrictive: a stable/contact source without new state changes becomes unknown and pauses the opted-in policy. This increment does NOT qualify availability/heartbeat freshness for a particular real contact/person integration. Do not enable these bindings as a production source qualification shortcut. A future model-specific reviewed context profile/heartbeat contract is required for long-lived unchanged contacts/presence; physical and real cadence checks remain open. No GPS/tracking entity is created.

A contact/person event reuses the original temperature observation and its original deadline. It cannot manufacture a new physical temperature sample. Only its own zone changes; unknown context cannot unblock source or actuator admission. At most two context cache records per room; existing native listeners/observation coalescing are reused. No new poller or timer.

## Verification and remaining gates

Evidence is in the sibling Stage23 COMFORT-CONNECTED-RESULT dossier. Native policy/controller tests, actual HA lifecycle/forms/entity service and a freshly compiled real C++ firmware peer cover simultaneous conflicts, monotonic expiry, exact duplicate/non-revival, native config readback, reconnect/reboot, source loss, unknown context, two-zone isolation, vacation clock loss and both Europe/Amsterdam DST transitions. These are finite test IO seams, not a LAN/broker/device/browser proof.

Pinned Xtensa/Arduino main type-check and ASan/UBSan are separately scoped. No full new image/link/release, source-selected production admission, actual phone/HA browser, hardware frost/contact/source cadence, actuator/boiler/heating or installation acceptance is claimed. R19–21 physical acceptance and full PLAN commissioning remain open. Canonical WORKBOARD is updated only by parent review.

Rollback is the separate Stage23 core patch/commit only. Keep prior room metrics correction/replay/CONTROL and parent docs/Recorder tests intact. No live DB/config/history changes or runtime rollback were performed.
