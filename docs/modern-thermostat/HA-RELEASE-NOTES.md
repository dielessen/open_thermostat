# HA 0.4.0b10 — one place for rooms, a clean dashboard and far fewer entities
<!-- user-release-notes:v2:en -->

Companion release for E32 beta18. Install both together.

## New

- **Rooms are set up in Home Assistant**: Settings → Devices & services →
  OpenThermostat → Configure → Rooms. Add, change or remove rooms, choose their
  temperature sources from your Home Assistant entities and the E32's
  Bluetooth sensors, the target, limits and a simple week program such as
  `mon-fri: 06:30 20.5, 22:30 19`. The plan is stored on the E32, so heating
  keeps running without Home Assistant.
- **°F and °C**: with Home Assistant in °F the room editor shows and accepts
  °F; sources in °F or K are converted to °C for the E32.
- **Flow temperature limits** (Configure → Rooms): the lowest and highest flow
  the E32 may ask for, with a warning for floor heating above 50 °C and above
  the boiler's own maximum heating temperature, which always stays the
  ceiling.
- **Heating dashboard**: per room the temperature, target, mode and "off
  until"; the E32 boiler request next to your thermostat's; boiler essentials;
  Bluetooth sensors; heating advice; and a short "How it works" card. English
  or Dutch.
- **Each E32 room and Bluetooth sensor is its own device**, with plain names
  ("Temperature", "Heat demand"). Existing entity IDs and history stay.
- **Shadow comparison sensors**: heating time and burner starts today for the
  E32 and the thermostat, and their agreement. They appear only once a
  thermostat to compare with is seen on the boiler bus.
- **Burner short cycling** warning and burner starts in the last hour.
- **Heating problem**: one yes/no sensor for "is my heating OK?", on only for
  real problems held long enough (a room without measurement for 30 minutes,
  no E32 report for 10 minutes, low or high water pressure, short cycling for
  2 hours). Its attributes list the reasons for your own notifications.
- **Heating advice** sensor (advice only, never changes a setting): short
  cycling, a maximum heating temperature far above what the house needs, a
  return too warm for condensing, the flow your rooms really need, night
  setback, hot-water temperature, water pressure. Each item says what was
  seen, why it matters, what to change and where, with its confidence.
- **Energy and outdoor temperature** (Configure → Energy and outdoor
  temperature): optionally a gas meter (m³ or kWh), a gas price sensor or fixed
  price, the calorific value, an outdoor temperature sensor or weather entity,
  and your boiler power. Without them the advice still works, with rougher
  estimates.
- **Learning per room**: learning status, recommended flow and predicted
  heating start from the E32, plus hot water today.
- Week programs compiled by Home Assistant accept any IANA time zone.
- The E32 address may be a local host name such as `e32.fritz.box`,
  `e32.home.arpa`, `e32.local` or `e32.lan`, as long as it resolves to a local
  address.
- When the E32 password changes, Home Assistant asks for the new one; a
  Repairs notice appears while the E32 still uses the default password.
- Every setup step and field explains in plain language what it does; all
  boiler values have English and Dutch names; icons for all entities.

## Fixed

- Far fewer entities: boiler values are created only once the boiler really
  reports them, and old duplicate or never-reported entities of this
  integration are removed (history is kept; entities you renamed or changed
  stay).
- Only one room menu is shown when the E32 has a room plan.
- Removing a room also removes its device and entities.
- Heating status with a flow request above 60 °C is accepted (up to 80 °C).

## Updating

Install the matching integration package, keep existing entries and restart
HA. Use it with E32 beta18. Entities of other integrations (for example old
EMS-ESP or MQTT devices) are never removed automatically.

## Limitations

The heat request is shadow-only; the advice is advice only. EMS Classic boilers
only; EMS+ is planned. E32 beta18 accepts a maximum flow up to 80 °C, never
above the boiler's own maximum heating temperature. The old HA room records
still exist for existing installations; the E32 heating control uses the E32
room plan.

# HA 0.4.0b9 — E32 rooms and Bluetooth sensors, firmware updates and the heat request
<!-- user-release-notes:v2:en -->

Companion release for E32 beta17. Install both together. HA0.4.0b8 was not
published; its changes are part of this release.

## New

- **Rooms from the E32 in Home Assistant**: per room the measured temperature,
  the active setpoint, the control status with its leading source, and the
  heat demand.
- **Operate rooms from Home Assistant**: room state (active or inactive),
  "inactive until" and the fallback setpoint. HA writes the E32 room plan with
  its revision; when the E32 page changed it in between, HA reads it again and
  applies just your change.
- **Bluetooth sensors of the E32** appear as temperature, humidity and battery
  sensors. They stay paired on the E32, so heating keeps working without HA.
- **E32 firmware updates in Home Assistant**, like ESPHome: an update entity
  checks GitHub every six hours, verifies the download and uploads it to the
  E32 over the local network, then confirms the new version.
- **Heat request** sensor: the flow temperature the E32 calculates (0 when it
  does not ask for heat). In beta17 the E32 only reports it (shadow mode).
- HA forwards the entities the E32 rooms read (for example the tado) to the
  E32, on every change and every five minutes.
- One table for all EMS entities: the thermostat, maintenance and EMS+ values
  arrive over the boiler-fields route and appear as entities.

## Fixed

- The room editor keeps its open advanced and comfort sections when it redraws.
- Unloading a product entry now also unloads its update entity.

## Updating

Install the matching integration package, keep existing entries, storage and
resources, validate the configuration and restart HA. Use it with E32 beta17.
Room operation needs the controller address and password of the connection
step.

## Limitations

The heat request is shadow-only. New rooms and their sources are added on the
E32 page "Rooms and heating"; the HA room editor for TRV rooms is not used by
the E32 heating control yet.

# HA 0.4.0b7 — requested boiler temperature over native MQTT, tidier entities
<!-- user-release-notes:v2:en -->

Companion release for E32 beta10.

## New

- Read **E32 requested flow temperature** from the native firmware topic
  `v1/fw/telemetry/controller_request`, using native availability. A live
  packet also proves the board is online after an HA-only restart.
- Hide boiler fields this boiler never reports: after15 minutes of a valid
  observed-field stream, unreported fields are disabled by the integration.
  Fields that are unreliable by default, or that you disabled yourself, are
  left alone. A field that appears later is enabled again; HA then reloads the
  integration.

## Fixed

- The requested-temperature entity now appears with modern-mode firmware.
  HA0.4.0b6 subscribed to a legacy topic that such firmware never sends.
- A repeated request with the same value (for example50°C every minute) now
  updates the entity's age and sequence instead of looking frozen.
- Legacy hub entities that a modern-mode E32 never feeds (DHW status, boiler
  states, hub connection, RTC temperature) are disabled instead of staying
  unavailable forever. Records are disabled, not deleted, so history is kept.

## Updating

Install the matching integration package, keep existing entries, storage and
resources, validate the configuration and restart HA. Use it with E32 beta10;
older firmware does not publish the native controller-request topic.

## Limitations

The requested temperature is our transmitted command, not boiler readback.
Room temperature source qualification is unchanged, and physical room control
is not accepted. No boiler, valve or setting writes are added.

# HA 0.4.0b6 — requested boiler temperature and plan recovery
<!-- user-release-notes:v2:en -->

Companion correction for E32 beta.8 and beta.9. Native plan recovery also supports beta.6.
The command record was introduced in unpublished candidate beta.7 and is delivered
in beta.8; the HA0.4.0b6 integration source remains frozen at6dbe42f.

## New

- Add read-only **E32 requested flow temperature** for the advertised Ecomline
  trial command record. Preserve every boiler-reported temperature entity.
- Unknown before the first transmission and after a new firmware boot;50C after
  an emitted50C request,0C after an emitted Stop. Attributes identify controller
  origin, original completion time and command age. No measurement statistics
  or restored command value is supplied.
- Reuse the existing EMS status subscription, without extra HTTP polling or
  command publication. Duplicate snapshots keep their original age; retained,
  malformed and reordered packets do not supply a temperature. Offline/expired
  status becomes unavailable.

## Fixed

- Expose **Review or recover room plan** for a running native plan connection.
  A retained staged plan could previously leave the bathroom climate unavailable
  while the recovery handler was missing from every product menu.
- Reuse the existing prepare/review/apply worker, current candidate/session/Store
  checks, separate confirmation and exact E32 readback. Merely reading the menu
  or status does not apply a plan or grant physical control.
- Advanced diagnostics now exposes applied-plan status. Inactive/disconnected
  installations do not show the native plan actions.
- Correct the old connected-menu test helper. CI rejected unpublished0.4.0b5
  because its helper still expected the old menu; that candidate was not installed.

## Updating

Install the matching integration package, preserve existing entry/storage and
resources, validate configuration and restart HA. A normal explicit plan review
resolves the pre-existing accepted6/staged7 horizon recovery; no storage rewrite.
E32 beta.8 supplies the command record. Existing beta.4/6 firmware keeps its other
entities and can use the recovered plan menu.

## Limitations

This is a controller-command history value, not boiler acknowledgement or an
independent water-temperature measurement. It does not replace a boiler's own
selected-flow report. Physical installation acceptance and the complete new
attended50C/600s trial remain open. Automatic boiler/valve outputs stay disabled.

# HA 0.4.0b5 — unpublished recovery candidate

Tagged24fd54b; exact-tag CI rejected an old connected-menu test expectation.
No public package or active installation was made from that candidate.

# HA 0.4.0b4 — integrated room and installation controls
<!-- user-release-notes:v2:en -->

Experimental coordinated release for E32 beta.6. Installation is verified separately.

## New

- Edit the installation name and shared water limits while connected to the E32.
  Linked radiators follow the limits; custom circuit limits are preserved and
  stored curve points stay bounded. Water-limit changes use the normal verified
  apply route and may restart the E32. Name/dashboard changes do not write device
  settings. Unsupported weather controls are omitted from this connected form.

- Show native cached battery percentages and device low-battery flags for the
  saved room sensor and valves under Advanced settings. Reports retain their HA
  timestamp/age, shared devices appear once, and missing or ambiguous sources
  stay unknown. Reload explicitly refreshes the snapshot; no extra subscriptions
  or duplicate entities are created. [Scope](DEVICE-BATTERY-SNAPSHOT.md).

- Select up to eight window and door contacts in the normal room editor or room
  setup wizard. Configure opening/resume delays and maximum report age.
- Contact status distinguishes open, closed, waiting and unavailable/expired
  reports. Re-reading a page does not renew a report. Only explicitly selected
  contacts affect a room.
- Add or remove contacts on an active native plan through the existing save,
  reload and verified controller readback. Older firmware without the contact
  contract is rejected before saving the new active-room intent.
- Bind a built-in Home Assistant temperature Number helper as an extra manual
  room control. A new authenticated user change requests one temporary target
  for one minute to twelve hours; startup values and automations do not apply it.
  The normal programme resumes when the controller's override expires. The
  helper is not written back, and status updates add no polling.
- Configure room comfort modes, away target, temporary duration and an optional
  person in the normal editor or setup wizard. Native person reports retain the
  selected tracker's original age. Unknown/expired presence remains unknown;
  status reads and cached person re-emissions cannot renew it.
- Start/change vacation with an end date in the displayed HA time zone, or
  explicitly return to the programme. Repeated daylight-saving times require
  an offset choice; nonexistent times are rejected. The existing finite comfort
  service checks the expected room scope. Unconfirmed requests are not replayed.

## Fixed

- Validate complete profile storage before interrupting the existing connection.
  Room and installation changes share one apply path. Interrupted or unconfirmed
  changes retain saved intent without rolling back or automatically retrying.

- Contact, extra-target and comfort status share one canonical room identity
  check. Reusing an old entity ID for another room cannot display that room's
  state or a stale override countdown in the editor.
- The initial controller link recognises E32 beta release tags alongside alpha
  tags. Firmware identity, compiled contract, update state and authenticated
  settings checks still apply.
- Contacts can pause an ordinary room without enabling comfort modes or changing
  its temperature bounds, source profile or independent frost policy.
- A new incompatible comfort frost target is rejected before saving. Native
  installations retain their existing 5 °C source target and room-bound checks.
- The editor and wizard share identity validation; deletion/replacement during
  review or compilation cannot silently adopt another device. Removing contacts
  clears their persisted bindings and listeners.
- A new managed editor tag and versioned resource URL load the current editor
  after an update. Saved older card types remain supported.

## Updating

Install with the coordinated E32 beta.6 release using the normal HA update route,
a scoped backup and postcheck. Preserve installation, entity and programme identities.

## Limitations

Software verification does not qualify physical sensors, valves or boiler control.
Installing this package does not authorize physical device commands.
Physical wall controls still require their own original-action/echo profile.
Vacation is session-local: restart, reconnect and room reload clear the selection.

# HA 0.4.0b3 — original measurement diagnostics and field export
<!-- user-release-notes:v2:en -->

## New

- A diagnostics download and export for the original native boiler fields: raw value, scale, unit, measurement quality, source telegram, original reception time and expiry (TTL).
- A distinction between not received, invalid and expired readings and a lost connection. Missing values stay unknown.

## Fixed

- Invalid room temperatures and error codes are not offered as valid readings or statistics points; supported real zero values are kept.
- The field explanation stays available in the diagnostics when Home Assistant leaves out the attributes of an unavailable entity.

## Updating

Install `OpenThermostat-HA-0.4.0b3.zip` through the existing HA administration route with a backup and a post-check. This candidate belongs with E32 beta3; rooms, programs and entity identities are kept. The optional original Zigbee reception package remains a separate installation.

## Limitations

No physical boiler/valve release or automatic heating. The confirmed Ecomline setup has no digital pressure sensor; an unknown pressure is not replaced by a made-up value. Adjusting the heat-trial profile remains open.

# HA 0.4.0b1 — start-up recovery, monthly export and reliable measurement handling
<!-- user-release-notes:v2:en -->

## New

- **Export history per day, week or month:** CSV exports of up to 31 days from existing Recorder data, with an installation selector and Dutch/English explanations. Missing history stays missing.
- **Clear clock notice:** a faulty local measurement clock gives an installation-specific Repairs notice. Window and presence signals then also become unknown.
- **Optional Zigbee source package:** the existing receive-only original reception extensions (a Zigbee2MQTT companion) come separately in the same release. A checked tool keeps private device bindings before installation; nothing is installed automatically.

## Fixed

- OpenThermostat starts again on Core **2026.10.4**. A version check unintentionally blocked the "Installation and boiler" display group. Core .2, .3 and .4 compatibility is checked separately; unreviewed private configuration writes remain blocked.
- A screen error, an interrupted withdrawal, an old-profile callback or a replaced sensor profile can no longer bring back a withdrawn reading. Invalid temperatures, percentages and extremely large numbers are refused.
- The CSV export re-checks who owns the entities after waiting. Data does not appear under a changed binding.
- The original Zigbee reception extensions no longer wait indefinitely for MQTT when shutting down. A time-out does not confirm sending and starts no new receiver while old SDK work is still pending.

## Updating

Use `OpenThermostat-HA-0.4.0b1.zip` through the existing HA administration route. Rooms, programs, entity identities and bindings are kept. This is the HA half of the same software candidate as E32 beta1; the E32 firmware is a separate download. The optional Z2M source package is not an HA component and is not installed automatically; keep the private pins and follow the included NL/EN instructions.

## Limitations

The E32 also offers local Bluetooth diagnostics. This HA update does not qualify that data as a room source and does not release physical valve/boiler control, standalone heating or active learning control. Physical acceptance and qualified room-source work remain open. [Full workboard and remaining conditions](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0b1/docs/modern-thermostat/WORKBOARD.nl.md) (engineering notes, Dutch).

# HA 0.4.0.dev48 — more reliable shutdown and reload
<!-- user-release-notes:v2:en -->

## New

This maintenance update focuses on reliability; there are no new settings or controls.

## Fixed

- When the integration stops or reloads, background tasks are cleaned up better. Even when one part reports an error, cleaning up the other parts continues.

## Updating

Your rooms, week programs, bindings and dashboard cards are kept. This version was checked together with E32 alpha36.

## Limitations

This is a test version. Direct Bluetooth pairing with Shelly and Xiaomi devices is still in development. Boiler control is not released yet.

# HA 0.4.0.dev47 — robust start-up and joint updater diagnostics

Joint bundle with E32 alpha34. All 23 prepared parts and 31 requirements are kept, including earlier reception diagnostics and send checks.

- One native start-up owner across program, Store and MQTT read boundaries. Shutdown/cancellation can never restart an old worker, listener or timer later.
- A double start does not replace the first connection. Late unsubscribe handles are cleaned up immediately; another receiver is kept.
- The optional original temperature diagnostics share one subscription budget of one second; a diagnostics error leaves the existing control connection available. No new subscriptions, workers, routes or retries.
- The joint firmware stores four targeted checkpoints before the checksum, image validation, flash readback and boot selection. The existing status page explains them in Dutch and English.
- Ten new HA boundary cases demonstrably fail before the fix; 2,349 complete HA cases per supported Core pass locally. Native firmware: 782 cases, including 40 updater cases also under ASan/UBSan; 24 updater browser cases.
- Frontend dev41/v41 with v38/v35 aliases stays byte-identical. No card, settings, source or physical authorisation migration.

HA47 stays compatible with the observed E32 alpha31. An original TV02 worker reception was observed passively but is stale and unqualified; this is no causal valve ACK. A suitable room source, the product SOURCE factory, physical stop/failure qualification and the earlier E32 recovery route remain open. Tado stays the active controller; this bundle releases no physical output.

Publication/HA roll-out requires the exact frozen source, full CI, an independent review of the actual package, a fresh current HA46 backup and a separate post-check. No blind E32 flash retry and no claim that the earlier watchdog/HTTPS/short-cycling cause is solved.

English: native HA startup retains one owner across asynchronous configuration, journal and subscription boundaries. Closing/cancelling cannot revive a worker/listener/timer; duplicate startup cannot replace the first owner. Original-temperature diagnostics have one bounded optional subscription wait. The combined firmware adds four persisted pre-verification checkpoints with EN/NL explanations. Existing cards/settings and alpha31 compatibility are preserved; source/valve feedback, physical stop qualification and updater recovery remain separate open gates.

# HA 0.4.0.dev46 — original reception diagnostics and joint send checks

Joint preparation release with E32 alpha33. All 23 prepared parts and existing settings, programs and cards are kept.

- The existing HA diagnostics download shows bounded RAM counters for original temperature and TV02 reception: callbacks, placement, early drops and worker acceptance/rejection/errors.
- Two fixed groups without topics, device IDs, message content or exception texts. Counters are per connection owner, not per device or persistent. No counter or snapshot qualifies a measurement source or valve ACK.
- The existing queue and half-queue reservation stay in charge. A failed timestamp registration becomes visible as a drop and cannot make the MQTT callback hang on that exception.
- The joint E32 bundle guards re-entry at the final transfer boundary and at availability/clock callbacks during channel admission. The existing socket test confirms that a refused re-entry transfers no byte.
- Existing room and firmware messages stay the same by byte contract. Frontend dev41/v41 and the v38/v35 aliases are kept; there is no card or settings migration.

HA46 stays compatible with the observed alpha31 and the earlier alpha28; the optional prepared channel route needs at least HA45. Reception counters do not solve an unknown external producer or binding error and give no suitable room reading, physical feedback or control authority. Product SOURCE stays closed; Tado stays active.

Publication/roll-out requires exact source, CI, package and download checks, a fresh current HA backup and a separate post-check through the existing HA agent. The earlier E32 uploader watchdog, native HTTPS error and short-cycling cause remain open; no blind firmware retry.

English: bounded original-ingress counters in the existing HA diagnostics download distinguish callback drops from worker outcomes without payloads or identifiers. Counter scope is the connection owner's RAM lifetime, not per-device traffic or control authority. The combined firmware bundle closes handoff/availability/clock callback recursion. Existing frontend aliases and alpha31 compatibility remain. Physical feedback, ambient qualification and E32 updater recovery are separate open gates.

# HA 0.4.0.dev45 — original grant correlation and a larger firmware bundle

Joint preparation release with E32 alpha32; existing features, programs and all 23 prepared parts are kept.

- The existing native worker answers with the original request sequence number. Delayed grants cannot borrow a new firmware window.
- A grant that is not yet used stays with its original request; a higher request sequence number cannot relabel it. A shortened receiver deadline is also kept after such a refused request.
- The real C++ request/grant/command goes through the native HA worker to the guarded service adapter, including duplicate and failure tests. Service acceptance remains no original valve echo or control authority.
- The ACK-without-snapshot test now first reaches the real ACK stage before its real asyncio time-out expires. Delayed preparation is tested separately; the production time-out of 90 seconds is unchanged. The cause of the older occasional CI room failure remains unknown separately.
- Frontend dev41/v41 with v38/v35 compatibility stays byte-identical; no card migration, automatic sensor change or new product factory. Settings and identities are kept.

HA dev45 stays compatible with E32 alpha28 and the freshly observed alpha31; the new prepared firmware channel route needs dev45. Product SOURCE selection, a suitable original measurement source, a causal valve echo and physical acceptance remain open. This is not an active boiler beta: Tado stays in control and physical outputs remain blocked.

Roll-out requires exact CI/package checks, a fresh current backup and an independent post-check. The earlier E32 uploader watchdog, native HTTPS error and the reported short cycling are not presented as repaired.

English: original request-sequence correlation on the existing worker; unconsumed grants cannot be relabelled or regain a shortened deadline. Actual C++/worker/service and disconnect regressions preserve one-use ownership. Existing cards and alpha28 compatibility remain; product actuation, original physical feedback and E32 recovery are still unqualified.

# HA 0.4.0.dev44 — native valve route and joint reception checks

Joint prerelease with E32 alpha31; all existing features, settings and 23 prepared parts are kept.

- Grant requests and valve commands use the existing native MQTT worker and connection, without extra clients, timers, storage or queues. The product factory stays closed by default.
- Local controller/session/config/binding checks and the original reception/lease deadlines bound commands. One grant admits one new command; duplicates renew no window or service call.
- Firmware going offline or a changed scope revokes an existing owner immediately before the worker queue, even while it waits for the service lock. The adapter re-checks the context before and after the original source authorisation.
- Disabled, revoked or excessive optional valve traffic cannot reset the shadow session through the shared queue. Normal periodic hello messages do not extend a valve grant.
- All earlier ESP/EMS diagnostics, source selection explanations and EN/NL controls are kept. Frontend dev41/v41 with v38/v35 compatibility stays byte-identical; no automatic source change or new physical authorisation.

This package can keep working with the last verified E32 alpha28: it assumes no new firmware feature. A truly qualified product SOURCE factory, a normal firmware MQTT send route, an original causal Tuya echo and physical acceptance remain open. Service acceptance is no valve ACK or proven delivery path. This is not an active boiler beta; Tado stays in control and physical outputs remain blocked.

E32 update recovery is blocked separately by the earlier unexplained watchdog reset. HA installation requires the exactly tested package, a fresh backup, one normal restart and an independent post-check. No claims about solved short cycling, native HTTPS recovery or new Shelly/Xiaomi drivers.

English: native-worker actuator grant/command handling with default-denied product authority, original receiver deadlines, one-use grants, immediate scope/offline fencing and optional-queue isolation. Configuration and frontend remain compatible with installed alpha28. Service acceptance is not a physical valve acknowledgement; active heating and E32 recovery remain separate acceptance gates.

# HA 0.4.0.dev43 — clear temperature source selection and M2 receiver admission

A larger maintenance candidate that keeps all existing features and settings.

- The room editor warns immediately in Dutch/English when the chosen source is an internal device temperature. Diagnostic sensors get a recognisable label; no hidden automatic source change or qualification of an ordinary cached value.
- Missing/corrupt optional native MQTT metadata no longer prevents the room from loading. The warning follows the current draft choice and does not stick to a replacement sensor.
- Frontend dev41/v41 with explicit v38/v35 compatibility; existing manual cards keep working. Only the integration's own generated card/resource references may move along with the update.
- A new prepared M2 receiver core: closed by default, exact local source/session/config/binding ownership, five seconds of validity on the HA clock, one command in progress and no extension on reception. Duplicates are historical only; uncertain or cancelled actions are not repeated. Callback revocation and reuse of the same adapter cannot bypass the owner.

The receiver core is not selected by the production factory. Normal
FW→HA wiring, current lease binding, a causal original valve echo and physical
qualification remain open. This is not an active beta or a release of valve/boiler output.

59 new base cases plus four additional owner-boundary regressions,
an extra rounding-boundary case and a start-up loss regression.
An extra regression tests delayed first room messages. The test setup
starts the minimum-off waiting time only after both real firmware readings;
the 120-second rule and all original demand/stop assertions are kept.
The five-second boundary is tested from the original clock anchor,
so adding decimal numbers cannot produce a false test result. The room test
runs eight times per Core version with separate replayable, artificial
message sequences. The earlier intermittent room assertion is investigated with this;
the start-up loss regression does not by itself prove the original CI cause. Targeted
HA and cold browser tests on desktop/mobile in both languages pass; full
Core 2026.10.2/2026.10.3 and exact tag CI remain separate delivery conditions.

Entity IDs, units, statistics, SOURCE/journal and the settings format are
kept. E32 runtime code is unchanged: firmware download alpha30 stays in place,
the module stays on alpha28 until the unknown uploader watchdog cause and a
well-founded recovery route are established. No blind upload/restart/rollback.
Bluetooth support, physical source/valve/boiler tests and long-term stability
are not presented as ticked off.

English: room setup now explains internal/diagnostic temperature sources immediately,
without new broker traffic or source replacement. Missing optional native metadata
cannot break the editor. Frontend v41 retains v38/v35 compatibility. A default-deny
M2 receiver admission kernel is prepared with receiver-owned grants, bounded input,
strict ownership and no uncertain retry; it is not wired into production actuation.
Test warmup now waits for both actual firmware measurements before counting
the unchanged minimum-off interval; a lost-startup-report regression covers this.
E32 firmware and physical output blocks remain unchanged.

[Workboard and remaining conditions (Dutch)](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev43/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev40 — persistent clock monitoring of the M2 valve adapter

A maintenance release with all earlier features and the prepared B05/M2 repair.
The E32 firmware has no new runtime changes; alpha30 stays the current
firmware download. No unnecessary new firmware tag or E32 installation.

- A monotonic clock that runs backwards, is invalid or is not finite permanently revokes the existing valve adapter. Restored time, a new target or restored authorisation cannot restore old authority.
- The check covers waiting, every authorisation callback, the final check before sending and the return of the HA service. A refusal or exception cannot hide a clock loss either.
- A clock loss during a command that may have been sent keeps the physical outcome unknown and prevents a retry. An exact duplicate remains only a historical service acceptance receipt, without new IO or valve confirmation.
- No change to entity IDs, statistics, settings, MQTT contracts or frontend v38/v35 compatibility.

14 new regression cases; 13 failed on the old source. All 141 targeted cases
pass on real Core 2026.10.2 and 2026.10.3; the independent source review passed.
Final tag CI and package checks remain separate delivery conditions.

Passive maintenance release. The M2 adapter has no normal FW→HA send route yet
and no qualified physical feedback; boiler/valve outputs remain blocked.
The installed E32 stays on alpha28 as long as the earlier watchdog cause/recovery route
is unknown. No claim of an active beta or of a Bluetooth, short-cycling or updater repair.

English: preserves every existing feature and adds latched monotonic-clock
validation throughout the prepared M2 actuator adapter. Invalid/reversed time
cannot revive an old command budget; uncertain dispatch is never retried.
Historical duplicates remain acceptance-only. No physical actuation is enabled;
E32 alpha30 remains the latest firmware release, with alpha28 still installed.

[Current workboard (Dutch)](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev40/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev39 — reliable boiler values after errors and withdrawal

Joint passive maintenance bundle with E32 alpha30; all earlier features and frontend v38 are kept.

- A transport error withdraws the previously stored acquisitions of boiler values. A valid message for another field group does not make those old values available again.
- An explicit invalid value may withdraw the same acquisition; a repeated old numeric value cannot undo that withdrawal. Only demonstrably new reception restores availability.
- The firmware processes telegrams by original field time, keeps recent values on delayed reception and withdraws conflicting simultaneous values.
- Existing entity identities, units, statistics, settings and MQTT contracts are kept.

Tested locally on real Core 2026.10.2 and 2026.10.3: 2195 test cases per version, without failures or skips; the joint firmware base has 689 passing tests. Release CI and an independent package check are separate delivery conditions.

No physical control release. The installed E32 may stay on alpha28 as long as the earlier task watchdog reset has no well-founded recovery route; HA installation and E32 installation are checked separately. New Bluetooth drivers and M2/start/stop qualification remain open.

English: retires boiler field acquisitions across invalid transport frames and explicit withdrawal. Unrelated valid groups or cached replay cannot revive them; strictly newer original readings are required. Entity IDs and storage contracts are preserved; passive operation remains enforced.

[Current workboard (Dutch)](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev39/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev38 — original reports and compatible controls

Part of the joint maintenance bundle with E32 alpha29 at source
`d131c503f42e6b834a0815db8384983a7fc1b46f`.

- TV02 diagnostics can wait for late MQTT discovery with a pre-recorded device identity; no automatic source replacement.
- Native registry changes withdraw the original temperature diagnostics, also when settings are restored afterwards. Ordinary name changes keep working.
- EN/NL messages for missing metadata and unavailable reception; no old values in an error/waiting state.
- Frontend dev38/v38 with a compatibility alias for existing v35 cards, checked with a cold browser load.

Tested on real Home Assistant Core 2026.10.2 and 2026.10.3: 2189 cases per version without failures/skips. Browser regressions and the upgrade test passed. No physical control release or automatic sensor change. Shelly/Xiaomi Bluetooth support stays planned; M2 and physical boiler/valve tests remain open.

English: restores optional original-report diagnostics safely, retires changed sensor identities, and adds clear reception states while preserving existing v35 room cards. Passive operation remains enforced.

[Changes and remaining conditions in the source](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev38/docs/modern-thermostat/WORKBOARD.nl.md) (Dutch). The separate history file in this source contains the earlier release history.

# HA 0.4.0.dev37 — sessions, queue and reliable start-up

Joint release with E32 alpha28; all earlier features and fixes are kept.

- An invalid/backward-running monotonic clock withdraws the session, grants and waiting commands; reconnecting restores no old authority.
- After every waiting send, retries re-check the current lease/deadline, SOURCE and the original command registration. Revoked/replaced commands are not offered again; no heartbeat on an expired session.
- Start-up errors and cancellation also clean up resources created early; an old cleanup cannot remove a new owner.
- Oversized numeric valve metadata is refused as an unusable capability without crashing the editor.

The supported native Core versions stay 2026.10.2 and 2026.10.3, with full tests on both real runtimes. No frontend change: module dev35/v35 stays byte-identical. Rooms, programs, SOURCE, registry, reception pins and producer are kept.

No automatic valve/boiler commands or new receiver grant route. A received TV02 temperature message is no causal valve confirmation. Tado stays in control; active M2/boiler acceptance remains open.

**English:** Combined with E32 alpha28. Retires session evidence on invalid/backward monotonic time, rechecks queue ownership and original deadlines after awaited publishes, fixes failed/cancelled HA setup cleanup and oversized target metadata. Supports actual Core2026.10.2/2026.10.3; unchanged frontend and preserved configuration. Boiler/valve actuation stays disabled.

# HA 0.4.0.dev36 — Core 2026.10.3 and the joint E32 alpha27 bundle

Includes all changes from dev35 and fixes the start-up block after a Core update to 2026.10.3. The explicitly supported versions are now 2026.10.2 and 2026.10.3; other versions stay refused for the native configuration transaction. All five version checks use the same list. The full suite runs on both real Core versions; no version number or HA API is simulated. Settings and registry are not recreated.

Joint passive release with E32 alpha27; no new firmware variant needed. The previously published dev35 is kept as history and is not installed. This is no release for valve or boiler commands.

# HA 0.4.0.dev35 — joint diagnostics and safety bundle

Bundles all prepared HA changes since dev34, together with E32 alpha27.

- Frontend dev35/v35 with a clearer EN/NL status for outdated TV02 reception, without presenting old values as a current valve confirmation.
- Stricter binding and lifetime of valve commands: repeated commands share one service call and the original deadline; cancellation or uncertain execution causes no automatic retry.
- Loss of the owner, binding or valve mode during a service call blocks automatic follow-up actions.
- Additional supervisor diagnostics for invalid feedback clocks.

The command adapter is prepared, but not yet connected as a normal firmware-to-HA send route. An HA service confirmation does not prove that a valve moved. Existing rooms, programs, SOURCE, registry, reception pins and producer are kept. No automatic source qualification or device commands. Tado stays in control; this is a passive prerelease, not an active boiler beta.

# HA 0.4.0.dev34 — diagnostics and clear controls completed

Bundles all earlier HA fixes and the native ESP diagnostics with the EN/NL explanations of settings and checks. Belongs with E32 alpha26; that firmware does not need to be flashed again for this.

- The reception age of the read-only supervisor diagnostics is compared directly with the expiry deadline. This keeps an exactly expired report from staying visible through rounding when two clock values are subtracted.
- A deterministic test with a fractional clock start shows the original error and the fix. Control authority, commands, leases, source qualification and physical outputs do not change.

# HA 0.4.0.dev33 — the ESP's own diagnostics over native MQTT

Restores free/minimum free heap, the largest free block, CPU temperature and uptime together with E32 alpha25. Existing entity unique IDs and history are kept. The HA entities also exist before the first report. Live reports are available every 15 seconds; after 45 seconds without a valid report, or when offline, availability is withdrawn. An HA-only restart does not require an E32 restart. The disabled RTC temperature stays unknown. Legacy mode stays intact.

Settings and status make clear in English and Dutch that shadow mode only reads and calculates. A confirmed configuration and matching valve targets are explained separately; they are not presented as proof of valve movement or of safely stopping the boiler.

This uses the same native connection and the existing HA runtime for expiry; no valve or boiler commands are added. All features and fixes from dev32 are included. Without the matching E32 alpha25 these native diagnostic values stay unavailable.

# HA 0.4.0.dev32 — report lifetime and explainable transport rejections

Bundles all HA fixes since dev31. E32 alpha24 stays in place; this release
grants no physical measurement, valve or boiler qualification.

- Original temperature and TV02 reports stay bound to the chosen
  maximum report age. A policy change revokes the old receiver;
  restoring it does not reuse old reports. A new owner starts empty.
- Invalid clock values and overflowing time deltas are handled safely.
- The existing receiver keeps at most one historical rejection for a
  current, requested reply. HA diagnostics show only fixed stream, status
  and reason codes with the reception age. Unknown peer text is not executed
  or exported. A later healthy status does not turn this into a current fault.
  A session change or a detected clock error removes this diagnosis.
- Native configuration rejections with the optional `rejection_reason` field are
  processed correctly as a rejection; they no longer disappear because of an overly strict schema.
  Success remains valid only through the existing readback/SOURCE checks.

Rooms, programs, bindings, accepted SOURCE/journal, registry, dashboard,
private TV02 pins and the receiving producer are kept. No extra client,
watcher, automatic retry or device command. The frontend bytes and the existing
dev28/v28 card identity stay the same. Natural TV02 reception, causal
command confirmation and physical acceptances remain separate open checks.

# HA 0.4.0.dev31 — TV02 reception for native installation rooms

Restores the original TV02 receiver for rooms whose chosen valve is in
the central installation configuration. The receiver validates the same
native configuration owner as the room editor. Missing, duplicate, changed
or invalid bindings are refused; a revoked source does not revive
by itself. Identity, age and replay checks are kept.

This targeted follow-up update enables reception acceptance after the joint
alpha24/dev30 bundle. E32 alpha24 stays in place. No device command, automatic
valve mode change or source qualification. The private reception pins already in place
and the receiving Zigbee2MQTT extension are kept; the package contains no private
pins. Rooms, programs, SOURCE, registry and history are kept.
Frontend bytes and the dev28/v28 card identity stay the same.

# HA 0.4.0.dev30 — supervisor, bounded valve targets and private reception pins

Joint candidate with E32 alpha24; bundles all HA changes since dev29.
The default physical output stays blocked. This is not an active boiler beta.

- Read-only supervisor diagnostics show the reported phase and control intentions with a limited
  reception age. Expired, missing or invalid status is withdrawn;
  diagnostics grant no authority and do not discard valid room decisions.
- The prepared valve adapter bounds both the waiting time and the service call within the same
  action deadline. A newer waiting target replaces an older one. An uncertain outcome
  after dispatch blocks follow-up actions within the same adapter, without retry.
- Original TV02 reception pins can be read from the private file
  `.openthermostat-original-tv02.json` in the HA config root during a
  normal native start-up. Strict schema, private permissions, identity binding and
  error isolation; no Store, watcher, extra MQTT client or device command.
  A missing/invalid file lets the normal controller start-up work.

The update installs no Zigbee2MQTT producer, changes no measurement selection or
valve mode and grants no source/flow/valve qualification. Real original
reception requires separately reviewed private pins and a producer installation.
Rooms, programs, SOURCE, registry identities and history are kept.
The frontend bytes do not change: the existing dev28/v28 resource/card identity
stays valid and is not replaced on the basis of the manifest number.

# HA 0.4.0.dev29 — original TV02 reception visible

Bundles the prepared original TV02 data point reception through the existing
native MQTT connection and registry lifecycle. Reception is bounded, checks
the explicitly recorded device identity and source age, and does not make outdated,
retained, repeated or wrongly bound reports current again.
The default source pin list stays empty. Production source pins, the Zigbee2MQTT extension
installation and real original report reception must be reviewed
separately; the update does not enable them automatically.

The room editor shows available original reports in Dutch or
English: reported target, the valve's own temperature, program, heating stop and
frost protection. The reception age applies at load time. Reception is no
command confirmation, valve position, proven heat delivery or control release.
Expired, interrupted or invalid reports show no old data point values.
Draft changes do not use the diagnostics of an old saved binding.

The changed editor has its own dev28/v28 cache/card identity; dev29
keeps those same frontend bytes and adds complete package notes.
Existing manual cards stay compatible. No extra polling,
MQTT client, automatic valve mode repair or setpoint command was added.
Existing measurement entities, history, rooms, week programs, SOURCE and device
identities are kept. This is the joint passive test batch with
E32 alpha23 (logging/syslog and stable dashboard refresh). Physical
boiler/valve outputs remain blocked and the active beta remains open.

Dev28 remained an unpublished package candidate; the existing tag is
kept. Dev29 contains the complete updated Dutch package notes.

# HA 0.4.0.dev27 — current boiler fields visible in the overview

The managed boiler overview now uses the native boiler sensors that became
available with alpha20/dev26. Flow, return, reported
modulation and hot-water temperatures get their own history cards. All
available field definitions are included through the registered entity ID;
renaming, disabling and installation ownership are respected.
Reported fields and derived activity are listed separately. Enabled
unreliable raw diagnostics stay under Diagnostics and do not become flame or
pump evidence. No old statistics are merged and no counters are filled in.

This completes the HA presentation of the readout update; E32 alpha20 stays in place.
No SOURCE, room, program, controller or output changes. The existing
room editor and its dev25 cache identity do not change.

# HA 0.4.0.dev26 — native measurement binding for the product installation

Bundles all prepared dev25 features with the fix for existing v2
measurement entities. The product installation now uses the same validated native
MQTT cache as the native sensor platform tests. One owner per measurement identity
prevents duplicate sensors from legacy messages. Entity identities,
statistics definitions and the installation group are kept; expired or
unsupported values stay unavailable. The frontend stays on the same
already refreshed dev25 card version because the frontend bytes do not change.

Together with E32 alpha20, available Classic boiler fields become visible.
Outputs remain blocked; no change to SOURCE, rooms or programs.

# HA 0.4.0.dev25 — current boiler fields and consistent EN/NL controls

Together with E32 alpha19, available Classic boiler fields are offered as read sensors
on the existing installation through the existing native MQTT session.
The source age, quality, unit and validity stay visible. This restores
the missing modern readout path; old legacy aliases and their history are
kept and are not merged with new measurement definitions. Values the
boiler does not deliver stay unknown; unreliable diagnostics stay
disabled by default.

The complete EN/NL form catalogues were completed. The room editor follows the
HA profile language, with a new cache/card identity while older cards are kept.
Saved native dashboard texts use the agreed English fallback.
All prepared device/measurement diagnostics, week planner and storage fixes
are included. No room bindings, programs, valve modes or
heating releases are changed. Physical outputs remain blocked.

# HA 0.4.0.dev24 — joint source and device checks

This release bundles the prepared source changes with E32 alpha18. Measurement qualification is withdrawn when an observer is replaced or the native sensor or device is changed/disabled. Waiting readings are re-checked before handover; the cache and re-registration do not make an old reading fresh.

The valve adapter checks the identity and the current temperature capability just before dispatch. TV02 auto/vacation/off/unknown mode is shown as a conflict and grants no target authorisation. The device check shows the explicitly reported Zigbee2MQTT and converter package versions. The frontend gets a new cache and card identity.

Program, room identities, bindings and SOURCE are kept. This installation changes no profile, valve mode or physical output. The production measurement profile and physical valve/boiler acceptance remain open; missing qualification stays visible. All earlier planner, cold-start, setup and connection fixes are kept.

# HA 0.4.0.dev23 — bundled room and connection improvements

This release belongs to the joint test batch with E32 alpha17.

- At start-up the room page waits for the HA root element. That keeps the card registered after HA has set up its custom element registry; refreshing repeatedly should not be needed.
- With a normally linked native controller, the temperature sensor, radiator valve and room limits can be changed on the room page. The complete future plan is checked beforehand; the room, graph and new profile are saved together and applied through the existing secured controller connection.
- If applying cannot be confirmed, the saved settings are kept. The page blocks further changes and offers an explicit button to apply exactly those saved settings again. There is no automatic retry or restoring of an old profile.
- The existing native heartbeat can pass bounded UTF-8 room names to an E32 that supports them. Old firmware stays compatible.
- The old temporary source bench is refused for a control plan managed by SOURCE, before it can change configuration, timers or ownership.

Existing room identities, programs and bindings are kept by the update. Device changes happen only after an explicit save. One radiator valve per native room remains the current contract limit; program source changes remain a separate setup. Availability of an HA entity does not prove a qualified temperature reading. A missing measurement profile stays visible and gets no automatic qualification or heating release from this update.

Verification includes native HA save/reload cycles, the normal controller provisioning with checked external HTTP responses, real MQTT packet exchange with the C++ controller and desktop/mobile browser regressions. Physical device acceptance is separate from that.

# HA 0.4.0.dev22 — measurement status in the room controls

Next to the linked sensor, the page now shows separately whether the control has a qualified reading, is waiting for a measurement profile that is still missing, or has an unconfirmed/expired reading. The status is a snapshot at load time. It changes no sensor settings and writes no program or actuator commands.

Availability in Home Assistant and how current a reading is stay separate. A read action never renews the age of a reading. Report IDs and other source payloads are not included in this summary. The existing planner and cold-start fixes are kept.

# HA 0.4.0.dev21 — moving short week blocks reliably

On a touch screen, a short temperature block is now moved as a whole when dragged, keeping its duration and temperature. The fixed edge zone could previously take up the whole block and so unintentionally change its start time. With a mouse, every block keeps a middle area for moving; larger blocks can still be extended or shortened at the edges. Exact times stay adjustable in the fields below the planner.

The browser regression uses real Chromium touch events at 320, 390 and 1440 px, in Dutch and English. It checks short blocks, mouse use, time fields, overlap, day boundaries, cancelling and the absence of automatic saving. This is screen emulation, not acceptance on a physical phone.

The cold-start fix from dev20 is kept. This HA update contains no firmware and changes no saved room program or device bindings.

# Home Assistant 0.4.0.dev20 — room page registration on direct opening

The room editor previously waited for ha-card before registering its own custom
element. A direct room URL can load before that built-in component, leaving the
editor unregistered and showing a Lovelace Configuration error. The editor
extends HTMLElement and has no dependency on the ha-card definition.

Register immediately; a nested ha-card can upgrade later. The frontend module URL
and managed card type advance to dev20/v20 to refresh cached dev19 clients.
Eight desktop/mobile NL/EN browser cases now exercise both cold and preloaded
HA shells, including preserving a draft when ha-card registers later. Four
existing device-metadata cases remain covered. The regression failed against
the original script and passed after removing the unnecessary wait.

No room settings, schedule, SOURCE, sensor bindings or controller admission
rules are changed. No firmware is included. Browser fixtures use simulated
admin WebSocket responses; live deployment and the user's exact browser
session are separate verification steps.

# OpenThermostat Home Assistant 0.4.0.dev19 — test release

Dev19 fixes saving after room settings have been open for a longer time. A fresh
room status does not prove that the earlier configuration readout is still current.
On Save all, the existing connection first asks for a new
configuration confirmation when needed. Only then is the room saved and the
changed plan confirmed through the same controller. The existing age limit
still applies; no authority or source qualification is fabricated.
If that readout is missing, the draft stays visible and nothing is
saved. No automatic retry of a change. The live dev18 test
was refused before saving; 21 °C and revision 1 were kept.

With a connected controller you can now change the **name, base temperature and local
week blocks** directly on the room screen. Save all stores the
room, waits for the normal HA reload cycle and confirms the actual E32 plan
through the existing MQTT worker. An ACK alone does not count as completion. When
temperatures/blocks change, a temporary temperature expires when the
new program is applied. With active control, device bindings and profile limits
stay visible but locked for now; their full
profile migration is still open.

If applying cannot be confirmed, the draft is kept and no
command is retried automatically. After reloading, the user can explicitly apply the
saved program again. The existing SOURCE,
credentials, valves and physical authority are not replaced. This path
fabricates no qualified temperature source or physical operation. The earlier
rejection of a single temporary 22 °C command remains open separately;
this version does not yet explain or fix it.

One installation with central settings and rooms. New rooms use
a wizard; existing rooms have one direct configuration screen with linked
devices, temperatures and a graphical week program with temperature blocks.
Device identity, availability and valve limits are shown with the room.
This version correctly recognises the official Home Assistant feature flags of a climate device;
valid temperature limits therefore no longer need to look unknown.

Dev17 recognises Zigbee2MQTT climate devices without a general `state_topic`.
The prefix is derived only from both the published bridge and
the exact device availability, bound to the existing device identity.
Missing, invalid and conflicting data stay refused. This version
changes no device settings or physical control.

Dev16 fixes reading Home Assistant's own `MQTTDiscoveryPayload`
object. The regression test now uses that real native object, also together with the
actual HA MQTT client and a local test broker. The earlier dev15 tag and
files are kept; use dev19 for the current device check.

Present since dev15: on the room screen, under **Advanced settings**, there is
**Check device information**. Only on request, it reads the most recently
reported Zigbee2MQTT definitions for the saved sensor and valves. Target temperature,
external temperature input, valve position and converter options are shown separately.
Missing information stays unknown. A diagnostic device temperature
gets a clear explanation; it is not automatically a qualified
room reading. This is information about device capabilities, not a successful physical
valve test. No settings, interviews or heating commands are sent.
This readout uses the existing HA MQTT connection, two exact topics and
a short waiting time. Other devices and raw discovery/broker data are
not sent to the screen. Other device sources stay linked normally;
they cannot always offer this specific Zigbee2MQTT readout.

Also present since dev14: choose **Connect E32** in the central integration settings.
Enter the local web address and administrator password. The integration checks the
actual E32, keeps the existing network settings and synchronises the
room program through the existing connection. Receiving a command alone
is no success: the E32 must return the correct configuration and the current room status.
A first link can restart the E32 once. E32 alpha.9 or newer
compatible firmware is needed; the current profile supports one or two rooms.
The administrator password is stored in the existing HA integration; cookies and
check codes stay temporary. Ordinary room screens and diagnostics do not export
the password. With an interrupted link, no confirmed execution is
pretended; check the installation status before you try again.

This is a development release. The normal HA→E32 configuration chain was
confirmed live with dev14; the physical sensor/valve/boiler test and heating release
are not finished yet. Name, base temperature and local week blocks are editable in
dev18 with an active link. Changing devices and profile limits,
the optional external room target source, a window contact and several qualified
valve profiles remain follow-up work.
The new E32 firmware is tested and released separately; this release
contains only the Home Assistant integration. A saved setting is
not yet a confirmed execution on the E32.

Download `OpenThermostat-HA-0.4.0.dev19.zip` and check the SHA256 with
`HA-SHA256SUMS.txt`. Before installing, make a backup of the existing
integration/configuration. Copy `custom_components/open_thermostat` from the ZIP
to the Home Assistant configuration folder, check the configuration and restart
Home Assistant. Existing users do not need to add the integration
again. After the restart, check the version, rooms, device bindings and program.
Keep the previous package as a fallback.

Dev14 keeps the existing everyday controls and includes the earlier clock fix. For reproducible tests,
reception, the queue and the protocol now have one explicit monotonic clock source;
by default that remains the existing HA loop clock. The tests use the same
virtual clock as their C++ peer, independent of how long the test machine has been running.
The test also checks that delayed readings keep their real age and are
refused at the configured age limit. Freshness checks stay in place.

The pipeline builds both required C++ test probes in a clean CI environment.
The failed `ha-v0.4.0.dev11` and `ha-v0.4.0.dev12` tags are kept;
no release was published from them. Existing settings and device bindings
are kept with this update.
The package contains `SOURCE.json`, the original project licence and checksums.
No live HA storage, firmware, boiler release or device commands are included.
