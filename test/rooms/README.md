# Room lifecycle regression checks

Run `browser.cjs` using Playwright Core 1.63.0 and its installed Chromium:

```sh
NODE_PATH=/path/to/node_modules CHROMIUM_PATH=/path/to/chrome node test/rooms/browser.cjs
```

Executes the shipped catalog and program pages with the shipped jQuery,
Bootstrap and multiselect scripts and their shipped CSS. The successful-load
check asserts actual spinner invisibility, not only the presence of a hiding
class (Bootstrap's later `d-flex!important` can override `d-none!important`).
HTTP/storage is an explicit independent
in-memory fixture enforcing room references, not the ESP32 REST server. Covers
fresh empty state, create/save/readback/reload/rename/delete, dependency cleanup,
cancel, legacy orphan cleanup, concurrent-change detection, failure and partial
completion feedback. CI runs this alongside the existing onboarding pages.

`scripts/verify_e32v2.py` additionally requires empty factory room and program
JSONs; `scripts/test_e32v2_verifier.py` injects orphan and example-room faults.
At handoff, inspect the actual generated SPIFFS image, not staging alone.

Physical acceptance remains a separate board/browser test. A readback confirms
an HTTP representation, not power-loss-safe flash persistence. The existing
SPIFFS writes are not multi-file transactions; referenced deletion writes each
program first, verifies it, and deletes the catalog entry last. Partial failure
names completed programs and requires reload. Concurrent-change checks are
best-effort preflight/readback, not an atomic compare-and-swap across clients.
