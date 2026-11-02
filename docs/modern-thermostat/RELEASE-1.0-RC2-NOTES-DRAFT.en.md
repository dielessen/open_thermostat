# OpenThermostat 1.0 rc.2 — release notes draft

Draft only. Not frozen, tagged, published or installed. The published E32
1.0.0-rc.1 and HA 1.0.0rc1 (tags on 1dc0b06) are unchanged; their notes stay
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md` until the release step.

At the release step, the version-only commit moves the two sections below to
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md` (tags
`v1.0.0-e32v2-rc.2` and `ha-v1.0.0rc2`). Every `TODO` line must be resolved or
removed first; `verify_publication_notes` only reads the top section of each
file, and each section must stay under its 6 KB limit (6000 bytes including
the "Full release notes" link line). Leave room for the TODO items.

Written on 2 Nov 2026 against `release-1.0` at e33cbbf (rc2-ux, rc2-autotune,
rc2-persist, the HACS publish script, the manifest fields and the test fixes)
plus the commits on the branches still in progress: rc2-active-default
99d3f2a, rc2-security 6457d0b, rc2-fw-review2 b070073, rc2-learning-active
d9758d8, rc2-ha-review2 45d1e98, rc2-gui-e32 8e30fa4, rc2-gui-ha dd846ec.
A branch that changes before it is merged must be re-read.

- TODO (rc2-security, no commits yet): the forced password change on the E32,
  the verified manual firmware upload, request limits, the per-device sign-in
  lockout and the backup hardening. Extend "Better protected" in the E32
  section. The Updating text on the new password in both sections is written
  from the plan: check the real wording (E32 page, Repairs item) and what Home
  Assistant can still do before the password is changed.
- TODO (rc2-learning-active, only the active-mode learning is committed):
  hot-water bridging, warm-up planning without a cooling model, and learning
  the boiler's effective minimum flow. Add one New line to the E32 section
  (and to "What the thermostat learned" in HA if new figures show up there).
- TODO (rc2-fw-review2): the NVS budget for the learned state. Add a line only
  if users notice anything (for example a room that is not kept when space
  runs out); the AutoTuner fixes need no line, as self-tuning is new in rc.2.
- TODO (rc2-gui-e32b, rc2-rooms-active): no own commits yet (rc2-gui-e32b
  equals rc2-gui-e32; rc2-rooms-active only merged rc2-gui-e32). Add their
  visible changes to "Clearer pages" once committed.
- TODO (rc2-replay-tool): no commits yet. A developer tool; no reader line
  expected unless it becomes a user-facing feature.
- TODO (rc2-ha-review2 "upgrade fixes"): only the backup and house-mode
  commits exist. Add any upgrade fix that a user of HA 1.0.0rc1 or 0.4.0b15
  could have noticed to the HA Fixed list.

---

# E32 V2 1.0.0-rc.2 — the second 1.0 candidate: self-tuning, learning that is kept and a guided boiler test
<!-- user-release-notes:v2:en -->

The second 1.0 candidate. The E32 now tunes itself, keeps what it learned,
and a new installation can go straight to a guided boiler test. If it runs
14 days without problems with the E32 controlling the boiler, the same code
becomes 1.0.0. Install it together with HA 1.0.0rc2 (see Updating).

## New

- **Self-tuning:** the E32 tunes its burner and room control settings from
  the measured days: burner rest and run times, the start and stop margins,
  how firmly a room is corrected and how early an unlearned room starts. At
  most one small step per setting per day, only with enough evidence, never
  in the first 24 hours after a restart or a change, and only on days the E32
  controlled the boiler. During a trial run it shows what it would change.
- **Comfort and boiler care** (Home, was "Advanced: tuning"): each setting in
  plain words, marked automatic or set by you, with "Set it myself", "Back to
  automatic" and "Back to start values".
- **What the thermostat has learned** (Home): per room how far learning is,
  how fast it warms up and cools down, the lowest water temperature that
  still warms it in time, when it starts heating for the next program step
  and the night advice; the heating curve, the burner's starts and burn time,
  and the self-tuning's latest changes. Every figure says what it means.
- **Learning is kept** over restarts, power cuts and updates, and is part of
  the settings backup, so an E32 restored from a backup carries on learning.
- **Boiler test and takeover** (Rooms): a guided test before the E32 takes
  over: no other thermostat on the bus, your confirmation, a short heating
  start, hot water while heating (can be skipped) and a stop, each shown as
  passed, waiting or failed. A safety stop says why and how to give control
  back to your thermostat.
- **A new installation picks its route from the boiler bus:** a trial run
  beside a thermostat that still controls the boiler, or straight to the
  boiler test when none is heard. The other route is one button away.
  Nothing is sent to the boiler before you confirm the takeover. Existing
  installations keep their mode.
- **Plain-language texts** (English and Dutch): trial run instead of shadow
  mode, water temperature to heating and back instead of flow and return,
  burner power, switching margin, burner rest between starts.
- **Clearer pages:** a boiler fault and what to do now show at the top of the
  Overview; missing boiler messages are an amber notice; a low valve battery
  is amber and only a silent valve red; calmer room cards; System pages line
  up with the rest.
- **Better protected:** the E32 refuses web requests that do not address it
  by its own name or address (a web page elsewhere can no longer reach it
  through DNS rebinding), and malformed valve messages can no longer crash it.

## Fixed

- After the switch-over to E32 control, the E32 stopped learning how fast
  rooms warm up: it waited for requests from the old thermostat, which is
  off the bus by then. It now learns from its own requests.
- In dark mode the selected house mode button matches the other buttons.

## Updating

From beta22 or 1.0.0-rc.1, while someone is home. Home Assistant first:
install HA 1.0.0rc2 (now also through HACS), restart Home Assistant, then
press Install once on the E32's Firmware entity.

- **Confirm the takeover again right after the update.** A firmware change
  clears the confirmation; until then the E32 keeps only frost protection.
  Use Repairs in Home Assistant, or Rooms on the E32.
- **New password:** if the E32 still has the factory password, it asks you to
  choose a new one. The Repairs item in Home Assistant does it in one step.
- **Learning starts fresh once:** earlier firmware did not keep it, so this
  update starts from zero; from now on it is kept. Self-tuning waits at
  least 24 hours, then takes small steps.
- Settings, rooms, week programs, sensors and valves are kept. Tuning
  settings you changed in rc.1 stay yours; "Back to automatic" hands them to
  the self-tuning.

## Limitations

Radiator valve control is not yet verified on real valves. On boilers behind
an EMS adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter), the three-way valve position cannot be seen. EMS Classic
(EMS 1.0) boilers only; EMS+ comes in 1.1. Writing boiler settings comes after
1.0. Charts are lost on a restart. Self-tuning only changes settings on days
the E32 controlled the boiler.

# HA 1.0.0rc2 — the second 1.0 candidate: HACS, what the thermostat learned and plainer words
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.2. Needs Home Assistant 2026.10.0 or
newer.

## New

- **HACS:** install and update through HACS as a custom repository,
  `https://github.com/dielessen/openthermostat-ha` (type Integration).
  Release candidates are pre-releases: switch on beta versions for it. See
  Updating to move a manual install.
- **What the thermostat learned:** a new sensor and a Learned page on the
  dashboard: per room the learning progress, warm-up and cool-down, the
  lowest water temperature that still warms it in time, the planned start
  ("starts heating at 07:10 to be 21 °C at 09:00") and the night advice; the
  heating curve, the burner and the last ten self-tuning changes. The
  Heating view keeps a short summary after the rooms.
- **Plain-language names and texts** in English, Dutch and Polish, the same
  words as the E32 pages. Existing entity IDs stay; only a new installation
  gets IDs from the new names.
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
  restore summary names both. A restore keeps the rooms' mode from the
  backup; a new or reset E32 still waits for your takeover confirmation.

## Fixed

- A backup with accented letters in room or sensor names could be refused as
  too large before it reached the E32.
- An undo of a restore that the E32 refused no longer loses the "before a
  restore" backup.
- Setting the house mode and the away temperature right after each other no
  longer drops one or reverts the other.
- "Ready to take over?" no longer shows "None °C" for a value the E32 does
  not know yet.

## Updating

1. Install HA 1.0.0rc2 (HACS or the release ZIP) and restart Home Assistant.
2. Update the E32 with its Firmware entity, while someone is home.
3. Right after that, confirm the takeover again under Repairs.
4. If the E32 still has the factory password, the Repairs item sets a new one
   on the E32 and in Home Assistant in one step.

**From a manual install to HACS**, without a duplicate: keep the integration
as it is (do not delete it under Devices and services) and make a Home
Assistant backup. In HACS add the custom repository above, open
OpenThermostat, switch on beta versions and download 1.0.0rc2. HACS writes to
the same `custom_components/open_thermostat` folder and replaces the manual
files. Restart Home Assistant: still one OpenThermostat entry, same entities.
Keep no copy of the old folder inside `custom_components`.

Entity IDs and history are kept. Most new features need E32 1.0.0-rc.2.

## Limitations

Radiator valve control is not yet verified on real valves. The three-way
valve position cannot be seen behind an EMS adapter that leaves byte 7 of
telegram 0x18 empty. EMS Classic boilers only; EMS+ comes in 1.1. Writing
boiler settings comes after 1.0. HACS lists OpenThermostat as a custom
repository, not yet in the default HACS list.
