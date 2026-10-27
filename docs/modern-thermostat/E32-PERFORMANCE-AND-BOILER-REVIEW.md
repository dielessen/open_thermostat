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
Subscriber rendering errors are reported through the browser's normal error
handler and cannot poison a successful read for the other panels. Six shared-store
unit cases cover request sharing, teardown, failures, bounds, visibility and this
failure isolation.

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

## Update page lifecycle

The update page also owns its status-read lifecycle. Hidden tabs stop polling
and abort pending status bodies. Returning requires a new valid status before
commands can be used. Leaving the updater releases its timer, read, observer and
visibility listener. There is at most one outstanding status read; stale results
cannot unlock a newer command. An explicitly submitted update command is not
aborted or replayed by visibility/navigation changes. All 37 updater browser
scenarios pass against simulated HTTP, including these lifecycle cases. This
reduces idle background work without changing firmware installation authority.

## MQTT socket backpressure

The pinned Arduino WiFiClient implementation waits up to one second per socket
write readiness check and retries ten times; partial progress resets that retry
counter. A stalled MQTT peer can therefore hold the same main loop that serves
HTTP for seconds. This is a source-code finding, not a reproduced live outage.

The native MQTT socket now uses nonblocking sends with one total 100 ms budget
for an ordinary write. Partial progress advances the buffer without restarting
the deadline; backpressure yields to the scheduler. A backwards or stuck clock
cannot create an unbounded retry loop. A partial, failed or late write closes the
same socket before another MQTT frame can follow. A failed result remains an
uncertain outcome; already handed-off bytes cannot be retracted or replayed as a
new command. No extra socket, task, queue or response-body allocation is added.

The separate actuator path retains its existing original owner/freshness guard
and single nonblocking handoff. It does not inherit ordinary-write retries or
the new latency budget. Deterministic tests and actual host socket pairs cover
backpressure, byte order, partial progress, late/faulted clocks and the existing
actuator guards. These tests do not establish on-device timing. TCP connection
and MQTT reads retain their separate contracts. Native MQTT DNS resolution is
now handled by the additional change below.

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

## Native MQTT DNS without a main-loop wait

The pinned Arduino 2.0.17 `WiFiGeneric::hostByName` can wait for DNS readiness
for 16 seconds and then for the answer for another 15 seconds. PubSubClient
selects that synchronous path when configured with a hostname. This was a
source-code finding; no new failure was triggered on the installed E32.

The native transport now schedules DNS on lwIP's existing TCP/IP thread with
`tcpip_try_callback`, then returns to its normal owner tick and HTTP loop. The
try-post fails immediately when the native mailbox is full. The query requests
IPv4, matching the current WiFiClient transport. Numeric IPv4 broker addresses
skip DNS. PubSubClient receives only the resulting numeric address through its
public API, so it does not enter `hostByName`. The MQTT client and socket remain
the existing single connection. HTTPS firmware updates use a separate path.

A fixed pool of four hostname slots outlives transport instances. Retiring an
owner removes its authority immediately, but keeps callback storage reserved
until lwIP's one final callback completes. Native completion publishes its
result through release/acquire atomics. Callbacks never dereference a transport
object. Exhausting the pool fails without waiting or allocating more slots.
Queries have an original 16-second owner deadline; polling or late completion
does not renew it. No result is carried into another connect attempt: native
lwIP remains the DNS cache owner and applies its own TTL. Network loss and SOURCE
lockout retire the pending lease.

The callback and nonblocking-post contracts were reviewed against the pinned
[ESP-IDF v4.4.7 lwIP submodule](https://github.com/espressif/esp-lwip/tree/a45be9e438f6cf9c54ec150581819c3b95d5af6b):
[`dns.c`](https://github.com/espressif/esp-lwip/blob/a45be9e438f6cf9c54ec150581819c3b95d5af6b/src/core/dns.c)
and [`tcpip.c`](https://github.com/espressif/esp-lwip/blob/a45be9e438f6cf9c54ec150581819c3b95d5af6b/src/api/tcpip.c).
The SDK may allocate its own bounded queue message and DNS packet; the new owner
does not create a task, socket, unbounded queue or private DNS cache.

Host fixtures exercise queued/cache/error results, an immediate error callback,
mailbox exhaustion, destruction, replacement, pool exhaustion/reuse, original
deadlines and cross-thread completion. These are software lifetime and scheduling
checks. On-device page latency, TCP connect and MQTT CONNACK/read delays remain
separate acceptance and review work. No firmware or boiler action was performed.

## Avoid work for disabled log messages

The vendor logging macros evaluate message arguments before the logger filters
them. A disabled project feature could therefore still build JSON, query heap
statistics or traverse SPIFFS. The E32 now checks destination acceptance before
evaluating those arguments, using the public logger interface. Logger, level and
feature/format expressions are evaluated once. Generic-board macros are unchanged.

BufferedLogger's feature acceptance combines the existing serial/TCP sinks with
the independent web and syslog settings, including the ESP/EMS source choices.
A published atomic mask allows that read without taking the SystemLog queue
mutex. The existing append method still owns filtering, redaction, contention
accounting and storage. Messages accepted only by web/syslog no longer undergo
a second serial formatter and sink-vector allocation; messages accepted only
by serial avoid the diagnostic-copy formatter. Disabled EMS debug output no
longer formats each payload byte as hexadecimal. Deferred EMS receipt logging
also skips formatting when neither web nor syslog wants the record. Reception,
monitor updates, device inventory and transmit admission are unchanged.

The ten-second heap summary remains at INFO. The separate SPIFFS usage line is
now DEBUG, so the flash scan runs only when a selected destination requests App
debug output. The existing E32 serial sink remains TRACE: enabling App keeps
that debug line available there. No installed logging setting was changed.

The periodic Ethernet route refresh also uses `tcpip_try_callback`. A full
network mailbox returns immediately; the existing one-second refresh supplies
the next attempt. No authoritative network check is replaced with cached data.

The real logger/NVS/native-hook/UDP fixture checks side-effect-free rejection,
single evaluation and independent destination acceptance, alongside the existing
credential redaction and full serial output. Native tests compare the lazy
acceptance mask with actual append outcomes across every level/source setting.
These checks establish avoided work and preserved output semantics, not a
measured on-device page-load improvement.
