# Hardware

## BBQKees Gateway E32 V2 — experimental native target

Use the separate `[env:e32v2]` build, not `esp32s3` or the old E32 board profile.
The E32 V2 is a classic ESP32 with 16 MB flash, PSRAM and LAN8720 Ethernet.
The [E32 V2 guide](BBQKEES_E32V2.md) is the canonical source for official pinout,
PHY/clock configuration, revision differences, unknown electrical details,
backup/recovery and the required physical tests.

**This port is not hardware validated and cannot control a boiler:** EMS TX,
forwarding/reset breaks and local GPIO/relay/valve/I2C/RTC outputs are locked.
The generic `cfgpins.json` examples and the parts/wiring below do not apply to
this gateway. No external relay, RTC, second ESP32 or mains actuator wiring is
required or enabled by the native gateway target. There is no automatic migration
from EMS-ESP or setting to unlock transmission. Do not flash or connect to a
boiler based on this component list.

## Original upstream DIY thermostat assembly

The following is the upstream author's original build, retained for users of
the original targets. It is **not the E32 V2 bill of materials or wiring diagram**.

In building my project, I used the following components:

- [EMS interface board v3.1 from BBQKEES](https://bbqkees-electronics.nl/product/ems-interface-board-v3-1/)
- Relay board with optical isolation, capable of being controlled by 3.3V
- ESP32 development board, two units, the second one for handling [EMS-ESP32](https://github.com/emsesp/EMS-ESP32)
- RTC clock module
- Phone charger as the cheapest 230V->5V converter
- Microphone sockets and plugs - for powering the actuators
- Microphone sockets and plugs - for connecting the EMS boiler and outside temperature sensor
- Power socket (computer type) with a 1A fuse
- External WIFI/BT antenna - for increased range
- 3D printed enclosure
- Herz thermal actuators powered by 230V, normally open

![Microphone sockets and plugs - for powering the actuators](img/actuator_connectors.jpg)
![Microphone sockets and plugs - for connecting the EMS boiler and outside temperature sensor](img/emsbus_and_temp_sensor_connetor.jpg)
![Relays and PSU](img/relays_and_psu.jpg)
![Beta version wiring](img/wiring.jpg)