# E32 page performance and boiler workflow review

Review date: 27 October 2026. Development target: E32 beta.6. The installed device
remains beta.4; none of the changes below has been installed or exercised against
the physical boiler during this work.

## Measured starting point

Read-only LAN measurements against installed beta.4 used three sequential samples
per route. These are small-sample measurements, not a load or soak test.

| Resource | Response body | Median complete response |
| --- | ---: | ---: |
| Home HTML | 71,273 bytes | 381 ms |
| UI translations | 101,906 bytes | 537 ms |
| Complete EMS reference, gzip | 69,922 bytes | 390 ms |
| EMS device controller | 28,874 bytes | 220 ms |
| Telemetry API | 15,016 bytes | 130 ms |
| Device API | 13,195 bytes | 133 ms |
| Settings metadata API | 676 bytes | 62 ms |

A separate authenticated Chromium cold navigation reached the dashboard in
2,494 ms and transferred approximately 436 kB including the document and resource
response overhead. Authentication and the device identity were checked. Browser
mutations and foreign-origin requests were blocked for this measurement.

Local measurement evidence is retained in `out/e32-performance-20261027/`.
Authentication material stays in ignored private files and is not in this report.

## Changes

Larger HTML, JavaScript and CSS files have gzip representations generated at
build time. The E32 sends flash-resident bytes directly; it does not compress
responses or construct another complete response body in RAM. Original source
bytes remain embedded for existing independent package verification. The extra
compressed representations consume flash rather than the runtime heap.

Static UI responses use representation-specific SHA-256 ETags and
`Cache-Control: private, no-cache`. Authorization runs before conditional
responses. Every reload revalidates the cached bytes, including after a firmware
change. Live APIs, authentication, mutations, redirects and errors retain
`no-store`. Gzip negotiation respects explicit exclusions. Conditional responses
carry the selected representation's length and avoid the pinned server's empty
response warning. The behavior follows
[HTTP representation negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.3).

Home no longer downloads the EMS controller/catalogue, Bluetooth editor, or log
controller. These load on demand. The boiler panel now needs a compact generated
metadata file, approximately 4.3 kB compressed, instead of the 70 kB complete EMS
reference. Its slow or failed download does not delay mounting the test controls;
failed dependencies can be retried on a later visit.

Boiler controls and device values subscribe to one bounded telemetry request and
one polling timer. The response carries the inventory, the existing monitor's
fields, operation metadata and session-scoped test state under one lock/time.
Leaving the page cancels its subscriptions, timers and pending reads. Large telemetry JSON bodies are built in one
reusable 64 kB PSRAM buffer. An allocation failure or oversized response produces
a complete 503 error before any body is sent, without falling back to a growing
internal-heap allocation. Hidden tabs
pause polling; returning reads current state without restoring test supervision.

Classic Home/About and parameter status use compatibility projections of the
same aged monitor. This removes the E32 Classic loop's repeated copying into the
legacy cache while preserving JSON units and the generic/Plus implementation.
Old or unreliable values cannot appear as fresh dashboard measurements.

## Boiler page

The page starts with **Read settings → Prepare → Start → Stop**. Only the
applicable action is visible. Flow temperature and duration are editable during
preparation even when a settings read is still required. Defaults follow the
received firmware limits, including 50 °C / 600 seconds for the prepared profile.

One explicit setup declaration covers the settings read and preparation. It
expires after two minutes and is consumed by preparation. A read cannot silently
erase that declaration; a foreign scope, hidden page, uncertain outcome or changed
boot cannot inherit it. Starting heating retains a separate explicit action.
Stop remains accessible using the last known test scope after a read failure.

Devices have one received-entity table each. Product identity comes from received
metadata, never the decorative boiler selection. The reviewed E32 bus identity is
not displayed as another external thermostat. Read-only values, settings and the
manual demand entry appear together. The duplicate measurement/settings tables
and unrelated all-model catalogue have been removed from the page. Diagnostic
telegram information and zero-only testing remain in a collapsed section.

The display follows the device-oriented approach described in
[EMS-ESP configuration](https://docs.emsesp.org/Configuring#customizing-entities)
and the upstream
[Devices view](https://github.com/emsesp/EMS-ESP32/blob/8f7049b47a1641cc22c91c63cfb27c1278b282ed/interface/src/app/main/Devices.tsx).
The complete pinned factual reference remains available in the source. Its
writeability flags describe EMS-ESP support; they never authorize an E32 write.
The E32's persistent-settings source/installation gates remain closed and the
page explains that distinction. These UI changes preserve the finite attended
test service and its existing hardware limits.

## Validation and remaining measurement

The initial performance checkpoint passed 1,186 native cases. Twenty-one compiled scenarios exercise the actual
E32 authorization/static response branches, including authentication before 304,
wrong representation tags, uncached live APIs, exclusions, PSRAM allocation
failure and overflow. Six dedicated buffer cases also pass ASAN/UBSAN and leak
checks. Generator
checks reject stale or missing compressed/source bytes. Firmware image checks
also verify decompression identity and actual inclusion of the generated bytes.

Chromium fixtures cover desktop/mobile and Dutch/English, the complete
read/prepare/start/stop path, bounded declarations, lost supervision, uncertain
outcomes, duplicate suppression, dependency failure, navigation and cache reuse.
The cold Home fixture has a 160 kB body budget; current results are approximately
141 kB. These fixture byte counts are not a measured on-device speedup.

After the next separately authorized installation, repeat the same read-only
browser/LAN measurements and compare navigation time, transferred bytes, API
latency, internal free/largest heap blocks and disconnect behavior. Current local
evidence is in `out/boiler-workflow-20261027/` and `out/page-loading-browser/`.
No physical heating or installation acceptance is inferred from these tests.

## Follow-up: identity and closed trial state

A subsequent passive read of the installed device found a closed trial with a
restart requirement, reported stop and zero positive-demand frames. Its reviewed
local bus identity is 0x0B. Received traffic from 0x08 and 0x17 contained no
complete version report. An unknown product label therefore reflects missing
identity evidence; it must not be filled from the decorative boiler selection.

The candidate adds an explicit optional identity read next to the unknown boiler.
It shares the existing boot/revision/session owner and finite poll/response
deadlines with configuration reading. The only additional permitted wire frame
is a fixed 0x02 read of ten bytes from boiler address 0x08. There is no arbitrary
frame input, scan, automatic request or heating command. Separate per-kind
cooldowns allow the next explicit configuration read without making identification
a heating prerequisite. Received model metadata updates the existing entity card.
Other unidentified senders remain in collapsed traffic diagnostics.

A closed trial now names its restart requirement and offers the existing
confirmed, authenticated, update-aware restart control. No restart was performed
during this work. The same four desktop/mobile and EN/NL workflow fixtures cover
identity reading, received model naming, the subsequent configuration/preparation
path and restart cancellation. The native suite now passes 1,194 cases; 63 scoped
read/transaction/UART cases also pass ASAN/UBSAN with leak detection.

GitHub's first performance checkpoint exposed a missing dependency in the
isolated post-build verifier fixture. The fixture now copies both web verifier
modules, source assets and generated metadata; eleven cases check valid output,
corrupted data and the existing firmware/layout constraints. The actual E32
firmware build passed in that run. No failed CI run is represented as release
acceptance.
