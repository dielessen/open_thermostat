# HA 1.0.0rc7 — more on the cards, a Connection page, and plainer names
<!-- user-release-notes:v2:en -->

Companion of E32 1.0.0-rc.5 (also runs with rc.4 until you install rc.5).
Needs Home Assistant 2026.10.0 or newer.

## New

- **Room cards show the week program:** under the reason, the level now and the
  next step: "Comfort until 22:30, then Night 18.0 °C". It is left out while
  something else holds the room (away, holiday, open window, a temporary
  change).
- **The house card says more:** the burner power and the boiler's display code
  ("burner 37 % · code -H"), the hot water temperature, and the burner starts
  in the last hour.
- **Diagnostics starts with "Connection with the E32":** does the E32 report,
  do the room values reach it (if not: since when, what it refused, and what to
  do), does the MQTT broker work, and which firmware runs.
- **"Your boiler" in lines:** highest water temperature, rest and lowest water
  temperature, each with what the E32 does because of it.
- **The knowledge ring is honest:** it shows 100 % and "It has learned
  everything it needs" only when nothing is missing.
- Trial run: the Comparison tiles have names a phone shows in full.

## Fixed

- **Plain language:** the Today card no longer says "warms up from 9:00 to be
  warm at 9:00" (it says the room is warm enough by itself), the learning
  progress no longer says "6 of 6", the rooms chip says "Learned", the burner
  power graph says "%" without "not kW", and a day with one outdoor
  temperature says it once.
- **Today and Learning, in plain words:** no warm-up is announced while the
  house is away, on holiday or a window is open; the start includes free heat;
  the trial run says "would". "Did not get warm within 3 hours" replaces "180
  minutes late", "next time it starts a little earlier/later" replaces a
  percentage, and "0.0 °C too warm" is gone. Once judged, "Today it was warm 2
  minutes late" (not "This morning": the judged step can be in the afternoon).
  A room renamed in Home Assistant keeps its learned lines. The weather line
  says what the learned line gives and what it sends when a room asks for heat.
  One outdoor temperature on the Overview; times as 06:10; plurals, hours and
  dates ("5 Nov") correct; Polish grammar; proposals are never shown as "Latest
  change"; night advice names the currency and "until {time}"; with a gas meter
  Yesterday shows the measured m³. The week card marks unsaved changes per tab
  and asks before Reload.
- **Room values reach the E32 reliably:** they are sent again at once when the
  E32 comes back or restarts, and a source that froze for 3 hours is no longer
  sent as fresh. A renamed source is followed; a removed one raises a repair
  after 10 minutes. The "values not accepted" repair now says since when and
  why.
- A new Dutch installation no longer doubles the room in entity IDs
  (`sensor.woonkamer_reden`, not `sensor.woonkamer_woonkamer_reden`).
- Firmware installs that fail say where (download, check, upload, not
  confirmed). Choosing the house mode Holiday uses the next planned holiday or
  tells you what to do. Window and door wording is the same everywhere.
- **Names changed** (entity IDs did not; check automations that use names):
  "Burner starts today" is now "Burner starts (total)", likewise Burner time and
  Missed comfort time; scoreboard sensors say "(yesterday)";
  "Temperature without Home Assistant" is "Temperature without a week program";
  "Boiler request" sensor is "Requested water temperature"; "Knowledge" is
  "Known about your house".

## Updating

1. Update OpenThermostat in HACS (switch **Pre-release** on, or it is not
   offered) and restart Home Assistant.
2. E32 rc.5 stays as it is; there is nothing to do on the E32.

Entity IDs and history are kept. On the first start a one-time tidy-up runs:
the degree-day statistics get their new unit (kWh/°C·d, numbers unchanged) and
the old "Device uptime" statistics are deleted. No repair is shown. New
entities are placed under Configuration (settings) or Diagnostics (figures)
instead of the main list. A Dutch installation made with rc.5 or rc.6 keeps its
doubled IDs; Configure → Advanced → **Tidy entity IDs** can fix them.

## Limitations

The E32's own page still says "6 of 6 warm-ups seen" (firmware, next release).
The knowledge sentences come in the E32's language, not Home Assistant's.
Radiator valve control is not yet verified on real valves. EMS Classic boilers
only; EMS+ comes in 1.1. Pairing Bluetooth sensors is done on the E32. HACS
lists OpenThermostat as a custom repository.
