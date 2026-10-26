# OpenThermostat

Local, open source heating software for **room schedules, radiator valves and
EMS boiler diagnostics**, with Home Assistant and a BBQKees E32 V2 gateway.
Developed independently by **Mark Dielessen**.

Set up rooms, select your Home Assistant devices, edit weekly schedules and
inspect what your boiler reports. The control and learning software is being
extended towards coordinated heating. **The current beta keeps physical boiler
and valve outputs disabled.** Active heating still requires installation and
hardware acceptance.

[Downloads](https://github.com/dielessen/open_thermostat/releases) ·
[Features](#features) · [Roadmap](#roadmap) · [Screenshots](#screenshots) ·
[Installation](#installation) · [Documentation](#documentation)

<!-- openthermostat-readme-releases:start -->

## Latest published releases

| Component | Version | Channel |
| --- | --- | --- |
| E32 V2 firmware | [v0.1.0-e32v2-beta.3](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-beta.3) | Pre-release |
| Home Assistant integration | [0.4.0b3](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0b3) | Pre-release |

Firmware and the HA integration are separate downloads. Read each release’s
changes, compatibility notes and installation instructions before updating.

To build the published E32 firmware, start from its exact tag:

```sh
git clone --branch v0.1.0-e32v2-beta.3 https://github.com/dielessen/open_thermostat.git
```

<!-- openthermostat-readme-releases:end -->

Published packages and installation acceptance are tracked separately. The last
recorded, independently checked installation is E32 beta.1 with HA 0.4.0b1;
beta.3 installation acceptance is still pending. Publication does not enable
physical heating.

**Next release:** E32 beta.4 is in preparation, with explicit web-session
recovery, 30-minute idle expiry, a local fallback boiler illustration and a
read-only heating-settings overview. It is not frozen or published. These
changes require no new HA package. The prepared settings editor remains disabled
in the standard firmware. [Current release work](https://github.com/dielessen/open_thermostat/blob/review/mark-vscode-20261021/docs/modern-thermostat/NEXT-RELEASE.nl.md).

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
| EMS devices page | **Available:** devices, entities, source quality, age, search and retained open details; English and Dutch. No active scan. |
| Classic and EMS Plus | Decoder foundations **available**; field coverage is model dependent. This is not full EMS-ESP parity. |
| Boiler values in HA | **Available:** 69 Classic field definitions, quality and source age, with an overview and three history charts. Reported and derived values stay separate. |
| Data quality | **Available:** measured, derived, stale, unreliable and unavailable values remain distinguishable. |
| Boiler diagnostics | Passive reception, protocol information, counters and report download **available**. Active trial controls remain blocked. |
| Heating demand, modulation and weather compensation | Calculations and policies **prepared**. Physical EMS control, full outside-source setup, flow conditions and installation tests remain open. |
| Boiler settings | Writable-entity metadata is inventoried. Four Classic settings have a guarded source implementation: heating enabled, heating temperature, minimum burner period and pump delay. **Physical writes remain disabled.** This does not provide all writable EMS-ESP entities. |
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
| Local Bluetooth diagnostics | **Delivered:** Shelly BLU H&T Display ZB, Xiaomi Monitor 3 / MJWSD05MMC with bindkey, and Shelly BLU TRV diagnostic profiles. Private keys are stored separately and are not read back. Device acceptance, GATT valve control and use as a heating source remain open. |
| History and CSV | **Available:** read-only recorder views and exports for day/week/month periods up to 31 days. |
| ESP/EMS logs and syslog | **Available:** view, filter and download local logs; independently forward ESP/EMS sources to an RFC5424 UDP collector. External syslog is off by default. |
| Updates and recovery | **Available:** web login/logout, About, restart under Settings, HTTPS updates and recovery routes. Normal application updates preserve settings. |
| Energy, cost and comfort analysis | **Partly prepared**; actual sources, calibration and presentation remain open. |
| Standalone E32 heating, external wall controls and further notifications | **Planned**, with additional device, ownership and failure acceptance. |

Core operation has no mandatory thermostat cloud. Devices connected through HA
still depend on HA and MQTT. Software checks reject stale or unconfirmed input;
complete physical failure tests for HA, MQTT, sensors and the E32 remain open.

## Roadmap

1. Qualify original room measurements and physical valve commands with fresh feedback.
2. Qualify the E32/converter/boiler chain and complete a separately authorized,
   bounded start/stop trial before enabling active heating.
3. Finish normal user flows for central settings, comfort modes, outside sources,
   and window **and door** contacts with per-room status and recovery.
4. Add qualified devices, multiple valves per room, eight tested zones and
   separately tested floor-heating functions.
5. Validate learning, optimum start and heating-curve adaptation against real results.

No release dates are promised for these steps. The
[workboard](https://github.com/dielessen/open_thermostat/blob/review/mark-vscode-20261021/docs/modern-thermostat/WORKBOARD.nl.md)
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

- **E32 application update:** use the normal GitHub updater with `firmware.bin`.
  A new partition layout or factory installation uses a different procedure.
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

- [Current release work](https://github.com/dielessen/open_thermostat/blob/review/mark-vscode-20261021/docs/modern-thermostat/NEXT-RELEASE.nl.md)
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
