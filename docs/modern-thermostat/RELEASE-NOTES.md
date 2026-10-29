# E32 V2 beta18 — a refreshed interface, learning in shadow mode and a sturdier E32
<!-- user-release-notes:v2:en -->

A large follow-up to beta17. The E32 still runs heating in shadow mode: it
calculates and learns, compares itself with your thermostat, and does not send
its request to the boiler yet. Use it together with HA 0.4.0b10.

## New

- A refreshed interface in English and Dutch, light and dark: five menu items
  (Overview, Rooms, Boiler, Sensors, System), pages that remember where you are,
  larger controls for phones and a short plain-language help line at every
  setting.
- Rooms are managed in Home Assistant when you use it. The E32 page then shows
  them read-only with the connection state, explains where to set what, and
  still lets you edit here when Home Assistant is not reachable. An E32 that
  was never linked to Home Assistant edits its rooms, Bluetooth sensors and
  week programs on the Rooms page itself, and the Overview shows the E32's own
  rooms with or without Home Assistant.
- Your own web password under System → About (8–64 characters). Until you
  change it the sign-in stays `admin` / `admin`, and the Overview reminds you.
  The E32 stores only a salted hash; `password-reset` over USB restores the
  factory password.
- Week programs, "today" and the daily comparison follow the E32's own time
  zone (System → Network), so any time zone and summer-time rule works.
- Learning per room in shadow mode: how fast the room warms up at which flow
  temperature, the lowest flow that still warms it in time, when to start
  before the next week-program switch, and whether holding the night
  temperature or letting it drop uses less gas (estimates in kWh, m³ and €).
- My boiler starts with the essentials: temperatures, pressure, burner starts
  in the last hour with a short-cycling warning, and hot water today (tapping
  versus keeping warm). The attended trial and all EMS values sit below.
- The last locking and blocking boiler fault and the boiler's own uptime join
  the one EMS table; the thermostat values were checked against real
  telegrams of an RC10-type thermostat.
- The flow limits show your boiler's own maximum heating temperature; the E32
  never asks for more than that.
- A new E32 gets a unique name, `openthermostat-` plus the end of its MAC
  address, as network name and MQTT client ID, so two E32s never clash.
  Existing settings are kept.
- Heating telemetry is split into `fw/telemetry/heating`, `heating_summary`
  and `heating_learned/<room>`, so each message stays small.
- Prepared but switched off: active heating control behind a firmware gate,
  with takeover only after you confirm your thermostat is disconnected, a stop
  when another controller sends heat requests, frost protection below 8 °C and
  a hand-back button.

## Fixed

- Bluetooth thermometers deliver readings reliably: scanning no longer pauses,
  readings stay valid for 15 minutes, a sensor whose counter restarts (new
  battery) is accepted again, one bad report no longer clears the values, and
  the E32 restarts by itself 30 seconds after you save Bluetooth settings.
- An update that fails to start rolls back to the previous firmware instead of
  restarting forever. Firmware update errors are now in English.
- Very deeply nested JSON from the network can no longer crash the E32; all
  parsers of outside input are fuzz-tested in CI.
- A watchdog now also covers start-up; a stalled GitHub download can no longer
  switch off the supervisor; the E32 restarts itself when Wi-Fi reports
  "connected" but the network no longer answers or when no Bluetooth sensor has
  been heard for 30 minutes, reconnects to Wi-Fi more patiently, and backs off
  instead of restarting every 15 minutes during a long Wi-Fi or network outage.
- Less use of the memory Wi-Fi needs: JSON documents and large replies live in
  PSRAM, and the Bluetooth page reply is small and bounded.

## Updating

Install this firmware and HA 0.4.0b10 together. HA 0.4.0b9 keeps working with
the fields it knows, but ignores heating status with a request above 60 °C:
keep the maximum flow at 60 °C until HA is updated. After an update the E32 confirms the new firmware itself
once it has run normally for about a minute and the network has worked; until
then a failed start rolls back to the previous version, and other restarts are
postponed. Without a working network connection within 10 minutes (router,
MQTT broker or the web page answering) it also rolls back. The name of the
setup Wi-Fi network now ends in the last digits of the E32 MAC address and may
differ from before.
Check the time zone under System → Network if you live outside Central Europe.

## Limitations

Shadow mode only: active control stays switched off until the attended
switch-over. EMS Classic (EMS 1.0) boilers only; EMS+ is planned. The learned
advice is shown, not applied. The plan's maximum flow can be set up to 80 °C,
never above the boiler's own maximum heating temperature. Night-setback gas
estimates need an outdoor temperature and become more accurate with a gas
meter in Home Assistant.

# E32 V2 beta17 — rooms and heating in shadow mode, a stable Bluetooth page and pvvx sensors
<!-- user-release-notes:v2:en -->

The first step towards the E32 heating the house itself. Rooms live on the E32,
and the E32 calculates the boiler request from them. In this beta it only
reports that request (shadow mode) and compares it with the thermostat that
still controls the boiler. Use it together with HA0.4.0b9. The beta16 tag was
not published: its CI expected the older number of boiler-field entities, its
package linked one unreviewed SDK object, and a pvvx sensor profile would not
have survived a restart.

## New

- Rooms and heating page: rooms with a state (active, inactive or inactive
  until a date), the heat emitter, and up to four temperature sources in order
  (a Home Assistant entity such as the tado, or a Bluetooth sensor). The first
  fresh source leads; the others are fallback. Without any source the room uses
  its last value for 30 minutes, then stops asking for heat.
- One room plan, edited from two sides: Home Assistant and the E32 page work on
  the same plan with a revision number, so an edit never silently overwrites a
  newer one. Editing a room keeps its readings and burner timers.
- A week program per room (up to six switch points a day, or the same every
  day) keeps the night setback and morning warm-up going when Home Assistant is
  away; without a clock the fixed fallback applies. The page shows where each
  setpoint comes from.
- Calculated boiler request: the flow temperature follows the largest room
  shortfall between 30 and at most 60 °C, with five-minute minimum burner on and
  off times.
- Daily comparison with the thermostat: heating time, burner starts, flow range
  and how close the starts are, for today and the last seven days.
- The E32 shares its Bluetooth sensors with Home Assistant.
- Bluetooth thermometers with the pvvx firmware (BTHome v2, plain or with a
  bindkey; also the older PVVX Custom format). The Bluetooth page counts
  received and unrecognised reports and explains why a sensor waits.
- One table for all EMS entities: thermostat, maintenance and EMS+ values reach
  Home Assistant over the boiler-fields route; HA's list is generated from it.
- My boiler and Boiler test are one page. Old links still work.
- The system log shows what the device was doing before its last restart.

## Fixed

- Opening the Bluetooth page could make the E32 unreachable until a power
  cycle. Its status built a large reply from up to 128 nearby devices every five
  seconds and ran the device out of memory. The reply is now small and bounded
  (at most 32 nearby devices, strongest first), the nearby list only fills
  during a search, and Search no longer loses to the automatic scan.
- If the E32 still hangs completely, a hardware watchdog restarts it within
  about two minutes and keeps the record of what it was doing.
- Boiler reception no longer stays broken after a bus error: a reset could
  leave a stray 00 in front of every later message until a reboot.
- A failed boiler trial sends its safety zero request for one stop window only.
- The E32 restarts itself when its main loop hangs for 5 minutes, or when
  Wi-Fi or the MQTT broker stays unreachable for 15 minutes, never during an
  update.

## Updating

Home Assistant now checks for new firmware and installs it over the local
network (HA0.4.0b9); the upload on the update page stays available. Install
this firmware and HA0.4.0b9 together. A sensor with pvvx firmware needs the
profile "Thermometer with pvvx firmware (BTHome)" on the Bluetooth page, then a
restart.

## Limitations

Shadow mode only: the E32 does not send its heat request yet. That needs an
attended switch-over with failure tests first. The whole room plan must fit in
4 KB, so many rooms with full week programs do not fit. Native GitHub HTTPS is
no longer used.

# E32 V2 beta15 — reliable boiler trial, browser-checked updates and more EMS devices
<!-- user-release-notes:v2:en -->

Follow-up to the beta12 attended trial, which the owner accepted: about 6½
minutes of 50 °C heat, ended early by a hot-water tap. Use it with HA0.4.0b7.
The beta13 and beta14 tags were not published: their CI stopped on a Home
Assistant room editor test. On a slow runner the editor closed its open advanced
section when it redrew; it now keeps open sections. Beta15 is the same firmware
change with that fix and sturdier browser tests.

## New

- Read EMS+ boilers (0xE4-0xEA: flow, return, modulation, pressure, counters,
  hot water) and room thermostats (RC10, RC20, RC25, RC30, RC35 and the EMS+
  heating-circuit monitor: room temperature, setpoint, target flow) from one
  table based on the EMS-ESP reference. They appear as read-only cards on the
  Boiler test page and under `ems_entities`; not yet verified on hardware.
  The thermostat's own boiler request (0x1A) and the maintenance message are
  rows in that same table; beta11's separate `bus_observations` is removed.
- The update page can look up the latest release on GitHub in your browser and
  check a downloaded firmware.bin (SHA-256, size and version) before uploading.

## Fixed

- A missed end-of-frame BREAK after our own transmission no longer stops a
  trial: the 0x00 delimiter is verified and dropped, and the boiler's reply is
  kept (`echo_break_recoveries`). Missing echo data is still a fault.
- Tap water during a trial pauses central heating instead of ending the trial,
  and Stop is confirmed once CH is off even while the burner serves tap water.
  Starting a trial still needs hot water off. The result counts interruptions.
- The trial result relies on reported CH operation; the boiler's read-back
  setpoint, which Classic boilers keep at 0, is optional.
- Read device identity for the thermostat now really transmits; beta12
  refused that request before sending it.
- Failed automatic GitHub checks back off from 30 minutes up to 12 hours, and
  the main loop has more stack (8 KiB instead of 6 KiB).

## Updating

Install the exact public firmware with the local upload; since beta12 the
update slot is erased sector by sector, so the upload no longer resets the
board. HA0.4.0b7 needs no update.

## Limitations

Native GitHub HTTPS still fails on this device. GitHub's download server does
not let a web page fetch the file itself, so the browser check needs you to
download firmware.bin first. Automatic boiler/valve control and persistent
boiler-setting writes remain disabled.

# E32 V2 beta12 — thermostat requests, device identity and a tidier dashboard
<!-- user-release-notes:v2:en -->

Follow-up to beta10 after a review against the EMS-ESP telegram reference.
Use it with HA0.4.0b7. The attended trial limits are unchanged. The beta11 tag
was not published: its CI stopped on a host test stub that did not yet know the
new sequential OTA erase. Beta12 is the same firmware change with that test fixed.

## New

- Read what another controller, such as the room thermostat, asks of the
  boiler: the requested flow temperature, burner power and pump setting from
  its UBASetPoints (0x1A) telegrams. Our own trial requests are kept apart.
- Read the boiler's maintenance message (0x1C, for example H03) and its most
  recent fault record (0x10/0x11: code, number, start time and duration).
  These are passive reads under `bus_observations` in the EMS telemetry.
- Read device identity now also works for other devices seen on the bus, such
  as the room thermostat. It is one explicit version request per button press,
  only to an address that sent a report during this boot.

## Fixed

- The completed controller request now really reaches Home Assistant. Beta10
  expected the profile name `classic`, but the device reports
  `classic_observed`, so the MQTT message was never sent.
- Firmware uploads no longer reset the board halfway through. The update slot
  is now erased sector by sector while writing, instead of in one multi-second
  erase that tripped the task watchdog. This applies to the local upload and to
  the native GitHub update.
- The dashboard shows only boiler values that were actually reported:
  flow, return, modulation and pressure tiles appear only with a value. The
  read-back setpoint, flame/pump/fan bits and the flow rate are no longer on the
  dashboard because they are not reliable on Classic boilers; the Boiler test
  page still lists every entity with its quality.

## Updating

Preserve settings and install the exact public firmware. The board runs beta10,
which still has the old one-step erase; if the local upload resets the board,
flash this release manually once. Later updates use the new erase. HA0.4.0b7
needs no update.

## Limitations

The UART accounting fault is still recorded, not fixed. Native GitHub HTTPS
still fails on this device; a failed connection now records its duration and
the largest free memory block, to narrow down the cause. No TLS repair is
claimed. Automatic boiler/valve control and persistent boiler-setting writes
remain disabled.

# E32 V2 beta10 — responsive web server and UART fault trace
<!-- user-release-notes:v2:en -->

Diagnostic follow-up to the beta9 attended trial. Use it with HA0.4.0b7.
The60second request interval and all trial limits are unchanged.

## New

- Keep the UART events from just before an `echo_event_accounting` fault:
  the last16 receive/break/overflow/timeout events, our own write starts and
  ends, and the echo bookkeeping (consumed, trailing, frame, broken, pending
  length). Telemetry shows them under `last_uart_error.echo_fault`. Diagnostic
  only, never used to admit or block a request.
- Publish the completed controller request on the existing native MQTT
  connection (`v1/fw/telemetry/controller_request`, not retained) in the same
  15-second status window. No extra network client and no new command route.

## Fixed

- An open connection that never sends a request no longer holds up the web
  server for five seconds. It is closed after250ms, so the five-second trial
  supervision is not starved by an idle client. Request parsing is unchanged.
  The fix was measured on the device as private build beta9-httpfix.1.
- HA0.4.0b6 listened for the controller request on a legacy topic that modern
  firmware never sends, so its command entity never appeared.

## Updating

Preserve settings and install the exact public firmware using the existing
application update route, then install HA0.4.0b7. The board currently runs the
private diagnostic build beta9-httpfix.1. Installation and any attended trial
are checked separately.

## Limitations

This release records the UART accounting fault; it does not fix it. The beta9
trial stopped after about five minutes on that fault, so a full ten-minute
trial remains unproven. Native GitHub HTTPS updates still fail on this device;
the root cause is unknown and no TLS repair is claimed. Automatic boiler/valve
control and persistent boiler-setting writes remain disabled.

# E32 V2 beta9 — one-minute boiler request interval
<!-- user-release-notes:v2:en -->

Narrow correction for the owner-requested50°C, ten-minute attended trial.
HA0.4.0b6 remains compatible and unchanged.

## New

- Send the first heat request on Start, then repeat the same target every60
  seconds at the next eligible EMS poll. Measure the interval from the previous
  completed transmission. Identical values are really transmitted again.
- Show the actual firmware interval on Boiler test in English and Dutch.
  HTTP supervision remains frequent; it does not transmit a new boiler target.

## Fixed

- Separate positive refresh from zero pacing. Manual Stop, supervision loss
  and the fixed600second deadline immediately request withdrawal; they never
  wait for the60second refresh period. Existing short zero retries and later
  stop-report checks remain unchanged.
- Retain beta8's separate completed-controller-request record, warm-water
  preparation and last UART fault diagnostics. Boiler temperatures stay intact.

## Updating

Preserve settings and install the exact public firmware using the existing
application update route. HA0.4.0b6 needs no further update. Beta8 is published,
but its local upload did not complete: the observed board still runs beta6.
Installation and the full attended trial are checked separately.

## Limitations

The one-minute interval is the requested test method, not a proven timeout
for every boiler. The two earlier trials were incomplete. Native GitHub HTTPS
and a local upload have failed on the current device; their root causes remain
under investigation. This release does not claim to repair TLS. Automatic
boiler/valve control and persistent boiler-setting writes remain disabled.

# E32 V2 beta8 — separate requested and reported boiler temperatures
<!-- user-release-notes:v2:en -->

Correction bundle with HA0.4.0b6 for the attended Ecomline Classic trial.
Beta.7 was not published: packaging caught an extra SDK atomic dependency in
UART diagnostics. Beta.8 uses the existing ESP critical section and retains
only the reviewed SDK inputs. The requested test/command behavior is unchanged.

## New

- Show **Last E32 flow request** separately from the boiler-reported selected
  temperature. The value is recorded after completed UART transmission, including
  a transmitted zero on Stop. Opening a form or queuing a target does not change
  it. A reboot starts unknown. The boiler's own temperature fields are preserved.
- The existing non-retained EMS status packet carries this command record for
  the separate read-only HA entity. It states controller origin and original
  completion time; it is not a boiler acknowledgement or measured temperature.
- An already-warm boiler can receive a lower50C request. Remove the former60C
  water cutoff; retain live-report checks and a separate5–<90C observation bound.
  The requested target remains40–50C and the trial at most600seconds. Existing
  boiler temperature settings are not increased. The full66C/50C/600s case is
  software-tested; the next attended physical test is separate.
- Preserve the initiating manual Stop or deadline when a later transport fault
  occurs. Also retain the last UART error reason/time for investigation.
- Yield between manual app-upload chunks so a continuous sender shares time
  with other tasks. Native GitHub HTTPS repair is not claimed by this change.

The first physical beta.6 trial showed pump/burner operation and a later stop,
but the owner stopped it after about375seconds. A transport fault was also
recorded; its causal order with the manual stop is unknown. The adapter kept
reporting selected temperature0 while reported water moved59→46→50C.
A complete new600second trial is still required. Automatic boiler/valve control
and persistent boiler-setting writes remain disabled.

## Retained from beta.6

Room contacts, manual helpers, comfort/presence/vacation, battery snapshots,
connected installation settings, compressed web assets, shared telemetry and
bounded background work remain included. Trial setup still uses one declaration,
a fresh gauge reading, an explicit Start action and an always-available Stop.

[Full beta.6 changes](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-beta.6/docs/modern-thermostat/RELEASE-NOTES.md).

## Fixed

Keep a manual stop visible when another fault follows. Retain the UART fault
kind/time for the next diagnosis and share task time during app uploads.

## Updating

Use the exact beta.8 firmware and matching public checksums after preserving
settings. HA0.4.0b6 provides the separate entity; older firmware leaves it absent.
Installation uses the existing update/app-upload routes and a separate postcheck.

## Limitations

Experimental, attended trial only. Boiler readback and original controller
commands remain distinct. A complete ten-minute physical test is still open;
source qualification and automatic boiler/valve control remain disabled.

# E32 V2 beta6 — integrated room and installation controls
<!-- user-release-notes:v2:en -->

Experimental coordinated release with HA 0.4.0b4. Installation and physical boiler/valve
acceptance are verified separately.

## New

- Guided boiler trial: **Setup → Prepare → Heat → Result**, default 50 °C / ten
  minutes. One setup confirmation, explicit next actions, remaining time and Stop.
  Results distinguish a full reported pass, partial duration, missing evidence,
  zero-only checks and faults. E32 session observations survive page reopening
  until a new preparation or restart, without resuming supervision.
- One entity table per observed device, identified from its received product
  report. Read-only values and configurable settings are distinguished in the
  same table. The unrelated all-model catalogue and duplicate settings/value
  lists have been removed from the page.
- Optional **Read device identity** requests one bounded version report for an
  unknown boiler. Opening or refreshing the page never sends this bus request.
- A closed trial shows its restart requirement directly and offers the existing
  confirmed, update-aware restart action. No heating resumes automatically.

- Room **Details** on the E32 dashboard explains the effective target source,
  selected comfort mode, reported temporary duration and explicit UTC vacation end.
  Window/door and presence pauses have clear reasons. It uses the existing
  control snapshot and does not add polling or a second countdown clock.

## Fixed

- Load debug feature filters only when **Settings → Debug settings** is opened.
  Folding preserves edits; closing/navigation cancels pending reads. Saving
  applies the existing live filters without an unnecessary restart prompt, and
  an unconfirmed save requires a fresh read before retrying.

- Keep WiFi setup’s five-second request deadlines active through status, scan
  and completion JSON bodies. A lost accepted completion is recovered from
  current status without repeating it; text acknowledgements for connection and
  scan requests retain their existing handling.
- Keep the shared session check’s original ten-second timeout active through
  the response body. A stalled or late reply cannot block page data indefinitely
  or release queued actions after timeout; a new request can recover normally.

- Compress larger UI files at build time and serve them directly from flash.
  Private ETags revalidate cached UI bytes after authentication; live readings,
  credentials, operation outcomes and errors remain uncached.
- Load page-specific scripts only when needed. The device panel uses a compact
  model/field metadata file instead of downloading the complete telegram library.
- Reuse one bounded PSRAM buffer for dashboard and large telemetry JSON responses; allocation
  failure or overflow returns a complete error without partial JSON.
- Share one bounded telemetry GET/poll between boiler controls and device values.
  Leaving the page cancels its subscriptions and pending reads.
- Derive Classic Home/About values directly from the same aged monitor used by
  telemetry and control, retaining the existing JSON units and suppressing stale
  or unreliable values. Generic-board and existing Plus paths remain separate.

- Bound ordinary native MQTT socket writes to one 100 ms total budget, closing
  partial or late frames on the same connection. Existing actuator handoff
  guards remain separate.
- Resolve native MQTT broker hostnames asynchronously on the existing lwIP
  thread. DNS waits no longer hold the HTTP/main loop; retired lookups retain
  bounded callback storage until completion. TCP opening also progresses between
  loop passes with its original deadline, and transfers the same socket into
  MQTT. A peer disappearing at handoff cannot trigger a synchronous reconnect.
  CONNACK/read timing remains separate; firmware-update HTTPS uses a different path.
- Show main-loop interval counters under **System log → Loop timing**, using
  the existing log-status response. These distinguish observed loop delays from
  page-load time. Hidden log pages stop polling; submitted settings writes are
  retained through navigation without automatic replay.
- Skip repeated clock/settings/queue work while syslog is disabled or the route
  is offline. Local and serial records remain independent, and reconnecting
  preserves bounded queues without replaying old packets.
- Avoid building disabled log messages. Web/syslog levels and source selections
  remain independent of serial output; enabled messages retain redaction and
  bounded storage. The periodic route refresh also fails fast if its native
  network mailbox is full.
- Pause Bluetooth status polling while hidden, and resume with one read without
  replacing drafts, keys, focus or expanded panels. Settings loads/saves do not
  overlap automatic status reads. Submitted saves and scans keep their own
  deadline across navigation, without replay or retired-page verification reads.
- Retire dashboard reads while hidden or after navigation. Returning starts one
  fresh read; late or timed-out bodies cannot replace its state or the next page.
- Suspend updater status reads while the page is hidden and release them on
  navigation. Submitted install/check commands are not aborted or replayed.

## Updating

Use the E32 GitHub updater and the separate HA 0.4.0b4 package, with backups and
postchecks. An update does not start a boiler trial.

## Limitations

No live boiler or valve test, device restart or physical qualification is implied.
Prepared capabilities retain their explicit installation and source requirements.

# E32 V2 beta5 — longer attended boiler trial and clearer diagnostics
<!-- user-release-notes:v2:en -->

Adds an attended ten-minute boiler demand and clearer entity/update controls.
Firmware installation and physical boiler commissioning are verified separately.

## New

- **Ten-minute attended demand.** Prepare 50 °C for 600 seconds to allow time for
  boiler startup. The Classic trial supports 40–50 °C, repeated setpoints and a
  separate 5–<60 °C measured-water cutoff. Fresh setup/gauge checks precede start;
  their declarations remain valid for that finite run. A five-second supervision
  lease, separate Start/Stop actions and later stop feedback remain required.
- **One boiler page.** Boiler test now also contains the settings, received
  devices and values, and telegram reference. The separate EMS devices menu
  entry is removed; existing page links open Boiler test.
- **Visible entity access.** Read-only values, configurable settings and
  commands have distinct labels and filters. The complete pinned EMS-ESP
  boiler catalogue includes all 258 model-dependent definitions, with types,
  options, bounds and E32 implementation status. Catalogue entries do not
  grant write permission or assert support by the connected boiler.
- Boiler-test read and zero-test buttons explain missing setup confirmations,
  unavailable feedback and hot-water operation. Confirmations still apply to
  one read or trial and must be repeated afterwards.
- A blocked heat trial shows the measured flow temperature beside the existing
  trial window. Automatic heating and persistent settings writes remain disabled.
## Fixed

- Update errors distinguish a failed release check from a failed installation.
  Advanced diagnostics separate HTTP responses from local connection, TLS and
  interrupted-transfer errors. Only the allowlisted download host and numeric
  codes are exposed; signed redirect paths and query strings are excluded.

## Updating

No new HA package is required for these E32 changes.

## Limitations

This release does not prove
that the observed GitHub connection failure is fixed, qualify a physical boiler
trial or enable automatic heating, valve control or persistent boiler writes.
No new retries, firmware installation or test command is performed by the UI.

# E32 V2 beta4 — attended boiler trial and Bluetooth discovery
<!-- user-release-notes:v2:en -->

Beta.4 adds attended boiler commissioning and a larger Bluetooth discovery list.
The earlier beta.3 downloads remain available.

## New

- **Scrollable Bluetooth discovery.** Browse up to 128 received devices, including
  unnamed devices and unsupported profiles. The list shows its count, keeps its
  scroll position during polling and warns when full. The eight saved sensor
  bindings remain separate; discovery does not establish profile support.
- **An attended Ecomline Classic commissioning trial.** Read the boiler settings,
  confirm exclusive ownership and a local stop, then prove a zero-demand baseline.
  Starting heat requires a separate action, an open heat path and a new boiler-gauge
  reading of 1.1–2.5 bar. Demand is bounded to 40–45 °C and at most 60 seconds,
  with a five-second supervision lease and an explicit Stop action.

- **Recover access when all four saved sessions are occupied.** Select the
  recovery option on the login page and enter your username and password again
  to sign other browsers out. Device settings are preserved.
- **A boiler illustration even without a model photo.** A local, unbranded
  illustration appears on Home and My boiler when the selected profile has no
  photo or its photo fails to load. Available model photos retain their credits.
- **Heating settings overview on the EMS devices page.** Four prepared Classic
  settings show their received value, status and age, with a mobile layout.
  Missing or expired readings stay blank. Refresh reads the local snapshot;
  it does not query the boiler.

- **Correct pressure requirements for the target boiler.** The Ecomline trial
  profile explains that this installation has no digital pressure sensor. It
  uses a fresh operator-entered mechanical gauge reading for each heat trial,
  valid for at most two minutes. This remains separate from reported telemetry
  and completed physical installation acceptance.

## Fixed

- Abandoned web sessions expire after 30 minutes without accepted authenticated
  requests, rather than occupying a slot for seven days. Communicating dashboards
  keep access for up to seven days. Late requests cannot revive an expired session.
- Login messages describe saved sessions instead of currently open browsers.
  Ordinary login does not sign other browsers out; recovery requires a separate choice.
- A failed model image falls back to the generic illustration and clears the
  unavailable photo's credit.
- Prepared manual boiler diagnostics only count a bus exchange as completed
  when its acknowledgement finishes within the reply window and the transport
  remains available. Delayed processing cannot turn an old reply into a new one.
- Prepared manual tests and settings readback prevent repeated bus completion
  during nested timing or permission checks. A nested call cannot replace the
  current exchange; exceptions release its guard without retrying completion.
- The prepared settings path guards timing and permission checks as part of
  each send, preventing nested processing from sending the same write or read
  request twice. Exceptions release the guard without retrying the request.

- **Prepared boiler diagnostics:** queued settings-read requests are cancelled
  when the operator logs out or the web session expires or is replaced. An
  already-sent read retains its bounded response window, without confirming a
  cancelled acquisition or retrying automatically. The page labels cancellation
  in English and Dutch, clears earlier setup confirmations and keeps new reads
  blocked until the current request finishes. Late status cannot retract a
  known cancellation for the same request. Pressure confirmation appears only
  for test profiles that require it.

## Updating

Update the E32 through its normal GitHub updater. These
changes require no new HA installation; HA 0.4.0b3 remains unchanged. Verify the
new boot, version and retained settings.

Session recovery is unavailable during a boiler trial, firmware update or
unconfirmed firmware boot. Recovery does not require a factory reset.

## Limitations

Automatic boiler and valve control remain disabled. The only enabled boiler
command path is the attended commissioning trial and its one-shot configuration
read. Persistent boiler settings stay read-only in the standard firmware. The prepared four-setting editor and the
EMS-ESP entity reference do not grant write permission or complete EMS-ESP
write support. The trial does not complete physical installation acceptance; its actual
results and the independent stop still need to be recorded on site.

# E32 V2 beta3 — controls, diagnostics and update recovery
<!-- user-release-notes:v2:en -->

## New

- Alphabetical boiler selection by brand/model and a more extensive EMS devices page with search across devices, entities, telegrams and the EMS reference.
- Search for and add Bluetooth devices while keeping draft input; devices that are already saved are recognised.
- Clearer ESP/EMS system logging and Dutch/English explanations.
- A prepared, bounded one-time boiler configuration read and a separate close-out of manual bus transactions. These routes remain physically blocked; physical transmission stays disabled.

## Fixed

- Bluetooth settings confirm storage only after a matching readback; private keys are not read back.
- The update check retries a failed list check after half an hour. Installation and restart are not repeated automatically. Controls require a fresh status.
- Stricter EMS message checks and decoding, correct product versions and a smaller compressed telegram reference.
- An active boiler trial postpones the background update check.

## Updating

Joint candidate with HA 0.4.0b3. Update through the existing GitHub updater; after the new boot, check the version, source and that settings were kept. Publication alone does not prove installation.

## Limitations

This is a passive beta: physical boiler/valve control and automatic heating remain blocked. The user confirms that their Ecomline Classic HRC 22H has no digital pressure sensor. The current heat-trial guard still requires a digital pressure reading; adapting it to the model and recording a suitable separate pressure check are still open. No made-up pressure reading is added. Transmitter, installation and stop qualification also remain open.

# E32 V2 beta1 — a large bundle for reception, controls and recovery
<!-- user-release-notes:v2:en -->

## New

- **Bluetooth under Settings:** Shelly BLU H&T Display, Xiaomi Monitor 3 and Shelly BLU TRV each have their own local diagnostic profile. Reception runs locally on the E32. The TRV shows its reported target, calculated temperature and any external temperature separately.
- **Hidden keys:** bindkeys are write-only and stay in separate private storage; they are never sent back. Input and open details stay in place while the page refreshes. Explanations and errors are in Dutch and English.
- **Automatic update check:** every twelve hours, with a dashboard notice. A successful check stays available for five minutes; installing remains a separate action.

## Fixed

- Invalid or unknown readings and missing humidity/averages no longer become made-up zero values. Names with quotation marks or line breaks no longer break the room controls or the JSON.
- The older room control pauses cleanly when the device time is missing. The clock request uses an SDK time-out of 100 ms instead of five seconds per room.
- Bluetooth recovers after a failed scan. A full discovery list does not block configured sensors; changing a draft source no longer shows readings of the old source.
- Saving reserves space for control settings and learning models. Running out of memory while loading cleans up and closes the storage. An extreme time jump no longer causes an arithmetic overflow in the warm-up model clock.

## Updating

This is one joint **software candidate**, together with HA 0.4.0b1. For the E32, use only the normal app-only firmware updater with `firmware.bin`; settings and programs are kept. The beta bundle also checks the update path from alpha36 with the real final file (discovery and image compatibility). HA has its own download; the optional receive-only original Zigbee reports come as a separate source package within the same release.

## Limitations

Bluetooth values are diagnostics, not a qualified heating source. Pairing, valve control, standalone control and the physical boiler trial are not released yet; physical boiler/valve control remains unavailable pending its acceptance. All prepared control/learning parts are retained. Source preparation does not constitute a physical test. [Current conditions and progress](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-beta.1/docs/modern-thermostat/WORKBOARD.nl.md) (engineering notes, Dutch).

# E32 V2 alpha37 — unpublished preparation, included in beta1
<!-- user-release-notes:v2:en -->

## New

- **The E32 checks for updates itself:** every twelve hours, starting five minutes after start-up. You still download and install yourself.
- **Update shown on the dashboard:** when a newer compatible version exists, a notice appears with a button to the update page.
- **Faster re-checks:** a successful check is reused for five minutes. The dashboard reads the local status and does not query GitHub itself.

## Fixed

- Prepared Zigbee receivers clean up errors during start and stop better. A restart can no longer let an old and a new receiver run side by side.
- Simultaneous reception can no longer start a duplicate publication. Stopping also waits for the running publication when cleanup fails.
- An automatic update check waits while a boiler trial is active.

## Updating

Update through the E32 firmware update page. Your network, rooms, programs and log settings are kept. Home Assistant dev48 does not need to be reinstalled.

## Limitations

This is a test version. The reception fixes add no new sensor pairing and do not enable boiler or valve control. After a failed automatic check it does not keep retrying; checking by hand remains possible.

# E32 V2 alpha36 — more boiler choices and better logging
<!-- user-release-notes:v2:en -->

## New

- **More boiler choices:** 60 models and model groups under **Settings → My boiler**.
- **Boiler images:** some models show an original image with a source link. The selection also stays available without internet.
- **Clearer system log:** choose only E32 messages, only EMS messages from the boiler, or both.
- **Keep logs longer:** choose separately which E32 and EMS messages you send to your own log server (syslog).
- **About is quicker to reach:** it now sits directly to the right of Settings.

## Fixed

- Saving from an older log page that was still open no longer resets your new log choices.

## Updating

Update through the E32 firmware update page. Your network, rooms and programs are kept. Home Assistant dev48 does not need to be reinstalled for this.

## Limitations

This is a test version. Choosing a boiler model adapts the display; boiler control is not released yet. Not every model has its own picture yet; one is also still missing for the Ecomline Classic HRC22H.

# E32 V2 alpha35 — joint HA48 bundle and sensor preparation

This passive preparation release bundles all earlier features with HA0.4.0.dev48 and the tested Shelly SBHT-103C decoder foundation.

- A pure BTHome v2 parser for temperature, humidity, battery, light and separate identification/button fields. Truncated, duplicate, out-of-order, unknown or invalid objects never yield a partial reading.
- Encrypted frames only yield a key_required format status; no decryption, authentication or readings. Broadcast model information and the packet counter are not a trusted identity or a new acquisition.
- No field cache, dynamic parser allocation or selection by the current BLE reader. Settings/onboarding, device keys, source/replay qualification, Xiaomi Monitor 3 and BLU TRV remain open.
- 798 native tests, 16 separate decoder sanitizer cases and a real ESP32 toolchain syntax check pass locally. Full frozen builds/CI and reviews of the actual packages remain required. The joint HA contains the cleanup fix and the validated clock fixture.
- All 23 prepared parts/31 requirements retained. Existing updater checkpoints, EN/NL explanations and source/session/deadline gates are kept; the product factory, boiler/valve output and EMS TX stay closed.

No claim of an active beta, physical sensor/valve qualification, solved short cycling or a repaired old upload watchdog. Publication is not proof of installation; firmware updates only through a demonstrably reviewed, recoverable route.

English: shared HA48/alpha35 maintenance bundle with a strict passive SBHT-103C decoder foundation. The current BLE reader does not select it; encrypted bytes never become measurements, and model/counter declarations never grant physical freshness or authority. Existing updater, settings and output blocks remain. Pairing, keys, physical tests and recovery are separate gates.

# E32 V2 alpha34 — targeted updater diagnostics and robust HA start-up

Joint bundle with Home Assistant dev47, keeping all 23 prepared parts and 31 product requirements. Passive preparation release; the active beta remains NOT_READY.

- The existing bounded update journal now stores a separate stage before the checksum check, native image validation, independent flash readback and boot selection.
- The existing EN/NL status page makes clear that a saved "before" stage does not prove a completed operation, a successful installation or the cause of a reset. Schema 1 / 164 bytes and the old stage numbers 1–5 are kept; no chunk logging and no new worker/route/retry.
- All verification gates remain mandatory in the same order. An error, exception or callback re-entry never reaches a next transfer or boot selection. 40 updater cases also pass under strict ASan/UBSan.
- HA dev47 closes late-reviving start-up tasks and listeners on shutdown/cancellation and protects against a double start. Program, Store and optional diagnostic boundaries were tested on real native HA runtimes.
- 782 native firmware cases, 24 updater browser cases and 2,349 HA cases per supported Core pass locally. The final exact CI/source/package reviews remain separate release gates.

EMS TX, forwarding and physical outputs remain blocked. Suitable original room readings, a causal valve echo and physical start/stop/failure acceptance remain open. Bluetooth drivers, active PID/learning qualification and other roadmap goals are not presented as complete.

Installation limit: targeted checkpoints provide material for future investigation, not proof of recovery for the earlier installed uploader watchdog or the native HTTPS deviation. Manual uploads are not recorded by this journal. The installation method observed earlier for alpha31 is unknown; this release order performs no blind new upload/reboot/HTTPS trial. HA can be updated separately with a fresh backup and an independent post-check.

English: four bounded persisted pre-operation checkpoints distinguish checksum, image validation, independent flash readback and boot-slot selection. They preserve verification gates and do not imply completion or reset causation. HA dev47 adds single-owner asynchronous startup and bounded optional original-temperature diagnostics. Existing features/settings remain intact. No physical boiler/valve qualification or proven installed-updater recovery is claimed.

# E32 V2 alpha33 — guarded callback boundaries and original reception diagnostics

Joint preparation release with HA dev46; all 23 prepared parts, 31 product requirements and existing settings are kept.

- The final non-blocking transfer check has its own re-entry guard. Availability and the clock also guard their own callback boundary, so the same check cannot be bypassed through ordinary channel admission.
- Nested callbacks permanently revoke all channel owners involved. Availability callbacks cannot create an extra owner. A normal final check inside the existing send callback remains possible.
- Six new channel cases and an additional real local socket test cover the re-entry paths. In that socket test the old code sends a byte; the corrected boundary keeps the same socket empty.
- The included HA46 companion adds bounded original reception counters to the existing HA diagnostics download, without an extra MQTT subscription, worker, storage or device command.
- Earlier original request correlation, one-time grants, the shared clock and original deadlines are kept. Physical product authority stays closed by default.

The firmware chain is prepared, not physically qualified. A suitable original room reading, a causal valve echo, safety producers and physical stop/failure tests remain open. Service acceptance and reception counters are not a physical ACK. Tado stays in control; EMS TX, forwarding and physical output remain blocked. The optional channel route needs at least HA45, the diagnostics download feature HA46.

The earlier uploader watchdog, HTTPS deviation and the cause of the short cycling are not presented as solved. Publishing alpha33 does not prove installation or recovery of the route that failed earlier. No blind firmware retry. Shelly/Xiaomi drivers and full PID/learning qualification remain roadmap work.

English: independent guards at final handoff, availability and shared-clock callback boundaries retire all channel owners on recursion, including reentry from normal admission. A real local socket regression confirms zero-byte refusal. The included HA46 companion adds bounded receive diagnostics without control authority. Product-source/physical feedback qualification and earlier E32 updater recovery remain open; publication is not installation.

# E32 V2 alpha32 — original valve request and guarded socket transfer

A larger joint preparation release with HA dev45. All 23 prepared parts, 31 product requirements and existing settings are kept.

- A complete prepared request/grant/command chain: its own request sequence number, the original local start time, the exact session/config/binding and a one-time grant. A delayed answer gets no new time window.
- Optional channel wiring on the same MQTT client and loop. At most eight owners; callback re-entry, a SOURCE change and a disconnect revoke without rebuilding or automatic retry. This does not qualify an eight-zone installation.
- One shared monotonic clock watermark and a permanently lower deadline ceiling, also at context and socket boundaries. The current local network state counts when TCP still seems connected.
- Only during the explicit actuator publish does the same socket use a non-blocking write without SDK wait/retry. Partial, late or failed IO first revokes all owners and closes the existing socket without an extra MQTT write. Ordinary shadow traffic keeps its SDK path.
- Native core, real C++/HA worker exchange, strict sanitizer/iterator checks and four real local socket tests; exact source/tag CI and package checks remain publication conditions.

The product SOURCE factory stays closed. This package grants no valve/boiler authority, physical ACK, delivery path or proven stop guarantee. Tado stays in control. A suitable original room reading, a causal valve echo, safety producers and physical qualification remain open. The new request route needs the matching HA dev45.

The earlier alpha28 uploader watchdog and the native HTTPS error are not claimed as solved. Publishing alpha32 does not prove installation; no blind upload retry. Shelly/Xiaomi drivers and active PID/learning qualification remain roadmap work.

English: combined preparation release with HA dev45: correlated original requests, single-use grants, bounded channel ownership, a shared lifetime clock and nonblocking writes on the existing MQTT socket. Partial/late/failed IO is never retried. Default product authority remains denied; physical feedback/stop qualification and E32 update recovery remain open.

# E32 V2 alpha31 — joint M2 source, session and transport bundle

Joint passive prerelease with Home Assistant dev44. Keeps all 23 prepared parts and existing settings; not an active boiler beta.

- A prepared C++ valve encoder and send check guard the exact source/session/config/binding, the original request deadline and the current lease. Shorter deadlines can never grow again later; an uncertain transfer gets no automatic retry.
- The real local controller supplies a bounded session context without renewing rights or granting physical authority. Memory errors and revocation close the owner permanently.
- HA dev44 connects grant requests and commands to the existing native worker and also guards against loss of scope or going offline before the queue. Service acceptance remains no valve ACK.
- Strict sanitizer gates and real C++→HA interoperability check the prepared chain; all earlier diagnostics, EMS, UI, source-selection and upload checks are kept.

The product factory selects no physical valve owner. Firmware MQTT send wiring, a suitable room source, a causal original valve echo, installation qualification and physical stop/failure tests remain open. EMS TX, forwarding and physical outputs remain blocked; Tado stays in control. New Shelly/Xiaomi Bluetooth drivers are not marked as ready.

Installation limit: the earlier upload through the installed alpha28 caused a task watchdog reset whose task/cause is still unknown. Alpha31 does not prove recovery of that running uploader. No blind OTA retry; keep settings and first establish a well-founded recovery route. The earlier short cycling and the native HTTPS updater error are not claimed as solved.

English: combined passive prerelease with HA dev44, preserving prepared features and configuration. Adds source/session/deadline fences and native-worker actuator message handling with default-denied physical authority. No active boiler qualification, original valve ACK, new Bluetooth drivers or proven alpha28 uploader recovery. Do not blindly retry the failed installed upload route.

# E32 V2 alpha30 — boiler reports, safety facts and upload checks

Joint passive maintenance bundle with Home Assistant dev39; all previously prepared features are kept.

- Boiler values follow the original reception order per field. Older telegrams do not overwrite newer values; conflicting values from the same acquisition stay unusable until a new reading.
- Safety and hydraulic facts do not revive through repetition, the clock running backwards or the expiry of an earlier invalid future time. A valid acquisition at uptime zero remains supported.
- A manual app upload checks the exact file size, an interrupted transfer and complete multipart handling before the boot partition is selected. Native OTA handles are closed once.
- HA permanently withdraws boiler values that became invalid until new original reception, also after a transport error or an update of another field group.

Checked locally: 689 firmware tests, 11 REST upload scenarios and 2195 HA test cases per Core 2026.10.2/2026.10.3. The mandatory release CI checks the frozen source and packages separately.

Installation limit: the earlier alpha29 upload ended on the installed alpha28 with a task watchdog reset; the cause is unknown. These source changes do not prove recovery of that uploader, which was already running. No blind OTA retry; installation needs a well-founded recovery route and a check of the real boot identity.

EMS TX, forwarding and physical outputs remain blocked. The active beta, physical start/stop tests and the new Shelly/Xiaomi Bluetooth drivers remain open. Short cycling and the native HTTPS updater are not marked as solved.

English: passive combined maintenance release with ordered boiler field acquisition, persistent retirement of rejected safety facts and HA cached values, and transactional manual upload validation. Existing alpha28 upload watchdog recovery remains unproven; no automatic retry or active heating qualification.

[Current workboard (Dutch)](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-alpha.30/docs/modern-thermostat/WORKBOARD.nl.md).

# E32 V2 alpha29 — joint diagnostics and maintenance bundle

Bundles all prepared software with Home Assistant dev38 at source
`d131c503f42e6b834a0815db8384983a7fc1b46f`.

- TV02 reception diagnostics recover when MQTT metadata becomes available late.
- Original sensor diagnostics are withdrawn when the native device identity is changed or disabled; old information does not revive.
- Clear EN/NL reception messages; frontend v38 keeps existing v35 cards.
- All 23 prepared parts are kept. No changes to settings or the storage layout.

Passive maintenance release: EMS TX, forwarding and physical boiler/valve output remain blocked. The active beta, Shelly/Xiaomi Bluetooth drivers and physical stop/failure tests are not ready yet. The earlier short cycling and the native HTTPS updater deviation are not marked as solved.

All seven software gates passed; 2189 HA test cases per supported Core version, without failures/skips. Install only the matching app-only firmware file through the existing recoverable route; keep settings and check the real boot identity.

English: combined passive maintenance bundle with HA dev38. Fixes diagnostic source lifetime/startup and preserves older room cards. No active heating or Bluetooth device support is enabled.

[Changes and remaining conditions in the source](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-alpha.29/docs/modern-thermostat/WORKBOARD.nl.md) (Dutch). The separate history file in this source contains the earlier release history.

# E32 V2 alpha28 + Home Assistant dev37 — stable controls and EMS devices

Joint passive prerelease with all tested fixes since alpha27/dev36.

- Settings → EMS devices shows the senders actually received, product/version where known, and entities with quality/age. Dutch/English, the search filter and the expanded state are kept when refreshing. No active scan.
- Expired E32 and HA session rights do not revive after the clock runs backwards. With an invalid monotonic clock, HA withdraws the session and waiting commands; recovery requires a new transport instance.
- After waiting, every HA retry re-checks the time, lease, SOURCE and the original queue registration. No old command after revocation or replacement; the original bytes and deadlines are kept.
- HA start-up and cancellation clean up their own resources without removing a replacement owner. Oversized numeric valve metadata no longer crashes the editor.
- Delayed web responses can no longer overwrite a newer page or run old scripts. The EMS table reuses rows and checks values and order.
- The current plan separates installed, prepared and physical acceptance; the future stop/send/failure test is described concretely.

Partitions and settings format stay the same. The E32 installation is app-only; HA has a separate package. Existing settings, programs, SOURCE/journal, registry and reception producer are kept. Frontend dev35/v35 stays the same version with the same bytes.

EMS TX, the forwarder and physical valve/boiler output remain blocked; Tado stays the active controller. The normal M2 valve send route, a suitable room source and physical stop/failure qualification are still open. The earlier short cycling and the native HTTPS updater deviation are not claimed as repaired. No blind retry of that HTTPS route.

**English:** Combined passive maintenance release: EMS device inventory under Settings with EN/NL display, stable filtering/expanded rows, monotonic session fences, current-owner/deadline checks after awaited MQTT sends, reliable HA setup cleanup, metadata validation and stale-navigation protection. Configuration is preserved; boiler/valve transmission remains disabled. No active heating qualification or claimed cycling/HTTPS-updater repair.

# E32 V2 alpha27 + Home Assistant dev35 — bundled failsafe and controls

Bundles all prepared changes since alpha26/dev34 in one passive prerelease.

- HA heartbeat and a bounded run-on after a lost connection; unusable or outdated source readings cannot become valid again through repeated processing.
- Stricter hydraulic feedback: invalid partial evidence loses its validity; limiting error signals are kept. A clock running backwards blocks positive release.
- Bounded boiler trials guard stop confirmations and ask for new evidence after expired or conflicting feedback.
- Persistent, bounded updater checkpoints support future fault diagnosis. This does not show that the earlier HTTPS update error is solved.
- Logging processes complete validated pages; uncertain storage blocks an automatic retry. Boiler settings are read back independently after saving.
- EN/NL controls and HA frontend dev35/v35, with clearer outdated TV02 reception and prepared command checks.

All inventoried prepared features are included. Partitions and settings format stay the same; the firmware installation is app-only. Existing configuration, programs, SOURCE and reception pins are kept. The normal valve send route and physical acceptance are still open. EMS TX, the forwarder and physical outputs remain blocked, Tado stays in control. No automatic send test or release for active boiler control.

# E32 V2 alpha26 — ESP diagnostics and clear settings

Restores the ESP's own diagnostics in native MQTT mode, together with HA dev33.
All existing prepared features from alpha24 and the HA fixes are kept.

- Free/minimum free internal heap, the largest free memory block, CPU temperature and uptime are sent every 15 seconds over the same MQTT connection. The disabled RTC temperature stays unknown.
- HA dev33 keeps the existing diagnostic identities and withdraws availability after 45 seconds without a valid reading. An HA restart does not require an E32 restart.
- The E32 settings and dashboard explain shadow mode in English and Dutch: reading data and calculating heat demand, without valve or boiler commands. EMS reception and the installation profile are no release for physical control.
- HA dev33 explains configuration confirmation, valve target checks and calculations separately. Reliable source readings, confirmed commands and safe stop behaviour still have to be signed off separately.

The normal HTTPS update stays app-only with the same partitions and settings.
Home Assistant remains a separate package; the existing dev28/v28 room card stays the same.
Boiler reception stays passive, Tado stays in control and all physical outputs remain blocked.

# E32 V2 alpha24 + Home Assistant dev30 — bundled control and reception foundation

Bundles all prepared changes since alpha23/dev29 in one joint passive
candidate. This is not an active boiler beta or a release of physical output.

- Bounded boiler trials guard late base/stop confirmations and keep their
  original deadline on lease loss or a phase change.
- The shadow controller is linked to the hydraulic supervisor with separate
  source ages and boot/owner/session binding. An error does not resume by itself.
  The concrete production sources stay unconfigured by default.
- Log redaction also protects format codes and long lines before both log sinks.
  The EMS encoder refuses oversized frames and invalid READ payloads.
- HA dev30 adds read-only supervisor diagnostics, a stricter lifetime for waiting
  valve targets and private installation pins for original TV02 reception.
  Uncertain dispatched valve actions get no automatic follow-up command.
- The Ecomline profile keeps the current passive field review and a separate
  Recorder observation. Three varying temperature fields are candidates for
  further validation; no claim of a calibrated reading or six hours of continuous evidence.
- The installation runbook covers backup, version compatibility, source pins,
  a separate Z2M producer installation, reception acceptance and a limited fallback.

Existing dashboard refresh, logging/syslog, EN/NL controls, model selection,
69 boiler field definitions, the week planner and settings are all included.
Settings format and partition layout stay the same; the normal HTTPS update
is app-only. HA remains a separate package with the same dev28/v28 frontend bytes.

The public source lists stay empty. Installing a private file or extension
grants no measurement/flow/valve/control qualification. The update changes no
sensor, valve mode, program, SOURCE owner or syslog destination. EMS TX, the
forwarder and physical outputs remain blocked; Tado stays the active controller.

# E32 V2 alpha23 + Home Assistant dev29 — logging and stable controls

Alpha22 remained an unpublished candidate: the public native logger test
needed an explicit cstdint header for the vendor compilation. That test build
is fixed; the existing tag is kept.

Joint passive test release with all prepared changes since alpha21/dev27.
No release for active boiler or valve control.

- E32: system log in Settings, with levels, a module filter, pause, download
  and local clearing. Bounded RAM storage; no log archive in flash.
- E32: an optional RFC5424 UDP syslog server with IPv4 address, port, its own
  level and markers. Settings are applied only after an NVS readback.
  External logging is off by default; destination and reception are set up and
  checked locally. See LOGGING.nl.md.
- E32 dashboard: readings refresh without rebuilding open details, keyboard focus,
  scroll position or the boiler illustration. Status requests do not
  overlap; connection errors keep the page in place with a message.
- HA dev29: original TV02 data point reception through the existing native MQTT
  lifecycle, with explicit source pins, age and identity checks.
  The room page shows available original reports in English or Dutch,
  including the reported target, the valve's own temperature, program, heating
  stop and frost protection. Reception does not prove a command confirmation,
  valve position or delivered heat. The default source pins stay empty: without a
  separately reviewed source and extension, no original reports appear.
- The HA editor gets its own dev28/v28 identity so an old browser card cannot
  overwrite the new view. Old manual cards stay compatible. No new polling
  or automatic valve commands.

The app-only HTTPS update uses the same partition layout and keeps existing
settings. HA is a separate package; the firmware does not install it.
Earlier boiler profiles, model-independent reception, 69 prepared field definitions,
EN/NL controls and the configuration/program structures are kept.

Physical source/valve/send interface/start-stop qualification remains open. E32 EMS TX,
the forwarder and physical outputs remain blocked at compile time. This release
changes no measurement selection, week program, SOURCE ownership or syslog destination.

# E32 V2 alpha21 — Nefit Ecomline Classic HRC 22H profile

Settings → My boiler now includes the separate profile Nefit Ecomline Classic
HRC 22H, the exact model confirmed by the user. Home shows the full
name and the existing family illustration. The older generic Classic choice
is kept and stays valid. Saving and the original NVS readback are tested for
both identities; the save message follows English/Dutch.

The source profile keeps the observed reported candidate fields, with derived
activity listed separately and usability not yet physically proven. A model
choice never limits EMS reception and selects no bus addresses, limits or
send mode. All earlier readout, language and interface fixes are kept.
E32 TX and physical outputs remain blocked; no release of the active boiler beta.

# E32 V2 alpha20 — full passive measurement release with HA dev26

Bundles all alpha19 preparation: native Classic boiler fields, EN/NL controls,
boiler profile and diagnostics. HA dev26 also restores the existing v2 sensors
in the product installation through the validated native MQTT cache. A missing
standard header in the native BLE test was added explicitly for a clean
CI build. Alpha19 was not installed live; historical tags are kept.

The normal app-only update keeps settings and the same partition layout.
EMS TX and physical outputs remain blocked. No release of the active boiler beta.

# E32 V2 alpha19 — boiler fields to HA and bilingual controls

Joint passive update with HA dev25. The existing native MQTT connection
now publishes all 69 prepared Classic field definitions with the original
report age, quality and units. This makes valid received boiler fields
visible in HA; values that were not received, expired or are unreliable are not
presented as a working reading. A model choice never limits reception.
This decoder coverage is not a maximum for other EMS boilers.

Included: English/Dutch with a remembered E32 browser choice, completed HA
translations, My boiler with a local illustration, extended message diagnostics and
all earlier prepared fixes. The ordinary app-only HTTPS update keeps the
network, SOURCE, rooms and programs and uses the same partition layout.

E32 sending and physical boiler/valve outputs remain blocked. This is a
bundled readout update, not a release of the active boiler beta. The real
measurement producer, valve, send interface and stop acceptance remain separate.

# E32 V2 alpha18 — joint reception and diagnostics release

This release bundles the prepared source changes with HA dev24. Settings → Boiler test shows reception diagnostics, age and available boiler values and offers a downloadable report. Original UART reception times are kept. The bounded trial policy, shared poll route, Classic encoder and SDK send checks are included as blocked preparation.

E32 EMS sending and additional GPIO outputs remain blocked at compile time. The trial controls grant no release for heating. A real measurement report producer, physical valve acceptance, the send interface and independent stop behaviour remain open. This release is meant for the next passive field check, not as a finished active boiler beta.

Normal app-only HTTPS update, keeping settings and the same partition layout. All earlier update, web, About, dashboard and session improvements are kept.

# E32 V2 alpha17 — bundled update and web improvements

This release belongs to the joint test batch with Home Assistant dev23.

- The automatic updater finds the recent alpha releases through a bounded tag index, then checks the real public release, assets, the compatible manifest and the source commit. Annotated tags are resolved only when needed. The existing catalogue route remains available as a fallback.
- Built-in web files get an explicit GET route with the existing authentication. This removes the misleading serial message `request handler not found` for web pages and files that are delivered correctly; real unknown routes stay a 404.
- The dashboard can show the actual room names from the admitted HA session, including UTF-8. The labels are bounded and change no saved control plan, measurement evidence or output authority.
- The internal/PSRAM memory diagnostics delivered in alpha16 and the earlier HTTPS memory fixes are kept.

App-only update through the normal HTTPS updater; existing settings and partition layout are kept. Test release for the BBQKees E32 V2 with a dual-app/SPIFFS layout. No factory erase or filesystem upload needed. The E32 output blocks and the existing separate physical acceptance conditions still apply.

# E32 V2 alpha16 — reading memory during normal device management

The existing status route now reports free memory, the SDK minimum counters and the largest free memory block separately for internal RAM and PSRAM. This information therefore stays available in HA-managed operation, where the old MQTT device reporter is deliberately not started. This adds no second MQTT client or controller.

The counters are readouts of the pinned SDK. According to the SDK, the minimum counters apply since boot; they are not a separate 72-hour or hard real-time qualification. HTTP response times were measured separately on the existing device as a network baseline; no speed gain is claimed.

The native CI now logs test names and a stack trace when a wait takes long, with the same time limit and unchanged release gates. The included HA source is dev22; the firmware installs no HA component.

# E32 V2 alpha15 — navigation, About and release management

Sign out sits on the right of the top bar, also on mobile. Restart device sits at the bottom of Settings and keeps its confirmation. About describes OpenThermostat and Mark Dielessen as the developer, with the original author and library credits in an expandable part.

The working HTTPS updater from alpha14 is kept. After publication, current downloads and archive labels are updated automatically. The included HA source equals dev20; this firmware update installs no HA component.

This is an experimental firmware update that keeps existing settings. Hardware and long-term acceptance remain open separately.

# E32 V2 alpha.14 — explicit inactive-task allocator guard

The scoped TLS allocator now explicitly requires a registered, non-null updater
task before querying or matching the current task. Outside an active updater,
the original SDK allocator is always used, including early initialization.
This small follow-up also supplies a subsequent normal app release for actual
alpha.13 in-device HTTPS download/install verification. No live verification
is assumed by these notes. The TLS-memory fix and all restrictions below remain.

# E32 V2 alpha.13 — external memory for verified HTTPS updates

The real updater trace reports FFFFBD70 (-0x4290). The pinned mbedTLS source
combines RSA_PUBLIC_FAILED (-0x4280) and MPI_ALLOC_FAILED (-0x0010): memory
allocation failed during certificate signature verification. This is not
proof of an untrusted root. The pinned SDK reserves internal RAM for TLS.

Only the temporary HTTPS updater task now requests its TLS allocations from
PSRAM, following the SDK external-memory allocation policy. A scoped linker
wrapper selects that task; all other tasks retain the original SDK allocator.
The SDK free function supports both heaps. No global allocator or SDK binary
is replaced. A changed SDK memory configuration fails the build for review.
External allocation failure stops the connection; it never consumes internal
heap as fallback. Response buffers are also explicitly bounded in PSRAM,
and converted to JSON text only after TLS teardown. The older default malloc
could already place large buffers externally; that change alone was not
accepted as a fix. Alpha.12 was an unpublished intermediate candidate.

Certificate/hostname verification, approved redirects, release/manifest checks,
image SHA, native image validation, flash readback, previous valid slot and
normal boot confirmation remain required. Settings, filesystem and partitions
are unchanged; physical heating outputs remain blocked. Keep EMS disconnected.

Native tests and complete release CI are required. Actual board HTTPS discovery
and a subsequent verified in-device update must still establish physical
acceptance; this release does not assume success from compilation alone.
Use only firmware.bin for app-only updates; do not erase or upload SPIFFS or
the factory image. Retain existing settings and programs.

# E32 V2 v0.1.0-e32v2-alpha.11 — test candidate

The update catalogue checks all up to twelve release messages before
it offers the two most recently published matching firmware versions. The real
GitHub list placed alpha.10 after 9, 8 and 7; previously the check already stopped at 9 and 8.
The publication time is used only as a valid UTC date. Per release, the
fixed hosts, matching manifests and all existing download/image/readback
checks remain required. An error later in the scan yields no partial admission.
The included HA source contains the separately released dev17 fix.

The admission diagnostics of alpha.10 remain; there is no automatic
command retry or loosening of grants, replay checks or physical outputs.
The earlier 22 °C rejection is not explained yet. The alpha.10 HTTP upload was
interrupted; a real readback confirmed alpha.9 with unchanged configuration.
That failure is not solved by this catalogue fix. The settings format,
partitions, physical conditions and open recovery acceptance are kept.

# E32 V2 alpha.10 — bounded command-admission diagnostics

Experimental bench-test candidate. The normal HA connection/configuration path
is live-verified, while a subsequent 22°C command was rejected. Its precise
admission reason has not yet been established; this release adds observations,
without changing admission rules or enabling heating.

- Rejected envelope acknowledgements include a static `rejection_reason` from
  the existing admission decision. No grant token, private setting or secret hash
  is added to diagnostics.
- The existing authenticated state snapshot optionally includes the most recent
  user-command admission: binding, sequence, received revision/time and outcome.
  This bounded RAM record clears when the session/owner is invalidated. It is
  neither an execution receipt nor a measurement timestamp or durable state.
- Expired grants, changed duplicates and other rejected commands still cannot
  execute. Diagnostics never retry a command, refresh a grant or change a
  watermark. Qualified measurements, hydraulic commissioning and physical output
  rights remain separate and unchanged.
- Settings/update schemas and partitions are unchanged. Current HA16 sources
  accompany this firmware source commit; no HA installation is performed by OTA.

Use the immutable CI app-only release with current configuration/source/plan
before-and-after checks. Cold/power-loss/USB recovery and physical acceptance
remain open. The earlier live command failure is not declared fixed by adding
its diagnostic field.

# E32 V2 alpha.9 — conditional device settings for Home Assistant linking

Experimental bench-test candidate. Physical boiler/TRV/GPIO authority is unchanged.

- Authenticated device-settings reads return an opaque random ETag associated
  with this boot, browser session and the complete saved settings. The private
  settings digest stays on the controller; broker/weather secret hashes are not
  exposed as ETags.
- A settings POST with `If-Match` is rejected with HTTP412 before merging or
  saving if another edit changed the settings or the session/readback expired.
  Unquoted, weak, wildcard, combined and other-session tags are rejected. Existing
  local forms remain compatible; cookie, origin, CSRF and update guards remain.
- This is the firmware prerequisite for the normal Home Assistant connection
  step under development. It does not itself install that integration flow,
  select a room profile, validate measurements or enable heating.

Use the immutable CI release assets, app-only with private before/after snapshots.
Cold/power-loss/USB recovery and physical room/boiler acceptance remain separate.

# E32 V2 alpha.8 — bounded OTA upload headers and updater stack

Experimental bench-test candidate. Keep EMS disconnected; physical outputs remain
blocked until the existing commissioning checks pass.

- Authenticated multipart app/filesystem uploads no longer append three security
  headers for every chunk. The final response emits them once; cookie, origin,
  CSRF and updater-busy checks still run for each chunk and the final route.
- Flash SHA readback uses a separate non-inlined 1 KiB scratch frame, keeping its
  buffer out of the updater's TLS/download frame. Exact image length, board marker,
  streamed SHA, native validation, whole-image flash SHA and boot selection remain
  required. This bounds stack use; it does not establish the cause of the earlier
  alpha.6 manifest-stage reset.
- Alpha.7 was installed app-only on the development E32 and its published
  source/UI/ELF identities, confirmed boot and saved settings/program were verified.
  Its GitHub install attempt had reset to idle; local upload installed it but
  exposed the duplicate headers. These observations are not acceptance of alpha.8
  or proof of cold recovery, physical TRV operation or boiler heating.

Publish only through the existing full CI/release pipeline. Upload only the exact
published `firmware.bin`; preserve filesystem/settings and the previous valid slot.

# E32 V2 alpha.7 — controller status and separate firmware release discovery

Experimental bench-test candidate. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This candidate is not approved for heating.**

- Authenticated controller status distinguishes compiled graph/controller
  contracts and limits from the active configuration and physical permissions.
  A compiled capability does not enable runtime control or certify a device.
- The managed web interface presents controller status without requiring a
  restart for ordinary display refreshes. The complete heating dashboard and
  end-to-end HA→E32→acknowledgement/TRV acceptance remain follow-up work.
- Firmware discovery searches up to twelve bounded GitHub release pages for
  at most two compatible E32 app releases. Home Assistant releases, drafts,
  missing firmware assets and incompatible manifests are skipped. A transport
  failure preserves the previous list. The image, board/layout, hash/readback
  and boot-selection checks are unchanged.
- Home Assistant integration packages have separate `ha-v…` releases. Installing
  an HA ZIP does not update this firmware or enable physical heating control.
- The complete release kit supplies pinned vendor source/notice archives,
  exact application source and objects, an offline relink recipe, and evidence
  that both original and deliberately modified Arduino libraries link. Required
  CI independently reproduces all 629 reviewed open SDK/runtime compilation
  units. The vendor binary-only archives retain their original provenance and
  notices; this is a target-specific distribution check.

## Candidate and update status

Release downloads are produced from the same clean source commit as their
firmware and embedded UI identity. Publication requires the current source,
relink and SDK reproduction evidence and all build/package checks. Source-only
`sources-e32v2-…` releases are not firmware updates. These notes do not claim
physical installation or acceptance.

After a verified firmware release is published, use the existing device updater
or upload only its `firmware.bin`. The web interface is embedded in the app.
**Do not erase flash, install the factory image or upload SPIFFS for this update.**
Preserve a private settings backup and the previous immutable alpha.6 release.
Verify firmware/source/UI identity, settings, network health and recovery after
installation. Software and simulated-browser checks do not prove physical
update/recovery behavior or qualify the bathroom sensor/TRV control chain.
