# Controller request and boiler readback

The Ecomline Classic/EasyControl path observed on27October returned selected
flow0 in raw0x18 byte0 while the attended50C request ran the pump and burner.
This observation does not apply to every boiler and does not qualify a generic
fallback from zero. The existing received fields remain unchanged.

During that trial, the reported current flow temperature fell from59°C to
46°C, then rose towards50°C. The owner confirmed that the pump and burner
were running and later observed64°C. Cooler return water entering the boiler
when circulation starts is consistent with the initial fall. A period near
the requested50°C therefore does not establish that a command was copied into
the measured field. These are bus reports and operator observations, without
an independent temperature measurement. The follow-up trial must retain both
the original received telegrams and the separately completed UART requests.

`controller_request` is a separate record in the existing REST telemetry and
non-retained `ems_status` packet. It has schema1, the fixed Ecomline trial profile,
controller UART origin, boot ID, original completion timestamp, snapshot timestamp,
sequence, known flag and nullable Celsius value. Only a matching successful UART
completion records a value. Preparing/starting alone does not; a transmitted zero
records0. A new boot is unknown. This is not a boiler acknowledgement.

The existing HA product EMS status listener creates one read-only sensor for
this advertised profile. It adds no MQTT subscription, HTTP polling or writes.
Duplicate snapshots preserve original age; bad/retained/reordered snapshots are
unavailable. A new status may repeat historical command information without
making the original transmission new. The entity exposes that completion age.
A single local expiry callback bounds status freshness; unloading cancels it.

Software tests exercise unknown→zero→50→zero, failed transmission, independent
received curflow/selected-flow fields, new boot, duplicate/reordered/retained data,
clock changes, existing subscriber reuse and no publisher calls. The actual
E32/HA installation and complete next physical trial remain separate evidence.

The owner-requested follow-up method repeats50°C every60seconds for a fixed
ten-minute run. The firmware separates that positive cadence from short zero
retries. Start and withdrawal are immediate; supervision still expires after
five seconds. Each repeat is an actual UART write even when its value is
unchanged. Record completion timestamps and bus-poll delay in the real trial.
The existing command sensor retains original age between those transmissions.
[EMS-ESP maintainer's one-minute recommendation](https://github.com/emsesp/EMS-ESP32/issues/954)
is a starting interval, not evidence of this boiler's exact demand timeout.
