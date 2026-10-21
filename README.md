# OpenThermostat E32 V2 — independent thermostat & Home Assistant project

**Our own locally controlled heating-software project, developed by Mark Dielessen,
combining E32 V2 firmware with a dedicated Home Assistant integration.**

This project started from [OpenThermostat by intuibase](https://github.com/intuibase/open_thermostat).
We are developing it independently: our product scope, architecture, maintenance
and release schedule are our own. It is not an official intuibase release or an
endorsed version of the original project. The repository name currently remains
[`dielessen/open_thermostat`](https://github.com/dielessen/open_thermostat).

## What we are building

The goal is one coherent, local heating system rather than a collection of
separate thermostat controllers:

- **E32 V2 firmware as the control core:** room targets and schedules, coordinated
  zone and boiler demand, bounded control decisions and native EMS communication.
- **Home Assistant as the configuration and device layer:** select existing room
  sensors, optional wall controls, TRVs and supported heating actuators.
- **A consistent user interface:** room configuration, weekly schedules, clear
  applied/pending/error feedback, diagnostics and measured heating history.
- **Modern heating functions under development:** weather-dependent water targets,
  radiator and optional floor-heating profiles, adaptive learning and preheating.

These are product goals, **not a claim that the complete system is already
implemented, installed or physically validated**.

No separate SAT, Versatile Thermostat, Better Thermostat or EMS-ESP controller is
required by the intended architecture. We retain useful existing code and use
maintained platform components instead of rewriting every dependency. Devices
connected through Home Assistant still depend on HA and the local MQTT broker;
local operation does not make those devices independent of either service.

## Development status

**Experimental — not a production-ready heating release.** The integrated
multi-zone product, actuator/boiler operation, learning benefits, complete UI and
recovery/failure behaviour still require acceptance. Experimental alpha packages
and limited device checks must not be mistaken for a finished heating system.

The published `main` branch contains the initial E32 V2 adaptations and reference
documentation. It does **not** contain every newer development change or provide
a complete snapshot of the firmware/integration currently being developed.
[PR #1](https://github.com/dielessen/open_thermostat/pull/1) records the initial port.
Use each [release's own notes and matching source](https://github.com/dielessen/open_thermostat/releases)
to identify what that particular test package contains.

> **E32 V2 heating outputs remain locked in the published experimental baseline.**
> EMS TX, forwarding and reset breaks cannot be enabled through runtime settings.
> Generic GPIO/relay/valve outputs, I2C, wired RTC and startup LED are disabled on
> this target. Software demand is not proof of a running burner or an open valve.
> Do not replace a working heating installation on the strength of this README.

## Origins and licensing

The original OpenThermostat code is by **Pawel Filipczak / intuibase** and is
provided under the [MIT license](LICENSE). We preserve the original copyright
and license notices. Our independent development does not imply that we wrote
all inherited code from scratch. Third-party libraries, SDKs and other reused
components retain their own licenses and applicable distribution obligations.

## Start here

- [Easy flashing guide, backup and restore](docs/FLASHING.md)
- [E32 V2 hardware, pinout, limitations, backup and recovery](docs/BBQKEES_E32V2.md)
- [Executed software builds/tests and remaining physical gates](docs/BBQKEES_E32V2_VALIDATION.md)
- [Original versus E32 V2 hardware](docs/HARDWARE.md)
- [Current REST API and E32 V2 restrictions](docs/RESTAPI.md)

## Published main-branch target capabilities

| Capability | Original `esp32dev` / `esp32s3` | Experimental `e32v2` |
| --- | --- | --- |
| Boiler EMS TX / forwarding | Existing upstream behavior | Hard blocked; RX can be configured, unvalidated |
| Relay / wired zone outputs / I2C RTC | Existing configured hardware | Disabled; no safe expansion wiring assumed |
| BLE room sensors / schedules / curves | Existing functionality | Code retained; no hardware/comfort validation |
| Networking | Existing WiFi / configuration AP | LAN8720 + WiFi/AP paths implemented; unvalidated |
| MQTT / HA / web / REST / NTP / OTA | Existing functionality | Code retained/adapted; runtime unvalidated |
| Filesystem | `esp32dev`: one slot; `esp32s3`: two slots | Two slots; inert board-specific defaults |

E32 V2 is the **classic ESP32**, not ESP32-S3: 16 MB flash and 8 MB physical
PSRAM (normally about 4 MB directly usable). It is not the old E32 model.
Ethernet uses the official LAN8720/GPIO0 output-clock configuration; Espressif
warns about simultaneous WiFi/Ethernet stability with this older Arduino core.
The implemented fallback is not evidence that either interface works on a device.

## Build E32 V2 without accessing hardware

Clone this fork; its default `main` contains the E32 V2 target:

```sh
git clone https://github.com/dielessen/open_thermostat.git
cd open_thermostat
python3 -m venv ~/.venvs/open-thermostat-pio
. ~/.venvs/open-thermostat-pio/bin/activate
pip install platformio==6.2.0
pio run -e e32v2
pio run -e e32v2 -t buildfs
python scripts/verify_e32v2.py
python scripts/test_e32v2_verifier.py
pio test -e native
```

These commands build/check files only; they do not flash a device. Firmware and
filesystem images are generated under `.pio/build/e32v2/`. Run PlatformIO commands
sequentially in one checkout. The original targets remain buildable with
`pio run -e esp32dev` and `pio run -e esp32s3`.

The E32 filesystem stages upstream web assets with board-specific safe settings:
EMS/forwarder/RTC/MQTT initially off, correct fixed EMS pins, no wired outputs and
no sample rooms. It does not edit the shared `data/` directory. Configure real
rooms and MQTT for a later authorized bench test; an empty HA room list is
expected until configured. No GPIO/configuration setting unlocks physical outputs.
Before any future installation, follow the [backup and recovery gates](docs/BBQKEES_E32V2.md#backup-before-any-future-physical-experiment).
A firmware-only OTA cannot install the new partition layout.

![Original project interface — reference image, not the new product GUI](docs/img/screen.jpg)

**Original targets:** OpenThermostat can control the boiler using an ON/OFF relay or directly via the EMS2 protocol (e.g., via the EMS interface board from [EMS Interface Board](https://bbqkees-electronics.nl/product/ems-interface-board-v3-1/)).

## Independent maintenance and upstream references

[The original OpenThermostat project](https://github.com/intuibase/open_thermostat)
remains the acknowledged starting point. Its future releases, roadmap or
maintainer approval are **not prerequisites for our own development or releases**.
We may review and selectively reuse useful upstream fixes, with their notices
and appropriate verification; importing them is a project decision, not a required
runtime dependency.

Our firmware and HA integration are developed as one product. Independence means
owning those engineering and maintenance decisions, not discarding working code,
removing platform dependencies or claiming third-party support.
The detailed sections below describe the existing published baseline and inherited
features; they are not a completion checklist for the newer product roadmap.

## Original project features

The following describes the upstream thermostat design, not a promise that all
features are enabled or physically verified on E32 V2. Use the target matrix above.

- Remote temperature reading of rooms via Bluetooth from Xiaomi thermometers (displaying temperature, battery status, and humidity)
- Configuration and access through WIFI - web interface
- Support for battery-powered real-time clock
- NTP time synchronization
- Sending status and temperature via MQTT
- Integration with Home Assistant
- Can work with any boiler as a simple ON/OFF thermostat
- Compatible with EMS2 compliant boilers
- Ability to read external temperature from EMS2 boilers
- Ability to read external temperature from the internet using OpenWeather data (weather display on web interface)
- Displaying the status of EMS2 boilers, such as operating mode, temperatures, system pressure, etc.
- Ability to freely configure the heating curve for EMS2 compliant boilers
- Ability to configure any number of programs
- Ability to set room temperatures with an accuracy of 0.1°C
- Ability to override the basic configuration for a circuit (room) at any time for any selected days of the week
- Ability to forward EMS2 packets (allows connection of a second EMS32 board with EMS-ESP32)
- REST API

## Home Assistant climate panels

**Published main-branch E32 V2 baseline:** the integration code is retained, but MQTT defaults to disabled and
the staged room catalog is empty. Runtime HA/MQTT operation remains untested.
An accepted target-temperature change or a displayed `boilerStarted` /
`hvac_action` value represents software demand, **not actual boiler activation**
when EMS TX and wired outputs are locked. This firmware has its own MQTT schema;
it is not a drop-in producer of EMS-ESP topics.

Copy `ha/config/custom_components/open_thermostat` to the `custom_components` directory in your Home Assistant configuration and restart Home Assistant. With the MQTT integration enabled, Home Assistant should discover **OpenThermostat** from the existing `<MQTT base>/room_data` messages. Confirm the discovered integration once; it will then add room entities as rooms appear. You can also add the integration manually and enter the MQTT base configured in the thermostat (`ib-therm` in this project's configuration).

The **OpenThermostat** integration contains a main device with memory, uptime, boiler energy, water usage, and outdoor temperature sensors, plus one thermostat device per room. Each room device contains a climate entity and sensors for current temperature, temperature set by the program, humidity, battery, program name, heating enabled, and heating activity when the thermostat reports those values. Room devices are named `OpenThermostat — <room name>` so their generated entity IDs remain distinguishable from unrelated devices in the same room. Temperature set, battery level, and program name are also available as attributes of the climate entity. Room entities use the permanent ID from `rooms.json`; messages without room IDs are ignored.

The firmware setting **Publish Home Assistant MQTT Discovery** controls whether the thermostat also creates standard MQTT entities. Leave it disabled when using the custom integration to avoid duplicate readings. MQTT state topics continue to be published when Discovery is disabled, so the custom integration keeps working. Enable it when the thermostat should integrate with Home Assistant without the custom integration. Configuration files that predate this setting retain the previous behavior and publish Discovery.

The integration includes light and dark brand images in `brand/`. Home Assistant 2026.3 or newer loads them directly from the custom integration directory, so copy the complete `open_thermostat` directory when updating it.

During setup, you can choose to create a separate **OpenThermostat** dashboard in the HA sidebar. For an integration already installed, open **Settings → Devices & services → OpenThermostat → Configure** and enable **Create an OpenThermostat dashboard**. Its first view contains a standard thermostat card for each room reported over MQTT. The diagnostics view contains separate device diagnostics and EMS information cards. The EMS card includes energy, water, temperatures, pressure, burner power, boiler display and service codes, plus the available burner, pump, fan, heating, hot-water, siphon-filling and venting states. These entities remain visible as unavailable when the thermostat has no current reading. View titles follow the Home Assistant language for Polish and English installations. The integration updates the dashboard when rooms or entity IDs change and removes the sidebar panel when the option is disabled. It manages the contents of this dashboard, so edits to its cards can be replaced by the next update. Other HA dashboards are untouched.

The dashboard also contains a **Heating** view. Every room has a **Radiator rated power** number entity that can be filled in later with the combined EN 442 rated output of its radiators at ΔT50. The integration counts radiator heating time only while the room is being heated, the boiler reports space heating active, and domestic hot water is inactive. With rated power configured, it estimates current radiator output and cumulative room energy from the boiler flow temperature, room temperature, a 10 °C assumed return-temperature drop, and the standard radiator exponent 1.3. The time and energy counters are restored after a Home Assistant restart and are marked as total-increasing statistics.

Changing the target temperature in an HA climate panel creates a temporary override on the thermostat. Each room has a **Temperature override duration** number entity (10–720 minutes, default 120) that controls the next change. HA sends a non-retained JSON command to `<MQTT base>/command/temporary` with `requestId`, `roomName`, `temperature` in hundredths of a degree Celsius, and `validSeconds`. New firmware validates the command, applies the override, replies on `<MQTT base>/response/temporary`, and immediately publishes updated `room_data`. HA reports an error if the thermostat rejects the command or does not reply within 10 seconds. The thermostat's program configuration remains unchanged. Upload the new firmware before using this control from HA.

The climate `hvac_action` uses the same condition as the thermostat web UI's flame icon: `shouldContinueHeating` for that room and `boilerStarted` for the boiler. New firmware publishes `boilerStarted` in `room_data`; with older firmware the climate entity falls back to `isBeingHeated`. The separate **Heating** binary sensor keeps the thermostat's original `isBeingHeatedState` value, based on the boiler and the room valve. The optional dashboard shows the current temperature below the target temperature on each thermostat card. For a manually created dashboard, use this card configuration (the climate details popup uses a different layout):

```yaml
type: thermostat
entity: climate.openthermostat_biuro
show_current_as_primary: false
```

The `room_data` MQTT message includes each room's `currentProgram` and `temporaryProgramSecondsLeft`. New firmware also publishes `activeProgram` at the top level. The integration displays a temporary override first, then a room-specific program, then the active main program. Upload the new firmware to make the main program available for rooms without a room-specific program.

For low battery alerts, copy `ha/config/custom_components/open_thermostat/blueprints/low_battery.yaml` to `<HA config>/blueprints/automation/open_thermostat/low_battery.yaml`. In **Settings → Automations & scenes → Blueprints**, create an automation from **OpenThermostat - low room battery**. Select the room battery sensors, set the percentage threshold, and choose the notification action. The default action creates a persistent HA notification; it can be replaced with a mobile notification action. The blueprint ignores `-1` (no battery reading) and alerts when a valid level first falls below the threshold or returns low after an unavailable reading. Home Assistant does not load blueprints directly from `custom_components`.

## Room and program configuration

Rooms and heating programs are stored separately. `data/cfg/rooms.json` contains each room's permanent eight-character ID, name, temperature sensor and valves. Files in `data/programs` refer to rooms by `room_id` and contain only heating settings. Programs do not share room settings with one another.

The web interface provides separate **Rooms** and **Programs** tabs and separate save buttons. Creating a room generates its permanent ID. Renaming or reordering the room does not change that ID. A program can only add settings for a room that already exists in the room catalog.

This firmware only supports the separated format; `/cfg/rooms.json` is required.
For the original targets, build the matching filesystem from the versioned
`data` directory. For **E32 V2**, `pio run -e e32v2 -t buildfs` instead generates
the safe staged filesystem described above. Do not substitute a generic or S3
image, or copy the upstream example GPIO configuration onto the gateway. Building
a filesystem is not authorization to install it; follow the E32 backup/recovery
and physical-test gates before a separately planned installation.

## Filesystem OTA

The `esp32s3` and `e32v2` partition tables each contain two equal SPIFFS slots. A filesystem OTA update is written sector by sector to the inactive slot while the current slot remains mounted. The firmware checks the complete byte count, mounts the uploaded image, verifies required UI and configuration files, and only then records the new slot in NVS for the next reboot. If the selected slot cannot be mounted during startup, the firmware automatically falls back to the other slot.

The classic 4 MB ESP32 keeps one SPIFFS partition because there is not enough flash for two useful slots. It uses the same incremental erase, size checks, and filesystem validation, but an interrupted upload can still damage its only filesystem. The firmware provides a dependency-free recovery page at `/recovery`; when SPIFFS cannot be mounted, `/` displays that page as well.

**Original ESP32-S3 hardware only — not E32 V2 instructions.** Moving an existing ESP32-S3 installation from the old single SPIFFS partition to the dual-slot layout requires one USB deployment because application OTA does not update the partition table:

```bash
pio run -e esp32s3 -t upload
pio run -e esp32s3 -t uploadfs
```

After that **S3** migration, filesystem updates can use the web UI. Always upload the `spiffs.bin` built for the same hardware environment. The server requires the image size to match its target partition exactly: 589,824 bytes for `esp32dev` and 4,653,056 bytes for each dual-slot `esp32s3` / `e32v2` layout. E32 OTA/recovery is not hardware-tested; initial migration from EMS-ESP needs the separate [E32 backup/recovery procedure](docs/BBQKEES_E32V2.md), not the S3 commands above.

The firmware publishes room IDs in `room_data`, and the custom Home Assistant integration uses them as stable device and entity identities.

MQTT Discovery also uses the permanent room ID instead of the room's array position. For example, with MQTT base `ib-therm`, room ID `d29a8f11` produces `sensor.ib_therm_d29a8f11_current_temperature`. The MQTT base is sanitized only where Home Assistant requires an entity ID (`ib-therm` becomes `ib_therm`); MQTT topics and unique IDs continue to use the configured value.

After upgrading from index-based Discovery, inspect the retained messages that belong to the old OpenThermostat configuration:

```bash
./tools/cleanup_open_thermostat_mqtt.sh MQTT_BROKER_HOST MQTT_BASE
```

Run the command again with `--execute` before the host to clear the listed retained messages, then restart the thermostat so it publishes the current Discovery configuration. The script accepts `MQTT_PORT`, `MQTT_USERNAME`, and `MQTT_PASSWORD` through the environment. It does not modify the Home Assistant entity registry or recorder history.

## Disclaimer

This project is provided "as is" without any guarantees or warranty. In association with the product, the developer makes no warranties of any kind, either express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, of title, or of noninfringement of third party rights. Use of the product by a user is at the user’s risk. In no event shall the developer be liable for any damages, including but not limited to direct, indirect, special, incidental, or consequential damages, losses, or expenses arising in connection with the use of this project.

## ⚠️ Safety Note

**Hardware-specific guidance:** the high-voltage warning below concerns the
original DIY mains-powered relay/actuator assembly. It is **not** an instruction
to connect mains voltage to a BBQKees gateway. E32 V2 uses the manufacturer's
EMS/power interface; never connect ESP32 GPIOs directly to the EMS bus. Follow
[the E32 V2 guide](docs/BBQKEES_E32V2.md) for that board.

**WARNING: The original relay/actuator assembly can operate at high voltage (110V / 230V)**

The original DIY thermostat assembly can operate at high voltages, including 110V or 230V. The system includes components such as a power supply, relays, and valve actuators, which can pose a risk to health and life if improperly installed or used.

**WARNING: Installation and operation of this device should only be performed by individuals with the appropriate qualifications and certifications, in accordance with the regulations applicable in their country.**

The creators of this project disclaim all responsibility for any damages, injuries, material losses, or other consequences resulting from improper use, installation, or maintenance of the device. The user assumes full responsibility for complying with local regulations regarding the operation of electrical devices. This includes, but is not limited to, any potential damage to heating systems, such as boilers, resulting from incorrect use or installation.

**Recommendations:**
1. Ensure that the power supply is disconnected before starting the installation.
2. Always follow local electrical codes and the manufacturer's recommendations.
3. Consult a qualified electrician if you have any doubts regarding the installation or operation of the device.

Failure to follow these recommendations may result in serious injury or death. Installation and use of the device are at the user’s own risk.
Depending on the method chosen for implementing the hardware part, the project may require working with high voltages, such as 230V. This requires proper qualifications and adherence to regulations in the respective country.
