# OpenThermostat

Local, open source heating software for **room schedules, radiator valves and
EMS boiler diagnostics**, with Home Assistant and a BBQKees E32 V2 gateway.
Developed independently by **Mark Dielessen**.

Set up rooms, select your Home Assistant devices, edit weekly schedules and
inspect what your boiler reports. **E32 beta.17 runs room heating control in
shadow mode:** the E32 keeps its own room plan, calculates the boiler request
and compares it with the thermostat that still controls the boiler, but it does
not send that request yet. Automatic boiler and valve control remain disabled
until an attended switch-over with failure tests.

[Downloads](https://github.com/dielessen/open_thermostat/releases) ·
[Features](#features) · [Roadmap](#roadmap) · [Screenshots](#screenshots) ·
[Installation](#installation) · [Documentation](#documentation)

<!-- openthermostat-readme-releases:start -->

## Latest published releases

| Component | Version | Channel |
| --- | --- | --- |
| E32 V2 firmware | [v0.1.0-e32v2-beta.18](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-beta.18) | Pre-release |
| Home Assistant integration | [0.4.0b10](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0b10) | Pre-release |

Firmware and the HA integration are separate downloads. Read each release’s
changes, compatibility notes and installation instructions before updating.

To build the published E32 firmware, start from its exact tag:

```sh
git clone --branch v0.1.0-e32v2-beta.18 https://github.com/dielessen/open_thermostat.git
```

<!-- openthermostat-readme-releases:end -->

**E32 beta.17 + HA 0.4.0b9** (the unpublished beta.16 is included):

- **Rooms and heating on the E32**, so heating keeps working without Home
  Assistant: room state (active, inactive, inactive until), emitter, up to four
  temperature sources in order (an HA entity such as a thermostat, or a
  Bluetooth sensor), a week program per room and a calculated flow request
  between 30 and 60 °C. One room plan is edited from HA and from the E32 page,
  with a revision number so neither side silently overwrites the other.
- **Shadow comparison:** heating time, burner starts and flow range of the E32
  decision next to the current thermostat, per day.
- **Home Assistant:** rooms, the E32's Bluetooth sensors and the heat request
  as entities; room state and fallback setpoint can be changed from HA; firmware
  updates are installed from HA over the local network.
- **Reliability:** the Bluetooth page no longer exhausts the E32's memory, a
  supervisor and hardware watchdog restart a hung device and keep a record of
  what it was doing, and boiler reception recovers by itself after a bus error.
- **One EMS entity table** feeds the firmware and the HA entities.

[Current release work](docs/modern-thermostat/NEXT-RELEASE.nl.md) ·
[Firmware release notes](docs/modern-thermostat/RELEASE-NOTES.md) ·
[HA release notes](docs/modern-thermostat/HA-RELEASE-NOTES.md)

## Features

**Available** means delivered for the stated use. **Prepared** means code exists
but the complete user flow, device connection or physical acceptance is still
open. **Planned** means further implementation or qualification is required.

### Rooms and comfort

| Feature | Current status |
| --- | --- |
| Room setup | **Available:** name rooms and select HA sensors, radiator valves, emitter types and temperature limits. Current setup supports 1–2 rooms, with one valve per room. |
| Weekly schedules | **Available:** edit temperature blocks, including touch controls, save and apply with confirmation. |
| Temperature targets and HEAT/OFF | **Available as control intent** through the native HA climate entity. Physical execution remains gated. |
| Original sensor and valve reports | **HA reception and diagnostics delivered.** Original Zigbee report producers, source qualification and physical valve feedback still need acceptance. Cached values are distinguished from original measurements. |
| Hysteresis, PI and slow time-proportional control | **Prepared** in the control core, including minimum cycle times. PI has no derivative term; locally regulating TRVs keep their own control loop. |
| Comfort, eco, away, holiday and boost | Priority and expiry logic **prepared**; complete everyday controls remain to be connected. |
| Window and door contacts | **Planned user flow:** select contacts per room, pause demand while open and resume with valid readings. Context logic exists; source selection, multiple contacts, status and stale-data handling still need completion. |
| Learning and optimum start | Models and storage **prepared**. Active learning, earlier starts, residual-heat use and heating-curve adaptation need real measurements and comfort validation. |
| Eight zones and multiple valves per room | **Planned.** The current room editor does not provide these capacities. |

Selecting a sensor does not qualify it as a control source. TV02 mode conflicts
are visible, but physical valve commands and fresh causal feedback remain open.

### Boiler and EMS

| Feature | Current status |
| --- | --- |
| Boiler brand/model selection | **Available:** catalogue with 60 choices, EMS-ESP product groups and official model references. Listing a model does not qualify a new driver. Product images are hosted outside the ESP. |
| Passive EMS reception | **Available:** Classic boiler messages, temperatures, targets, modulation and other supported fields. Coverage depends on the boiler and messages actually received. |
| Boiler entities and settings | **Available on Boiler test:** received devices/values and protocol references, access labels and filters, plus all 258 pinned EMS-ESP boiler definitions. E32 support and write permission are shown separately. Existing EMS devices links redirect here. |
| Classic and EMS Plus | Decoder foundations **available**; field coverage is model dependent. This is not full EMS-ESP parity. |
| Boiler values in HA | **Available:** 69 Classic field definitions, quality and source age, with an overview and three history charts. Reported and derived values stay separate. |
| Data quality | **Available:** measured, derived, stale, unreliable and unavailable values remain distinguishable. |
| Boiler diagnostics | Passive reception, protocol information, counters and report download **available**. Beta.5 supports an attended Ecomline Classic trial at 40–50 °C for up to ten minutes: zero baseline, separate start, supervision and Stop. Physical qualification remains open. |
| Heating demand, modulation and weather compensation | Calculations and policies **prepared**. Automatic EMS regulation, full outside-source setup, flow conditions and installation tests remain open. The attended trial uses its own guarded route. |
| Boiler settings | Writable-entity metadata is inventoried. Four Classic settings have a guarded source implementation: heating enabled, heating temperature, minimum burner period and pump delay. **Persistent setting writes remain disabled.** This does not provide all writable EMS-ESP entities. |
| Domestic hot water | **Readout where supported.** Model-specific control is planned. |
| Underfloor heating and mixed emitters | Group limits and control foundations **prepared**; active valve, pump and mixer routes require separate hardware acceptance. |

Reported modulation describes the boiler's response; calculated demand describes
the controller's intention. Neither proves that a command was sent or accepted.
The current Ecomline Classic installation has no digital pressure sensor; no
synthetic pressure reading is substituted.

### Home Assistant and daily use

| Feature | Current status |
| --- | --- |
| Native HA integration | **Available:** room pages, configuration, climate controls and weekly planner. Uses a local MQTT broker. |
| E32 web interface | **Available:** setup, room overview, calculated demand, boiler values, diagnostics and device management. |
| English and Dutch | **Available:** English default and fallback; E32 language selection and native HA translations. Stored dashboard text falls back to English. |
| Local Bluetooth sensors | **Available:** Shelly BLU H&T Display ZB, Xiaomi Monitor 3 / MJWSD05MMC with bindkey, thermometers with pvvx firmware (BTHome v2) and a Shelly BLU TRV diagnostic profile. Up to eight sensors are paired on the E32, can be room sources and appear in HA. Search lists the 32 strongest nearby devices. Private keys are stored separately and are not read back. GATT valve control remains open. |
| History and CSV | **Available:** read-only recorder views and exports for day/week/month periods up to 31 days. |
| ESP/EMS logs and syslog | **Available:** view, filter and download local logs; independently forward ESP/EMS sources to an RFC5424 UDP collector. External syslog is off by default. |
| Updates and recovery | **Available:** web login/logout, About, restart under Settings, updates from Home Assistant or the local upload on the update page, recovery routes, a supervisor and watchdog. Normal application updates preserve settings. |
| Energy, cost and comfort analysis | **Partly prepared**; actual sources, calibration and presentation remain open. |
| Standalone E32 heating | **Shadow mode:** rooms, sources, week programs and the flow request run on the E32 without HA; sending the request to the boiler needs the attended switch-over first. |
| External wall controls and further notifications | **Planned**, with additional device, ownership and failure acceptance. |

Core operation has no mandatory thermostat cloud. Devices connected through HA
still depend on HA and MQTT. Software checks reject stale or unconfirmed input;
complete physical failure tests for HA, MQTT, sensors and the E32 remain open.

## Roadmap

1. Qualify original room measurements and physical valve commands with fresh feedback.
2. Qualify the E32/converter/boiler chain through a separately authorized,
   attended start/stop trial, then complete the evidence required for automatic heating.
3. Finish normal user flows for central settings, comfort modes, outside sources,
   and window **and door** contacts with per-room status and recovery.
4. Add qualified devices, multiple valves per room, eight tested zones and
   separately tested floor-heating functions.
5. Validate learning, optimum start and heating-curve adaptation against real results.

No release dates are promised for these steps. The
[workboard](docs/modern-thermostat/WORKBOARD.nl.md)
and [design plan](docs/modern-thermostat/PLAN.nl.md) track the detailed requirements
and remaining acceptance. Much of the engineering documentation is in Dutch;
GitHub-facing project and future release descriptions are maintained in English.

## Screenshots

<details>
<summary>Home Assistant room editor and weekly planner — demonstration</summary>

![Home Assistant room editor and weekly planner with sample data](docs/img/screenshots/ha-room-dev24.png)

Demonstration of the delivered dev24 frontend using sample data, not a live HA capture.

</details>

<details>
<summary>E32 dashboard — historical alpha18 capture</summary>

![E32 dashboard with room demand, targets and boiler status](docs/img/screenshots/e32-dashboard-alpha18.png)

Actual alpha18 capture. Calculated demand, reported boiler status and permission
to control physical outputs are shown separately.

</details>

<details>
<summary>Passive EMS diagnostics — historical alpha18 capture</summary>

![E32 passive Classic EMS reception and field quality](docs/img/screenshots/e32-keteltest-alpha18.png)

Actual alpha18 capture of passively received Classic messages. Transmission and
active trial controls are blocked.

</details>

## Installation

Download the E32 firmware and the HA integration separately from the release
links above. For the native HA connection, configure Home Assistant's MQTT
integration and a local MQTT broker. Follow the release's compatibility notes.

- **E32 application update:** install it from Home Assistant (the firmware
  update entity) or upload `firmware.bin` on the E32 update page. A new
  partition layout or factory installation uses a different procedure.
- **Home Assistant:** install the separate integration package; the E32 updater
  does not install it.
- **Optional Zigbee report companion:** source-only material for original
  receive reports; no automatic installation or valve-control enablement.

Back up first, then verify the new boot, version and retained settings.
See [installation and recovery](docs/FLASHING.md),
[update packages](docs/modern-thermostat/GITHUB-UPDATES.nl.md) and
[HA setup](docs/modern-thermostat/HA-MANAGED-GUI.md).

## Hardware and development

The main target is **BBQKees E32 V2**: classic ESP32, 16 MB flash and physical
PSRAM. It differs from the original E32 and ESP32-S3. The `esp32dev` and
`esp32s3` builds remain supported as source targets; their output capabilities
do not automatically apply to E32 V2. Network and recovery acceptance is
installation specific.

Use the tagged clone command above, then build locally:

```sh
cd open_thermostat
python3 -m venv .venv
. .venv/bin/activate
pip install platformio==6.2.0 intelhex==2.3.0
pio run -e e32v2
pio run -e e32v2 -t buildfs
python3 scripts/verify_e32v2.py
pio test -e native
```

These commands build and verify files. Run PlatformIO operations sequentially
within a checkout. Other source targets use `pio run -e esp32dev` or
`pio run -e esp32s3`.

## Documentation

- [Current release work](docs/modern-thermostat/NEXT-RELEASE.nl.md)
- [Firmware release history](docs/modern-thermostat/RELEASE-NOTES.md)
- [Home Assistant release history](docs/modern-thermostat/HA-RELEASE-NOTES.md)
- [E32 V2 hardware and pins](docs/BBQKEES_E32V2.md)
- [Hardware differences](docs/HARDWARE.md)
- [REST API](docs/RESTAPI.md)
- [Test infrastructure](docs/modern-thermostat/TEST-INFRA.nl.md)
- [Third-party sources and licences](docs/third-party/README.md)
- [Legacy project documentation](docs/README-LEGACY.md)

## Credits and licence

This project derives from [OpenThermostat by Pawel Filipczak / intuibase](https://github.com/intuibase/open_thermostat).
Original copyright notices and the [MIT licence](LICENSE) are preserved.
Further development, product decisions and releases are independently maintained
by Mark Dielessen; this is not an official intuibase release.

Reused libraries and SDK components retain their own licences. The
[third-party documentation](docs/third-party/README.md) describes source
availability, redistribution and relinking information.
