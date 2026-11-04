# E32 V2 1.0.0-rc.4 — the fourth 1.0 candidate: learning that works from day one, a holiday planner and a sturdier E32
<!-- user-release-notes:v2:en -->

The fourth 1.0 candidate. Smart warm-up now heats early from the first
morning and learns from every morning whether it was on time; you can plan
holidays ahead with their own temperature; the E32 shows why each room heats,
also without Home Assistant; and 16 robustness fixes from a full code review.
If it runs 14 days without problems with the E32 controlling the boiler, the
same code becomes 1.0.0. Install it with HA 1.0.0rc5.

## New

- **Smart warm-up from day one:** until now the E32 waited until it had
  learned both how fast a room warms up and how fast it cools down, and a
  store boiler's keep-warm rounds kept the cooling model from ever being
  learned. It now starts early at once, as an estimate (2 h per degree for a
  floor, 45 min for radiators, at most 3 h or 90 min), and the pages say so:
  "starts at 07:40 (estimate; it learns from every morning)".
- **It checks every morning:** was the room warm at the program time? Late by
  more than 10 min: the next start is 10 % earlier; early by more than
  15 min: 8 % later. Home and Home Assistant show "Yesterday warm at 09:12
  (12 min late); tomorrow 10 % earlier." Cooling is now learned despite the
  keep-warm rounds, and the warm-up time counts as learned after one water
  temperature instead of two.
- **Holiday planner:** plan holidays ahead (up to 8) with their own holiday
  temperature, on the Home page and in Home Assistant. A holiday starts and
  ends by itself, the house returns to the mode it had, and the rooms warm up
  before you come home. A "Holiday until" date set earlier is converted once.
- **Yesterday in figures** (Home and HA): heating hours, burner starts per
  heating hour, short burner runs, gas for heating (estimate), degree-days,
  and per room how many minutes late or early it was warm and how far it
  overshot. Kept over a restart.
- **Why each room heats** on the E32's Overview, in the same words as Home
  Assistant (off, window open, no reading, hot water, boiler rest, holiday,
  away, Smart warm-up heating early, warm enough), with icons for who is
  home and open windows. The Overview now also shows the E32's own rooms
  when Home Assistant is not linked.
- **Clearer pages:** one "Heating on" label instead of two, at most two
  labels on a phone; frequent burner starts are shown as learning information
  ("the E32 lengthens the burner rest step by step") instead of a warning;
  "Weather compensation" is the name of the former heating curve, with
  "Water temperature in hard frost (−10 °C)"; the learned card is two lines
  per room with "More"; Sign out is in the System menu.
- **Self-tuning that keeps going:** the day's counters survive a restart, a
  restart waits 2 hours instead of a day, and renaming a room or changing
  the away temperature no longer starts the learning day over.
- **Hot water counters** (today and the last 7 days) survive a restart; the
  boiler's own counters are hidden while the boiler never reports them.

## Fixed

- A firmware upload, a Wi-Fi setup restart or an unreadable room plan no
  longer leave the boiler with an open heat request: the E32 withdraws it
  first, also after a restart.
- Rolling back checks that the previous firmware is really there before it
  clears anything; the update page shows which version it would go back to.
- Web responses to a slow or stalled client are bounded, so the E32 stays
  responsive; a web update blocked by the update gate is refused before its
  body is read; the heating curve accepts exactly nine points.
- MQTT: a replacement message that does not fit no longer drops the one
  waiting; reconnects back off (5 s up to 60 s) instead of hammering the
  broker.
- Storage: comfort, valve and holiday records make room for themselves like a
  plan save and are never refused silently; the E32 keeps room for every
  learned room.
- Pages: Save rooms saved twice; a typed away temperature or holiday date
  was lost on the 10-second refresh; a stored date shifted a day; two failed
  refreshes now show a notice; the boiler card retries a failed read.
- Reordering or renaming rooms keeps what the E32 learned and measured for
  them (warm-up starts, the self-tuning's evidence, the arrival check).
- A hung main loop restarts after one minute instead of five; the 10-second
  heartbeat lines are gone from the log.

## Updating

From 1.0.0-rc.3, while someone is home. First install HA 1.0.0rc5 (HACS)
and restart Home Assistant, then press Install on the E32's Firmware entity.
Then confirm the takeover again: a firmware change clears it, and until then
the E32 keeps only frost protection. Repair "Confirm again that the E32 may
control the boiler", or Rooms on the E32.

- Settings, rooms, programs, sensors, valves and learning are kept. Smart
  warm-up starts heating early from the first morning after the update.
- A holiday set with "Holiday until" before this update becomes a planned
  holiday with the away temperature.

## Limitations

Radiator valve control is not yet verified on real valves. Behind an EMS
adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter) the three-way valve position cannot be seen. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
Pairing Bluetooth sensors is done on the E32. Charts are lost on a restart.
