# Boiler capability profile

The boiler profile records which boiler fields a particular boiler actually has.
The E32 learns this passively from the boiler's own reports, so Home Assistant and
the E32 pages only show values the boiler can deliver. For example, a boiler
without a digital pressure sensor does not get a "Water pressure" tile that stays
unavailable forever. The mechanism contains nothing specific to one brand, model
or installation.

Source: `src/EMS/BoilerProfile.h` (rules and persistence),
`src/EMS/BoilerProfileReport.h` (JSON), `ha/.../boiler_fields.py` and
`v1_boiler_fields.py` (Home Assistant).

## Fields and states

The profile covers every boiler field Home Assistant knows:

- the 69 Classic fields, wire index 0..68;
- the entity catalog fields (`src/EMS/EmsEntityTable.h`), wire index 70 and up.
  These are the EMS+ boiler monitors, the room thermostat rows and the UBA records.

Each field has one of four states:

| State | Rule |
|---|---|
| `supported` | At least one valid value was seen. This state is sticky: a sensor that fails later reads unavailable, not "not fitted". |
| `not_fitted` | The telegram that carries the field arrived at least 10 times over at least 10 minutes, and every time the decoder found no value. |
| `not_reported` | The telegram that carries the field has never been seen. Some telegrams only arrive when another controller asks for them, or only in some states (for example a fault record). |
| `unknown` | The telegram was seen, but there are too few observations to decide. |

A field becomes `supported` as soon as one valid value arrives, even if it was
`not_fitted` before. A sensor fitted later therefore shows up automatically.

## Sentinel rules per field type

There is no guessing. The profile uses the decoder's own verdict for each frame
that contains the field (`FieldEvidence`):

| Field type | "No value" (counts towards not_fitted) | Proves nothing |
|---|---|---|
| Unsigned byte (temperatures in °C, %, codes) | `0xFF`, or above the field's documented maximum | — |
| Signed byte (hysteresis) | `0x7F` | — |
| Temperature word (0.1 °C) | `0x8000`, `0x7FFF`, or outside −60..130 °C (for example `0x7D00`; exhaust up to 500 °C) | — |
| Ionisation current word | `0x7D00`, `0x7FFF`, `0x8000`, `0x8300`, `0xFFFF` | — |
| 3-byte counter (UBA) | `0xFFFFFF` | `0` (see below) |
| On/off byte (`heating_enabled`, …) | anything other than `0x00`/`0xFF` | — |
| Display code (two ASCII characters) | a non-printable character | — |
| Service number word | `0xFFFF` | — |
| Catalog `u8`/`u16`/`s16`/`u24` | `0xFF` / `0x8000`, `0x7FFF`, `0xFFFF` / `0x8000`, `0x7FFF`, `0x7D00` / `0xFFFFFF`, or outside the row's raw range. EMS+ return temperature and pressure use 0 for "no sensor", so their range starts at 1. | — |
| Raw bits, unreliable OEM counters and DHW flow | the field's sentinel | `0`: adapters such as the EasyControl fill bytes they do not support with `00`. A field that only ever reads 0 stays `unknown` and never becomes `not_fitted`. |

The same table drives the values themselves: a field the profile calls
`not_fitted` never had a usable value in Home Assistant either.

## Boiler identity and starting again

The profile belongs to the boiler at address 0x08:

- **Version telegram.** When the boiler's version telegram (0x02 from 0x08) is
  received passively, for example because another controller asked for it, its
  product ID and version are recorded. If a different product ID or version
  arrives later, that is another boiler and the profile starts again.
- **Protocol family.** Without a version telegram, the profile stores the
  protocol family (Classic or EMS+). If the first boiler report after a restart
  is from a family the stored boiler never used, that is another boiler and the
  profile starts again. A boiler that sends both families in one run is recorded
  as `mixed` and is never mistaken for a new boiler.

The E32 never sends anything on the bus for this.

## Persistence

NVS namespace `ot_boiler`, key `profile`: one blob of about 50 bytes. It holds the
identity, 2 bits of state per field, 1 "show anyway" bit per field, and the
`settled` flag. A record written by older firmware with fewer catalog fields
restores those fields, because the catalog only grows at its end. Any other
invalid record is ignored.

Writes happen only after a classification change. Once nothing has changed for
30 seconds the record is written, and then at most once every 5 minutes. An
owner's "show anyway" is written at once. Each field moves at most
not_reported → unknown → not_fitted → supported, so writes stay few even on a
new boiler.

The profile is `settled` once the boiler has been heard for the not-fitted span
(10 minutes). The flag is persisted.

## Interfaces

- `GET /status/boiler/profile`: the identity, rules, counts, `settled`, write
  statistics, and per field `{index, name, state, last_valid_age_s, shown_anyway?}`.
- `POST /config/boiler-profile` `{"index": n, "show": bool}`: the owner's
  "show anyway" for a `not_fitted` field. HA then treats it as supported.
- MQTT, retained `fw/config/boiler_profile` (under 1 KB): `{"schema":1,
  "boiler":{address, family, product_id, version}, "supported":[…],
  "not_fitted":[…], "not_reported":[…], "settled":bool}`, with wire indexes.
  A field in none of the lists is `unknown`. The topic is published by
  `TelemetryPublisher` through the boiler-fields source at
  `boilerProfileGroup` (255). The publisher checks it every 10 s and sends it only
  when it changed.

## Home Assistant

An EMS+ field and its Classic twin are one value (F28). Their combined state is
`supported` if either field is, otherwise `unknown` if either is, otherwise
`not_fitted` if either is, and otherwise `not_reported`.

| Combined state | Entity |
|---|---|
| supported | Created at once, also before HA saw the value (no gap after a restart). |
| unknown | Created on the first real value, as without a profile. |
| not_fitted | Never created. An existing record is removed if the user never touched it (no name, icon, area, label, hidden or user-disabled state) and it never delivered a real value (`REPORTED`). Otherwise it stays, unavailable, with `availability_reason: not_fitted`. |
| not_reported | Created disabled once the profile is settled, and marked `not_reported_placeholder` so the setup cleanup keeps it. It is enabled and marked `REPORTED` on its first real value, and removed if it becomes not fitted. |

Unique IDs never change. Without a profile (older firmware), nothing changes.
Each entity's `boiler_profile` attribute names its state.

The dashboards call `v1_boiler_fields.boiler_field_shown(hass, entry_id, field)`.
It is false for a value this boiler does not have (anything but supported),
and true without a profile.

## EMS+ (1.1)

EMS+ needs no second mechanism. EMS+ boiler telegrams (0xE4, 0xE5, 0xE9, 0xE6,
0xEA, …) are catalog rows, and `EmsEntityObserver` reports every row's verdict to
the same profile. New EMS+ fields are added as new rows at the end of the
`entityCatalog`, with a raw range that excludes their "no sensor" value. This
gives them their wire index, their sentinel rule and their profile state. A stored
profile from older firmware keeps its states, and the new fields start as
not_reported. The family rule above already recognises an EMS+ boiler. The
product ID from the EMS+ version telegram identifies the boiler in the same way.
