# OpenThermostat 1.0 candidate — release notes draft

Draft only. Not frozen, tagged, published or installed. The published E32
beta22, HA 0.4.0b14 and HA 0.4.0b15 downloads are unchanged.

At the release step, the version-only commit moves the two sections below to
the top of `RELEASE-NOTES.md` and `HA-RELEASE-NOTES.md`, with the final
headings (planned: `# E32 V2 1.0.0-rc.1` and `# HA 1.0.0rc1`, see
STABLE-RELEASE-TAGS.en.md). `verify_publication_notes` only reads the top
section of each file; each section must stay under its 6 KB limit.

Written against `release-1.0` at 7916d31: all 1.0 work merged on top of
beta22 / HA 0.4.0b15.

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
  date (warm again in time), plus the flow limits, the heating curve and the
  learned flow. Away is now only a house mode.
- **Persons per room:** a room with its own persons drops to the away
  temperature when they are all away, even while others are home.
- **Week planner:** Comfort, Eco and Night per room, each set on its own;
  changing a level changes all its blocks. "Away" in the planner is now Eco.
  Also step-by-step undo, Copy… and a block list on a phone.
- **Room page:** collapsible blocks with a one-line summary each, a window
  pause delay per room (default 2 minutes) and Discard changes.
- **Radiator valves per room**, off by default: Zigbee2MQTT valves (Bosch
  BTH-RA, Sonoff TRVZB and TRV Gen2, Tuya TV02, others) driven by the E32
  itself, or any valve Home Assistant controls. Valves are driven only while
  the room's Valve control is on and you have confirmed the takeover. Valve
  positions keep the flow as low as possible; when all valves are closed the
  boiler request stops, within the burner's minimum on and off times.
- **Ready to take over?** In shadow mode the Rooms page shows a checklist:
  72 hours stable, enough heating periods compared, matching timing, the
  flow limit kept and every room measured.
- **Tuning as settings:** Home → Advanced: tuning holds ten bounded control
  settings, such as the burner minimum on and off times. The defaults behave
  exactly as before; leave them unless advised. Safety limits are not
  adjustable.
- **The boiler's display code in words** on the home and Boiler pages, from
  the manufacturers' manuals, with what to do on a fault. Eleven boiler
  families (Nefit, Buderus, Bosch, Worcester Bosch) plus a generic EMS table;
  an unknown code shows as the raw code.
- **What the boiler is doing now** (heating, tapping, keeping warm, charging
  a cylinder) and a hot-water strip in the 24-hour chart.
- The E32 reads the identity of every device on the EMS bus by itself.

## Fixed

- Safer active control: after a restart or an update while it ran the
  boiler, the E32 first sends a zero request, so an old heat request never
  lingers. After an update it keeps frost protection while it waits for your
  new confirmation (it used to keep none), and confirming then takes over at
  once.
- "Hand back to the thermostat" stops the E32 first, then saves the plan.
- Values that an EMS adapter leaves at 0 while the boiler works (such as the
  selected flow behind the Bosch EasyControl Adapter) now read "Not
  reported" instead of a misleading 0 °C or Off.
- Hot water is split correctly into tapping and keeping warm: short reheats
  of a store no longer count as taps.
- The web pages use less internal memory per answer.

## Updating

Install while someone is home. A firmware change clears the takeover
confirmation: if the E32 controlled your boiler, it keeps only frost
protection after the update until you confirm the takeover again (Repairs in
Home Assistant, or Rooms → Active control). Do that right after the update.

Update the integration to HA 1.0.0rc1 first, restart Home Assistant, then
press Install once on the E32's Firmware entity. Settings, rooms, week
programs and Bluetooth sensors are kept. Radiator valve control stays off
until you switch it on per room. New installers: follow docs/INSTALL.md;
docs/INSTALL-CHECK.md is a checklist for a second person.

## Limitations

Radiator valve control is not yet verified on real valves. On boilers behind
an EMS adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter), the three-way valve position cannot be seen. EMS Classic
(EMS 1.0) boilers only; EMS+ comes in 1.1. Writing boiler settings comes after
1.0. Charts are lost on a restart.

---

# HA 1.0.0rc1 — the 1.0 candidate: radiator valves, house mode, daily backups and a daily summary
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0 candidate. Needs Home Assistant 2026.10.0
or newer.

## New

- **Daily E32 backups:** Home Assistant saves the E32's settings once a day
  (the last 7 days, inside Home Assistant's own backups), with a "Back up E32
  settings now" button and a Repairs item after 3 days without one. Configure
  → Advanced → Restore settings to this E32 puts a backup on a new or reset
  E32; it shows what changes first and comes back in shadow mode.
- **Configure menu:** Rooms · Home · E32 connection · Dashboard and name ·
  Advanced. Window contacts (up to 8), persons and the window pause delay are
  set in each room; room defaults and presence under Home.
- **House mode and presence:** a House mode control (Automatic, At home,
  Away, Holiday until a date) and several people: the house is away once
  everyone has been away for 15 minutes, counted from when the last person
  left. The Away actions for automations set the house mode.
- **Week planner:** independent Comfort, Eco and Night levels per room; room
  presets Comfort, Eco, Night and Boost.
- **Radiator valves per room**, off by default: Zigbee2MQTT valves or any
  climate entity (ZHA, Z-Wave, Shelly, cloud) under Configure → Rooms →
  Radiator valves, with position, battery and problem entities, the opening
  on the dashboard and Repairs for a low battery or a silent valve.
- **Daily summary** on the Heating view: burner time and starts, short runs,
  time to target, missed comfort, outdoor temperature and gas per day,
  including keeping hot water warm.
- **Warnings** for a room that stays cold or a lost E32 link; every heating
  problem is also a Repairs item that clears itself.
- **Takeover readiness** sensor: the E32's "Ready to take over?" check.
- **Display code in words** on the Heating view; the sensor keeps the raw
  code, so history and automations are unchanged.
- **Hot water split** into tapping and keeping warm, with gas for each, a
  boiler activity timeline and an optional water meter (Configure → Home →
  Energy).
- The devices on the EMS bus appear as Home Assistant devices (and go away
  24 hours after they leave the bus). A boiler power is suggested, but only
  stored when you save your own.
- **Tidy entity IDs** (Configure → Advanced, optional): preview, where each
  ID is used (also scenes), rename with history, undo within 30 days.

## Fixed

- Changes made in Home Assistant no longer fail when all four E32 web
  sessions are busy: writes wait for a free session (up to about 2.5
  minutes), and only the newest change per room is sent.
- Values your boiler never sends are hidden instead of reading "unknown";
  the old "unavailable" MQTT entities from before the current E32 link are
  removed once.
- Memory in kB and uptime in hours also on existing installations, and the
  repeated TV02 notice is gone.
- Help texts name the real E32 menu paths, such as System → Network and Home
  Assistant.
- After an E32 firmware update, Repairs shows one "Confirm the takeover
  again" item.

## Updating

Install HA 1.0.0rc1, restart Home Assistant, then update the E32 to the 1.0
candidate with the Firmware entity, while someone is home. Then confirm the
takeover again under Repairs. The first E32 backup follows shortly after the
start. Most new features need the new E32 firmware; older firmware keeps
working as before. Entity IDs and history are kept.

## Limitations

Radiator valve control is not yet verified on real valves. The three-way
valve position cannot be seen behind an EMS adapter that leaves byte 7 of
telegram 0x18 empty. EMS Classic boilers only; EMS+ comes in 1.1. Writing
boiler settings comes after 1.0. No HACS listing yet: install from the
release ZIP.
