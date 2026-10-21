# Integrated source release preparation — not a release or commissioning result

Stage25 continues PLAN11785 using existing test/build/release tooling. The source candidate includes corrected room-metrics restore, connected F10 comfort and native api2 DATA review/apply. Parent owns canonical merge, official CI/build/publication and WORKBOARD integration; no production action was performed.

## What ran locally

One combined existing CI-style discovery over **ha/tests + ha/tests_native**: **668 passed,68 subtests passed,1 skipped,2 deselected** after correcting the now-stale architecture boundary. Actual HA2026.10.2 native lifecycle/Store/entity platform/registries/Recorder/statistics/CSV/model source, plus freshly compiled actual finite C++ graph validation/store/session/shadow/room observation peers where required; no fake alternative wire validator. Native test network is forbidden. The existing optional isolated-localhost-broker packet test skipped because no fixture was supplied, never pointed at a production broker.

The two exact deselections are existing parent-owned Recorder test-barrier races in test_metric_definition_v2.py and test_metrics_presentation.py. Their source bytes/SQL/assertions remain unchanged here. Parent canonical already owns its FIFO SynchronizeTask test-only fix; **this report is not a claim the full canonical HA job passed**. That job must run all tests, without these local exclusions, after parent integration.

The integrated run found one obsolete source-boundary assertion: native options originally could not import graph validation at all. The approved native source-selected review path now imports only its error type. Updated boundary explicitly forbids root-level graph activation, source-profile/client/connection/journal creation, direct graph validation or direct journal apply in GUI; UI may dispatch only apply through the existing worker. Actual native UI tests additionally prove no default/profile/qualification activation and no options reload. No validator semantics changed; its stale module docstring was corrected. Final strengthened boundary also passed separately.

Earlier current-source scoped evidence remains independently scoped: Stage23 C++51 + same51ASan/UBSan + actual HA51 + pinned E32 main syntax; Stage24 actual native HA107 with19new review/fault cases and freshly built graph peer. Do not add repeated tests as extra unique scenarios or claim a browser/device result.

## Existing official gates, still required

The existing .github/workflows/build.yml already discovers all native C++ test files, all shipped JS test files, actual Chromium source-page scenarios and all native HA tests, builds the required finite peers, pins PlatformIO/Arduino/HA, and runs the real image/layout/fault/package checks. No new CI framework, dependencies, scheduler, wrappers or release service is introduced.

On the canonical reviewed source, use those existing native gates:

- PlatformIO native tests and existing onboarding ASan/UBSan scenario runner.
- Existing Node tests and actual Chromium source-page tests (simulated HTTP; still not physical browser acceptance).
- All actual native HA tests with canonical parent Recorder test barriers and isolated temporary MQTT fixture; no local deselection substitute.
- Standard pinned E32/genericESP32/S3 image builds. Current local worker has512MiB memory; previous standard E32 compile attempts hit that limit. No new full candidate image/link is claimed from a main syntax check, and no old alpha.6 image was substituted. Parent host/official CI must provide the normal image proof.
- E32 filesystem build plus scripts/verify_e32v2.py and scripts/test_e32v2_verifier.py against **the new real build outputs**, then existing scripts/package_e32v2_release.py / scripts/verify_e32v2_release.py / actual native image checker. No fabricated image or old source package counts as new-source proof.

The current release.json remains immutable published alpha.6 metadata, not a publication of this changed source. No version/tag/remote push/release, image upload/installation or live update was performed. A future release requires distinct reviewed immutable version/tag and all canonical gates; existing tag-triggered publication is not executed as part of this source preparation.

## Product boundaries that software PASS does not close

- Explicit comfort/source context last_changed120s TTL is conservative; stable unchanged contacts/person become unknown. A reviewed model-specific freshness/heartbeat profile and real cadence/availability tests remain required; no arbitrary home/away inference.
- API2 graph_ready is DATA readback only; source-selected bounded profile does not qualify arbitrary native graph drafts, control/sources, readiness, hydraulics, memory/NVS endurance or hardware outputs. Default/api1 unchanged. Native arbitrary-draft translation and production profile selection require independent source work/review, not a checkbox granting qualification.
- Enabled model toy replay rejected every evaluated policy under declared acceptance; advisory code is not proven home/model benefit.
- Real HA/mobile/frontend/device/reboot/settings/OTA rollback under the next actual release, real thermal/emitter/valve/pump/limits/TX/EMS/boiler installation and commissioning remain OPEN. Historical cable status is not current-device evidence. No heating GO or Tado action.

Stage25 rollback is its tiny test/doc-only patch; it changes no runtime policy, existing Recorder data or settings. Keep separate Stage23/24 core patches, scoped frozen source archives and source-specific rollback. Whole PLAN11785 is not declared complete or physically released.
