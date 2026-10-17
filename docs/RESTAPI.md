# REST API

This reference describes the routes registered in [src/REST.h](../src/REST.h).
The old `/cfg/...` and `/room?cmd=...` examples do not describe the current API.
These are source-checked interface descriptions, not results of on-device tests.

The web UI and API use the same HTTP listener on the configured port. On E32 V2,
Ethernet/WiFi handling is implemented but hardware operation is unvalidated.
The current server has no active authentication guard; keep it on a trusted
network. JSON configuration writes use the HTTP request body, not password or
configuration query-string parameters. Use the existing web UI for complete
payload examples; this page is not an installation or boiler-test procedure.

## Read/status routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/status` | Combined thermostat status |
| GET | `/status/boiler` | Software boiler/controller status |
| GET | `/status/ems` | Available EMS telemetry/state |
| GET | `/params/boiler` | Available EMS boiler parameters (read, not a write endpoint) |
| GET | `/status/rooms` | Room temperatures and heating status |
| GET | `/status/devices` | Discovered temperature-sensor devices |
| GET | `/status/programs` | Available programs |
| GET | `/status/version` | Firmware build/version/hash |
| GET | `/status/wifi` | WiFi network scan; not Ethernet link status |

## Configuration routes

| Methods | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/config/wifi` | Read SSID / save WiFi JSON configuration |
| GET, POST | `/config/device` | Read/save network and device configuration |
| GET, POST | `/config/boiler` | Read/save boiler configuration |
| GET, POST | `/config/hardware` | Read/save pin/expander configuration |
| GET, POST | `/config/debug` | Read/save logger feature settings |
| GET, POST | `/config/rooms` | Read/save the room catalog |
| GET, POST, DELETE | `/config/programs/{name}` | Read/save/delete a program, case-sensitive name without `.json` |
| GET, POST | `/config/program/current` | Read/save the selected main program |
| POST | `/config/temporary` | Temporary room-temperature override |

Room catalog entries have stable eight-character hexadecimal IDs; program entries
refer to existing rooms using `room_id`. Catalog changes conflicting with saved
programs are rejected. See the [room/program format](../README.md#room-and-program-configuration).
Some settings require a restart to take effect; successful persistence alone is
not proof that hardware was initialized or a setting is supported on the board.

`/config/temporary` takes `roomName`, integer `temperature` in hundredths of a
degree Celsius, and `validSeconds`. A successful request updates software demand;
it does not bypass board-level output locks. MQTT's temporary-override envelope
also supports `requestId`; do not assume the HTTP and MQTT response formats match.

## Hardware, restart and update routes

| Methods | Path | Purpose / E32 V2 behavior |
| --- | --- | --- |
| GET | `/hardware/i2c/scan` | I2C scan; **E32 V2 returns HTTP 403** |
| POST | `/hardware/test/gpio` | Start timed manual output test; **E32 V2 returns HTTP 403** |
| DELETE | `/hardware/test/gpio` | Stop the software manual-output test |
| GET | `/config/reboot` | **Restarts the device**; not a read-only health check |
| POST | `/ota` | Multipart firmware update, with image `size` and file |
| POST | `/otafs` | Multipart filesystem update, with image `size` and file |
| GET | `/recovery` | Filesystem-independent recovery page |
| GET | `/` | Main web UI, or recovery page when SPIFFS is unavailable |

On **E32 V2**, `emsEnabled` permits receive initialization only: EMS transmission,
forwarding and reset breaks remain hard blocked. `/config/hardware` may persist
JSON, but runtime wiring is fixed and configured GPIO/expander outputs are
ignored; saving configuration does not unlock I2C/RTC/relays. Likewise,
`boilerStarted`, heating activity and accepted temperature overrides are software
states, **not proof of real heat or successful EMS transmission**.

Update endpoints do not install a new partition table. Do not use them to migrate
an existing EMS-ESP installation to this layout. E32 network, OTA and recovery
have not been physically tested. Follow the [E32 hardware/backup/recovery gates](BBQKEES_E32V2.md)
before any separately authorized device experiment.
