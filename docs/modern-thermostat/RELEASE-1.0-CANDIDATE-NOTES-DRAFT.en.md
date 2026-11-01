# OpenThermostat 1.0 candidate — release notes draft

Draft only. Not frozen, tagged, published or installed. The published E32
beta22, HA 0.4.0b14 and HA 0.4.0b15 downloads are unchanged.

At the release step, the version-only commit moves the two sections below to
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md`, with the final
headings (planned: `# E32 V2 1.0.0-rc.1` and `# HA 1.0.0rc1`, see
STABLE-RELEASE-TAGS.en.md). Every `TODO` line must be resolved or removed
first; `verify_publication_notes` only reads the top section of each file.

Written against `release-1.0` at a81d991 (16 merged branches on top of
beta22 / HA 0.4.0b15).

- TODO: automatic E32 backups in Home Assistant, with restore onto a new E32
  (branch 10-ha-backup, not on release-1.0 yet). Add a New line to both
  sections once merged.
- TODO: the internal-heap fix (branch 10-heap, not on release-1.0 yet). Add a
  Fixed line to the E32 section once merged, describing what the user noticed.
- TODO: the install-guide review (branch 10-docs, not on release-1.0 yet).
  Mention the reviewed docs/INSTALL.md under Updating once merged.
- TODO: the learning tuning from about a week of active control (from
  1 Nov 2026). The merged tuning branch adds review tools and an opt-in
  hot-water bridge with the defaults unchanged, so nothing is claimed below;
  add a line only if a later change alters what the user sees.

---

# E32 V2 1.0.0-rc.1 — the 1.0 candidate: radiator valves, house mode and a clearer boiler
<!-- user-release-notes:v2:en -->

The first 1.0 candidate. It brings together everything planned for beta23,
beta24 and 1.0 in one release. If it runs 14 days without problems, with the
E32 controlling the boiler and the radiator valves, the same code becomes
1.0.0. Install it together with HA 1.0.0rc1 (see Updating).

## New

- **One menu:** Overview · Rooms · Home · Boiler · System. System holds
  Network and Home Assistant, Password, Backup and restore, Bluetooth
  sensors, Firmware update, Diagnostics and About. Old links still work.
- **Home page and house mode:** Automatic, At home, Away and Holiday until a
  date (warm again in time). It also holds the flow limits, the heating
  curve and the learned flow. Away is now only a house mode.
- **Persons per room:** a room with its own persons drops to the away
  temperature when they are all away, even while others are home.
- **Week planner:** Comfort, Eco and Night per room, each set on its own.
  Changing a level changes all its blocks. "Away" in the planner is now Eco.
  Also: step-by-step undo, Copy…, and a block list on a phone.
- **Room page:** collapsible blocks (Temperature, Week program, Windows and
  doors, Persons) with a one-line summary each. Window pause delay per room
  (default 2 minutes), and Discard changes next to Save.
- **Radiator valves per room**, off by default: Zigbee2MQTT valves (Bosch
  BTH-RA, Sonoff TRVZB and TRV Gen2, Tuya TV02, others) driven by the E32
  itself, or any valve Home Assistant controls. Valves are only driven while
  the room's Valve control is on and the E32 runs the boiler. Valve positions
  keep the flow as low as possible; when all valves are closed the boiler
  request stops.
- **The boiler's display code in words** on the home and Boiler pages, from
  the manufacturer's manuals for the chosen boiler model, with a warning or
  error box and what to do. An unknown code shows as the raw code.
- **What the boiler is doing now** (heating, tapping, keeping warm, charging
  a cylinder) and a hot-water strip under the burner in the 24-hour chart.
- The E32 reads the identity of every device on the EMS bus by itself a few
  minutes after start-up.

## Fixed

- After an unexpected restart while it controlled the boiler, the E32 first
  sends a zero request, so an old heat request no longer lingers in the
  boiler.
- After a firmware update the E32 keeps frost protection while it waits for
  you to confirm the takeover again (it used to keep none).
- "Hand back to the thermostat" now stops the E32 first and then saves the
  plan as shadow, with a clear message if either step fails.
- Hot water is sorted into tapping and keeping warm correctly: short reheats
  of a store are no longer counted as taps.

## Updating

Install while someone is home. A firmware change clears the takeover
confirmation: if the E32 controlled your boiler, it keeps only frost
protection after the update until you confirm the takeover again (Repairs in
Home Assistant, or Rooms → Active control). Do that right after the update.

Update the integration to HA 1.0.0rc1 first, restart Home Assistant, then
press Install once on the E32's Firmware entity. Settings, rooms, week
programs and Bluetooth sensors are kept. Radiator valve control stays off
until you switch it on per room.

## Limitations

Radiator valve control is not yet verified on real valves. On boilers behind
an EMS adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter), the three-way valve position cannot be seen. EMS Classic
(EMS 1.0) boilers only; EMS+ comes in 1.1. Writing boiler settings comes after
1.0. Charts are lost on a restart.

---

# HA 1.0.0rc1 — the 1.0 candidate: radiator valves, house mode and a daily summary
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0 candidate. Needs Home Assistant 2026.10.0
or newer.

## New

- **Configure menu:** Rooms · Home · E32 connection · Dashboard and name ·
  Advanced. The separate Comfort menu is gone: window contacts are set in
  each room, room defaults under Home.
- **House mode and presence:** a House mode control (Automatic, At home,
  Away, Holiday until a date) and several people for presence: the house is
  away only once everyone has been away for 15 minutes. The Away actions for
  automations now set the house mode.
- **Persons per room** in the room settings, and a window pause delay per
  room.
- **Week planner:** independent Comfort, Eco and Night levels per room; room
  thermostat presets Comfort, Eco, Night and Boost.
- **Radiator valves per room**, off by default: pick Zigbee2MQTT valves or
  any climate entity (ZHA, Z-Wave, Shelly, cloud) under Configure → Rooms →
  Radiator valves. Each room gets Valve control, Valve position, Valve
  battery and Valve problem entities, and the dashboard shows the opening.
  Low battery or a silent valve is a Repairs issue.
- **Daily summary:** burner time, starts, short runs, time to target, missed
  comfort, outdoor temperature and gas per day, in a "Yesterday" section on
  the Heating view.
- **Warnings** for a room that stays cold for 3 hours or a lost E32 link;
  every heating problem is now also a Repairs issue that clears itself.
- **Display code in words** on the Heating view, with what to do on a fault.
  The sensor keeps the raw code, so history and automations are unchanged.
- **Hot water split** into tapping and keeping warm: gas for each, a boiler
  activity timeline, and an optional water meter (Configure → Home → Energy)
  that tells them apart more reliably.
- The devices on the EMS bus appear as Home Assistant devices, and a boiler
  power is suggested so the gas estimates work without typing one in.
- **Tidy entity IDs** (Configure → Advanced, optional): preview, where each
  ID is used, rename with history, undo within 30 days.

## Fixed

- Values your boiler never sends are disabled and hidden instead of reading
  "unknown"; they come back by themselves when a value arrives.
- The old "unavailable" MQTT entities from before the current E32 link are
  removed once; entities you changed stay.
- Memory shows in kB and uptime in hours also on existing installations.
- The repeated TV02 notice for a TV02 used only as a temperature source is
  gone.
- After an E32 firmware update, Repairs offers "Confirm the takeover again".

## Updating

Install HA 1.0.0rc1, restart Home Assistant, then update the E32 to the 1.0
candidate with the Firmware entity, while someone is home. Then confirm the
takeover again under Repairs. Most new features need the new E32 firmware;
older firmware keeps working as before. Entity IDs and history are kept.

## Limitations

Radiator valve control is not yet verified on real valves. The three-way
valve position cannot be seen behind an EMS adapter that leaves byte 7 of
telegram 0x18 empty. EMS Classic boilers only; EMS+ comes in 1.1. Writing
boiler settings comes after 1.0. No HACS listing yet: install from the
release ZIP.
