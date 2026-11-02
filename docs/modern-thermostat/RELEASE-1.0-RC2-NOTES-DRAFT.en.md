# OpenThermostat 1.0 rc.2 — release notes draft

Draft only. Not frozen, tagged, published or installed. The published E32
1.0.0-rc.1 and HA 1.0.0rc1 (tags on 1dc0b06) are unchanged; their notes stay
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md` until the release step.

At the release step, the version-only commit moves the two sections below to
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md` (tags
`v1.0.0-e32v2-rc.2` and `ha-v1.0.0rc2`). `verify_publication_notes` only reads
the top section of each file, and each section must stay under its 6 KB limit
(6000 bytes including the "Full release notes" link line).

Updated on 2 Nov 2026 against `release-1.0` at a146e73: e33cbbf (rc2-ux,
rc2-autotune, rc2-persist, the HACS publish script, the manifest fields) plus
the merged rc2-replay-tool, rc2-ble-fix, rc2-security (with the hand-back
exemption 69e581f), rc2-ha-review2, rc2-active-default, rc2-rooms-active,
rc2-gui-e32b (with rc2-gui-e32), rc2-gui-ha and rc2-ha-polish. rc2-replay-tool
is a developer tool and has no reader line.

Not merged yet: `rc2-learned-room` (1b214fd), which merges rc2-fw-review2
(06e3ab8) and rc2-learning-active (a598ea3) and is still to get room for all
learned rooms. Every line written from those branches ends with
`<!-- pending merge: rc2-learned-room -->`. When the branch is merged, re-read
its commits, check each marked line and remove the marker (markers count
towards the limit); if a part does not make it, delete its words. The words
"every room's learning has room in storage" are written from the plan for the
last commit, not from a commit.

---

# E32 V2 1.0.0-rc.2 — the second 1.0 candidate: self-tuning, learning that is kept and a guided boiler test
<!-- user-release-notes:v2:en -->

The second 1.0 candidate: the E32 tunes itself, keeps what it learned, asks
for your own password, and a new installation can go straight to a guided
boiler test. If it runs 14 days without problems with the E32 controlling
the boiler, the same code becomes 1.0.0. Install it with HA 1.0.0rc2.

## New

- **Self-tuning:** the E32 tunes its burner and room control settings from
  the measured days: burner rest and run times, start and stop margins, how
  firmly a room is corrected and how early an unlearned room starts. At most
  one small step per setting per day, with enough evidence, not in the first
  24 hours after a restart or change, and only on days the E32 controlled the
  boiler. In a trial run it shows what it would change.
- **Comfort and boiler care** (Home, was "Advanced: tuning"): each setting in
  plain words, automatic or set by you, with "Set it myself", "Back to
  automatic" and "Back to start values".
- **What the thermostat has learned** (Home): per room how far learning is,
  warm-up and cool-down, the lowest water temperature that still warms it in
  time, when it starts heating for the next program step and the night
  advice; the heating curve, the burner and the self-tuning's latest changes,
  each explained.
- **Learning is kept** over restarts, power cuts and updates, and is part of
  the settings backup, so an E32 restored from a backup carries on learning.
- **Learning that fits your boiler:** self-tuning counts only the E32's own
  heating starts, so a boiler that cycles by itself gets no longer pauses;
  the E32 learns from which water temperature your boiler really heats and
  asks at least that; every room's learning has room in storage, never at
  the cost of rooms, the hand-back or Bluetooth sensors; a settings backup
  always fits what a restore accepts. <!-- pending merge: rc2-learned-room -->
- **Boiler test and takeover** (Rooms): a guided test before the E32 takes
  over: no other thermostat on the bus, your confirmation, a short heating
  start, hot water while heating (can be skipped) and a stop, each passed,
  waiting or failed. A safety stop says why and how to give control back.
- **A new installation picks its route from the boiler bus:** a trial run
  beside a thermostat that still controls the boiler, else straight to the
  boiler test. Nothing is sent to the boiler before you confirm the takeover.
  Existing installations keep their mode.
- **Your own password first:** with the factory password admin the E32
  accepts no change; signing in leads to "Choose your own password". Reading
  and heating go on, and giving control back to your old thermostat always
  works.
- **Plain words** (English and Dutch): trial run instead of shadow mode,
  water to heating and back instead of flow and return, burner power.
- **Clearer pages:** a boiler fault and what to do at the top of the
  Overview; on Rooms, active control first, saying when and why it stopped;
  amber for missing boiler messages and a low valve battery, red only for a
  silent valve; calmer room cards; errors (with Try again) and confirmations
  on the page; sign-in and System pages match the rest.
- **Better protected:** requests that do not name the E32 are refused (DNS
  rebinding); a manual upload must be an OpenThermostat E32 V2 image; slow or
  huge requests can no longer stall the heating; failed sign-ins lock out
  only that device; a backup binds its passwords to its network settings and
  needs a 12+ character passphrase; malformed valve messages cannot crash it.

## Fixed

- Learning after the switch-over: the E32 waited for the old thermostat's
  requests and now learns from its own; short hot-water rounds no longer cut
  a heating period short; until a room's cooling is learned, its warm-up is
  planned from its current temperature, not the night one (it could start
  hours early). <!-- pending merge: rc2-learned-room -->
- A replayed Bluetooth sensor message could lock the real sensor out for
  about 10 minutes after its counter restarted.
- In dark mode the selected house mode button matches the other buttons.

## Updating

From beta22 or 1.0.0-rc.1, while someone is home. First install HA 1.0.0rc2
(now also through HACS) and restart Home Assistant, then press Install on the
E32's Firmware entity. Then, in this order:

1. **Factory password admin?** Choose your own on the E32 page after signing
   in, or with the Home Assistant repair "Choose a new E32 password" (E32
   and Home Assistant at once).
2. **Confirm the takeover again:** a firmware change clears it, and until
   then the E32 keeps only frost protection. Repair "Confirm again that the
   E32 may control the boiler", or Rooms on the E32.

- **Learning starts fresh once:** earlier firmware did not keep it.
  Self-tuning waits at least 24 hours, then takes small steps.
- Settings, rooms, programs, sensors and valves are kept; tuning you set in
  rc.1 stays yours. A backup made by rc.2 opens its passwords only on rc.2 or
  newer.

## Limitations

Radiator valve control is not yet verified on real valves. Behind an EMS
adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter) the three-way valve position cannot be seen. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
Charts are lost on a restart.

# HA 1.0.0rc2 — the second 1.0 candidate: HACS, what the thermostat learned and plainer words
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.2. Needs Home Assistant 2026.10.0 or
newer.

## New

- **HACS:** install and update through HACS as a custom repository,
  `https://github.com/dielessen/openthermostat-ha` (type Integration).
  Release candidates are pre-releases; see Updating.
- **What the thermostat learned:** a new sensor and a Learned page on the
  dashboard: per room the learning progress, warm-up and cool-down, the
  lowest water temperature that still warms it in time, the planned start
  ("starts heating at 07:10 to be 21 °C at 09:00") and the night advice; the
  heating curve, the burner and the last ten self-tuning changes. The
  Heating view keeps a short summary after the rooms.
- The self-tuning changes explain when the boiler switches on and off by
  itself and longer pauses would only delay heat. <!-- pending merge: rc2-learned-room -->
- **Plain-language names and texts** in English, Dutch and Polish, the same
  words as the E32 pages; the dashboard, advice and weekly summary are now
  in Polish too. Existing entity IDs stay; only a new installation gets IDs
  from the new names.
- **E32 password:** the repair "E32 still uses the default password" can now
  be fixed: "Choose a new E32 password" sets it on the E32 and in Home
  Assistant in one step. Until then the E32 accepts no changes, and a
  refused change says so.
- **Boiler test and takeover:** the readiness sensor follows the E32's guided
  boiler test step by step, and the dashboard shows the next step while the
  E32 waits for the takeover. A new installation no longer reports a heating
  problem before its first takeover.
- **Tidier device pages:** the boiler's settings, counters, fault history and
  service details are under Diagnostic, a room's "Temperature without Home
  Assistant" under Configuration, and entities have their own icons instead
  of the generic eye. Entities and history are kept.
- **Configure:** a new installation shows the dashboard by default; the room
  form names its room; sources show by name; the default window pause is in
  minutes, like each room's.
- **Week program card on a phone:** only Save and Discard stay at the
  bottom, the selected room stands out, and the setting device shows by name.
- **Backups** include what the thermostat learned and its tuning, and the
  restore summary names each changed setting in plain words. A restore keeps
  the rooms' mode; a new or reset E32 still waits for your takeover
  confirmation.

## Fixed

- A backup with accented letters in room or sensor names could be refused as
  too large before it reached the E32.
- An undo of a restore that the E32 refused no longer loses the "before a
  restore" backup.
- A restore could overwrite and take over the E32 of another OpenThermostat
  installation in the same Home Assistant; it is now refused.
- A replacement E32 that already held the backup's settings could not be
  taken into use; the restore now offers "Use this E32 from now on".
- Setting the house mode and the away temperature right after each other no
  longer drops one or reverts the other.
- After a restart, a hidden boiler request sensor raised errors and could
  stop other heating updates.
- Boiler values renamed in 1.0 stayed as empty rows on boilers that do not
  report them.
- "Ready to take over?" no longer shows "None °C" for a value the E32 does
  not know yet.

## Updating

1. Install HA 1.0.0rc2 (HACS or the release ZIP) and restart Home Assistant.
2. Update the E32 with its Firmware entity, while someone is home.
3. If the E32 still has the factory password, fix the repair "E32 still uses
   the default password" first; until then changes wait.
4. Then fix the repair "Confirm again that the E32 may control the boiler".

**From a manual install to HACS**, without a duplicate: keep the integration
as it is (do not delete it under Devices and services) and make a Home
Assistant backup. In HACS add the custom repository above, open
OpenThermostat, choose Download, open "Need a different version?" and pick
1.0.0rc2. HACS writes to the same `custom_components/open_thermostat` folder
and replaces the manual files. Restart Home Assistant: still one
OpenThermostat entry, same entities. Keep no copy of the old folder inside
`custom_components`. To be offered later release candidates, turn on the
"Pre-release" switch of OpenThermostat's device under the HACS integration
(enable that entity first if it is disabled).

Entity IDs and history are kept. Most new features need E32 1.0.0-rc.2.

## Limitations

Radiator valve control is not yet verified on real valves. The three-way
valve position cannot be seen behind an EMS adapter that leaves byte 7 of
telegram 0x18 empty. EMS Classic boilers only; EMS+ comes in 1.1. Writing
boiler settings comes after 1.0. HACS lists OpenThermostat as a custom
repository, not yet in the default HACS list.
