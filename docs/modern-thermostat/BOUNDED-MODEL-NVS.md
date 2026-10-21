# Bounded SOURCE-only NVS model backend/provider (Stage43)

## Scope and construction contract

`NvsModelStore.h` adds an **explicitly SOURCE-constructed** backend for the existing `ThermalModelStore`, `CoastModelStore`, `CurveModelStore`, `ControlStore` and corrected `ModelResourceGate`. It is not imported or selected by main/ModernTransport/default factories, GUI/options, telemetry or capabilities. No model caller, advertisement, worker, service or automatic model/config migration is added. Default learning/admission and all physical output locks remain unchanged.

One `NvsModelProvider` owns the existing shared resource gate and a fixed reservation table. Only the existing `e32_nvs_shadow_v1` plan with valid schema/counts/resident/scratch/stack/persistent/checkpoint quotas can construct a healthy provider. The source caller must use its `gate()` and matching zone/kind when constructing the existing modelstore, in the **same serialized source-owner execution context**. The provider must outlive the backends AND modelstores; the model must outlive its modelstore. This source-only lifetime/serialization contract is not a new cross-task lock or thread-safety guarantee.

The namespace is fixed `ot_models_v1`; keys are fixed `warm_0..7`, `coast_0..7`, `curve_0..7`, and only declared reservation slots can be claimed. No caller-provided namespace/key and no access to `ot_control/config`. Construction performs no NVS IO and creates no keys. A duplicate active provider faults both providers; a duplicate key faults the shared gate. Key claims and original checkpoint quota are not refunded during provider lifetime. Provider shutdown disables registered models; stores must already have detached according to the lifetime contract. None of this grants control/learning/admission.

The original conservative ledger reserves config/network namespaces. This extra model namespace is charged **one additional entry within the same total**, not by enlarging partition/quota/GC. Constructor admission requires room for that entry; every write also uses a stricter free-entry check. Eight triples still fail before IO, even with otherwise generous original resource declarations. No erase, nvs_flash_init, partition creation/resizing, manual GC or migration/reset API is used.

## Bounded IO and checkpoint semantics

- Unbounded `load/save` deliberately fail and latch the shared gate. Bounded maximum must equal that key's existing codec limit, not a caller-selected larger buffer. Oversized preallocated output capacity is rejected.
- Every bounded read/readback requires fresh valid partition/stat evidence before open (without requiring write-free-entry quota). Read-only open never creates a missing namespace/key. Empty success means never configured. Existing blob length is queried before resize/copy. Zero/oversized/failed length rejects before data-copy; a changed length or SDK read failure rejects without retry.
- Existing modelstore validates hash, codec, binding, snapshot and shared gate, with corrected post-decode/pre-restore latch checks unchanged. Nonempty restore never reinstates mode or source admission.
- Existing modelstore performs its pre-write exact old-data comparison and reserves the original checkpoint attempt **before mutation**. `modelPartitionStats()` supplies a fresh public NVS snapshot, not a cached plan.
- Backend rechecks fresh partition size/stats before `nvs_open(READWRITE)` (which may create a namespace), and again immediately before `nvs_set_blob`. Namespace/other key usage is then already in used entries. Insufficient/malformed/missing stats latch failure; no new blob is set.
- Exactly one set and one commit; failed/ambiguous commit is NOT retried or erased, even if bytes may have become durable. Gate health is rechecked after SDK boundaries before proceeding to copy/commit.
- The existing modelstore performs its **one existing exact bounded readback** after successful backend commit. Backend adds no redundant readback, checkpoint clock or retry loop. Direct low-level backend writes are not a product API or substitute for the existing store/gate checkpoint path.
- Every backend/resource/hash/readback fault leaves the shared modelstores unhealthy and modes disabled. Later checkpoint/load/save attempts do no further backend IO in the same failed owner. A fresh owner may inspect existing valid bytes only through normal disabled restore; no data is erased.

## SHA implementation and provenance

`modelSha256` uses the existing SDK `mbedtls_sha256_ret`, with a caller-owned 64-char hex output and a 32-byte local binary digest, no heap digest string. SDK header version is **2.28.7**. Actual native tests compile authentic upstream **2.28.7 SHA256 and platform zeroization source**, checked against known empty/abc SHA vectors; SHA is not mocked. Upstream archive SHA256 `1df6073f0cf6a4e1953890bf5e0de2a8c7e6be50d6d6c69fa9fefcb1d14e981a`, provenance/license archive supplied in dossier. This is an offline test dependency only: no production dependency/core/library patch or flag change.

Actual target object compiles against the pinned Arduino2.0.17/ESP-IDF NVS, partition and mbedTLS headers (no SDK fake include there). Native software SHA and target ESP hardware SHA port are explicitly different execution boundaries: hardware SHA execution/internal workspace/locking/callgraph are **not** proved by a native hash vector or target object compile.

## Measured source accounting, not available-device resource proof

| Pinned Xtensa accounting object/budget | Bytes / entries |
|---|---:|
| Provider including existing shared gate | 736 B |
| Existing shared gate | 696 B |
| One backend | 16 B |
| Provider extra + one backend | 56 B, within original 128 B per-slot allowance |
| One warm+coast+curve original resident accounting | 6,616 B |
| Original scratch reservation incl 4,096 B external-provider allowance | 6,924 B |
| Original minimum stack reservation | 4,096 B |
| Maximum durable codec payload total | 1,392 B = 426 + 554 + 412 |
| Conservative ledger including extra model namespace | 558 / 630 entries |

Fixture plans use the original computed requirements, not increased maxima. Compiler per-function frames: backend load64 B, save64 B, stats80 B, permit64 B, fixed-output SHA wrapper96 B and provider placement-construction wrapper176 B. These do **not** sum to a proved callgraph peak. Existing model/codec algorithms, store scratch/accounting, checkpoint floor30min, partition20KiB, config4096, network2048 and GC-page reserve126 entries are unchanged. Current SDK NVS internals, allocator/fragmentation, actual available heap/loop stack, concurrent config writes, GC, wear, power loss and eight-zone operation remain OPEN. The ledger and fresh stats are necessary conservative gates, not proof of contiguous page allocation or successful hardware commit.

## Focused verification

- **20 strict GCC12 C++ cases PASS (15 original +5 missing IO/decode acceptance)**, same20 with actual GTest/framework/test TU/backend header AND actual upstream SHA/zeroization compiled under ASan/UBSan/leak detection, no sanitizer diagnostics. Native-only nonPIE sanitizer flags, no firmware flags changed.
- Actual three existing modelstores reach all maximum valid codecs426/554/412 B, save/commit/exact readback and disabled restore. An unchanged snapshot causes no extra writes. Duplicate claim faults all three models; the untouched config namespace sentinel survives.
- Missing namespace; unreviewed/wrong profile/eight triples; duplicate provider/key; unknown kind/unreserved slot/unbounded API; zero/oversized/SIZE_MAX length and caller-buffer bound; SDK open/length/read/changed length; SHA failure/corruption; set/commit/ambiguous durable commit; exact readback corruption; missing/wrong/exhausted/inconsistent/changing partition stats; extra namespace free-entry boundary; clock/quota deferral; SDK-boundary reentry fault; exact no-retry/no-extra-IO assertions.
- NVS/partition API calls are a clearly isolated SDK IO fault fixture around the **actual production backend header**, not a substituted store. These tests do not execute a flash device, NVS GC or a real reset. Actual SHA/model/store code executes.
- Tests live in `test/model_nvs`, like the separate onboarding harness, so default `test_filter=test_native` remains unchanged. The dedicated verifier selects only `NvsModelBackend.*`; original resource tests reused as source fixtures are NOT re-executed or relabelled new. No hosted CI/full composed image/HA/broker/device run is claimed here.

Initial strict test-build formatting warnings were fixed with explicit braces/newlines, not suppressed. The initial SIZE_MAX fault case mistakenly used the fixture's no-override sentinel; separate override state fixed the fixture. Intermediate passing results preceded final stricter namespace charging; final native/sanitizer/target hashes identify the exact final source. Initial failures/logs remain in dossier.

## Reproduction and rollback

Dossier commands: `python3 verify-model-nvs.py`, `python3 verify-model-nvs.py --sanitize`, `python3 verify-model-nvs-target.py`; fresh isolated output folders by default, `OPENTHERMOSTAT_REVIEW_SOURCE` selects a checkout and `OPENTHERMOSTAT_MODEL_NVS_OUTPUT` overrides output. Exact SHA archive/headers, GTest/sysroot references, commands and hashes are supplied. `verify-model-nvs-evidence.py` checks frozen integrity without re-running suites.

Rollback only this six-path source/test/doc package (initial commit plus bounded IO-completion followup) before dependents. Do not delete model keys, reset NVS, overwrite config/history/Recorder/models or revert parent DHW/Recorder/restore fixes. Parent owns canonical WORKBOARD/PLAN/merge and official image/release gates; generic-size remains with the separate child. No installation/publication/login/broker/live HA/device/reboot/EMS/Tado/TX/actuator/heating action. Whole PLAN remains in progress; admission is not completion.

## Same-package IO/decode acceptance completion

The original15case Stage43 draft remains immutable historical evidence, superseded for review by MODEL-NVS-FINAL-RESULT.json. New tests reproduced18/20PASS with two source-contract failures BEFORE the four-line read-side check: invalid/missing/wrong partition still allowed nonempty reads, and postcommit readback ignored stat failure. After correction20/20native +same20fullyinstrumentedASan/UBSan and actualSDKobjectPASS; receipts are in the final manifest. This is not a new backend or a change to accepted resource/store algorithms.

All3nonempty warm/coast/curve decode tests execute real SHA successfully, then attempt gate.begin inside the active shared transaction. Gate failure must stay latched before model.restore and before success; all three attached models report storagefault/disabled, repeated load/checkpoint performs no further IO and old bytes stay exact. A postcommit stat failure preserves the already durable blob and never retries or erases it. SDK_IO remains a test boundary, not real NVS/device evidence. DefaultNone, quotas, GC, config key and no runtimebinding remain unchanged.
