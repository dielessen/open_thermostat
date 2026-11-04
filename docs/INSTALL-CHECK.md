# Installation checklist

For a second person who follows the [installation guide](INSTALL.md) from
start to finish, with a BBQKees E32 V2, an EMS Classic boiler and, if used,
Home Assistant 2026.10.0 or newer. Follow only the guide and the
[user guide](USER-GUIDE.md). Every question you have to ask someone is a gap
in the guide: write it down.

For each step, tick it and note **done**, **done with trouble** or
**stuck**, with the time it took and anything that did not match (a word, a
button, a missing explanation).

## Before you start

- [ ] The newest E32 V2 release is downloaded, and you know which Home
  Assistant release its release notes pair with it (installed through HACS or
  from its ZIP).
- [ ] A USB-C data cable and a computer with Chrome or Edge (or Python for
  esptool).
- [ ] HACS in Home Assistant, or access to the Home Assistant configuration
  folder (for example the Samba share or File editor add-on).
- [ ] The existing thermostat stays connected to the boiler: this checklist
  switches nothing over (the boiler test and takeover are a separate step with
  someone at the boiler).

## Checklist

| Done | Step (INSTALL.md section) | Expected result | Where to look |
| --- | --- | --- | --- |
| [ ] | Firmware over USB (2) | The tool reports success; the MD5 equals "MD5 before first boot" | ESPConnect **Flash Integrity**, or `verify_flash`; `FACTORY-CHECK.txt` |
| [ ] | First start and Wi-Fi (3) | Network `OpenThermostat-xxxxxx` appears; the page shows **WiFi connected** and an address | Phone or laptop Wi-Fi list; `http://10.10.10.1/` |
| [ ] | E32 on the home network (3) | The E32 page opens at the saved address (or `openthermostat-xxxxxx.local`) | Browser; the router's device list |
| [ ] | Sign in and password (4) | Signed in with `admin` / `admin`, then your own password set; the Overview reminder is gone | E32 **System → Password** |
| [ ] | Menu (4) | Top menu Overview, Rooms, Home, Boiler, System; System lists Network and Home Assistant, Password, Backup and restore, Bluetooth sensors, Firmware update, Diagnostics and system log, About, Restart device | E32 menu bar |
| [ ] | Time zone and boiler reception (5) | Time zone chosen, **Boiler bus (EMS) on** ticked, saved, E32 restarted | E32 **System → Network and Home Assistant** (page "Settings"), sections **Time** and **Advanced settings → Hardware services** |
| [ ] | Connect to the boiler (6) | Flow and return temperature and status appear within a few minutes; no "Listening to the boiler bus (EMS) is off." | E32 **Boiler** |
| [ ] | Boiler model (6) | Your model is saved; the display code reads in words | E32 **Boiler → Boiler model**; **Display code** under **Now** |
| [ ] | Bluetooth thermometer (7, optional) | The sensor shows a temperature, not "Waiting" | E32 **System → Bluetooth sensors**, **Your sensors** |
| [ ] | MQTT broker (8.1, 8.2) | Broker running, MQTT integration added, a broker user for the E32 | HA **Settings → Add-ons** and **Settings → Devices & services** |
| [ ] | MQTT on the E32 (8.3) | Saved and restarted; the log shows a broker connection | E32 **System → Diagnostics and system log** (log, or console `mqtt`) |
| [ ] | Install the integration (9) | `<config>/custom_components/open_thermostat/manifest.json` exists; HA restarted | HACS lists **OpenThermostat** as downloaded; without HACS: HA file editor or Samba share |
| [ ] | Add the integration (10.1) | Form **Set up your heating installation** saved with **Add installation** | HA **Settings → Devices & services → Add integration → OpenThermostat** |
| [ ] | Connect the E32 (10.2) | **E32 connected** appears; the E32 Overview shows **Home Assistant: connected** | HA **Configure → E32 connection**; E32 **Overview** |
| [ ] | Configure menu (10.2) | Configure has six items: Rooms, House, Heating and boiler, Energy and outdoor temperature, E32 connection, Advanced and diagnostics; every submenu has **← Back**; **Done** closes it | HA **Settings → Devices & services → OpenThermostat → Configure** |
| [ ] | First room (11.1) | The room is on the E32 and in HA, with a temperature | HA **Configure → Rooms**; E32 **Rooms** (read-only, "Managed in Home Assistant") |
| [ ] | Room blocks on the E32 (11.1) | The room card opens; **Temperature**, **Week program**, **Windows and doors** and **Persons** fold open, each with a summary line when closed | E32 **Rooms** |
| [ ] | Week program (11.2) | **Comfort**, **Eco** and **Night** set, one day copied with **Copy…**, saved | HA dashboard **OpenThermostat**, tab **Week program**, or E32 **Rooms** |
| [ ] | Setting device (11.3, optional) | The device shows the program's temperature at the next switch point | The device or its app; the room's thermostat in HA |
| [ ] | Water temperature limits (11.4) | Limits checked or saved (**Save limits**) | HA **Configure → Heating and boiler → Water temperature limits**; E32 **Home → Water temperature limits** |
| [ ] | House mode and presence (11.5) | People chosen; changing **House mode** shows on the E32 Home page | HA **Configure → House → Presence and away temperature** and **Configure → House → House mode and holiday**; E32 **Home** |
| [ ] | Smart warm-up and Weather compensation (11.5) | Both are on; the **Learning and settings** tab says what the E32 uses | HA **Configure → Heating and boiler**; dashboard tab **Learning and settings** |
| [ ] | Persons per room (11.5, optional) | The room's persons are chosen; the E32 room card shows them | HA room form, section **Persons**; E32 **Rooms → Persons** |
| [ ] | Window contact (11.5, optional) | Open longer than **Pause after**: the room pauses; closed: it resumes | HA room form, section **Windows and doors**; E32 room card |
| [ ] | Check (11.6) | The **Overview** tab shows a status card for every room (temperature, target and why it heats or not); **Heating problem** is off; no **Heating needs attention** under Repairs | HA sidebar **OpenThermostat**; **Settings → System → Repairs** |
| [ ] | Route to the takeover (12) | With the old thermostat on the bus: **Trial run** and the line "Your boiler still gets requests from another thermostat, so the E32 first runs alongside it (trial run)"; without one: **Boiler test and takeover**, "Not run yet", and the E32 sends nothing to the boiler | E32 **Rooms**, section **Boiler test and takeover** |
| [ ] | Boiler test (12, optional, someone at the boiler) | Every step **Passed**, then "Last test: passed on …" (kept after a restart); or stopped with the steps to give control back; or **I have already done this test**: "Marked as done by you on …"; an E32 that controlled this boiler before: "Not needed" | E32 **Rooms**; the line "Boiler test: … · Open" on the E32 **Boiler** page; HA sensor *Ready for E32 control*, attributes `boiler_test`, `boiler_test_summary` |
| [ ] | Update through Home Assistant (13.3) | When a new release exists, **Install** runs and the E32 reports the new version | HA **Settings → Updates**, the **Firmware** entity |
| [ ] | Backup (14.1) | A backup file is downloaded, optionally with a passphrase | E32 **System → Backup and restore** |
| [ ] | Diagnostics console (user guide) | `status` and `log 20` answer | E32 **System → Diagnostics and system log** |
| [ ] | Daily summary (user guide, the day after) | **Daily summary** shows the last finished day | HA, the OpenThermostat device |

## After the check

- [ ] Every step done without help: the 1.0 criterion "an installation guide
  that someone else can follow" is met. Note the name (or anonymous), the
  date and the firmware and integration versions.
- [ ] Every note becomes a fix in the guide.
- [ ] Keep the filled-in list with the release records.
