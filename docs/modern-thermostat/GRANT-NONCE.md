# Grant nonce / jitter availability correction — source11785

GRANT-JITTER-PROBE.json captured the prior actual C++/native HA availability loss:
5s rotation becomes6s with coarse2s firmware ticks, but a safe minimum5s extrapolated
HA bound accumulates drift. Both prior formulas were unchanged before Stage13.
The historic reproduction asserts that OLD failure; run it on c16e714/earlier
source, not on this correction. No actual broker/device issue or metric cause claimed.

## Freshness proof, not relaxed receipt timeout

New FW hello includes optional session_capabilities:[session.grant_nonce.v1].
HA only then includes grant_request_nonce in a NEW heartbeat: sequence-prefixed,
bounded32-char ID, same bytes and ORIGINAL send timestamp on retry. At most8 local
proofs retained; eviction is safe fallback, not a refreshed proof.

FW validates whole heartbeat shape before admission; only NEW accepted sequence
can replace latest pending nonce. Exact duplicate, changed duplicate, rejected
owner/grant/sequence or nonce on another stream cannot set it. Existing scheduled
>=5s grant rotation consumes that pending nonce, echoes in fw/session; no immediate
extra rotation that could race commands. Next rotation without fresh nonce omits
the proof. Reconnect/config/session invalidation clear pending/issued values.

HA requires newer same-composite-scope grant and supported capability. A known,
not-yet-consumed nonce with original monotonic age0<=age<10s establishes that FW
issued this grant AFTER accepting the heartbeat. ORIGINAL send+10 is therefore a
safe issuance lower-bound deadline. Max with old safe minimum5s bound is still safe.
No receiver wall-clock comparison; initial grant still uses open nonce round trip.
Never receipt+10. Duplicate/reordered status cannot renew deadline; missing/unknown/
expired/evicted/malformed proof uses old bound. Reset clears map/capability.
This echo does not acknowledge/renew lease, source freshness, training or outputs.
Heartbeat lease remains original send+15 ONLY after existing accepted result.

Compatibility: old HA heartbeat has no extra fields and remains accepted. New HA
with old/absent/malformed capability retains exact old body and conservative bound
(including old availability limitation); no capability falsely upgraded from read-only
metrics capabilities. No API-major/config/profile/storage/writer expansion.

## Verification

34actual C++ (6new +28preserved controller/metrics/admission),63actual native HA
(23new+40preserved),25real finite C++/HA interop (4new+21preserved),5 dependency
deprecations/no skips. Two360s SYNTHETIC schedules: coarse2s and1/3/2/4/2s jitter.
Stable same session, ready each step, every HA bound<=actual firmware grant expiry,
no new physical samples/no metric frames/all physical flagsfalse. Lost-grant and
replayed status fail closed; capability-absent simulated old-peer stays old.
These are not real-time soak, broker delivery/latency or device checks.
Pinned actual current main.cpp typecheck PASS; same cached prior generated webassets
only at typecheck boundary, no new image/link/release/board claim.

Rollback: reverse grant-nonce-only-core.patch/revert source commit before deployment;
old fail-closed availability limitation returns. No runtime device/HA/broker/EMS/
Tado/config/credentials action. Parent sole canonical reviewer/merger.
