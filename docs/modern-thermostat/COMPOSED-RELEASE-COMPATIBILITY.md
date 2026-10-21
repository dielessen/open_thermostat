# Composed source candidate — release/rollback boundaries

This is source preparation, not a release, installed firmware, or commissioning result. Parent alone merges the canonical project/WORKBOARD. The composed specialist tree synchronizes only the independently accepted DHW range correction and actual-binary OTA CI gate from the available parent snapshot; its source manifest must identify this tree rather than assume equality to a newer canonical HEAD. Stage33 corrected shared model-resource restore is included; rejected Stage32 must not be applied separately. Stage34 adds offline replay holdouts only.

## Compatibility matrix

| Surface | Existing contract / candidate rule | Rollback and remaining acceptance |
|---|---|---|
| API1 / default transport | Preserve existing default and topics; API2 readiness is not implied by an integer version. | Revert only reviewed source; no production broker change. Native compatibility is not a live reconnect test. |
| API2 graph | Explicit source-qualified shadow graph, schema2 config/mapping, schema1 HA journal. Persist/stage and ACK do not establish verified apply; exact fresh session/readback tuple required. | Unknown/future schema, conflict, retained/stale/changed identity fail closed. Never downgrade or rewrite an unknown journal to fabricate compatibility. Restore does not restore control admission. |
| HA entry/options | Native ConfigEntry/Store lifecycle; preserve native entry data/options, registries and legacy API1. | Test native migrations on isolated fixtures. A source rollback across a future persisted schema is NOT promised: stop, preserve bytes and restore a compatible source/backup; never erase/reinterpret data. |
| Metrics / Recorder | Existing legacy delta history remains legacy; schema2 boot counters and native units/identities remain distinct. Missing/stale is not zero. | No production Recorder migration, identity relabel or backfill. Reverting source does not undo data written by a hypothetical deployment. Native SQLite fixtures only. |
| Warm/coast/curve models | Existing codec versions/bindings plus explicit bounded shared resource admission. All restores remain disabled/advisory; storage/decode callback faults latch. | Do not erase model bytes, change budgets or adopt restored learning. Unknown profile/model/schema or failed readback fails closed. Real 8-zone heap/callgraph/NVS-GC/endurance remain OPEN. |
| App/settings/filesystem | release.json retains historical alpha.6, settings_schema1/update_schema1/layout e32v2-dual-app-spiffs-v1; partitions and inert defaults unchanged. | No new alpha.6 asset publication or silent replacement. Previous published alpha.4 is historical app recovery evidence, not proof that all future HA/graph/model data can downgrade. App-only rollback must use a separately verified compatible image and postcheck; no erase/factory/SPIFFS/NVS reset. |
| Firmware build | Normal pinned PlatformIO/Arduino/library/toolchain, existing E32 flags and dual slots; actual .bin must fit BOTH app slots. | An object check, ELF-only size, older source image or modified compiler config is not a new composed full-build PASS. Existing generic overflow remains blocking until proven fixed with real bytes. |
| DHW/UI | Read-only qualified Classic/Plus capability presentation; unknown/unreliable visible; accepted huge-integer guard preserved. Source UI hash must match embedded-web metadata. | No inferred DHW writes, heating support, new profiles or physical browser PASS. |

## Existing commands (source-only, not publication)

Run in the exact reviewed clean source using official PlatformIO6.2.0 / IntelHex2.3.0 and its pinned packages:

```sh
python -m platformio run -e esp32dev -j 1
python -m platformio run -e e32v2 -j 1
python -m platformio run -e e32v2 -t buildfs
python scripts/verify_e32v2.py
python scripts/test_e32v2_verifier.py
python -m platformio run -e esp32s3 -j 1
```

Also execute the existing build.yml actual-binary slot check for each target. Preserve full command/log/exit/source/UI/ELF/map/bin/embedded-web/partition/dependency hashes. Before any future release packaging, choose and review distinct immutable release metadata; this preparation must not package changed source as the already published alpha.6. Existing package/image-verifier tooling remains authoritative after that separate version decision. Run native, browser-source, HA/native-peer and isolated temporary broker gates from the existing workflow on the *same* source; no disabled assertions or Recorder exclusions.

## Nonclaims and source rollback

No tag, publish, asset upload, installation, login, reboot, live HA/broker or physical action is part of these commands. Hardware heap/PSRAM/stack callgraph, 8-zone runtime, NVS GC/power loss/endurance, 72h operation, real device/mobile/browser/OTA rollback, TX/EMS/actuators/heating remain OPEN. Offline synthetic model replay is not measured thermal improvement. Revert only this bounded source-sync/documentation commit before deployment, after reviewing dependents; preserve parent WORKBOARD/PLAN, Recorder fixes, original evidence, settings, history and model data.

## This bounded preparation result

Normal full generic and E32 commands were actually attempted on clean composed commit fc928dffc472b8da94d782b7e1add3abe74635de, with unmodified compiler/partition configuration. Both cc1plus processes were killed during main.cpp compilation inside the 536870912-byte cgroup. The E32 attempt increased oom_kill from4 to5; no new linked ELF or firmware.bin exists. This is a concrete worker-resource block, not a compiler syntax PASS or proof of source failure. No repeat with special flags. The normal E32 buildfs target succeeded separately; its SPIFFS image is a local validation artifact only, not an installation artifact.

The existing targeted native HA group passed150 tests after parent synchronization. Four additional real ConfigEntry migration checks then passed with that group (154 total, zero skips/exclusions): versions1/2 remain compatible/idempotent; versions3/255 refuse downgrade without modifying version, nested data, synthetic credential fields, options, entry identity or creating runtime_data. Initial new-test fixture incorrectly expected runtime_data=None; actual HA leaves it absent until setup. The corrected assertion requires absence, all preservation assertions unchanged; initial failure evidence is retained. These are source tests, not a physical app/settings downgrade test. Build-attempt source fc928dff and the later test/doc-only child are distinguished in evidence; all build-relevant production/UI/configuration bytes remain equal.

The exact parent full-image results on older b3d521f/dabdfe2 remain historical evidence only. Generic actual raw-image overflow remains release-blocking; no compiler-size fix, partition widening or full composed release PASS is claimed here. Required next native host action: integrate the bounded new test/doc changes into current canonical source, then run existing ordinary generic/E32/S3, full native/browser/HA-peer and real-image gates there. Do not replay already accepted parent DHW/CI deltas as new changes. Parent owns canonical WORKBOARD integration.
