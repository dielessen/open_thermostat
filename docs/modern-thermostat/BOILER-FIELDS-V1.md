# Native passive boiler fields v1

Prepared source for the next combined release; not installed on alpha18/dev24.
The existing session owner publishes `fw/telemetry/boiler_fields` over the same
native MQTT connection. No new client, worker, subscription or bus request.
The existing `fw/#` listener dispatches this read-only branch.

## Contract and bounds

Capability `boiler.fields.v1` is optional and independent of metrics v2.
The envelope uses the current controller/boot/epoch/configuration/adapter/session/
grant scope, a strictly increasing sequence, group 0–6, mode `shadow`, both output
flags false and `values`. Unknown envelope keys are rejected. Retained data is
ignored. Missing capability or control-session admission leaves fields unavailable.

`values` has exactly `schema:1`, `sampled_at_ms`, `profile` and `fields`.
Each field is `[id, raw_or_null, original_observed_ms_or_null, quality, source_type]`.
IDs 0–68 are immutable and match the Classic monitor's existing order. The fixed
unit/divisor/TTL/type/quality schema is compiled into both peers, not supplied by
a message. Quality 0=reported, 1=unreliable, 2=inferred. Only the existing five
Classic types are decoded. The family must be `classic_observed` for availability.
The Plus decoder remains separate; these 69 IDs do not promise Plus coverage.

One group contains at most ten fields, at most 1,200 source JSON bytes and 2,048
envelope bytes. The owner attempts one group every two seconds; seven groups
normally cycle in fourteen seconds. Getter errors skip that attempt. Missing
fields/groups never become synthetic zeroes. Disabled EMS emits no groups.
The existing 8,448-byte MQTT packet buffer and metrics-v2 validator are unchanged.

## Age and failure handling

Firmware preserves the UART acquisition timestamp, including partial frames.
HA subtracts the source age at publication from each field's fixed TTL and counts
its own elapsed time from MQTT arrival, including time queued in the existing
worker. A repeated acquisition cannot extend its first deadline, even with a new
publication sequence. Changed data under an unchanged acquisition, reversed source
clocks, invalid source type/quality/range, foreign scope and old sequences are
rejected. No field-group stream for twenty seconds also suppresses availability.
The two-second existing runtime notification checks expiry; no new timer is added.

Network transit time before MQTT arrival is not independently measured. Attributes
state this age basis explicitly. These are read-only diagnostics, not qualified
room samples, actuator readiness, flame confirmation or authorization to heat.
Receiving telemetry does not renew heartbeat, grant, lease, room data or models.
Disconnect/source change resets the cache. A malformed read-only group suppresses
field availability without resetting a valid control session.

## Home Assistant presentation

The sensor platform adds 69 stable `boiler_fields_v1` identities only when the
capability is advertised, under the existing controller/installation device.
This preserves legacy entity/statistic identities. Temperatures, pressure,
modulation, ionisation and settings use fixed units and raw scaling. The display
code is decoded from two printable bytes. Unknown/stale/unreliable values stay
unavailable. Unreliable bits and OEM counters are disabled by default and labelled
as diagnostics; none of these entities declares statistical counter semantics.
Every entity exposes quality, original observation time, source type, profile and
`control_qualified:false`. Neither these entities nor the transport can write a
boiler setting. Actual field support still depends on received model-specific data.

## Verification boundary

Native tests exercise all 69 real monitor fields, bounded serialization, session
admission and malformed getters. HA tests exercise cache age/replay/queue delay,
scope/retained/schema rejection, all-field scaling, listener cleanup and disabled
mode. A finite actual C++ controller exchanges all seven groups with the real HA
client and entities. The full native/HA suites and all board builds are checked
before source handoff; real deployment and physical field comparison remain open.
