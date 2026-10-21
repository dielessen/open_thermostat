# Explicit old-journal quarantine for the native shadow plan

Scope: source only. No install, runtime profile selection, physical protection or actuation qualification. Parent independently reviews the frozen package. Existing API1 pinned-source/API2 DATA contracts are unchanged by default.

## Independent version contract

The normal two-room source stays `installation.shadow.v1` / metadata schema 2 and rejects old configurations. A separately reviewed typed installation source may opt into `legacyReadbackReviewed`; its canonical HA SOURCE document is schema 2 / `native_profile.shadow.v2`, with `legacy_readback: schema1_quarantine_only`. Its independently hashed identity must match firmware metadata schema 3 / `installation.shadow.v2` and the extra `control.plan.legacy_readback.v1` capability. These are different version spaces from durable config schema 2. None of DATA readiness, form choices, remotely supplied configuration or cached sensor state creates this source selection.

## Upgrade chain and invariants

1. Existing controller loads known, bounded schema 1 bytes using its original decoder into one temporary heap object. Only its revision and canonical bytes/digest are retained for readback. There are ZERO active zones and no mapping readiness, restored grant, override or learning.
2. HA loads the existing accepted/staged control journal through the same Store. Only a current own-request, correctly scoped exact snapshot of an already known record proves read-only quarantine. Unknown remote data is a conflict: never adopt or overwrite it.
3. Existing normal HA options prepare/review/apply explicitly builds a complete two-room schema 2 plan at revision N+1, under the SAME independent source profile. No per-config compiled pin or controller/factory swap. Cancel sends nothing. Actual commit goes through the existing ControlStore and original exact new readback barrier. ACK alone is not apply evidence.
4. Failed save preserves old bytes and pending journal; ambiguous commit retains pending and requires exact current readback after restart. A new session never restores an old grant. Owner/source/entry loss at final Store await refuses before staging or send.

## Deliberate bounds

Legacy readback supports 1–2 known current room IDs, no legacy comfort object, compatible evidence/age/target bounds, and at most 8 UTC transitions TOTAL. Old aliases are never activated. Unknown rooms, schemas, oversized records, incompatible ages or profiles are refused without writes. No general eight-room migration, DATA-journal import, unlimited week schedule or physical compatibility is claimed. Existing 4096-byte config, 8192-byte wire, node/queue/NVS quotas are unchanged. Operator must retain unsupported old records for explicit review, not erase them to force acceptance.

## Evidence and limitations

Actual HA 2026.10.2 Store/options lifecycle and freshly compiled finite real C++controller/cJSON peer, including same-case ASan/UBSan, exercise save/ambiguous/lost-ACK/reconnect/owner-await/proof/profile negatives. Finite synthetic source/safety/report/clock/MQTT seams are not actual producer, device, broker or physical evidence. Full source-only record in LEGACY-PLAN-RECONCILIATION-RESULT.json beside the review artifacts.

Pinned Xtensa/Arduino 2.0.17 object and current main type-check pass; source=632 B, controller=4648 B, largest individual measured frame=2192 B. An extra temporary Configuration heap object is used only at quarantine load. Summed callgraph, peak dynamic heap, NVS-GC, actual queue high-water, eight-zone and duration/device proof remain OPEN. Recorded compiler-GC/g0 test/object settings are not a normal full image proof.

The real default MQTT factory still does not select this installation source and HA registered sources remain NONE. Production source/producer binding is the next genuine integration gap. Finite Z2M bench/cached values are not promoted to continuous physical freshness. All F9 candidates remain rejected; source/UI review is not model-benefit/release acceptance. Parenthost desktop/mobile actual frontend proof and composed final image/license gates remain separate.

## Rollback

Reverse only this bounded source delta before dependent activation. Preserve old and new native config/journals, identities, previous profiles, model/Recorder/history and immutable prior packages. Do not erase data, silently downgrade schema 2 to schema 1, or describe code rollback as data migration. An old firmware/profile unable to understand schema 2 must refuse it; recovery requires retained compatible source/firmware and explicit review.
